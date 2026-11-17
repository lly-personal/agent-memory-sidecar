#!/usr/bin/env python3
"""Synthetic contract fixtures and self-test suite for Global Owner Scout validators."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


def _vo() -> Any:
    import validate_output

    return validate_output


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def valid_model(*, observed: bool = True, window_kind: str = "manual_30d") -> dict[str, Any]:
    vo = _vo()
    requested_model = vo.PILOT_MODEL if window_kind == "rolling_72h" else "gpt-5.6-terra"
    requested_reasoning = vo.PILOT_REASONING if window_kind == "rolling_72h" else "high"
    return {
        "requested_model": requested_model,
        "requested_reasoning": requested_reasoning,
        "policy_resolved_at": vo.PILOT_POLICY_DATE if window_kind == "rolling_72h" else "2026-08-12",
        "runtime_metadata_status": "observed" if observed else "request_only",
        "actual_model": requested_model if observed else None,
        "actual_reasoning": requested_reasoning if observed else None,
        "usage_status": "unavailable",
        "input_tokens": None,
        "output_tokens": None,
    }


def valid_read_only(*, scheduled: bool = False) -> dict[str, Any]:
    return {
        "snapshot_scope": "isolated_worktree",
        "before_context_snapshot_hash": sha("context"),
        "after_context_snapshot_hash": sha("context"),
        "before_head": "a" * 40,
        "after_head": "a" * 40,
        "before_status_hash": sha("status"),
        "after_status_hash": sha("status"),
        "before_staged_diff_hash": sha("staged"),
        "after_staged_diff_hash": sha("staged"),
        "before_unstaged_diff_hash": sha("unstaged"),
        "after_unstaged_diff_hash": sha("unstaged"),
        "diff_created": False,
        "external_write_observed": False,
        "host_automation_memory_read": scheduled,
        "host_automation_memory_updated": scheduled,
        "automation_memory_used_as_evidence": False,
        "concurrent_source_changes": False,
    }


def build_card(index: int = 1, project: str = "example-project") -> dict[str, Any]:
    vo = _vo()
    card: dict[str, Any] = {
        "card_id": f"{project}-card-{index}",
        "project_claim_hash": "",
        "human_context": {
            "display_locale": vo.DISPLAY_LOCALE,
            "decision_title": "是否要求完成声明以用户真正看到的结果为准？",
            "project_story": "项目中的底层检查已经通过，但用户要求的最终可见结果仍未出现。后续验收把判断点移到真实使用界面，才暴露出此前完成声明过早。",
            "user_cost": "用户需要重复追问并自行检查最终结果，增加了说明和验收成本。",
            "recommended_outcome": "把该行为提升为全局协作规则，并继续保留诊断型任务的明确例外。",
            "concrete_before": "底层机制通过后，任务可能直接报告整体完成。",
            "concrete_after": "只有用户要求的最终结果被实际观察后，任务才报告完成。",
            "strongest_counterpoint": "如果用户明确只要求诊断机制状态，底层检查本身就可以是最终结果。",
            "evidence_refs": ["event:visible-result"],
        },
        "classification": "add",
        "evidence_level": "E2",
        "project_support": {"count": 1, "project_refs": ["pref_" + sha(project)], "basis": "当前项目存在重复纠正与正式验收。", "coverage_note": "只证明一个项目，不伪装为跨项目共识。"},
        "normalized_evidence_hash": sha(f"evidence-{project}-{index}"),
        "owner_recommendation": "global_agents",
        "pain": "机制在用户可见结果出现前就被报告为完成，导致用户必须额外追问和复核。",
        "event_timeline": [
            {"order": 1, "event": "底层检查通过。", "outcome": "用户要求的可见结果仍然缺失。"},
            {"order": 2, "event": "验收移动到真实使用界面。", "outcome": "此前被掩盖的结果缺口变得可观察。"},
        ],
        "direct_evidence": [
            {"type": "acceptance", "ref": "event:visible-result", "summary": "最终可见结果经过了独立检查。"}
        ],
        "counterevidence": {
            "searched": True,
            "items": ["部分诊断任务的最终目标本来就是基础设施状态。"],
            "globalization_risk": "如果要求所有任务都产生界面产物，规则会被错误扩大。",
        },
        "causal_chain": {
            "failure_or_repetition": "代理机制完成被误认为用户目标完成。",
            "accepted_change": "验收改为绑定用户要求的可观察结果。",
            "preventive_behavior": "声明完成前先命名并检查终态用户结果。",
            "evidence_boundary": "现有证据只证明该项目模式，尚未证明跨项目采用。",
        },
        "abstraction": {
            "project_specific": "本地流水线检查没有产生用户要求的可见产物。",
            "removed_details": ["项目路径", "本地命令", "业务阈值"],
            "generalized_behavior": "不要把机制就绪当作用户终态结果已经成立的证据。",
        },
        "owner_rationale": "该行为可用于不相关项目，适合进入全局协作 Owner。",
        "anti_examples": ["用户只要求确认机制状态的诊断任务。"],
        "privacy_check": {"status": "passed", "removed": ["绝对路径", "原始对话", "完整命令"]},
        "unproven": ["尚未观察到跨项目采用。"],
        "rule_payload": {
            "trigger": "When claiming a requested workflow or mechanism is complete.",
            "action": "Verify the terminal user-visible outcome and label proxy-only proof as incomplete.",
            "skip_boundary": "Skip when the user explicitly requested only the proxy or diagnostic state.",
            "scope": "global",
            "why": "This avoids repeated false completion and follow-up verification cost.",
            "evidence": "Repeated correction plus acceptance against the real surface.",
            "instruction_target": "global_agents",
        },
    }
    card["normalized_evidence_hash"] = vo.canonical_hash(card["direct_evidence"])
    card["project_claim_hash"] = vo.project_claim_hash(card)
    return card


def valid_project(
    *,
    status: str = "ok",
    card_count: int = 2,
    coverage: str = "complete",
    observed: bool = True,
    window_kind: str = "manual_30d",
    execution_protocol_failed: bool = False,
    thread_pages_terminal_failure: bool = False,
) -> dict[str, Any]:
    vo = _vo()
    if status in {"no_material_delta", "failed", "output_budget_exceeded"}:
        card_count = 0
    truncated = coverage == "bounded"
    discovered = vo.PILOT_TASK_INDEX_LIMIT if truncated else 4
    selected = 3
    if execution_protocol_failed:
        status = "failed"
        coverage = "degraded"
        card_count = 0
    if thread_pages_terminal_failure:
        status = "degraded"
        coverage = "degraded"
        truncated = True
    limitations = ["Session 索引返回明确终态错误；本轮使用了正式项目证据。"] if status == "degraded" else []
    if execution_protocol_failed:
        limitations = ["原生任务执行协议未完成，本轮没有生成可操作卡片。"]
    if thread_pages_terminal_failure:
        limitations = ["至少一个相关任务分页返回明确终态错误；仅保留其他正式证据独立支持的卡片。"]
    project = {
        "contract_version": vo.LEGACY_PROJECT_CONTRACT,
        "mode": "project_scout",
        "status": status,
        "display_locale": vo.DISPLAY_LOCALE,
        "project_key": "example-project",
        "project_identity": {"identity_kind": "content", "content_identity_hash": "pci_" + sha("repo"), "host_project_ref_hash": "hpr_" + sha("host-project"), "git_worktree_eligible": True, "binding_status": "bound"},
        "run_id": "run-example",
        "task_id": "task-example",
        "skill_version": vo.SKILL_VERSION,
        "evidence_window": {"kind": window_kind, "start": "2026-07-08T00:00:00+08:00", "end": "2026-08-07T00:00:00+08:00"},
        "model_observation": valid_model(observed=observed, window_kind=window_kind),
        "owner_snapshot": {"project_instruction_hash": sha("owner"), "owners_read": ["项目 AGENTS", "项目 L1"]},
        "session_coverage": {
            "task_index_limit": vo.PILOT_TASK_INDEX_LIMIT,
            "index_pages_read": 2,
            "index_terminals": {"active": "has_more" if coverage == "bounded" else "failed" if coverage == "degraded" and not thread_pages_terminal_failure else "window_boundary", "archived": "eof"},
            "discovered_task_count": discovered,
            "window_task_count": 3,
            "selected_task_count": selected,
            "fully_read_task_count": selected - 1 if thread_pages_terminal_failure else selected if coverage != "degraded" else 0,
            "turn_pages_read": 4 if thread_pages_terminal_failure else 6 if coverage != "degraded" else 0,
            "excluded": [{"task_ref": "task:unrelated", "reason": "项目身份不一致。"}],
            "truncated": truncated,
            "status": coverage,
            "discovery_methods": (
                ["native_index_completed", "native_thread_pages_terminal_failure"]
                if thread_pages_terminal_failure
                else ["execution_protocol_failed"]
                if execution_protocol_failed
                else ["native_index_terminal_failure"]
                if coverage == "degraded"
                else ["native_index_host_cap", "native_thread_pages_completed"]
                if coverage == "bounded"
                else ["native_index_completed", "native_thread_pages_completed"]
            ),
        },
        "evidence_sources": [
            {
                "kind": "sessions",
                "status": "degraded" if thread_pages_terminal_failure else "unavailable" if coverage == "degraded" else "available",
                "coverage": "已检查窗口任务普查和所选任务分页。",
            },
            {"kind": "owners", "status": "available", "coverage": "已读取指令链和正式决策。"},
            {"kind": "acceptance", "status": "available", "coverage": "已检查测试与用户可见验收。"},
        ],
        "events": [],
        "observations": [
            {
                "observation_id": "obs-1",
                "evidence_level": "E1",
                "summary": "单次事件只有在后续重复后才可能成为可复用经验。",
                "direct_evidence": [{"type": "event", "ref": "event:single", "summary": "目前只观察到一次独立事件。"}],
                "disposition": "仅保留为观察项。",
            }
        ],
        "project_cards": [build_card(index + 1) for index in range(card_count)],
        "read_only_proof": valid_read_only(scheduled=window_kind == "rolling_72h"),
        "limitations": limitations,
    }
    # Synthetic contract fixtures only; never infer real discovery from cards.
    owner_ref = {"type": "owner", "ref": "owner:current", "summary": "当前正式规则及适用边界已读取。"}
    single_ref = {"type": "acceptance", "ref": "event:single", "summary": "目前只观察到一次独立事件。"}
    accepted_ref = {"type": "acceptance", "ref": "event:visible-result", "summary": "最终可见结果经过了独立检查。"}
    for source in project["evidence_sources"]:
        source["uncovered"] = []
        if source["status"] in {"degraded", "unavailable"}:
            source["uncovered"] = ["相关任务记录未能完整读取。"]
        source["refs"] = (
            [owner_ref] if source["kind"] == "owners" else
            [single_ref, accepted_ref] if source["kind"] == "acceptance" else
            [] if source["status"] == "unavailable" else
            [{"type": "session", "ref": "session:reviewed", "summary": "相关自然任务已读取到已声明边界。"}]
        )
    for kind in ("decisions", "successes", "failures"):
        project["evidence_sources"].append({
            "kind": kind, "status": "available", "coverage": "已读取相应正式来源及适用边界。",
            "refs": [{"type": kind, "ref": f"source:{kind}", "summary": "正式项目证据已核对。"}], "uncovered": [],
        })
    project["events"] = [{
        "event_id": "event:reviewed", "order": 1, "summary": "一次结果判断需要补充验收。",
        "before_belief": "仅凭局部状态推断结果。", "observed_change": "实际结果需要独立检查。",
        "accepted_result": "已记录当前证据边界。", "direct_evidence": [single_ref],
    }]
    observation = project["observations"][0]
    observation["direct_evidence"] = [copy.deepcopy(single_ref)]
    observation["event_ids"] = ["event:reviewed"]
    observation["disposition"] = {
        "kind": "insufficient_evidence", "reason": "尚缺重复、正式接受或真实验收，不能提升为规则。",
        "card_ids": [], "owner_refs": [], "local_scope": "当前项目的单次结果判断。",
        "portable_delta": "目前不足以证明独立的通用行为增量。",
    }
    for index, card in enumerate(project["project_cards"]):
        event_id = f"event:accepted-{index + 1}"
        project["events"].append({
            "event_id": event_id, "order": len(project["events"]) + 1, "summary": card["pain"],
            "before_belief": "仅凭局部状态推断结果。", "observed_change": "真实验收改变了原有判断。",
            "accepted_result": "正式接受该行为的适用边界。", "direct_evidence": copy.deepcopy(card["direct_evidence"]),
        })
        project["observations"].append({
            "observation_id": f"candidate-{index + 1}", "evidence_level": card["evidence_level"],
            "summary": card["pain"], "direct_evidence": copy.deepcopy(card["direct_evidence"]), "event_ids": [event_id],
            "disposition": {
                "kind": "candidate", "reason": "真实验收支持独立通用行为候选。", "card_ids": [card["card_id"]],
                "owner_refs": [], "local_scope": "项目当前用户表面的结果判断。",
                "portable_delta": "先验证真实结果再声明完成，并保留诊断任务例外。",
            },
        })
    return project


def valid_parity(status: str = "matched") -> dict[str, Any]:
    vo = _vo()
    source = sha("owner") if status != "unavailable" else None
    target = source if status == "matched" else (sha("other-owner") if status == "drift" else sha("local-owner"))
    parity = {
        "status": status,
        "canonical_source_ref": "canonical_global_agents",
        "canonical_source_hash": source,
        "local_target_ref": "host_local_global_agents",
        "local_target_hash": target,
        "snapshot_id": "",
    }
    parity["snapshot_id"] = vo.owner_snapshot_id(parity)
    return parity


def valid_review_pack(project: dict[str, Any] | None = None, *, parity_status: str = "matched") -> dict[str, Any]:
    vo = _vo()
    project = copy.deepcopy(project or valid_project())
    parity = valid_parity(parity_status)
    review_cards = []
    for card in project["project_cards"]:
        recommended, actions = vo.expected_action_policy(card, parity_status)
        reasons = {
            "confirm": "该候选建议进入全局 Owner，且当前 canonical 与本机 Owner 一致，可以精确选择一张或多张确认。",
            "keep_project": "该结论依赖项目专属事实，应先保留在项目 Owner 中。",
            "make_skill": "该结论描述可复用的多步骤方法，更适合沉淀为 Skill。",
            "ignore": "现有 Owner 已覆盖该行为，或当前证据不支持长期持久化。",
            "edit": "当前 Owner parity 或候选关系不允许直接确认，需要先刷新或修改卡片。",
        }
        review_cards.append(
            {
                "project_claim_hash": card["project_claim_hash"],
                "recommended_action": recommended,
                "recommended_action_reason": reasons[recommended],
                "integration_preview": {
                    "global_relation": ("already_covered_exact" if card["classification"] == "already_covered" else card["classification"] if card["classification"] in {"add", "replace", "consolidate"} else "route_supported"),
                    "research": {
                        "status": "official_supported",
                        "sources": [{"title": "Official scheduled tasks guidance", "url": "https://learn.chatgpt.com/docs/automations.md", "support": "官方资料要求在启用定时任务前验证结果是否便于审阅。"}],
                        "conclusion": "官方资料支持在定时运行前验证用户真正看到的结果。",
                    },
                    "owner_comparison": {"current": "当前 Owner 要求完成声明有证据支持。", "gap": "尚未明确区分代理机制证据与用户终态结果证据。"},
                    "before_after": {
                        "before": "机制检查通过后，任务可能直接报告整体完成。",
                        "after": "只有用户要求的终态界面产生证据后，任务才报告完成。",
                        "unchanged": ["现有写入授权边界保持不变。"],
                    },
                    "globalization_risk": "过度使用可能给只要求诊断状态的任务增加不必要的端到端检查。",
                    "repeat_status": "new",
                    "supersedes": [],
                },
                "selection_token": None,
                "expected_behavior_change": "后续任务会区分机制就绪与用户要求的真实结果。",
                "allowed_actions": copy.deepcopy(actions),
            }
        )
        if "confirm" in actions:
            review_cards[-1]["selection_token"] = vo.selection_token(
                card_id=card["card_id"],
                project_claim_hash=card["project_claim_hash"],
                proposal=card["rule_payload"],
                supersedes=review_cards[-1]["integration_preview"]["supersedes"],
                target_before_sha256=parity["canonical_source_hash"],
            )
    pack = {
        "contract_version": {vo.PROJECT_CONTRACT: vo.REVIEW_PACK_CONTRACT, vo.MAP_PROJECT_CONTRACT: vo.MAP_REVIEW_PACK_CONTRACT, vo.LEGACY_PROJECT_CONTRACT: vo.LEGACY_REVIEW_PACK_CONTRACT}[project['contract_version']],
        "mode": "review_pack",
        "status": project["status"],
        "display_locale": vo.DISPLAY_LOCALE,
        "skill_version": vo.SKILL_VERSION,
        "project_result": project,
        "owner_parity": parity,
        "review_cards": review_cards,
        "selection_preview": None,
        "limitations": copy.deepcopy(project["limitations"]),
        "review_pack_hash": "",
    }
    bundle = vo.review_bundle(pack)
    if bundle:
        projection = lambda: {"status": "ready", "projected_bytes": 250, "target_after_sha256": "d" * 64, "error_code": None}
        pack["selection_preview"] = {"core_artifact_sha256": "c" * 64, "error_code": None, "result": {
            "contract_version": "rule_bundle_preview_v1", "target_before_sha256": bundle["target_before_sha256"],
            "bundle_sha256": vo.canonical_hash(bundle), "before_bytes": 0, "budget_bytes": 8192,
            "items": [{"card_id": item["card_id"], **projection()} for item in bundle["items"]],
            "combined": {"card_ids": [item["card_id"] for item in bundle["items"]], **projection()},
        }}
    pack["review_pack_hash"] = vo.review_pack_hash(pack)
    return pack


def expect_invalid(value: dict[str, Any], validator: Callable[[Any], Any], label: str) -> None:
    vo = _vo()
    try:
        validator(value)
    except vo.ContractError:
        return
    raise AssertionError(f"expected invalid fixture: {label}")


def run_self_test() -> None:
    vo = _vo()
    tests = 0

    fixtures = [
        valid_project(),
        valid_project(observed=False),
        valid_project(status="degraded", coverage="degraded", observed=False),
        valid_project(status="no_material_delta", card_count=0),
        valid_project(status="failed", card_count=0),
        valid_project(status="output_budget_exceeded", card_count=0),
        valid_project(coverage="bounded"),
        valid_project(window_kind="rolling_72h"),
        valid_project(execution_protocol_failed=True),
        valid_project(thread_pages_terminal_failure=True),
    ]
    regular_forward_test = valid_project(window_kind="rolling_72h")
    regular_forward_test["read_only_proof"]["host_automation_memory_read"] = False
    regular_forward_test["read_only_proof"]["host_automation_memory_updated"] = False
    fixtures.append(regular_forward_test)
    for fixture in fixtures:
        vo.validate_project(fixture)
        tests += 1
        vo.validate_review_pack(valid_review_pack(fixture))
        tests += 1

    invalid = copy.deepcopy(fixtures[0])
    del invalid["session_coverage"]["turn_pages_read"]
    expect_invalid(invalid, vo.validate_project, "missing coverage field")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["session_coverage"]["task_index_limit"] = 1000
    expect_invalid(invalid, vo.validate_project, "oversized pilot task index")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["session_coverage"]["discovery_methods"] = ["原生任务索引", "项目身份匹配"]
    expect_invalid(invalid, vo.validate_project, "free-form discovery methods")
    tests += 1

    invalid = valid_project(status="degraded", coverage="degraded", observed=False)
    invalid["session_coverage"]["discovery_methods"] = ["native_index_completed"]
    expect_invalid(invalid, vo.validate_project, "degraded without terminal failure")
    tests += 1

    invalid = valid_project(thread_pages_terminal_failure=True)
    invalid["session_coverage"]["fully_read_task_count"] = invalid["session_coverage"]["selected_task_count"]
    expect_invalid(invalid, vo.validate_project, "thread page failure disguised as complete selected-task coverage")
    tests += 1

    invalid = valid_project(status="degraded", coverage="degraded", observed=False)
    invalid["session_coverage"]["discovery_methods"] = ["execution_protocol_failed"]
    expect_invalid(invalid, vo.validate_project, "protocol failure disguised as degraded result")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["read_only_proof"]["host_automation_memory_read"] = True
    expect_invalid(invalid, vo.validate_project, "manual run read automation memory")
    tests += 1

    invalid = valid_project(window_kind="rolling_72h")
    invalid["read_only_proof"]["host_automation_memory_updated"] = False
    expect_invalid(invalid, vo.validate_project, "scheduled run skipped required automation memory update")
    tests += 1

    invalid = valid_project(window_kind="rolling_72h")
    invalid["read_only_proof"]["automation_memory_used_as_evidence"] = True
    expect_invalid(invalid, vo.validate_project, "automation memory used as evidence")
    tests += 1

    inherited = valid_project(window_kind="manual_30d")
    vo.require(inherited["model_observation"]["requested_model"] != vo.PILOT_MODEL, "manual fixture did not inherit a non-pilot model")
    vo.validate_project(inherited)
    tests += 1

    invalid = valid_project(window_kind="manual_30d")
    invalid["model_observation"]["actual_model"] = "different-model"
    expect_invalid(invalid, vo.validate_project, "manual actual model differs from requested")
    tests += 1

    invalid = valid_project(window_kind="rolling_72h")
    invalid["model_observation"]["requested_reasoning"] = "high"
    invalid["model_observation"]["actual_reasoning"] = "high"
    expect_invalid(invalid, vo.validate_project, "scheduled reasoning differs from pilot")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "See C:\\private\\evidence.txt"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "absolute path leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "git push origin main"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "command leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "api_key=" + "sk-" + "private-example-value"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "secret leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "<response-annotations>原始对话片段</response-annotations>"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "raw transcript leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["pain"] = "This sentence is intentionally long enough to prove that an English-only user-facing narrative is rejected."
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "English-only user narrative")
    tests += 1

    valid_tech = copy.deepcopy(fixtures[0])
    valid_tech["project_cards"][0]["pain"] = (
        "静态盘点入口已定位。`skills/lly-workflow-eval/scripts/lib/resources-pi.mjs` -> "
        "`inspectPiCallerSkillsDetails` (`pi_caller_skill_patterns_unobserved`)"
    )
    valid_tech["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(valid_tech["project_cards"][0])
    vo.validate_project(valid_tech)
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["concrete_before"] = "`skills/lly-workflow-eval/scripts/lib/resources-pi.mjs`"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "pure-code human_context without Han")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["evidence_refs"] = ["event:missing"]
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "human context evidence reference")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["decision_title"] = "是否应该把一个超过六十个字符且无法快速扫描的项目决策标题继续展示给用户，从而再次增加本来可以避免的阅读和判断负担并破坏三十秒判断目标？"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "oversized decision title")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["project_story"] = "第一段。\n\n第二段。\n\n第三段。\n\n第四段。"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "too many project story paragraphs")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["evidence_level"] = "E1"
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "E1 promotion")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["project_support"]["project_refs"] = ["raw-project-name"]
    invalid["project_cards"][0]["project_claim_hash"] = vo.project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, vo.validate_project, "non-opaque project support")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["model_observation"]["actual_reasoning"] = "xhigh"
    expect_invalid(invalid, vo.validate_project, "model mismatch")
    tests += 1

    invalid = valid_project(status="output_budget_exceeded")
    invalid["project_cards"] = [build_card()]
    expect_invalid(invalid, vo.validate_project, "partial capacity output")
    tests += 1

    pack = valid_review_pack()
    invalid = copy.deepcopy(pack)
    invalid["review_cards"].pop()
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "silent card truncation")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_cards"].reverse()
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "card order drift")
    tests += 1

    drift = valid_review_pack(parity_status="drift")
    vo.validate_review_pack(drift)
    tests += 1
    invalid = copy.deepcopy(drift)
    invalid["review_cards"][0]["allowed_actions"].insert(0, "confirm")
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "confirm during owner drift")
    tests += 1

    routed_project = valid_project(card_count=1)
    routed_card = routed_project["project_cards"][0]
    routed_card["classification"] = "route_to_owner"
    routed_card["owner_recommendation"] = "project_owner"
    routed_card["rule_payload"]["scope"] = "project"
    routed_card["rule_payload"]["instruction_target"] = "project_owner"
    routed_card["project_claim_hash"] = vo.project_claim_hash(routed_card)
    routed = valid_review_pack(routed_project)
    vo.validate_review_pack(routed)
    vo.require(routed["review_cards"][0]["recommended_action"] == "keep_project", "route_to_owner recommendation mismatch")
    vo.require("confirm" not in routed["review_cards"][0]["allowed_actions"], "route_to_owner must not allow confirm")
    tests += 1

    skill_project = valid_project(card_count=1)
    skill_card = skill_project["project_cards"][0]
    skill_card["owner_recommendation"] = "skill"
    skill_card["rule_payload"]["scope"] = "skill"
    skill_card["rule_payload"]["instruction_target"] = "skill"
    skill_card["project_claim_hash"] = vo.project_claim_hash(skill_card)
    skill_pack = valid_review_pack(skill_project)
    vo.validate_review_pack(skill_pack)
    vo.require(skill_pack["review_cards"][0]["recommended_action"] == "make_skill", "Skill recommendation mismatch")
    vo.require("confirm" not in skill_pack["review_cards"][0]["allowed_actions"], "Skill card must not allow confirm")
    tests += 1

    unavailable = valid_review_pack(parity_status="unavailable")
    vo.validate_review_pack(unavailable)
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["owner_parity"]["snapshot_id"] = sha("wrong")
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "nondeterministic parity identity")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["owner_parity"]["local_target_ref"] = "project_root_agents"
    invalid["owner_parity"]["snapshot_id"] = vo.owner_snapshot_id(invalid["owner_parity"])
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "project owner substituted for global target")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_cards"][0]["integration_preview"]["research"]["sources"][0]["url"] = "file://private"
    invalid["review_pack_hash"] = vo.review_pack_hash(invalid)
    expect_invalid(invalid, vo.validate_review_pack, "private research source")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_pack_hash"] = sha("wrong")
    expect_invalid(invalid, vo.validate_review_pack, "review pack hash mismatch")
    tests += 1

    old_contract = copy.deepcopy(pack)
    old_contract["contract_version"] = "global_owner_scout_digest_manifest_v3"
    old_contract["mode"] = "central_manifest"
    old_contract["review_pack_hash"] = vo.review_pack_hash(old_contract)
    expect_invalid(old_contract, vo.validate_review_pack, "removed central manifest")
    tests += 1

    old_review_pack = copy.deepcopy(pack)
    old_review_pack["contract_version"] = "global_owner_scout_review_pack_v2"
    old_review_pack["review_pack_hash"] = vo.review_pack_hash(old_review_pack)
    expect_invalid(old_review_pack, vo.validate_review_pack, "old Review Pack contract")
    tests += 1

    old_project = copy.deepcopy(fixtures[0])
    old_project["contract_version"] = "global_owner_scout_project_v3"
    expect_invalid(old_project, vo.validate_project, "old Project contract")
    tests += 1

    baseline = valid_project(card_count=24)
    vo.validate_review_pack(valid_review_pack(baseline))
    tests += 1

    print(
        json.dumps(
            {
                "status": "ok",
                "tests": tests,
                "baseline_project_card_count": 24,
                "active_modes": ["project_scout", "review_pack"],
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    _vo().configure_utf8_stdio()
    run_self_test()
