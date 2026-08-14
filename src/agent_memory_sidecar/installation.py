from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import CORE_SCHEMA_SHA256, CoreDatabase
from .errors import CoreError
from .file_security import logical_absolute


RUNTIME_IDENTITY_VERSION = "runtime_installation_v1"
GLOBAL_BINDING_VERSION = "global_instruction_binding_v3"


@dataclass(frozen=True)
class RuntimeInstallation:
    database_namespace: str
    artifact_path: str
    artifact_sha256: str
    hook_config_sha256: str
    platform_command_sha256: str
    schema_sha256: str
    source_commit: str | None
    source_tree_clean: bool
    skill_sha256: str | None
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_version": RUNTIME_IDENTITY_VERSION,
            "database_namespace": self.database_namespace,
            "artifact_path": self.artifact_path,
            "artifact_sha256": f"sha256:{self.artifact_sha256}",
            "hook_config_sha256": f"sha256:{self.hook_config_sha256}",
            "platform_command_sha256": f"sha256:{self.platform_command_sha256}",
            "schema_sha256": f"sha256:{self.schema_sha256}",
            "source_commit": self.source_commit,
            "source_tree_clean": self.source_tree_clean,
            "skill_sha256": (
                f"sha256:{self.skill_sha256}" if self.skill_sha256 else None
            ),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class GlobalBinding:
    source_root: str
    source_commit: str
    source_file_sha256: str
    target_file_sha256: str
    updated_at: str

    @property
    def source_file(self) -> Path:
        return Path(self.source_root) / "global" / "AGENTS.md"

    def to_dict(self) -> dict[str, str]:
        return {
            "binding_version": GLOBAL_BINDING_VERSION,
            "source_root": self.source_root,
            "source_commit": self.source_commit,
            "source_file_sha256": f"sha256:{self.source_file_sha256}",
            "target_file_sha256": f"sha256:{self.target_file_sha256}",
            "updated_at": self.updated_at,
        }


class InstallationRegistry:
    def __init__(self, db: CoreDatabase) -> None:
        self.db = db

    def runtime(self) -> RuntimeInstallation | None:
        row = self.db.conn.execute(
            "SELECT * FROM runtime_installation WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return None
        return RuntimeInstallation(
            database_namespace=str(row["database_namespace"]),
            artifact_path=str(row["artifact_path"]),
            artifact_sha256=str(row["artifact_sha256"]),
            hook_config_sha256=str(row["hook_config_sha256"]),
            platform_command_sha256=str(row["platform_command_sha256"]),
            schema_sha256=str(row["schema_sha256"]),
            source_commit=(
                str(row["source_commit"]) if row["source_commit"] else None
            ),
            source_tree_clean=bool(row["source_tree_clean"]),
            skill_sha256=(
                str(row["skill_sha256"]) if row["skill_sha256"] else None
            ),
            updated_at=str(row["updated_at"]),
        )

    def bind_runtime(
        self,
        *,
        artifact_path: Path | str,
        artifact_sha256: str,
        hook_config_sha256: str,
        platform_command_sha256: str,
        source_commit: str | None,
        source_tree_clean: bool,
        skill_sha256: str | None,
        database_namespace: str | None = None,
        updated_at: str | None = None,
    ) -> RuntimeInstallation:
        existing = self.runtime()
        requested_namespace = (
            str(database_namespace).strip()
            if database_namespace is not None
            else None
        )
        if requested_namespace is not None and not re.fullmatch(
            r"db_[0-9a-f]{32}",
            requested_namespace,
        ):
            raise CoreError(
                "runtime_identity_invalid",
                "database namespace is invalid",
            )
        value = RuntimeInstallation(
            database_namespace=(
                existing.database_namespace
                if existing is not None
                else requested_namespace or f"db_{uuid.uuid4().hex}"
            ),
            artifact_path=str(Path(artifact_path).resolve(strict=False)),
            artifact_sha256=_digest(artifact_sha256, "artifact_sha256"),
            hook_config_sha256=_digest(
                hook_config_sha256, "hook_config_sha256"
            ),
            platform_command_sha256=_digest(
                platform_command_sha256, "platform_command_sha256"
            ),
            schema_sha256=CORE_SCHEMA_SHA256,
            source_commit=str(source_commit) if source_commit else None,
            source_tree_clean=bool(source_tree_clean),
            skill_sha256=(
                _digest(skill_sha256, "skill_sha256")
                if skill_sha256 is not None
                else None
            ),
            updated_at=updated_at or _now(),
        )
        self.db.conn.execute(
            """
            INSERT INTO runtime_installation (
                singleton, identity_version, database_namespace, artifact_path,
                artifact_sha256, hook_config_sha256, platform_command_sha256,
                schema_sha256, source_commit, source_tree_clean, skill_sha256,
                updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                identity_version=excluded.identity_version,
                database_namespace=excluded.database_namespace,
                artifact_path=excluded.artifact_path,
                artifact_sha256=excluded.artifact_sha256,
                hook_config_sha256=excluded.hook_config_sha256,
                platform_command_sha256=excluded.platform_command_sha256,
                schema_sha256=excluded.schema_sha256,
                source_commit=excluded.source_commit,
                source_tree_clean=excluded.source_tree_clean,
                skill_sha256=excluded.skill_sha256,
                updated_at=excluded.updated_at
            """,
            (
                RUNTIME_IDENTITY_VERSION,
                value.database_namespace,
                value.artifact_path,
                value.artifact_sha256,
                value.hook_config_sha256,
                value.platform_command_sha256,
                value.schema_sha256,
                value.source_commit,
                int(value.source_tree_clean),
                value.skill_sha256,
                value.updated_at,
            ),
        )
        return value

    def global_binding(self) -> GlobalBinding | None:
        row = self.db.conn.execute(
            "SELECT * FROM global_instruction_binding WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return None
        return GlobalBinding(
            source_root=str(row["source_root"]),
            source_commit=str(row["source_commit"]),
            source_file_sha256=str(row["source_file_sha256"]),
            target_file_sha256=str(row["target_file_sha256"]),
            updated_at=str(row["updated_at"]),
        )

    def bind_global(
        self,
        *,
        source_root: Path | str,
        source_commit: str,
        source_file_sha256: str,
        target_file_sha256: str,
        updated_at: str | None = None,
    ) -> GlobalBinding:
        root = logical_absolute(source_root)
        if not root.is_absolute():
            raise CoreError(
                "global_binding_invalid",
                "global source root must be absolute",
            )
        value = GlobalBinding(
            source_root=str(root),
            source_commit=str(source_commit).strip(),
            source_file_sha256=_digest(
                source_file_sha256, "source_file_sha256"
            ),
            target_file_sha256=_digest(
                target_file_sha256, "target_file_sha256"
            ),
            updated_at=updated_at or _now(),
        )
        if not value.source_commit:
            raise CoreError(
                "global_binding_invalid",
                "global source commit is required",
            )
        self.db.conn.execute(
            """
            INSERT INTO global_instruction_binding (
                singleton, binding_version, source_root, source_commit,
                source_file_sha256, target_file_sha256, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
                binding_version=excluded.binding_version,
                source_root=excluded.source_root,
                source_commit=excluded.source_commit,
                source_file_sha256=excluded.source_file_sha256,
                target_file_sha256=excluded.target_file_sha256,
                updated_at=excluded.updated_at
            """,
            (
                GLOBAL_BINDING_VERSION,
                value.source_root,
                value.source_commit,
                value.source_file_sha256,
                value.target_file_sha256,
                value.updated_at,
            ),
        )
        return value


def _digest(value: str, name: str) -> str:
    text = str(value or "").removeprefix("sha256:").strip().casefold()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise CoreError("invalid_digest", f"{name} must be SHA-256")
    return text


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
