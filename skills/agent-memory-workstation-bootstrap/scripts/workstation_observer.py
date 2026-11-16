#!/usr/bin/env python3
"""Host, plugin distribution, consumer scope, and release bundle observation for Bootstrap."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from typing import Any
import zipfile

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from bootstrap_contracts import (
    BOOTSTRAP_VERSION,
    CONSUMER_SKILLS,
    CONSUMER_SKILL_MAX_BYTES,
    CONSUMER_SKILL_MAX_ENTRIES,
    DESKTOP_PROJECT_INPUT_FIELDS,
    DESKTOP_PROJECT_INVENTORY_FIELDS,
    DESKTOP_PROJECT_INVENTORY_VERSION,
    DESKTOP_PROJECT_MAX_COUNT,
    MANAGED_REVIEW_SKILL,
    NATIVE_SKILLS_MAX_BYTES,
    NATIVE_SKILLS_TIMEOUT_SECONDS,
    PUBLIC_REPOSITORY,
    RELEASE_ASSET_FIELDS,
    RELEASE_MANIFEST_FIELDS,
    RELEASE_MANIFEST_VERSION,
    RELEASE_RESOLUTION_FIELDS,
    RELEASE_RESOLUTION_VERSION,
    RELEASE_SOURCE_FIELDS,
    RELEASE_VERSION_FIELDS,
    REVIEW_DISABLED_NOTICE,
    REVIEW_SKILL,
    SCOUT_VERSION,
    SEMVER,
    SHA40,
    SHA64,
    SourceSpec,
    _consumer_capability,
    _load_json_file,
    _physical_file_bytes,
    _validate_host_materialization,
    canonical,
    exact,
    load_source_manifest,
    normalize_remote,
    require,
    safe_text,
    validate_consumer_scope,
    validate_desired_bundle,
    validate_marketplace,
    validate_observed_distribution,
)
from bootstrap_security import (
    BootstrapError,
    is_reparse,
    read_global_instruction_binding,
    validate_physical_directory_chain,
)
from source_cutover import (
    _codex_home_root,
    _current_owner_root,
    _installed_skill_root,
    _managed_source_root,
    _preserved_owner_identity,
    bounded_physical_tree_hash,
    inspect_checkout,
    inspect_existing_checkout,
    inspect_marketplace_checkout,
    physical_tree_hash,
)


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
) -> tuple[dict[str, Any], SourceSpec, str, str]:
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
    return desired, sidecar, source_sha256, assets[portable_name]["sha256"]


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
    *,
    facade: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    codex_home = _codex_home_root(codex_home, create=False)
    codex_json_fn = getattr(facade, "run_codex_json", run_codex_json)
    private: dict[str, Any] = {
        "marketplace": {"present": False, "remote": None, "ref": None},
        "plugin": {"installed": False, "enabled": None},
    }
    try:
        marketplace_payload = codex_json_fn(
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
            inspect_marketplace_fn = getattr(
                facade, "inspect_marketplace_checkout", inspect_marketplace_checkout,
            )
            root = Path(root_text).expanduser().resolve()
            checkout = inspect_marketplace_fn(root)
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
        plugin_payload = codex_json_fn(
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


def observe_distribution(codex_home: Path, *, facade: Any = None) -> dict[str, Any]:
    observed, _ = _observe_distribution_with_private(codex_home, facade=facade)
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


def native_skill_catalog(
    codex_home: Path,
    project_roots: list[Path],
    *,
    timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Ask the native discovery owner; never start a task or change enablement."""
    timeout = NATIVE_SKILLS_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    executable = shutil.which("codex")
    require(executable is not None, "codex_cli_unavailable")
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    messages: queue.Queue = queue.Queue()
    with subprocess.Popen(
        [executable, "app-server", "--stdio"], cwd=codex_home, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    ) as process:
        def read_messages() -> None:
            try:
                total = 0
                while True:
                    line = process.stdout.readline(NATIVE_SKILLS_MAX_BYTES + 1)
                    if not line:
                        break
                    total += len(line)
                    if total > NATIVE_SKILLS_MAX_BYTES:
                        break
                    messages.put(json.loads(line))
            except (OSError, ValueError):
                pass
            finally:
                messages.put(None)

        reader = threading.Thread(target=read_messages, daemon=True)
        reader.start()

        def stop_process_tree() -> None:
            if process.poll() is not None:
                return
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        watchdog = threading.Timer(timeout, stop_process_tree)
        watchdog.daemon = True
        watchdog.start()
        deadline = time.monotonic() + timeout

        def send(message: dict[str, Any]) -> None:
            process.stdin.write(canonical(message) + b"\n")
            process.stdin.flush()

        def receive(identifier: int) -> dict[str, Any]:
            while True:
                try:
                    message = messages.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty as exc:
                    raise BootstrapError("native_skills_timeout") from exc
                require(isinstance(message, dict), "native_skills_output_invalid")
                if message.get("id") == identifier:
                    require("error" not in message and isinstance(message.get("result"), dict), "native_skills_failed")
                    return message["result"]

        try:
            send({"id": 1, "method": "initialize", "params": {
                "clientInfo": {"name": "agent_memory_bootstrap", "version": BOOTSTRAP_VERSION},
            }})
            receive(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "skills/list", "params": {
                "cwds": [str(path) for path in project_roots], "forceReload": True,
            }})
            result = receive(2)
            require(isinstance(result.get("data"), list), "native_skills_output_invalid")
            return result["data"]
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                stop_process_tree()
                process.wait()
            watchdog.cancel()
            reader.join(timeout=2)


def _consumer_skill_path(raw_path: Any) -> Path:
    require(isinstance(raw_path, str), "native_skill_path_invalid")
    path = Path(raw_path)
    require(path.is_absolute() and path.name == "SKILL.md", "native_skill_path_invalid")
    try:
        validate_physical_directory_chain(
            path.parent,
            allow_missing_tail=False,
            error_code="consumer_skill_parent_unsafe",
            error_cls=BootstrapError,
        )
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError("consumer_skill_parent_unsafe") from exc
    return path.parent


def observe_consumer_scope(
    inventory: Any,
    *,
    desired: dict[str, Any],
    codex_home: Path,
    expected_review_sha256: str,
    facade: Any = None,
) -> dict[str, Any]:
    """Read effective native candidates, then verify enabled product Skill bytes."""
    catalog_fn = getattr(facade, "native_skill_catalog", native_skill_catalog)
    skill_path_fn = getattr(facade, "_consumer_skill_path", _consumer_skill_path)
    max_bytes = getattr(facade, "CONSUMER_SKILL_MAX_BYTES", CONSUMER_SKILL_MAX_BYTES)

    desired = validate_desired_bundle(desired)
    require(SHA64.fullmatch(expected_review_sha256) is not None, "expected review skill hash invalid")
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

    catalogs: dict[str, dict[str, Any]] = {}
    native_available = False
    roots = [path for _, path, _ in normalized if path is not None]
    if roots:
        try:
            for entry in catalog_fn(codex_home, roots):
                require(isinstance(entry, dict) and isinstance(entry.get("cwd"), str), "native_skills_output_invalid")
                identity = os.path.normcase(str(Path(entry["cwd"]).resolve()))
                require(identity in seen_paths and identity not in catalogs, "native_skills_cwd_invalid")
                catalogs[identity] = entry
            native_available = True
        except (BootstrapError, OSError, ValueError):
            catalogs = {}
    projects: list[dict[str, Any]] = []
    scanned_project_count = 0
    review_disabled = False
    managed_review_path = os.path.normcase(os.path.abspath(
        codex_home / "plugins" / "cache" / "agent-memory" / "agent-memory-sidecar" /
        desired["plugin_version"] / "skills" / REVIEW_SKILL / "SKILL.md"
    ))
    for index, (display_name, project_root, _is_git_repository) in enumerate(normalized):
        project_ref = "desktop-project-" + hashlib.sha256(
            canonical({"display_name": display_name, "ordinal": index})
        ).hexdigest()[:16]
        project_status = "exact"
        skills: list[dict[str, Any]] = []
        try:
            require(project_root is not None, "consumer_project_unavailable")
            root_state = project_root.lstat()
            require(stat.S_ISDIR(root_state.st_mode) and not is_reparse(root_state), "consumer_project_unreadable")
            scanned_project_count += 1
            entry = catalogs.get(os.path.normcase(str(project_root)))
            require(native_available and isinstance(entry, dict), "native_skills_unavailable")
            require(entry.get("errors") == [] and isinstance(entry.get("skills"), list), "native_skills_incomplete")
            require(all(isinstance(item, dict) for item in entry["skills"]), "native_skills_output_invalid")
            candidates = [item for item in entry["skills"] if _consumer_capability(item.get("name")) is not None]
            seen_candidates: set[str] = set()
            managed_review_disabled = False
            managed_review_found = False
            for item in candidates:
                name = item["name"]
                require(isinstance(item.get("enabled"), bool), "native_skill_enabled_missing")
                require(item.get("scope") in {"repo", "user", "system", "admin"}, "native_skill_scope_invalid")
                raw_path = item.get("path")
                require(isinstance(raw_path, str) and Path(raw_path).is_absolute(), "native_skill_path_invalid")
                identity = os.path.normcase(os.path.abspath(raw_path))
                require(identity not in seen_candidates, "native_skill_path_duplicated")
                seen_candidates.add(identity)
                if name == MANAGED_REVIEW_SKILL and item["scope"] == "user" and identity == managed_review_path:
                    managed_review_found = True
                    if not item["enabled"]:
                        managed_review_disabled = True
                        review_disabled = True
                version = content_sha256 = "unavailable"
                relation = "disabled"
                if item["enabled"]:
                    try:
                        skill_root = skill_path_fn(raw_path)
                        content_sha256 = bounded_physical_tree_hash(
                            skill_root, max_entries=CONSUMER_SKILL_MAX_ENTRIES, max_bytes=max_bytes,
                        )
                        capability = _consumer_capability(name)
                        version = _skill_version(skill_root) if capability != REVIEW_SKILL else "unavailable"
                        require(content_sha256 == bounded_physical_tree_hash(
                            skill_root, max_entries=CONSUMER_SKILL_MAX_ENTRIES, max_bytes=max_bytes,
                        ), "consumer_skill_changed_during_read")
                        version_field, hash_field = CONSUMER_SKILLS[capability]
                        if capability == REVIEW_SKILL:
                            relation = "exact" if content_sha256 == expected_review_sha256 else "drifted"
                            if relation == "exact":
                                version = desired[version_field]
                        else:
                            relation = "exact" if version == desired[version_field] and content_sha256 == desired[hash_field] else "drifted"
                    except (BootstrapError, OSError, UnicodeError):
                        version = content_sha256 = "unavailable"
                        relation = "unreadable"
                skills.append({
                    "name": name, "scope": item["scope"], "enabled": item["enabled"],
                    "version": version, "content_sha256": content_sha256, "relation": relation,
                })
            require(managed_review_found, "consumer_managed_review_entry_missing")
            for name in CONSUMER_SKILLS:
                enabled = [item for item in skills if _consumer_capability(item["name"]) == name and item["enabled"]]
                optional_disabled = name == REVIEW_SKILL and managed_review_disabled and not enabled
                require(enabled or optional_disabled, "consumer_skill_no_enabled_entry")
                if len(enabled) > 1:
                    for item in enabled:
                        if item["relation"] != "unreadable":
                            item["relation"] = "drifted"
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
    if review_disabled:
        limitations.append(REVIEW_DISABLED_NOTICE)
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
    facade: Any = None,
) -> dict[str, Any]:
    """Read the current Core, Doctor, Owner binding, and installed Skill state."""
    run_json_fn = getattr(facade, "run_json", run_json)
    inspect_checkout_fn = getattr(facade, "inspect_checkout", inspect_checkout)
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
        inspect_checkout_fn(sidecar, by_name["sidecar"])
        init_text = _physical_file_bytes(
            sidecar / "src" / "agent_memory_sidecar" / "__init__.py",
            "core_version_unreadable",
        ).decode("utf-8")
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
        payload = run_json_fn(
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


def _has_existing_global_binding(codex_home: Path) -> bool:
    return read_global_instruction_binding(
        codex_home,
        strict_commit=False,
        allow_any_schema=True,
        error_code="public_core_binding_check_failed",
        error_cls=BootstrapError,
    ) is not None


def materialize_host(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    preserve_existing_owner: bool = False,
    facade: Any = None,
) -> dict[str, Any]:
    run_json_fn = getattr(facade, "run_json", run_json)
    has_binding_fn = getattr(facade, "_has_existing_global_binding", _has_existing_global_binding)
    inspect_checkout_fn = getattr(facade, "inspect_checkout", inspect_checkout)
    inspect_existing_fn = getattr(facade, "inspect_existing_checkout", inspect_existing_checkout)
    current_owner_root_fn = getattr(facade, "_current_owner_root", _current_owner_root)
    preserved_owner_fn = getattr(facade, "_preserved_owner_identity", _preserved_owner_identity)
    installed_skill_root_fn = getattr(facade, "_installed_skill_root", _installed_skill_root)
    core_setup_data_fn = getattr(facade, "core_setup_data", core_setup_data)
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
            not has_binding_fn(codex_home),
            "public_core_existing_global_binding",
        )
    for spec in specs:
        inspect_checkout_fn(root / spec.name, spec)
    sidecar = root / "sidecar"
    canonical_owner = root / "canonical_owner" if "canonical_owner" in by_name else None
    if preserve_existing_owner:
        owner_root = current_owner_root_fn(codex_home)
        current_owner = inspect_existing_fn(owner_root)
        require(
            preserved_owner_fn(codex_home, current_owner) is not None,
            "source_cutover_owner_state_ambiguous",
        )
        canonical_owner = owner_root
    enrollment = sidecar / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "enrollment.py"
    require(enrollment.is_file(), "managed_bootstrap_missing")
    skill_root = installed_skill_root_fn(codex_home, create=True)
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(sidecar / "src") + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    bootstrap_result = run_json_fn([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / "skills" / "agent-memory-workstation-bootstrap"),
        "--target", str(skill_root / "agent-memory-workstation-bootstrap"), "--version", BOOTSTRAP_VERSION,
    ], cwd=sidecar, env=env)
    scout_result = run_json_fn([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / "skills" / "global-owner-scout"),
        "--target", str(skill_root / "global-owner-scout"), "--version", SCOUT_VERSION,
    ], cwd=sidecar, env=env)
    setup_command = [
        sys.executable, "-B", "-m", "agent_memory_sidecar", "--cwd", str(sidecar), "setup", "--apply",
    ]
    if canonical_owner is not None:
        setup_command.extend([
            "--global-rules-source", str(canonical_owner), "--rebind-global-rules-source",
        ])
    setup_data = core_setup_data_fn(run_json_fn(setup_command, cwd=sidecar, env=env))
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
        init_text = _physical_file_bytes(
            sidecar / "src" / "agent_memory_sidecar" / "__init__.py",
            "core_version_unreadable",
        ).decode("utf-8")
    except (BootstrapError, OSError, UnicodeError) as exc:
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


def _expected_review_hash(release_manifest_path: Path | str, desired: dict[str, Any], archive_sha256: str) -> str:
    release_path = Path(release_manifest_path).expanduser().resolve()
    plugin = _portable_root_for_release_manifest(release_path) / "plugins" / "agent-memory-sidecar"

    def plugin_hash() -> str:
        return physical_tree_hash(plugin, excluded_relatives={"source-manifest.json"})

    require(plugin_hash() == desired["plugin_sha256"], "verified_plugin_content_changed")
    archive_name = f"agent-memory-portable-{desired['core_version']}.zip"
    archive_bytes = _physical_file_bytes(release_path.with_name(archive_name), "release_resolution_assets_incomplete", limit=67_108_864)
    require(SHA64.fullmatch(archive_sha256) is not None and hashlib.sha256(archive_bytes).hexdigest() == archive_sha256,
            "release_resolution_asset_mismatch:portable")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            prefix = f"plugins/agent-memory-sidecar/skills/{REVIEW_SKILL}/"
            entries = [entry for entry in archive.infolist() if entry.filename.startswith(prefix)]
            require(len(entries) <= CONSUMER_SKILL_MAX_ENTRIES, "component_tree_entry_budget_exceeded")
            names = [entry.filename for entry in entries]
            require(len(names) == len({name.casefold() for name in names}), "release_portable_duplicate")
            files = []
            for entry in entries:
                if entry.filename == prefix and entry.is_dir():
                    continue
                relative = entry.filename[len(prefix):].rstrip("/")
                parts = relative.split("/")
                require(relative and all(part not in {"", ".", ".."} and ":" not in part and "\\" not in part for part in parts),
                        "release_portable_path_invalid")
                if not entry.is_dir() and not any(part in {".git", "__pycache__"} for part in parts):
                    if Path(relative).suffix.casefold() not in {".pyc", ".pyo"}:
                        files.append((relative, entry))
            require(files, "component_tree_empty")
            require(sum(entry.file_size for _, entry in files) <= CONSUMER_SKILL_MAX_BYTES,
                    "component_tree_byte_budget_exceeded")
            digest = hashlib.sha256()
            for relative, entry in sorted(files, key=lambda item: item[0]):
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(archive.read(entry))
                digest.update(b"\0")
            review_hash = digest.hexdigest()
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise BootstrapError("release_portable_invalid") from exc
    require(bounded_physical_tree_hash(
        plugin / "skills" / REVIEW_SKILL, max_entries=CONSUMER_SKILL_MAX_ENTRIES, max_bytes=CONSUMER_SKILL_MAX_BYTES,
    ) == review_hash, "verified_review_content_mismatch")
    require(plugin_hash() == desired["plugin_sha256"], "verified_plugin_content_changed")
    return review_hash
