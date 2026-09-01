#!/usr/bin/env python3
"""Atomic workstation reconcile and deployment-pack contracts for Bootstrap 2.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


BOOTSTRAP_VERSION = "2.2.0"
SCOUT_VERSION = "5.7.0"
PACK_VERSION = "agent_memory_workstation_deployment_pack_v3"
DESKTOP_PROJECT_INVENTORY_VERSION = "agent_memory_desktop_project_inventory_v1"
WORKSTATION_RECONCILE_PLAN_VERSION = "agent_memory_workstation_reconcile_plan_v2"
WORKSTATION_RECONCILE_RECEIPT_VERSION = "agent_memory_workstation_reconcile_receipt_v3"
SOURCE_MANIFEST_VERSION = "agent_memory_source_manifest_v1"
RELEASE_MANIFEST_VERSION = "agent_memory_public_release_manifest_v1"
RELEASE_RESOLUTION_VERSION = "agent_memory_release_resolution_v1"
PUBLIC_REPOSITORY = "lly-personal/agent-memory-sidecar"
SOURCE_CUTOVER_PLAN_VERSION = "agent_memory_source_cutover_plan_v2"
SOURCE_CUTOVER_RECEIPT_VERSION = "agent_memory_source_cutover_receipt_v2"
SOURCE_CUTOVER_PLAN_FIELDS = {
    "contract_version", "bootstrap_version", "status", "owner_action",
    "current", "desired", "changes", "plan_hash",
}
SOURCE_MANIFEST_FIELDS = {
    "contract_version", "distribution", "sidecar", "canonical_owner",
}
SOURCE_FIELDS = {"remote", "ref", "commit"}
RELEASE_MANIFEST_FIELDS = {
    "contract_version", "status", "source", "versions", "artifacts", "verification",
}
RELEASE_SOURCE_FIELDS = {
    "repository", "ref", "commit", "authority_epoch", "engineering_source_commit",
    "initial_public_release", "authority_activated_at",
}
RELEASE_VERSION_FIELDS = {"core", "plugin", "bootstrap", "scout"}
RELEASE_RESOLUTION_FIELDS = {
    "contract_version", "status", "repository", "tag", "commit", "portable_root", "assets",
}
RELEASE_ASSET_FIELDS = {"sha256", "bytes"}
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
PACK_FIELDS = {
    "contract_version", "status", "display_locale", "generated_at", "desired_bundle",
    "distribution", "source_sync", "host_materialization", "consumer_scope",
    "consumer_activation", "limitations", "pack_hash",
}
RECONCILE_PLAN_FIELDS = {
    "contract_version", "bootstrap_version", "status", "desired_bundle",
    "observed_distribution", "source_plan_hash", "changes", "blockers",
    "confirmation_required", "requires_reload", "plan_hash",
}
DESIRED_BUNDLE_FIELDS = {
    "release_ref", "source_commit", "core_version", "plugin_version",
    "plugin_sha256", "bootstrap_version", "bootstrap_sha256",
    "scout_version", "scout_sha256",
}
DISTRIBUTION_FIELDS = {"marketplace", "plugin"}
MARKETPLACE_STATE_FIELDS = {"status", "source_sha256", "ref", "commit"}
PLUGIN_STATE_FIELDS = {
    "status", "source_sha256", "ref", "version", "content_sha256", "enabled",
}
SOURCE_SYNC_FIELDS = {"sidecar", "canonical_owner"}
SOURCE_RECEIPT_FIELDS = {"status", "ref", "commit"}
MATERIALIZATION_FIELDS = {
    "core", "global_binding", "doctor", "bootstrap_skill", "scout_skill",
}
CORE_STATE_FIELDS = {"status", "version", "source_commit", "artifact_sha256"}
SKILL_STATE_FIELDS = {"status", "version", "content_sha256"}
ACTIVATION_FIELDS = {"desktop_reload", "interactive_entry", "scheduled"}
DESKTOP_PROJECT_INVENTORY_FIELDS = {"contract_version", "inventory_status", "projects"}
DESKTOP_PROJECT_INPUT_FIELDS = {"display_name", "path", "is_git_repository"}
CONSUMER_SCOPE_FIELDS = {
    "status", "inventory_status", "desktop_project_count", "scanned_project_count",
    "matching_skill_count", "projects", "limitations",
}
CONSUMER_PROJECT_FIELDS = {"project_ref", "display_name", "status", "skills"}
CONSUMER_SKILL_FIELDS = {"name", "scope_level", "version", "content_sha256", "relation"}
CONSUMER_SKILLS = {
    "agent-memory-workstation-bootstrap": ("bootstrap_version", "bootstrap_sha256"),
    "global-owner-scout": ("scout_version", "scout_sha256"),
}
CONSUMER_SKILL_MAX_ENTRIES = 512
CONSUMER_SKILL_MAX_BYTES = 8 * 1024 * 1024
DESKTOP_PROJECT_MAX_COUNT = 500
STREAM_CHUNK_BYTES = 64 * 1024
MARKETPLACE_FIELDS = {"name", "interface", "plugins"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$")
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|opt|mnt)/)", re.IGNORECASE)
RAW_URL = re.compile(r"(?:https?|ssh|git)://|git@[^\s:]+:", re.IGNORECASE)


class BootstrapError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    remote: str
    ref: str = "main"
    expected_commit: str | None = None


def validate_source_manifest(value: Any) -> tuple[SourceSpec, ...]:
    exact(value, SOURCE_MANIFEST_FIELDS, "$")
    require(
        value["contract_version"] == SOURCE_MANIFEST_VERSION,
        "source_manifest_contract_invalid",
    )
    distribution = value["distribution"]
    require(distribution in {"development", "release"}, "source_manifest_distribution_invalid")
    specs: list[SourceSpec] = []
    for name in ("sidecar", "canonical_owner"):
        source = value[name]
        if source is None:
            require(name == "canonical_owner", "source_manifest_sidecar_required")
            continue
        exact(source, SOURCE_FIELDS, f"$.{name}")
        remote = str(source["remote"]).strip()
        ref = str(source["ref"]).strip()
        commit_value = source["commit"]
        commit = str(commit_value).strip().casefold() if commit_value is not None else None
        require(
            remote and not remote.startswith("-") and not re.search(r"[\r\n]", remote),
            f"source_manifest_{name}_remote_invalid",
        )
        normalize_remote(remote)
        require(
            SAFE_REF.fullmatch(ref) is not None
            and ".." not in ref
            and "//" not in ref
            and "@{" not in ref
            and not ref.endswith(("/", ".", ".lock")),
            f"source_manifest_{name}_ref_invalid",
        )
        require(commit is None or SHA40.fullmatch(commit) is not None, f"source_manifest_{name}_commit_invalid")
        if distribution == "release":
            require(commit is not None, f"source_manifest_{name}_commit_required")
        specs.append(SourceSpec(name, remote, ref, commit))
    return tuple(specs)


def load_source_manifest(path: Path | str) -> tuple[SourceSpec, ...]:
    value = _load_json_file(path, "source_manifest_unreadable")
    return validate_source_manifest(value)


def _physical_file_bytes(path: Path, code: str, *, limit: int = 1_048_576) -> bytes:
    try:
        value = path.lstat()
        require(
            stat.S_ISREG(value.st_mode)
            and not stat.S_ISLNK(value.st_mode)
            and not _is_reparse(value)
            and value.st_nlink == 1
            and 0 < value.st_size <= limit,
            code,
        )
        data = path.read_bytes()
        require(len(data) == value.st_size, code)
        return data
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError(code) from exc


def _load_json_file(path: Path | str, code: str) -> dict[str, Any]:
    try:
        value = json.loads(_physical_file_bytes(Path(path), code).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError(code) from exc
    require(isinstance(value, dict), code)
    return value


def _portable_root_for_release_manifest(path: Path) -> Path:
    path = path.expanduser().resolve()
    candidates = (path.parent / "portable", path.parent)
    for candidate in candidates:
        if (
            (candidate / "plugins" / "agent-memory-sidecar").is_dir()
            and (candidate / ".agents" / "skills" / "agent-memory-workstation-bootstrap").is_dir()
            and (candidate / ".agents" / "skills" / "global-owner-scout").is_dir()
        ):
            return candidate
    raise BootstrapError("release_portable_root_unavailable")


def load_desired_bundle(
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
) -> tuple[dict[str, Any], SourceSpec, str]:
    specs = load_source_manifest(source_manifest_path)
    by_name = {item.name: item for item in specs}
    sidecar = by_name["sidecar"]
    require(sidecar.expected_commit is not None, "desired_source_commit_required")
    release_path = Path(release_manifest_path).expanduser().resolve()
    release = _load_json_file(release_path, "release_manifest_unreadable")
    exact(release, RELEASE_MANIFEST_FIELDS, "$.release_manifest")
    require(release["contract_version"] == RELEASE_MANIFEST_VERSION, "release_manifest_contract_invalid")
    require(release["status"] == "public_artifact_verified", "release_manifest_status_invalid")
    source = release["source"]
    exact(source, RELEASE_SOURCE_FIELDS, "$.release_manifest.source")
    require(source["ref"] == sidecar.ref, "release_source_ref_mismatch")
    require(source["commit"] == sidecar.expected_commit, "release_source_commit_mismatch")
    require(normalize_remote(str(source["repository"])) == normalize_remote(sidecar.remote), "release_source_identity_mismatch")
    require(
        normalize_remote(str(source["repository"]))
        == normalize_remote(f"https://github.com/{PUBLIC_REPOSITORY}"),
        "release_public_repository_mismatch",
    )
    versions = release["versions"]
    exact(versions, RELEASE_VERSION_FIELDS, "$.release_manifest.versions")
    for field in RELEASE_VERSION_FIELDS:
        require(SEMVER.fullmatch(str(versions[field])) is not None, f"release {field} version invalid")
    require(sidecar.ref == f"v{versions['core']}", "release_core_ref_mismatch")
    resolution = _load_json_file(
        release_path.with_name("resolution.json"), "release_resolution_receipt_unreadable",
    )
    exact(resolution, RELEASE_RESOLUTION_FIELDS, "$.release_resolution")
    require(
        resolution["contract_version"] == RELEASE_RESOLUTION_VERSION
        and resolution["status"] == "verified"
        and resolution["repository"] == PUBLIC_REPOSITORY
        and resolution["tag"] == sidecar.ref
        and resolution["commit"] == sidecar.expected_commit
        and resolution["portable_root"] == "portable",
        "release_resolution_receipt_invalid",
    )
    assets = resolution["assets"]
    require(isinstance(assets, dict), "release_resolution_assets_invalid")
    for name, asset in assets.items():
        safe_text(name, "$.release_resolution.assets.name", 200)
        exact(asset, RELEASE_ASSET_FIELDS, f"$.release_resolution.assets.{name}")
        require(
            SHA64.fullmatch(str(asset["sha256"])) is not None
            and isinstance(asset["bytes"], int)
            and 0 < asset["bytes"] <= 67_108_864,
            "release_resolution_assets_invalid",
        )
    portable_name = f"agent-memory-portable-{versions['core']}.zip"
    for name in ("release-manifest.json", portable_name):
        artifact = release_path.with_name(name)
        require(name in assets, "release_resolution_assets_incomplete")
        data = _physical_file_bytes(artifact, "release_resolution_assets_incomplete", limit=67_108_864)
        require(
            len(data) == assets[name]["bytes"]
            and hashlib.sha256(data).hexdigest() == assets[name]["sha256"],
            f"release_resolution_asset_mismatch:{name}",
        )
    resolved_source = release_path.with_name("source-manifest.json")
    if Path(source_manifest_path).expanduser().resolve() == resolved_source:
        source_bytes = _physical_file_bytes(
            resolved_source, "release_resolution_asset_mismatch:source-manifest.json",
        )
        require(
            "source-manifest.json" in assets
            and len(source_bytes) == assets["source-manifest.json"]["bytes"]
            and hashlib.sha256(source_bytes).hexdigest()
            == assets["source-manifest.json"]["sha256"],
            "release_resolution_asset_mismatch:source-manifest.json",
        )
    portable_root = _portable_root_for_release_manifest(release_path)
    plugin_manifest = _load_json_file(
        portable_root / "plugins" / "agent-memory-sidecar" / ".codex-plugin" / "plugin.json",
        "release_plugin_manifest_unreadable",
    )
    require(plugin_manifest.get("version") == versions["plugin"], "release_plugin_version_mismatch")
    require(
        _skill_version(portable_root / ".agents" / "skills" / "agent-memory-workstation-bootstrap")
        == versions["bootstrap"],
        "release_bootstrap_version_mismatch",
    )
    require(
        _skill_version(portable_root / ".agents" / "skills" / "global-owner-scout")
        == versions["scout"],
        "release_scout_version_mismatch",
    )
    desired = {
        "release_ref": sidecar.ref,
        "source_commit": sidecar.expected_commit,
        "core_version": versions["core"],
        "plugin_version": versions["plugin"],
        "plugin_sha256": physical_tree_hash(
            portable_root / "plugins" / "agent-memory-sidecar",
            excluded_relatives={"source-manifest.json"},
        ),
        "bootstrap_version": versions["bootstrap"],
        "bootstrap_sha256": physical_tree_hash(
            portable_root / ".agents" / "skills" / "agent-memory-workstation-bootstrap",
        ),
        "scout_version": versions["scout"],
        "scout_sha256": physical_tree_hash(
            portable_root / ".agents" / "skills" / "global-owner-scout",
        ),
    }
    validate_desired_bundle(desired)
    source_sha256 = hashlib.sha256(normalize_remote(sidecar.remote).encode("utf-8")).hexdigest()
    return desired, sidecar, source_sha256


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BootstrapError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(value: dict[str, Any], field: str) -> str:
    copied = dict(value)
    copied.pop(field, None)
    return hashlib.sha256(canonical(copied)).hexdigest()


def exact(value: Any, fields: set[str], path: str) -> None:
    require(isinstance(value, dict), f"{path} must be an object")
    require(set(value) == fields, f"{path} fields invalid")


def safe_text(value: Any, path: str, limit: int = 400) -> None:
    require(isinstance(value, str) and value.strip(), f"{path} must be non-empty text")
    require(len(value) <= limit, f"{path} too long")
    require(ABSOLUTE_PATH.search(value) is None, f"{path} leaks an absolute path")
    require(RAW_URL.search(value) is None, f"{path} leaks a source URL")


def normalize_remote(remote: str) -> str:
    remote = remote.strip()
    require(remote and not re.search(r"[\r\n]", remote), "source remote invalid")
    if re.match(r"^[A-Za-z]:[\\/]", remote) or Path(remote).is_absolute():
        normalized = str(Path(remote).resolve()).replace("\\", "/")
    elif re.match(r"^[^@\s]+@[^:\s]+:.+$", remote):
        require("?" not in remote and "#" not in remote, "source remote contains query or fragment")
        host_path = remote.split("@", 1)[1]
        host, path = host_path.split(":", 1)
        normalized = f"{host.lower()}/{path.strip('/')}"
    else:
        parsed = urlsplit(remote)
        require(parsed.scheme in {"https", "ssh", "file"} or parsed.scheme == "", "source remote scheme invalid")
        require(parsed.username is None and parsed.password is None, "source remote contains credentials")
        require(not parsed.query and not parsed.fragment, "source remote contains query or fragment")
        if parsed.scheme:
            normalized = urlunsplit((parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.path.rstrip("/"), "", ""))
        else:
            normalized = str(Path(remote).resolve()).replace("\\", "/")
    return normalized[:-4] if normalized.lower().endswith(".git") else normalized


def run_git(args: list[str], *, cwd: Path | None = None) -> str:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError("source_git_timeout") from exc
    if result.returncode:
        raise BootstrapError("source_git_failed")
    return result.stdout.strip()


def _is_reparse(value: os.stat_result) -> bool:
    return bool(getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _physical_directory(path: Path, *, create: bool) -> Path:
    if create and not path.exists() and not path.is_symlink():
        path.mkdir()
    if not path.exists() and not path.is_symlink():
        return path
    value = path.lstat()
    require(
        stat.S_ISDIR(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and not _is_reparse(value),
        "managed_directory_alias_forbidden",
    )
    return path


def _codex_home_root(codex_home: Path, *, create: bool) -> Path:
    root = codex_home.expanduser().resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    require(root.is_dir(), "codex_home_invalid")
    return root


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
    store = codex_home.resolve() / "agent-memory-sidecar" / "memory.sqlite"
    if not store.exists() and not store.is_symlink():
        return None
    try:
        value = store.lstat()
        require(
            stat.S_ISREG(value.st_mode)
            and not stat.S_ISLNK(value.st_mode)
            and not _is_reparse(value)
            and value.st_nlink == 1,
            "source_cutover_owner_state_ambiguous",
        )
        connection = sqlite3.connect(f"file:{store.as_posix()}?mode=ro", uri=True)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='global_instruction_binding'"
            ).fetchone()
            if table is None:
                return None
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(global_instruction_binding)")
            }
            require(
                {"singleton", "source_root", "source_commit"}.issubset(columns),
                "source_cutover_owner_state_ambiguous",
            )
            row = connection.execute(
                "SELECT source_root, source_commit FROM global_instruction_binding WHERE singleton = 1"
            ).fetchone()
            if row is None:
                return None
            source_root = str(row[0]).strip()
            source_commit = str(row[1]).strip().casefold()
            require(
                source_root and SHA40.fullmatch(source_commit) is not None,
                "source_cutover_owner_state_ambiguous",
            )
            return {"source_root": source_root, "source_commit": source_commit}
        finally:
            connection.close()
    except BootstrapError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise BootstrapError("source_cutover_owner_state_ambiguous") from exc


def _preserved_owner_identity(
    codex_home: Path,
    current_owner: dict[str, str] | None,
) -> dict[str, str] | None:
    binding = _existing_global_binding(codex_home)
    if current_owner is None and binding is None:
        return None
    require(
        current_owner is not None and binding is not None,
        "source_cutover_owner_state_ambiguous",
    )
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
        target = root / name
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


def validate_source_cutover_plan(value: Any) -> dict[str, Any]:
    exact(value, SOURCE_CUTOVER_PLAN_FIELDS, "$")
    require(value["contract_version"] == SOURCE_CUTOVER_PLAN_VERSION, "source_cutover_plan_contract_invalid")
    require(value["bootstrap_version"] == BOOTSTRAP_VERSION, "source_cutover_plan_bootstrap_invalid")
    require(value["status"] in {"ready", "noop"}, "source_cutover_plan_status_invalid")
    require(value["owner_action"] in {"keep_owner", "public_core"}, "source_cutover_plan_owner_action_invalid")
    require(
        isinstance(value["current"], dict)
        and set(value["current"]) == {"sidecar", "canonical_owner"}
        and isinstance(value["desired"], dict)
        and set(value["desired"]) == {"sidecar", "canonical_owner"},
        "source_cutover_plan_sources_invalid",
    )
    changes = value["changes"]
    require(
        isinstance(changes, list)
        and len(changes) <= 2
        and len(changes) == len(set(changes))
        and all(
            isinstance(item, str)
            and re.fullmatch(r"(?:sidecar|canonical_owner):(?:install|replace)", item) is not None
            for item in changes
        ),
        "source_cutover_plan_changes_invalid",
    )
    require((value["status"] == "noop") == (not changes), "source_cutover_plan_status_invalid")
    plan_hash = str(value["plan_hash"]).casefold()
    require(
        SHA64.fullmatch(plan_hash) is not None
        and object_hash(value, "plan_hash") == plan_hash,
        "source_cutover_plan_hash_invalid",
    )
    return value


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
            # DirEntry.stat() reports zero for st_ino/st_dev/st_nlink on
            # Windows.  The path-based call performs the metadata query that
            # keeps the hard-link and reparse-point checks meaningful there.
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
    external_apply: Callable[[], None] | None = None,
    external_rollback: Callable[[], None] | None = None,
    precommit_verify: Callable[[dict[str, Any]], None] | None = None,
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
            target = root / name
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
        materialization = materialize_host(
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
        _discard_skill_snapshots(_installed_skill_root(codex_home, create=False), skill_snapshots)
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


def run_json(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError("host_materialization_timeout") from exc
    require(len(result.stdout) <= 1_048_576 and len(result.stderr) <= 1_048_576, "host_materialization_output_too_large")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError("host_materialization_output_invalid") from exc
    require(isinstance(payload, dict), "host_materialization_output_invalid")
    if result.returncode:
        error = payload.get("error")
        code = error.get("code", "host_materialization_failed") if isinstance(error, dict) else "host_materialization_failed"
        raise BootstrapError(str(code))
    return payload


def run_codex_json(arguments: list[str], *, codex_home: Path) -> dict[str, Any]:
    executable = shutil.which("codex")
    require(executable is not None, "codex_cli_unavailable")
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    try:
        result = subprocess.run(
            [executable, *arguments],
            cwd=codex_home,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError("codex_plugin_command_timeout") from exc
    require(
        len(result.stdout) <= 1_048_576 and len(result.stderr) <= 1_048_576,
        "codex_plugin_output_too_large",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError("codex_plugin_output_invalid") from exc
    require(isinstance(payload, dict), "codex_plugin_output_invalid")
    require(result.returncode == 0, "codex_plugin_command_failed")
    return payload


def _missing_marketplace_state() -> dict[str, Any]:
    return {
        "status": "missing", "source_sha256": "unavailable",
        "ref": "unavailable", "commit": "unavailable",
    }


def _missing_plugin_state() -> dict[str, Any]:
    return {
        "status": "missing", "source_sha256": "unavailable", "ref": "unavailable",
        "version": "unavailable", "content_sha256": "unavailable", "enabled": None,
    }


def _unavailable_marketplace_state() -> dict[str, Any]:
    return {**_missing_marketplace_state(), "status": "unavailable"}


def _unavailable_plugin_state() -> dict[str, Any]:
    return {**_missing_plugin_state(), "status": "unavailable"}


def _observe_distribution_with_private(
    codex_home: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    codex_home = _codex_home_root(codex_home, create=False)
    private: dict[str, Any] = {
        "marketplace": {"present": False, "remote": None, "ref": None},
        "plugin": {"installed": False, "enabled": None},
    }
    try:
        marketplace_payload = run_codex_json(
            ["plugin", "marketplace", "list", "--json"], codex_home=codex_home,
        )
        marketplaces = marketplace_payload.get("marketplaces")
        require(isinstance(marketplaces, list), "marketplace_observation_invalid")
        matches = [item for item in marketplaces if isinstance(item, dict) and item.get("name") == "agent-memory"]
        require(len(matches) <= 1, "marketplace_observation_ambiguous")
        if not matches:
            marketplace_state = _missing_marketplace_state()
        else:
            entry = matches[0]
            root_text = entry.get("root")
            source_data = entry.get("marketplaceSource")
            require(isinstance(root_text, str) and root_text, "marketplace_root_invalid")
            require(
                isinstance(source_data, dict)
                and source_data.get("sourceType") == "git"
                and isinstance(source_data.get("source"), str),
                "marketplace_source_invalid",
            )
            root = Path(root_text).expanduser().resolve()
            checkout = inspect_marketplace_checkout(root)
            remote = str(source_data["source"])
            require(
                checkout["remote_sha256"]
                == hashlib.sha256(normalize_remote(remote).encode("utf-8")).hexdigest(),
                "marketplace_source_identity_mismatch",
            )
            marketplace_value = _load_json_file(
                root / ".agents" / "plugins" / "marketplace.json",
                "marketplace_manifest_unreadable",
            )
            validate_marketplace(marketplace_value, expected_remote=remote)
            source = marketplace_value["plugins"][0]["source"]
            if checkout["metadata_ref"] is not None:
                require(checkout["metadata_ref"] == source["ref"], "marketplace_ref_mismatch")
            marketplace_state = {
                "status": "present",
                "source_sha256": checkout["remote_sha256"],
                "ref": source["ref"],
                "commit": checkout["commit"],
            }
            private["marketplace"] = {
                "present": True, "remote": remote, "ref": source["ref"],
            }
    except (BootstrapError, OSError, UnicodeError):
        marketplace_state = _unavailable_marketplace_state()

    try:
        plugin_payload = run_codex_json(
            ["plugin", "list", "--marketplace", "agent-memory", "--available", "--json"],
            codex_home=codex_home,
        )
        installed = plugin_payload.get("installed")
        require(isinstance(installed, list), "plugin_observation_invalid")
        matches = [
            item for item in installed
            if isinstance(item, dict) and item.get("pluginId") == "agent-memory-sidecar@agent-memory"
        ]
        require(len(matches) <= 1, "plugin_observation_ambiguous")
        if not matches:
            plugin_state = _missing_plugin_state()
        else:
            entry = matches[0]
            source = entry.get("source")
            version = str(entry.get("version", ""))
            enabled = entry.get("enabled")
            require(
                entry.get("installed") is True
                and isinstance(enabled, bool)
                and SEMVER.fullmatch(version) is not None
                and isinstance(source, dict)
                and source.get("source") == "git-subdir"
                and isinstance(source.get("url"), str)
                and source.get("path") in {"plugins/agent-memory-sidecar", "./plugins/agent-memory-sidecar"}
                and isinstance(source.get("ref"), str),
                "plugin_observation_invalid",
            )
            cache_root = (
                codex_home / "plugins" / "cache" / "agent-memory"
                / "agent-memory-sidecar" / version
            )
            manifest = _load_json_file(
                cache_root / ".codex-plugin" / "plugin.json",
                "plugin_manifest_unreadable",
            )
            require(manifest.get("version") == version, "plugin_manifest_version_mismatch")
            plugin_state = {
                "status": "installed",
                "source_sha256": hashlib.sha256(
                    normalize_remote(str(source["url"])).encode("utf-8")
                ).hexdigest(),
                "ref": str(source["ref"]),
                "version": version,
                "content_sha256": physical_tree_hash(
                    cache_root, excluded_relatives={"source-manifest.json"},
                ),
                "enabled": enabled,
            }
            private["plugin"] = {"installed": True, "enabled": enabled}
    except (BootstrapError, OSError, UnicodeError):
        plugin_state = _unavailable_plugin_state()
    observed = {"marketplace": marketplace_state, "plugin": plugin_state}
    return validate_observed_distribution(observed), private


def observe_distribution(codex_home: Path) -> dict[str, Any]:
    observed, _ = _observe_distribution_with_private(codex_home)
    return observed


def core_setup_data(payload: dict[str, Any]) -> dict[str, Any]:
    require(
        payload.get("contract_version") == "agent_memory_result_v1"
        and payload.get("operation") == "setup"
        and payload.get("status") == "ok"
        and payload.get("error") is None,
        "core_setup_result_invalid",
    )
    data = payload.get("data")
    require(isinstance(data, dict), "core_setup_output_invalid")
    require(data.get("status") == "ok", "core_setup_failed")
    doctor = data.get("doctor")
    require(isinstance(doctor, dict), "core_setup_doctor_missing")
    require(doctor.get("status") == "ok", "doctor_failed")
    return data


def _skill_version(root: Path) -> str:
    try:
        text = (root / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BootstrapError("installed_skill_version_unreadable") from exc
    match = re.search(r"^- Skill version:\s*`([^`]+)`\s*$", text, re.MULTILINE)
    require(match is not None and SEMVER.fullmatch(match.group(1)) is not None, "installed_skill_version_invalid")
    return match.group(1)


def _unavailable_skill_state() -> dict[str, Any]:
    return {"status": "unavailable", "version": "unavailable", "content_sha256": "unavailable"}


def _observe_installed_skill(codex_home: Path, name: str) -> dict[str, Any]:
    target = _installed_skill_root(codex_home, create=False) / name
    if not target.exists() and not target.is_symlink():
        return _unavailable_skill_state()
    try:
        return {
            "status": "unchanged",
            "version": _skill_version(target),
            "content_sha256": physical_tree_hash(target),
        }
    except (BootstrapError, OSError, UnicodeError):
        return _unavailable_skill_state()


def _not_observed_consumer_scope() -> dict[str, Any]:
    return {
        "status": "not_observed",
        "inventory_status": "not_observed",
        "desktop_project_count": 0,
        "scanned_project_count": 0,
        "matching_skill_count": 0,
        "projects": [],
        "limitations": ["当前任务尚未执行 Desktop 项目级同名 Skill 检查。"],
    }


def validate_consumer_scope(value: Any) -> dict[str, Any]:
    exact(value, CONSUMER_SCOPE_FIELDS, "$.consumer_scope")
    require(value["status"] in {"not_observed", "exact", "drifted", "bounded"}, "consumer scope status invalid")
    require(
        value["inventory_status"] in {"not_observed", "complete", "bounded"},
        "consumer inventory status invalid",
    )
    for field in ("desktop_project_count", "scanned_project_count", "matching_skill_count"):
        require(isinstance(value[field], int) and value[field] >= 0, f"consumer scope {field} invalid")
    require(value["scanned_project_count"] <= value["desktop_project_count"], "consumer scope project count invalid")
    require(isinstance(value["projects"], list), "consumer scope projects invalid")
    require(isinstance(value["limitations"], list), "consumer scope limitations invalid")
    seen_refs: set[str] = set()
    matching_skill_count = 0
    has_drift = False
    has_bounded = False
    for index, project in enumerate(value["projects"]):
        exact(project, CONSUMER_PROJECT_FIELDS, f"$.consumer_scope.projects[{index}]")
        safe_text(project["project_ref"], f"$.consumer_scope.projects[{index}].project_ref", 80)
        safe_text(project["display_name"], f"$.consumer_scope.projects[{index}].display_name", 160)
        require(project["project_ref"] not in seen_refs, "consumer project ref duplicated")
        seen_refs.add(project["project_ref"])
        require(project["status"] in {"exact", "drifted", "bounded"}, "consumer project status invalid")
        require(isinstance(project["skills"], list), "consumer project skills invalid")
        project_relations: set[str] = set()
        skill_identities: set[tuple[str, int]] = set()
        for skill_index, skill in enumerate(project["skills"]):
            exact(skill, CONSUMER_SKILL_FIELDS, f"$.consumer_scope.projects[{index}].skills[{skill_index}]")
            require(skill["name"] in CONSUMER_SKILLS, "consumer skill name invalid")
            require(isinstance(skill["scope_level"], int) and skill["scope_level"] >= 0, "consumer skill scope level invalid")
            skill_identity = (skill["name"], skill["scope_level"])
            require(skill_identity not in skill_identities, "consumer skill duplicated")
            skill_identities.add(skill_identity)
            require(skill["relation"] in {"exact", "drifted", "unreadable"}, "consumer skill relation invalid")
            if skill["relation"] == "unreadable":
                require(skill["version"] == "unavailable", "unreadable consumer skill version invalid")
                require(skill["content_sha256"] == "unavailable", "unreadable consumer skill hash invalid")
            else:
                require(SEMVER.fullmatch(str(skill["version"])) is not None, "consumer skill version invalid")
                require(SHA64.fullmatch(str(skill["content_sha256"])) is not None, "consumer skill hash invalid")
            project_relations.add(skill["relation"])
            matching_skill_count += 1
        expected_project_status = (
            "bounded" if "unreadable" in project_relations or project["status"] == "bounded"
            else ("drifted" if "drifted" in project_relations else "exact")
        )
        require(project["status"] == expected_project_status, "consumer project status inconsistent")
        has_drift = has_drift or "drifted" in project_relations
        has_bounded = has_bounded or project["status"] == "bounded"
    require(value["matching_skill_count"] == matching_skill_count, "consumer skill count invalid")
    if value["status"] == "not_observed":
        require(value["inventory_status"] == "not_observed", "unobserved consumer inventory invalid")
        require(
            value["desktop_project_count"] == 0
            and value["scanned_project_count"] == 0
            and value["matching_skill_count"] == 0
            and value["projects"] == [],
            "unobserved consumer scope must be empty",
        )
    else:
        expected_status = (
            "bounded" if value["inventory_status"] == "bounded" or has_bounded
            else ("drifted" if has_drift else "exact")
        )
        require(value["status"] == expected_status, "consumer scope status inconsistent")
        if value["status"] in {"exact", "drifted"}:
            require(value["inventory_status"] == "complete", "qualified consumer scope requires complete inventory")
            require(
                value["scanned_project_count"] == value["desktop_project_count"],
                "qualified consumer scope requires complete project read",
            )
    for index, item in enumerate(value["limitations"]):
        safe_text(item, f"$.consumer_scope.limitations[{index}]", 300)
    return value


def _consumer_discovery_roots(project_root: Path, *, is_git_repository: bool) -> list[Path]:
    if not is_git_repository:
        return [project_root]
    repository_root = Path(run_git(["rev-parse", "--show-toplevel"], cwd=project_root)).resolve()
    require(
        repository_root == project_root or repository_root in project_root.parents,
        "consumer_repository_root_invalid",
    )
    roots: list[Path] = []
    current = project_root
    while True:
        roots.append(current)
        if current == repository_root:
            return roots
        current = current.parent


def observe_consumer_scope(inventory: Any, *, desired: dict[str, Any]) -> dict[str, Any]:
    """Read product same-name project Skills from one ephemeral Desktop inventory."""
    desired = validate_desired_bundle(desired)
    exact(inventory, DESKTOP_PROJECT_INVENTORY_FIELDS, "$.desktop_project_inventory")
    require(
        inventory["contract_version"] == DESKTOP_PROJECT_INVENTORY_VERSION,
        "desktop project inventory contract invalid",
    )
    require(inventory["inventory_status"] in {"complete", "bounded"}, "desktop project inventory status invalid")
    require(
        isinstance(inventory["projects"], list)
        and len(inventory["projects"]) <= DESKTOP_PROJECT_MAX_COUNT,
        "desktop project inventory invalid",
    )
    normalized: list[tuple[str, Path | None, bool]] = []
    seen_paths: set[str] = set()
    for index, project in enumerate(inventory["projects"]):
        exact(project, DESKTOP_PROJECT_INPUT_FIELDS, f"$.desktop_project_inventory.projects[{index}]")
        safe_text(project["display_name"], f"$.desktop_project_inventory.projects[{index}].display_name", 160)
        require(not re.search(r"[\r\n]", project["display_name"]), "desktop project display name invalid")
        require(isinstance(project["is_git_repository"], bool), "desktop project Git state invalid")
        raw_path = project["path"]
        if raw_path is None:
            resolved = None
        else:
            require(isinstance(raw_path, str) and raw_path.strip(), "desktop project path invalid")
            path = Path(raw_path).expanduser()
            require(path.is_absolute(), "desktop project path must be absolute")
            resolved = path.resolve()
            identity = os.path.normcase(str(resolved))
            require(identity not in seen_paths, "desktop project path duplicated")
            seen_paths.add(identity)
        normalized.append((project["display_name"].strip(), resolved, project["is_git_repository"]))
    normalized.sort(
        key=lambda item: (
            item[0].casefold(), "" if item[1] is None else os.path.normcase(str(item[1])), item[2],
        )
    )

    projects: list[dict[str, Any]] = []
    scanned_project_count = 0
    for index, (display_name, project_root, is_git_repository) in enumerate(normalized):
        project_ref = "desktop-project-" + hashlib.sha256(
            canonical({"display_name": display_name, "ordinal": index})
        ).hexdigest()[:16]
        project_status = "exact"
        skills: list[dict[str, Any]] = []
        try:
            require(project_root is not None, "consumer_project_unavailable")
            root_state = project_root.lstat()
            require(stat.S_ISDIR(root_state.st_mode) and not _is_reparse(root_state), "consumer_project_unreadable")
            scanned_project_count += 1
            discovery_roots = _consumer_discovery_roots(
                project_root, is_git_repository=is_git_repository,
            )
            for scope_level, scope_root in enumerate(discovery_roots):
                agents_root = scope_root / ".agents"
                skills_root = agents_root / "skills"
                if agents_root.exists() or agents_root.is_symlink():
                    agents_state = agents_root.lstat()
                    require(
                        stat.S_ISDIR(agents_state.st_mode) and not stat.S_ISLNK(agents_state.st_mode) and not _is_reparse(agents_state),
                        "consumer_skill_parent_unsafe",
                    )
                if not skills_root.exists() and not skills_root.is_symlink():
                    continue
                skills_state = skills_root.lstat()
                require(
                    stat.S_ISDIR(skills_state.st_mode) and not stat.S_ISLNK(skills_state.st_mode) and not _is_reparse(skills_state),
                    "consumer_skill_parent_unsafe",
                )
                for name, (version_field, hash_field) in CONSUMER_SKILLS.items():
                    skill_root = skills_root / name
                    if not skill_root.exists() and not skill_root.is_symlink():
                        continue
                    try:
                        version = _skill_version(skill_root)
                        content_sha256 = bounded_physical_tree_hash(
                            skill_root,
                            max_entries=CONSUMER_SKILL_MAX_ENTRIES,
                            max_bytes=CONSUMER_SKILL_MAX_BYTES,
                        )
                        require(version == _skill_version(skill_root), "consumer_skill_changed_during_read")
                        require(
                            content_sha256 == bounded_physical_tree_hash(
                                skill_root,
                                max_entries=CONSUMER_SKILL_MAX_ENTRIES,
                                max_bytes=CONSUMER_SKILL_MAX_BYTES,
                            ),
                            "consumer_skill_changed_during_read",
                        )
                        relation = (
                            "exact"
                            if version == desired[version_field] and content_sha256 == desired[hash_field]
                            else "drifted"
                        )
                    except (BootstrapError, OSError, UnicodeError):
                        version = "unavailable"
                        content_sha256 = "unavailable"
                        relation = "unreadable"
                    skills.append({
                        "name": name,
                        "scope_level": scope_level,
                        "version": version,
                        "content_sha256": content_sha256,
                        "relation": relation,
                    })
            relations = {item["relation"] for item in skills}
            project_status = (
                "bounded" if "unreadable" in relations
                else ("drifted" if "drifted" in relations else "exact")
            )
        except (BootstrapError, OSError):
            project_status = "bounded"
        if skills or project_status == "bounded":
            projects.append({
                "project_ref": project_ref,
                "display_name": display_name,
                "status": project_status,
                "skills": skills,
            })

    has_bounded = any(project["status"] == "bounded" for project in projects)
    has_drift = any(project["status"] == "drifted" for project in projects)
    status = (
        "bounded" if inventory["inventory_status"] == "bounded" or has_bounded
        else ("drifted" if has_drift else "exact")
    )
    limitations: list[str] = []
    if inventory["inventory_status"] == "bounded":
        limitations.append("Desktop 项目清单不完整；未枚举的消费者范围保持未知。")
    if has_bounded:
        limitations.append("至少一个项目或同名 Skill 无法安全完整读取；该消费者范围保持未知。")
    result = {
        "status": status,
        "inventory_status": inventory["inventory_status"],
        "desktop_project_count": len(normalized),
        "scanned_project_count": scanned_project_count,
        "matching_skill_count": sum(len(project["skills"]) for project in projects),
        "projects": projects,
        "limitations": limitations,
    }
    return validate_consumer_scope(result)


def _unavailable_host_materialization(*, owner_expected: bool) -> dict[str, Any]:
    return {
        "core": {
            "status": "unavailable", "version": "unavailable",
            "source_commit": "unavailable", "artifact_sha256": "unavailable",
        },
        "global_binding": "failed" if owner_expected else "unavailable",
        "doctor": "failed",
        "bootstrap_skill": _unavailable_skill_state(),
        "scout_skill": _unavailable_skill_state(),
    }


def observe_host_materialization(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    owner_expected: bool,
) -> dict[str, Any]:
    """Read the current Core, Doctor, Owner binding, and installed Skill state."""
    codex_home = _codex_home_root(codex_home, create=False)
    by_name = {spec.name: spec for spec in specs}
    require("sidecar" in by_name and len(by_name) == len(specs), "managed_source_name_invalid")
    sidecar = _managed_source_root(codex_home, create=False) / "sidecar"
    state = _unavailable_host_materialization(owner_expected=owner_expected)
    state["bootstrap_skill"] = _observe_installed_skill(
        codex_home, "agent-memory-workstation-bootstrap",
    )
    state["scout_skill"] = _observe_installed_skill(codex_home, "global-owner-scout")
    try:
        inspect_checkout(sidecar, by_name["sidecar"])
        init_text = (sidecar / "src" / "agent_memory_sidecar" / "__init__.py").read_text(encoding="utf-8")
        version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        require(
            version_match is not None and SEMVER.fullmatch(version_match.group(1)) is not None,
            "core_version_invalid",
        )
        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(sidecar / "src") + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        payload = run_json(
            [sys.executable, "-B", "-m", "agent_memory_sidecar", "--cwd", str(sidecar), "doctor"],
            cwd=sidecar,
            env=env,
        )
        require(
            payload.get("contract_version") == "agent_memory_result_v1"
            and payload.get("operation") == "doctor"
            and payload.get("status") == "ok"
            and payload.get("error") is None,
            "core_doctor_result_invalid",
        )
        data = payload.get("data")
        require(isinstance(data, dict) and data.get("status") == "ok", "doctor_failed")
        runtime = data.get("runtime")
        require(isinstance(runtime, dict), "core_runtime_identity_missing")
        source_commit = str(runtime.get("source_commit", "")).casefold()
        artifact_sha256 = str(runtime.get("artifact_sha256", "")).removeprefix("sha256:")
        require(
            SHA40.fullmatch(source_commit) is not None
            and SHA64.fullmatch(artifact_sha256) is not None,
            "core_runtime_identity_invalid",
        )
        global_state = data.get("global")
        if owner_expected:
            require(
                isinstance(global_state, dict) and global_state.get("full_document_parity") is True,
                "global_binding_unverified",
            )
            binding = "verified"
        else:
            require(global_state is None, "unexpected_global_binding")
            binding = "unavailable"
        state.update({
            "core": {
                "status": "verified",
                "version": version_match.group(1),
                "source_commit": source_commit,
                "artifact_sha256": artifact_sha256,
            },
            "global_binding": binding,
            "doctor": "verified",
        })
    except (BootstrapError, OSError, UnicodeError):
        pass
    return _validate_host_materialization(state)


def materialize_host(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    preserve_existing_owner: bool = False,
) -> dict[str, Any]:
    codex_home = _codex_home_root(codex_home, create=False)
    root = _managed_source_root(codex_home, create=False)
    by_name = {spec.name: spec for spec in specs}
    require(set(by_name).issubset({"sidecar", "canonical_owner"}), "managed_source_name_invalid")
    require("sidecar" in by_name, "managed_sidecar_source_missing")
    require(len(by_name) == len(specs), "managed_source_name_duplicate")
    require(
        not preserve_existing_owner or "canonical_owner" not in by_name,
        "managed_owner_preservation_invalid",
    )
    if "canonical_owner" not in by_name and not preserve_existing_owner:
        require(
            not _has_existing_global_binding(codex_home),
            "public_core_existing_global_binding",
        )
    for spec in specs:
        inspect_checkout(root / spec.name, spec)
    sidecar = root / "sidecar"
    canonical_owner = root / "canonical_owner" if "canonical_owner" in by_name else None
    if preserve_existing_owner:
        current_owner = inspect_existing_checkout(root / "canonical_owner")
        require(
            _preserved_owner_identity(codex_home, current_owner) is not None,
            "source_cutover_owner_state_ambiguous",
        )
        canonical_owner = root / "canonical_owner"
    enrollment = sidecar / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "enrollment.py"
    require(enrollment.is_file(), "managed_bootstrap_missing")
    skill_root = _installed_skill_root(codex_home, create=True)
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(sidecar / "src") + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    bootstrap_result = run_json([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / ".agents" / "skills" / "agent-memory-workstation-bootstrap"),
        "--target", str(skill_root / "agent-memory-workstation-bootstrap"), "--version", BOOTSTRAP_VERSION,
    ], cwd=sidecar, env=env)
    scout_result = run_json([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / ".agents" / "skills" / "global-owner-scout"),
        "--target", str(skill_root / "global-owner-scout"), "--version", SCOUT_VERSION,
    ], cwd=sidecar, env=env)
    setup_command = [
        sys.executable, "-B", "-m", "agent_memory_sidecar", "--cwd", str(sidecar), "setup", "--apply",
    ]
    if canonical_owner is not None:
        setup_command.extend([
            "--global-rules-source", str(canonical_owner), "--rebind-global-rules-source",
        ])
    setup_data = core_setup_data(run_json(setup_command, cwd=sidecar, env=env))
    runtime = setup_data.get("runtime")
    require(isinstance(runtime, dict), "core_runtime_identity_missing")
    source_commit = runtime.get("source_commit")
    artifact_sha256 = str(runtime.get("artifact_sha256", ""))
    if artifact_sha256.startswith("sha256:"):
        artifact_sha256 = artifact_sha256.removeprefix("sha256:")
    require(
        source_commit == by_name["sidecar"].expected_commit
        and SHA64.fullmatch(artifact_sha256) is not None,
        "core_runtime_identity_mismatch",
    )
    try:
        init_text = (sidecar / "src" / "agent_memory_sidecar" / "__init__.py").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BootstrapError("core_version_unreadable") from exc
    version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    require(
        version_match is not None and SEMVER.fullmatch(version_match.group(1)) is not None,
        "core_version_invalid",
    )
    return {
        "core": {
            "status": "verified",
            "version": version_match.group(1),
            "source_commit": source_commit,
            "artifact_sha256": artifact_sha256,
        },
        "global_binding": "verified" if canonical_owner is not None else "unavailable",
        "doctor": "verified",
        "bootstrap_skill": {
            "status": bootstrap_result["status"],
            "version": bootstrap_result["version"],
            "content_sha256": bootstrap_result["hash"],
        },
        "scout_skill": {
            "status": scout_result["status"],
            "version": scout_result["version"],
            "content_sha256": scout_result["hash"],
        },
    }


def _has_existing_global_binding(codex_home: Path) -> bool:
    store = codex_home.resolve() / "agent-memory-sidecar" / "memory.sqlite"
    if not store.exists():
        return False
    try:
        connection = sqlite3.connect(f"file:{store.as_posix()}?mode=ro", uri=True)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='global_instruction_binding'"
            ).fetchone()
            if table is None:
                return False
            return connection.execute(
                "SELECT 1 FROM global_instruction_binding LIMIT 1"
            ).fetchone() is not None
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise BootstrapError("public_core_binding_check_failed") from exc


def validate_desired_bundle(value: Any) -> dict[str, Any]:
    exact(value, DESIRED_BUNDLE_FIELDS, "$.desired_bundle")
    safe_text(value["release_ref"], "$.desired_bundle.release_ref", 128)
    require(SHA40.fullmatch(str(value["source_commit"])) is not None, "desired source commit invalid")
    for field in ("core_version", "plugin_version", "bootstrap_version", "scout_version"):
        require(SEMVER.fullmatch(str(value[field])) is not None, f"desired {field} invalid")
    for field in ("plugin_sha256", "bootstrap_sha256", "scout_sha256"):
        require(SHA64.fullmatch(str(value[field])) is not None, f"desired {field} invalid")
    require(value["bootstrap_version"] == BOOTSTRAP_VERSION, "desired Bootstrap version invalid")
    require(value["scout_version"] == SCOUT_VERSION, "desired Scout version invalid")
    return value


def _unavailable_or_sha64(value: Any, path: str) -> None:
    require(value == "unavailable" or SHA64.fullmatch(str(value)) is not None, f"{path} invalid")


def _unavailable_or_sha40(value: Any, path: str) -> None:
    require(value == "unavailable" or SHA40.fullmatch(str(value)) is not None, f"{path} invalid")


def validate_observed_distribution(value: Any) -> dict[str, Any]:
    exact(value, DISTRIBUTION_FIELDS, "$.observed_distribution")
    marketplace = value["marketplace"]
    exact(marketplace, MARKETPLACE_STATE_FIELDS, "$.observed_distribution.marketplace")
    require(marketplace["status"] in {"present", "missing", "unavailable"}, "marketplace state invalid")
    _unavailable_or_sha64(marketplace["source_sha256"], "marketplace source identity")
    _unavailable_or_sha40(marketplace["commit"], "marketplace commit")
    require(isinstance(marketplace["ref"], str) and marketplace["ref"], "marketplace ref invalid")

    plugin = value["plugin"]
    exact(plugin, PLUGIN_STATE_FIELDS, "$.observed_distribution.plugin")
    require(plugin["status"] in {"installed", "missing", "unavailable"}, "plugin state invalid")
    _unavailable_or_sha64(plugin["source_sha256"], "plugin source identity")
    _unavailable_or_sha64(plugin["content_sha256"], "plugin content identity")
    require(isinstance(plugin["ref"], str) and plugin["ref"], "plugin ref invalid")
    require(isinstance(plugin["version"], str) and plugin["version"], "plugin version invalid")
    require(plugin["enabled"] is None or isinstance(plugin["enabled"], bool), "plugin enabled invalid")
    if marketplace["status"] == "missing":
        require(
            marketplace == {
                "status": "missing", "source_sha256": "unavailable",
                "ref": "unavailable", "commit": "unavailable",
            },
            "missing marketplace carries identity",
        )
    if plugin["status"] == "missing":
        require(
            plugin == {
                "status": "missing", "source_sha256": "unavailable", "ref": "unavailable",
                "version": "unavailable", "content_sha256": "unavailable", "enabled": None,
            },
            "missing plugin carries identity",
        )
    return value


def _distribution_is_exact(
    desired: dict[str, Any],
    observed: dict[str, Any],
    *,
    desired_source_sha256: str,
) -> bool:
    marketplace = observed["marketplace"]
    plugin = observed["plugin"]
    return bool(
        marketplace == {
            "status": "present",
            "source_sha256": desired_source_sha256,
            "ref": desired["release_ref"],
            "commit": desired["source_commit"],
        }
        and plugin == {
            "status": "installed",
            "source_sha256": desired_source_sha256,
            "ref": desired["release_ref"],
            "version": desired["plugin_version"],
            "content_sha256": desired["plugin_sha256"],
            "enabled": True,
        }
    )


def build_workstation_reconcile_plan(
    desired_bundle: dict[str, Any],
    observed_distribution: dict[str, Any],
    *,
    desired_source_sha256: str,
    source_plan: dict[str, Any],
    host_materialization: dict[str, Any],
) -> dict[str, Any]:
    desired = validate_desired_bundle(desired_bundle)
    observed = validate_observed_distribution(observed_distribution)
    require(SHA64.fullmatch(desired_source_sha256) is not None, "desired source identity invalid")
    source = validate_source_cutover_plan(source_plan)
    host = _validate_host_materialization(host_materialization)
    changes: list[str] = []
    blockers: list[str] = []
    confirmation_required = False

    marketplace = observed["marketplace"]
    if marketplace["status"] == "unavailable":
        blockers.append("marketplace:unavailable")
    elif marketplace["status"] == "missing":
        changes.append("marketplace:install")
    elif marketplace != {
        "status": "present",
        "source_sha256": desired_source_sha256,
        "ref": desired["release_ref"],
        "commit": desired["source_commit"],
    }:
        changes.append("marketplace:replace")
        confirmation_required = marketplace["source_sha256"] != desired_source_sha256

    plugin = observed["plugin"]
    if plugin["status"] == "unavailable":
        blockers.append("plugin:unavailable")
    elif plugin["status"] == "missing":
        changes.append("plugin:install")
    elif plugin["enabled"] is False:
        blockers.append("plugin:disabled")
    elif plugin != {
        "status": "installed",
        "source_sha256": desired_source_sha256,
        "ref": desired["release_ref"],
        "version": desired["plugin_version"],
        "content_sha256": desired["plugin_sha256"],
        "enabled": True,
    }:
        changes.append("plugin:replace")

    changes.extend(f"source:{item}" for item in source["changes"])
    if not _host_is_exact(
        desired,
        host,
        owner_expected=source["desired"]["canonical_owner"] is not None,
    ):
        changes.append("host:materialize")
    for item in source["changes"]:
        name, action = item.split(":", 1)
        if action != "replace":
            continue
        current_identity = source["current"][name]
        desired_identity = source["desired"][name]
        if (
            not isinstance(current_identity, dict)
            or not isinstance(desired_identity, dict)
            or current_identity.get("remote_sha256") != desired_identity.get("remote_sha256")
        ):
            confirmation_required = True
    status = "distribution_reconcile_blocked" if blockers else ("ready" if changes else "noop")
    if blockers:
        confirmation_required = False
    plan = {
        "contract_version": WORKSTATION_RECONCILE_PLAN_VERSION,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "status": status,
        "desired_bundle": desired,
        "observed_distribution": observed,
        "source_plan_hash": source["plan_hash"],
        "changes": changes,
        "blockers": blockers,
        "confirmation_required": confirmation_required,
        "requires_reload": bool(changes),
        "plan_hash": "",
    }
    plan["plan_hash"] = object_hash(plan, "plan_hash")
    return validate_workstation_reconcile_plan(plan)


def validate_workstation_reconcile_plan(value: Any) -> dict[str, Any]:
    exact(value, RECONCILE_PLAN_FIELDS, "$")
    require(value["contract_version"] == WORKSTATION_RECONCILE_PLAN_VERSION, "reconcile plan contract invalid")
    require(value["bootstrap_version"] == BOOTSTRAP_VERSION, "reconcile plan Bootstrap version invalid")
    require(value["status"] in {"ready", "noop", "distribution_reconcile_blocked"}, "reconcile plan status invalid")
    validate_desired_bundle(value["desired_bundle"])
    validate_observed_distribution(value["observed_distribution"])
    require(SHA64.fullmatch(str(value["source_plan_hash"])) is not None, "reconcile source plan hash invalid")
    require(isinstance(value["changes"], list) and len(value["changes"]) == len(set(value["changes"])), "reconcile changes invalid")
    require(
        all(
            re.fullmatch(
                r"(?:marketplace|plugin):(?:install|replace)|source:(?:sidecar|canonical_owner):(?:install|replace)|host:materialize",
                str(item),
            ) is not None
            for item in value["changes"]
        ),
        "reconcile changes invalid",
    )
    require(
        isinstance(value["blockers"], list)
        and len(value["blockers"]) == len(set(value["blockers"]))
        and all(item in {"marketplace:unavailable", "plugin:unavailable", "plugin:disabled"} for item in value["blockers"]),
        "reconcile blockers invalid",
    )
    require(isinstance(value["confirmation_required"], bool), "reconcile confirmation invalid")
    require(isinstance(value["requires_reload"], bool), "reconcile reload invalid")
    require((value["status"] == "noop") == (not value["changes"] and not value["blockers"]), "reconcile plan status mismatch")
    require((value["status"] == "distribution_reconcile_blocked") == bool(value["blockers"]), "reconcile blocker status mismatch")
    require(not value["blockers"] or not value["confirmation_required"], "blocked reconcile cannot request confirmation")
    require(value["requires_reload"] == bool(value["changes"]), "reconcile reload mismatch")
    require(
        SHA64.fullmatch(str(value["plan_hash"])) is not None
        and value["plan_hash"] == object_hash(value, "plan_hash"),
        "reconcile plan hash invalid",
    )
    return value


def _workstation_reconcile_context(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    desired, sidecar, source_sha256 = load_desired_bundle(
        source_manifest_path, release_manifest_path,
    )
    specs = load_source_manifest(source_manifest_path)
    observed, private_distribution = _observe_distribution_with_private(codex_home)
    source_plan = plan_source_cutover(codex_home, specs)
    if source_plan["status"] == "noop":
        observed_host = observe_host_materialization(
            codex_home,
            specs,
            owner_expected=source_plan["desired"]["canonical_owner"] is not None,
        )
    else:
        observed_host = _unavailable_host_materialization(
            owner_expected=source_plan["desired"]["canonical_owner"] is not None,
        )
    plan = build_workstation_reconcile_plan(
        desired,
        observed,
        desired_source_sha256=source_sha256,
        source_plan=source_plan,
        host_materialization=observed_host,
    )
    return plan, {
        "desired": desired,
        "sidecar": sidecar,
        "source_sha256": source_sha256,
        "specs": specs,
        "source_plan": source_plan,
        "observed": observed,
        "observed_host": observed_host,
        "private_distribution": private_distribution,
    }


def inspect_workstation_reconcile(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
) -> dict[str, Any]:
    plan, _ = _workstation_reconcile_context(
        codex_home, source_manifest_path, release_manifest_path,
    )
    return plan


def legacy_release_reconcile_manifest(source_manifest_path: Path | str) -> Path | None:
    """Recognize the verified Resolver layout consumed by pre-v2 public Anchors."""
    source = Path(source_manifest_path).expanduser().resolve()
    if source.name != "source-manifest.json":
        return None
    release = source.with_name("release-manifest.json")
    resolution = source.with_name("resolution.json")
    portable = source.with_name("portable")
    if release.is_file() and resolution.is_file() and portable.is_dir():
        return release
    return None


def _remove_plugin(codex_home: Path) -> None:
    run_codex_json(
        ["plugin", "remove", "agent-memory-sidecar@agent-memory", "--json"],
        codex_home=codex_home,
    )


def _remove_marketplace(codex_home: Path) -> None:
    run_codex_json(
        ["plugin", "marketplace", "remove", "agent-memory", "--json"],
        codex_home=codex_home,
    )


def _add_marketplace(codex_home: Path, *, remote: str, ref: str) -> None:
    run_codex_json(
        ["plugin", "marketplace", "add", remote, "--ref", ref, "--json"],
        codex_home=codex_home,
    )


def _add_plugin(codex_home: Path) -> None:
    run_codex_json(
        ["plugin", "add", "agent-memory-sidecar@agent-memory", "--json"],
        codex_home=codex_home,
    )


def _restore_distribution(
    codex_home: Path,
    *,
    before: dict[str, Any],
    private_before: dict[str, Any],
    marketplace_touched: bool,
    plugin_touched: bool,
) -> None:
    current, _ = _observe_distribution_with_private(codex_home)
    if plugin_touched and current["plugin"]["status"] == "installed":
        _remove_plugin(codex_home)
    if marketplace_touched and current["marketplace"]["status"] == "present":
        _remove_marketplace(codex_home)
    if marketplace_touched and private_before["marketplace"]["present"]:
        remote = private_before["marketplace"]["remote"]
        ref = private_before["marketplace"]["ref"]
        require(isinstance(remote, str) and isinstance(ref, str), "distribution_rollback_snapshot_invalid")
        _add_marketplace(codex_home, remote=remote, ref=ref)
    if plugin_touched and private_before["plugin"]["installed"]:
        require(private_before["plugin"]["enabled"] is True, "distribution_rollback_disabled_plugin_unsupported")
        _add_plugin(codex_home)
    restored = observe_distribution(codex_home)
    require(restored == before, "distribution_rollback_verification_failed")


def _apply_distribution_changes(
    codex_home: Path,
    *,
    plan: dict[str, Any],
    sidecar: SourceSpec,
) -> tuple[bool, bool]:
    marketplace_touched = any(item.startswith("marketplace:") for item in plan["changes"])
    plugin_touched = marketplace_touched or any(item.startswith("plugin:") for item in plan["changes"])
    before = plan["observed_distribution"]
    if plugin_touched and before["plugin"]["status"] == "installed":
        _remove_plugin(codex_home)
    if marketplace_touched and before["marketplace"]["status"] == "present":
        _remove_marketplace(codex_home)
    if marketplace_touched:
        _add_marketplace(codex_home, remote=sidecar.remote, ref=sidecar.ref)
    if plugin_touched:
        _add_plugin(codex_home)
    return marketplace_touched, plugin_touched


def apply_workstation_reconcile(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    *,
    plan_hash: str,
) -> dict[str, Any]:
    require(SHA64.fullmatch(plan_hash.casefold()) is not None, "reconcile_plan_hash_invalid")
    plan, context = _workstation_reconcile_context(
        codex_home, source_manifest_path, release_manifest_path,
    )
    require(plan["plan_hash"] == plan_hash.casefold(), "reconcile_plan_stale")
    require(plan["status"] != "distribution_reconcile_blocked", "distribution_reconcile_blocked")
    before = context["observed"]
    private_before = context["private_distribution"]
    marketplace_touched = any(item.startswith("marketplace:") for item in plan["changes"])
    plugin_touched = marketplace_touched or any(item.startswith("plugin:") for item in plan["changes"])
    pack_holder: dict[str, Any] = {}

    def apply_distribution() -> None:
        _apply_distribution_changes(codex_home, plan=plan, sidecar=context["sidecar"])

    def rollback_distribution() -> None:
        _restore_distribution(
            codex_home,
            before=before,
            private_before=private_before,
            marketplace_touched=marketplace_touched,
            plugin_touched=plugin_touched,
        )

    def verify_and_build_pack(source_receipt: dict[str, Any]) -> None:
        observed_after = observe_distribution(codex_home)
        require(
            _distribution_is_exact(
                context["desired"],
                observed_after,
                desired_source_sha256=context["source_sha256"],
            ),
            "distribution_readback_mismatch",
        )
        materialization = observe_host_materialization(
            codex_home,
            context["specs"],
            owner_expected=source_receipt["sources"]["canonical_owner"]["status"] != "unavailable",
        )
        require(
            _host_is_exact(
                context["desired"],
                materialization,
                owner_expected=source_receipt["sources"]["canonical_owner"]["status"] != "unavailable",
            ),
            "host_materialization_readback_mismatch",
        )
        source_receipt["materialization"] = materialization
        effective_reload = bool(
            plan["requires_reload"]
            or materialization["bootstrap_skill"]["status"] == "installed"
            or materialization["scout_skill"]["status"] == "installed"
        )
        pack_holder["value"] = build_deployment_pack(
            desired=context["desired"],
            observed_distribution=observed_after,
            desired_source_sha256=context["source_sha256"],
            source_sync=source_receipt["sources"],
            host_materialization=source_receipt["materialization"],
            requires_reload=effective_reload,
            consumer_verified=False,
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    apply_source_cutover(
        codex_home,
        context["specs"],
        plan_hash=context["source_plan"]["plan_hash"],
        external_apply=apply_distribution if (marketplace_touched or plugin_touched) else None,
        external_rollback=rollback_distribution if (marketplace_touched or plugin_touched) else None,
        precommit_verify=verify_and_build_pack,
    )
    require("value" in pack_holder, "deployment_pack_not_built")
    return {
        "contract_version": WORKSTATION_RECONCILE_RECEIPT_VERSION,
        "status": "applied",
        "plan_hash": plan["plan_hash"],
        "deployment_pack": pack_holder["value"],
    }


def _source_sync_from_exact_plan(source_plan: dict[str, Any]) -> dict[str, Any]:
    source = validate_source_cutover_plan(source_plan)
    require(source["status"] == "noop", "source_sync_requires_exact_plan")
    desired = source["desired"]
    sidecar = desired["sidecar"]
    owner = desired["canonical_owner"]
    receipts = {
        "sidecar": {
            "status": "unchanged", "ref": sidecar["ref"], "commit": sidecar["commit"],
        },
        "canonical_owner": (
            {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"}
            if owner is None
            else {"status": "unchanged", "ref": owner["ref"], "commit": owner["commit"]}
        ),
    }
    return _validate_source_sync(receipts)


def verify_workstation_consumer(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    desktop_project_inventory_path: Path | str,
) -> dict[str, Any]:
    plan, context = _workstation_reconcile_context(
        codex_home, source_manifest_path, release_manifest_path,
    )
    require(plan["status"] == "noop", "consumer_verification_requires_exact_host")
    inventory = _load_json_file(
        Path(desktop_project_inventory_path), "desktop_project_inventory_unreadable",
    )
    consumer_scope = observe_consumer_scope(inventory, desired=context["desired"])
    return build_deployment_pack(
        desired=context["desired"],
        observed_distribution=context["observed"],
        desired_source_sha256=context["source_sha256"],
        source_sync=_source_sync_from_exact_plan(context["source_plan"]),
        host_materialization=context["observed_host"],
        requires_reload=False,
        consumer_verified=True,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        consumer_scope=consumer_scope,
    )


def _validate_source_sync(value: Any) -> dict[str, Any]:
    exact(value, SOURCE_SYNC_FIELDS, "$.source_sync")
    for name in SOURCE_SYNC_FIELDS:
        receipt = value[name]
        exact(receipt, SOURCE_RECEIPT_FIELDS, f"$.source_sync.{name}")
        require(receipt["status"] in {"synced", "unchanged", "unavailable", "failed"}, f"source {name} status invalid")
        safe_text(receipt["ref"], f"$.source_sync.{name}.ref", 128)
        _unavailable_or_sha40(receipt["commit"], f"source {name} commit")
    return value


def _validate_host_materialization(value: Any) -> dict[str, Any]:
    exact(value, MATERIALIZATION_FIELDS, "$.host_materialization")
    core = value["core"]
    exact(core, CORE_STATE_FIELDS, "$.host_materialization.core")
    require(core["status"] in {"verified", "failed", "unavailable"}, "Core materialization status invalid")
    require(
        core["version"] == "unavailable" or SEMVER.fullmatch(str(core["version"])) is not None,
        "Core materialization version invalid",
    )
    _unavailable_or_sha40(core["source_commit"], "Core materialization source commit")
    _unavailable_or_sha64(core["artifact_sha256"], "Core artifact identity")
    require(value["global_binding"] in {"verified", "unavailable", "failed"}, "global binding state invalid")
    require(value["doctor"] in {"verified", "failed"}, "Doctor state invalid")
    for name in ("bootstrap_skill", "scout_skill"):
        skill = value[name]
        exact(skill, SKILL_STATE_FIELDS, f"$.host_materialization.{name}")
        require(skill["status"] in {"installed", "unchanged", "failed", "unavailable"}, f"{name} state invalid")
        require(
            skill["version"] == "unavailable" or SEMVER.fullmatch(str(skill["version"])) is not None,
            f"{name} version invalid",
        )
        _unavailable_or_sha64(skill["content_sha256"], f"{name} content identity")
    return value


def _host_is_exact(
    desired: dict[str, Any],
    material: dict[str, Any],
    *,
    owner_expected: bool,
) -> bool:
    expected_binding = "verified" if owner_expected else "unavailable"
    return bool(
        material["core"]["status"] == "verified"
        and material["core"]["version"] == desired["core_version"]
        and material["core"]["source_commit"] == desired["source_commit"]
        and material["global_binding"] == expected_binding
        and material["doctor"] == "verified"
        and material["bootstrap_skill"]["status"] in {"installed", "unchanged"}
        and material["bootstrap_skill"]["version"] == desired["bootstrap_version"]
        and material["bootstrap_skill"]["content_sha256"] == desired["bootstrap_sha256"]
        and material["scout_skill"]["status"] in {"installed", "unchanged"}
        and material["scout_skill"]["version"] == desired["scout_version"]
        and material["scout_skill"]["content_sha256"] == desired["scout_sha256"]
    )


def build_deployment_pack(
    *,
    desired: dict[str, Any],
    observed_distribution: dict[str, Any],
    desired_source_sha256: str,
    source_sync: dict[str, Any],
    host_materialization: dict[str, Any],
    requires_reload: bool,
    consumer_verified: bool,
    generated_at: str,
    consumer_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    desired = validate_desired_bundle(desired)
    observed = validate_observed_distribution(observed_distribution)
    require(SHA64.fullmatch(desired_source_sha256) is not None, "desired source identity invalid")
    source_sync = _validate_source_sync(source_sync)
    material = _validate_host_materialization(host_materialization)
    scope = validate_consumer_scope(
        _not_observed_consumer_scope() if consumer_scope is None else consumer_scope
    )
    distribution_exact = _distribution_is_exact(
        desired, observed, desired_source_sha256=desired_source_sha256,
    )
    source_exact = (
        source_sync["sidecar"]["status"] in {"synced", "unchanged"}
        and source_sync["sidecar"]["ref"] == desired["release_ref"]
        and source_sync["sidecar"]["commit"] == desired["source_commit"]
        and source_sync["canonical_owner"]["status"] in {"synced", "unchanged", "unavailable"}
    )
    host_exact = _host_is_exact(
        desired,
        material,
        owner_expected=source_sync["canonical_owner"]["status"] != "unavailable",
    )
    if not distribution_exact:
        status = "distribution_reconcile_blocked"
    elif not source_exact:
        status = "source_sync_blocked"
    elif not host_exact:
        status = "host_materialization_blocked"
    elif requires_reload or not consumer_verified:
        status = "reload_required"
    elif scope["status"] == "drifted":
        status = "consumer_scope_drift"
    elif scope["status"] != "exact":
        status = "consumer_scope_bounded"
    else:
        status = "ready"
    blocked = status in {
        "distribution_reconcile_blocked", "source_sync_blocked", "host_materialization_blocked",
    }
    activation_pending = not blocked and (requires_reload or not consumer_verified)
    if blocked:
        interactive_entry = "blocked"
    elif activation_pending:
        interactive_entry = "available_next_task"
    elif status == "consumer_scope_drift":
        interactive_entry = "ambiguous"
    elif status == "consumer_scope_bounded":
        interactive_entry = "unproven"
    else:
        interactive_entry = "verified"
    limitations = ["真实第二台设备的首次部署与项目续接仍需独立验收。"]
    if not consumer_verified and not blocked:
        limitations.insert(0, "当前任务未证明新版本已被模型加载；需在一次 Desktop 刷新后的新任务中验收。")
    limitations = [*scope["limitations"], *limitations]
    pack = {
        "contract_version": PACK_VERSION,
        "status": status,
        "display_locale": "zh-CN",
        "generated_at": generated_at,
        "desired_bundle": desired,
        "distribution": observed,
        "source_sync": source_sync,
        "host_materialization": material,
        "consumer_scope": scope,
        "consumer_activation": {
            "desktop_reload": "required" if activation_pending else "not_required",
            "interactive_entry": interactive_entry,
            "scheduled": "unchanged",
        },
        "limitations": limitations,
        "pack_hash": "",
    }
    pack["pack_hash"] = object_hash(pack, "pack_hash")
    return validate_pack(pack)


def validate_pack(value: Any) -> dict[str, Any]:
    exact(value, PACK_FIELDS, "$")
    require(value["contract_version"] == PACK_VERSION, "deployment pack contract invalid")
    require(value["display_locale"] == "zh-CN", "deployment pack locale invalid")
    require(
        value["status"] in {
            "ready", "reload_required", "distribution_reconcile_blocked",
            "source_sync_blocked", "host_materialization_blocked",
            "consumer_scope_drift", "consumer_scope_bounded",
        },
        "deployment pack status invalid",
    )
    safe_text(value["generated_at"], "$.generated_at", 80)
    validate_desired_bundle(value["desired_bundle"])
    validate_observed_distribution(value["distribution"])
    _validate_source_sync(value["source_sync"])
    _validate_host_materialization(value["host_materialization"])
    validate_consumer_scope(value["consumer_scope"])
    activation = value["consumer_activation"]
    exact(activation, ACTIVATION_FIELDS, "$.consumer_activation")
    require(activation["desktop_reload"] in {"required", "not_required"}, "Desktop reload state invalid")
    require(activation["interactive_entry"] in {"available_next_task", "verified", "ambiguous", "unproven", "blocked"}, "interactive activation invalid")
    require(activation["scheduled"] == "unchanged", "Scheduled activation invalid")
    if value["status"] == "reload_required":
        require(activation["desktop_reload"] == "required", "reload-required pack must require Desktop reload")
        require(activation["interactive_entry"] == "available_next_task", "reload-required pack must expose next-task entry")
    if value["status"] == "ready":
        require(activation["desktop_reload"] == "not_required", "ready pack cannot require Desktop reload")
        require(activation["interactive_entry"] == "verified", "ready pack requires verified interactive entry")
        require(value["consumer_scope"]["status"] == "exact", "ready pack requires exact consumer scope")
    if value["status"] == "consumer_scope_drift":
        require(activation["desktop_reload"] == "not_required", "consumer drift cannot request Desktop reload")
        require(activation["interactive_entry"] == "ambiguous", "consumer drift must expose ambiguous entry")
        require(value["consumer_scope"]["status"] == "drifted", "consumer drift pack requires drift evidence")
    if value["status"] == "consumer_scope_bounded":
        require(activation["desktop_reload"] == "not_required", "bounded consumer scope cannot request Desktop reload")
        require(activation["interactive_entry"] == "unproven", "bounded consumer scope must remain unproven")
        require(value["consumer_scope"]["status"] == "bounded", "bounded pack requires bounded scope")
    if value["status"].endswith("_blocked"):
        require(activation["desktop_reload"] == "not_required", "blocked pack cannot request Desktop reload")
        require(activation["interactive_entry"] == "blocked", "blocked pack must block interactive entry")
    require(isinstance(value["limitations"], list), "$.limitations must be a list")
    for index, item in enumerate(value["limitations"]):
        safe_text(item, f"$.limitations[{index}]", 300)
    require(value["pack_hash"] == object_hash(value, "pack_hash"), "deployment pack hash mismatch")
    return value


def validate_marketplace(
    value: Any,
    *,
    require_immutable: bool = False,
    expected_remote: str | None = None,
) -> dict[str, Any]:
    exact(value, MARKETPLACE_FIELDS, "$")
    require(value["name"] == "agent-memory", "marketplace name invalid")
    require(value["interface"] == {"displayName": "Agent Memory"}, "marketplace interface invalid")
    require(isinstance(value["plugins"], list) and len(value["plugins"]) == 1, "marketplace plugin count invalid")
    entry = value["plugins"][0]
    exact(entry, {"name", "source", "policy", "category"}, "$.plugins[0]")
    require(entry["name"] == "agent-memory-sidecar", "marketplace plugin name invalid")
    require(entry["category"] == "Productivity", "marketplace category invalid")
    require(entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "marketplace policy invalid")
    source = entry["source"]
    exact(source, {"source", "url", "path", "ref"}, "$.plugins[0].source")
    require(source["source"] == "git-subdir", "marketplace source kind invalid")
    remote = str(source["url"]).strip()
    ref = str(source["ref"]).strip().casefold()
    normalize_remote(remote)
    if expected_remote is not None:
        require(normalize_remote(remote) == normalize_remote(expected_remote), "marketplace source identity invalid")
    require(source["path"] == "./plugins/agent-memory-sidecar", "marketplace plugin path invalid")
    require(
        SAFE_REF.fullmatch(ref) is not None
        and ".." not in ref
        and "//" not in ref
        and "@{" not in ref
        and not ref.endswith(("/", ".", ".lock")),
        "marketplace ref invalid",
    )
    if require_immutable:
        require(SHA40.fullmatch(ref) is not None, "marketplace immutable ref required")
    return value


def _markdown_table_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")


def render_pack(value: Any) -> str:
    pack = validate_pack(value)
    status = {
        "ready": "本机托管能力、新任务入口与 Desktop 项目消费者范围已对齐",
        "reload_required": "能力已对齐到磁盘，需一次 Desktop 刷新后在新任务验收",
        "consumer_scope_drift": "托管能力已对齐，但 Desktop 可见项目存在不同版本或内容的同名 Skill",
        "consumer_scope_bounded": "托管能力已对齐，但 Desktop 项目消费者范围尚未完整观察",
        "distribution_reconcile_blocked": "Plugin 或 Marketplace 尚未精确对齐",
        "source_sync_blocked": "远端能力源同步受阻",
        "host_materialization_blocked": "本机能力物化受阻",
    }[pack["status"]]
    desired = pack["desired_bundle"]
    distribution = pack["distribution"]
    sources = pack["source_sync"]
    material = pack["host_materialization"]
    scope = pack["consumer_scope"]
    activation = pack["consumer_activation"]
    lines = [
        "# Agent Memory 本机部署结果",
        "",
        f"> **{status}**。本次没有创建或恢复 Scheduled Task，也没有修改任何项目 Owner。",
        "",
        "| 能力层 | 结果 | 说明 |",
        "|---|---|---|",
        f"| 期望发行身份 | Core `{desired['core_version']}` / Plugin `{desired['plugin_version']}` | Release `{desired['release_ref']}` / `{desired['source_commit'][:12]}` |",
        f"| Plugin 分发 | Marketplace `{distribution['marketplace']['status']}` / Plugin `{distribution['plugin']['status']}` | Ref `{distribution['plugin']['ref']}` / enabled `{str(distribution['plugin']['enabled']).lower()}` |",
        f"| 能力源同步 | Sidecar `{sources['sidecar']['status']}` / Global Owner `{sources['canonical_owner']['status']}` | 只更新本机受管缓存，不清理活跃工程 |",
        f"| 主机物化 | Core `{material['core']['status']}` / Doctor `{material['doctor']}` / Scout `{material['scout_skill']['status']}` | Bootstrap {material['bootstrap_skill']['version']}；Scout {material['scout_skill']['version']} |",
        f"| 项目消费者范围 | `{scope['status']}` | Desktop 项目 {scope['desktop_project_count']}；已读 {scope['scanned_project_count']}；同名 Skill {scope['matching_skill_count']} |",
        f"| 消费者采用 | Desktop 刷新 `{activation['desktop_reload']}` / 交互入口 `{activation['interactive_entry']}` | Scheduled `{activation['scheduled']}`，项目集合仍由当前主机和用户决定 |",
    ]
    if scope["projects"]:
        lines.extend(["", "## Desktop 可见项目级同名 Skill", "", "| 项目 | Skill | 版本 | 关系 |", "|---|---|---|---|"])
        for project in scope["projects"]:
            display_name = _markdown_table_text(project["display_name"])
            if not project["skills"]:
                lines.append(f"| {display_name} | 无法完整读取 | unavailable | `{project['status']}` |")
            for skill in project["skills"]:
                lines.append(
                    f"| {display_name} | `{skill['name']}@scope-{skill['scope_level']}` | `{skill['version']}` | `{skill['relation']}` |"
                )
    if pack["limitations"]:
        lines.extend(["", "## 尚未证明", ""])
        lines.extend(f"> {item}" for item in pack["limitations"])
    next_step = {
        "reload_required": "下一步：刷新一次 Codex Desktop，并在新任务中再次发送“同步并部署本机 Agent Memory”完成采用验收。",
        "ready": "下一步：可在目标工程的新任务中发送 `$global-owner-scout 复盘当前项目`。",
        "consumer_scope_drift": "下一步：先判断上表项目级同名 Skill 是待发布开发版本还是陈旧副本；更新或移除该项目来源后重新验收。调和器不会自动修改 checkout。",
        "consumer_scope_bounded": "下一步：恢复完整 Desktop 项目枚举与只读访问后，在新任务重新执行同一句部署入口。",
        "distribution_reconcile_blocked": "下一步：处理上表显示的 Plugin/Marketplace 唯一阻断后，再发送“同步并部署本机 Agent Memory”。",
        "source_sync_blocked": "下一步：恢复期望来源的只读访问或消除来源歧义后，再发送“同步并部署本机 Agent Memory”。",
        "host_materialization_blocked": "下一步：保留当前失败现场并重试同一句部署入口；不得手工跳过 Core、Doctor 或 Skill 步骤。",
    }[pack["status"]]
    lines.extend([
        "",
        next_step,
        "",
        f"校验回执：`{PACK_VERSION}`｜Pack `{pack['pack_hash'][:12]}`",
    ])
    return "\n".join(lines) + "\n"


def render_workstation_reconcile_plan(value: Any) -> str:
    plan = validate_workstation_reconcile_plan(value)
    if plan["blockers"]:
        blocker_labels = {
            "marketplace:unavailable": "Marketplace 状态无法可靠读取",
            "plugin:unavailable": "Plugin 状态无法可靠读取",
            "plugin:disabled": "Plugin 已由用户显式停用，调和不会静默改写该选择",
        }
        items = [f"- 阻断：{blocker_labels[item]}" for item in plan["blockers"]]
        return "\n".join(["## 本机 Agent Memory 调和受阻", "", *items, "", "未执行任何部署变更。", ""])
    labels = {
        "marketplace:install": "安装受发行身份固定的 Marketplace",
        "marketplace:replace": "将 Marketplace 更新到期望发行身份",
        "plugin:install": "安装 Agent Memory Plugin",
        "plugin:replace": "将 Agent Memory Plugin 更新到期望版本和内容",
        "host:materialize": "修复并复核 Core、Owner、Doctor、Bootstrap 与 Scout",
    }
    rendered_changes: list[str] = []
    for item in plan["changes"]:
        rendered_changes.append(
            "同步并物化受管能力源" if item.startswith("source:") else labels[item]
        )
    if not rendered_changes:
        rendered_changes = ["所有受管分发面身份一致；只进行确定性复核"]
    confirmation = (
        "检测到既有来源身份变化，需要一次明确确认后才能执行 exact-hash apply。"
        if plan["confirmation_required"]
        else "当前部署请求已覆盖这些同身份安装或更新动作。"
    )
    return "\n".join([
        "## 本机 Agent Memory 统一调和计划",
        "",
        *[f"- {item}" for item in dict.fromkeys(rendered_changes)],
        f"- 授权：{confirmation}",
        f"- 平台边界：{'执行后需要一次 Desktop 刷新。' if plan['requires_reload'] else '无需额外刷新。'}",
        "",
    ])


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


def self_test() -> None:
    desired = {
        "release_ref": "v0.3.8", "source_commit": "a" * 40,
        "core_version": "0.3.8", "plugin_version": "1.5.0", "plugin_sha256": "b" * 64,
        "bootstrap_version": BOOTSTRAP_VERSION, "bootstrap_sha256": "c" * 64,
        "scout_version": SCOUT_VERSION, "scout_sha256": "d" * 64,
    }
    source_identity_hash = "e" * 64
    pack = build_deployment_pack(
        desired=desired,
        observed_distribution={
            "marketplace": {
                "status": "present", "source_sha256": source_identity_hash,
                "ref": "v0.3.8", "commit": "a" * 40,
            },
            "plugin": {
                "status": "installed", "source_sha256": source_identity_hash,
                "ref": "v0.3.8", "version": "1.5.0",
                "content_sha256": "b" * 64, "enabled": True,
            },
        },
        desired_source_sha256=source_identity_hash,
        source_sync={
            "sidecar": {"status": "unchanged", "ref": "v0.3.8", "commit": "a" * 40},
            "canonical_owner": {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"},
        },
        host_materialization={
            "core": {
                "status": "verified", "version": "0.3.8",
                "source_commit": "a" * 40, "artifact_sha256": "f" * 64,
            },
            "global_binding": "unavailable", "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged", "version": BOOTSTRAP_VERSION, "content_sha256": "c" * 64,
            },
            "scout_skill": {
                "status": "unchanged", "version": SCOUT_VERSION, "content_sha256": "d" * 64,
            },
        },
        requires_reload=True,
        consumer_verified=False,
        generated_at="2026-08-21T12:00:00+08:00",
    )
    require("真实第二台设备" in render_pack(pack), "deployment renderer lost proof boundary")
    marketplace = {
        "name": "agent-memory", "interface": {"displayName": "Agent Memory"},
        "plugins": [{
            "name": "agent-memory-sidecar",
            "source": {"source": "git-subdir", "url": "https://github.com/example/agent-memory-sidecar.git", "path": "./plugins/agent-memory-sidecar", "ref": "main"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }],
    }
    validate_marketplace(marketplace)
    marketplace["plugins"][0]["source"]["ref"] = "a" * 40
    validate_marketplace(
        marketplace,
        require_immutable=True,
        expected_remote="https://github.com/example/agent-memory-sidecar.git",
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = create_remote(root, "sidecar")
        second = create_remote(root, "owner")
        first_commit = run_git(["rev-parse", "HEAD"], cwd=root / "sidecar-work")
        second_commit = run_git(["rev-parse", "HEAD"], cwd=root / "owner-work")
        release_manifest = {
            "contract_version": SOURCE_MANIFEST_VERSION,
            "distribution": "release",
            "sidecar": {"remote": str(first), "ref": "main", "commit": first_commit},
            "canonical_owner": {"remote": str(second), "ref": "main", "commit": second_commit},
        }
        specs = validate_source_manifest(release_manifest)
        receipt = sync_sources(root / "codex-home", specs)
        require({item["status"] for item in receipt["sources"].values()} == {"synced"}, "first sync did not install both sources")
        again = sync_sources(root / "codex-home", specs)
        require({item["status"] for item in again["sources"].values()} == {"unchanged"}, "second sync was not idempotent")
        public_manifest = dict(release_manifest)
        public_manifest["canonical_owner"] = None
        public_specs = validate_source_manifest(public_manifest)
        require([item.name for item in public_specs] == ["sidecar"], "public manifest retained a private Owner")
        wrong = json.loads(json.dumps(public_manifest))
        wrong["sidecar"]["commit"] = "f" * 40
        try:
            sync_sources(root / "other-home", validate_source_manifest(wrong))
        except BootstrapError as exc:
            require(str(exc) == "managed_source_commit_mismatch", "wrong commit did not fail closed")
        else:
            raise BootstrapError("wrong commit was accepted")
        new_sidecar = create_remote(root, "public-sidecar")
        new_commit = run_git(["rev-parse", "HEAD"], cwd=root / "public-sidecar-work")
        cutover_manifest = json.loads(json.dumps(release_manifest))
        cutover_manifest["sidecar"] = {
            "remote": str(new_sidecar), "ref": "main", "commit": new_commit,
        }
        cutover_plan = plan_source_cutover(root / "codex-home", validate_source_manifest(cutover_manifest))
        require(cutover_plan["owner_action"] == "keep_owner", "cutover lost Owner boundary")
        require("sidecar:replace" in cutover_plan["changes"], "cutover did not detect source identity change")
    print(json.dumps({"status": "ok", "tests": 11}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync-sources")
    sync.add_argument("--codex-home", required=True)
    sync.add_argument("--source-manifest", required=True)
    materialize = sub.add_parser("materialize-host")
    materialize.add_argument("--codex-home", required=True)
    materialize.add_argument("--source-manifest", required=True)
    cutover = sub.add_parser("source-cutover")
    cutover.add_argument("--codex-home", required=True)
    cutover.add_argument("--source-manifest", required=True)
    cutover_mode = cutover.add_mutually_exclusive_group(required=True)
    cutover_mode.add_argument("--dry-run", action="store_true")
    cutover_mode.add_argument("--apply", action="store_true")
    cutover.add_argument("--plan-hash")
    reconcile = sub.add_parser("workstation-reconcile")
    reconcile.add_argument("--codex-home", required=True)
    reconcile.add_argument("--source-manifest", required=True)
    reconcile.add_argument("--release-manifest", required=True)
    reconcile_mode = reconcile.add_mutually_exclusive_group(required=True)
    reconcile_mode.add_argument("--dry-run", action="store_true")
    reconcile_mode.add_argument("--apply", action="store_true")
    reconcile_mode.add_argument("--verify-consumer", action="store_true")
    reconcile.add_argument("--plan-hash")
    reconcile.add_argument("--desktop-project-inventory")
    validate_source = sub.add_parser("validate-source-manifest")
    validate_source.add_argument("--path", required=True)
    sub.add_parser("validate-pack")
    sub.add_parser("render-pack")
    sub.add_parser("render-cutover-plan")
    sub.add_parser("render-reconcile-plan")
    observe = sub.add_parser("observe-distribution")
    observe.add_argument("--codex-home", required=True)
    sub.add_parser("validate-marketplace")
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "sync-sources":
            specs = load_source_manifest(args.source_manifest)
            print(json.dumps(sync_sources(Path(args.codex_home), specs), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "materialize-host":
            specs = load_source_manifest(args.source_manifest)
            print(json.dumps(materialize_host(Path(args.codex_home), specs), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "source-cutover":
            legacy_release = legacy_release_reconcile_manifest(args.source_manifest)
            if legacy_release is not None:
                if args.dry_run:
                    require(args.plan_hash is None, "source_cutover_plan_hash_unexpected")
                    result = inspect_workstation_reconcile(
                        Path(args.codex_home), args.source_manifest, legacy_release,
                    )
                else:
                    require(args.plan_hash is not None, "source_cutover_plan_hash_required")
                    result = apply_workstation_reconcile(
                        Path(args.codex_home), args.source_manifest, legacy_release,
                        plan_hash=args.plan_hash,
                    )
            else:
                specs = load_source_manifest(args.source_manifest)
                if args.dry_run:
                    require(args.plan_hash is None, "source_cutover_plan_hash_unexpected")
                    result = plan_source_cutover(Path(args.codex_home), specs)
                else:
                    require(args.plan_hash is not None, "source_cutover_plan_hash_required")
                    result = apply_source_cutover(
                        Path(args.codex_home), specs, plan_hash=args.plan_hash,
                    )
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif args.command == "workstation-reconcile":
            if args.dry_run:
                require(args.plan_hash is None, "reconcile_plan_hash_unexpected")
                require(args.desktop_project_inventory is None, "desktop_project_inventory_unexpected")
                result = inspect_workstation_reconcile(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                )
            elif args.apply:
                require(args.plan_hash is not None, "reconcile_plan_hash_required")
                require(args.desktop_project_inventory is None, "desktop_project_inventory_unexpected")
                result = apply_workstation_reconcile(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                    plan_hash=args.plan_hash,
                )
            else:
                require(args.plan_hash is None, "reconcile_plan_hash_unexpected")
                require(args.desktop_project_inventory is not None, "desktop_project_inventory_required")
                result = verify_workstation_consumer(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                    args.desktop_project_inventory,
                )
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif args.command == "validate-source-manifest":
            specs = load_source_manifest(args.path)
            print(json.dumps({"status": "ok", "sources": [item.name for item in specs]}, separators=(",", ":")))
        elif args.command == "validate-pack":
            pack = validate_pack(json.load(sys.stdin))
            print(json.dumps({"status": "ok", "contract_version": pack["contract_version"]}, separators=(",", ":")))
        elif args.command == "render-pack":
            sys.stdout.write(render_pack(json.load(sys.stdin)))
        elif args.command == "render-cutover-plan":
            plan = json.load(sys.stdin)
            if plan.get("contract_version") == WORKSTATION_RECONCILE_PLAN_VERSION:
                sys.stdout.write(render_workstation_reconcile_plan(plan))
            else:
                sys.stdout.write(render_source_cutover_plan(plan))
        elif args.command == "render-reconcile-plan":
            sys.stdout.write(render_workstation_reconcile_plan(json.load(sys.stdin)))
        elif args.command == "observe-distribution":
            print(json.dumps(observe_distribution(Path(args.codex_home)), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "validate-marketplace":
            validate_marketplace(json.load(sys.stdin))
            print(json.dumps({"status": "ok", "contract": "agent-memory-marketplace-v1"}, separators=(",", ":")))
        else:
            self_test()
        return 0
    except (BootstrapError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
