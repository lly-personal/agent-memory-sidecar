#!/usr/bin/env python3
"""Schema constants and validators for Bootstrap workstation reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from bootstrap_security import BootstrapError, physical_file_bytes


BOOTSTRAP_VERSION = "2.5.11"
SCOUT_VERSION = "5.19.8"
PACK_VERSION = "agent_memory_workstation_deployment_pack_v4"
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
CONSUMER_SKILL_FIELDS = {"name", "scope", "enabled", "version", "content_sha256", "relation"}
CONSUMER_SKILLS = {
    "agent-memory-workstation-bootstrap": ("bootstrap_version", "bootstrap_sha256"),
    "global-owner-scout": ("scout_version", "scout_sha256"),
    "engineering-contract-review": ("plugin_version", None),
}
REVIEW_SKILL = "engineering-contract-review"
MANAGED_REVIEW_SKILL = "agent-memory-sidecar:engineering-contract-review"
REVIEW_DISABLED_NOTICE = "工程契约审查的托管 Plugin 入口已停用；本次保留该选择，未验证其启用后使用。"
NATIVE_SKILLS_TIMEOUT_SECONDS = 30
NATIVE_SKILLS_MAX_BYTES = 16 * 1024 * 1024
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


@dataclass(frozen=True)
class SourceSpec:
    name: str
    remote: str
    ref: str = "main"
    expected_commit: str | None = None


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


def _physical_file_bytes(path: Path, code: str, *, limit: int = 1_048_576) -> bytes:
    return physical_file_bytes(path, code, limit=limit, error_cls=BootstrapError)


def _load_json_file(path: Path | str, code: str) -> dict[str, Any]:
    try:
        value = json.loads(_physical_file_bytes(Path(path), code).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError(code) from exc
    require(isinstance(value, dict), code)
    return value


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


def _consumer_capability(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    if name in CONSUMER_SKILLS:
        return name
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*:engineering-contract-review", name):
        return REVIEW_SKILL
    return None


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
        for skill_index, skill in enumerate(project["skills"]):
            exact(skill, CONSUMER_SKILL_FIELDS, f"$.consumer_scope.projects[{index}].skills[{skill_index}]")
            capability = _consumer_capability(skill["name"])
            require(capability is not None, "consumer skill name invalid")
            require(skill["scope"] in {"repo", "user", "system", "admin"}, "consumer skill scope invalid")
            require(isinstance(skill["enabled"], bool), "consumer skill enabled invalid")
            require(skill["relation"] in {"exact", "drifted", "unreadable", "disabled"}, "consumer skill relation invalid")
            require((skill["relation"] == "disabled") == (not skill["enabled"]), "consumer skill enabled inconsistent")
            if skill["relation"] in {"unreadable", "disabled"}:
                require(skill["version"] == "unavailable", "unreadable consumer skill version invalid")
                require(skill["content_sha256"] == "unavailable", "unreadable consumer skill hash invalid")
            else:
                require(
                    SEMVER.fullmatch(str(skill["version"])) is not None
                    or (capability == REVIEW_SKILL and skill["relation"] == "drifted" and skill["version"] == "unavailable"),
                    "consumer skill version invalid",
                )
                require(SHA64.fullmatch(str(skill["content_sha256"])) is not None, "consumer skill hash invalid")
            project_relations.add(skill["relation"])
            matching_skill_count += 1
        expected_project_status = (
            "bounded" if "unreadable" in project_relations or project["status"] == "bounded"
            else ("drifted" if "drifted" in project_relations else "exact")
        )
        require(project["status"] == expected_project_status, "consumer project status inconsistent")
        if project["status"] in {"exact", "drifted"}:
            require(any(item["name"] == MANAGED_REVIEW_SKILL and item["scope"] == "user" for item in project["skills"]),
                    "qualified consumer project requires managed review entry")
            for name in CONSUMER_SKILLS:
                enabled = [item for item in project["skills"] if _consumer_capability(item["name"]) == name and item["enabled"]]
                disabled_review = name == REVIEW_SKILL and any(
                    item["name"] == MANAGED_REVIEW_SKILL and item["scope"] == "user" and not item["enabled"]
                    for item in project["skills"]
                )
                if disabled_review:
                    require(REVIEW_DISABLED_NOTICE in value["limitations"], "disabled review requires notice")
                require(enabled or disabled_review, "qualified consumer project requires each enabled capability")
                if project["status"] == "exact":
                    require(not enabled or (len(enabled) == 1 and enabled[0]["relation"] == "exact"),
                            "consumer effective entry must be unique and exact")
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
            require(len(value["projects"]) == value["desktop_project_count"], "qualified consumer scope requires every project")
            require(
                value["scanned_project_count"] == value["desktop_project_count"],
                "qualified consumer scope requires complete project read",
            )
    for index, item in enumerate(value["limitations"]):
        safe_text(item, f"$.consumer_scope.limitations[{index}]", 300)
    return value


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
    if REVIEW_DISABLED_NOTICE in value["consumer_scope"]["limitations"]:
        require(REVIEW_DISABLED_NOTICE in value["limitations"], "consumer scope limitations missing from pack")
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
