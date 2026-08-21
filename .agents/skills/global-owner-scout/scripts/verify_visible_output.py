#!/usr/bin/env python3
"""Verify exact Global Owner Scout v5.6 renderer or artifact Markdown bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any

from utf8_stdio import configure_utf8_stdio

from validate_output import ContractError, valid_project, valid_review_pack


HASH = r"[0-9a-f]{64}"
RECEIPT_RE = re.compile(
    r"^校验回执：`surface=(?P<surface>interactive|scheduled)`；"
    rf"`review_pack_hash=(?P<pack>{HASH})`；"
    rf"`visible_body_sha256=(?P<body>{HASH})`；"
    r"`project_cards=(?P<project>\d+)`；"
    r"`visible_cards=(?P<visible>\d+)`；"
    r"`visible_action_counts=(?P<action_counts>none|\d+(?:,\d+)*)`；"
    r"`visible_actions=(?P<actions>\d+)`；"
    r"`bundle_action_count=(?P<bundle_actions>[01])`；"
    r"`wrapper_count=(?P<wrapper_count>[01])`；守恒 `passed`。$"
)
WRAPPER_RE = re.compile(r'^::inbox-item\{title="[^"\r\n]+" summary="[^"\r\n]+"\}$')
CARD_RE = re.compile(r"^## 决策卡 \d+：", re.MULTILINE)
ACTION_RE = re.compile(r"^- `(?:确认|修改|留在项目|改做 Skill|忽略) [^`]+` — ", re.MULTILINE)
BUNDLE_ACTION_RE = re.compile(
    r"^- \*\*一次确认命令\*\*：`确认 (?P<ids>[^`]+)` — ",
    re.MULTILINE,
)
CARD_BLOCK_RE = re.compile(r"(?ms)^## 决策卡 \d+：.*?(?=^## 决策卡 \d+：|^## 技术附录$)")
RAW_JSON_RE = re.compile(r'(?m)^\s*[\[{]\s*"(?:contract_version|mode|project_result|review_cards)"\s*:')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def verify_visible_output(value: str, *, surface: str) -> dict[str, Any]:
    require(surface in {"interactive", "scheduled"}, "surface must be interactive or scheduled")
    text = normalized_text(value)
    require(bool(text.strip()), "visible output must not be empty")
    require("```json" not in text.lower(), "visible output contains a JSON code fence")
    require(not RAW_JSON_RE.search(text), "visible output contains raw contract JSON")
    expected_wrapper_count = 1 if surface == "scheduled" else 0
    require(text.count("::inbox-item{") == expected_wrapper_count, "visible output wrapper count does not match surface")
    require(text.count("校验回执：") == 1, "visible output must contain exactly one validation receipt")

    marker = "---\n校验回执："
    require(text.count(marker) == 1, "validation receipt must follow one final Markdown separator")
    marker_index = text.index(marker)
    body = text[:marker_index]
    tail = text[marker_index:].rstrip("\n").split("\n")
    expected_tail_length = 4 if surface == "scheduled" else 2
    require(len(tail) == expected_tail_length, "receipt envelope contains manual trailing or inserted text")
    require(tail[0] == "---", "receipt envelope layout is invalid")
    receipt = RECEIPT_RE.fullmatch(tail[1])
    require(receipt is not None, "validation receipt is invalid")
    require(receipt.group("surface") == surface, "validation receipt surface mismatch")
    require(int(receipt.group("wrapper_count")) == expected_wrapper_count, "validation receipt wrapper count mismatch")
    if surface == "scheduled":
        require(tail[2] == "", "receipt envelope layout is invalid")
        require(WRAPPER_RE.fullmatch(tail[3]) is not None, "inbox wrapper is invalid or is not final")
        require("本次需要判断" not in body, "scheduled output contains interactive decision copy")
    else:
        for forbidden in ("Scheduled", "Inbox", "0/14", "今日需要判断", "14 次"):
            require(forbidden not in text, f"interactive output contains forbidden copy: {forbidden}")
        if CARD_RE.search(body):
            require("本次需要判断" in body, "interactive output is missing interactive decision copy")

    expected_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    require(receipt.group("body") == expected_hash, "visible body SHA-256 mismatch")
    project_cards = int(receipt.group("project"))
    visible_cards = int(receipt.group("visible"))
    visible_actions = int(receipt.group("actions"))
    bundle_actions = int(receipt.group("bundle_actions"))
    rendered_cards = len(CARD_RE.findall(body))
    rendered_actions = len(ACTION_RE.findall(body))
    rendered_bundle_actions = len(BUNDLE_ACTION_RE.findall(body))
    rendered_action_counts = [len(ACTION_RE.findall(block)) for block in CARD_BLOCK_RE.findall(body)]
    receipt_action_counts = (
        []
        if receipt.group("action_counts") == "none"
        else [int(value) for value in receipt.group("action_counts").split(",")]
    )
    require(project_cards == visible_cards == rendered_cards, "Project Card and visible card counts do not conserve")
    require(receipt_action_counts == rendered_action_counts, "per-card visible action counts do not conserve")
    require(visible_actions == rendered_actions, "visible action count does not conserve")
    require(
        bundle_actions == rendered_bundle_actions,
        "bundle action count does not conserve",
    )
    bundle_match = BUNDLE_ACTION_RE.search(body)
    if bundle_match is not None:
        bundle_ids = bundle_match.group("ids").split("、")
        require(
            len(bundle_ids) > 1 and len(set(bundle_ids)) == len(bundle_ids),
            "bundle action must select multiple unique cards",
        )
        for card_id in bundle_ids:
            require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}@[0-9a-f]{32}", card_id) is not None, "bundle action contains an invalid card selection")
            require(
                f"- `确认 {card_id}` — " in body,
                "bundle action references a card without a confirm action",
            )
    return {
        "status": "ok",
        "visible_body_sha256": expected_hash,
        "review_pack_hash": receipt.group("pack"),
        "project_cards": project_cards,
        "visible_cards": visible_cards,
        "visible_action_counts": rendered_action_counts,
        "visible_actions": visible_actions,
        "bundle_action_count": bundle_actions,
        "surface": surface,
        "wrapper_count": expected_wrapper_count,
    }


def replace_body_and_hash(rendered: str, transform) -> str:
    text = normalized_text(rendered)
    marker = "---\n校验回执："
    marker_index = text.index(marker)
    body = transform(text[:marker_index])
    tail = text[marker_index:]
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    tail = re.sub(r"visible_body_sha256=[0-9a-f]{64}", f"visible_body_sha256={body_hash}", tail, count=1)
    return body + tail


def expect_invalid(value: str, label: str, *, surface: str = "interactive") -> None:
    try:
        verify_visible_output(value, surface=surface)
    except ContractError:
        return
    raise AssertionError(f"expected invalid visible output: {label}")


def run_self_test() -> None:
    from render_review import render_review_pack

    tests = 0
    for surface in ("interactive", "scheduled"):
        for card_count in (1, 3, 24):
            project = valid_project(card_count=card_count, window_kind="rolling_72h" if surface == "scheduled" else "manual_30d")
            result = verify_visible_output(
                render_review_pack(valid_review_pack(project), surface=surface),
                surface=surface,
            )
            assert result["visible_cards"] == card_count
            assert result["wrapper_count"] == (1 if surface == "scheduled" else 0)
            tests += 1

    no_delta = render_review_pack(valid_review_pack(valid_project(status="no_material_delta", card_count=0)), surface="interactive")
    assert verify_visible_output(no_delta, surface="interactive")["visible_cards"] == 0
    tests += 1

    degraded = render_review_pack(valid_review_pack(valid_project(status="degraded", coverage="degraded", observed=False)), surface="interactive")
    assert verify_visible_output(degraded, surface="interactive")["visible_cards"] == 2
    tests += 1

    failed = render_review_pack(valid_review_pack(valid_project(status="failed", card_count=0)), surface="interactive")
    assert verify_visible_output(failed, surface="interactive")["visible_cards"] == 0
    tests += 1

    capacity = render_review_pack(valid_review_pack(valid_project(status="output_budget_exceeded", card_count=0)), surface="interactive")
    assert verify_visible_output(capacity, surface="interactive")["visible_cards"] == 0
    tests += 1

    drift = render_review_pack(valid_review_pack(parity_status="drift"), surface="interactive")
    assert verify_visible_output(drift, surface="interactive")["visible_cards"] == 2
    tests += 1

    one = render_review_pack(valid_review_pack(valid_project(card_count=1)), surface="interactive")
    expect_invalid(one.replace("项目里发生了什么", "项目发生了什么", 1), "body hash drift")
    tests += 1

    missing_action = replace_body_and_hash(one, lambda body: re.sub(r"^- `忽略 [^\n]+\n", "", body, count=1, flags=re.MULTILINE))
    expect_invalid(missing_action, "action loss with recomputed body hash")
    tests += 1

    three = render_review_pack(valid_review_pack(valid_project(card_count=3)), surface="interactive")

    def move_first_ignore(body: str) -> str:
        lines = body.splitlines(keepends=True)
        first_index = next(index for index, line in enumerate(lines) if line.startswith("- `忽略 example-project-card-1`"))
        first = lines.pop(first_index)
        second_index = next(index for index, line in enumerate(lines) if line.startswith("- `忽略 example-project-card-2`"))
        lines.insert(second_index + 1, first)
        return "".join(lines)

    moved_action = replace_body_and_hash(three, move_first_ignore)
    expect_invalid(moved_action, "per-card action movement with conserved total")
    tests += 1

    raw_json = replace_body_and_hash(one, lambda body: body + '{"contract_version":"forbidden"}\n')
    expect_invalid(raw_json, "raw JSON")
    tests += 1

    expect_invalid(one + "手工尾注\n", "manual trailing text")
    tests += 1
    expect_invalid(one + one.splitlines()[-1] + "\n", "duplicate wrapper")
    tests += 1
    expect_invalid(one[:-40], "truncated output")
    tests += 1

    scheduled = render_review_pack(valid_review_pack(valid_project(card_count=1, window_kind="rolling_72h")), surface="scheduled")
    expect_invalid(scheduled, "scheduled output on interactive verifier", surface="interactive")
    tests += 1
    expect_invalid(one, "interactive output on scheduled verifier", surface="scheduled")
    tests += 1

    print(json.dumps({"status": "ok", "tests": tests, "verifier": "global_owner_scout_visible_output_v1"}, separators=(",", ":")))


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Verify exact Global Owner Scout rendered Markdown from stdin.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--surface", choices=("interactive", "scheduled"))
    args = parser.parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            if args.surface is None:
                raise ContractError("--surface is required")
            result = verify_visible_output(sys.stdin.read(), surface=args.surface)
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
