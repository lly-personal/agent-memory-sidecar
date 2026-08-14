#!/usr/bin/env python3
"""Render a validated Global Owner Scout v5.5 Review Pack as deterministic Chinese Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Iterable

from utf8_stdio import configure_utf8_stdio

from validate_output import (
    ContractError,
    project_claim_hash,
    valid_project,
    valid_review_pack,
    validate_review_pack,
)


ACTION_LABELS = {
    "confirm": "确认",
    "edit": "修改",
    "keep_project": "留在项目",
    "make_skill": "改做 Skill",
    "ignore": "忽略",
}
SURFACES = {"interactive", "scheduled"}


def visible_body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def inbox_wrapper(pack: dict[str, Any]) -> str:
    count = len(pack["review_cards"])
    if pack["status"] in {"failed", "output_budget_exceeded"}:
        title = "Owner Scout：运行失败"
        summary = "本次没有可操作卡片，请查看完整失败终态。"
    elif pack["status"] == "no_material_delta":
        title = "Owner Scout：暂无新候选"
        summary = "事实普查已完成，本窗口没有新的 E2/E3 候选。"
    else:
        title = f"Owner Scout：{count} 项待判断"
        summary = "请在当前任务中审阅完整中文依据；可单选或一次选择多张可确认卡。"
    return f'::inbox-item{{title="{title}" summary="{summary}"}}'


def bullet_lines(items: Iterable[str], *, prefix: str = "- ") -> list[str]:
    values = list(items)
    return [f"{prefix}{item}" for item in values] if values else [f"{prefix}无"]


def render_evidence(items: list[dict[str, Any]]) -> list[str]:
    return [f"- `{item['type']} · {item['ref']}`：{item['summary']}" for item in items]


def action_command(action: str, card_id: str, selection_token: str | None = None) -> str:
    if action == "confirm":
        if not selection_token:
            raise ContractError("confirm action requires a selection token")
        return f"确认 {card_id}@{selection_token}"
    if action == "edit":
        return f"修改 {card_id}：<你的修改>"
    if action == "keep_project":
        return f"留在项目 {card_id}"
    if action == "make_skill":
        return f"改做 Skill {card_id}"
    return f"忽略 {card_id}"


def confirmable_card_selections(
    pack: dict[str, Any],
    cards_by_hash: dict[str, dict[str, Any]],
) -> list[str]:
    return [
        f"{cards_by_hash[review['project_claim_hash']]['card_id']}@{review['selection_token']}"
        for review in pack["review_cards"]
        if "confirm" in review["allowed_actions"]
    ]


def table_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def render_card(card: dict[str, Any], review: dict[str, Any], ordinal: int) -> list[str]:
    human = card["human_context"]
    preview = review["integration_preview"]
    support = card["project_support"]
    causal = card["causal_chain"]
    abstraction = card["abstraction"]
    rule = card["rule_payload"]
    research = preview["research"]
    before_after = preview["before_after"]
    recommended = review["recommended_action"]
    recommended_command = action_command(recommended, card["card_id"], review["selection_token"])
    lines = [
        f"## 决策卡 {ordinal}：{human['decision_title']}",
        "",
        f"`{card['card_id']}` · `{card['classification']} / {card['evidence_level']} / {support['count']} 个项目` · Owner `{card['owner_recommendation']}`",
        "",
        "> [!IMPORTANT]",
        f"> **推荐动作：`{recommended_command}`**  ",
        f"> {review['recommended_action_reason']}",
        "",
        "### 30 秒判断",
        "",
        "**项目里发生了什么**",
        "",
        human["project_story"],
        "",
        "| 判断维度 | 内容 |",
        "| --- | --- |",
        f"| 重复成本 | {table_cell(human['user_cost'])} |",
        f"| 建议结果 | {table_cell(human['recommended_outcome'])} |",
        f"| 最大反例 | {table_cell(human['strongest_counterpoint'])} |",
        "",
        "**接受前后**",
        "",
        "| 接受前 | 接受后 |",
        "| --- | --- |",
        f"| {table_cell(human['concrete_before'])} | {table_cell(human['concrete_after'])} |",
        "",
        f"**判断依据**：{card['evidence_level']}；独立项目支持 {support['count']}；{support['coverage_note']}；直接证据 `{', '.join(human['evidence_refs'])}`。",
        "",
        "### 完整核对依据",
        "",
        "#### 真实痛点与事件时间线",
        "",
        card["pain"],
        "",
    ]
    for item in card["event_timeline"]:
        lines.append(f"{item['order']}. {item['event']} → {item['outcome']}")
    lines.extend(
        [
            "",
            "#### 直接证据",
            "",
            *render_evidence(card["direct_evidence"]),
            "",
            "#### 反向证据与错误全局化风险",
            "",
            *bullet_lines(card["counterevidence"]["items"]),
            f"- 项目判断：{card['counterevidence']['globalization_risk']}",
            f"- 集成判断：{preview['globalization_risk']}",
            "",
            "#### 因果链与已接受变化",
            "",
            f"- 失败或重复：{causal['failure_or_repetition']}",
            f"- 已接受变化：{causal['accepted_change']}",
            f"- 可预防行为：{causal['preventive_behavior']}",
            f"- 证据边界：{causal['evidence_boundary']}",
            "",
            "#### 从项目事实到 Rule Projection",
            "",
            f"- 项目事实：{abstraction['project_specific']}",
            f"- 通用行为：{abstraction['generalized_behavior']}",
            "- 未晋升细节：",
            *bullet_lines(abstraction["removed_details"], prefix="  - "),
            f"- Owner 理由：{card['owner_rationale']}",
            "",
            "#### 外部一手调研",
            "",
            f"- 结论状态：`{research['status']}`",
            f"- 结论：{research['conclusion']}",
        ]
    )
    if research["sources"]:
        for source in research["sources"]:
            lines.append(f"- [{source['title']}]({source['url']})：{source['support']}")
    else:
        lines.append("- 来源：本候选不需要外部调研，或当前不可用。")
    lines.extend(
        [
            "",
            "#### 当前 global owner 关系",
            "",
            f"- 语义关系：`{preview['global_relation']}`",
            f"- 当前表达：{preview['owner_comparison']['current']}",
            f"- 缺口：{preview['owner_comparison']['gap']}",
            "",
            "#### 精确 Rule Projection：When / Do / Skip",
            "",
            f"- **When**：{rule['trigger']}",
            f"- **Do**：{rule['action']}",
            f"- **Skip**：{rule['skip_boundary']}",
            f"- 作用域：`{rule['scope']}`；目标：`{rule['instruction_target']}`",
            f"- 理由：{rule['why']}",
            f"- 证据摘要：{rule['evidence']}",
            "",
            "#### 预期行为与精确 Owner 变更",
            "",
            f"- 未来行为：{review['expected_behavior_change']}",
            f"- Before：{before_after['before']}",
            f"- After：{before_after['after']}",
            "- Unchanged：",
            *bullet_lines(before_after["unchanged"], prefix="  - "),
            "",
            "#### 反例、未证明事项与风险",
            "",
            "- 不应使用的反例：",
            *bullet_lines(card["anti_examples"], prefix="  - "),
            "- 尚未证明：",
            *bullet_lines(card["unproven"], prefix="  - "),
            "",
            "#### 你的单卡动作",
            "",
        ]
    )
    for action in review["allowed_actions"]:
        suffix = "（推荐）" if action == recommended else ""
        lines.append(f"- `{action_command(action, card['card_id'], review['selection_token'])}` — {ACTION_LABELS[action]}{suffix}")
    return lines


def render_review_pack(pack: dict[str, Any], *, surface: str) -> str:
    if surface not in SURFACES:
        raise ContractError(f"surface must be one of {sorted(SURFACES)}")
    pack = validate_review_pack(pack)
    project = pack["project_result"]
    coverage = project["session_coverage"]
    model = project["model_observation"]
    window = project["evidence_window"]
    proof = project["read_only_proof"]
    if surface == "interactive":
        if window["kind"] != "manual_30d":
            raise ContractError("interactive surface requires manual_30d")
        if proof["host_automation_memory_read"] or proof["host_automation_memory_updated"]:
            raise ContractError("interactive surface cannot use automation memory")
    else:
        if window["kind"] != "rolling_72h":
            raise ContractError("scheduled surface requires rolling_72h")
        if not proof["host_automation_memory_read"] or not proof["host_automation_memory_updated"]:
            raise ContractError("scheduled surface requires its bounded automation memory wrapper")
    cards_by_hash = {card["project_claim_hash"]: card for card in project["project_cards"]}
    lines = [
        f"# Global Owner Scout · {project['project_key']}",
        "",
        f"**终态**：`{pack['status']}`  ",
        f"**决策卡**：{len(pack['review_cards'])} 张  ",
        f"**Owner parity**：`{pack['owner_parity']['status']}`",
        "",
    ]
    if pack["status"] == "failed":
        pass
    elif coverage["status"] == "degraded":
        warning = "> 本次为 `degraded / session coverage unavailable`。下列卡片仍由独立 Owner、ADR、Git、测试或验收事实支持并完整展示。"
        if surface == "scheduled":
            warning += "本次不计入 14 次有效运行。"
        lines.extend(["> [!WARNING]", warning, ""])
    elif pack["status"] == "degraded":
        warning = "> 本次为 `degraded / evidence coverage limitation`。卡片保持可见；具体限制见覆盖摘要。"
        if surface == "scheduled":
            warning = "> 本次为 `degraded / evidence coverage limitation`。卡片保持可见，但本次不计入 14 次有效运行；具体限制见覆盖摘要。"
        lines.extend(["> [!WARNING]", warning, ""])
    if pack["owner_parity"]["status"] != "matched":
        lines.extend(
            [
                "> [!CAUTION]",
                "> canonical/local global owner 当前不一致或不可用；所有卡片保持可见，但“确认”动作已移除。",
                "",
            ]
        )
    if pack["status"] == "no_material_delta":
        lines.extend(["", "## 结果", "", "已完成事实普查、候选穷举与反证；本窗口没有新的 E2/E3 候选。"])
    elif pack["status"] == "failed":
        lines.extend(["", "## 失败", "", "本次运行未通过隐私、只读、完整性或来源门禁，没有输出可操作卡片。"])
    elif pack["status"] == "output_budget_exceeded":
        lines.extend(["", "## 容量失败", "", "完整卡片无法在一次结果中无损呈现，因此整次运行失败；没有输出部分卡片。"])
    else:
        decision_scope = "本次" if surface == "interactive" else "今日"
        lines.extend(["", f"## {decision_scope}需要判断 {len(pack['review_cards'])} 项", ""])
        lines.extend(["| # | 决策 | 推荐动作 | 证据 |", "| --- | --- | --- | --- |"])
        for index, review in enumerate(pack["review_cards"], start=1):
            card = cards_by_hash[review["project_claim_hash"]]
            support = card["project_support"]
            lines.append(
                f"| {index} | {table_cell(card['human_context']['decision_title'])} | "
                f"{ACTION_LABELS[review['recommended_action']]} | {card['evidence_level']} · {support['count']} 个项目 |"
            )
        confirmable = confirmable_card_selections(pack, cards_by_hash)
        if len(confirmable) > 1:
            lines.extend(
                [
                    "",
                    "### 一次确认多张",
                    "",
                    "选中的卡会在同一个最新 Owner 快照上联合重算，并作为一个原子规则包提交：全部成功，或整包零写入。若关系发生实质变化，只返回刷新预览，不写入。",
                    "",
                    f"- **一次确认命令**：`确认 {'、'.join(confirmable)}` — 确认全部当前可确认卡；可删除不想选择的完整 `card_id@token` 对。",
                ]
            )
        for index, review in enumerate(pack["review_cards"], start=1):
            lines.extend(["", *render_card(cards_by_hash[review["project_claim_hash"]], review, index)])

    lines.extend(
        [
            "",
            "## 技术附录",
            "",
            f"**证据窗口**：`{window['kind']}` · {window['start']} → {window['end']}  ",
            f"**模型请求**：`{model['requested_model']} + {model['requested_reasoning']}`  ",
            f"**实际模型**：`{model['actual_model'] or model['runtime_metadata_status']} + {model['actual_reasoning'] or model['runtime_metadata_status']}`",
            "",
            f"Session 覆盖：`{coverage['status']}`；发现 {coverage['discovered_task_count']}，窗口内 {coverage['window_task_count']}，选择 {coverage['selected_task_count']}，完整读取 {coverage['fully_read_task_count']}，读取 {coverage['turn_pages_read']} 页/轮；宿主上限 {coverage['task_index_limit']}；截断 `{str(coverage['truncated']).lower()}`。",
            "",
            "### 证据来源",
            "",
        ]
    )
    for source in project["evidence_sources"]:
        lines.append(f"- `{source['kind']} / {source['status']}`：{source['coverage']}")
    if project["limitations"]:
        lines.extend(["", "### 限制", "", *bullet_lines(project["limitations"])])
    lines.extend(["", "### E1 观察项", ""])
    if project["observations"]:
        for observation in project["observations"]:
            lines.append(f"- `{observation['observation_id']}`：{observation['summary']}（{observation['disposition']}）")
    else:
        lines.append("- 无。")

    body = "\n".join(lines).rstrip() + "\n"
    action_counts = [len(review["allowed_actions"]) for review in pack["review_cards"]]
    action_count = sum(action_counts)
    action_counts_text = ",".join(str(count) for count in action_counts) or "none"
    bundle_action_count = 1 if len(confirmable_card_selections(pack, cards_by_hash)) > 1 else 0
    wrapper_count = 1 if surface == "scheduled" else 0
    receipt = (
        f"校验回执：`surface={surface}`；"
        f"`review_pack_hash={pack['review_pack_hash']}`；"
        f"`visible_body_sha256={visible_body_sha256(body)}`；"
        f"`project_cards={len(project['project_cards'])}`；"
        f"`visible_cards={len(pack['review_cards'])}`；"
        f"`visible_action_counts={action_counts_text}`；"
        f"`visible_actions={action_count}`；"
        f"`bundle_action_count={bundle_action_count}`；"
        f"`wrapper_count={wrapper_count}`；守恒 `passed`。"
    )
    envelope = body + "---\n" + receipt + "\n"
    if surface == "scheduled":
        envelope += "\n" + inbox_wrapper(pack) + "\n"
    return envelope


def run_self_test() -> None:
    tests = 0
    for surface, decision_heading, wrapper_count in (
        ("interactive", "本次需要判断 2 项", 0),
        ("scheduled", "今日需要判断 2 项", 1),
    ):
        project = valid_project(window_kind="rolling_72h") if surface == "scheduled" else valid_project()
        rendered = render_review_pack(valid_review_pack(project), surface=surface)
        assert rendered.count("## 决策卡 ") == 2
        assert decision_heading in rendered and "30 秒判断" in rendered
        assert "完整核对依据" in rendered and "技术附录" in rendered
        assert rendered.index(decision_heading) < rendered.index("## 决策卡 1") < rendered.index("技术附录")
        assert "| 接受前 | 接受后 |" in rendered
        assert "确认 example-project-card-1@" in rendered
        assert "、example-project-card-2@" in rendered
        assert "全部成功，或整包零写入" in rendered
        assert f"surface={surface}" in rendered
        assert "review_pack_hash=" in rendered and "visible_body_sha256=" in rendered
        assert "visible_action_counts=5,5" in rendered and "visible_actions=10" in rendered
        assert "bundle_action_count=1" in rendered
        assert f"wrapper_count={wrapper_count}" in rendered
        assert rendered.count("::inbox-item{") == wrapper_count
        if surface == "scheduled":
            assert rendered.rstrip().endswith("}")
        else:
            assert "Scheduled" not in rendered and "Inbox" not in rendered and "0/14" not in rendered
            assert "今日需要判断" not in rendered and "14 次" not in rendered
        assert "{\"contract_version\"" not in rendered and "```json" not in rendered
        tests += 1

    degraded = render_review_pack(valid_review_pack(valid_project(status="degraded", coverage="degraded", observed=False)), surface="interactive")
    assert "degraded / session coverage unavailable" in degraded
    assert degraded.count("## 决策卡 ") == 2
    tests += 1

    request_only = render_review_pack(valid_review_pack(valid_project(observed=False)), surface="interactive")
    assert "request_only + request_only" in request_only
    assert "[!WARNING]" not in request_only
    tests += 1

    no_delta = render_review_pack(valid_review_pack(valid_project(status="no_material_delta")), surface="interactive")
    assert "本窗口没有新的 E2/E3 候选" in no_delta and "## 决策卡 " not in no_delta
    tests += 1

    failed = render_review_pack(valid_review_pack(valid_project(status="failed")), surface="interactive")
    assert "本次运行未通过" in failed and "## 决策卡 " not in failed
    assert "degraded / session coverage unavailable" not in failed
    tests += 1

    capacity = render_review_pack(valid_review_pack(valid_project(status="output_budget_exceeded")), surface="interactive")
    assert "容量失败" in capacity and "部分卡片" in capacity
    tests += 1

    drift = render_review_pack(valid_review_pack(parity_status="drift"), surface="interactive")
    assert "确认 example-project-card-1@" not in drift
    assert "一次确认多张" not in drift
    assert "修改 example-project-card-1" in drift
    tests += 1

    routed_project = valid_project(card_count=1)
    routed_card = routed_project["project_cards"][0]
    routed_card["classification"] = "route_to_owner"
    routed_card["owner_recommendation"] = "project_owner"
    routed_card["rule_payload"]["scope"] = "project"
    routed_card["rule_payload"]["instruction_target"] = "project_owner"
    routed_card["project_claim_hash"] = project_claim_hash(routed_card)
    routed = render_review_pack(valid_review_pack(routed_project), surface="interactive")
    assert "留在项目 example-project-card-1" in routed
    assert "留在项目（推荐）" in routed
    assert "确认 example-project-card-1@" not in routed
    tests += 1

    twenty_four = render_review_pack(valid_review_pack(valid_project(card_count=24)), surface="interactive")
    assert twenty_four.count("## 决策卡 ") == 24
    assert "project_cards=24" in twenty_four and "visible_cards=24" in twenty_four
    assert "visible_action_counts=" + ",".join(["5"] * 24) in twenty_four
    assert "visible_actions=120" in twenty_four
    assert "bundle_action_count=1" in twenty_four
    tests += 1

    print(json.dumps({"status": "ok", "tests": tests, "renderer": "global_owner_scout_review_pack_v4"}, separators=(",", ":")))


def load_stdin_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Render a validated Global Owner Scout Review Pack from stdin.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--surface", choices=sorted(SURFACES))
    args = parser.parse_args()
    try:
        if args.self_test:
            run_self_test()
            return 0
        if args.surface is None:
            raise ContractError("--surface is required")
        pack = load_stdin_json()
        if isinstance(pack, dict) and pack.get("contract_version") == "global_owner_scout_review_pack_v2":
            if args.surface != "scheduled":
                raise ContractError("legacy v2 Review Pack only supports the scheduled surface")
            from render_review_v4 import render_review_pack as render_legacy
            print(render_legacy(pack), end="")
        else:
            print(render_review_pack(pack, surface=args.surface), end="")
        return 0
    except (ContractError, AssertionError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
