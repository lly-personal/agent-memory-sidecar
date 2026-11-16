#!/usr/bin/env python3
"""Workstation reconciliation planner, apply orchestration, and deployment pack v4."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from bootstrap_contracts import (
    BOOTSTRAP_VERSION,
    PACK_VERSION,
    SHA64,
    SourceSpec,
    _distribution_is_exact,
    _host_is_exact,
    _load_json_file,
    _validate_host_materialization,
    _validate_source_sync,
    load_source_manifest,
    object_hash,
    require,
    validate_consumer_scope,
    validate_desired_bundle,
    validate_observed_distribution,
    validate_pack,
    validate_source_cutover_plan,
    validate_workstation_reconcile_plan,
)
from source_cutover import apply_source_cutover, plan_source_cutover
from workstation_observer import (
    _not_observed_consumer_scope,
    _observe_distribution_with_private,
    _unavailable_host_materialization,
    load_desired_bundle,
    observe_consumer_scope,
    observe_distribution,
    observe_host_materialization,
    run_codex_json,
    _expected_review_hash,
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
        "contract_version": "agent_memory_workstation_reconcile_plan_v2",
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


def _workstation_reconcile_context(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    *,
    facade: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observe_host_fn = getattr(facade, "observe_host_materialization", observe_host_materialization)
    desired, sidecar, source_sha256, archive_sha256 = load_desired_bundle(
        source_manifest_path, release_manifest_path,
    )
    specs = load_source_manifest(source_manifest_path)
    observed, private_distribution = _observe_distribution_with_private(codex_home, facade=facade)
    source_plan = plan_source_cutover(codex_home, specs)
    if source_plan["status"] == "noop":
        observed_host = observe_host_fn(
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
        "archive_sha256": archive_sha256,
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
    *,
    facade: Any = None,
) -> dict[str, Any]:
    context_fn = getattr(facade, "_workstation_reconcile_context", _workstation_reconcile_context)
    plan, _ = context_fn(codex_home, source_manifest_path, release_manifest_path)
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


def _remove_plugin(codex_home: Path, *, facade: Any = None) -> None:
    getattr(facade, "run_codex_json", run_codex_json)(
        ["plugin", "remove", "agent-memory-sidecar@agent-memory", "--json"],
        codex_home=codex_home,
    )


def _remove_marketplace(codex_home: Path, *, facade: Any = None) -> None:
    getattr(facade, "run_codex_json", run_codex_json)(
        ["plugin", "marketplace", "remove", "agent-memory", "--json"],
        codex_home=codex_home,
    )


def _add_marketplace(codex_home: Path, *, remote: str, ref: str, facade: Any = None) -> None:
    getattr(facade, "run_codex_json", run_codex_json)(
        ["plugin", "marketplace", "add", remote, "--ref", ref, "--json"],
        codex_home=codex_home,
    )


def _add_plugin(codex_home: Path, *, facade: Any = None) -> None:
    getattr(facade, "run_codex_json", run_codex_json)(
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
    facade: Any = None,
) -> None:
    current, _ = _observe_distribution_with_private(codex_home, facade=facade)
    if plugin_touched and current["plugin"]["status"] == "installed":
        _remove_plugin(codex_home, facade=facade)
    if marketplace_touched and current["marketplace"]["status"] == "present":
        _remove_marketplace(codex_home, facade=facade)
    if marketplace_touched and private_before["marketplace"]["present"]:
        remote = private_before["marketplace"]["remote"]
        ref = private_before["marketplace"]["ref"]
        require(isinstance(remote, str) and isinstance(ref, str), "distribution_rollback_snapshot_invalid")
        _add_marketplace(codex_home, remote=remote, ref=ref, facade=facade)
    if plugin_touched and private_before["plugin"]["installed"]:
        require(private_before["plugin"]["enabled"] is True, "distribution_rollback_disabled_plugin_unsupported")
        _add_plugin(codex_home, facade=facade)
    restored = getattr(facade, "observe_distribution", observe_distribution)(codex_home)
    require(restored == before, "distribution_rollback_verification_failed")


def _apply_distribution_changes(
    codex_home: Path,
    *,
    plan: dict[str, Any],
    sidecar: SourceSpec,
    facade: Any = None,
) -> tuple[bool, bool]:
    marketplace_touched = any(item.startswith("marketplace:") for item in plan["changes"])
    plugin_touched = marketplace_touched or any(item.startswith("plugin:") for item in plan["changes"])
    before = plan["observed_distribution"]
    if plugin_touched and before["plugin"]["status"] == "installed":
        _remove_plugin(codex_home, facade=facade)
    if marketplace_touched and before["marketplace"]["status"] == "present":
        _remove_marketplace(codex_home, facade=facade)
    if marketplace_touched:
        _add_marketplace(codex_home, remote=sidecar.remote, ref=sidecar.ref, facade=facade)
    if plugin_touched:
        _add_plugin(codex_home, facade=facade)
    return marketplace_touched, plugin_touched


def apply_workstation_reconcile(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    *,
    plan_hash: str,
    facade: Any = None,
) -> dict[str, Any]:
    context_fn = getattr(facade, "_workstation_reconcile_context", _workstation_reconcile_context)
    observe_dist_fn = getattr(facade, "observe_distribution", observe_distribution)
    observe_host_fn = getattr(facade, "observe_host_materialization", observe_host_materialization)
    cutover_fn = getattr(facade, "apply_source_cutover", apply_source_cutover)

    require(SHA64.fullmatch(plan_hash.casefold()) is not None, "reconcile_plan_hash_invalid")
    plan, context = context_fn(codex_home, source_manifest_path, release_manifest_path)
    require(plan["plan_hash"] == plan_hash.casefold(), "reconcile_plan_stale")
    require(plan["status"] != "distribution_reconcile_blocked", "distribution_reconcile_blocked")
    before = context["observed"]
    private_before = context["private_distribution"]
    marketplace_touched = any(item.startswith("marketplace:") for item in plan["changes"])
    plugin_touched = marketplace_touched or any(item.startswith("plugin:") for item in plan["changes"])
    pack_holder: dict[str, Any] = {}

    def apply_distribution() -> None:
        _apply_distribution_changes(codex_home, plan=plan, sidecar=context["sidecar"], facade=facade)

    def rollback_distribution() -> None:
        _restore_distribution(
            codex_home,
            before=before,
            private_before=private_before,
            marketplace_touched=marketplace_touched,
            plugin_touched=plugin_touched,
            facade=facade,
        )

    def verify_and_build_pack(source_receipt: dict[str, Any]) -> None:
        observed_after = observe_dist_fn(codex_home)
        require(
            _distribution_is_exact(
                context["desired"],
                observed_after,
                desired_source_sha256=context["source_sha256"],
            ),
            "distribution_readback_mismatch",
        )
        materialization = observe_host_fn(
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

    cutover_fn(
        codex_home,
        context["specs"],
        plan_hash=context["source_plan"]["plan_hash"],
        external_apply=apply_distribution if (marketplace_touched or plugin_touched) else None,
        external_rollback=rollback_distribution if (marketplace_touched or plugin_touched) else None,
        precommit_verify=verify_and_build_pack,
    )
    require("value" in pack_holder, "deployment_pack_not_built")
    return {
        "contract_version": "agent_memory_workstation_reconcile_receipt_v3",
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
    *,
    facade: Any = None,
) -> dict[str, Any]:
    context_fn = getattr(facade, "_workstation_reconcile_context", _workstation_reconcile_context)
    expected_hash_fn = getattr(facade, "_expected_review_hash", _expected_review_hash)
    observe_scope_fn = getattr(facade, "observe_consumer_scope", observe_consumer_scope)
    plan, context = context_fn(codex_home, source_manifest_path, release_manifest_path)
    require(plan["status"] == "noop", "consumer_verification_requires_exact_host")
    inventory = _load_json_file(
        Path(desktop_project_inventory_path), "desktop_project_inventory_unreadable",
    )
    consumer_scope = observe_scope_fn(
        inventory,
        desired=context["desired"],
        codex_home=codex_home,
        expected_review_sha256=expected_hash_fn(
            release_manifest_path, context["desired"], context["archive_sha256"],
        ),
    )
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
    limitations = [
        "安装与范围读回不观察宿主会话加载；模型自动加载、自然采用和实际体验仍未证明。",
        "本次结果只适用于执行检查的主机；其他设备与跨任务连续性仍未证明。",
    ]
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


def _markdown_table_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")


def render_pack(value: Any) -> str:
    pack = validate_pack(value)
    status = {
        "ready": "本机托管能力和 Desktop 项目消费者范围已对齐",
        "reload_required": "本机安装与读回已完成；消费者范围及真实采用尚未验证",
        "consumer_scope_drift": "托管能力已对齐，但 Desktop 可见项目存在重复启用或内容不符的同名 Skill",
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
        f"| 主机物化 | Core `{material['core']['status']}` / Doctor `{material['doctor']}` / Scout `{material['scout_skill']['status']}` | Doctor 包含安装后的命令入口；Bootstrap {material['bootstrap_skill']['version']}；Scout {material['scout_skill']['version']} |",
        f"| 项目消费者范围 | `{scope['status']}` | Desktop 项目 {scope['desktop_project_count']}；已读 {scope['scanned_project_count']}；同名 Skill {scope['matching_skill_count']} |",
        f"| 消费者入口条件 | 入口检查 `{activation['interactive_entry']}` | `verified` 仅表示安装与项目范围检查通过；Scheduled `{activation['scheduled']}` |",
        "| Scout 实际运行 | 本次未运行 | 本次未验证 Scout 运行验收，不判断其他运行的验收结果 |",
    ]
    attention = [project for project in scope["projects"] if project["status"] != "exact"]
    if attention:
        lines.extend(["", "## Desktop 可见项目级同名 Skill", "", "| 项目 | Skill | 版本 | 关系 |", "|---|---|---|---|"])
        for project in attention:
            display_name = _markdown_table_text(project["display_name"])
            if not project["skills"]:
                lines.append(f"| {display_name} | 无法完整读取 | unavailable | `{project['status']}` |")
            for skill in project["skills"]:
                lines.append(
                    f"| {display_name} | `{skill['name']}@{skill['scope']} enabled={str(skill['enabled']).lower()}` | `{skill['version']}` | `{skill['relation']}` |"
                )
    if pack["limitations"]:
        lines.extend(["", "## 尚未证明", ""])
        lines.extend(f"> {item}" for item in pack["limitations"])
    next_step = {
        "reload_required": "本次安装交付到此完成。若本次已要求验收，Agent 继续在同一主机、同一聊天完成只读消费者检查，无需重复请求。未要求时到此结束；仅在能力未显示或宿主明确要求时提示刷新。",
        "ready": "已完成所请求的安装与项目范围检查。实际使用继续沿用目标工程的现有入口，无需另建验收聊天。",
        "consumer_scope_drift": "下一步：Agent 根据已授权范围处理重复启用或内容不符的来源；可复用原生按路径停用，不能自动覆盖 checkout 或重新启用已停用项。",
        "consumer_scope_bounded": "下一步：恢复完整 Desktop 项目枚举与只读访问后，继续你已请求的只读消费者检查；无需重复部署。",
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
        "- 平台发现：仅在能力未显示或宿主明确要求时刷新；已请求的只读检查可在原聊天继续。",
        "",
    ])
