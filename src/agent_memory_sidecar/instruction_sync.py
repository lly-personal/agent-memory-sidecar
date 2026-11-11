"""On-demand whole-document distribution; no rule discovery or authorization events."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from contextlib import closing, ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .database import CORE_SCHEMA_SHA256, CORE_SCHEMA_VERSION, CoreDatabase, _schema_fingerprint
from .errors import CoreError
from .file_security import logical_absolute, prepare_store_parent, secure_store_location, validate_store_identity, hold_physical_directory
from .installation import InstallationRegistry
from .instructions import InstructionRepository, assert_physical_directory, atomic_write, read_document, read_document_bytes

CONTRACT = "global_instruction_sync_v1"
OWNER_FILE = "global/AGENTS.md"
HOST_ENV = {"codex": "CODEX_HOME", "pi": "PI_CODING_AGENT_DIR", "claude": "CLAUDE_CONFIG_DIR"}
HOST_FILE = {"codex": "AGENTS.md", "pi": "AGENTS.md", "claude": "CLAUDE.md"}
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


def _bytes(path: Path, *, directory_fd: int | None = None) -> bytes | None:
    snapshot = read_document(path=path, target="global_agents", directory_fd=directory_fd)
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


def _set_binding(home: Path, value: dict[str, Any] | None, *, require_existing: bool = False) -> None:
    path = _store(home)
    with CoreDatabase(path, create=not require_existing and not path.exists(), now=datetime.now(UTC).isoformat()) as db:
        with db.transaction():
            db.conn.execute("DELETE FROM global_instruction_binding WHERE singleton=1")
            if value is not None:
                InstallationRegistry(db).bind_global(**{
                    key: value[key] for key in (
                        "source_root", "source_commit", "source_file_sha256", "target_file_sha256", "updated_at"
                    )
                })


def _connection_binding(db: CoreDatabase) -> dict[str, Any] | None:
    row = db.conn.execute("SELECT * FROM global_instruction_binding WHERE singleton=1").fetchone()
    return dict(row) if row else None


def _replace_exit_binding(db: CoreDatabase, expected: dict[str, Any] | None,
                          value: dict[str, Any] | None) -> None:
    with db.transaction():
        if _connection_binding(db) != expected:
            raise CoreError("instruction_sync_stale_plan", "Claude binding changed before removal")
        db.conn.execute("DELETE FROM global_instruction_binding WHERE singleton=1")
        if value is not None:
            InstallationRegistry(db).bind_global(**{key: value[key] for key in (
                "source_root", "source_commit", "source_file_sha256", "target_file_sha256", "updated_at"
            )})


def _distinct_hosts(targets: dict[str, Path]) -> None:
    identities = set()
    for path in targets.values():
        assert_physical_directory(path, allow_missing=True)
        if path.exists():
            value = path.stat()
            identity = (value.st_dev, value.st_ino)
        else:
            identity = os.path.normcase(str(path.resolve()))
        if identity in identities:
            raise CoreError("instruction_target_alias", "Hosts must have distinct physical instruction directories")
        identities.add(identity)


def _targets(codex_home: Path | None, pi_agent_dir: Path | None, claude_home: Path | None,
             saved: dict[str, Any]) -> dict[str, Path]:
    explicit = {name: path for name, path in {"codex": codex_home, "pi": pi_agent_dir, "claude": claude_home}.items() if path is not None}
    targets = {name: logical_absolute(path) for name, path in saved.get("targets", {}).items()}
    if set(targets) - set(HOST_ENV):
        raise CoreError("instruction_sync_state_invalid", "Unknown host binding")
    defaults = {"codex": Path.home() / ".codex", "pi": Path.home() / ".pi" / "agent"}
    for name in HOST_ENV:
        if name == "claude" and name not in explicit and name not in targets:
            continue
        observed = explicit.get(name)
        configured = os.environ.get(HOST_ENV[name])
        if (name == "claude" and observed is not None and configured
                and logical_absolute(observed) != logical_absolute(configured)):
            raise CoreError("instruction_target_rebind_required", "Explicit Claude directory differs from the active host context", host=name)
        if observed is None and configured:
            observed = Path(configured)
        if observed is not None:
            observed = logical_absolute(observed)
            if name in targets and targets[name] != observed:
                raise CoreError("instruction_target_rebind_required", "Existing host directory differs; review the binding before changing it", host=name)
            if name == "claude" and name not in targets and not observed.is_dir():
                raise CoreError("instruction_targets_missing", "Claude enrollment requires an existing observed host directory", host=name)
            targets[name] = observed
        elif name not in targets and not explicit and name in defaults and defaults[name].is_dir():
            targets[name] = logical_absolute(defaults[name])
    if not targets:
        raise CoreError("instruction_targets_missing", "No enrolled or observed host directory")
    _distinct_hosts(targets)
    return targets


def synchronize(*, source: Path | None = None, codex_home: Path | None = None,
                pi_agent_dir: Path | None = None, claude_home: Path | None = None, state_dir: Path | None = None,
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
    targets = _targets(codex_home, pi_agent_dir, claude_home, saved)
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
            target = home / HOST_FILE[name]
            if name != "claude" and _bytes(home / "AGENTS.override.md") is not None:
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
        paths = [config_path, journal, *(home / HOST_FILE[name] for name, home in targets.items()),
                 *(Path(row["source_root"]) / OWNER_FILE for row in bindings.values() if row)]
        repository = InstructionRepository()
        with repository.lock_paths(paths):
            if _bytes(journal) is not None or _bytes(config_path) != config_before:
                raise CoreError("instruction_sync_stale_plan", "Synchronization state changed while waiting for the lock")
            for name, home in targets.items():
                if (_bytes(home / HOST_FILE[name]) != before[name] or _binding(home) != bindings[name]
                        or (name != "claude" and _bytes(home / "AGENTS.override.md") is not None)):
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
            target = home / HOST_FILE[name]
            if (_bytes(target) != before[name] or _binding(home) != bindings[name]
                    or (name != "claude" and _bytes(home / "AGENTS.override.md") is not None)):
                raise CoreError("instruction_sync_stale_plan", "Host changed before its write", host=name)
            prepare_store_parent(target)
            touched.append(name)
            if before[name] != data:
                atomic_write(target, data)
            row = {"source_root": str(snapshot_root), "source_commit": snapshot_root.name,
                   "source_file_sha256": digest, "target_file_sha256": digest,
                   "updated_at": datetime.now(UTC).isoformat()}
            previous = bindings[name]
            if previous is None or any(previous[key] != row[key] for key in row if key != "updated_at"):
                _set_binding(home, row)
            if _bytes(target) != data or _binding(home)["target_file_sha256"] != digest:
                raise CoreError("instruction_sync_readback_failed", "Target or binding readback differs", host=name)
        if _bytes(config_path) != _json(config):
            atomic_write(config_path, _json(config))
        if _bytes(config_path) != _json(config):
            raise CoreError("instruction_sync_readback_failed", "Local source binding readback differs")
    except BaseException as failure:
        errors = []
        for name in reversed(touched):
            home = targets[name]
            target = home / HOST_FILE[name]
            try:
                if _bytes(target) not in (before[name], data):
                    raise CoreError("instruction_sync_recovery_required", "Concurrent edit retained during rollback", host=name)
                if before[name] is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_write(target, before[name])
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


def unenroll_claude(*, claude_home: Path | None = None, state_dir: Path | None = None,
                   apply: bool = False, plan_hash: str | None = None) -> dict[str, Any]:
    """Remove only an exact managed Claude projection before an older-runtime downgrade."""
    state = logical_absolute(state_dir or Path.home() / ".agents" / "agent-memory")
    assert_physical_directory(state, allow_missing=True)
    journal, config_path = state / "instruction-sync-recovery.json", state / "instruction-sync.json"
    if _bytes(journal) is not None:
        raise CoreError("instruction_sync_recovery_required", "An interrupted transaction requires reviewed recovery")
    config_before = _bytes(config_path)
    saved = _record(config_path) or {}
    targets = saved.get("targets", {})
    if not isinstance(targets, dict) or set(targets) - set(HOST_ENV):
        raise CoreError("instruction_sync_state_invalid", "Unknown host binding")
    if "claude" not in targets:
        raise CoreError("instruction_host_not_enrolled", "Claude is not enrolled; no files were removed")
    home = logical_absolute(targets["claude"])
    _distinct_hosts({name: logical_absolute(path) for name, path in targets.items()})
    for observed in (claude_home, os.environ.get(HOST_ENV["claude"])):
        if observed and logical_absolute(observed) != home:
            raise CoreError("instruction_target_rebind_required", "Claude directory differs from the saved enrollment", host="claude")
    assert_physical_directory(home)
    target = home / HOST_FILE["claude"]
    before, binding = _bytes(target), _binding(home)
    if (binding is None or not saved.get("source_root")
            or logical_absolute(binding["source_root"]) != logical_absolute(saved["source_root"])
            or binding["source_file_sha256"] != binding["target_file_sha256"]):
        raise CoreError("instruction_binding_unavailable", "Claude enrollment and source binding do not match")
    if before is None or _hash(before) != binding["target_file_sha256"]:
        raise CoreError("global_instruction_drift", "Claude instructions differ from their bound deployment; nothing was removed", host="claude")
    store_stat = _store(home).stat()
    target_stat = target.lstat()
    config_after = _json({**saved, "targets": {name: path for name, path in targets.items() if name != "claude"}})
    plan = {"contract_version": "global_instruction_unenroll_v1", "host": "claude", "home": str(home),
            "config_before_sha256": _hash(config_before), "before_sha256": _hash(before), "binding": binding,
            "store_identity": [store_stat.st_dev, store_stat.st_ino],
            "target_identity": [target_stat.st_dev, target_stat.st_ino]}
    computed_hash = _hash(_json(plan))
    receipt = {"contract_version": plan["contract_version"], "host": "claude", "plan_hash": computed_hash,
               "remaining_hosts": sorted(set(targets) - {"claude"}), "applied": False, "adoption": "unverified"}
    if not apply:
        return {**receipt, "status": "planned"}
    if not plan_hash or plan_hash != computed_hash:
        raise CoreError("instruction_sync_stale_plan", "Exit preview changed; inspect a fresh plan before applying")
    def relative(fd: int | None, path: Path) -> str:
        return path.name if fd is not None else str(path)

    def entry(fd: int | None, path: Path):
        try:
            return os.stat(relative(fd, path), dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return None

    with InstructionRepository().lock_paths([config_path, journal, target]):
        if (_bytes(journal) is not None or _bytes(config_path) != config_before
                or _bytes(target) != before or _binding(home) != binding
                or not os.path.samestat(store_stat, _store(home).stat())):
            raise CoreError("instruction_sync_stale_plan", "Claude enrollment changed while waiting for the lock")
        prepare_store_parent(journal)
        secure_store_location(journal, allow_missing=True)
        with hold_physical_directory(home) as home_fd, hold_physical_directory(state) as state_fd, CoreDatabase(_store(home)) as db:
            def selected_state_exists() -> bool:
                try:
                    return state_fd is None or os.path.samestat(os.fstat(state_fd), state.stat())
                except OSError:
                    return False

            if not os.path.samestat(store_stat, _store(home).stat()) or _connection_binding(db) != binding:
                raise CoreError("instruction_sync_stale_plan", "Claude Store changed while opening")
            if _bytes(config_path, directory_fd=state_fd) != config_before or _bytes(journal, directory_fd=state_fd) is not None:
                raise CoreError("instruction_sync_stale_plan", "State changed while opening")
            stage = home / (".agent-memory-exit-" + uuid.uuid4().hex)
            os.mkdir(relative(home_fd, stage), mode=0o700, dir_fd=home_fd)
            captured = stage / "instruction"
            capture_pending = stage_cleanup_started = False
            try:
                secure_store_location(captured, allow_missing=True)
                with ExitStack() as handles:
                    if home_fd is not None:
                        stage_fd = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
                        handles.callback(os.close, stage_fd)
                    else:
                        stage_fd = handles.enter_context(hold_physical_directory(stage))
                    recovery = {"contract_version": plan["contract_version"], "targets": {"claude": {
                        "home": str(home), "before": base64.b64encode(before).decode(), "binding": binding,
                        "store_existed": True, "capture_directory": str(stage)}},
                        "config_before": base64.b64encode(config_before).decode(), "after_sha256": None}
                    atomic_write(journal, _json(recovery), directory_fd=state_fd)
                    verified = binding_started = config_started = False

                    def approved_capture() -> bool:
                        value = entry(stage_fd, captured)
                        if (value is None or not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
                                or not os.path.samestat(target_stat, value)):
                            return False
                        descriptor = os.open(relative(stage_fd, captured), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=stage_fd)
                        with os.fdopen(descriptor, "rb") as stream:
                            return os.path.samestat(target_stat, os.fstat(stream.fileno())) and stream.read(len(before) + 1) == before

                    try:
                        os.replace(relative(home_fd, target), relative(stage_fd, captured),
                                   src_dir_fd=home_fd, dst_dir_fd=stage_fd)
                        capture_pending = True
                        verified = approved_capture()
                        if not verified:
                            raise CoreError("instruction_sync_recovery_required", "A changed instruction was captured and retained", capture_directory=str(stage))
                        if not os.path.samestat(store_stat, _store(home).stat()):
                            raise CoreError("instruction_sync_stale_plan", "Claude binding changed before removal")
                        _replace_exit_binding(db, binding, None)
                        binding_started = True
                        if _bytes(config_path, directory_fd=state_fd) != config_before:
                            raise CoreError("instruction_sync_stale_plan", "Enrollment changed before removal")
                        config_started = True
                        atomic_write(config_path, config_after, directory_fd=state_fd)
                        if (entry(home_fd, target) is not None or _connection_binding(db) is not None or _bytes(config_path, directory_fd=state_fd) != config_after
                                or not os.path.samestat(store_stat, _store(home).stat())):
                            raise CoreError("instruction_sync_readback_failed", "Claude exit readback differs")
                        if not selected_state_exists():
                            raise CoreError("instruction_sync_stale_plan", "Selected state directory moved; recovery retained")
                    except BaseException as failure:
                        errors = []
                        try:
                            current = _bytes(config_path, directory_fd=state_fd)
                            if config_started and current == config_after:
                                atomic_write(config_path, config_before, directory_fd=state_fd)
                            elif current != config_before:
                                errors.append("source_binding")
                        except Exception:
                            errors.append("source_binding")
                        try:
                            if not os.path.samestat(store_stat, _store(home).stat()):
                                raise CoreError("instruction_binding_unavailable", "Claude Store was replaced")
                            current_binding = _connection_binding(db)
                            if binding_started and current_binding is None:
                                _replace_exit_binding(db, None, binding)
                            elif current_binding != binding:
                                errors.append("claude_binding")
                        except Exception:
                            errors.append("claude_binding")
                        try:
                            moved = entry(stage_fd, captured)
                            if moved is not None:
                                if not verified or not approved_capture():
                                    raise CoreError("instruction_sync_recovery_required", "Changed capture retained")
                                # A hard link restores without overwriting a recreated user file.
                                os.link(relative(stage_fd, captured), relative(home_fd, target),
                                        src_dir_fd=stage_fd, dst_dir_fd=home_fd, follow_symlinks=False)
                                os.unlink(relative(stage_fd, captured), dir_fd=stage_fd)
                                capture_pending = False
                            elif entry(home_fd, target) is None:
                                errors.append("claude_file")
                        except Exception:
                            errors.append("claude_file")
                        if errors:
                            raise CoreError("instruction_sync_recovery_required", "Exit recovery material retained", hosts=errors,
                                            capture_directory=str(stage)) from failure
                        if not selected_state_exists():
                            raise CoreError("instruction_sync_recovery_required", "Selected state directory moved; inspect retained journal") from failure
                        try:
                            os.unlink(relative(state_fd, journal), dir_fd=state_fd)
                        except OSError as exc:
                            raise CoreError("instruction_sync_recovery_required", "Exit rolled back; journal cleanup remains", operation_committed=False) from exc
                        raise
                    # Enrollment removal is committed. Capture or journal cleanup cannot roll it back.
                    try:
                        if not approved_capture():
                            raise OSError("instruction capture changed after commit")
                        os.unlink(relative(stage_fd, captured), dir_fd=stage_fd)
                        capture_pending = False
                    except OSError as exc:
                        raise CoreError("instruction_sync_cleanup_required", "Claude exit committed; capture retained", operation_committed=True,
                                        capture_directory=str(stage)) from exc
                stage_cleanup_started = True
                os.rmdir(relative(home_fd, stage), dir_fd=home_fd)
            except BaseException as failure:
                # Only an empty, owned stage may be reclaimed after a failed operation.
                if not capture_pending and not stage_cleanup_started:
                    try:
                        os.rmdir(relative(home_fd, stage), dir_fd=home_fd)
                    except OSError as exc:
                        raise CoreError("instruction_sync_recovery_required", "Owned stage cleanup remains", capture_directory=str(stage)) from exc
                if _bytes(config_path, directory_fd=state_fd) == config_after and _connection_binding(db) is None and not isinstance(failure, CoreError):
                    raise CoreError("instruction_sync_cleanup_required", "Claude exit committed; stage cleanup remains", operation_committed=True,
                                    capture_directory=str(stage)) from failure
                raise
            try:
                os.unlink(relative(state_fd, journal), dir_fd=state_fd)
            except OSError as exc:
                raise CoreError("instruction_sync_cleanup_required", "Claude exit committed; journal cleanup remains", operation_committed=True) from exc
    return {**receipt, "status": "unenrolled", "applied": True}
