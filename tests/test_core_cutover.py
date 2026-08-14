from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar.core_cutover import (
    apply_core_cutover,
    preview_core_cutover,
)
from agent_memory_sidecar.database import CORE_TABLES, CoreDatabase
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.identity import ProjectIdentity
from agent_memory_sidecar.installation import InstallationRegistry
from agent_memory_sidecar.skill import SkillPlan


class CoreCutoverTests(unittest.TestCase):
    def test_dry_run_is_stable_across_append_only_prompt_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            identity, _ = _legacy_store(store, root)
            first = preview_core_cutover(store_path=store)
            _append_prompt(store, identity, "evt_second")
            second = preview_core_cutover(store_path=store)
            self.assertEqual(first.plan_hash, second.plan_hash)
            self.assertNotEqual(
                first.source_counts["events"],
                second.source_counts["events"],
            )

    def test_apply_rebuilds_store_keeps_permanent_backup_and_activates_zipapp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            codex.mkdir()
            store = codex / "agent-memory-sidecar" / "memory.sqlite"
            store.parent.mkdir()
            identity, approval_ref = _legacy_store(store, root)
            plan = preview_core_cutover(store_path=store)
            fake_skill = SkillPlan(
                path=root / "skill",
                action="noop",
                canonical_sha256="a" * 64,
                installed_sha256="a" * 64,
            )
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.core_cutover.install_skill",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.core_cutover.plan_skill_install",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.installed_skill_sha256",
                    return_value="a" * 64,
                ),
            ):
                result = apply_core_cutover(
                    store_path=store,
                    identity=identity,
                    approval_ref=approval_ref,
                    expected_plan_hash=plan.plan_hash,
                )
            self.assertTrue(result["applied"])
            backup = Path(result["backup"]["path"])
            self.assertTrue(backup.exists())
            self.assertTrue(Path(f"{backup}.sha256").exists())
            self.assertEqual(
                hashlib.sha256(backup.read_bytes()).hexdigest(),
                result["backup"]["sha256"].removeprefix("sha256:"),
            )
            with CoreDatabase(store) as db:
                self.assertEqual(db.table_names(), CORE_TABLES)
                self.assertEqual(
                    InstallationRegistry(db).runtime().database_namespace,
                    "db_" + ("1" * 32),
                )
                self.assertEqual(
                    db.conn.execute(
                        """
                        SELECT operation FROM approval_consumptions
                        WHERE operation = 'maintenance.core_cutover'
                        """
                    ).fetchone()["operation"],
                    "maintenance.core_cutover",
                )
                metadata = db.conn.execute(
                    "SELECT metadata_json FROM prompt_events "
                    "WHERE event_id = 'evt_current'"
                ).fetchone()["metadata_json"]
                self.assertNotIn("diagnostic_excerpt", metadata)
            hooks = json.loads(
                (codex / "hooks.json").read_text(encoding="utf-8")
            )
            command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0][
                "commandWindows"
            ]
            self.assertIn(".pyz", command)

    def test_plan_mismatch_does_not_create_backup_or_change_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            identity, approval_ref = _legacy_store(store, root)
            before = store.read_bytes()
            with self.assertRaises(CoreError) as raised:
                apply_core_cutover(
                    store_path=store,
                    identity=identity,
                    approval_ref=approval_ref,
                    expected_plan_hash="0" * 64,
                )
            self.assertEqual(raised.exception.code, "cutover_plan_changed")
            self.assertEqual(store.read_bytes(), before)
            self.assertEqual(list(root.glob("*.pre-core-v1-*.bak")), [])

    def test_approval_is_revalidated_after_maintenance_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            identity, approval_ref = _legacy_store(store, root)
            plan = preview_core_cutover(store_path=store)

            @contextmanager
            def changed_current_event(_store: Path):
                _append_prompt(store, identity, "evt_after_lock")
                yield

            with patch(
                "agent_memory_sidecar.core_cutover._maintenance_lock",
                changed_current_event,
            ):
                with self.assertRaises(CoreError) as raised:
                    apply_core_cutover(
                        store_path=store,
                        identity=identity,
                        approval_ref=approval_ref,
                        expected_plan_hash=plan.plan_hash,
                    )
            self.assertEqual(raised.exception.code, "approval_invalid")
            self.assertEqual(list(root.glob("*.pre-core-v1-*.bak")), [])

    def test_post_replace_failure_restores_legacy_store_and_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            codex.mkdir()
            hooks = codex / "hooks.json"
            old_hooks = b'{"hooks":{"Other":[]}}\n'
            hooks.write_bytes(old_hooks)
            store = codex / "agent-memory-sidecar" / "memory.sqlite"
            store.parent.mkdir()
            identity, approval_ref = _legacy_store(store, root)
            plan = preview_core_cutover(store_path=store)
            fake_skill = SkillPlan(
                path=root / "skill",
                action="noop",
                canonical_sha256="a" * 64,
                installed_sha256="a" * 64,
            )
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.core_cutover.install_skill",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.core_cutover.plan_skill_install",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.core_cutover.doctor",
                    return_value={
                        "status": "error",
                        "errors": [{"code": "injected"}],
                    },
                ),
            ):
                with self.assertRaises(CoreError):
                    apply_core_cutover(
                        store_path=store,
                        identity=identity,
                        approval_ref=approval_ref,
                        expected_plan_hash=plan.plan_hash,
                    )
            connection = sqlite3.connect(store)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            connection.close()
            self.assertIn("memories", tables)
            self.assertEqual(hooks.read_bytes(), old_hooks)


def _legacy_store(
    path: Path, root: Path
) -> tuple[Identity, str]:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            source_session TEXT,
            cwd TEXT NOT NULL,
            repo_root TEXT,
            branch TEXT,
            scope_key TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE memories (id TEXT PRIMARY KEY);
        CREATE TABLE memory_mutations (id TEXT PRIMARY KEY);
        CREATE TABLE runbooks (id TEXT PRIMARY KEY);
        CREATE TABLE runtime_deliveries (
            source_session TEXT,
            context_epoch INTEGER,
            lineage_id TEXT
        );
        CREATE TABLE runtime_sessions (
            source_session TEXT PRIMARY KEY,
            scope_key TEXT NOT NULL,
            context_epoch INTEGER NOT NULL,
            last_prompt_event_id TEXT,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT,
            checksum TEXT,
            applied_at TEXT
        );
        CREATE TABLE state (
            scope_key TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(scope_key, key)
        );
        CREATE TABLE suggestion_tokens (
            token TEXT PRIMARY KEY,
            source_event_id TEXT
        );
        """
    )
    identity = Identity(
        cwd=str(root),
        repo_root=str(root),
        branch="main",
        scope_key=str(root.resolve()),
    )
    event_id = "evt_current"
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    prompt_hash = hashlib.sha256(b"approve cutover").hexdigest()
    metadata = json.dumps(
        {
            "content_hash": f"sha256:{prompt_hash}",
            "content_bytes": 16,
            "diagnostic_excerpt": "sensitive prompt text",
        },
        sort_keys=True,
    )
    connection.execute(
        """
        INSERT INTO events VALUES (
            ?, 'UserPromptSubmit', ?, ?, 'session', ?, ?, 'main', ?, ?
        )
        """,
        (
            event_id,
            f"UserPromptSubmit sha256:{prompt_hash} bytes=16",
            metadata,
            str(root),
            str(root),
            identity.scope_key,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO runtime_sessions VALUES ('session', ?, 0, ?, ?)
        """,
        (identity.scope_key, event_id, now),
    )
    connection.execute(
        """
        INSERT INTO state VALUES (
            '__runtime_install__',
            'runtime_install_identity_v1',
            ?,
            ?
        )
        """,
        (
            json.dumps(
                {
                    "identity_version": "runtime_install_identity_v1",
                    "database_namespace": "db_" + ("1" * 32),
                },
                sort_keys=True,
            ),
            now,
        ),
    )
    connection.commit()
    connection.close()
    return identity, f"user_prompt:{event_id}"


def _append_prompt(path: Path, identity: "Identity", event_id: str) -> None:
    connection = sqlite3.connect(path)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    digest = hashlib.sha256(event_id.encode()).hexdigest()
    connection.execute(
        """
        INSERT INTO events VALUES (
            ?, 'UserPromptSubmit', ?, ?, 'session', ?, ?, 'main', ?, ?
        )
        """,
        (
            event_id,
            f"UserPromptSubmit sha256:{digest} bytes=1",
            json.dumps(
                {
                    "content_hash": f"sha256:{digest}",
                    "content_bytes": 1,
                }
            ),
            identity.cwd,
            identity.repo_root,
            identity.scope_key,
            now,
        ),
    )
    connection.execute(
        """
        UPDATE runtime_sessions
        SET last_prompt_event_id = ?, last_seen_at = ?
        WHERE source_session = 'session'
        """,
        (event_id, now),
    )
    connection.commit()
    connection.close()


Identity = ProjectIdentity
