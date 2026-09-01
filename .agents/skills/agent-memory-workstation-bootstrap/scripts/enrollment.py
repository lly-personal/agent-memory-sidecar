#!/usr/bin/env python3
"""Deterministic identity, validation, installation, and rendering for Bootstrap 1.9."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PACK_VERSION = "global_owner_scout_enrollment_pack_v1"
PROFILE_VERSION = "global_owner_scout_host_profile_v1"
BOOTSTRAP_VERSION = "2.1.0"
SCOUT_VERSION = "5.7.0"
PACK_FIELDS = {
    "contract_version", "status", "display_locale", "bootstrap_version", "generated_at",
    "portable_layer", "discovery", "projects", "recommended_project_refs",
    "current_automation_count", "automation_change_count", "allowed_actions", "limitations", "pack_hash",
}
PORTABLE_FIELDS = {
    "sidecar", "canonical_owner", "core_setup", "doctor", "scout_skill_version", "scout_skill_hash",
}
DISCOVERY_FIELDS = {
    "inventory_status", "activity_status", "desktop_project_count", "accessible_count", "active_count",
    "eligible_count", "enrolled_count", "task_index_limit", "limitations",
}
PROJECT_FIELDS = {
    "project_ref", "display_name", "identity_kind", "content_identity_hash", "host_project_ref",
    "discovered", "accessible", "activity", "activity_coverage", "eligibility", "eligibility_reason",
    "enrollment_status", "existing_automation_ref", "recommended_action", "recommendation_reason",
}
PROFILE_FIELDS = {
    "contract_version", "profile_version", "updated_at", "scout_skill_version", "entries", "profile_hash",
}
ENTRY_FIELDS = {
    "content_identity_hash", "host_project_ref", "automation_ref", "status", "cadence", "time_slot",
    "last_verified_at",
}
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|opt|mnt)/)", re.IGNORECASE)
RAW_URL = re.compile(r"(?:https?|ssh|git)://|git@[^\s:]+:", re.IGNORECASE)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TIME_SLOT = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def exact(obj: Any, fields: set[str], path: str) -> None:
    require(isinstance(obj, dict), f"{path} must be an object")
    actual = set(obj)
    require(actual == fields, f"{path} fields mismatch: missing={sorted(fields-actual)} extra={sorted(actual-fields)}")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(value: dict[str, Any], field: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical(payload)).hexdigest()


def opaque(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def nonempty(value: Any, path: str, maximum: int = 400) -> None:
    require(isinstance(value, str) and value.strip() != "", f"{path} must be non-empty text")
    require(len(value) <= maximum, f"{path} is too long")


def safe_text(value: Any, path: str, maximum: int = 400) -> None:
    nonempty(value, path, maximum)
    require(not ABSOLUTE_PATH.search(value), f"{path} leaks an absolute path")
    require(not RAW_URL.search(value), f"{path} leaks a raw URL or remote")


def iso_time(value: Any, path: str) -> None:
    nonempty(value, path, 40)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{path} must be ISO-8601") from exc


def normalize_remote(raw: str) -> str:
    value = raw.strip()
    require(value != "", "Git remote is empty")
    if re.match(r"^[^/@:\s]+@[^/:\s]+:.+$", value):
        user_host, path = value.split(":", 1)
        host = user_host.split("@", 1)[1].lower()
        normalized = f"{host}/{path.lstrip('/')}"
    else:
        parsed = urlsplit(value)
        if parsed.scheme:
            host = (parsed.hostname or "").lower()
            port = f":{parsed.port}" if parsed.port else ""
            normalized = f"{host}{port}/{parsed.path.lstrip('/')}"
        else:
            normalized = value.replace("\\", "/")
    normalized = normalized.rstrip("/")
    if normalized.lower().endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold()


def run_git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise ContractError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def inspect_project(path: Path, display_name: str, host_project_ref: str) -> dict[str, Any]:
    nonempty(display_name, "display_name", 120)
    nonempty(host_project_ref, "host_project_ref", 240)
    project_ref = opaque("project", host_project_ref)
    try:
        root = Path(run_git(path, "rev-parse", "--show-toplevel")).resolve()
        relative = path.resolve().relative_to(root).as_posix() or "."
        remote = run_git(path, "remote", "get-url", "origin")
        normalized = normalize_remote(remote)
        identity = opaque("pci", normalized + "\n" + relative.casefold())
        return {
            "project_ref": project_ref,
            "display_name": display_name,
            "identity_kind": "content",
            "content_identity_hash": identity,
            "host_project_ref": host_project_ref,
            "discovered": True,
            "accessible": path.exists(),
            "eligibility": "eligible",
            "eligibility_reason": "Git 工程具备可验证的远端内容身份，可使用隔离 worktree。",
        }
    except (ContractError, ValueError, OSError):
        local_identity = opaque("hostlocal", host_project_ref)
        return {
            "project_ref": project_ref,
            "display_name": display_name,
            "identity_kind": "host_local",
            "content_identity_hash": local_identity,
            "host_project_ref": host_project_ref,
            "discovered": True,
            "accessible": path.exists(),
            "eligibility": "ineligible",
            "eligibility_reason": "缺少可验证的 Git 远端内容身份，无法证明隔离周期运行条件。",
        }


def validate_pack(obj: Any) -> dict[str, Any]:
    exact(obj, PACK_FIELDS, "$")
    require(obj["contract_version"] == PACK_VERSION, "$.contract_version invalid")
    require(obj["status"] in {"ready", "bounded", "host_activation_blocked"}, "$.status invalid")
    require(obj["display_locale"] == "zh-CN", "$.display_locale invalid")
    require(obj["bootstrap_version"] == BOOTSTRAP_VERSION, "$.bootstrap_version invalid")
    iso_time(obj["generated_at"], "$.generated_at")
    exact(obj["portable_layer"], PORTABLE_FIELDS, "$.portable_layer")
    states = {"synced", "unchanged", "installed", "verified", "failed", "unavailable"}
    for field in ("sidecar", "canonical_owner", "core_setup", "doctor"):
        require(obj["portable_layer"][field] in states, f"$.portable_layer.{field} invalid")
    require(obj["portable_layer"]["scout_skill_version"] == SCOUT_VERSION, f"Scout version must be {SCOUT_VERSION}")
    require(HEX64.fullmatch(obj["portable_layer"]["scout_skill_hash"]) is not None, "Scout hash invalid")

    discovery = obj["discovery"]
    exact(discovery, DISCOVERY_FIELDS, "$.discovery")
    require(discovery["inventory_status"] in {"complete", "bounded", "unavailable"}, "inventory status invalid")
    require(discovery["activity_status"] in {"complete", "bounded", "unavailable"}, "activity status invalid")
    for field in ("desktop_project_count", "accessible_count", "active_count", "eligible_count", "enrolled_count", "task_index_limit"):
        require(isinstance(discovery[field], int) and discovery[field] >= 0, f"$.discovery.{field} invalid")
    require(isinstance(discovery["limitations"], list), "$.discovery.limitations must be a list")
    for index, item in enumerate(discovery["limitations"]):
        safe_text(item, f"$.discovery.limitations[{index}]", 300)

    projects = obj["projects"]
    require(isinstance(projects, list), "$.projects must be a list")
    require(len(projects) == discovery["desktop_project_count"], "Desktop project count does not conserve")
    refs: set[str] = set()
    accessible = active = eligible = enrolled = 0
    eligible_recommended: set[str] = set()
    for index, project in enumerate(projects):
        path = f"$.projects[{index}]"
        exact(project, PROJECT_FIELDS, path)
        for field in ("project_ref", "display_name", "content_identity_hash", "host_project_ref", "eligibility_reason", "recommendation_reason"):
            safe_text(project[field], f"{path}.{field}", 400)
        require(project["project_ref"] not in refs, f"{path}.project_ref duplicates")
        refs.add(project["project_ref"])
        require(project["identity_kind"] in {"content", "host_local"}, f"{path}.identity_kind invalid")
        require(isinstance(project["discovered"], bool) and project["discovered"], f"{path}.discovered invalid")
        require(isinstance(project["accessible"], bool), f"{path}.accessible invalid")
        require(project["activity"] in {"active", "inactive", "unknown"}, f"{path}.activity invalid")
        require(project["activity_coverage"] in {"complete", "bounded", "unavailable"}, f"{path}.activity_coverage invalid")
        require(project["eligibility"] in {"eligible", "ineligible"}, f"{path}.eligibility invalid")
        require(project["enrollment_status"] in {"enabled", "deferred", "excluded", "not_enrolled"}, f"{path}.enrollment_status invalid")
        require(project["recommended_action"] in {"migrate_enabled", "enable", "trial", "defer", "exclude", "keep", "blocked"}, f"{path}.recommended_action invalid")
        require(isinstance(project["existing_automation_ref"], str), f"{path}.existing_automation_ref invalid")
        if project["identity_kind"] == "host_local":
            require(project["eligibility"] == "ineligible", f"{path} host-local project cannot be eligible")
        if project["accessible"]:
            accessible += 1
        if project["activity"] == "active":
            active += 1
        if project["eligibility"] == "eligible":
            eligible += 1
        if project["enrollment_status"] == "enabled":
            enrolled += 1
        if project["accessible"] and project["activity"] == "active" and project["eligibility"] == "eligible" and project["recommended_action"] in {"enable", "migrate_enabled"}:
            eligible_recommended.add(project["project_ref"])
    require(accessible == discovery["accessible_count"], "accessible_count mismatch")
    require(active == discovery["active_count"], "active_count mismatch")
    require(eligible == discovery["eligible_count"], "eligible_count mismatch")
    require(enrolled == discovery["enrolled_count"], "enrolled_count mismatch")

    recommended = obj["recommended_project_refs"]
    require(isinstance(recommended, list) and len(recommended) == len(set(recommended)), "recommended refs invalid")
    require(set(recommended) == eligible_recommended, "recommended refs must equal active + eligible defaults")
    require(isinstance(obj["current_automation_count"], int) and obj["current_automation_count"] >= 0, "automation count invalid")
    require(obj["automation_change_count"] == 0, "inspect pack must not change automations")
    normal_actions = {"apply_recommended", "enable_selected", "defer_selected", "exclude_selected", "keep_current", "rescan"}
    blocked_actions = {"keep_current", "rescan"}
    require(set(obj["allowed_actions"]) == (blocked_actions if obj["status"] == "host_activation_blocked" else normal_actions), "allowed actions invalid")
    require(isinstance(obj["limitations"], list), "$.limitations invalid")
    for index, item in enumerate(obj["limitations"]):
        safe_text(item, f"$.limitations[{index}]", 300)
    require(obj["pack_hash"] == object_hash(obj, "pack_hash"), "pack_hash mismatch")
    return obj


def validate_profile(obj: Any) -> dict[str, Any]:
    exact(obj, PROFILE_FIELDS, "$")
    require(obj["contract_version"] == PROFILE_VERSION, "profile contract invalid")
    require(obj["profile_version"] == "1.0.0", "profile version invalid")
    require(obj["scout_skill_version"] == SCOUT_VERSION, "profile Scout version invalid")
    iso_time(obj["updated_at"], "$.updated_at")
    require(isinstance(obj["entries"], list), "$.entries must be a list")
    identities: set[str] = set()
    slots: set[str] = set()
    for index, entry in enumerate(obj["entries"]):
        path = f"$.entries[{index}]"
        exact(entry, ENTRY_FIELDS, path)
        for field in ("content_identity_hash", "host_project_ref"):
            nonempty(entry[field], f"{path}.{field}", 100)
        require(entry["content_identity_hash"] not in identities, f"{path} duplicates content identity")
        identities.add(entry["content_identity_hash"])
        require(entry["status"] in {"enabled", "deferred", "excluded"}, f"{path}.status invalid")
        iso_time(entry["last_verified_at"], f"{path}.last_verified_at")
        if entry["status"] == "enabled":
            require(entry["cadence"] == "weekdays_daily", f"{path}.cadence invalid")
            require(TIME_SLOT.fullmatch(entry["time_slot"]) is not None, f"{path}.time_slot invalid")
            nonempty(entry["automation_ref"], f"{path}.automation_ref", 180)
            require(entry["time_slot"] not in slots, f"{path}.time_slot duplicates")
            slots.add(entry["time_slot"])
        else:
            require(entry["cadence"] == "none" and entry["time_slot"] == "" and entry["automation_ref"] == "", f"{path} inactive fields invalid")
    require(obj["profile_hash"] == object_hash(obj, "profile_hash"), "profile_hash mismatch")
    return obj


def _logical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _is_reparse(value: os.stat_result) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _is_trusted_host_directory_alias(
    path: Path,
    value: os.stat_result,
    *,
    platform: str | None = None,
) -> bool:
    platform = os.name if platform is None else platform
    logical = Path(path)
    return bool(
        platform == "posix"
        and stat.S_ISLNK(value.st_mode)
        and getattr(value, "st_uid", -1) == 0
        and logical.parent == Path(logical.anchor)
    )


def _assert_directory_chain(path: Path, *, allow_missing_tail: bool) -> None:
    logical = _logical_absolute(path)
    cursor = Path(logical.anchor)
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise ContractError("Skill path ancestor is missing")
        alias = stat.S_ISLNK(value.st_mode) or _is_reparse(value)
        if alias and _is_trusted_host_directory_alias(cursor, value):
            try:
                resolved_value = cursor.resolve(strict=True).stat()
            except OSError as exc:
                raise ContractError("trusted host directory mapping cannot be resolved") from exc
            require(
                stat.S_ISDIR(resolved_value.st_mode),
                "trusted host directory mapping is not a directory",
            )
            continue
        require(
            stat.S_ISDIR(value.st_mode) and not alias,
            "Skill path ancestor is not a physical directory",
        )


def _skill_files(root: Path) -> list[Path]:
    logical = _logical_absolute(root)
    _assert_directory_chain(logical, allow_missing_tail=False)
    files: list[Path] = []
    for item in logical.rglob("*"):
        value = item.lstat()
        require(not stat.S_ISLNK(value.st_mode) and not _is_reparse(value), "Skill tree contains an alias")
        if stat.S_ISDIR(value.st_mode):
            continue
        require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, "Skill tree contains an unsafe file")
        if "__pycache__" not in item.parts and not item.name.endswith((".pyc", ".pyo")):
            files.append(item)
    return sorted(files)


def tree_hash(root: Path) -> str:
    root = _logical_absolute(root)
    require(root.is_dir(), f"Skill root does not exist: {root}")
    digest = hashlib.sha256()
    for item in _skill_files(root):
        relative = item.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def install_skill(source: Path, target: Path, version: str = SCOUT_VERSION) -> dict[str, str]:
    source = _logical_absolute(source)
    target = _logical_absolute(target)
    require(source.is_dir(), "Scout source directory is missing")
    source_hash = tree_hash(source)
    _assert_directory_chain(target.parent, allow_missing_tail=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_directory_chain(target.parent, allow_missing_tail=False)
    if target.exists() or target.is_symlink():
        value = target.lstat()
        require(
            stat.S_ISDIR(value.st_mode)
            and not stat.S_ISLNK(value.st_mode)
            and not _is_reparse(value),
            "Skill target is not a physical directory",
        )
    if target.is_dir() and tree_hash(target) == source_hash:
        return {"status": "unchanged", "version": version, "hash": source_hash}
    token = uuid.uuid4().hex
    staged = target.parent / f".{target.name}.install-{token}"
    rollback = target.parent / f".{target.name}.rollback-{token}"
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        require(tree_hash(staged) == source_hash, "staged Skill hash mismatch")
        if target.exists():
            os.replace(target, rollback)
        os.replace(staged, target)
        require(tree_hash(target) == source_hash, "installed Skill hash mismatch")
        if rollback.exists():
            shutil.rmtree(rollback)
        return {"status": "installed", "version": version, "hash": source_hash}
    except Exception:
        if target.exists() and rollback.exists():
            shutil.rmtree(target)
        if rollback.exists() and not target.exists():
            os.replace(rollback, target)
        if staged.exists():
            shutil.rmtree(staged)
        raise


def write_profile(path: Path, obj: Any) -> dict[str, str]:
    profile = validate_profile(obj)
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.parent / f".{path.name}.write-{uuid.uuid4().hex}"
    try:
        staged.write_bytes(canonical(profile) + b"\n")
        reread = json.loads(staged.read_text(encoding="utf-8"))
        validate_profile(reread)
        os.replace(staged, path)
        return {"status": "written", "profile_hash": profile["profile_hash"]}
    finally:
        if staged.exists():
            staged.unlink()


def status_zh(value: str) -> str:
    return {
        "ready": "可确认", "bounded": "受限但可确认", "host_activation_blocked": "主机激活受阻",
        "active": "活跃", "inactive": "近期不活跃", "unknown": "活动性未知",
        "complete": "完整", "bounded": "受限", "unavailable": "不可用",
        "eligible": "可隔离运行", "ineligible": "不可隔离运行",
        "migrate_enabled": "迁移现有任务", "enable": "建议启用", "trial": "建议试运行",
        "defer": "暂不启用", "exclude": "不再建议", "keep": "保持现状", "blocked": "不可启用",
    }.get(value, value)


def render_pack(obj: Any) -> str:
    pack = validate_pack(obj)
    discovery = pack["discovery"]
    portable = pack["portable_layer"]
    lines = [
        "# 本机 Agent Memory 部署与项目启用建议",
        "",
        f"> 状态：**{status_zh(pack['status'])}**。本次只完成能力同步、发现和建议；Scheduled Task 变化：**0**。",
        "",
        "## 可移植能力",
        "",
        "| Sidecar | Canonical Owner | Core / Doctor | Global Owner Scout |",
        "|---|---|---|---|",
        f"| {portable['sidecar']} | {portable['canonical_owner']} | {portable['core_setup']} / {portable['doctor']} | {portable['scout_skill_version']} / 已校验 |",
        "",
        "## 主动项目复盘入口",
        "",
        "已可在任一目标 Git 工程的当前项目任务中发送 `$global-owner-scout 复盘当前项目`。Scout 会在深挖前自动投影隔离 worktree 执行，用户无需手工创建或重复指令。该入口无需 Host Enrollment；下方 Scheduled 项目发现仅用于信息展示或以后显式复测。",
        "",
        "## 本机项目概览",
        "",
        f"发现 **{discovery['desktop_project_count']}** 个；可访问 **{discovery['accessible_count']}** 个；活跃 **{discovery['active_count']}** 个；可隔离运行 **{discovery['eligible_count']}** 个；当前已启用 **{discovery['enrolled_count']}** 个。",
        "",
        "| 项目 | 活跃与覆盖 | 安全条件 | 推荐动作 |",
        "|---|---|---|---|",
    ]
    for project in pack["projects"]:
        activity = f"{status_zh(project['activity'])} / {status_zh(project['activity_coverage'])}"
        safety = status_zh(project["eligibility"])
        recommendation = f"{status_zh(project['recommended_action'])}：{project['recommendation_reason']}"
        lines.append(f"| {project['display_name']} | {activity} | {safety} | {recommendation} |")
    warnings = [*discovery["limitations"], *pack["limitations"]]
    if warnings:
        lines.extend(["", "## 需要注意", ""])
        lines.extend(f"> {item}" for item in warnings)
    action_copy = {
        "apply_recommended": "- `按建议启用`：一次确认所有已证明为活跃且可隔离运行的建议项目。",
        "enable_selected": "- `启用：A、B`：只启用点名项目；“建议试运行”的项目必须这样显式选择。",
        "defer_selected": "- `暂不启用：C`：保留项目，事实不变时不重复打扰。",
        "exclude_selected": "- `不再建议：D`：本机排除，除非你以后明确重新扫描并改变决定。",
        "keep_current": "- `保持现状`：不迁移、不新增、不修改任何任务。",
        "rescan": "- `重新扫描`：刷新本机项目和近期任务后重新生成建议。",
    }
    lines.extend(["", "## Scheduled 实验（可选）", ""])
    if pack["status"] == "host_activation_blocked":
        lines.append("当前周期执行能力受阻；项目列表仅供了解，使用主动复盘入口无需处理 enrollment 建议。")
        lines.append("")
    lines.extend(action_copy[action] for action in pack["allowed_actions"])
    lines.extend([
        "",
        f"校验回执：`{pack['contract_version']}`｜项目守恒 {len(pack['projects'])}/{discovery['desktop_project_count']}｜Pack `{pack['pack_hash'][:12]}`",
    ])
    return "\n".join(lines) + "\n"


FORBIDDEN_PROMPT = [
    re.compile(r"project_key\s*[:=]", re.IGNORECASE),
    re.compile(r"projectId\s*[:=]", re.IGNORECASE),
    ABSOLUTE_PATH,
]


def validate_prompt(text: str) -> None:
    nonempty(text, "prompt", 4000)
    for pattern in FORBIDDEN_PROMPT:
        require(pattern.search(text) is None, "v5 Scheduled Prompt contains a fixed project binding")
    required = ["global-owner-scout", "project_scout", "5.7.0", "72", "global_owner_scout_project_v4", "global_owner_scout_review_pack_v4", "gpt-5.6-sol", "medium"]
    for token in required:
        require(token in text, f"v5 Scheduled Prompt missing {token}")


def load_stdin() -> Any:
    return json.load(sys.stdin)


def self_test() -> None:
    now = "2026-08-07T10:00:00+08:00"
    project = {
        "project_ref": "project_" + "a" * 64, "display_name": "示例工程", "identity_kind": "content",
        "content_identity_hash": "pci_" + "b" * 64, "host_project_ref": "hpr_" + "c" * 64,
        "discovered": True, "accessible": True, "activity": "active", "activity_coverage": "complete",
        "eligibility": "eligible", "eligibility_reason": "Git 工程可使用隔离 worktree。",
        "enrollment_status": "not_enrolled", "existing_automation_ref": "",
        "recommended_action": "enable", "recommendation_reason": "近期存在自然任务，且安全条件完整。",
    }
    pack = {
        "contract_version": PACK_VERSION, "status": "ready", "display_locale": "zh-CN",
        "bootstrap_version": BOOTSTRAP_VERSION, "generated_at": now,
        "portable_layer": {"sidecar": "unchanged", "canonical_owner": "unchanged", "core_setup": "verified", "doctor": "verified", "scout_skill_version": SCOUT_VERSION, "scout_skill_hash": "d" * 64},
        "discovery": {"inventory_status": "complete", "activity_status": "complete", "desktop_project_count": 1, "accessible_count": 1, "active_count": 1, "eligible_count": 1, "enrolled_count": 0, "task_index_limit": 50, "limitations": []},
        "projects": [project], "recommended_project_refs": [project["project_ref"]], "current_automation_count": 0,
        "automation_change_count": 0, "allowed_actions": ["apply_recommended", "enable_selected", "defer_selected", "exclude_selected", "keep_current", "rescan"], "limitations": [], "pack_hash": "",
    }
    pack["pack_hash"] = object_hash(pack, "pack_hash")
    validate_pack(pack)
    rendered = render_pack(pack)
    require("示例工程" in rendered, "renderer lost project")
    require("$global-owner-scout 复盘当前项目" in rendered, "renderer lost interactive entry")
    require("无需 Host Enrollment" in rendered, "renderer made enrollment a prerequisite")
    invalid = copy.deepcopy(pack)
    invalid["automation_change_count"] = 1
    try:
        validate_pack(invalid)
        raise AssertionError("mutating inspect pack accepted")
    except ContractError:
        pass
    try:
        validate_prompt("project_key=hard-coded")
        raise AssertionError("fixed prompt accepted")
    except ContractError:
        pass
    good_prompt = "Use $global-owner-scout mode project_scout Skill 5.7.0 rolling 72 hours global_owner_scout_project_v4 global_owner_scout_review_pack_v4 gpt-5.6-sol medium read-only"
    validate_prompt(good_prompt)
    profile = {"contract_version": PROFILE_VERSION, "profile_version": "1.0.0", "updated_at": now, "scout_skill_version": SCOUT_VERSION, "entries": [], "profile_hash": ""}
    profile["profile_hash"] = object_hash(profile, "profile_hash")
    validate_profile(profile)
    print(json.dumps({"status": "ok", "tests": 9}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect-project")
    inspect_parser.add_argument("--path", required=True)
    inspect_parser.add_argument("--display-name", required=True)
    inspect_parser.add_argument("--host-project-ref", required=True)
    sub.add_parser("validate-pack")
    sub.add_parser("render-pack")
    sub.add_parser("validate-profile")
    prompt_parser = sub.add_parser("validate-prompt")
    prompt_parser.add_argument("--text", required=True)
    install_parser = sub.add_parser("install-scout")
    install_parser.add_argument("--source", required=True)
    install_parser.add_argument("--target", required=True)
    generic_install_parser = sub.add_parser("install-skill")
    generic_install_parser.add_argument("--source", required=True)
    generic_install_parser.add_argument("--target", required=True)
    generic_install_parser.add_argument("--version", required=True)
    profile_parser = sub.add_parser("write-profile")
    profile_parser.add_argument("--path", required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "inspect-project":
            print(json.dumps(inspect_project(Path(args.path), args.display_name, args.host_project_ref), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "validate-pack":
            obj = validate_pack(load_stdin())
            print(json.dumps({"status": "ok", "contract_version": obj["contract_version"]}, separators=(",", ":")))
        elif args.command == "render-pack":
            sys.stdout.write(render_pack(load_stdin()))
        elif args.command == "validate-profile":
            obj = validate_profile(load_stdin())
            print(json.dumps({"status": "ok", "contract_version": obj["contract_version"]}, separators=(",", ":")))
        elif args.command == "validate-prompt":
            validate_prompt(args.text)
            print(json.dumps({"status": "ok", "prompt_contract": "v5"}, separators=(",", ":")))
        elif args.command == "install-scout":
            print(json.dumps(install_skill(Path(args.source), Path(args.target)), separators=(",", ":")))
        elif args.command == "install-skill":
            print(json.dumps(install_skill(Path(args.source), Path(args.target), args.version), separators=(",", ":")))
        elif args.command == "write-profile":
            print(json.dumps(write_profile(Path(args.path), load_stdin()), separators=(",", ":")))
        else:
            self_test()
        return 0
    except (ContractError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
