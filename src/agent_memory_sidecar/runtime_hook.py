from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .ambient_capability import build_ambient_capability
from .database import CoreDatabase
from .event_policy import minimize_hook_event
from .identity import ProjectIdentity, resolve_identity
from .runtime_ledger import RuntimeLedger
from .store_lifecycle import clean_store_rotation_locked


DEFAULT_HOOK_EVENTS = frozenset({"UserPromptSubmit", "SessionStart"})


@dataclass(frozen=True)
class RuntimeHookAudit:
    event_type: str
    source_session: str | None
    event_id: str | None
    duration_ms: float
    connection_count: int
    capability_bytes: int
    additional_context_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source_session": self.source_session,
            "event_id": self.event_id,
            "duration_ms": round(self.duration_ms, 3),
            "connection_count": self.connection_count,
            "capability_bytes": self.capability_bytes,
            "additional_context_bytes": self.additional_context_bytes,
        }


@dataclass(frozen=True)
class RuntimeHookExecution:
    output: str
    audit: RuntimeHookAudit


def runtime_store_path() -> Path:
    configured = os.environ.get("CODEX_HOME")
    home = (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.home() / ".codex").resolve()
    )
    return home / "agent-memory-sidecar" / "memory.sqlite"


def execute_runtime_hook(
    *,
    payload: dict[str, Any],
    official_memory_mode: str = "complement",
    store_path: Path | str | None = None,
    allow_maintenance: bool = False,
) -> RuntimeHookExecution:
    del official_memory_mode
    started = time.perf_counter()
    event_type = str(payload.get("hook_event_name") or "")
    session = _payload_session(payload)
    if (
        event_type not in DEFAULT_HOOK_EVENTS
        or session is None
        or (
            event_type == "SessionStart"
            and payload.get("source") != "compact"
        )
    ):
        return _execution(
            event_type=event_type,
            session=session,
            event_id=None,
            started=started,
            connections=0,
            context="",
        )
    target = Path(store_path) if store_path is not None else runtime_store_path()
    if clean_store_rotation_locked(target) and not allow_maintenance:
        return _execution(
            event_type=event_type,
            session=session,
            event_id=None,
            started=started,
            connections=0,
            context="",
        )

    with CoreDatabase(target, runtime=True) as db:
        ledger = RuntimeLedger(db)
        if event_type == "SessionStart":
            event = ledger.current_event(source_session=session)
            _validate_compact_scope(payload=payload, scope_key=event.scope_key)
        else:
            identity = _identity_for_event(
                db=db,
                payload=payload,
                source_session=session,
            )
            prompt = _content_from_payload(payload)
            _stored, metadata = minimize_hook_event(
                payload={**payload, "hook_event_name": event_type},
                content=prompt,
            )
            event = ledger.capture_prompt(
                identity=identity,
                source_session=session,
                prompt=prompt,
                metadata=metadata,
            )
    context = build_ambient_capability(event.event_id)
    output = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": event_type,
                "additionalContext": context,
            }
        },
        ensure_ascii=False,
    )
    return _execution(
        event_type=event_type,
        session=session,
        event_id=event.event_id,
        started=started,
        connections=1,
        context=context,
        output=output,
    )


def run_runtime_hook(
    *,
    payload: dict[str, Any],
    official_memory_mode: str = "complement",
    store_path: Path | str | None = None,
) -> tuple[int, str, str]:
    try:
        execution = execute_runtime_hook(
            payload=payload,
            official_memory_mode=official_memory_mode,
            store_path=store_path,
        )
        return 0, execution.output, ""
    except Exception:
        return 0, "", ""


def main(argv: Sequence[str] | None = None) -> int:
    mode = _parse_runtime_args(
        list(argv) if argv is not None else sys.argv[1:]
    )
    if mode is None:
        return 0
    try:
        raw = _read_utf8(sys.stdin)
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            return 0
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 0
    code, stdout, stderr = run_runtime_hook(
        payload=payload,
        official_memory_mode=mode,
    )
    if stdout:
        _write_utf8(sys.stdout, stdout)
    if stderr:
        _write_utf8(sys.stderr, stderr)
    return code


def _identity_for_event(
    *,
    db: CoreDatabase,
    payload: dict[str, Any],
    source_session: str,
) -> ProjectIdentity:
    row = db.conn.execute(
        """
        SELECT s.scope_key, e.repo_root
        FROM runtime_sessions s
        LEFT JOIN prompt_events e ON e.event_id = s.last_prompt_event_id
        WHERE s.source_session = ?
        """,
        (source_session,),
    ).fetchone()
    if row is None:
        cwd = payload.get("cwd")
        explicit = payload.get("scope_key") or payload.get("repo_root")
        if explicit:
            scope_key = str(Path(str(explicit)).resolve(strict=False))
            return ProjectIdentity(
                cwd=str(Path(str(cwd or scope_key)).resolve(strict=False)),
                repo_root=(
                    str(Path(str(payload["repo_root"])).resolve(strict=False))
                    if payload.get("repo_root")
                    else None
                ),
                branch=None,
                scope_key=scope_key,
            )
        return resolve_identity(str(cwd) if cwd else None)
    cached_scope = str(row["scope_key"])
    explicit = payload.get("scope_key") or payload.get("repo_root")
    if explicit and not _same_path(str(explicit), cached_scope):
        raise ValueError("runtime session scope changed")
    cwd = str(payload.get("cwd") or cached_scope)
    if not explicit and not _path_is_within(cwd, cached_scope):
        resolved = resolve_identity(cwd)
        if not _same_path(resolved.scope_key, cached_scope):
            raise ValueError("runtime session was reused across scopes")
    return ProjectIdentity(
        cwd=cwd,
        repo_root=(str(row["repo_root"]) if row["repo_root"] else None),
        branch=None,
        scope_key=cached_scope,
    )


def _validate_compact_scope(
    *, payload: dict[str, Any], scope_key: str
) -> None:
    explicit = payload.get("scope_key") or payload.get("repo_root")
    if explicit and not _same_path(str(explicit), scope_key):
        raise ValueError("compact event belongs to another scope")
    cwd = payload.get("cwd")
    if not explicit and cwd and not _path_is_within(str(cwd), scope_key):
        raise ValueError("compact cwd belongs to another scope")


def _execution(
    *,
    event_type: str,
    session: str | None,
    event_id: str | None,
    started: float,
    connections: int,
    context: str,
    output: str = "",
) -> RuntimeHookExecution:
    return RuntimeHookExecution(
        output=output,
        audit=RuntimeHookAudit(
            event_type=event_type,
            source_session=session,
            event_id=event_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            connection_count=connections,
            capability_bytes=len(context.encode("utf-8")),
            additional_context_bytes=len(context.encode("utf-8")),
        ),
    )


def _parse_runtime_args(argv: list[str]) -> str | None:
    mode = "complement"
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"-h", "--help"}:
            return None
        if argument == "--official-memory-mode" and index + 1 < len(argv):
            mode = argv[index + 1]
            index += 2
        elif argument.startswith("--official-memory-mode="):
            mode = argument.split("=", 1)[1]
            index += 1
        else:
            return None
        if mode not in {"complement", "observe"}:
            return None
    return mode


def _payload_session(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id") or payload.get("source_session")
    text = str(value or "").strip()
    if (
        not text
        or len(text.encode("utf-8", errors="replace")) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return None
    return text


def _content_from_payload(payload: dict[str, Any]) -> str:
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return prompt
    return ""


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(str(Path(left).resolve(strict=False))) == os.path.normcase(
        str(Path(right).resolve(strict=False))
    )


def _path_is_within(path: str, parent: str) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(
            Path(parent).resolve(strict=False)
        )
        return True
    except ValueError:
        return False


def _read_utf8(stream: Any) -> str:
    binary = getattr(stream, "buffer", None)
    return stream.read() if binary is None else binary.read().decode("utf-8")


def _write_utf8(stream: Any, value: str) -> None:
    line = f"{value}\n"
    binary = getattr(stream, "buffer", None)
    try:
        if binary is None:
            stream.write(line)
            stream.flush()
        else:
            binary.write(line.encode("utf-8"))
            binary.flush()
    except (OSError, UnicodeError):
        return


if __name__ == "__main__":
    raise SystemExit(main())
