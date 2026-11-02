#!/usr/bin/env python3
"""Validate Global Owner Scout v4 project results and directly visible review packs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from typing import Any, Callable, Iterable

from utf8_stdio import configure_utf8_stdio


SKILL_VERSION = "4.0.0"
PROJECT_CONTRACT = "global_owner_scout_project_v3"
REVIEW_PACK_CONTRACT = "global_owner_scout_review_pack_v2"
DISPLAY_LOCALE = "zh-CN"
PILOT_MODEL = "gpt-5.6-sol"
PILOT_REASONING = "medium"
PILOT_POLICY_DATE = "2026-08-06"
CONFIGURED_PROJECT_COUNT = 3
PILOT_TASK_INDEX_LIMIT = 50

STATUSES = {"ok", "degraded", "no_material_delta", "failed", "output_budget_exceeded"}
COVERAGE_STATUSES = {"complete", "bounded", "degraded"}
CLASSIFICATIONS = {"already_covered", "add", "replace", "consolidate", "route_to_owner"}
OWNER_RECOMMENDATIONS = {"project_owner", "skill", "global_agents", "no_persistence"}
GLOBAL_RELATIONS = {
    "already_covered_exact",
    "add",
    "replace",
    "consolidate",
    "route_supported",
    "globalization_challenged",
    "needs_project_clarification",
}
RESEARCH_STATUSES = {"official_supported", "official_challenged", "mixed", "not_required", "unavailable"}
REPEAT_STATUSES = {"new", "repeated_unchanged", "unknown"}
ALL_ACTIONS = ["confirm", "edit", "keep_project", "make_skill", "ignore"]
READ_ONLY_ACTIONS = ["edit", "keep_project", "make_skill", "ignore"]

PROJECT_CLAIM_FIELDS = (
    "card_id",
    "human_context",
    "classification",
    "evidence_level",
    "project_support",
    "normalized_evidence_hash",
    "owner_recommendation",
    "pain",
    "event_timeline",
    "direct_evidence",
    "counterevidence",
    "causal_chain",
    "abstraction",
    "owner_rationale",
    "anti_examples",
    "privacy_check",
    "unproven",
    "rule_payload",
)

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")
WINDOWS_ABS_RE = re.compile(r"(?i)(?:^|[\s\"'(])(?:[a-z]:[\\/])")
UNC_RE = re.compile(r"(?:^|[\s\"'(])\\\\[^\\\s]+\\")
POSIX_PRIVATE_RE = re.compile(r"(?:^|\s)/(?:home|Users|root|mnt|tmp)/")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization)\b\s*[:=]\s*\S+"
)
COMMAND_RE = re.compile(
    r"(?im)(?:^|[\n;])\s*(?:git|python|py|pwsh|powershell|cmd|curl|wget|npm|npx|gh|rg|pytest|Invoke-[A-Za-z]+)\s+(?:--?\S+|\S+\s*)"
)
RAW_MARKERS = ("<codex_delegation>", "<response-annotations>", "BEGIN PRIVATE KEY", "turn_context", "response_item")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
LONG_SENTENCE_SPLIT_RE = re.compile(r"(?:[。！？!?]\s*|\.\s+|\n+)")
LANGUAGE_EXEMPT_PATH_PARTS = (
    ".rule_payload.",
    ".before_after.before",
    ".before_after.after",
    ".ref",
    ".url",
    ".project_key",
    ".run_id",
    ".task_id",
    ".card_id",
    ".project_claim_hash",
    ".normalized_evidence_hash",
    ".snapshot_id",
    "_hash",
    ".requested_model",
    ".actual_model",
    ".requested_reasoning",
    ".actual_reasoning",
    ".policy_resolved_at",
    ".contract_version",
    ".skill_version",
    ".mode",
    ".status",
    ".display_locale",
    ".evidence_level",
    ".classification",
    ".owner_recommendation",
    ".global_relation",
    ".repeat_status",
    ".recommended_action",
    ".allowed_actions",
    ".scope",
    ".instruction_target",
)


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_object(value: Any, path: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{path} must be an object")
    return value


def require_list(value: Any, path: str, *, nonempty: bool = False) -> list[Any]:
    require(isinstance(value, list), f"{path} must be an array")
    if nonempty:
        require(bool(value), f"{path} must not be empty")
    return value


def require_string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    require(isinstance(value, str), f"{path} must be a string")
    if not allow_empty:
        require(bool(value.strip()), f"{path} must not be empty")
    return value


def validate_zh_cn_text(value: Any, path: str, *, max_chars: int | None = None) -> str:
    text = require_string(value, path)
    if max_chars is not None:
        require(len(text) <= max_chars, f"{path} must be <= {max_chars} characters")
    for sentence in LONG_SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if len(sentence) > 40:
            require(bool(HAN_RE.search(sentence)), f"{path} contains an English-only sentence longer than 40 characters")
    return text


def validate_user_facing_language(value: Any) -> None:
    for path, text in walk_strings(value):
        if any(part in path for part in LANGUAGE_EXEMPT_PATH_PARTS):
            continue
        validate_zh_cn_text(text, path)


def require_int(value: Any, path: str, *, minimum: int = 0) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{path} must be an integer")
    require(value >= minimum, f"{path} must be >= {minimum}")
    return value


def require_exact_keys(value: dict[str, Any], expected: Iterable[str], path: str) -> None:
    expected_set = set(expected)
    missing = sorted(expected_set - set(value))
    extra = sorted(set(value) - expected_set)
    require(not missing and not extra, f"{path} keys mismatch; missing={missing}, extra={extra}")


def validate_hash(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    text = require_string(value, path)
    require(bool(HASH_RE.fullmatch(text)), f"{path} must be lowercase SHA-256")
    return text


def validate_git_id(value: Any, path: str) -> str:
    text = require_string(value, path)
    require(bool(GIT_ID_RE.fullmatch(text)), f"{path} must be a Git object id")
    return text


def validate_iso(value: Any, path: str) -> datetime:
    text = require_string(value, path)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{path} must be ISO-8601") from exc


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def hash_without_field(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    return canonical_hash(payload)


def project_claim_hash(card: dict[str, Any]) -> str:
    return canonical_hash({field: card[field] for field in PROJECT_CLAIM_FIELDS})


def owner_snapshot_id(parity: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "status": parity["status"],
            "canonical_source_ref": parity["canonical_source_ref"],
            "canonical_source_hash": parity["canonical_source_hash"],
            "local_target_ref": parity["local_target_ref"],
            "local_target_hash": parity["local_target_hash"],
        }
    )


def review_pack_hash(pack: dict[str, Any]) -> str:
    return hash_without_field(pack, "review_pack_hash")


def walk_strings(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f"{path}[{index}]")


def validate_privacy_surface(value: Any) -> None:
    for path, text in walk_strings(value):
        require(not WINDOWS_ABS_RE.search(text), f"{path} contains an absolute Windows path")
        require(not UNC_RE.search(text), f"{path} contains a UNC path")
        require(not POSIX_PRIVATE_RE.search(text), f"{path} contains a private POSIX path")
        require("file://" not in text.lower(), f"{path} contains a file URI")
        require(not SECRET_ASSIGNMENT_RE.search(text), f"{path} contains a secret-like assignment")
        require(not COMMAND_RE.search(text), f"{path} contains a complete command")
        for marker in RAW_MARKERS:
            require(marker not in text, f"{path} contains raw transcript or internal diagnostic material")


def validate_model_observation(value: Any, path: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(
        obj,
        {
            "requested_model",
            "requested_reasoning",
            "policy_resolved_at",
            "runtime_metadata_status",
            "actual_model",
            "actual_reasoning",
            "usage_status",
            "input_tokens",
            "output_tokens",
        },
        path,
    )
    require(obj["requested_model"] == PILOT_MODEL, f"{path}.requested_model must be {PILOT_MODEL}")
    require(obj["requested_reasoning"] == PILOT_REASONING, f"{path}.requested_reasoning must be {PILOT_REASONING}")
    require(obj["policy_resolved_at"] == PILOT_POLICY_DATE, f"{path}.policy_resolved_at must be {PILOT_POLICY_DATE}")
    metadata_status = obj["runtime_metadata_status"]
    require(metadata_status in {"observed", "request_only", "unavailable"}, f"{path}.runtime_metadata_status invalid")
    if metadata_status == "observed":
        require(obj["actual_model"] == PILOT_MODEL, f"{path}.actual_model does not match pilot")
        require(obj["actual_reasoning"] == PILOT_REASONING, f"{path}.actual_reasoning does not match pilot")
    else:
        require(obj["actual_model"] is None and obj["actual_reasoning"] is None, f"{path} unobserved actual metadata must be null")
    usage_status = obj["usage_status"]
    require(usage_status in {"available", "unavailable"}, f"{path}.usage_status invalid")
    if usage_status == "available":
        require_int(obj["input_tokens"], f"{path}.input_tokens")
        require_int(obj["output_tokens"], f"{path}.output_tokens")
    else:
        require(obj["input_tokens"] is None and obj["output_tokens"] is None, f"{path} unavailable usage must be null")


def validate_evidence_refs(value: Any, path: str, *, nonempty: bool = True) -> None:
    refs = require_list(value, path, nonempty=nonempty)
    for index, raw in enumerate(refs):
        item_path = f"{path}[{index}]"
        item = require_object(raw, item_path)
        require_exact_keys(item, {"type", "ref", "summary"}, item_path)
        require_string(item["type"], f"{item_path}.type")
        reference = require_string(item["ref"], f"{item_path}.ref")
        require("/" not in reference and "\\" not in reference, f"{item_path}.ref must be a logical reference")
        require_string(item["summary"], f"{item_path}.summary")


def validate_session_coverage(value: Any, path: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(
        obj,
        {
            "task_index_limit",
            "discovered_task_count",
            "window_task_count",
            "selected_task_count",
            "fully_read_task_count",
            "turn_pages_read",
            "excluded",
            "truncated",
            "status",
            "discovery_methods",
        },
        path,
    )
    limit = require_int(obj["task_index_limit"], f"{path}.task_index_limit", minimum=1)
    require(limit == PILOT_TASK_INDEX_LIMIT, f"{path}.task_index_limit must be {PILOT_TASK_INDEX_LIMIT} during the v4 pilot")
    discovered = require_int(obj["discovered_task_count"], f"{path}.discovered_task_count")
    window = require_int(obj["window_task_count"], f"{path}.window_task_count")
    selected = require_int(obj["selected_task_count"], f"{path}.selected_task_count")
    read = require_int(obj["fully_read_task_count"], f"{path}.fully_read_task_count")
    require_int(obj["turn_pages_read"], f"{path}.turn_pages_read")
    require(read <= selected <= window <= discovered <= limit, f"{path} counts are inconsistent")
    require(isinstance(obj["truncated"], bool), f"{path}.truncated must be boolean")
    status = obj["status"]
    require(status in COVERAGE_STATUSES, f"{path}.status invalid")
    if status == "complete":
        require(not obj["truncated"] and read == selected, f"{path} complete coverage is inconsistent")
    if status == "bounded":
        require(obj["truncated"] and discovered == limit and read == selected, f"{path} bounded coverage must prove the host limit")
    excluded = require_list(obj["excluded"], f"{path}.excluded")
    for index, raw in enumerate(excluded):
        item_path = f"{path}.excluded[{index}]"
        item = require_object(raw, item_path)
        require_exact_keys(item, {"task_ref", "reason"}, item_path)
        require_string(item["task_ref"], f"{item_path}.task_ref")
        require_string(item["reason"], f"{item_path}.reason")
    methods = require_list(obj["discovery_methods"], f"{path}.discovery_methods", nonempty=True)
    for index, item in enumerate(methods):
        require_string(item, f"{path}.discovery_methods[{index}]")


def validate_rule_payload(value: Any, path: str) -> None:
    obj = require_object(value, path)
    fields = {"trigger", "action", "skip_boundary", "scope", "why", "evidence", "instruction_target"}
    require_exact_keys(obj, fields, path)
    for field in fields:
        require_string(obj[field], f"{path}.{field}")
    target = obj["instruction_target"]
    require(target in {"project_agents", "global_agents", "project_owner", "skill", "none"}, f"{path}.instruction_target invalid")
    if target == "global_agents":
        require(obj["scope"] == "global", f"{path}.scope must be global for global_agents")
    if target in {"project_agents", "project_owner"}:
        require(obj["scope"] == "project", f"{path}.scope must be project for project owner")


def validate_project_support(value: Any, path: str, level: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(obj, {"count", "total", "projects"}, path)
    count = require_int(obj["count"], f"{path}.count", minimum=1)
    total = require_int(obj["total"], f"{path}.total", minimum=1)
    require(total == CONFIGURED_PROJECT_COUNT, f"{path}.total must be {CONFIGURED_PROJECT_COUNT}")
    require(count <= total, f"{path}.count exceeds total")
    projects = [require_string(item, f"{path}.projects[{index}]") for index, item in enumerate(require_list(obj["projects"], f"{path}.projects", nonempty=True))]
    require(len(projects) == count and len(projects) == len(set(projects)), f"{path}.projects must be unique and match count")
    if level == "E3":
        require(count >= 2, f"{path} E3 requires at least two projects")


def validate_human_context(value: Any, path: str, direct_evidence: list[dict[str, Any]]) -> None:
    obj = require_object(value, path)
    fields = {
        "display_locale",
        "decision_title",
        "project_story",
        "user_cost",
        "recommended_outcome",
        "concrete_before",
        "concrete_after",
        "strongest_counterpoint",
        "evidence_refs",
    }
    require_exact_keys(obj, fields, path)
    require(obj["display_locale"] == DISPLAY_LOCALE, f"{path}.display_locale must be {DISPLAY_LOCALE}")
    validate_zh_cn_text(obj["decision_title"], f"{path}.decision_title", max_chars=60)
    story = validate_zh_cn_text(obj["project_story"], f"{path}.project_story")
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", story) if paragraph.strip()]
    require(1 <= len(paragraphs) <= 3, f"{path}.project_story must contain 1 to 3 paragraphs")
    for index, paragraph in enumerate(paragraphs):
        require(len(paragraph) <= 300, f"{path}.project_story paragraph {index + 1} must be <= 300 characters")
    for field in (
        "user_cost",
        "recommended_outcome",
        "concrete_before",
        "concrete_after",
        "strongest_counterpoint",
    ):
        validate_zh_cn_text(obj[field], f"{path}.{field}", max_chars=240)
    refs = require_list(obj["evidence_refs"], f"{path}.evidence_refs", nonempty=True)
    direct_refs = {item["ref"] for item in direct_evidence}
    for index, ref in enumerate(refs):
        require_string(ref, f"{path}.evidence_refs[{index}]")
        require(ref in direct_refs, f"{path}.evidence_refs[{index}] must reference direct_evidence")
    require(len(refs) == len(set(refs)), f"{path}.evidence_refs must be unique")


def validate_project_card(value: Any, path: str) -> dict[str, Any]:
    obj = require_object(value, path)
    require_exact_keys(obj, set(PROJECT_CLAIM_FIELDS) | {"project_claim_hash"}, path)
    require_string(obj["card_id"], f"{path}.card_id")
    require(obj["classification"] in CLASSIFICATIONS, f"{path}.classification invalid")
    level = obj["evidence_level"]
    require(level in {"E2", "E3"}, f"{path}.evidence_level must be E2 or E3")
    validate_project_support(obj["project_support"], f"{path}.project_support", level)
    validate_hash(obj["normalized_evidence_hash"], f"{path}.normalized_evidence_hash")
    require(obj["owner_recommendation"] in OWNER_RECOMMENDATIONS, f"{path}.owner_recommendation invalid")
    require_string(obj["pain"], f"{path}.pain")
    timeline = require_list(obj["event_timeline"], f"{path}.event_timeline", nonempty=True)
    orders: list[int] = []
    for index, raw in enumerate(timeline):
        item_path = f"{path}.event_timeline[{index}]"
        item = require_object(raw, item_path)
        require_exact_keys(item, {"order", "event", "outcome"}, item_path)
        orders.append(require_int(item["order"], f"{item_path}.order", minimum=1))
        require_string(item["event"], f"{item_path}.event")
        require_string(item["outcome"], f"{item_path}.outcome")
    require(orders == list(range(1, len(orders) + 1)), f"{path}.event_timeline order must be contiguous")
    validate_evidence_refs(obj["direct_evidence"], f"{path}.direct_evidence")
    validate_human_context(obj["human_context"], f"{path}.human_context", obj["direct_evidence"])
    counter = require_object(obj["counterevidence"], f"{path}.counterevidence")
    require_exact_keys(counter, {"searched", "items", "globalization_risk"}, f"{path}.counterevidence")
    require(counter["searched"] is True, f"{path}.counterevidence.searched must be true")
    for index, item in enumerate(require_list(counter["items"], f"{path}.counterevidence.items", nonempty=True)):
        require_string(item, f"{path}.counterevidence.items[{index}]")
    require_string(counter["globalization_risk"], f"{path}.counterevidence.globalization_risk")
    causal = require_object(obj["causal_chain"], f"{path}.causal_chain")
    causal_fields = {"failure_or_repetition", "accepted_change", "preventive_behavior", "evidence_boundary"}
    require_exact_keys(causal, causal_fields, f"{path}.causal_chain")
    for field in causal_fields:
        require_string(causal[field], f"{path}.causal_chain.{field}")
    abstraction = require_object(obj["abstraction"], f"{path}.abstraction")
    require_exact_keys(abstraction, {"project_specific", "removed_details", "generalized_behavior"}, f"{path}.abstraction")
    require_string(abstraction["project_specific"], f"{path}.abstraction.project_specific")
    for index, item in enumerate(require_list(abstraction["removed_details"], f"{path}.abstraction.removed_details", nonempty=True)):
        require_string(item, f"{path}.abstraction.removed_details[{index}]")
    require_string(abstraction["generalized_behavior"], f"{path}.abstraction.generalized_behavior")
    require_string(obj["owner_rationale"], f"{path}.owner_rationale")
    for field in ("anti_examples", "unproven"):
        for index, item in enumerate(require_list(obj[field], f"{path}.{field}", nonempty=True)):
            require_string(item, f"{path}.{field}[{index}]")
    privacy = require_object(obj["privacy_check"], f"{path}.privacy_check")
    require_exact_keys(privacy, {"status", "removed"}, f"{path}.privacy_check")
    require(privacy["status"] == "passed", f"{path}.privacy_check.status must be passed")
    for index, item in enumerate(require_list(privacy["removed"], f"{path}.privacy_check.removed", nonempty=True)):
        require_string(item, f"{path}.privacy_check.removed[{index}]")
    validate_rule_payload(obj["rule_payload"], f"{path}.rule_payload")
    stored = validate_hash(obj["project_claim_hash"], f"{path}.project_claim_hash")
    require(stored == project_claim_hash(obj), f"{path}.project_claim_hash mismatch")
    return obj


def validate_read_only_proof(value: Any, path: str, status: str, window_kind: str) -> None:
    obj = require_object(value, path)
    fields = {
        "snapshot_scope",
        "before_head",
        "after_head",
        "before_status_hash",
        "after_status_hash",
        "before_staged_diff_hash",
        "after_staged_diff_hash",
        "before_unstaged_diff_hash",
        "after_unstaged_diff_hash",
        "diff_created",
        "external_write_observed",
        "host_automation_memory_read",
        "host_automation_memory_updated",
        "automation_memory_used_as_evidence",
        "concurrent_source_changes",
    }
    require_exact_keys(obj, fields, path)
    require(obj["snapshot_scope"] == "isolated_worktree", f"{path}.snapshot_scope invalid")
    validate_git_id(obj["before_head"], f"{path}.before_head")
    validate_git_id(obj["after_head"], f"{path}.after_head")
    for field in fields & {
        "before_status_hash", "after_status_hash", "before_staged_diff_hash", "after_staged_diff_hash",
        "before_unstaged_diff_hash", "after_unstaged_diff_hash",
    }:
        validate_hash(obj[field], f"{path}.{field}")
    for field in (
        "diff_created",
        "external_write_observed",
        "host_automation_memory_read",
        "host_automation_memory_updated",
        "automation_memory_used_as_evidence",
        "concurrent_source_changes",
    ):
        require(isinstance(obj[field], bool), f"{path}.{field} must be boolean")
    unchanged = (
        obj["before_head"] == obj["after_head"]
        and obj["before_status_hash"] == obj["after_status_hash"]
        and obj["before_staged_diff_hash"] == obj["after_staged_diff_hash"]
        and obj["before_unstaged_diff_hash"] == obj["after_unstaged_diff_hash"]
        and not obj["diff_created"]
        and not obj["external_write_observed"]
    )
    require(not obj["automation_memory_used_as_evidence"], f"{path}.automation_memory_used_as_evidence must be false")
    if window_kind == "rolling_72h":
        require(obj["host_automation_memory_read"], f"{path}.host_automation_memory_read must be true for Scheduled runs")
        require(obj["host_automation_memory_updated"], f"{path}.host_automation_memory_updated must be true for Scheduled runs")
    else:
        require(not obj["host_automation_memory_read"], f"{path}.host_automation_memory_read must be false for manual runs")
        require(not obj["host_automation_memory_updated"], f"{path}.host_automation_memory_updated must be false for manual runs")
    if status != "failed":
        require(unchanged, f"{path} does not prove a read-only run")


def validate_project(value: Any) -> dict[str, Any]:
    obj = require_object(value, "$")
    require_exact_keys(
        obj,
        {
            "contract_version", "mode", "status", "display_locale", "project_key", "run_id", "task_id", "skill_version",
            "evidence_window", "model_observation", "owner_snapshot", "session_coverage", "evidence_sources",
            "events", "observations", "project_cards", "read_only_proof", "limitations",
        },
        "$",
    )
    require(obj["contract_version"] == PROJECT_CONTRACT, "$.contract_version invalid")
    require(obj["mode"] == "project_scout", "$.mode invalid")
    require(obj["display_locale"] == DISPLAY_LOCALE, f"$.display_locale must be {DISPLAY_LOCALE}")
    status = obj["status"]
    require(status in STATUSES, "$.status invalid")
    require(obj["skill_version"] == SKILL_VERSION, "$.skill_version invalid")
    for field in ("project_key", "run_id", "task_id"):
        require_string(obj[field], f"$.{field}")
    window = require_object(obj["evidence_window"], "$.evidence_window")
    require_exact_keys(window, {"kind", "start", "end"}, "$.evidence_window")
    require(window["kind"] in {"manual_30d", "rolling_72h"}, "$.evidence_window.kind invalid")
    start = validate_iso(window["start"], "$.evidence_window.start")
    end = validate_iso(window["end"], "$.evidence_window.end")
    require(start <= end, "$.evidence_window start exceeds end")
    validate_model_observation(obj["model_observation"], "$.model_observation")
    owner = require_object(obj["owner_snapshot"], "$.owner_snapshot")
    require_exact_keys(owner, {"project_instruction_hash", "owners_read"}, "$.owner_snapshot")
    validate_hash(owner["project_instruction_hash"], "$.owner_snapshot.project_instruction_hash")
    for index, item in enumerate(require_list(owner["owners_read"], "$.owner_snapshot.owners_read", nonempty=True)):
        require_string(item, f"$.owner_snapshot.owners_read[{index}]")
    validate_session_coverage(obj["session_coverage"], "$.session_coverage")
    sources = require_list(obj["evidence_sources"], "$.evidence_sources", nonempty=True)
    for index, raw in enumerate(sources):
        path = f"$.evidence_sources[{index}]"
        item = require_object(raw, path)
        require_exact_keys(item, {"kind", "status", "coverage"}, path)
        require_string(item["kind"], f"{path}.kind")
        require(item["status"] in {"available", "degraded", "unavailable"}, f"{path}.status invalid")
        require_string(item["coverage"], f"{path}.coverage")
    orders: list[int] = []
    for index, raw in enumerate(require_list(obj["events"], "$.events")):
        path = f"$.events[{index}]"
        item = require_object(raw, path)
        require_exact_keys(item, {"event_id", "order", "summary", "before_belief", "observed_change", "accepted_result", "direct_evidence"}, path)
        require_string(item["event_id"], f"{path}.event_id")
        orders.append(require_int(item["order"], f"{path}.order", minimum=1))
        for field in ("summary", "before_belief", "observed_change", "accepted_result"):
            require_string(item[field], f"{path}.{field}")
        validate_evidence_refs(item["direct_evidence"], f"{path}.direct_evidence")
    require(orders == list(range(1, len(orders) + 1)), "$.events order must be contiguous")
    for index, raw in enumerate(require_list(obj["observations"], "$.observations")):
        path = f"$.observations[{index}]"
        item = require_object(raw, path)
        require_exact_keys(item, {"observation_id", "evidence_level", "summary", "direct_evidence", "disposition"}, path)
        require_string(item["observation_id"], f"{path}.observation_id")
        require(item["evidence_level"] == "E1", f"{path}.evidence_level must be E1")
        require_string(item["summary"], f"{path}.summary")
        validate_evidence_refs(item["direct_evidence"], f"{path}.direct_evidence")
        require_string(item["disposition"], f"{path}.disposition")
    cards = require_list(obj["project_cards"], "$.project_cards")
    hashes = [validate_project_card(card, f"$.project_cards[{index}]")["project_claim_hash"] for index, card in enumerate(cards)]
    require(len(hashes) == len(set(hashes)), "$.project_cards contains duplicate claim hashes")
    validate_read_only_proof(obj["read_only_proof"], "$.read_only_proof", status, window["kind"])
    limitations = require_list(obj["limitations"], "$.limitations")
    for index, item in enumerate(limitations):
        require_string(item, f"$.limitations[{index}]")
    coverage = obj["session_coverage"]["status"]
    if status == "ok":
        require(cards and coverage in {"complete", "bounded"}, "ok requires cards and complete or bounded coverage")
    elif status == "degraded":
        require(bool(limitations), "degraded requires explicit limitations")
    elif status == "no_material_delta":
        require(not cards and coverage in {"complete", "bounded"}, "no_material_delta requires no cards and complete or bounded coverage")
    else:
        require(not cards, f"{status} must not contain Project Cards")
    validate_privacy_surface(obj)
    validate_user_facing_language(obj)
    return obj


def validate_owner_parity(value: Any, path: str) -> dict[str, Any]:
    obj = require_object(value, path)
    require_exact_keys(
        obj,
        {
            "status",
            "canonical_source_ref",
            "canonical_source_hash",
            "local_target_ref",
            "local_target_hash",
            "snapshot_id",
        },
        path,
    )
    status = obj["status"]
    require(status in {"matched", "drift", "unavailable"}, f"{path}.status invalid")
    require(obj["canonical_source_ref"] == "canonical_global_agents", f"{path}.canonical_source_ref invalid")
    require(obj["local_target_ref"] == "host_local_global_agents", f"{path}.local_target_ref invalid")
    source = validate_hash(obj["canonical_source_hash"], f"{path}.canonical_source_hash", nullable=True)
    target = validate_hash(obj["local_target_hash"], f"{path}.local_target_hash", nullable=True)
    validate_hash(obj["snapshot_id"], f"{path}.snapshot_id")
    require(obj["snapshot_id"] == owner_snapshot_id(obj), f"{path}.snapshot_id is not deterministic")
    if status == "matched":
        require(source is not None and source == target, f"{path} matched hashes differ")
    elif status == "drift":
        require(source is not None and target is not None and source != target, f"{path} drift hashes are invalid")
    else:
        require(source is None or target is None, f"{path} unavailable must have at least one unavailable hash")
    return obj


def validate_integration_preview(value: Any, path: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(obj, {"global_relation", "research", "owner_comparison", "before_after", "globalization_risk", "repeat_status"}, path)
    require(obj["global_relation"] in GLOBAL_RELATIONS, f"{path}.global_relation invalid")
    research = require_object(obj["research"], f"{path}.research")
    require_exact_keys(research, {"status", "sources", "conclusion"}, f"{path}.research")
    require(research["status"] in RESEARCH_STATUSES, f"{path}.research.status invalid")
    for index, raw in enumerate(require_list(research["sources"], f"{path}.research.sources")):
        item_path = f"{path}.research.sources[{index}]"
        item = require_object(raw, item_path)
        require_exact_keys(item, {"title", "url", "support"}, item_path)
        require_string(item["title"], f"{item_path}.title")
        require(require_string(item["url"], f"{item_path}.url").startswith("https://"), f"{item_path}.url must be HTTPS")
        require_string(item["support"], f"{item_path}.support")
    require_string(research["conclusion"], f"{path}.research.conclusion")
    comparison = require_object(obj["owner_comparison"], f"{path}.owner_comparison")
    require_exact_keys(comparison, {"current", "gap"}, f"{path}.owner_comparison")
    require_string(comparison["current"], f"{path}.owner_comparison.current")
    require_string(comparison["gap"], f"{path}.owner_comparison.gap")
    before_after = require_object(obj["before_after"], f"{path}.before_after")
    require_exact_keys(before_after, {"before", "after", "unchanged"}, f"{path}.before_after")
    require_string(before_after["before"], f"{path}.before_after.before")
    require_string(before_after["after"], f"{path}.before_after.after")
    for index, item in enumerate(require_list(before_after["unchanged"], f"{path}.before_after.unchanged")):
        require_string(item, f"{path}.before_after.unchanged[{index}]")
    require_string(obj["globalization_risk"], f"{path}.globalization_risk")
    require(obj["repeat_status"] in REPEAT_STATUSES, f"{path}.repeat_status invalid")


def expected_action_policy(card: dict[str, Any], parity_status: str) -> tuple[str, list[str]]:
    globally_confirmable = (
        parity_status == "matched"
        and card["owner_recommendation"] == "global_agents"
        and card["classification"] in {"add", "replace", "consolidate"}
    )
    if globally_confirmable:
        return "confirm", copy.deepcopy(ALL_ACTIONS)
    if card["classification"] == "already_covered" or card["owner_recommendation"] == "no_persistence":
        return "ignore", copy.deepcopy(READ_ONLY_ACTIONS)
    if card["owner_recommendation"] == "skill":
        return "make_skill", copy.deepcopy(READ_ONLY_ACTIONS)
    if card["classification"] == "route_to_owner" or card["owner_recommendation"] in {"project_owner"}:
        return "keep_project", copy.deepcopy(READ_ONLY_ACTIONS)
    return "edit", copy.deepcopy(READ_ONLY_ACTIONS)


def validate_review_pack(value: Any) -> dict[str, Any]:
    obj = require_object(value, "$")
    require_exact_keys(
        obj,
        {"contract_version", "mode", "status", "display_locale", "skill_version", "project_result", "owner_parity", "review_cards", "limitations", "review_pack_hash"},
        "$",
    )
    require(obj["contract_version"] == REVIEW_PACK_CONTRACT, "$.contract_version invalid")
    require(obj["mode"] == "review_pack", "$.mode invalid")
    require(obj["display_locale"] == DISPLAY_LOCALE, f"$.display_locale must be {DISPLAY_LOCALE}")
    require(obj["skill_version"] == SKILL_VERSION, "$.skill_version invalid")
    project = validate_project(obj["project_result"])
    require(obj["status"] == project["status"], "$.status must match project_result.status")
    parity = validate_owner_parity(obj["owner_parity"], "$.owner_parity")
    cards = require_list(obj["review_cards"], "$.review_cards")
    project_cards = project["project_cards"]
    require(len(cards) == len(project_cards), "$.review_cards must conserve every Project Card")
    for index, raw in enumerate(cards):
        path = f"$.review_cards[{index}]"
        item = require_object(raw, path)
        require_exact_keys(
            item,
            {
                "project_claim_hash",
                "recommended_action",
                "recommended_action_reason",
                "integration_preview",
                "expected_behavior_change",
                "allowed_actions",
            },
            path,
        )
        require(item["project_claim_hash"] == project_cards[index]["project_claim_hash"], f"{path} Project Card order or identity changed")
        recommended, expected_actions = expected_action_policy(project_cards[index], parity["status"])
        require(item["recommended_action"] == recommended, f"{path}.recommended_action violates owner routing")
        validate_zh_cn_text(item["recommended_action_reason"], f"{path}.recommended_action_reason", max_chars=240)
        validate_integration_preview(item["integration_preview"], f"{path}.integration_preview")
        require_string(item["expected_behavior_change"], f"{path}.expected_behavior_change")
        require(
            require_list(item["allowed_actions"], f"{path}.allowed_actions") == expected_actions,
            f"{path}.allowed_actions must exactly match owner and parity policy",
        )
        require(item["recommended_action"] in item["allowed_actions"], f"{path}.recommended_action must be allowed")
    limitations = require_list(obj["limitations"], "$.limitations")
    for index, item in enumerate(limitations):
        require_string(item, f"$.limitations[{index}]")
    require(obj["limitations"] == project["limitations"], "$.limitations must preserve Project limitations")
    if obj["status"] in {"failed", "output_budget_exceeded", "no_material_delta"}:
        require(not cards, f"{obj['status']} must not contain Review Cards")
    stored_hash = validate_hash(obj["review_pack_hash"], "$.review_pack_hash")
    require(stored_hash == review_pack_hash(obj), "$.review_pack_hash mismatch")
    validate_privacy_surface(obj)
    validate_user_facing_language(obj)
    return obj


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def valid_model(*, observed: bool = True) -> dict[str, Any]:
    return {
        "requested_model": PILOT_MODEL,
        "requested_reasoning": PILOT_REASONING,
        "policy_resolved_at": PILOT_POLICY_DATE,
        "runtime_metadata_status": "observed" if observed else "request_only",
        "actual_model": PILOT_MODEL if observed else None,
        "actual_reasoning": PILOT_REASONING if observed else None,
        "usage_status": "unavailable",
        "input_tokens": None,
        "output_tokens": None,
    }


def valid_read_only(*, scheduled: bool = False) -> dict[str, Any]:
    return {
        "snapshot_scope": "isolated_worktree",
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
    card: dict[str, Any] = {
        "card_id": f"{project}-card-{index}",
        "project_claim_hash": "",
        "human_context": {
            "display_locale": DISPLAY_LOCALE,
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
        "project_support": {"count": 1, "total": 3, "projects": [project]},
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
    card["project_claim_hash"] = project_claim_hash(card)
    return card


def valid_project(
    *,
    status: str = "ok",
    card_count: int = 2,
    coverage: str = "complete",
    observed: bool = True,
    window_kind: str = "manual_30d",
) -> dict[str, Any]:
    if status in {"no_material_delta", "failed", "output_budget_exceeded"}:
        card_count = 0
    truncated = coverage == "bounded"
    discovered = PILOT_TASK_INDEX_LIMIT if truncated else 4
    selected = 3
    limitations = ["Session 覆盖不可用；本轮使用了正式项目证据。"] if status == "degraded" else []
    project = {
        "contract_version": PROJECT_CONTRACT,
        "mode": "project_scout",
        "status": status,
        "display_locale": DISPLAY_LOCALE,
        "project_key": "example-project",
        "run_id": "run-example",
        "task_id": "task-example",
        "skill_version": SKILL_VERSION,
        "evidence_window": {"kind": window_kind, "start": "2026-07-08T00:00:00+08:00", "end": "2026-08-07T00:00:00+08:00"},
        "model_observation": valid_model(observed=observed),
        "owner_snapshot": {"project_instruction_hash": sha("owner"), "owners_read": ["项目 AGENTS", "项目 L1"]},
        "session_coverage": {
            "task_index_limit": PILOT_TASK_INDEX_LIMIT,
            "discovered_task_count": discovered,
            "window_task_count": 3,
            "selected_task_count": selected,
            "fully_read_task_count": selected if coverage != "degraded" else 0,
            "turn_pages_read": 6 if coverage != "degraded" else 0,
            "excluded": [{"task_ref": "task:unrelated", "reason": "项目身份不一致。"}],
            "truncated": truncated,
            "status": coverage,
            "discovery_methods": ["原生任务索引", "项目身份匹配"],
        },
        "evidence_sources": [
            {"kind": "sessions", "status": "unavailable" if coverage == "degraded" else "available", "coverage": "已检查窗口任务普查和所选任务分页。"},
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
    return project


def valid_parity(status: str = "matched") -> dict[str, Any]:
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
    parity["snapshot_id"] = owner_snapshot_id(parity)
    return parity


def valid_review_pack(project: dict[str, Any] | None = None, *, parity_status: str = "matched") -> dict[str, Any]:
    project = copy.deepcopy(project or valid_project())
    parity = valid_parity(parity_status)
    review_cards = []
    for card in project["project_cards"]:
        recommended, actions = expected_action_policy(card, parity_status)
        reasons = {
            "confirm": "该候选建议进入全局 Owner，且当前 canonical 与本机 Owner 一致，可以逐卡确认。",
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
                    "global_relation": "add",
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
                },
                "expected_behavior_change": "后续任务会区分机制就绪与用户要求的真实结果。",
                "allowed_actions": copy.deepcopy(actions),
            }
        )
    pack = {
        "contract_version": REVIEW_PACK_CONTRACT,
        "mode": "review_pack",
        "status": project["status"],
        "display_locale": DISPLAY_LOCALE,
        "skill_version": SKILL_VERSION,
        "project_result": project,
        "owner_parity": parity,
        "review_cards": review_cards,
        "limitations": copy.deepcopy(project["limitations"]),
        "review_pack_hash": "",
    }
    pack["review_pack_hash"] = review_pack_hash(pack)
    return pack


def expect_invalid(value: dict[str, Any], validator: Callable[[Any], Any], label: str) -> None:
    try:
        validator(value)
    except ContractError:
        return
    raise AssertionError(f"expected invalid fixture: {label}")


def run_self_test() -> None:
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
    ]
    for fixture in fixtures:
        validate_project(fixture)
        tests += 1
        validate_review_pack(valid_review_pack(fixture))
        tests += 1

    invalid = copy.deepcopy(fixtures[0])
    del invalid["session_coverage"]["turn_pages_read"]
    expect_invalid(invalid, validate_project, "missing coverage field")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["session_coverage"]["task_index_limit"] = 1000
    expect_invalid(invalid, validate_project, "oversized pilot task index")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["read_only_proof"]["host_automation_memory_read"] = True
    expect_invalid(invalid, validate_project, "manual run read automation memory")
    tests += 1

    invalid = valid_project(window_kind="rolling_72h")
    invalid["read_only_proof"]["host_automation_memory_updated"] = False
    expect_invalid(invalid, validate_project, "scheduled run skipped required automation memory update")
    tests += 1

    invalid = valid_project(window_kind="rolling_72h")
    invalid["read_only_proof"]["automation_memory_used_as_evidence"] = True
    expect_invalid(invalid, validate_project, "automation memory used as evidence")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "See C:\\private\\evidence.txt"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "absolute path leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "git push origin main"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "command leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "api_key=" + "sk-" + "private-example-value"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "secret leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["direct_evidence"][0]["summary"] = "<response-annotations>原始对话片段</response-annotations>"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "raw transcript leakage")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["pain"] = "This sentence is intentionally long enough to prove that an English-only user-facing narrative is rejected."
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "English-only user narrative")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["evidence_refs"] = ["event:missing"]
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "human context evidence reference")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["decision_title"] = "是否应该把一个超过六十个字符且无法快速扫描的项目决策标题继续展示给用户，从而再次增加本来可以避免的阅读和判断负担并破坏三十秒判断目标？"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "oversized decision title")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["human_context"]["project_story"] = "第一段。\n\n第二段。\n\n第三段。\n\n第四段。"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "too many project story paragraphs")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["evidence_level"] = "E1"
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "E1 promotion")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["project_cards"][0]["project_support"]["total"] = 12
    invalid["project_cards"][0]["project_claim_hash"] = project_claim_hash(invalid["project_cards"][0])
    expect_invalid(invalid, validate_project, "wrong configured-project total")
    tests += 1

    invalid = copy.deepcopy(fixtures[0])
    invalid["model_observation"]["actual_reasoning"] = "xhigh"
    expect_invalid(invalid, validate_project, "model mismatch")
    tests += 1

    invalid = valid_project(status="output_budget_exceeded")
    invalid["project_cards"] = [build_card()]
    expect_invalid(invalid, validate_project, "partial capacity output")
    tests += 1

    pack = valid_review_pack()
    invalid = copy.deepcopy(pack)
    invalid["review_cards"].pop()
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "silent card truncation")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_cards"].reverse()
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "card order drift")
    tests += 1

    drift = valid_review_pack(parity_status="drift")
    validate_review_pack(drift)
    tests += 1
    invalid = copy.deepcopy(drift)
    invalid["review_cards"][0]["allowed_actions"].insert(0, "confirm")
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "confirm during owner drift")
    tests += 1

    routed_project = valid_project(card_count=1)
    routed_card = routed_project["project_cards"][0]
    routed_card["classification"] = "route_to_owner"
    routed_card["owner_recommendation"] = "project_owner"
    routed_card["rule_payload"]["scope"] = "project"
    routed_card["rule_payload"]["instruction_target"] = "project_owner"
    routed_card["project_claim_hash"] = project_claim_hash(routed_card)
    routed = valid_review_pack(routed_project)
    validate_review_pack(routed)
    require(routed["review_cards"][0]["recommended_action"] == "keep_project", "route_to_owner recommendation mismatch")
    require("confirm" not in routed["review_cards"][0]["allowed_actions"], "route_to_owner must not allow confirm")
    tests += 1

    skill_project = valid_project(card_count=1)
    skill_card = skill_project["project_cards"][0]
    skill_card["owner_recommendation"] = "skill"
    skill_card["rule_payload"]["scope"] = "skill"
    skill_card["rule_payload"]["instruction_target"] = "skill"
    skill_card["project_claim_hash"] = project_claim_hash(skill_card)
    skill_pack = valid_review_pack(skill_project)
    validate_review_pack(skill_pack)
    require(skill_pack["review_cards"][0]["recommended_action"] == "make_skill", "Skill recommendation mismatch")
    require("confirm" not in skill_pack["review_cards"][0]["allowed_actions"], "Skill card must not allow confirm")
    tests += 1

    unavailable = valid_review_pack(parity_status="unavailable")
    validate_review_pack(unavailable)
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["owner_parity"]["snapshot_id"] = sha("wrong")
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "nondeterministic parity identity")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["owner_parity"]["local_target_ref"] = "project_root_agents"
    invalid["owner_parity"]["snapshot_id"] = owner_snapshot_id(invalid["owner_parity"])
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "project owner substituted for global target")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_cards"][0]["integration_preview"]["research"]["sources"][0]["url"] = "file://private"
    invalid["review_pack_hash"] = review_pack_hash(invalid)
    expect_invalid(invalid, validate_review_pack, "private research source")
    tests += 1

    invalid = copy.deepcopy(pack)
    invalid["review_pack_hash"] = sha("wrong")
    expect_invalid(invalid, validate_review_pack, "review pack hash mismatch")
    tests += 1

    old_contract = copy.deepcopy(pack)
    old_contract["contract_version"] = "global_owner_scout_digest_manifest_v3"
    old_contract["mode"] = "central_manifest"
    old_contract["review_pack_hash"] = review_pack_hash(old_contract)
    expect_invalid(old_contract, validate_review_pack, "removed central manifest")
    tests += 1

    old_review_pack = copy.deepcopy(pack)
    old_review_pack["contract_version"] = "global_owner_scout_review_pack_v1"
    old_review_pack["review_pack_hash"] = review_pack_hash(old_review_pack)
    expect_invalid(old_review_pack, validate_review_pack, "old Review Pack contract")
    tests += 1

    old_project = copy.deepcopy(fixtures[0])
    old_project["contract_version"] = "global_owner_scout_project_v2"
    expect_invalid(old_project, validate_project, "old Project contract")
    tests += 1

    baseline = valid_project(card_count=24)
    validate_review_pack(valid_review_pack(baseline))
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


def load_stdin_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Validate Global Owner Scout v4 JSON contracts from stdin.")
    parser.add_argument("--mode", choices=("project_scout", "review_pack"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--hash-project-card", action="store_true")
    parser.add_argument("--hash-owner-parity", action="store_true")
    parser.add_argument("--hash-review-pack", action="store_true")
    args = parser.parse_args()
    hash_flags = [args.hash_project_card, args.hash_owner_parity, args.hash_review_pack]
    try:
        if args.self_test:
            require(not args.mode and not any(hash_flags), "--self-test cannot be combined with another mode")
            run_self_test()
            return 0
        require(sum(bool(flag) for flag in hash_flags) <= 1, "hash modes are mutually exclusive")
        if any(hash_flags):
            require(not args.mode, "hash mode cannot be combined with --mode")
            data = require_object(load_stdin_json(), "$")
            if args.hash_project_card:
                result = {"project_claim_hash": project_claim_hash(data)}
            elif args.hash_owner_parity:
                result = {"snapshot_id": owner_snapshot_id(data)}
            else:
                result = {"review_pack_hash": review_pack_hash(data)}
            print(json.dumps(result, separators=(",", ":")))
            return 0
        require(bool(args.mode), "--mode is required unless a self-test or hash mode is used")
        data = load_stdin_json()
        validators = {"project_scout": validate_project, "review_pack": validate_review_pack}
        validated = validators[args.mode](data)
        print(json.dumps({"status": "ok", "mode": args.mode, "contract_version": validated["contract_version"]}, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
