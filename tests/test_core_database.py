from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_memory_sidecar import file_security
from agent_memory_sidecar.authorization import Approval, AuthorizationLedger
from agent_memory_sidecar.database import (
    CORE_TABLES,
    RUNTIME_JOURNAL_MODE,
    CoreDatabase,
)
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.identity import ProjectIdentity
from agent_memory_sidecar.proposal import RuleProposal
from agent_memory_sidecar.runtime_hook import (
    execute_runtime_hook,
    run_runtime_hook,
)
from agent_memory_sidecar.runtime_ledger import RuntimeLedger
from agent_memory_sidecar.store_lifecycle import (
    canonical_store_path,
    clean_store_rotation_lock_path,
)


class CoreDatabaseTests(unittest.TestCase):
    def test_physical_chain_only_tolerates_os_owned_top_level_aliases(self) -> None:
        predicate = getattr(file_security, "_is_trusted_host_directory_alias")
        root_owned_link = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)
        user_owned_link = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=1000)
        self.assertTrue(predicate(Path("/var"), root_owned_link, platform="posix"))
        self.assertFalse(predicate(Path("/var"), user_owned_link, platform="posix"))
        self.assertFalse(predicate(Path("/tmp/user-alias"), root_owned_link, platform="posix"))
        self.assertFalse(predicate(Path("/var"), root_owned_link, platform="nt"))

    def test_windows_acl_validation_is_semantic_not_ace_count_based(self) -> None:
        validator = getattr(file_security, "_validate_windows_dacl")
        sid = "S-1-5-21-1000"
        validator(
            f"D:P(A;;0x001f01ff;;;{sid})(A;;FA;;;SY)(A;;FA;;;BA)(D;;FR;;;WD)",
            sid=sid,
            path=Path("store"),
        )
        validator(
            "D:P(A;;FA;;;LA)(A;;FA;;;SY)",
            sid="S-1-5-21-1000-500",
            path=Path("store"),
        )
        with self.assertRaises(CoreError) as raised:
            validator(
                f"D:P(A;;FA;;;{sid})(A;;FA;;;SY)(A;;FR;;;AU)",
                sid=sid,
                path=Path("store"),
            )
        self.assertEqual(raised.exception.code, "store_permissions_unsafe")
        with self.assertRaises(CoreError):
            validator(
                "D:P(A;;FA;;;LA)(A;;FA;;;SY)",
                sid=sid,
                path=Path("store"),
            )

    @unittest.skipUnless(os.name == "nt", "Windows ACL round trip")
    def test_windows_acl_round_trip_uses_supported_principals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            try:
                with CoreDatabase(
                    Path(directory) / "memory.sqlite",
                    create=True,
                    now="2026-08-14T00:00:00+00:00",
                ):
                    pass
            except CoreError as exc:
                self.fail(json.dumps(exc.to_dict(), sort_keys=True))

    def test_schema_has_exactly_seven_owned_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ) as db:
                self.assertEqual(db.table_names(), CORE_TABLES)
                self.assertEqual(db.integrity_check(), "ok")
                self.assertEqual(db.foreign_key_violations(), [])
                for legacy in (
                    "memories",
                    "memory_mutations",
                    "runbooks",
                    "runtime_deliveries",
                    "state",
                ):
                    self.assertNotIn(legacy, db.table_names())

    def test_store_is_private_and_rejects_filesystem_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-08-13T00:00:00+00:00",
            ):
                pass
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            symbolic = root / "symbolic.sqlite"
            try:
                symbolic.symlink_to(path)
            except OSError:
                symbolic = None
            if symbolic is not None:
                with self.assertRaises(CoreError) as raised:
                    CoreDatabase(symbolic)
                self.assertEqual(raised.exception.code, "store_unsafe")
                with self.assertRaises(CoreError) as lifecycle_error:
                    canonical_store_path(symbolic)
                self.assertEqual(
                    lifecycle_error.exception.code,
                    "store_unsafe",
                )

            physical_directory = root / "physical-store-root"
            physical_directory.mkdir()
            directory_alias = root / "store-root-alias"
            try:
                directory_alias.symlink_to(
                    physical_directory,
                    target_is_directory=True,
                )
            except OSError:
                directory_alias = None
            if directory_alias is not None:
                with self.assertRaises(CoreError) as parent_error:
                    CoreDatabase(
                        directory_alias / "nested" / "memory.sqlite",
                        create=True,
                        now="2026-08-13T00:00:00+00:00",
                    )
                self.assertEqual(parent_error.exception.code, "store_unsafe")
                self.assertFalse((physical_directory / "nested").exists())

                physical_inner = physical_directory / "existing"
                physical_inner.mkdir()
                with self.assertRaises(CoreError) as ancestor_error:
                    CoreDatabase(
                        directory_alias / "existing" / "memory.sqlite",
                        create=True,
                        now="2026-08-13T00:00:00+00:00",
                    )
                self.assertEqual(ancestor_error.exception.code, "store_unsafe")

            hardlink = root / "hardlink.sqlite"
            try:
                hardlink.hardlink_to(path)
            except OSError:
                hardlink = None
            if hardlink is not None:
                with self.assertRaises(CoreError) as raised:
                    CoreDatabase(path)
                self.assertEqual(raised.exception.code, "store_unsafe")

    def test_runtime_storage_policy_is_verified_on_each_connection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch=None,
                scope_key=str(root.resolve()),
            )

            with CoreDatabase(path, runtime=True) as first:
                self.assertEqual(
                    first.conn.execute(
                        "PRAGMA journal_mode"
                    ).fetchone()[0],
                    RUNTIME_JOURNAL_MODE.lower(),
                )
                self.assertEqual(
                    first.conn.execute("PRAGMA synchronous").fetchone()[0],
                    1,
                )
                with CoreDatabase(path, runtime=True) as second:
                    self.assertEqual(
                        second.conn.execute(
                            "PRAGMA journal_mode"
                        ).fetchone()[0],
                        RUNTIME_JOURNAL_MODE.lower(),
                    )
                    self.assertEqual(
                        second.conn.execute(
                            "PRAGMA synchronous"
                        ).fetchone()[0],
                        1,
                    )
                    RuntimeLedger(first).capture_prompt(
                        identity=identity,
                        source_session="committed",
                        prompt="commit",
                        metadata={},
                    )
                    self.assertEqual(
                        second.conn.execute(
                            "SELECT COUNT(*) FROM prompt_events"
                        ).fetchone()[0],
                        1,
                    )
                    with self.assertRaises(RuntimeError):
                        with first.transaction():
                            RuntimeLedger(first).capture_prompt(
                                identity=identity,
                                source_session="rolled-back",
                                prompt="rollback",
                                metadata={},
                            )
                            raise RuntimeError("rollback")
                    self.assertEqual(
                        second.conn.execute(
                            "SELECT COUNT(*) FROM prompt_events"
                        ).fetchone()[0],
                        1,
                    )
                self.assertEqual(first.integrity_check(), "ok")
                self.assertEqual(first.foreign_key_violations(), [])

            with CoreDatabase(path, runtime=True) as reopened:
                self.assertEqual(
                    reopened.conn.execute(
                        "PRAGMA journal_mode"
                    ).fetchone()[0],
                    RUNTIME_JOURNAL_MODE.lower(),
                )
                self.assertEqual(
                    reopened.conn.execute(
                        "PRAGMA synchronous"
                    ).fetchone()[0],
                    1,
                )

    def test_non_runtime_connection_does_not_apply_runtime_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            with patch(
                "agent_memory_sidecar.database._configure_runtime_storage"
            ) as configure:
                with CoreDatabase(path):
                    pass
            configure.assert_not_called()

    def test_unavailable_runtime_policy_fails_open_at_hook_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            failure = CoreError(
                "runtime_journal_mode_unavailable",
                "injected unsupported mode",
            )
            with patch(
                "agent_memory_sidecar.database._configure_runtime_storage",
                side_effect=failure,
            ):
                with self.assertRaises(CoreError) as raised:
                    CoreDatabase(path, runtime=True)
                code, stdout, stderr = run_runtime_hook(
                    payload={
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "fail-open",
                        "cwd": str(root),
                        "prompt": "x",
                    },
                    store_path=path,
                )
            self.assertEqual(
                raised.exception.code,
                "runtime_journal_mode_unavailable",
            )
            self.assertEqual((code, stdout, stderr), (0, "", ""))

    def test_schema_fingerprint_detects_missing_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            connection = sqlite3.connect(path)
            connection.execute("DROP INDEX idx_proposal_tokens_expiry")
            connection.commit()
            connection.close()
            with self.assertRaises(CoreError) as raised:
                CoreDatabase(path)
            self.assertEqual(raised.exception.code, "schema_mismatch")

    def test_legacy_store_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY)")
            connection.commit()
            connection.close()
            with self.assertRaises(CoreError) as raised:
                CoreDatabase(path)
            self.assertEqual(raised.exception.code, "migration_required")

    def test_proposal_requires_exact_seven_fields_and_matching_target(self) -> None:
        payload = _proposal_payload()
        value = RuleProposal.from_payload(payload)
        self.assertEqual(value.scope, "project")
        self.assertEqual(len(value.proposal_sha256), 64)
        with self.assertRaises(CoreError):
            RuleProposal.from_payload({**payload, "summary": "legacy"})
        with self.assertRaises(CoreError):
            RuleProposal.from_payload(
                {**payload, "instruction_target": "global_agents"}
            )

    def test_runtime_stores_hash_not_prompt_and_compact_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            prompt = "secret-free but raw prompt must not persist"
            first = execute_runtime_hook(
                payload={
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "session-a",
                    "cwd": str(root),
                    "prompt": prompt,
                },
                store_path=path,
            )
            self.assertIn("approval_ref=user_prompt:", first.output)
            with CoreDatabase(path) as db:
                row = db.conn.execute(
                    "SELECT * FROM prompt_events"
                ).fetchone()
                before = db.conn.execute(
                    "SELECT COUNT(*) FROM prompt_events"
                ).fetchone()[0]
                self.assertNotIn("prompt", row.keys())
                self.assertNotIn(prompt, str(dict(row)))
                metadata = json.loads(str(row["metadata_json"]))
                self.assertNotIn(prompt, json.dumps(metadata))
            compact = execute_runtime_hook(
                payload={
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                    "session_id": "session-a",
                    "cwd": str(root),
                },
                store_path=path,
            )
            self.assertEqual(compact.output, first.output.replace(
                '"hookEventName": "UserPromptSubmit"',
                '"hookEventName": "SessionStart"',
            ))
            with CoreDatabase(path) as db:
                after = db.conn.execute(
                    "SELECT COUNT(*) FROM prompt_events"
                ).fetchone()[0]
            self.assertEqual(after, before)

    def test_runtime_fails_open_during_maintenance_and_on_legacy_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "memory.sqlite"
            with CoreDatabase(
                core,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            lock = clean_store_rotation_lock_path(core)
            lock.write_text("{}", encoding="utf-8")
            result = execute_runtime_hook(
                payload={
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "s",
                    "cwd": str(root),
                    "prompt": "x",
                },
                store_path=core,
            )
            self.assertEqual(result.output, "")

    def test_native_memory_mode_does_not_change_hook_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            contexts: list[str] = []
            for session, mode in (
                ("memory-on", "complement"),
                ("memory-off", "observe"),
            ):
                execution = execute_runtime_hook(
                    payload={
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": session,
                        "cwd": str(root),
                        "prompt": "remember the same explicit rule",
                    },
                    official_memory_mode=mode,
                    store_path=path,
                )
                contexts.append(
                    json.loads(execution.output)["hookSpecificOutput"][
                        "additionalContext"
                    ]
                )
            normalized = [
                re.sub(r"user_prompt:evt_[0-9a-f]+", "user_prompt:<event>", value)
                for value in contexts
            ]
            self.assertEqual(normalized[0], normalized[1])

    def test_multifolder_runtime_uses_explicit_primary_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary"
            secondary = root / "secondary"
            primary.mkdir()
            secondary.mkdir()
            path = root / "memory.sqlite"
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            for prompt in ("first", "second"):
                execution = execute_runtime_hook(
                    payload={
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "multi-folder",
                        "cwd": str(secondary),
                        "scope_key": str(primary),
                        "prompt": prompt,
                    },
                    store_path=path,
                )
                self.assertTrue(execution.output)
            compact = execute_runtime_hook(
                payload={
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                    "session_id": "multi-folder",
                    "cwd": str(secondary),
                    "scope_key": str(primary),
                },
                store_path=path,
            )
            self.assertTrue(compact.output)
            with CoreDatabase(path) as db:
                rows = db.conn.execute(
                    "SELECT DISTINCT scope_key FROM prompt_events"
                ).fetchall()
                self.assertEqual(
                    [str(row["scope_key"]) for row in rows],
                    [str(primary.resolve())],
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM prompt_events"
                    ).fetchone()[0],
                    2,
                )
            with self.assertRaises(ValueError):
                execute_runtime_hook(
                    payload={
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "multi-folder",
                        "cwd": str(secondary),
                        "scope_key": str(secondary),
                        "prompt": "wrong owner",
                    },
                    store_path=path,
                )

    def test_retention_prunes_old_events_and_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch="main",
                scope_key=str(root.resolve()),
            )
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-01T00:00:00+00:00",
            ) as db:
                ledger = RuntimeLedger(db)
                ledger.capture_prompt(
                    identity=identity,
                    source_session="old",
                    prompt="old",
                    metadata={},
                    now="2026-07-01T00:00:00+00:00",
                )
                ledger.capture_prompt(
                    identity=identity,
                    source_session="new",
                    prompt="new",
                    metadata={},
                    now="2026-07-24T00:00:00+00:00",
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM prompt_events"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM runtime_sessions"
                    ).fetchone()[0],
                    1,
                )

    def test_retention_cascades_consumed_approval_with_expired_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch="main",
                scope_key=str(root.resolve()),
            )
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-01T00:00:00+00:00",
            ) as db:
                ledger = RuntimeLedger(db)
                event = ledger.capture_prompt(
                    identity=identity,
                    source_session="consumed-old",
                    prompt="old",
                    metadata={},
                    now="2026-07-01T00:00:00+00:00",
                )
                approval_ref = f"user_prompt:{event.event_id}"
                approval = Approval(
                    approval_ref=approval_ref,
                    approval_ref_sha256=hashlib.sha256(
                        approval_ref.encode("utf-8")
                    ).hexdigest(),
                    event=event,
                )
                with db.transaction():
                    AuthorizationLedger(db, ledger).consume(
                        approval=approval,
                        operation="rule.deploy",
                        request_sha256="0" * 64,
                        result_rule_id="rule_000000000000",
                        transaction_id="tx_retention",
                        consumed_at="2026-07-01T00:00:00+00:00",
                    )
                ledger.capture_prompt(
                    identity=identity,
                    source_session="new",
                    prompt="new",
                    metadata={},
                    now="2026-07-24T00:00:00+00:00",
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM approval_consumptions"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM prompt_events"
                    ).fetchone()[0],
                    1,
                )

    def test_approval_event_expires_even_before_a_prune_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "memory.sqlite"
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch="main",
                scope_key=str(root.resolve()),
            )
            with CoreDatabase(
                path,
                create=True,
                now="2026-07-01T00:00:00+00:00",
            ) as db:
                event = RuntimeLedger(db).capture_prompt(
                    identity=identity,
                    source_session="old-current",
                    prompt="remember",
                    metadata={},
                    now="2026-07-01T00:00:00+00:00",
                )
                with self.assertRaises(CoreError) as raised:
                    RuntimeLedger(db).resolve_approval_event(
                        approval_ref=f"user_prompt:{event.event_id}",
                        identity=identity,
                        now="2026-07-24T00:00:00+00:00",
                    )
                self.assertEqual(raised.exception.code, "approval_invalid")


def _proposal_payload() -> dict[str, str]:
    return {
        "trigger": "When reviewing repository changes.",
        "action": "Run the relevant tests before reporting completion.",
        "skip_boundary": "Skip for prose-only work with no executable checks.",
        "scope": "project",
        "why": "This avoids repeated regression corrections.",
        "evidence": "The user explicitly required test-backed completion.",
        "instruction_target": "project_agents",
    }
