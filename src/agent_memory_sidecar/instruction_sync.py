"""On-demand whole-document distribution; no rule discovery or authorization events."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .database import CORE_SCHEMA_SHA256, CORE_SCHEMA_VERSION, CoreDatabase, _schema_fingerprint
from .errors import CoreError
from .file_security import logical_absolute, prepare_store_parent, secure_store_location, validate_store_identity
from .installation import InstallationRegistry
from .instructions import InstructionRepository, assert_physical_directory, atomic_write, read_document, read_document_bytes

CONTRACT = "global_instruction_sync_v1"
OWNER_FILE = "global/AGENTS.md"
HOST_ENV = {"codex": "CODEX_HOME", "pi": "PI_CODING_AGENT_DIR"}
GIT_OBSERVATION_SECONDS = 60


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _git(root: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items()
           if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, env=env, timeout=GIT_OBSERVATION_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoreError("instruction_source_unavailable", "Git source operation did not complete") from exc
    if result.returncode:
        # Git stderr can contain credentials and private remote URLs.
        raise CoreError("instruction_source_unavailable", "Git source operation failed")
    return result.stdout


def _origin(root: Path) -> str:
    origin = _git(root, "remote", "get-url", "origin").decode().strip()
    parsed = urlsplit(origin)
    if parsed.scheme in {"http", "https"} and (parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise CoreError("instruction_source_credentials", "Use Git credentials, not credentials embedded in a remote")
    return origin


def _clean(root: Path) -> None:
    assert_physical_directory(root)
    if _git(root, "status", "--porcelain"):
        raise CoreError("instruction_source_dirty", "Publish or reconcile the source worktree before synchronizing")


def _bytes(path: Path) -> bytes | None:
    snapshot = read_document(path=path, target="global_agents")
    return snapshot.data if snapshot.existed else None


def _record(path: Path) -> dict[str, Any] | None:
    data = _bytes(path)
    if data is None:
        return None
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except (ValueError, UnicodeError) as exc:
        raise CoreError("instruction_sync_state_invalid", "Local synchronization metadata is invalid") from exc


def _store(home: Path) -> Path:
    return home / "agent-memory-sidecar" / "memory.sqlite"


def _binding(home: Path) -> dict[str, Any] | None:
    path = _store(home)
    if not path.exists():
        return None
    validate_store_identity(path, allow_missing=False)
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
            if _schema_fingerprint(conn) != CORE_SCHEMA_SHA256:
                raise CoreError("instruction_binding_unavailable", "Existing Store requires its supported migration path")
            schema = conn.execute("SELECT schema_version, schema_sha256 FROM core_schema WHERE singleton=1").fetchone()
            if schema != (CORE_SCHEMA_VERSION, CORE_SCHEMA_SHA256):
                raise CoreError("instruction_binding_unavailable", "Existing Store schema does not match this release")
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM global_instruction_binding WHERE singleton=1").fetchone()
            return dict(row) if row else None
    except sqlite3.DatabaseError as exc:
        raise CoreError("instruction_binding_unavailable", "Existing Store requires its supported migration path") from exc


def _set_binding(home: Path, value: dict[str, Any] | None) -> None:
    path = _store(home)
    with CoreDatabase(path, create=not path.exists(), now=datetime.now(UTC).isoformat()) as db:
        with db.transaction():
            db.conn.execute("DELETE FROM global_instruction_binding WHERE singleton=1")
            if value is not None:
                InstallationRegistry(db).bind_global(**{
                    key: value[key] for key in (
                        "source_root", "source_commit", "source_file_sha256", "target_file_sha256", "updated_at"
                    )
                })


def _targets(codex_home: Path | None, pi_agent_dir: Path | None, saved: dict[str, Any]) -> dict[str, Path]:
    explicit = {name: path for name, path in {"codex": codex_home, "pi": pi_agent_dir}.items() if path is not None}
    targets = {name: logical_absolute(path) for name, path in saved.get("targets", {}).items()}
    if set(targets) - set(HOST_ENV):
        raise CoreError("instruction_sync_state_invalid", "Unknown host binding")
    defaults = {"codex": Path.home() / ".codex", "pi": Path.home() / ".pi" / "agent"}
    for name in HOST_ENV:
        observed = explicit.get(name)
        configured = os.environ.get(HOST_ENV[name])
        if observed is None and configured:
            observed = Path(configured)
        if observed is not None:
            observed = logical_absolute(observed)
            if name in targets and targets[name] != observed:
                raise CoreError("instruction_target_rebind_required", "Existing host directory differs; review the binding before changing it", host=name)
            targets[name] = observed
        elif name not in targets and not explicit and defaults[name].is_dir():
            targets[name] = logical_absolute(defaults[name])
    if not targets:
        raise CoreError("instruction_targets_missing", "No enrolled or observed host directory")
    if len({os.path.normcase(str(path)) for path in targets.values()}) != len(targets):
        raise CoreError("instruction_target_alias", "Hosts must have distinct instruction directories")
    return targets


def synchronize(*, source: Path | None = None, codex_home: Path | None = None,
                pi_agent_dir: Path | None = None, state_dir: Path | None = None,
                apply: bool = False, plan_hash: str | None = None,
                adopt_existing: list[str] | None = None) -> dict[str, Any]:
    state = logical_absolute(state_dir or Path.home() / ".agents" / "agent-memory")
    assert_physical_directory(state, allow_missing=True)
    journal = state / "instruction-sync-recovery.json"
    if _bytes(journal) is not None:
        raise CoreError("instruction_sync_recovery_required", "An interrupted transaction requires reviewed recovery; no targets were overwritten")
    config_path = state / "instruction-sync.json"
    config_before = _bytes(config_path)
    saved = _record(config_path) or {}
    targets = _targets(codex_home, pi_agent_dir, saved)
    bindings = {name: _binding(home) for name, home in targets.items()}
    accepted: dict[str, str] = {}
    for selection in adopt_existing or []:
        host, separator, digest = selection.partition("=")
        if (separator != "=" or host not in targets or host in accepted or bindings[host] is not None
                or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)):
            raise CoreError("instruction_adoption_invalid", "First enrollment requires an exact reviewed host/content hash, not a force override")
        accepted[host] = digest
    source_root = source or saved.get("source_root")
    if source_root is None:
        candidates = {row["source_root"] for row in bindings.values() if row}
        if len(candidates) != 1:
            raise CoreError("instruction_source_binding_missing", "First installation requires one explicitly selected canonical source")
        source_root = candidates.pop()
    root = logical_absolute(source_root)
    _clean(root)
    if _git(root, "branch", "--show-current").decode().strip() != "main":
        raise CoreError("instruction_source_branch", "Canonical source must be on main")
    origin = _origin(root)
    source_identity = _hash(origin.encode())
    if saved and saved.get("source_identity") != source_identity:
        raise CoreError("instruction_source_rebind_required", "Synchronization cannot replace the canonical source identity")
    for row in bindings.values():
        if row:
            bound = logical_absolute(row["source_root"])
            _clean(bound)
            if _origin(bound) != origin:
                raise CoreError("instruction_source_rebind_required", "Host binding belongs to another canonical source")
    # No checkout is pulled. Resolve an isolated exact remote-main snapshot each time.
    with tempfile.TemporaryDirectory(prefix="agent-memory-source-") as directory:
        stage = Path(directory) / "source"
        _git(Path(directory), "-c", "core.autocrlf=false", "clone", "--quiet", "--branch", "main", "--single-branch", "--", origin, str(stage))
        commit = _git(stage, "rev-parse", "HEAD").decode().strip()
        data = _git(stage, "show", f"{commit}:{OWNER_FILE}")
        read_document_bytes(data=data, path=stage / OWNER_FILE, target="global_agents")
        if _bytes(stage / OWNER_FILE) != data:
            raise CoreError("instruction_source_snapshot_drift", "Checkout bytes differ from the committed document")
        if not data:
            raise CoreError("instruction_source_empty", "The published global document is empty")
        # A local unpublished commit must not silently disappear from the publication flow.
        local_commit = _git(root, "rev-parse", "HEAD").decode().strip()
        try:
            _git(stage, "merge-base", "--is-ancestor", local_commit, commit)
        except CoreError as exc:
            raise CoreError("instruction_source_unpublished", "Local source is not an ancestor of published main") from exc
        digest = _hash(data)
        snapshot_root = state / "sources" / source_identity / commit
        before: dict[str, bytes | None] = {}
        rows = []
        for name, home in targets.items():
            assert_physical_directory(home, allow_missing=True)
            target = home / "AGENTS.md"
            if _bytes(home / "AGENTS.override.md") is not None:
                raise CoreError("instruction_target_shadowed", "Host override prevents global instruction qualification", host=name)
            current = _bytes(target)
            before[name] = current
            binding = bindings[name]
            if name in accepted and (current is None or _hash(current) != accepted[name]):
                raise CoreError("instruction_sync_stale_plan", "Reviewed first-enrollment content changed", host=name)
            if (current and current != data and name not in accepted
                    and (binding is None or _hash(current) != binding["target_file_sha256"])):
                raise CoreError("global_instruction_drift", "Local instructions differ from the last deployment; no target changed", host=name)
            rows.append({"host": name, "target": str(target), "before_sha256": _hash(current) if current is not None else None,
                         "action": "noop" if current == data else "update", "binding": binding})
        desired_config = {"contract_version": CONTRACT, "source_identity": source_identity,
                          "source_root": str(snapshot_root), "targets": {key: str(value) for key, value in targets.items()}}
        plan = {"contract_version": CONTRACT, "source_identity": source_identity, "source_commit": commit,
                "content_sha256": digest, "targets": rows, "state_dir": str(state),
                "config_before_sha256": _hash(config_before) if config_before is not None else None,
                "adopt_existing": accepted}
        computed_hash = _hash(_json(plan))
        receipt = {"contract_version": CONTRACT, "source_commit": commit, "content_sha256": digest,
                   "plan_hash": computed_hash, "applied": False,
                   "hosts": [{"host": row["host"], "action": row["action"]} for row in rows],
                   "adoption": "unverified", "other_devices": "unverified"}
        if not apply:
            return {**receipt, "status": "planned"}
        if not plan_hash or plan_hash != computed_hash:
            raise CoreError("instruction_sync_stale_plan", "Preview changed; inspect the fresh plan before applying")
        paths = [config_path, journal, *(home / "AGENTS.md" for home in targets.values()),
                 *(Path(row["source_root"]) / OWNER_FILE for row in bindings.values() if row)]
        repository = InstructionRepository()
        with repository.lock_paths(paths):
            if _bytes(journal) is not None or _bytes(config_path) != config_before:
                raise CoreError("instruction_sync_stale_plan", "Synchronization state changed while waiting for the lock")
            for name, home in targets.items():
                if (_bytes(home / "AGENTS.md") != before[name] or _binding(home) != bindings[name]
                        or _bytes(home / "AGENTS.override.md") is not None):
                    raise CoreError("instruction_sync_stale_plan", "Host changed while waiting for the lock", host=name)
            for row in bindings.values():
                if row:
                    _clean(Path(row["source_root"]))
            _apply(state, snapshot_root, stage, data, targets, before, bindings, desired_config, config_before)
        return {**receipt, "applied": True, "status": "reload_required"}


def _apply(state: Path, snapshot_root: Path, stage: Path, data: bytes, targets: dict[str, Path],
           before: dict[str, bytes | None], bindings: dict[str, Any], config: dict[str, Any], config_before: bytes | None) -> None:
    journal = state / "instruction-sync-recovery.json"
    config_path = state / "instruction-sync.json"
    prepare_store_parent(journal)
    secure_store_location(journal, allow_missing=True)
    digest = _hash(data)
    snapshot_created = False
    if snapshot_root.exists():
        _clean(snapshot_root)
        if (_bytes(snapshot_root / OWNER_FILE) != data or _origin(snapshot_root) != _origin(stage)
                or _git(snapshot_root, "rev-parse", "HEAD").decode().strip() != snapshot_root.name):
            raise CoreError("instruction_source_snapshot_drift", "Managed source snapshot differs from the verified source")
    else:
        prepare_store_parent(snapshot_root / OWNER_FILE)
        # Remove only the empty directory created for the staging destination.
        (snapshot_root / "global").rmdir()
        snapshot_root.rmdir()
        shutil.copytree(stage, snapshot_root)
        snapshot_created = True
    stores_existed = {name: _store(home).exists() for name, home in targets.items()}
    recovery = {"contract_version": CONTRACT, "targets": {name: {
        "home": str(home), "before": base64.b64encode(before[name]).decode() if before[name] is not None else None,
        "binding": bindings[name], "store_existed": stores_existed[name],
    } for name, home in targets.items()}, "config_before": base64.b64encode(config_before).decode() if config_before is not None else None,
        "after_sha256": digest}
    atomic_write(journal, _json(recovery))
    touched: list[str] = []
    try:
        for name, home in targets.items():
            if (_bytes(home / "AGENTS.md") != before[name] or _binding(home) != bindings[name]
                    or _bytes(home / "AGENTS.override.md") is not None):
                raise CoreError("instruction_sync_stale_plan", "Host changed before its write", host=name)
            prepare_store_parent(home / "AGENTS.md")
            touched.append(name)
            if before[name] != data:
                atomic_write(home / "AGENTS.md", data)
            row = {"source_root": str(snapshot_root), "source_commit": snapshot_root.name,
                   "source_file_sha256": digest, "target_file_sha256": digest,
                   "updated_at": datetime.now(UTC).isoformat()}
            previous = bindings[name]
            if previous is None or any(previous[key] != row[key] for key in row if key != "updated_at"):
                _set_binding(home, row)
            if _bytes(home / "AGENTS.md") != data or _binding(home)["target_file_sha256"] != digest:
                raise CoreError("instruction_sync_readback_failed", "Target or binding readback differs", host=name)
        if _bytes(config_path) != _json(config):
            atomic_write(config_path, _json(config))
        if _bytes(config_path) != _json(config):
            raise CoreError("instruction_sync_readback_failed", "Local source binding readback differs")
    except BaseException as failure:
        errors = []
        for name in reversed(touched):
            home = targets[name]
            try:
                if _bytes(home / "AGENTS.md") not in (before[name], data):
                    raise CoreError("instruction_sync_recovery_required", "Concurrent edit retained during rollback", host=name)
                if before[name] is None:
                    (home / "AGENTS.md").unlink(missing_ok=True)
                else:
                    atomic_write(home / "AGENTS.md", before[name])
                if stores_existed[name]:
                    _set_binding(home, bindings[name])
                else:
                    _store(home).unlink(missing_ok=True)
            except Exception:
                errors.append(name)
        try:
            if config_before is None:
                config_path.unlink(missing_ok=True)
            else:
                atomic_write(config_path, config_before)
        except Exception:
            errors.append("source_binding")
        if errors:
            raise CoreError("instruction_sync_recovery_required", "Rollback incomplete; preserve recovery data and inspect affected hosts", hosts=errors) from failure
        journal.unlink()
        if snapshot_created:
            shutil.rmtree(snapshot_root)
        raise
    # Commit already completed. A cleanup failure is not a rollback or an unchanged result.
    try:
        journal.unlink()
    except OSError as exc:
        raise CoreError("instruction_sync_cleanup_required", "Deployment committed; recovery journal cleanup remains", operation_committed=True) from exc
