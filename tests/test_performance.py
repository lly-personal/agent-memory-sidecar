from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent_memory_sidecar.database import CoreDatabase
from agent_memory_sidecar.identity import ProjectIdentity
from agent_memory_sidecar.runtime_ledger import RuntimeLedger
from agent_memory_sidecar.runtime_package import (
    build_runtime_artifact,
    install_runtime_artifact,
)

TRANSACTION_BUDGET_MS = 10.0
HOOK_SUBPROCESS_BUDGET_MS = 150.0


class PerformanceTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("AGENT_MEMORY_PERFORMANCE_MODE") in {"gate", "observe"},
        "performance requires an explicit gate or observation mode",
    )
    def test_runtime_transaction_and_hook_subprocess_p95(self) -> None:
        mode = os.environ["AGENT_MEMORY_PERFORMANCE_MODE"]
        rounds = 3
        transaction_p95: list[float] = []
        subprocess_p95: list[float] = []
        for _ in range(rounds):
            transaction, hook = _measure_runtime_p95()
            transaction_p95.append(transaction)
            subprocess_p95.append(hook)
        transaction_result = _median(transaction_p95)
        subprocess_result = _median(subprocess_p95)
        print(
            json.dumps(
                {
                    "contract_version": "agent_memory_performance_measurement_v1",
                    "mode": mode,
                    "transaction_p95_ms": transaction_p95,
                    "hook_subprocess_p95_ms": subprocess_p95,
                    "decision_transaction_p95_ms": transaction_result,
                    "decision_hook_subprocess_p95_ms": subprocess_result,
                    "transaction_budget_ms": TRANSACTION_BUDGET_MS,
                    "hook_subprocess_budget_ms": HOOK_SUBPROCESS_BUDGET_MS,
                    "transaction_within_budget": (
                        transaction_result <= TRANSACTION_BUDGET_MS
                    ),
                    "hook_subprocess_within_budget": (
                        subprocess_result <= HOOK_SUBPROCESS_BUDGET_MS
                    ),
                },
                separators=(",", ":"),
            )
        )
        _enforce_local_budget(
            mode=mode,
            transaction_result=transaction_result,
            subprocess_result=subprocess_result,
            transaction_p95=transaction_p95,
            subprocess_p95=subprocess_p95,
        )

    def test_hosted_observation_does_not_claim_local_qualification(self) -> None:
        _enforce_local_budget(
            mode="observe",
            transaction_result=50.0,
            subprocess_result=250.0,
            transaction_p95=[50.0],
            subprocess_p95=[250.0],
        )
        with self.assertRaises(AssertionError):
            _enforce_local_budget(
                mode="gate",
                transaction_result=50.0,
                subprocess_result=250.0,
                transaction_p95=[50.0],
                subprocess_p95=[250.0],
            )


def _measure_runtime_p95() -> tuple[float, float]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        codex_home = root / "codex"
        store = codex_home / "agent-memory-sidecar" / "memory.sqlite"
        project = root / "project"
        store.parent.mkdir(parents=True)
        project.mkdir()
        identity = ProjectIdentity(
            cwd=str(project),
            repo_root=str(project),
            branch=None,
            scope_key=str(project),
        )
        with CoreDatabase(
            store,
            create=True,
            now="2026-07-24T00:00:00+00:00",
        ) as db:
            RuntimeLedger(db).capture_prompt(
                identity=identity,
                source_session="performance-session",
                prompt="warmup",
                metadata={},
            )

        transaction_ms: list[float] = []
        with CoreDatabase(store, runtime=True) as db:
            ledger = RuntimeLedger(db)
            for index in range(60):
                started = time.perf_counter()
                ledger.capture_prompt(
                    identity=identity,
                    source_session="performance-session",
                    prompt=f"transaction {index}",
                    metadata={},
                )
                transaction_ms.append((time.perf_counter() - started) * 1000)

        artifact = install_runtime_artifact(
            artifact=build_runtime_artifact(),
            runtime_root=root / "runtime",
        )
        command = [
            str(Path(sys.executable).resolve()),
            str(artifact),
            "runtime-hook",
        ]
        environment = {**os.environ, "CODEX_HOME": str(codex_home)}
        subprocess_ms: list[float] = []
        for index in range(55):
            payload = json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "performance-session",
                    "cwd": str(project),
                    "scope_key": str(project),
                    "prompt": f"subprocess {index}",
                }
            )
            started = time.perf_counter()
            completed = subprocess.run(
                command,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=5,
                check=False,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            if index >= 5:
                subprocess_ms.append(duration_ms)
            if completed.returncode != 0 or not completed.stdout:
                raise AssertionError(
                    f"runtime hook failed: returncode={completed.returncode} stderr={completed.stderr}"
                )
        return _p95(transaction_ms), _p95(subprocess_ms)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _enforce_local_budget(
    *,
    mode: str,
    transaction_result: float,
    subprocess_result: float,
    transaction_p95: list[float],
    subprocess_p95: list[float],
) -> None:
    if mode != "gate":
        return
    if transaction_result > TRANSACTION_BUDGET_MS:
        raise AssertionError(
            f"transaction p95 rounds={transaction_p95} result={transaction_result}"
        )
    if subprocess_result > HOOK_SUBPROCESS_BUDGET_MS:
        raise AssertionError(
            f"hook subprocess p95 rounds={subprocess_p95} result={subprocess_result}"
        )


if __name__ == "__main__":
    unittest.main()
