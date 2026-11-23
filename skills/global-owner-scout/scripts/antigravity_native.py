#!/usr/bin/env python3
"""Ordinary Skill adapter for Antigravity: runtime context binding and local transcript capture."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from history_import import import_history
from scout import inspect_git_context, inspect_native_context
from scout_security import (
    is_reparse,
    is_within,
    pinned_directory,
    safe_artifact_bytes,
    safe_existing_directory,
    validate_output_root,
)
from utf8_stdio import configure_utf8_stdio
from validate_output import ContractError

SKILL_ROOT = Path(__file__).resolve().parents[1]
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TRANSCRIPT_CONTRACT = "global_owner_scout_native_transcript_v1"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def _valid_session_id(value: Any, error: str) -> str:
    _require(isinstance(value, str) and bool(value) and "<" not in value and ">" not in value, error)
    _require(SESSION_ID_RE.fullmatch(value) is not None, error)
    return value


def _valid_abs_dir(value: Any, error: str) -> str:
    _require(isinstance(value, str) and bool(value) and "<" not in value and ">" not in value, error)
    path = Path(value)
    _require(path.is_absolute(), error)
    return value


def _assert_physical_dir_chain(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts:
        current = current / part
        try:
            st = current.lstat()
        except OSError as exc:
            raise ContractError("antigravity_transcript_missing") from exc
        _require(not is_reparse(st) and stat.S_ISDIR(st.st_mode), "antigravity_transcript_not_regular")
    return current


def _load_transcript_steps(app_data_dir: Path, source_session_id: str) -> tuple[str, list[dict[str, Any]]]:
    base = safe_existing_directory(app_data_dir, label="app-data-dir")
    logs_dir = _assert_physical_dir_chain(base, ("brain", source_session_id, ".system_generated", "logs"))
    selected_kind: str | None = None
    selected_path: Path | None = None
    with pinned_directory(logs_dir) as logs_fd:
        selected_name: str | None = None
        for kind, filename in (("transcript_full", "transcript_full.jsonl"), ("transcript", "transcript.jsonl")):
            candidate = logs_dir / filename
            try:
                st = os.lstat(filename, dir_fd=logs_fd) if logs_fd is not None else candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ContractError("antigravity_transcript_not_regular") from exc
            _require(not is_reparse(st) and stat.S_ISREG(st.st_mode) and st.st_nlink == 1, "antigravity_transcript_not_regular")
            selected_kind = kind
            selected_path = candidate
            selected_name = filename
            selected_stat = st
            break
        _require(selected_kind is not None and selected_path is not None and selected_name is not None, "antigravity_transcript_missing")
        if logs_fd is not None:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(selected_name, flags, dir_fd=logs_fd)
                with os.fdopen(fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    _require(
                        stat.S_ISREG(opened.st_mode)
                        and not is_reparse(opened)
                        and opened.st_nlink == 1
                        and (opened.st_dev, opened.st_ino) == (selected_stat.st_dev, selected_stat.st_ino),
                        "antigravity_transcript_not_regular",
                    )
                    raw_text = stream.read().decode("utf-8-sig")
            except ContractError:
                raise
            except (OSError, UnicodeError) as exc:
                raise ContractError("antigravity_transcript_not_regular") from exc
        else:
            raw_text = safe_artifact_bytes(selected_path).decode("utf-8-sig")
    steps: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = json.loads(stripped)
        _require(isinstance(item, dict), "antigravity_transcript_step_invalid")
        steps.append(item)
    return selected_kind, steps


def _resolve_session_artifact_exemption(
    artifact_dir: Path,
    *,
    app_data_path: Path,
    session_id: str,
) -> dict[Path, Path]:
    resolved_dir = safe_existing_directory(artifact_dir, label="artifact-dir")
    if not is_within(resolved_dir, app_data_path):
        return {}
    try:
        session_dir = _assert_physical_dir_chain(app_data_path, ("brain", session_id))
        resolved_session_dir = safe_existing_directory(session_dir, label="artifact-dir")
    except ContractError:
        return {}
    if resolved_dir == resolved_session_dir:
        return {app_data_path: resolved_session_dir}
    return {}


def invoke_antigravity(
    *,
    operation: str,
    session_id: str,
    project_root: str,
    app_data_dir: str,
    artifact_dir: str | None = None,
    source_session_id: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    _require(operation in {"context", "capture"}, "antigravity_native_operation_invalid")
    _valid_session_id(session_id, "antigravity_native_runtime_info_required")
    _valid_abs_dir(project_root, "antigravity_native_runtime_info_required")
    _valid_abs_dir(app_data_dir, "antigravity_native_runtime_info_required")
    app_data_path = safe_existing_directory(Path(app_data_dir), label="app-data-dir")
    effective_cwd = cwd if cwd is not None else os.getcwd()
    native = {
        "contract_version": "global_owner_scout_native_context_v1",
        "native_host": "antigravity",
        "context": {
            "source_kind": "antigravity_runtime_info",
            "cwd": effective_cwd,
            "project_dir": project_root,
            "session_id": session_id,
            "app_data_dir": app_data_dir,
        },
    }
    if operation == "context":
        binding = inspect_native_context(native)
        return {"native_context": native, "native_binding": binding}

    _require(
        isinstance(artifact_dir, str) and bool(artifact_dir) and Path(artifact_dir).is_absolute(),
        "native_source_current_authorized_artifact_dir_required",
    )
    selected_source = source_session_id if source_session_id is not None else session_id
    _valid_session_id(selected_source, "antigravity_source_session_id_invalid")
    # Antigravity local JSONL transcripts do not carry an independent per-session cwd;
    # restrict capture to the currently bound session so historical sessions cannot be misattributed.
    _require(selected_source == session_id, "antigravity_historical_project_binding_unverified")

    # Bind git root lightly before checking output boundary so untracked project files
    # are never read prior to output authorization.
    binding = inspect_native_context(native, include_snapshot=False)
    bound_project = Path(binding["project_root"])
    strict_protected = [bound_project, SKILL_ROOT]
    # Enforce strict project and Skill write protection with zero exemptions first,
    # even if app_data_path aliases or coincides with project_root or SKILL_ROOT.
    validate_output_root(Path(artifact_dir), strict_protected)
    exempt_exact_roots = _resolve_session_artifact_exemption(
        Path(artifact_dir),
        app_data_path=app_data_path,
        session_id=session_id,
    )
    validate_output_root(
        Path(artifact_dir),
        [app_data_path],
        exempt_exact_roots=exempt_exact_roots,
    )
    # Collect full git snapshot after output authorization succeeds and before writing
    # any capture files, so missing HEAD or git errors never leave orphan artifacts.
    binding["git_snapshot"] = inspect_git_context(bound_project)

    transcript_kind, steps = _load_transcript_steps(app_data_path, selected_source)
    payload = {
        "contract_version": TRANSCRIPT_CONTRACT,
        "native_host": "antigravity",
        "session": {
            "id": selected_source,
            "cwd": str(bound_project),
            "transcript_kind": transcript_kind,
        },
        "steps": steps,
    }
    captured = import_history(
        payload,
        project_root=bound_project,
        session_id=selected_source,
        artifact_dir=Path(artifact_dir),
        protected_roots=[*strict_protected, app_data_path],
        exempt_exact_roots=exempt_exact_roots,
    )
    result: dict[str, Any] = {"native_context": native, "native_binding": binding}
    result["capture"] = {
        key: captured[key]
        for key in (
            "contract_version",
            "status",
            "native_host",
            "native_file",
            "sha256",
            "index_path",
            "record_count",
            "truncation_paths",
            "evidence_scope",
        )
    }
    result["source_session_id"] = selected_source
    result["transcript_kind"] = transcript_kind
    return result


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="antigravity_native.py",
        description=(
            "Antigravity native adapter for Global Owner Scout.\n"
            "context requires current native --session-id, --project-root and --app-data-dir.\n"
            "capture also requires --artifact-dir (restricted to current bound session-id).\n"
            "Prepare native results: scout.py describe-input native-project|native-review\n"
            "Help reads no project or transcript and grants no output access."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("operation", choices=("context", "capture"))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--app-data-dir", required=True)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--source-session-id")
    args = parser.parse_args(argv)
    try:
        output = invoke_antigravity(
            operation=args.operation,
            session_id=args.session_id,
            project_root=args.project_root,
            app_data_dir=args.app_data_dir,
            artifact_dir=args.artifact_dir,
            source_session_id=args.source_session_id,
        )
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ContractError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
