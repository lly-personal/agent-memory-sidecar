from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .codex_integration import (
    _git_identity,
    _package_root,
    _read_hooks,
    _write_hooks,
    codex_home,
    doctor,
    hooks_path,
    runtime_root,
)
from .database import (
    CORE_SCHEMA_SHA256,
    CORE_TABLES,
    CoreDatabase,
    canonical_json_sha256,
    schema_manifest,
)
from .errors import CoreError
from .file_security import (
    logical_absolute,
    secure_store_location,
    validate_store_identity,
)
from .identity import ProjectIdentity
from .installation import InstallationRegistry
from .runtime_ledger import EVENT_RETENTION_DAYS, SESSION_RETENTION_DAYS
from .runtime_package import (
    build_runtime_artifact,
    desired_hooks_document,
    hooks_bytes,
    install_runtime_artifact,
    runtime_commands,
    self_test_artifact,
    sidecar_hooks_sha256,
)
from .skill import (
    SkillSnapshot,
    discard_skill_snapshot,
    install_skill,
    plan_skill_install,
    restore_skill,
    snapshot_skill,
)
from .store_lifecycle import clean_store_rotation_lock_path


CUTOVER_CONTRACT = "agent_memory_core_cutover_v1"


@dataclass(frozen=True)
class CutoverPlan:
    status: str
    store_path: str
    source_schema_sha256: str
    target_schema_sha256: str
    artifact_sha256: str
    plan_hash: str
    source_tables: tuple[str, ...]
    source_counts: dict[str, int]
    migration_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CUTOVER_CONTRACT,
            "status": self.status,
            "store_path": self.store_path,
            "source_schema_sha256": f"sha256:{self.source_schema_sha256}",
            "target_schema": schema_manifest(),
            "artifact_sha256": f"sha256:{self.artifact_sha256}",
            "source_tables": list(self.source_tables),
            "source_counts": self.source_counts,
            "migration_policy": self.migration_policy,
            "backup_policy": {
                "retention": "permanent_manual_cleanup",
                "directory": str(Path(self.store_path).parent),
                "file_pattern": "memory.sqlite.pre-core-v1-<timestamp>-<nonce>.bak",
                "checksum": "sha256_sidecar",
            },
            "plan_hash": self.plan_hash,
            "applied": False,
        }


def preview_core_cutover(
    *,
    store_path: Path | str,
) -> CutoverPlan:
    target = validate_store_identity(store_path, allow_missing=False)
    artifact = build_runtime_artifact()
    with _open_readonly(target) as source:
        tables = _table_names(source)
        schema_sha = _legacy_schema_sha256(source)
        counts = {
            table: int(
                source.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
                ).fetchone()[0]
            )
            for table in sorted(tables)
        }
    status = "ready"
    if tables == CORE_TABLES:
        try:
            with CoreDatabase(target):
                status = "already_core_v1"
        except CoreError:
            status = "ready"
    policy = {
        "copy": [
            "retained prompt events",
            "retained runtime sessions",
            "approval consumptions with retained source events",
            "runtime installation identity",
            "global instruction binding",
        ],
        "invalidate": ["all legacy suggestion tokens"],
        "drop": [
            "memories",
            "memory_mutations",
            "runbooks",
            "runtime_deliveries",
            "generic state",
            "legacy schema history",
        ],
        "event_retention_days": EVENT_RETENTION_DAYS,
        "session_retention_days": SESSION_RETENTION_DAYS,
        "runtime_activation": "immutable_zipapp_and_atomic_hooks",
    }
    stable = {
        "contract_version": CUTOVER_CONTRACT,
        "store_path": str(target),
        "source_schema_sha256": schema_sha,
        "target_schema_sha256": CORE_SCHEMA_SHA256,
        "artifact_sha256": artifact.sha256,
        "source_tables": sorted(tables),
        "migration_policy": policy,
    }
    return CutoverPlan(
        status=status,
        store_path=str(target),
        source_schema_sha256=schema_sha,
        target_schema_sha256=CORE_SCHEMA_SHA256,
        artifact_sha256=artifact.sha256,
        plan_hash=canonical_json_sha256(stable),
        source_tables=tuple(sorted(tables)),
        source_counts=counts,
        migration_policy=policy,
    )


def apply_core_cutover(
    *,
    store_path: Path | str,
    identity: ProjectIdentity,
    approval_ref: str,
    expected_plan_hash: str,
) -> dict[str, Any]:
    target = validate_store_identity(store_path, allow_missing=False)
    expected = _digest(expected_plan_hash, "plan_hash")
    initial = preview_core_cutover(store_path=target)
    if initial.status == "already_core_v1":
        return {**initial.to_dict(), "status": "noop", "applied": False}
    if not hmac.compare_digest(expected, initial.plan_hash):
        raise CoreError(
            "cutover_plan_changed",
            "Core cutover plan changed; run dry-run again",
            expected_plan_hash=expected,
            actual_plan_hash=initial.plan_hash,
        )
    with _maintenance_lock(target):
        locked = preview_core_cutover(store_path=target)
        if not hmac.compare_digest(expected, locked.plan_hash):
            raise CoreError(
                "cutover_plan_changed",
                "Core cutover plan changed while acquiring maintenance lock",
            )
        approval = _validate_legacy_approval(
            store_path=target,
            approval_ref=approval_ref,
            identity=identity,
        )
        return _apply_locked(
            plan=locked,
            store_path=target,
            identity=identity,
            approval_ref=approval_ref,
            approval=approval,
        )


def _apply_locked(
    *,
    plan: CutoverPlan,
    store_path: Path,
    identity: ProjectIdentity,
    approval_ref: str,
    approval: dict[str, str],
) -> dict[str, Any]:
    secure_store_location(store_path, allow_missing=False)
    now = _now()
    artifact = build_runtime_artifact()
    if artifact.sha256 != plan.artifact_sha256:
        raise CoreError(
            "cutover_plan_changed",
            "runtime artifact changed after cutover planning",
        )
    backup_path, backup_sha = _backup_store(store_path=store_path, now=now)
    temporary = store_path.parent / f".{store_path.name}.core-v1-{uuid.uuid4().hex}.tmp"
    old_hooks, old_hook_bytes = _read_hooks()
    installed_artifact: Path | None = None
    store_replaced = False
    copied: dict[str, int] = {}
    database_namespace: str | None = None
    skill_snapshot: SkillSnapshot | None = None
    try:
        copied, database_namespace = _migrate_database(
            source_path=store_path,
            destination_path=temporary,
            source_schema_sha256=plan.source_schema_sha256,
            approval_ref=approval_ref,
            approval=approval,
            plan_hash=plan.plan_hash,
            now=now,
        )
        installed_artifact = install_runtime_artifact(
            artifact=artifact,
            runtime_root=runtime_root(),
        )
        commands = runtime_commands(artifact_path=installed_artifact)
        desired_hooks = desired_hooks_document(
            existing=old_hooks,
            commands=commands,
        )
        desired_hook_bytes = hooks_bytes(desired_hooks)
        hook_sha = sidecar_hooks_sha256(desired_hooks)
        source_commit, source_clean = _git_identity(_package_root())
        skill_plan = plan_skill_install()
        skill_snapshot = snapshot_skill(root=skill_plan.path.parent)
        skill = install_skill()
        with CoreDatabase(temporary) as db:
            registry = InstallationRegistry(db)
            with db.transaction():
                registry.bind_runtime(
                    artifact_path=installed_artifact,
                    artifact_sha256=artifact.sha256,
                    hook_config_sha256=hook_sha,
                    platform_command_sha256=commands[
                        "platform_command_sha256"
                    ],
                    source_commit=source_commit,
                    source_tree_clean=source_clean,
                    skill_sha256=skill.canonical_sha256,
                    database_namespace=database_namespace,
                )
            if db.integrity_check() != "ok" or db.foreign_key_violations():
                raise CoreError(
                    "cutover_integrity_failed",
                    "temporary Core Store failed integrity checks",
                )
        self_test_artifact(
            artifact_path=installed_artifact,
            store_path=temporary,
        )
        os.replace(temporary, store_path)
        store_replaced = True
        _write_hooks(desired_hook_bytes)
        self_test_artifact(
            artifact_path=installed_artifact,
            store_path=store_path,
        )
        report = doctor(identity=identity)
        if report["status"] != "ok":
            raise CoreError(
                "cutover_verification_failed",
                "strict doctor failed after Core cutover",
                doctor=report,
            )
        if skill_snapshot is not None:
            discard_skill_snapshot(skill_snapshot)
            skill_snapshot = None
        return {
            **plan.to_dict(),
            "status": "ok",
            "applied": True,
            "backup": {
                "path": str(backup_path),
                "sha256": f"sha256:{backup_sha}",
                "retention": "permanent_manual_cleanup",
            },
            "copied": copied,
            "runtime_artifact": {
                **artifact.to_dict(),
                "path": str(installed_artifact),
            },
            "doctor": report,
        }
    except BaseException:
        try:
            if store_replaced:
                _restore_backup(
                    backup_path=backup_path,
                    store_path=store_path,
                    expected_sha256=backup_sha,
                )
            if old_hook_bytes is None:
                hooks_path().unlink(missing_ok=True)
            else:
                _write_hooks(old_hook_bytes)
            if skill_snapshot is not None:
                restore_skill(skill_snapshot)
                skill_snapshot = None
        finally:
            temporary.unlink(missing_ok=True)
        raise


def _migrate_database(
    *,
    source_path: Path,
    destination_path: Path,
    source_schema_sha256: str,
    approval_ref: str,
    approval: dict[str, str],
    plan_hash: str,
    now: str,
) -> tuple[dict[str, int], str | None]:
    cutoff_events = (
        datetime.fromisoformat(now) - timedelta(days=EVENT_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    cutoff_sessions = (
        datetime.fromisoformat(now) - timedelta(days=SESSION_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    with _open_readonly(source_path) as source:
        database_namespace = _legacy_database_namespace(source)
        with CoreDatabase(
            destination_path,
            create=True,
            migrated_from_sha256=source_schema_sha256,
            now=now,
        ) as destination:
            copied_events = _copy_events(
                source=source,
                destination=destination,
                cutoff=cutoff_events,
            )
            copied_sessions = _copy_sessions(
                source=source,
                destination=destination,
                cutoff=cutoff_sessions,
            )
            copied_approvals = _copy_approvals(
                source=source,
                destination=destination,
            )
            _copy_global_binding(source=source, destination=destination, now=now)
            _insert_cutover_approval(
                destination=destination,
                approval_ref=approval_ref,
                approval=approval,
                plan_hash=plan_hash,
                now=now,
            )
            destination.conn.commit()
            if (
                destination.table_names() != CORE_TABLES
                or destination.integrity_check() != "ok"
                or destination.foreign_key_violations()
            ):
                raise CoreError(
                    "cutover_integrity_failed",
                    "migrated Core Store failed integrity checks",
                )
    return (
        {
            "prompt_events": copied_events,
            "runtime_sessions": copied_sessions,
            "approval_consumptions": copied_approvals + 1,
            "proposal_tokens": 0,
            "runtime_identity": int(database_namespace is not None),
        },
        database_namespace,
    )


def _legacy_database_namespace(source: sqlite3.Connection) -> str | None:
    if "state" not in _table_names(source):
        return None
    row = source.execute(
        """
        SELECT value FROM state
        WHERE key = 'runtime_install_identity_v1'
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(str(row["value"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    namespace = str(value.get("database_namespace") or "")
    if not re.fullmatch(r"db_[0-9a-f]{32}", namespace):
        return None
    return namespace


def _copy_events(
    *,
    source: sqlite3.Connection,
    destination: CoreDatabase,
    cutoff: str,
) -> int:
    if "events" not in _table_names(source):
        return 0
    rows = source.execute(
        """
        SELECT id, source_session, scope_key, cwd, repo_root, branch,
               raw_json, content, created_at
        FROM events
        WHERE event_type = 'UserPromptSubmit' AND created_at >= ?
        ORDER BY created_at, id
        """,
        (cutoff,),
    ).fetchall()
    count = 0
    for row in rows:
        try:
            metadata = json.loads(str(row["raw_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        raw_hash = str(metadata.get("content_hash") or "")
        digest = raw_hash.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            match = str(row["content"]).split("sha256:", 1)
            digest = match[1].split()[0] if len(match) == 2 else ""
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        try:
            prompt_bytes = max(0, int(metadata.get("content_bytes") or 0))
        except (TypeError, ValueError):
            prompt_bytes = 0
        bounded = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "content_hash": f"sha256:{digest}",
                "content_bytes": prompt_bytes,
                "retention_days": EVENT_RETENTION_DAYS,
                "migrated_from_legacy": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        destination.conn.execute(
            """
            INSERT INTO prompt_events (
                event_id, source_session, scope_key, cwd, repo_root, branch,
                prompt_sha256, prompt_bytes, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["id"]),
                str(row["source_session"]),
                str(row["scope_key"]),
                str(row["cwd"]),
                str(row["repo_root"]) if row["repo_root"] else None,
                str(row["branch"]) if row["branch"] else None,
                digest,
                prompt_bytes,
                bounded,
                str(row["created_at"]),
            ),
        )
        count += 1
    return count


def _copy_sessions(
    *,
    source: sqlite3.Connection,
    destination: CoreDatabase,
    cutoff: str,
) -> int:
    if "runtime_sessions" not in _table_names(source):
        return 0
    event_ids = {
        str(row[0])
        for row in destination.conn.execute(
            "SELECT event_id FROM prompt_events"
        )
    }
    rows = source.execute(
        """
        SELECT source_session, scope_key, context_epoch,
               last_prompt_event_id, last_seen_at
        FROM runtime_sessions WHERE last_seen_at >= ?
        """,
        (cutoff,),
    ).fetchall()
    for row in rows:
        event_id = (
            str(row["last_prompt_event_id"])
            if row["last_prompt_event_id"]
            and str(row["last_prompt_event_id"]) in event_ids
            else None
        )
        destination.conn.execute(
            """
            INSERT INTO runtime_sessions (
                source_session, scope_key, context_epoch,
                last_prompt_event_id, last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(row["source_session"]),
                str(row["scope_key"]),
                int(row["context_epoch"]),
                event_id,
                str(row["last_seen_at"]),
            ),
        )
    return len(rows)


def _copy_approvals(
    *,
    source: sqlite3.Connection,
    destination: CoreDatabase,
) -> int:
    if "state" not in _table_names(source):
        return 0
    state_rows = {
        str(row["key"]).split(":", 1)[1]: row
        for row in source.execute(
            """
            SELECT key, value, updated_at FROM state
            WHERE key LIKE 'approval_ref:%'
            """
        )
    }
    copied = 0
    for event in destination.conn.execute(
        """
        SELECT event_id, source_session, scope_key FROM prompt_events
        """
    ):
        digest = hashlib.sha256(
            f"user_prompt:{event['event_id']}".encode("utf-8")
        ).hexdigest()
        state = state_rows.get(digest)
        if state is None:
            continue
        try:
            value = json.loads(str(state["value"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        destination.conn.execute(
            """
            INSERT INTO approval_consumptions (
                approval_ref_sha256, source_event_id, source_session,
                scope_key, operation, request_sha256, result_rule_id,
                transaction_id, consumed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                digest,
                str(event["event_id"]),
                str(event["source_session"]),
                str(event["scope_key"]),
                str(value.get("operation") or "legacy"),
                value.get("request_hash"),
                value.get("result_memory_id"),
                str(state["updated_at"]),
            ),
        )
        copied += 1
    return copied


def _copy_global_binding(
    *,
    source: sqlite3.Connection,
    destination: CoreDatabase,
    now: str,
) -> None:
    if "state" not in _table_names(source):
        return
    row = source.execute(
        """
        SELECT value FROM state
        WHERE key = 'global_instruction_binding_v2'
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return
    try:
        value = json.loads(str(row["value"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return
    if not isinstance(value, dict):
        return
    try:
        registry = InstallationRegistry(destination)
        registry.bind_global(
            source_root=str(value["source_root"]),
            source_commit=str(value["source_commit"]),
            source_file_sha256=str(value["source_file_sha256"]),
            target_file_sha256=str(value["target_file_sha256"]),
            updated_at=now,
        )
    except (KeyError, CoreError, TypeError, ValueError):
        return


def _insert_cutover_approval(
    *,
    destination: CoreDatabase,
    approval_ref: str,
    approval: dict[str, str],
    plan_hash: str,
    now: str,
) -> None:
    digest = hashlib.sha256(approval_ref.encode("utf-8")).hexdigest()
    destination.conn.execute(
        """
        INSERT INTO approval_consumptions (
            approval_ref_sha256, source_event_id, source_session,
            scope_key, operation, request_sha256, result_rule_id,
            transaction_id, consumed_at
        ) VALUES (?, ?, ?, ?, 'maintenance.core_cutover', ?, NULL, ?, ?)
        """,
        (
            digest,
            approval["event_id"],
            approval["source_session"],
            approval["scope_key"],
            plan_hash,
            f"tx_cutover_{uuid.uuid4().hex}",
            now,
        ),
    )


def _validate_legacy_approval(
    *,
    store_path: Path,
    approval_ref: str,
    identity: ProjectIdentity,
) -> dict[str, str]:
    prefix = "user_prompt:"
    value = str(approval_ref or "").strip()
    if not value.startswith(prefix):
        raise CoreError(
            "approval_invalid",
            "Core cutover requires a current user_prompt approval ref",
        )
    event_id = value[len(prefix) :].strip()
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    with _open_readonly(store_path) as source:
        tables = _table_names(source)
        if not {"events", "runtime_sessions", "state"} <= tables:
            raise CoreError(
                "approval_invalid",
                "legacy Store lacks authorization tables",
            )
        row = source.execute(
            """
            SELECT e.id, e.source_session, e.scope_key, e.created_at,
                   s.last_prompt_event_id
            FROM events e
            JOIN runtime_sessions s ON s.source_session = e.source_session
            WHERE e.id = ? AND e.event_type = 'UserPromptSubmit'
            """,
            (event_id,),
        ).fetchone()
        if (
            row is None
            or str(row["last_prompt_event_id"] or "") != event_id
            or str(row["scope_key"]) != identity.scope_key
            or _parse_time(str(row["created_at"]))
            < datetime.now(UTC).replace(microsecond=0)
            - timedelta(days=EVENT_RETENTION_DAYS)
        ):
            raise CoreError(
                "approval_invalid",
                "cutover approval is missing, stale, or from another scope",
            )
        used = source.execute(
            """
            SELECT 1 FROM state WHERE key = ?
            """,
            (f"approval_ref:{digest}",),
        ).fetchone()
        if used is not None:
            raise CoreError(
                "approval_invalid",
                "cutover approval ref was already consumed",
            )
        return {
            "event_id": event_id,
            "source_session": str(row["source_session"]),
            "scope_key": str(row["scope_key"]),
        }


def _backup_store(*, store_path: Path, now: str) -> tuple[Path, str]:
    stamp = datetime.fromisoformat(now).strftime("%Y%m%dT%H%M%SZ")
    nonce = uuid.uuid4().hex[:12]
    backup = Path(f"{store_path}.pre-core-v1-{stamp}-{nonce}.bak")
    checksum = Path(f"{backup}.sha256")
    temporary = backup.parent / f".{backup.name}.{uuid.uuid4().hex}.tmp"
    with _open_readonly(store_path) as source:
        destination = sqlite3.connect(str(temporary))
        try:
            source.backup(destination)
        finally:
            destination.close()
    with temporary.open("r+b") as handle:
        os.fsync(handle.fileno())
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    checksum_temp = checksum.parent / f".{checksum.name}.{uuid.uuid4().hex}.tmp"
    try:
        checksum_temp.write_text(
            f"{digest}  {backup.name}\n",
            encoding="utf-8",
            newline="\n",
        )
        with checksum_temp.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, backup)
        os.replace(checksum_temp, checksum)
        secure_store_location(backup, allow_missing=False)
    finally:
        temporary.unlink(missing_ok=True)
        checksum_temp.unlink(missing_ok=True)
    return backup, digest


def _restore_backup(
    *,
    backup_path: Path,
    store_path: Path,
    expected_sha256: str,
) -> None:
    if hashlib.sha256(backup_path.read_bytes()).hexdigest() != expected_sha256:
        raise CoreError(
            "cutover_rollback_failed",
            "migration backup checksum changed",
        )
    temporary = store_path.parent / f".{store_path.name}.restore-{uuid.uuid4().hex}.tmp"
    shutil.copyfile(backup_path, temporary)
    os.replace(temporary, store_path)


@contextmanager
def _maintenance_lock(store_path: Path) -> Iterator[None]:
    lock = clean_store_rotation_lock_path(store_path)
    token = uuid.uuid4().hex
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CoreError(
            "maintenance_in_progress",
            "another Store maintenance operation is active",
        ) from exc
    try:
        os.write(
            descriptor,
            json.dumps(
                {
                    "operation": "core_cutover",
                    "token": token,
                    "pid": os.getpid(),
                    "started_at": _now(),
                },
                sort_keys=True,
            ).encode("utf-8"),
        )
    finally:
        os.close(descriptor)
    try:
        yield
    finally:
        try:
            value = json.loads(lock.read_text(encoding="utf-8"))
            if value.get("token") != token:
                raise CoreError(
                    "maintenance_lock_changed",
                    "maintenance lock ownership changed",
                )
            lock.unlink()
        except FileNotFoundError as exc:
            raise CoreError(
                "maintenance_lock_changed",
                "maintenance lock disappeared",
            ) from exc


@contextmanager
def _open_readonly(path: Path) -> Iterator[sqlite3.Connection]:
    target = validate_store_identity(path, allow_missing=False)
    connection = sqlite3.connect(
        target.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CoreError(
            "approval_invalid",
            "legacy approval event has an invalid timestamp",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _table_names(connection: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        str(row["name"])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    )


def _legacy_schema_sha256(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    manifest = [
        {
            "type": str(row["type"]),
            "name": str(row["name"]),
            "table": str(row["tbl_name"]),
            "sql": str(row["sql"] or ""),
        }
        for row in rows
    ]
    return canonical_json_sha256(manifest)


def _digest(value: str, name: str) -> str:
    text = str(value or "").removeprefix("sha256:").strip().casefold()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise CoreError("invalid_digest", f"{name} must be SHA-256")
    return text


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
