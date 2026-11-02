from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

from .database import CoreDatabase, schema_manifest
from .errors import CoreError
from .runtime_hook import execute_runtime_hook


def run(*, store_path: Path | str) -> dict[str, Any]:
    target = Path(store_path)
    session_id = f"core-v1-self-test-{uuid.uuid4().hex}"
    with CoreDatabase(target) as db:
        try:
            execution = execute_runtime_hook(
                payload={
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": session_id,
                    "cwd": str(target.parent),
                    "prompt": "Agent Memory immutable runtime self-test",
                },
                store_path=target,
                allow_maintenance=True,
            )
            captured = db.conn.execute(
                """SELECT 1 FROM prompt_events e JOIN runtime_sessions s
                   ON s.source_session = e.source_session AND s.last_prompt_event_id = e.event_id
                   WHERE e.event_id = ? AND e.source_session = ?""",
                (execution.audit.event_id, session_id),
            ).fetchone()
            integrity = db.integrity_check()
            if not execution.output or captured is None or integrity != "ok":
                raise CoreError(
                    "runtime_artifact_self_test_failed",
                    "runtime artifact failed prompt capture self-test",
                )
        finally:
            with db.transaction():
                db.conn.execute(
                    "DELETE FROM runtime_sessions WHERE source_session = ?",
                    (session_id,),
                )
                db.conn.execute(
                    "DELETE FROM prompt_events WHERE source_session = ?",
                    (session_id,),
                )
    return {
        "schema": schema_manifest(),
        "hook_output": True,
        "event_delta": 1,
        "integrity": integrity,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if len(arguments) != 2 or arguments[0] != "--store":
        return 1
    try:
        data = run(store_path=arguments[1])
        payload = {"status": "ok", "data": data, "error": None}
        code = 0
    except CoreError as exc:
        payload = {"status": "error", "data": None, "error": exc.to_dict()}
        code = 1
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
