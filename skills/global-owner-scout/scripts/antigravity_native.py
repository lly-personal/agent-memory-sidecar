#!/usr/bin/env python3
"""Ordinary Skill adapter for Antigravity: runtime context binding and local transcript capture."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from history_import import import_history
from scout import inspect_native_context
from scout_security import is_reparse, safe_artifact_bytes, validate_output_root
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


def _load_transcript_steps(app_data_dir: Path, source_session_id: str) -> tuple[str, list[dict[str, Any]]]:
    logs_dir = app_data_dir.resolve(strict=True) / "brain" / source_session_id / ".system_generated" / "logs"
    _require(logs_dir.is_dir() and not is_reparse(logs_dir), "antigravity_transcript_missing")
    selected_kind: str | None = None
    selected_path: Path | None = None
    for kind, filename in (("transcript_full", "transcript_full.jsonl"), ("transcript", "transcript.jsonl")):
        candidate = logs_dir / filename
        if candidate.exists() or is_reparse(candidate):
            _require(candidate.is_file() and not is_reparse(candidate), "antigravity_transcript_not_regular")
            selected_kind = kind
            selected_path = candidate
            break
    _require(selected_kind is not None and selected_path is not None, "antigravity_transcript_missing")
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
    binding = inspect_native_context(native)
    result: dict[str, Any] = {"native_context": native, "native_binding": binding}
    if operation == "context":
        return result

    _require(
        isinstance(artifact_dir, str) and bool(artifact_dir) and Path(artifact_dir).is_absolute(),
        "native_source_current_authorized_artifact_dir_required",
    )
    selected_source = source_session_id if source_session_id is not None else session_id
    _valid_session_id(selected_source, "antigravity_source_session_id_invalid")

    bound_project = Path(binding["project_root"])
    app_data_path = Path(app_data_dir)
    protected_roots = [bound_project, SKILL_ROOT, app_data_path]
    # Check every write boundary before reading any transcript bytes.
    validate_output_root(Path(artifact_dir), protected_roots)

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
        protected_roots=protected_roots,
    )
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
            "capture also requires --artifact-dir (and optional --source-session-id).\n"
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
