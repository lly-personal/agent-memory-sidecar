#!/usr/bin/env python3
"""Managed source synchronization, tree hashing, and atomic cutover for Bootstrap."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import sys
from typing import Any, Callable
import uuid

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from bootstrap_contracts import (
    BOOTSTRAP_VERSION,
    SHA40,
    SHA64,
    SOURCE_CUTOVER_PLAN_VERSION,
    SOURCE_CUTOVER_RECEIPT_VERSION,
    STREAM_CHUNK_BYTES,
    SourceSpec,
    _load_json_file,
    _validate_host_materialization,
    _validate_source_sync,
    canonical,
    exact,
    normalize_remote,
    object_hash,
    require,
    validate_source_cutover_plan,
)
from bootstrap_security import (
    BootstrapError,
    ensure_physical_directory,
    is_reparse,
    read_global_instruction_binding,
    run_git,
    validate_physical_directory_chain,
)


def _is_reparse(value: os.stat_result) -> bool:
    return is_reparse(value)


def _physical_directory(path: Path, *, create: bool) -> Path:
    return ensure_physical_directory(
        path,
        create=create,
        error_code="managed_directory_alias_forbidden",
        error_cls=BootstrapError,
    )


def _codex_home_root(codex_home: Path, *, create: bool) -> Path:
    root = ensure_physical_directory(
        codex_home,
        create=create,
        error_code="codex_home_invalid",
        error_cls=BootstrapError,
    )
    require(root.is_dir(), "codex_home_invalid")
    return root.resolve()


def _agent_memory_root(codex_home: Path, *, create: bool) -> Path:
    return _physical_directory(
        _codex_home_root(codex_home, create=create) / "agent-memory",
        create=create,
    )


def _managed_source_root(codex_home: Path, *, create: bool) -> Path:
    agent_root = _agent_memory_root(codex_home, create=create)
    if not agent_root.exists():
        return agent_root / "sources"
    return _physical_directory(agent_root / "sources", create=create)


def _installed_skill_root(codex_home: Path, *, create: bool) -> Path:
    return _physical_directory(
        _codex_home_root(codex_home, create=create) / "skills",
        create=create,
    )


def ensure_managed_child(root: Path, child: Path) -> None:
    root = root.resolve()
    resolved = child.resolve()
    require(resolved.parent == root, "managed source target escaped its root")


def safe_remove(root: Path, path: Path) -> None:
    if not path.exists():
        return
    ensure_managed_child(root, path)
    require(path.name.startswith("."), "only staged managed paths may be removed")
    if path.is_dir() and not path.is_symlink():
        def remove_readonly(function: Any, target: str, _: Any) -> None:
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(path, onerror=remove_readonly)
    else:
        path.unlink()


def inspect_checkout(path: Path, spec: SourceSpec) -> str:
    state = inspect_existing_checkout(path)
    actual_remote = run_git(["remote", "get-url", "origin"], cwd=path)
    require(normalize_remote(actual_remote) == normalize_remote(spec.remote), "managed_source_identity_mismatch")
    commit = state["commit"]
    require(
        spec.expected_commit is None or commit == spec.expected_commit,
        "managed_source_commit_mismatch",
    )
    return commit


def inspect_existing_checkout(path: Path) -> dict[str, str]:
    """Read a managed checkout without asserting its desired authority identity."""
    value = path.lstat()
    require(
        stat.S_ISDIR(value.st_mode) and not stat.S_ISLNK(value.st_mode) and not _is_reparse(value),
        "managed_source_invalid",
    )
    validate_physical_directory_chain(path, allow_missing_tail=False, error_code="managed_source_invalid")
    git_root = path / ".git"
    git_value = git_root.lstat()
    require(
        stat.S_ISDIR(git_value.st_mode)
        and not stat.S_ISLNK(git_value.st_mode)
        and not _is_reparse(git_value),
        "managed_source_not_git",
    )
    remote = normalize_remote(run_git(["remote", "get-url", "origin"], cwd=path))
    require(run_git(["status", "--porcelain"], cwd=path) == "", "managed_source_dirty")
    commit = run_git(["rev-parse", "HEAD"], cwd=path).lower()
    require(SHA40.fullmatch(commit) is not None, "managed_source_commit_invalid")
    return {
        "remote_sha256": hashlib.sha256(remote.encode("utf-8")).hexdigest(),
        "commit": commit,
    }


def source_identity(spec: SourceSpec) -> dict[str, str]:
    require(spec.expected_commit is not None, "source_cutover_commit_required")
    return {
        "remote_sha256": hashlib.sha256(normalize_remote(spec.remote).encode("utf-8")).hexdigest(),
        "ref": spec.ref,
        "commit": spec.expected_commit,
    }


def inspect_marketplace_checkout(path: Path) -> dict[str, str | None]:
    """Inspect a clean Codex-owned marketplace snapshot and optional legacy metadata."""
    value = path.lstat()
    require(
        stat.S_ISDIR(value.st_mode) and not stat.S_ISLNK(value.st_mode) and not _is_reparse(value),
        "marketplace_root_invalid",
    )
    validate_physical_directory_chain(path, allow_missing_tail=False, error_code="marketplace_root_invalid")
    git_root = path / ".git"
    git_value = git_root.lstat()
    require(
        stat.S_ISDIR(git_value.st_mode)
        and not stat.S_ISLNK(git_value.st_mode)
        and not _is_reparse(git_value),
        "marketplace_git_invalid",
    )
    require(
        run_git(["status", "--porcelain", "--untracked-files=no"], cwd=path) == "",
        "marketplace_tracked_tree_dirty",
    )
    untracked = set(filter(None, run_git(["ls-files", "--others", "--exclude-standard"], cwd=path).splitlines()))
    require(
        untracked in (set(), {".codex-marketplace-install.json"}),
        "marketplace_untracked_state_invalid",
    )
    commit = run_git(["rev-parse", "HEAD"], cwd=path).casefold()
    require(SHA40.fullmatch(commit) is not None, "marketplace_commit_invalid")
    actual_remote = run_git(["remote", "get-url", "origin"], cwd=path)
    metadata_ref: str | None = None
    if untracked:
        metadata = _load_json_file(
            path / ".codex-marketplace-install.json", "marketplace_install_metadata_unreadable",
        )
        exact(
            metadata,
            {"source_type", "source", "ref_name", "sparse_paths", "revision"},
            "$.marketplace_install_metadata",
        )
        require(
            metadata["source_type"] == "git"
            and isinstance(metadata["source"], str)
            and isinstance(metadata["ref_name"], str)
            and isinstance(metadata["sparse_paths"], list)
            and metadata["revision"] == commit,
            "marketplace_install_metadata_invalid",
        )
        require(
            normalize_remote(actual_remote) == normalize_remote(str(metadata["source"])),
            "marketplace_install_source_mismatch",
        )
        metadata_ref = str(metadata["ref_name"])
    return {
        "remote_sha256": hashlib.sha256(normalize_remote(actual_remote).encode("utf-8")).hexdigest(),
        "metadata_ref": metadata_ref,
        "commit": commit,
    }


def _existing_global_binding(codex_home: Path) -> dict[str, str] | None:
    return read_global_instruction_binding(
        codex_home,
        strict_commit=True,
        error_code="source_cutover_owner_state_ambiguous",
        error_cls=BootstrapError,
    )


def _current_owner_root(codex_home: Path) -> Path:
    binding = _existing_global_binding(codex_home)
    if binding is not None:
        bound = Path(binding["source_root"])
        if len(bound.parents) >= 3 and bound.parent.parent.name == "sources":
            return bound
    return _managed_source_root(codex_home, create=False) / "canonical_owner"


def _preserved_owner_identity(
    codex_home: Path,
    current_owner: dict[str, str] | None,
) -> dict[str, str] | None:
    binding = _existing_global_binding(codex_home)
    if current_owner is None and binding is None:
        return None
    require(binding is not None, "source_cutover_owner_state_ambiguous")
    # A multi-host instruction sync owns a verified source snapshot outside the
    # legacy Codex source slot. Import its identity, never its runtime state.
    bound = Path(binding["source_root"])
    if len(bound.parents) >= 3 and bound.parent.parent.name == "sources":
        metadata = bound.parents[2] / "instruction-sync.json"
        if metadata.is_file():
            value = metadata.lstat()
            require(
                stat.S_ISREG(value.st_mode) and not stat.S_ISLNK(value.st_mode)
                and not _is_reparse(value) and value.st_nlink == 1,
                "source_cutover_owner_state_ambiguous",
            )
            saved = _load_json_file(metadata, "source_cutover_owner_state_ambiguous")
            require(
                saved.get("contract_version") == "global_instruction_sync_v1"
                and saved.get("source_root") == str(bound)
                and os.path.normcase(str(Path(saved.get("targets", {}).get("codex", "")).resolve()))
                == os.path.normcase(str(codex_home.resolve())),
                "source_cutover_owner_state_ambiguous",
            )
            raw_remote = run_git(["remote", "get-url", "origin"], cwd=bound).strip()
            require(
                saved.get("source_identity") == bound.parent.name
                == hashlib.sha256(raw_remote.encode("utf-8")).hexdigest(),
                "source_cutover_owner_state_ambiguous",
            )
            observed = inspect_existing_checkout(bound)
            require(
                observed["commit"] == binding["source_commit"] == bound.name,
                "source_cutover_owner_state_ambiguous",
            )
            require(
                current_owner is None or current_owner["remote_sha256"] == observed["remote_sha256"],
                "source_cutover_owner_state_ambiguous",
            )
            return {**observed, "ref": "preserved"}
    require(current_owner is not None, "source_cutover_owner_state_ambiguous")
    owner_root = _managed_source_root(codex_home, create=False) / "canonical_owner"
    try:
        bound_root = Path(binding["source_root"]).expanduser().resolve()
        expected_root = owner_root.resolve()
    except OSError as exc:
        raise BootstrapError("source_cutover_owner_state_ambiguous") from exc
    require(
        os.path.normcase(str(bound_root)) == os.path.normcase(str(expected_root))
        and binding["source_commit"] == current_owner["commit"],
        "source_cutover_owner_state_ambiguous",
    )
    return {**current_owner, "ref": "preserved"}


def verify_remote_ref(spec: SourceSpec) -> None:
    require(spec.expected_commit is not None, "source_cutover_commit_required")
    output = run_git([
        "ls-remote", "--", spec.remote,
        spec.ref,
        f"refs/heads/{spec.ref}",
        f"refs/tags/{spec.ref}",
        f"refs/tags/{spec.ref}^{{}}",
    ])
    commits = {
        line.split("\t", 1)[0].casefold()
        for line in output.splitlines()
        if "\t" in line and SHA40.fullmatch(line.split("\t", 1)[0].casefold()) is not None
    }
    require(spec.expected_commit in commits, f"source_cutover_{spec.name}_ref_mismatch")


def _source_cutover_state(codex_home: Path, specs: tuple[SourceSpec, ...]) -> dict[str, Any]:
    root = _managed_source_root(codex_home, create=False)
    by_name = {spec.name: spec for spec in specs}
    require(set(by_name).issubset({"sidecar", "canonical_owner"}), "managed_source_name_invalid")
    require("sidecar" in by_name and len(by_name) == len(specs), "managed_source_name_invalid")
    for spec in specs:
        verify_remote_ref(spec)

    current: dict[str, Any] = {}
    desired: dict[str, Any] = {}
    changes: list[str] = []
    for name in ("sidecar", "canonical_owner"):
        target = (
            _current_owner_root(codex_home)
            if name == "canonical_owner" and name not in by_name else root / name
        )
        try:
            current[name] = inspect_existing_checkout(target) if target.exists() else None
        except BootstrapError as exc:
            if name == "canonical_owner" and name not in by_name:
                raise BootstrapError("source_cutover_owner_state_ambiguous") from exc
            raise
    desired["sidecar"] = source_identity(by_name["sidecar"])
    if "canonical_owner" in by_name:
        desired["canonical_owner"] = source_identity(by_name["canonical_owner"])
        owner_action = "keep_owner"
    else:
        desired["canonical_owner"] = _preserved_owner_identity(
            codex_home, current["canonical_owner"],
        )
        owner_action = "keep_owner" if desired["canonical_owner"] is not None else "public_core"

    for name in ("sidecar", "canonical_owner"):
        current_comparable = current[name]
        desired_comparable = desired[name]
        if current_comparable is not None:
            current_comparable = {
                **current_comparable,
                "ref": desired_comparable["ref"] if desired_comparable is not None else "",
            }
        if current_comparable != desired_comparable:
            action = "remove" if desired[name] is None else ("install" if current[name] is None else "replace")
            changes.append(f"{name}:{action}")

    return {
        "current": current,
        "desired": desired,
        "owner_action": owner_action,
        "changes": changes,
    }


def plan_source_cutover(codex_home: Path, specs: tuple[SourceSpec, ...]) -> dict[str, Any]:
    state = _source_cutover_state(codex_home, specs)
    plan = {
        "contract_version": SOURCE_CUTOVER_PLAN_VERSION,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "status": "ready" if state["changes"] else "noop",
        "owner_action": state["owner_action"],
        "current": state["current"],
        "desired": state["desired"],
        "changes": state["changes"],
        "plan_hash": "",
    }
    plan["plan_hash"] = object_hash(plan, "plan_hash")
    return plan


def render_source_cutover_plan(value: Any) -> str:
    plan = validate_source_cutover_plan(value)
    sidecar_change = next(
        (item.split(":", 1)[1] for item in plan["changes"] if item.startswith("sidecar:")),
        "unchanged",
    )
    sidecar_labels = {
        "install": "首次安装公开 Sidecar",
        "replace": "将现有 Sidecar 切换到已验证的公开发行来源",
        "unchanged": "Sidecar 来源身份不变，仅重新验证并修复主机物化",
    }
    owner_change = next(
        (item.split(":", 1)[1] for item in plan["changes"] if item.startswith("canonical_owner:")),
        "unchanged",
    )
    if owner_change == "install":
        owner_label = "绑定显式提供且已验证的私有 Owner"
    elif owner_change == "replace":
        owner_label = "切换到显式提供且已验证的私有 Owner"
    elif plan["owner_action"] == "keep_owner":
        owner_label = "保持本机已精确绑定的私有 Owner，不修改或公开其内容"
    else:
        owner_label = "使用 public Core；本机不存在待解绑 Owner"
    replaces_existing_source = any(item.endswith(":replace") for item in plan["changes"])
    confirmation = (
        "请回复“确认更新”后执行一次原子切换；任一步失败会恢复原状态。"
        if replaces_existing_source
        else "当前部署请求已覆盖该动作，将直接执行并在失败时恢复原状态。"
    )
    return "\n".join([
        "## 本机 Agent Memory 调和计划",
        "",
        f"- Sidecar：{sidecar_labels[sidecar_change]}",
        f"- Owner：{owner_label}",
        f"- 执行：{confirmation}",
    ]) + "\n"


def _snapshot_skill_targets(codex_home: Path) -> list[tuple[Path, Path | None]]:
    root = _installed_skill_root(codex_home, create=True)
    snapshots: list[tuple[Path, Path | None]] = []
    try:
        for name in ("agent-memory-workstation-bootstrap", "global-owner-scout"):
            target = root / name
            backup: Path | None = None
            if target.exists() or target.is_symlink():
                _validate_physical_skill_tree(target)
                backup = root / f".{name}.cutover-{uuid.uuid4().hex}"
                shutil.copytree(target, backup, symlinks=True)
                _validate_physical_skill_tree(backup)
            snapshots.append((target, backup))
        return snapshots
    except Exception:
        _restore_skill_targets(root, snapshots)
        raise


def _validate_physical_skill_tree(root: Path) -> None:
    root_value = root.lstat()
    require(
        stat.S_ISDIR(root_value.st_mode)
        and not stat.S_ISLNK(root_value.st_mode)
        and not _is_reparse(root_value),
        "installed_skill_target_invalid",
    )

    def failed(exc: OSError) -> None:
        raise BootstrapError("installed_skill_target_invalid") from exc

    for current_raw, directory_names, file_names in os.walk(
        root, topdown=True, onerror=failed, followlinks=False,
    ):
        current = Path(current_raw)
        for name in directory_names:
            value = (current / name).lstat()
            require(
                stat.S_ISDIR(value.st_mode)
                and not stat.S_ISLNK(value.st_mode)
                and not _is_reparse(value),
                "installed_skill_target_invalid",
            )
        for name in file_names:
            value = (current / name).lstat()
            require(
                stat.S_ISREG(value.st_mode)
                and not stat.S_ISLNK(value.st_mode)
                and not _is_reparse(value)
                and value.st_nlink == 1,
                "installed_skill_target_invalid",
            )


def physical_tree_hash(
    root: Path,
    *,
    excluded_relatives: set[str] | None = None,
) -> str:
    """Hash one physical portable component without caches or Git metadata."""
    excluded = set() if excluded_relatives is None else set(excluded_relatives)
    _validate_physical_skill_tree(root)
    files: list[Path] = []
    for current_raw, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names if name not in {".git", "__pycache__"}
        )
        current = Path(current_raw)
        for name in sorted(file_names):
            item = current / name
            relative = item.relative_to(root).as_posix()
            if relative in excluded or item.suffix.casefold() in {".pyc", ".pyo"}:
                continue
            files.append(item)
    require(files, "component_tree_empty")
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda candidate: candidate.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def bounded_physical_tree_hash(root: Path, *, max_entries: int, max_bytes: int) -> str:
    """Hash an untrusted project Skill with bounded traversal and streaming reads."""
    root_state = root.lstat()
    require(
        stat.S_ISDIR(root_state.st_mode) and not stat.S_ISLNK(root_state.st_mode) and not _is_reparse(root_state),
        "component_root_invalid",
    )
    files: list[Path] = []
    pending = [root]
    entry_count = 0
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise BootstrapError("component_tree_unreadable") from exc
        for entry in entries:
            entry_count += 1
            require(entry_count <= max_entries, "component_tree_entry_budget_exceeded")
            value = os.stat(entry.path, follow_symlinks=False)
            require(not entry.is_symlink() and not _is_reparse(value), "component_tree_alias_forbidden")
            if stat.S_ISDIR(value.st_mode):
                if entry.name not in {".git", "__pycache__"}:
                    pending.append(Path(entry.path))
            elif stat.S_ISREG(value.st_mode) and value.st_nlink == 1:
                item = Path(entry.path)
                if item.suffix.casefold() not in {".pyc", ".pyo"}:
                    files.append(item)
            else:
                raise BootstrapError("component_tree_entry_invalid")
    require(files, "component_tree_empty")
    digest = hashlib.sha256()
    total_bytes = 0
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    binary = getattr(os, "O_BINARY", 0)
    for item in sorted(files, key=lambda candidate: candidate.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        descriptor = os.open(item, os.O_RDONLY | nofollow | binary)
        try:
            opened = os.fstat(descriptor)
            require(
                stat.S_ISREG(opened.st_mode) and not _is_reparse(opened) and opened.st_nlink == 1,
                "component_tree_entry_invalid",
            )
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                while True:
                    chunk = handle.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    require(total_bytes <= max_bytes, "component_tree_byte_budget_exceeded")
                    digest.update(chunk)
        finally:
            os.close(descriptor)
        digest.update(b"\0")
    ending_root = root.lstat()
    require(
        stat.S_ISDIR(ending_root.st_mode)
        and not stat.S_ISLNK(ending_root.st_mode)
        and not _is_reparse(ending_root)
        and (ending_root.st_dev, ending_root.st_ino) == (root_state.st_dev, root_state.st_ino),
        "component_root_changed_during_read",
    )
    return digest.hexdigest()


def _restore_skill_targets(root: Path, snapshots: list[tuple[Path, Path | None]]) -> None:
    for target, backup in reversed(snapshots):
        if target.exists() or target.is_symlink():
            failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
            os.replace(target, failed)
            safe_remove(root, failed)
        if backup is not None and backup.exists():
            os.replace(backup, target)


def _discard_skill_snapshots(root: Path, snapshots: list[tuple[Path, Path | None]]) -> None:
    for _, backup in snapshots:
        if backup is not None and backup.exists():
            safe_remove(root, backup)


def _write_cutover_receipt(codex_home: Path, receipt: dict[str, Any]) -> Path:
    root = _agent_memory_root(codex_home, create=True)
    path = root / "source-cutover-receipt.json"
    _validate_cutover_receipt_target(path)
    staged = root / f".source-cutover-receipt-{uuid.uuid4().hex}"
    try:
        staged.write_bytes(canonical(receipt) + b"\n")
        os.replace(staged, path)
        return path
    finally:
        if staged.exists():
            staged.unlink()


def _validate_cutover_receipt_target(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    value = path.lstat()
    require(
        stat.S_ISREG(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and not _is_reparse(value)
        and value.st_nlink == 1,
        "source_cutover_receipt_target_invalid",
    )


def _preflight_cutover_receipt(codex_home: Path) -> None:
    """Prove the receipt directory supports the atomic commit primitive before mutation."""
    root = _agent_memory_root(codex_home, create=True)
    path = root / "source-cutover-receipt.json"
    _validate_cutover_receipt_target(path)
    staged = root / f".source-cutover-receipt-preflight-{uuid.uuid4().hex}"
    committed = root / f".source-cutover-receipt-preflighted-{uuid.uuid4().hex}"
    try:
        with staged.open("xb") as stream:
            stream.write(b"{}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, committed)
    except OSError as exc:
        raise BootstrapError("source_cutover_receipt_preflight_failed") from exc
    finally:
        for candidate in (staged, committed):
            if candidate.exists():
                candidate.unlink()


def apply_source_cutover(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    plan_hash: str,
    materialize_host_fn: Callable[..., dict[str, Any]] | None = None,
    external_apply: Callable[[], None] | None = None,
    external_rollback: Callable[[], None] | None = None,
    precommit_verify: Callable[[dict[str, Any]], None] | None = None,
    facade: Any = None,
) -> dict[str, Any]:
    require(SHA64.fullmatch(plan_hash.casefold()) is not None, "source_cutover_plan_hash_invalid")
    plan = plan_source_cutover(codex_home, specs)
    require(plan["plan_hash"] == plan_hash.casefold(), "source_cutover_plan_stale")
    require(plan["status"] in {"ready", "noop"}, "source_cutover_plan_invalid")
    _preflight_cutover_receipt(codex_home)
    root = _managed_source_root(codex_home, create=True)
    by_name = {spec.name: spec for spec in specs}
    prepared: dict[str, tuple[SourceSpec, Path, str]] = {}
    swapped: list[tuple[Path, Path | None]] = []
    skill_snapshots: list[tuple[Path, Path | None]] = []
    receipts: dict[str, Any] = {}
    external_started = False
    committed = False
    materialize_cb = (
        getattr(facade, "materialize_host")
        if facade is not None and hasattr(facade, "materialize_host")
        else materialize_host_fn
    )
    if materialize_cb is None:
        from workstation_observer import materialize_host as materialize_cb  # lazy break of mutual dep
    discard_cb = (
        getattr(facade, "_discard_skill_snapshots")
        if facade is not None and hasattr(facade, "_discard_skill_snapshots")
        else _discard_skill_snapshots
    )
    try:
        for name in ("sidecar", "canonical_owner"):
            spec = by_name.get(name)
            if spec is None:
                continue
            target = root / name
            desired = source_identity(spec)
            current = inspect_existing_checkout(target) if target.exists() else None
            if current == {"remote_sha256": desired["remote_sha256"], "commit": desired["commit"]}:
                receipts[name] = {"status": "unchanged", "ref": spec.ref, "commit": desired["commit"]}
                continue
            staged = root / f".{name}.stage-{uuid.uuid4().hex}"
            run_git([
                "clone", "--quiet", "--depth", "1", "--single-branch",
                "--branch", spec.ref, "--", spec.remote, str(staged),
            ])
            commit = inspect_checkout(staged, spec)
            prepared[name] = (spec, staged, commit)

        for name, (spec, staged, commit) in prepared.items():
            target = root / name
            rollback: Path | None = None
            if target.exists():
                require(
                    inspect_existing_checkout(target) == plan["current"][name],
                    "source_cutover_plan_stale",
                )
                rollback = root / f".{name}.rollback-{uuid.uuid4().hex}"
                os.replace(target, rollback)
            else:
                require(plan["current"][name] is None, "source_cutover_plan_stale")
            swapped.append((target, rollback))
            os.replace(staged, target)
            require(inspect_checkout(target, spec) == commit, "managed_source_post_swap_mismatch")
            receipts[name] = {"status": "synced", "ref": spec.ref, "commit": commit}

        for name in ("sidecar", "canonical_owner"):
            if name in prepared:
                continue
            target = (
                _current_owner_root(codex_home)
                if name == "canonical_owner" and name not in by_name else root / name
            )
            current = inspect_existing_checkout(target) if target.exists() else None
            require(current == plan["current"][name], "source_cutover_plan_stale")

        if plan["owner_action"] == "keep_owner" and "canonical_owner" not in by_name:
            preserved = _preserved_owner_identity(codex_home, plan["current"]["canonical_owner"])
            require(preserved == plan["desired"]["canonical_owner"], "source_cutover_plan_stale")
            receipts["canonical_owner"] = {
                "status": "unchanged",
                "ref": "preserved",
                "commit": preserved["commit"],
            }
        elif plan["owner_action"] == "public_core":
            receipts["canonical_owner"] = {
                "status": "unavailable", "ref": "unavailable", "commit": "unavailable",
            }

        if external_apply is not None:
            require(external_rollback is not None, "source_cutover_external_rollback_required")
            external_started = True
            external_apply()
        skill_snapshots = _snapshot_skill_targets(codex_home)
        materialization = materialize_cb(
            codex_home,
            specs,
            preserve_existing_owner=(
                plan["owner_action"] == "keep_owner" and "canonical_owner" not in by_name
            ),
        )
        receipt = {
            "contract_version": SOURCE_CUTOVER_RECEIPT_VERSION,
            "bootstrap_version": BOOTSTRAP_VERSION,
            "status": "applied",
            "plan_hash": plan["plan_hash"],
            "owner_action": plan["owner_action"],
            "previous": plan["current"],
            "current": plan["desired"],
            "sources": receipts,
            "materialization": materialization,
        }
        _validate_source_sync(receipt["sources"])
        _validate_host_materialization(receipt["materialization"])
        if precommit_verify is not None:
            precommit_verify(receipt)
        _write_cutover_receipt(codex_home, receipt)
        committed = True
        for _, rollback in swapped:
            if rollback is not None:
                safe_remove(root, rollback)
        discard_cb(_installed_skill_root(codex_home, create=False), skill_snapshots)
        return receipt
    except Exception as original:
        if committed:
            raise BootstrapError("source_cutover_postcommit_cleanup_failed") from original
        rollback_error: BaseException | None = None
        if external_started and external_rollback is not None:
            try:
                external_rollback()
            except BaseException as exc:
                rollback_error = exc
        if skill_snapshots:
            _restore_skill_targets(_installed_skill_root(codex_home, create=False), skill_snapshots)
        for target, rollback in reversed(swapped):
            if target.exists():
                failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
                os.replace(target, failed)
                safe_remove(root, failed)
            if rollback is not None and rollback.exists():
                os.replace(rollback, target)
        if rollback_error is not None:
            raise BootstrapError("distribution_rollback_failed") from rollback_error
        raise original
    finally:
        for _, staged, _ in prepared.values():
            if staged.exists():
                safe_remove(root, staged)
        for child in root.glob(".*.stage-*"):
            safe_remove(root, child)


def sync_sources(codex_home: Path, specs: tuple[SourceSpec, ...]) -> dict[str, Any]:
    root = _managed_source_root(codex_home, create=True)
    prepared: dict[str, tuple[SourceSpec, Path, str]] = {}
    swapped: list[tuple[Path, Path | None]] = []
    receipts: dict[str, Any] = {}
    try:
        for spec in specs:
            require(re.fullmatch(r"[a-z][a-z0-9_]*", spec.name) is not None, "source name invalid")
            target = root / spec.name
            ensure_managed_child(root, target)
            staged = root / f".{spec.name}.stage-{uuid.uuid4().hex}"
            ensure_managed_child(root, staged)
            run_git([
                "clone", "--quiet", "--depth", "1", "--single-branch",
                "--branch", spec.ref, "--", spec.remote, str(staged),
            ])
            staged_commit = inspect_checkout(staged, spec)
            if target.exists():
                current_commit = inspect_checkout(target, spec)
                if current_commit == staged_commit:
                    safe_remove(root, staged)
                    receipts[spec.name] = {"status": "unchanged", "ref": spec.ref, "commit": staged_commit}
                    continue
            prepared[spec.name] = (spec, staged, staged_commit)

        for name, (spec, staged, commit) in prepared.items():
            target = root / name
            rollback: Path | None = None
            if target.exists():
                rollback = root / f".{name}.rollback-{uuid.uuid4().hex}"
                ensure_managed_child(root, rollback)
                os.replace(target, rollback)
            swapped.append((target, rollback))
            os.replace(staged, target)
            require(inspect_checkout(target, spec) == commit, "managed_source_post_swap_mismatch")
            receipts[name] = {"status": "synced", "ref": spec.ref, "commit": commit}

        for _, rollback in swapped:
            if rollback is not None:
                safe_remove(root, rollback)
        return {"status": "ok", "sources": receipts}
    except Exception:
        for target, rollback in reversed(swapped):
            if rollback is not None and rollback.exists():
                if target.exists():
                    staged_failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
                    os.replace(target, staged_failed)
                    safe_remove(root, staged_failed)
                os.replace(rollback, target)
            elif rollback is None and target.exists():
                staged_failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
                os.replace(target, staged_failed)
                safe_remove(root, staged_failed)
        raise
    finally:
        for _, staged, _ in prepared.values():
            if staged.exists():
                safe_remove(root, staged)
        for child in root.glob(".*.stage-*"):
            safe_remove(root, child)


def create_remote(parent: Path, name: str) -> Path:
    work = parent / f"{name}-work"
    remote = parent / f"{name}.git"
    work.mkdir()
    run_git(["init", "-q", "-b", "main"], cwd=work)
    run_git(["config", "user.name", "Bootstrap Test"], cwd=work)
    run_git(["config", "user.email", "bootstrap@example.invalid"], cwd=work)
    (work / "README.md").write_text(name, encoding="utf-8")
    run_git(["add", "README.md"], cwd=work)
    run_git(["commit", "-q", "-m", "seed"], cwd=work)
    run_git(["clone", "--quiet", "--bare", str(work), str(remote)])
    return remote
