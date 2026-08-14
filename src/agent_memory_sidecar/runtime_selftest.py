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
        before = db.conn.execute(
            "SELECT COUNT(*) FROM prompt_events"
        ).fetchone()[0]
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
        after = db.conn.execute(
            "SELECT COUNT(*) FROM prompt_events"
        ).fetchone()[0]
        integrity = db.integrity_check()
        event_id = execution.audit.event_id
        if execution.output and after == before + 1 and event_id is not None:
            with db.transaction():
                db.conn.execute(
                    "DELETE FROM runtime_sessions WHERE source_session = ?",
                    (session_id,),
                )
                db.conn.execute(
                    "DELETE FROM prompt_events WHERE event_id = ?",
                    (event_id,),
                )
    if not execution.output or after != before + 1 or integrity != "ok":
        raise CoreError(
            "runtime_artifact_self_test_failed",
            "runtime artifact failed prompt capture self-test",
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
