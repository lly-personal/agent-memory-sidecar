from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import CORE_SCHEMA_SHA256, CoreDatabase, schema_manifest
from .errors import CoreError
from .identity import ProjectIdentity
from .installation import InstallationRegistry
from .instructions import InstructionRepository, atomic_write, read_document
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
    installed_skill_sha256,
    plan_skill_install,
    restore_skill,
    snapshot_skill,
)


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.home() / ".codex").resolve()
    )


def store_path() -> Path:
    return codex_home() / "agent-memory-sidecar" / "memory.sqlite"


def hooks_path() -> Path:
    return codex_home() / "hooks.json"


def runtime_root() -> Path:
    return codex_home() / "agent-memory-sidecar" / "runtime"


def setup(
    *,
    apply: bool,
    identity: ProjectIdentity,
    global_rules_source: Path | str | None = None,
    allow_global_source_rebind: bool = False,
) -> dict[str, Any]:
    if allow_global_source_rebind and global_rules_source is None:
        raise CoreError(
            "global_rebind_source_missing",
            "an explicit global source is required for rebinding",
        )
    target_store = store_path()
    existed = target_store.exists()
    if existed:
        try:
            with CoreDatabase(target_store) as db:
                existing_binding = InstallationRegistry(db).global_binding()
                registry_snapshot = _registry_snapshot(db)
        except CoreError as exc:
            if exc.code in {"migration_required", "schema_mismatch"}:
                raise CoreError(
                    "migration_required",
                    "legacy Store requires an explicit Core cutover",
                    next_action="maintenance core-cutover --dry-run",
                ) from exc
            raise
    else:
        existing_binding = None
        registry_snapshot = None

    artifact = build_runtime_artifact()
    artifact_path = runtime_root() / artifact.file_name
    commands = runtime_commands(artifact_path=artifact_path)
    existing_hooks, existing_hook_bytes = _read_hooks()
    desired_hooks = desired_hooks_document(
        existing=existing_hooks,
        commands=commands,
    )
    desired_hook_bytes = hooks_bytes(desired_hooks)
    hook_sha = sidecar_hooks_sha256(desired_hooks)
    current_sidecar_sha = sidecar_hooks_sha256(existing_hooks)
    skill_plan = plan_skill_install()
    source_root = (
        Path(global_rules_source).expanduser().resolve()
        if global_rules_source is not None
        else (
            Path(existing_binding.source_root)
            if existing_binding is not None
            else None
        )
    )
    global_plan = _global_materialization_plan(
        identity=identity,
        source_root=source_root,
        existing_binding=(
            existing_binding.to_dict()
            if existing_binding is not None
            else None
        ),
        allow_source_rebind=allow_global_source_rebind,
    )
    plan = {
        "schema": schema_manifest(),
        "store": str(target_store),
        "store_action": "create" if not existed else "noop",
        "runtime_artifact": {
            **artifact.to_dict(),
            "path": str(artifact_path),
            "action": (
                "noop"
                if artifact_path.exists()
                and hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                == artifact.sha256
                else "install"
            ),
        },
        "hooks": {
            "path": str(hooks_path()),
            "action": (
                "noop"
                if current_sidecar_sha == hook_sha
                else "install"
            ),
            "sha256": f"sha256:{hook_sha}",
        },
        "skill": skill_plan.to_dict(),
        "global": global_plan,
    }
    if not apply:
        return {"status": "ready", "applied": False, "plan": plan}

    created_store = False
    installed_artifact_path: Path | None = None
    old_target: bytes | None = None
    target_path: Path | None = None
    skill_snapshot: SkillSnapshot | None = None
    try:
        if not existed:
            with CoreDatabase(
                target_store,
                create=True,
                now=_now(),
            ):
                pass
            created_store = True
        installed_artifact_path = install_runtime_artifact(
            artifact=artifact,
            runtime_root=runtime_root(),
        )
        self_test_artifact(
            artifact_path=installed_artifact_path,
            store_path=target_store,
        )
        if global_plan and global_plan["materialize"]:
            target_path = Path(str(global_plan["target_path"]))
            old_target = target_path.read_bytes() if target_path.exists() else None
            atomic_write(
                target_path,
                Path(str(global_plan["source_path"])).read_bytes(),
            )
        if current_sidecar_sha != hook_sha:
            _write_hooks(desired_hook_bytes)
        skill_snapshot = snapshot_skill(root=skill_plan.path.parent)
        installed_skill = install_skill()
        source_commit, source_clean = _git_identity(_package_root())
        with CoreDatabase(target_store) as db:
            registry = InstallationRegistry(db)
            with db.transaction():
                runtime = registry.bind_runtime(
                    artifact_path=installed_artifact_path,
                    artifact_sha256=artifact.sha256,
                    hook_config_sha256=hook_sha,
                    platform_command_sha256=commands[
                        "platform_command_sha256"
                    ],
                    source_commit=source_commit,
                    source_tree_clean=source_clean,
                    skill_sha256=installed_skill.canonical_sha256,
                )
                if global_plan:
                    registry.bind_global(
                        source_root=str(global_plan["source_root"]),
                        source_commit=str(global_plan["source_commit"]),
                        source_file_sha256=str(
                            global_plan["source_file_sha256"]
                        ),
                        target_file_sha256=str(
                            global_plan["source_file_sha256"]
                        ),
                    )
        result = doctor(identity=identity)
        if result["status"] != "ok":
            raise CoreError(
                "setup_verification_failed",
                "setup completed writes but strict doctor did not pass",
                doctor=result,
            )
        if skill_snapshot is not None:
            discard_skill_snapshot(skill_snapshot)
            skill_snapshot = None
        return {
            "status": "ok",
            "applied": True,
            "plan": plan,
            "runtime": runtime.to_dict(),
            "doctor": result,
        }
    except BaseException:
        try:
            if existing_hook_bytes is None:
                hooks_path().unlink(missing_ok=True)
            else:
                _write_hooks(existing_hook_bytes)
            if target_path is not None:
                if old_target is None:
                    target_path.unlink(missing_ok=True)
                else:
                    atomic_write(target_path, old_target)
            if skill_snapshot is not None:
                restore_skill(skill_snapshot)
                skill_snapshot = None
            if not created_store and registry_snapshot is not None:
                _restore_registry(target_store, registry_snapshot)
            if created_store:
                target_store.unlink(missing_ok=True)
        finally:
            raise


def doctor(*, identity: ProjectIdentity) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    target_store = store_path()
    try:
        with CoreDatabase(target_store) as db:
            registry = InstallationRegistry(db)
            runtime = registry.runtime()
            binding = registry.global_binding()
            integrity = db.integrity_check()
            foreign_keys = db.foreign_key_violations()
    except CoreError as exc:
        return {
            "status": "error",
            "errors": [exc.to_dict()],
            "store": str(target_store),
        }
    if runtime is None:
        errors.append(
            {
                "code": "runtime_installation_missing",
                "message": "runtime installation record is missing",
            }
        )
    else:
        artifact = Path(runtime.artifact_path)
        expected_artifact = (
            runtime_root()
            / f"agent-memory-{runtime.artifact_sha256[:16]}.pyz"
        ).resolve(strict=False)
        if (
            artifact.resolve(strict=False) != expected_artifact
            or not artifact.exists()
            or hashlib.sha256(artifact.read_bytes()).hexdigest()
            != runtime.artifact_sha256
        ):
            errors.append(
                {
                    "code": "runtime_artifact_mismatch",
                    "message": "immutable runtime artifact is missing or changed",
                }
            )
        if runtime.schema_sha256 != CORE_SCHEMA_SHA256:
            errors.append(
                {
                    "code": "runtime_schema_mismatch",
                    "message": "runtime identity uses another schema",
                }
            )
    current_hooks, _current_hook_bytes = _read_hooks()
    if runtime is not None:
        commands = runtime_commands(artifact_path=runtime.artifact_path)
        desired = desired_hooks_document(
            existing=current_hooks,
            commands=commands,
        )
        expected_sidecar_sha = sidecar_hooks_sha256(desired)
        current_sidecar_sha = sidecar_hooks_sha256(current_hooks)
        if current_sidecar_sha != expected_sidecar_sha:
            errors.append(
                {
                    "code": "hook_config_mismatch",
                    "message": "required Hook entries do not match immutable runtime",
                }
            )
        if current_sidecar_sha != runtime.hook_config_sha256:
            errors.append(
                {
                    "code": "hook_identity_mismatch",
                    "message": "Hook bytes do not match the bound runtime identity",
                }
            )
        if (
            commands["platform_command_sha256"]
            != runtime.platform_command_sha256
        ):
            errors.append(
                {
                    "code": "platform_command_mismatch",
                    "message": "runtime command does not match the bound identity",
                }
            )
        installed_skill = installed_skill_sha256(
            plan_skill_install().path
        )
        if (
            runtime.skill_sha256 is None
            or installed_skill != runtime.skill_sha256
        ):
            errors.append(
                {
                    "code": "skill_installation_mismatch",
                    "message": "installed Skill does not match the bound identity",
                }
            )
    global_report: dict[str, Any] | None = None
    if binding is not None:
        source = binding.source_file
        target = InstructionRepository().target_path(
            target="global_agents",
            identity=identity,
        )
        try:
            source_bytes = source.read_bytes()
            target_bytes = target.read_bytes()
            source_sha = hashlib.sha256(source_bytes).hexdigest()
            target_sha = hashlib.sha256(target_bytes).hexdigest()
            parity = (
                source_bytes == target_bytes
                and source_sha == binding.source_file_sha256
                and target_sha == binding.target_file_sha256
            )
        except OSError:
            parity = False
            source_sha = target_sha = ""
        global_report = {
            "source": str(source),
            "target": str(target),
            "full_document_parity": parity,
            "source_sha256": (
                f"sha256:{source_sha}" if source_sha else None
            ),
            "target_sha256": (
                f"sha256:{target_sha}" if target_sha else None
            ),
        }
        if not parity:
            errors.append(
                {
                    "code": "global_instruction_drift",
                    "message": "global source and local target lost full-document parity",
                }
            )
    if integrity != "ok" or foreign_keys:
        errors.append(
            {
                "code": "store_integrity_failed",
                "message": "Core Store integrity checks failed",
                "integrity": integrity,
                "foreign_key_violations": foreign_keys,
            }
        )
    return {
        "status": "ok" if not errors else "error",
        "store": {
            "path": str(target_store),
            "schema": schema_manifest(),
            "integrity": integrity,
            "foreign_key_violations": foreign_keys,
        },
        "runtime": runtime.to_dict() if runtime is not None else None,
        "global": global_report,
        "errors": errors,
    }


def _global_materialization_plan(
    *,
    identity: ProjectIdentity,
    source_root: Path | None,
    existing_binding: dict[str, Any] | None,
    allow_source_rebind: bool = False,
) -> dict[str, Any] | None:
    del identity
    if source_root is None:
        return None
    source = source_root / "global" / "AGENTS.md"
    if not source.exists():
        raise CoreError(
            "global_source_missing",
            "global source must contain global/AGENTS.md",
            path=str(source),
        )
    source_snapshot = read_document(
        path=source,
        target="global_agents",
    )
    target = codex_home() / "AGENTS.md"
    target_snapshot = read_document(
        path=target,
        target="global_agents",
    )
    source_commit, source_clean = _git_identity(source_root)
    if source_commit is None or not source_clean:
        raise CoreError(
            "global_source_unready",
            "global source must be a clean Git checkout",
            source_root=str(source_root),
        )
    if existing_binding is not None:
        bound_root = Path(str(existing_binding["source_root"])).resolve()
        source_rebind = bound_root != source_root.resolve()
        if source_rebind and not allow_source_rebind:
            raise CoreError(
                "global_binding_mismatch",
                "setup cannot silently replace the bound global source",
            )
        bound_target_sha = str(
            existing_binding["target_file_sha256"]
        ).removeprefix("sha256:")
        if target_snapshot.file_sha256 != bound_target_sha:
            raise CoreError(
                "global_instruction_drift",
                "local global target changed after the last binding",
                target=str(target),
            )
    elif (
        target_snapshot.data
        and target_snapshot.data != source_snapshot.data
    ):
        raise CoreError(
            "global_instruction_drift",
            "non-empty local global target differs from the selected source",
            source=str(source),
            target=str(target),
        )
    else:
        source_rebind = False
    return {
        "source_root": str(source_root),
        "source_path": str(source),
        "target_path": str(target),
        "source_commit": source_commit,
        "source_file_sha256": source_snapshot.file_sha256,
        "materialize": target_snapshot.data != source_snapshot.data,
        "rebind": source_rebind,
    }


def _read_hooks() -> tuple[dict[str, Any], bytes | None]:
    path = hooks_path()
    if not path.exists():
        return {}, None
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoreError(
            "hook_config_invalid",
            "Codex hooks.json is unreadable or invalid",
            path=str(path),
        ) from exc
    if not isinstance(value, dict):
        raise CoreError(
            "hook_config_invalid",
            "Codex hooks.json must contain a JSON object",
        )
    return value, data


def _write_hooks(data: bytes) -> None:
    path = hooks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _registry_snapshot(
    db: CoreDatabase,
) -> dict[str, dict[str, Any] | None]:
    return {
        table: (dict(row) if row is not None else None)
        for table in (
            "runtime_installation",
            "global_instruction_binding",
        )
        for row in (
            db.conn.execute(
                f"SELECT * FROM {table} WHERE singleton = 1"
            ).fetchone(),
        )
    }


def _restore_registry(
    target_store: Path,
    snapshot: dict[str, dict[str, Any] | None],
) -> None:
    with CoreDatabase(target_store) as db:
        with db.transaction():
            for table, row in snapshot.items():
                db.conn.execute(f"DELETE FROM {table} WHERE singleton = 1")
                if row is None:
                    continue
                columns = tuple(row)
                placeholders = ", ".join("?" for _ in columns)
                db.conn.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({placeholders})",
                    tuple(row[column] for column in columns),
                )


def _git_identity(root: Path) -> tuple[str | None, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None, False
    value = commit.stdout.strip() if commit.returncode == 0 else ""
    return (value or None), status.returncode == 0 and not status.stdout.strip()


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
