from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .errors import CoreError
from .file_security import (
    logical_absolute,
    prepare_store_parent,
    secure_store_location,
)


CORE_SCHEMA_VERSION = "core_v1"
RUNTIME_JOURNAL_MODE = "PERSIST"
RUNTIME_SYNCHRONOUS = "NORMAL"
_RUNTIME_SYNCHRONOUS_VALUE = 1
CORE_SCHEMA_DDL = """
CREATE TABLE core_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL,
    schema_sha256 TEXT NOT NULL,
    migrated_from_sha256 TEXT,
    created_at TEXT NOT NULL,
    last_pruned_at TEXT NOT NULL
);

CREATE TABLE prompt_events (
    event_id TEXT PRIMARY KEY,
    source_session TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    cwd TEXT NOT NULL,
    repo_root TEXT,
    branch TEXT,
    prompt_sha256 TEXT NOT NULL,
    prompt_bytes INTEGER NOT NULL CHECK (prompt_bytes >= 0),
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_prompt_events_scope_created
    ON prompt_events(scope_key, created_at);
CREATE INDEX idx_prompt_events_session_created
    ON prompt_events(source_session, created_at);

CREATE TABLE runtime_sessions (
    source_session TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    context_epoch INTEGER NOT NULL DEFAULT 0 CHECK (context_epoch >= 0),
    last_prompt_event_id TEXT,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (last_prompt_event_id)
        REFERENCES prompt_events(event_id) ON DELETE SET NULL
);
CREATE INDEX idx_runtime_sessions_last_seen
    ON runtime_sessions(last_seen_at);

CREATE TABLE proposal_tokens (
    token_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    source_session TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('project', 'global')),
    scope_key TEXT NOT NULL,
    instruction_target TEXT NOT NULL
        CHECK (instruction_target IN ('project_agents', 'global_agents')),
    proposal_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (source_event_id)
        REFERENCES prompt_events(event_id) ON DELETE CASCADE,
    UNIQUE (source_session)
);
CREATE INDEX idx_proposal_tokens_expiry
    ON proposal_tokens(expires_at);

CREATE TABLE approval_consumptions (
    approval_ref_sha256 TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    source_session TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_sha256 TEXT,
    result_rule_id TEXT,
    transaction_id TEXT,
    consumed_at TEXT NOT NULL,
    FOREIGN KEY (source_event_id)
        REFERENCES prompt_events(event_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_approval_transaction
    ON approval_consumptions(transaction_id)
    WHERE transaction_id IS NOT NULL;

CREATE TABLE runtime_installation (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    identity_version TEXT NOT NULL,
    database_namespace TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    hook_config_sha256 TEXT NOT NULL,
    platform_command_sha256 TEXT NOT NULL,
    schema_sha256 TEXT NOT NULL,
    source_commit TEXT,
    source_tree_clean INTEGER NOT NULL CHECK (source_tree_clean IN (0, 1)),
    skill_sha256 TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE global_instruction_binding (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    binding_version TEXT NOT NULL,
    source_root TEXT NOT NULL,
    source_commit TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    target_file_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
CORE_TABLES = frozenset(
    {
        "core_schema",
        "prompt_events",
        "runtime_sessions",
        "proposal_tokens",
        "approval_consumptions",
        "runtime_installation",
        "global_instruction_binding",
    }
)

def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    canonical = "\n".join(
        "\0".join(str(value) for value in row)
        for row in rows
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Update this declared contract whenever CORE_SCHEMA_DDL changes. Every created
# or opened Store is compared with it through sqlite_master.
CORE_SCHEMA_SHA256 = (
    "f2153ec69335cbbac5bbab4330b4e213109c0bebcc8c56366b58fccb870c3c74"
)


class CoreDatabase:
    def __init__(
        self,
        path: Path | str,
        *,
        create: bool = False,
        runtime: bool = False,
        migrated_from_sha256: str | None = None,
        now: str | None = None,
    ) -> None:
        self.path = logical_absolute(path)
        existed = self.path.exists()
        if not existed and not create:
            raise CoreError(
                "store_unavailable",
                "Core Store does not exist",
                path=str(self.path),
            )
        if create:
            prepare_store_parent(self.path)
        secure_store_location(self.path, allow_missing=create)
        self.conn = sqlite3.connect(str(self.path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        try:
            secure_store_location(self.path, allow_missing=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA secure_delete = ON")
            self.conn.execute("PRAGMA busy_timeout = 30000")
            if runtime:
                _configure_runtime_storage(self.conn)
            if not existed:
                if not create or now is None:
                    raise CoreError(
                        "store_unavailable",
                        "new Core Store requires an explicit creation timestamp",
                    )
                self._create_schema(
                    migrated_from_sha256=migrated_from_sha256,
                    now=now,
                )
            self._assert_schema()
            secure_store_location(self.path, allow_missing=False)
        except BaseException:
            self.conn.close()
            raise

    def __enter__(self) -> "CoreDatabase":
        return self

    def __exit__(self, _type: object, _value: object, _tb: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.conn.in_transaction:
            yield
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def table_names(self) -> frozenset[str]:
        return frozenset(
            str(row["name"])
            for row in self.conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        )

    def integrity_check(self) -> str:
        return str(self.conn.execute("PRAGMA integrity_check").fetchone()[0])

    def foreign_key_violations(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.conn.execute("PRAGMA foreign_key_check")]

    def _create_schema(
        self, *, migrated_from_sha256: str | None, now: str
    ) -> None:
        self.conn.executescript(CORE_SCHEMA_DDL)
        self.conn.execute(
            """
            INSERT INTO core_schema (
                singleton, schema_version, schema_sha256,
                migrated_from_sha256, created_at, last_pruned_at
            ) VALUES (1, ?, ?, ?, ?, ?)
            """,
            (
                CORE_SCHEMA_VERSION,
                CORE_SCHEMA_SHA256,
                migrated_from_sha256,
                now,
                now,
            ),
        )
        self.conn.commit()

    def _assert_schema(self) -> None:
        tables = self.table_names()
        if tables != CORE_TABLES:
            raise CoreError(
                "migration_required",
                "Store is not Agent Memory Core v1",
                expected_tables=sorted(CORE_TABLES),
                actual_tables=sorted(tables),
            )
        row = self.conn.execute(
            """
            SELECT schema_version, schema_sha256
            FROM core_schema WHERE singleton = 1
            """
        ).fetchone()
        if (
            row is None
            or row["schema_version"] != CORE_SCHEMA_VERSION
            or row["schema_sha256"] != CORE_SCHEMA_SHA256
            or _schema_fingerprint(self.conn) != CORE_SCHEMA_SHA256
        ):
            raise CoreError(
                "schema_mismatch",
                "Core Store schema fingerprint does not match this runtime",
            )


def schema_manifest() -> dict[str, object]:
    return {
        "schema_version": CORE_SCHEMA_VERSION,
        "schema_sha256": f"sha256:{CORE_SCHEMA_SHA256}",
        "tables": sorted(CORE_TABLES),
    }


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _configure_runtime_storage(connection: sqlite3.Connection) -> None:
    try:
        row = connection.execute(
            f"PRAGMA journal_mode = {RUNTIME_JOURNAL_MODE}"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise CoreError(
            "runtime_journal_mode_unavailable",
            "Core Runtime could not enable the required journal mode",
            expected=RUNTIME_JOURNAL_MODE.lower(),
        ) from exc
    actual_journal = str(row[0]).lower() if row is not None else None
    if actual_journal != RUNTIME_JOURNAL_MODE.lower():
        raise CoreError(
            "runtime_journal_mode_unavailable",
            "Core Runtime could not enable the required journal mode",
            expected=RUNTIME_JOURNAL_MODE.lower(),
            actual=actual_journal,
        )

    try:
        connection.execute(
            f"PRAGMA synchronous = {RUNTIME_SYNCHRONOUS}"
        )
        row = connection.execute("PRAGMA synchronous").fetchone()
    except sqlite3.DatabaseError as exc:
        raise CoreError(
            "runtime_synchronous_unavailable",
            "Core Runtime could not enable the required synchronous mode",
            expected=RUNTIME_SYNCHRONOUS.lower(),
        ) from exc
    actual_synchronous = int(row[0]) if row is not None else None
    if actual_synchronous != _RUNTIME_SYNCHRONOUS_VALUE:
        raise CoreError(
            "runtime_synchronous_unavailable",
            "Core Runtime could not enable the required synchronous mode",
            expected=RUNTIME_SYNCHRONOUS.lower(),
            actual=actual_synchronous,
        )
