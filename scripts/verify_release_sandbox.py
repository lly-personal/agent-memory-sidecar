#!/usr/bin/env python3
"""Pre-tag Windows native Codex read-only sandbox verification gate for candidate releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
RECEIPT_CONTRACT = "agent_memory_pretag_sandbox_gate_v1"
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class SandboxGateError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SandboxGateError(code)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    entries = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and "__pycache__" not in item.parts:
            entries.append((item.relative_to(root).as_posix(), _sha256_file(item)))
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _default_run(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw, index)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("rc" in obj or "candidate_rc" in obj):
            return obj
    raise SandboxGateError("sandbox_gate_unparseable_codex_output")


def verify_candidate_in_codex_sandbox(
    *,
    root: Path = ROOT,
    commit: str | None = None,
    codex_home: Path | None = None,
    allow_dirty: bool = False,
    runner: CommandRunner = _default_run,
    codex_executable: str | None = None,
) -> dict[str, Any]:
    if not allow_dirty:
        dirty = runner(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"])
        _require(dirty.returncode == 0 and dirty.stdout.strip() == "", "sandbox_gate_source_dirty")

    resolved_commit = commit
    if not resolved_commit:
        head = runner(["git", "-C", str(root), "rev-parse", "HEAD"])
        _require(head.returncode == 0, "sandbox_gate_git_head_failed")
        resolved_commit = head.stdout.strip().casefold()
    else:
        rev = runner(["git", "-C", str(root), "rev-parse", "--verify", f"{commit}^{{commit}}"])
        _require(rev.returncode == 0, "sandbox_gate_commit_unresolved")
        resolved_commit = rev.stdout.strip().casefold()
    _require(SHA40.fullmatch(resolved_commit) is not None, "sandbox_gate_commit_invalid")

    codex_exe = codex_executable or shutil.which("codex") or shutil.which("codex.cmd")
    _require(bool(codex_exe), "sandbox_gate_codex_cli_missing")

    active_codex_home = codex_home or (Path.home() / ".codex")
    global_agents = active_codex_home / "AGENTS.md"
    project_agents = root / "AGENTS.md"
    before_global = _sha256_file(global_agents) if global_agents.is_file() else None
    before_project = _sha256_file(project_agents) if project_agents.is_file() else None

    temp_parent = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" if os.name == "nt" else Path(tempfile.gettempdir())
    temp_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="ams-pretag-gate-", dir=str(temp_parent)))
    src_dir = stage / "src"
    dist_dir = stage / "dist"
    venv_dir = stage / "venv"
    skill_root = stage / "skills"
    for folder in (src_dir, dist_dir, skill_root):
        folder.mkdir(parents=True, exist_ok=True)

    try:
        archive_path = stage / "candidate.tar"
        arch = runner(["git", "-C", str(root), "archive", "--format=tar", "-o", str(archive_path), resolved_commit])
        _require(arch.returncode == 0, "sandbox_gate_git_archive_failed")
        untar = runner(["tar", "-xf", str(archive_path), "-C", str(src_dir)])
        _require(untar.returncode == 0, "sandbox_gate_tar_extract_failed")

        build = runner([sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)], cwd=src_dir, timeout=180)
        _require(build.returncode == 0, "sandbox_gate_wheel_build_failed")
        wheels = sorted(dist_dir.glob("*.whl"))
        _require(len(wheels) == 1, "sandbox_gate_wheel_count_invalid")
        wheel = wheels[0]
        wheel_sha256 = _sha256_file(wheel)

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        vpy = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = runner([str(vpy), "-m", "pip", "install", "--no-deps", str(wheel)], timeout=120)
        _require(install.returncode == 0, "sandbox_gate_wheel_install_failed")

        if os.name == "nt":
            # Mirror real ~/.codex/skills parent inheritance so Windows CodexSandboxUsers can read staged Skill files.
            runner(["icacls", str(stage), "/grant", "CodexSandboxUsers:(OI)(CI)(RX)"])

        materialize = runner(
            [
                str(vpy),
                "-B",
                "-c",
                "from pathlib import Path; import sys; from agent_memory_sidecar.skill import install_skill; "
                "install_skill(root=Path(sys.argv[1]))",
                str(skill_root),
            ]
        )
        _require(materialize.returncode == 0, "sandbox_gate_skill_materialize_failed")

        skill_dir = skill_root / "agent-memory"
        candidate_entry = skill_dir / "scripts" / "agent-memory.py"
        _require(candidate_entry.is_file(), "sandbox_gate_installed_entry_missing")
        skill_sha256 = _tree_sha256(skill_dir)

        prompt = (
            "Execute this single read-only shell command and reply with ONLY one JSON object having keys "
            "candidate_rc, status, rules_count, pending_count, pending_status, stderr_tail: "
            f'python -B -S "{candidate_entry}" rule list'
        )
        probe = runner(
            [str(codex_exe), "exec", "-s", "read-only", "--skip-git-repo-check", "-C", str(root), "-"],
            input_text=prompt,
            timeout=120,
        )
        _require(probe.returncode == 0, "sandbox_gate_codex_exec_failed")
        observed = _extract_json_object(probe.stdout)
        _require(observed.get("candidate_rc") == 0, "sandbox_gate_candidate_nonzero_exit")
        _require(observed.get("status") == "ok", "sandbox_gate_candidate_status_not_ok")
        _require(isinstance(observed.get("rules_count"), int), "sandbox_gate_rules_count_invalid")
        if observed.get("pending_count") is None:
            _require(
                observed.get("pending_status") == "store_access_restricted",
                "sandbox_gate_unexpected_null_pending_status",
            )

        after_global = _sha256_file(global_agents) if global_agents.is_file() else None
        after_project = _sha256_file(project_agents) if project_agents.is_file() else None
        _require(before_global == after_global, "sandbox_gate_global_agents_mutated")
        _require(before_project == after_project, "sandbox_gate_project_agents_mutated")

        return {
            "contract_version": RECEIPT_CONTRACT,
            "status": "passed",
            "platform": sys.platform,
            "sandbox_mode": "read-only",
            "commit": resolved_commit,
            "wheel_name": wheel.name,
            "wheel_sha256": wheel_sha256,
            "skill_sha256": skill_sha256,
            "observed": {
                "candidate_rc": observed["candidate_rc"],
                "status": observed["status"],
                "rules_count": observed["rules_count"],
                "pending_count": observed.get("pending_count"),
                "pending_status": observed.get("pending_status"),
            },
            "protected_targets_unchanged": True,
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=False)
        _require(not stage.exists(), "sandbox_gate_temp_cleanup_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run pre-tag native Codex --sandbox read-only verification against a candidate commit."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--commit", default=None, help="Candidate commit SHA or ref (defaults to clean HEAD).")
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_candidate_in_codex_sandbox(
            root=args.root.resolve(),
            commit=args.commit,
            codex_home=args.codex_home.resolve() if args.codex_home else None,
            allow_dirty=args.allow_dirty,
        )
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (SandboxGateError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"contract_version": RECEIPT_CONTRACT, "status": "blocked", "error": str(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
