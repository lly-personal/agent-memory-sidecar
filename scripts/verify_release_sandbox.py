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
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _unwrap_shell_command(command_str: str) -> str:
    """Strip one outer shell wrapper (e.g. pwsh -Command / bash -c) to inspect the executed command."""
    text = command_str.strip()
    m = re.match(
        r'^(?:"[^"]*(?:pwsh|powershell|cmd|bash|sh)(?:\.exe)?"|\S*(?:pwsh|powershell|cmd|bash|sh)(?:\.exe)?)\s+(?:-Command|-c|/c)\s+(.+)$',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return text
    inner = m.group(1).strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in {'"', "'"}:
        quote = inner[0]
        inner = inner[1:-1]
        if quote == '"':
            inner = inner.replace('\\"', '"')
    return inner.strip()


def _extract_verified_command_execution(ndjson_text: str, candidate_entry: Path) -> dict[str, Any]:
    """Verify actual Codex --json command_execution output; never trust assistant prose."""
    entry_norm = re.sub(r"[\\/]+", "/", str(candidate_entry)).casefold()
    exact_cmd_re = re.compile(
        r"^(?:&\s*)?(?:[\"']?[^\"'\s]*python(?:3(?:\.\d+)?)?(?:\.exe)?[\"']?)\s+"
        r"(?:-[A-Za-z]+\s+)*"
        r"[\"']?" + re.escape(entry_norm) + r"[\"']?\s+rule\s+list\s*$",
        flags=re.IGNORECASE,
    )
    matched_events: list[dict[str, Any]] = []
    for raw_line in ndjson_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        inner_cmd = _unwrap_shell_command(str(item.get("command") or ""))
        inner_norm = re.sub(r"[\\/]+", "/", inner_cmd).casefold()
        if exact_cmd_re.fullmatch(inner_norm):
            matched_events.append(item)

    _require(bool(matched_events), "sandbox_gate_command_not_executed")
    item = matched_events[-1]
    _require(item.get("status") == "completed", "sandbox_gate_command_not_completed")
    _require(item.get("exit_code") == 0, "sandbox_gate_candidate_nonzero_exit")

    output = str(item.get("aggregated_output") or "").strip()
    try:
        envelope = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SandboxGateError("sandbox_gate_unparseable_command_output") from exc

    _require(isinstance(envelope, dict), "sandbox_gate_unparseable_command_output")
    _require(envelope.get("contract_version") == "agent_memory_result_v1", "sandbox_gate_contract_mismatch")
    _require(envelope.get("operation") == "rule.list", "sandbox_gate_operation_mismatch")
    _require(envelope.get("status") == "ok", "sandbox_gate_candidate_status_not_ok")
    data = envelope.get("data")
    _require(isinstance(data, dict) and isinstance(data.get("rules"), list), "sandbox_gate_rules_count_invalid")
    pending_count = data.get("pending_count")
    pending_status = data.get("pending_status")
    if pending_count is None:
        _require(pending_status == "store_access_restricted", "sandbox_gate_unexpected_null_pending_status")
    return {
        "candidate_rc": 0,
        "status": envelope["status"],
        "rules_count": len(data["rules"]),
        "pending_count": pending_count,
        "pending_status": pending_status,
        "verified_via": "codex_exec_json_command_execution",
    }


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

    if codex_home is not None:
        active_codex_home = codex_home
    elif os.environ.get("CODEX_HOME"):
        active_codex_home = Path(os.environ["CODEX_HOME"]).expanduser()
    else:
        active_codex_home = Path.home() / ".codex"
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
            "Execute this single read-only shell command verbatim and reply `done`: "
            f'python -B -S "{candidate_entry}" rule list'
        )
        probe_env = None
        if codex_home is not None:
            probe_env = dict(os.environ)
            probe_env["CODEX_HOME"] = str(active_codex_home)
        probe_kwargs: dict[str, Any] = {"input_text": prompt, "timeout": 120}
        if probe_env is not None:
            probe_kwargs["env"] = probe_env
        probe = runner(
            [str(codex_exe), "exec", "--json", "-s", "read-only", "--skip-git-repo-check", "-C", str(root), "-"],
            **probe_kwargs,
        )
        _require(probe.returncode == 0, "sandbox_gate_codex_exec_failed")
        observed = _extract_verified_command_execution(probe.stdout, candidate_entry)

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
            "observed": observed,
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
