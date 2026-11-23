#!/usr/bin/env python3
"""Validate Global Owner Scout 5.20.2 project results and Review Packs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from utf8_stdio import configure_utf8_stdio


SKILL_VERSION = "5.20.2"
PROJECT_CONTRACT = "global_owner_scout_project_v7"
NATIVE_PROJECT_CONTRACT = "global_owner_scout_project_v8"
MAP_PROJECT_CONTRACT = "global_owner_scout_project_v6"
REVIEW_PACK_CONTRACT = "global_owner_scout_review_pack_v8"
NATIVE_REVIEW_PACK_CONTRACT = "global_owner_scout_review_pack_v9"
NATIVE_COVERAGE_KEYS = {'native_host', 'scopes', 'discovered_task_count', 'selected_task_count',
                        'fully_read_task_count', 'status', 'discovery_methods'}
MAP_REVIEW_PACK_CONTRACT = "global_owner_scout_review_pack_v7"
LEGACY_PROJECT_CONTRACT = "global_owner_scout_project_v5"
LEGACY_REVIEW_PACK_CONTRACT = "global_owner_scout_review_pack_v6"
DISPLAY_LOCALE = "zh-CN"
PILOT_MODEL = "gpt-5.6-sol"
PILOT_REASONING = "medium"
PILOT_POLICY_DATE = "2026-08-06"
PILOT_TASK_INDEX_LIMIT = 50

STATUSES = {"ok", "degraded", "no_material_delta", "failed", "output_budget_exceeded", "view_ready"}
COVERAGE_STATUSES = {"complete", "bounded", "degraded"}
SOURCE_KINDS = {"sessions", "owners", "decisions", "successes", "failures", "acceptance"}
DISPOSITIONS = {"candidate", "already_covered", "project_only", "skill_only", "insufficient_evidence", "not_reusable"}
DISCOVERY_METHODS = {
    "native_index_completed",
    "native_index_host_cap",
    "native_index_terminal_failure",
    "native_thread_pages_completed",
    "native_thread_pages_terminal_failure",
    "execution_protocol_failed",
}
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

ENGINEERING_CLAIM_FIELDS = (
    "kind", "parent_card_id", "card_id", "human_context", "evidence_level", "normalized_evidence_hash",
    "owner_recommendation", "direct_evidence", "owner_rationale", "anti_examples", "privacy_check", "unproven",
    "benefit_hypothesis", "implementation_cost", "validation_conditions", "alternatives",
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
LONG_SENTENCE_SPLIT_RE = re.compile(r"(?:[。！？!?；]\s*|\.\s+|\n+)")
INLINE_CODE_SPAN_RE = re.compile(r"`[^`\n]+`")
TECHNICAL_TOKEN_RE = re.compile(r"(?:\b\S*(?:[/_\\]|::|--|->)\S*\b|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b)")
LANGUAGE_EXEMPT_PATH_PARTS = (
    ".selection_preview.",
    ".kind",
    ".parent_card_id",
    ".rule_payload.",
    ".before_after.before",
    ".before_after.after",
    ".ref",
    ".owner_refs",
    ".event_id",
    ".url",
    ".project_key",
    ".project_identity.",
    ".project_support.project_refs",
    ".run_id",
    ".task_id",
    ".card_id",
    ".project_claim_hash",
    ".selection_token",
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


def validate_zh_cn_text(value: Any, path: str, *, max_chars: int | None = None, require_han: bool = False) -> str:
    text = require_string(value, path)
    if max_chars is not None:
        require(len(text) <= max_chars, f"{path} must be <= {max_chars} characters")
    if require_han:
        require(bool(HAN_RE.search(text)), f"{path} must contain Simplified Chinese text")
    for sentence in LONG_SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence or HAN_RE.search(sentence):
            continue
        prose = re.sub(r"\s+", " ", TECHNICAL_TOKEN_RE.sub(" ", INLINE_CODE_SPAN_RE.sub(" ", sentence))).strip()
        if len(prose) > 40:
            require(False, f"{path} contains an English-only sentence longer than 40 characters")
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
    fields = ENGINEERING_CLAIM_FIELDS if card.get("kind") == "engineering" else PROJECT_CLAIM_FIELDS
    return canonical_hash({field: card[field] for field in fields})


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


def validate_model_observation(value: Any, path: str, *, window_kind: str) -> None:
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
    requested_model = require_string(obj["requested_model"], f"{path}.requested_model")
    requested_reasoning = require_string(obj["requested_reasoning"], f"{path}.requested_reasoning")
    policy_resolved_at = require_string(obj["policy_resolved_at"], f"{path}.policy_resolved_at")
    validate_iso(policy_resolved_at + "T00:00:00+00:00", f"{path}.policy_resolved_at")
    if window_kind == "rolling_72h":
        require(requested_model == PILOT_MODEL, f"{path}.requested_model must be {PILOT_MODEL} for Scheduled")
        require(requested_reasoning == PILOT_REASONING, f"{path}.requested_reasoning must be {PILOT_REASONING} for Scheduled")
        require(policy_resolved_at == PILOT_POLICY_DATE, f"{path}.policy_resolved_at must be {PILOT_POLICY_DATE} for Scheduled")
    metadata_status = obj["runtime_metadata_status"]
    require(metadata_status in {"observed", "request_only", "unavailable"}, f"{path}.runtime_metadata_status invalid")
    if metadata_status == "observed":
        require(obj["actual_model"] == requested_model, f"{path}.actual_model does not match requested model")
        require(obj["actual_reasoning"] == requested_reasoning, f"{path}.actual_reasoning does not match requested reasoning")
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


def validate_native_session_coverage(value: Any, path: str, project_status: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(obj, NATIVE_COVERAGE_KEYS, path)
    require(require_string(obj['native_host'], f'{path}.native_host') in {'pi', 'claude', 'antigravity'}, f'{path} native host invalid')
    discovered = require_int(obj['discovered_task_count'], f'{path}.discovered_task_count')
    selected = require_int(obj['selected_task_count'], f'{path}.selected_task_count')
    read = require_int(obj['fully_read_task_count'], f'{path}.fully_read_task_count')
    require(read == 0 and read <= selected <= discovered, f'{path} cannot prove loss-free selected histories')
    require(obj['status'] == project_status == 'degraded', f'{path} native history must remain degraded')
    require(obj['discovery_methods'] == ['native_scoped_sources_observed'], f'{path} native discovery method invalid')
    seen = set()
    for scope in require_list(obj['scopes'], f'{path}.scopes', nonempty=True):
        require_exact_keys(require_object(scope, path), {'kind', 'coverage', 'record_count', 'evidence_refs'}, path)
        require(require_string(scope['kind'], path) in {'project_sessions', 'session_messages'}, f'{path} native scope invalid')
        require(require_string(scope['coverage'], path) in {'observed_only', 'unknown', 'failed'}, f'{path} scope cannot claim complete')
        refs = require_list(scope['evidence_refs'], path, nonempty=scope['coverage'] == 'observed_only')
        require(all(isinstance(ref, str) and ref for ref in refs) and len(refs) == len(set(refs)), f'{path} scope refs invalid')
        if scope['coverage'] == 'observed_only':
            require_int(scope['record_count'], f'{path}.record_count')
        else:
            require(scope['record_count'] is None, f'{path} unknown/failed count must remain unknown')
        key = (scope['kind'], tuple(sorted(refs)))
        require(key not in seen, f'{path} duplicate native scope')
        seen.add(key)


def validate_session_coverage(value: Any, path: str, project_status: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(
        obj,
        {
            "task_index_limit",
            "index_pages_read",
            "index_terminals",
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
    require(limit == PILOT_TASK_INDEX_LIMIT, f"{path}.task_index_limit must be {PILOT_TASK_INDEX_LIMIT} during the v5 pilot")
    discovered = require_int(obj["discovered_task_count"], f"{path}.discovered_task_count")
    window = require_int(obj["window_task_count"], f"{path}.window_task_count")
    selected = require_int(obj["selected_task_count"], f"{path}.selected_task_count")
    read = require_int(obj["fully_read_task_count"], f"{path}.fully_read_task_count")
    require_int(obj["turn_pages_read"], f"{path}.turn_pages_read")
    pages = require_int(obj["index_pages_read"], f"{path}.index_pages_read")
    terminals = require_object(obj["index_terminals"], f"{path}.index_terminals")
    require_exact_keys(terminals, {"active", "archived"}, f"{path}.index_terminals")
    require(all(isinstance(item, str) and item in {"window_boundary", "eof", "has_more", "unavailable", "failed"} for item in terminals.values()), f"{path} index terminal invalid")
    index_complete = all(item in {"window_boundary", "eof"} for item in terminals.values())
    require(read <= selected <= window <= discovered <= pages * limit, f"{path} counts are inconsistent")
    require(isinstance(obj["truncated"], bool), f"{path}.truncated must be boolean")
    status = obj["status"]
    require(status in COVERAGE_STATUSES, f"{path}.status invalid")
    if status == "complete":
        require(index_complete and pages >= 2 and not obj["truncated"] and read == selected, f"{path} complete coverage requires both history partitions and selected tasks")
    if status == "bounded":
        require(not index_complete and obj["truncated"] and read == selected, f"{path} bounded coverage must expose the unfinished history")
    excluded = require_list(obj["excluded"], f"{path}.excluded")
    for index, raw in enumerate(excluded):
        item_path = f"{path}.excluded[{index}]"
        item = require_object(raw, item_path)
        require_exact_keys(item, {"task_ref", "reason"}, item_path)
        require_string(item["task_ref"], f"{item_path}.task_ref")
        require_string(item["reason"], f"{item_path}.reason")
    methods = [
        require_string(item, f"{path}.discovery_methods[{index}]")
        for index, item in enumerate(require_list(obj["discovery_methods"], f"{path}.discovery_methods", nonempty=True))
    ]
    require(len(methods) == len(set(methods)), f"{path}.discovery_methods must be unique")
    require(set(methods) <= DISCOVERY_METHODS, f"{path}.discovery_methods contains a non-terminal method")
    method_set = set(methods)
    if "native_index_completed" in method_set:
        require(index_complete and pages >= 2, f"{path} completed index needs both history partitions")
    if "native_index_host_cap" in method_set:
        require(not index_complete and not any(item in {"failed", "unavailable"} for item in terminals.values()) and obj["truncated"], f"{path} bounded index must expose unread history")
    if "native_index_terminal_failure" in method_set:
        require(status == "degraded" and project_status == "degraded", f"{path} index failure requires degraded coverage and project status")
        require(any(item in {"unavailable", "failed"} for item in terminals.values()), f"{path} index failure needs a failed or unavailable partition")
    protocol_failed = "execution_protocol_failed" in method_set
    thread_pages_failed = "native_thread_pages_terminal_failure" in method_set
    if protocol_failed:
        require(project_status == "failed", f"{path} execution_protocol_failed requires project status failed")
        require(status == "degraded", f"{path} execution_protocol_failed requires degraded coverage")
        require(
            method_set in (
                {"execution_protocol_failed"},
                {"native_index_completed", "execution_protocol_failed"},
                {"native_index_host_cap", "execution_protocol_failed"},
            ),
            f"{path} execution_protocol_failed may preserve only a previously proved index terminal result",
        )
    elif status == "complete":
        require(
            method_set == {"native_index_completed", "native_thread_pages_completed"},
            f"{path} complete coverage requires completed index and thread pages",
        )
    elif status == "bounded":
        require(
            method_set == {"native_index_host_cap", "native_thread_pages_completed"},
            f"{path} bounded coverage requires explicit host cap and completed thread pages",
        )
    elif thread_pages_failed:
        require(project_status == "degraded", f"{path} thread page terminal failure requires degraded project status")
        require(obj["truncated"] and read < selected, f"{path} thread page terminal failure must expose incomplete selected-task coverage")
        require(
            method_set in (
                {"native_index_completed", "native_thread_pages_terminal_failure"},
                {"native_index_host_cap", "native_thread_pages_terminal_failure"},
            ),
            f"{path} thread page terminal failure requires one proved index terminal result",
        )
    else:
        require(
            method_set == {"native_index_terminal_failure"},
            f"{path} degraded coverage requires an explicit terminal index failure",
        )


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
    require_exact_keys(obj, {"count", "project_refs", "basis", "coverage_note"}, path)
    count = require_int(obj["count"], f"{path}.count", minimum=1)
    projects = [require_string(item, f"{path}.project_refs[{index}]") for index, item in enumerate(require_list(obj["project_refs"], f"{path}.project_refs", nonempty=True))]
    require(len(projects) == count and len(projects) == len(set(projects)), f"{path}.project_refs must be unique and match count")
    for index, project_ref in enumerate(projects):
        require(re.fullmatch(r"pref_[0-9a-f]{64}", project_ref) is not None, f"{path}.project_refs[{index}] must be opaque")
    require_string(obj["basis"], f"{path}.basis")
    require_string(obj["coverage_note"], f"{path}.coverage_note")
    if level == "E3":
        require(count >= 2, f"{path} E3 requires at least two projects")


def validate_project_identity(value: Any, path: str) -> None:
    obj = require_object(value, path)
    require_exact_keys(obj, {"identity_kind", "content_identity_hash", "host_project_ref_hash", "git_worktree_eligible", "binding_status"}, path)
    require(obj["identity_kind"] in {"content", "host_local"}, f"{path}.identity_kind invalid")
    require(re.fullmatch(r"(?:pci|hostlocal)_[0-9a-f]{64}", require_string(obj["content_identity_hash"], f"{path}.content_identity_hash")) is not None, f"{path}.content_identity_hash invalid")
    require(re.fullmatch(r"hpr_[0-9a-f]{64}", require_string(obj["host_project_ref_hash"], f"{path}.host_project_ref_hash")) is not None, f"{path}.host_project_ref_hash invalid")
    require(isinstance(obj["git_worktree_eligible"], bool), f"{path}.git_worktree_eligible must be boolean")
    require(obj["binding_status"] in {"bound", "rebound", "ambiguous"}, f"{path}.binding_status invalid")
    if obj["identity_kind"] == "host_local":
        require(not obj["git_worktree_eligible"], f"{path} host-local identity cannot be worktree eligible")


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
    validate_zh_cn_text(obj["decision_title"], f"{path}.decision_title", max_chars=60, require_han=True)
    story = validate_zh_cn_text(obj["project_story"], f"{path}.project_story", require_han=True)
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
        validate_zh_cn_text(obj[field], f"{path}.{field}", max_chars=240, require_han=True)
    refs = require_list(obj["evidence_refs"], f"{path}.evidence_refs", nonempty=True)
    direct_refs = {item["ref"] for item in direct_evidence}
    for index, ref in enumerate(refs):
        require_string(ref, f"{path}.evidence_refs[{index}]")
        require(ref in direct_refs, f"{path}.evidence_refs[{index}] must reference direct_evidence")
    require(len(refs) == len(set(refs)), f"{path}.evidence_refs must be unique")


def validate_engineering_card(obj: dict[str, Any], path: str) -> dict[str, Any]:
    require_exact_keys(obj, set(ENGINEERING_CLAIM_FIELDS) | {"project_claim_hash"}, path)
    require_string(obj["card_id"], f"{path}.card_id")
    if obj["parent_card_id"] is not None:
        require_string(obj["parent_card_id"], f"{path}.parent_card_id")
    require(obj["evidence_level"] in {"E1", "E2", "E3"}, f"{path}.evidence_level invalid")
    require(obj["owner_recommendation"] in {"project_owner", "skill"}, f"{path}: engineering advice has no global authority")
    validate_evidence_refs(obj["direct_evidence"], f"{path}.direct_evidence")
    require(obj["normalized_evidence_hash"] == canonical_hash(obj["direct_evidence"]), f"{path}.normalized_evidence_hash mismatch")
    validate_human_context(obj["human_context"], f"{path}.human_context", obj["direct_evidence"])
    for field in ("owner_rationale", "benefit_hypothesis", "implementation_cost"):
        require_string(obj[field], f"{path}.{field}")
    for field in ("anti_examples", "unproven", "validation_conditions"):
        for item in require_list(obj[field], f"{path}.{field}", nonempty=field != "unproven"):
            require_string(item, f"{path}.{field}")
    for option in require_list(obj["alternatives"], f"{path}.alternatives", nonempty=True):
        require_exact_keys(require_object(option, "alternative"), {"approach", "tradeoff"}, "alternative")
        for field in ("approach", "tradeoff"): require_string(option[field], field)
    privacy = require_object(obj["privacy_check"], f"{path}.privacy_check")
    require_exact_keys(privacy, {"status", "removed"}, f"{path}.privacy_check")
    require(privacy["status"] == "passed", f"{path}.privacy_check.status must be passed")
    for item in require_list(privacy["removed"], f"{path}.privacy_check.removed"):
        require_string(item, "removed")
    require(obj["project_claim_hash"] == project_claim_hash(obj), f"{path}.project_claim_hash mismatch")
    return obj


def validate_card_hierarchy(cards):
    engineering = {c["card_id"]: c for c in cards if c.get("kind") == "engineering"}
    for card in engineering.values():
        seen = {card["card_id"]}
        parent = card["parent_card_id"]
        while parent is not None:
            require(parent in engineering and parent not in seen, "invalid engineering advice parent or cycle")
            seen.add(parent); parent = engineering[parent]["parent_card_id"]


def validate_project_card(value: Any, path: str) -> dict[str, Any]:
    obj = require_object(value, path)
    if obj.get("kind") == "engineering": return validate_engineering_card(obj, path)
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
    require(obj["normalized_evidence_hash"] == canonical_hash(obj["direct_evidence"]), f"{path}.normalized_evidence_hash mismatch")
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
        "before_context_snapshot_hash",
        "after_context_snapshot_hash",
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
    scopes = {"isolated_worktree"} if window_kind == "rolling_72h" else {"isolated_worktree", "current_project"}
    require(obj["snapshot_scope"] in scopes, f"{path}.snapshot_scope invalid")
    validate_git_id(obj["before_head"], f"{path}.before_head")
    validate_git_id(obj["after_head"], f"{path}.after_head")
    for field in fields & {
        "before_status_hash", "after_status_hash", "before_staged_diff_hash", "after_staged_diff_hash",
        "before_unstaged_diff_hash", "after_unstaged_diff_hash",
        "before_context_snapshot_hash", "after_context_snapshot_hash",
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
        and obj["before_context_snapshot_hash"] == obj["after_context_snapshot_hash"]
        and obj["before_status_hash"] == obj["after_status_hash"]
        and obj["before_staged_diff_hash"] == obj["after_staged_diff_hash"]
        and obj["before_unstaged_diff_hash"] == obj["after_unstaged_diff_hash"]
        and not obj["diff_created"]
        and not obj["external_write_observed"]
    )
    require(not obj["automation_memory_used_as_evidence"], f"{path}.automation_memory_used_as_evidence must be false")
    require(
        obj["host_automation_memory_read"] == obj["host_automation_memory_updated"],
        f"{path} automation memory read/update must agree",
    )
    if window_kind == "manual_30d":
        require(not obj["host_automation_memory_read"], f"{path} manual baseline must not read automation memory")
    if status != "failed":
        require(unchanged, f"{path} does not prove a read-only run")


def validate_discovery_trace(obj: dict[str, Any]) -> None:
    """Check declared provenance and dispositions, never infer semantic recall."""
    declared: dict[str, dict[str, Any]] = {}
    owner_refs: set[str] = set()
    formal_refs: set[str] = set()
    statuses: dict[str, str] = {}
    for source in obj["evidence_sources"]:
        kind, status = source["kind"], source["status"]
        statuses[kind] = status
        refs = require_list(source["refs"], f"{kind}.refs")
        gaps = require_list(source["uncovered"], f"{kind}.uncovered")
        for gap in gaps:
            require_string(gap, f"{kind}.uncovered")
        if refs:
            validate_evidence_refs(refs, f"{kind}.refs")
        if status == "available":
            require(bool(refs) and not gaps, f"{kind}: available requires refs and no gaps")
        elif status == "degraded":
            require(bool(gaps), f"{kind}: degraded requires uncovered scope")
        elif status == "unavailable":
            require(not refs and bool(gaps), f"{kind}: unavailable requires no refs and explicit gaps")
        else:
            require(kind != "owners" and not refs and not gaps, f"{kind}: invalid not_applicable source")
        source_refs = [item["ref"] for item in refs]
        require(len(source_refs) == len(set(source_refs)), f"{kind}: duplicate source refs")
        for item in refs:
            require(item["ref"] not in declared or declared[item["ref"]] == item, "conflicting source evidence")
            declared[item["ref"]] = item
        if kind in {"owners", "decisions"}:
            owner_refs.update(source_refs)
        if kind in SOURCE_KINDS - {"sessions"}:
            formal_refs.update(source_refs)
    if obj["status"] in {"ok", "degraded", "no_material_delta"}:
        require(SOURCE_KINDS <= statuses.keys(), "discovery requires all six source categories")
    if obj["status"] in {"ok", "no_material_delta"}:
        require(statuses.get("owners") == "available", "successful discovery requires available Owners")
        require(all(status in {"available", "not_applicable"} for kind, status in statuses.items() if kind != "sessions"),
                "incomplete project sources require degraded status")

    def evidence_ids(value: Any, path: str) -> set[str]:
        validate_evidence_refs(value, path)
        refs = [item["ref"] for item in value]
        require(len(refs) == len(set(refs)), f"{path}: duplicate evidence refs")
        require(set(refs) <= declared.keys(), f"{path}: undeclared evidence")
        require(all(item == declared[item["ref"]] for item in value), f"{path}: evidence differs from declared source")
        return set(refs)

    events: dict[str, set[str]] = {}
    for event in obj["events"]:
        event_id = event["event_id"]
        require(event_id not in events, "duplicate event ID")
        events[event_id] = evidence_ids(event["direct_evidence"], "event.direct_evidence")
    cards = {card["card_id"]: card for card in obj["project_cards"]}
    require(len(cards) == len(obj["project_cards"]), "duplicate card ID")
    card_refs = {key: evidence_ids(card["direct_evidence"], "card.direct_evidence") for key, card in cards.items()}
    if statuses.get("sessions") in {"degraded", "unavailable"}:
        require(all(refs & formal_refs for refs in card_refs.values()), "degraded Sessions require independent non-Session evidence for each card")
    seen_observations: set[str] = set()
    seen_events: set[str] = set()
    seen_cards: set[str] = set()
    for index, observation in enumerate(obj["observations"]):
        path = f"$.observations[{index}]"
        key = observation["observation_id"]
        require(key not in seen_observations, "duplicate observation ID")
        seen_observations.add(key)
        refs = evidence_ids(observation["direct_evidence"], f"{path}.direct_evidence")
        linked_events = require_list(observation["event_ids"], f"{path}.event_ids")
        for event_id in linked_events:
            require_string(event_id, f"{path}.event_ids")
            require(event_id in events, f"{path}: unknown event ID")
            require(events[event_id] <= refs, f"{path}: missing event evidence")
        require(len(linked_events) == len(set(linked_events)), f"{path}: duplicate event links")
        seen_events.update(linked_events)
        disposition = require_object(observation["disposition"], f"{path}.disposition")
        require_exact_keys(disposition, {"kind", "reason", "card_ids", "owner_refs", "local_scope", "portable_delta"}, f"{path}.disposition")
        require_string(disposition["kind"], f"{path}.disposition.kind")
        require(disposition["kind"] in DISPOSITIONS, f"{path}: invalid disposition")
        for field in ("reason", "local_scope", "portable_delta"):
            require_string(disposition[field], f"{path}.disposition.{field}")
        owners = require_list(disposition["owner_refs"], f"{path}.owner_refs")
        for ref in owners:
            require_string(ref, f"{path}.owner_refs")
            require(ref in owner_refs and ref in refs, f"{path}: owner exclusion must cite declared Owner evidence")
        linked_cards = require_list(disposition["card_ids"], f"{path}.card_ids")
        if disposition["kind"] == "candidate":
            require(bool(linked_cards), f"{path}: candidate requires cards")
            if any(cards.get(c, {}).get("kind") != "engineering" for c in linked_cards):
                require(observation["evidence_level"] in {"E2", "E3"}, f"{path}: rule candidate requires qualified cards")
                require(bool(linked_events), f"{path}: rule candidate requires linked events")
        else:
            require(not linked_cards, f"{path}: exclusion cannot contain cards")
        if disposition["kind"] in {"already_covered", "project_only", "skill_only"}:
            require(bool(owners), f"{path}: existing-owner exclusion requires exact Owner refs")
        for card_id in linked_cards:
            require_string(card_id, f"{path}.card_ids")
            require(card_id in cards and card_id not in seen_cards, f"{path}: unknown or multiply routed card")
            require(cards[card_id]["evidence_level"] == observation["evidence_level"], f"{path}: evidence level mismatch")
            require(card_refs[card_id] <= refs, f"{path}: missing card evidence")
            if cards[card_id].get("kind") != "engineering":
                require(card_refs[card_id] <= set().union(*(events[event_id] for event_id in linked_events)), f"{path}: card evidence bypasses linked events")
            seen_cards.add(card_id)
    require(seen_events == events.keys(), "every event needs a disposition")
    require(seen_cards == cards.keys(), "every card needs exactly one disposition")
    if obj["status"] == "no_material_delta":
        require(bool(obj["observations"]), "no_material_delta requires evidenced observations")


PROJECT_INPUT_KEYS = {
    "contract_version", "mode", "status", "display_locale", "project_key", "project_identity", "run_id", "task_id", "skill_version",
    "evidence_window", "model_observation", "owner_snapshot", "session_coverage", "evidence_sources",
    "events", "observations", "project_cards", "read_only_proof", "limitations",
}
REVIEW_INPUT_KEYS = {"contract_version", "mode", "status", "display_locale", "skill_version", "project_result", "owner_parity", "review_cards", "selection_preview", "limitations", "review_pack_hash"}


def describe_input(kind: str) -> dict[str, Any]:
    project = kind in {'project', 'native-project'}
    native = kind.startswith('native-')
    result = dict(contract_version=(NATIVE_PROJECT_CONTRACT if native else PROJECT_CONTRACT) if project else (NATIVE_REVIEW_PACK_CONTRACT if native else REVIEW_PACK_CONTRACT),
                mode='project_scout' if project else 'review_pack', skill_version=SKILL_VERSION,
                display_locale=DISPLAY_LOCALE,
                required_keys=sorted(PROJECT_INPUT_KEYS | {'purpose', 'project_map'} if project else REVIEW_INPUT_KEYS),
                purpose_choices=['inspect', 'review'] if project else None,
                semantic_input='Use current source-backed claims, evidence refs and coverage; no inferred defaults.')
    field = 'project_claim_hash' if project else 'review_pack_hash'
    result['hash_helpers'] = {field: dict(script='scripts/validate_output.py',
        flag='--hash-project-card' if project else '--hash-review-pack')}
    if native:
        result['native_session_coverage_keys'] = sorted(NATIVE_COVERAGE_KEYS)
        result['history_guarantee'] = 'observed scopes only; history completeness unknown; review remains degraded'
    return result


def validate_project(value: Any) -> dict[str, Any]:
    obj = require_object(value, "$")
    native = obj.get('contract_version') == NATIVE_PROJECT_CONTRACT
    mapped = obj.get('contract_version') in {NATIVE_PROJECT_CONTRACT, PROJECT_CONTRACT, MAP_PROJECT_CONTRACT}
    inspect = mapped and obj.get('purpose') == 'inspect'
    require_exact_keys(
        obj,
        PROJECT_INPUT_KEYS | ({'purpose', 'project_map'} if mapped else set()),
        "$",
    )
    require(obj["contract_version"] in {NATIVE_PROJECT_CONTRACT, PROJECT_CONTRACT, MAP_PROJECT_CONTRACT, LEGACY_PROJECT_CONTRACT}, "$.contract_version invalid")
    if mapped:
        require(obj['purpose'] in {'inspect', 'review'}, 'invalid project purpose')
    require(obj['status'] != 'view_ready' or inspect, 'view_ready is only for inspection')
    require(obj["mode"] == "project_scout", "$.mode invalid")
    require(obj["display_locale"] == DISPLAY_LOCALE, f"$.display_locale must be {DISPLAY_LOCALE}")
    status = obj["status"]
    require(status in STATUSES, "$.status invalid")
    require(obj["skill_version"] == SKILL_VERSION, "$.skill_version invalid")
    for field in ("project_key", "run_id", "task_id"):
        require_string(obj[field], f"$.{field}")
    validate_project_identity(obj["project_identity"], "$.project_identity")
    window = require_object(obj["evidence_window"], "$.evidence_window")
    require_exact_keys(window, {"kind", "start", "end"}, "$.evidence_window")
    require(not native or window.get('kind') != 'rolling_72h', 'native-session candidate is interactive only')
    require(window["kind"] in ({'current'} if inspect else {"manual_30d", "rolling_72h"}), "$.evidence_window.kind invalid")
    if window["kind"] == "rolling_72h":
        require(obj["project_identity"]["identity_kind"] == "content", "Scheduled v5 run requires content identity")
        require(obj["project_identity"]["git_worktree_eligible"], "Scheduled v5 run requires isolated worktree eligibility")
        require(obj["project_identity"]["binding_status"] != "ambiguous", "Scheduled v5 run rejects ambiguous binding")
    start = validate_iso(window["start"], "$.evidence_window.start")
    end = validate_iso(window["end"], "$.evidence_window.end")
    require(start <= end, "$.evidence_window start exceeds end")
    validate_model_observation(obj["model_observation"], "$.model_observation", window_kind='manual_30d' if inspect else window["kind"])
    owner = require_object(obj["owner_snapshot"], "$.owner_snapshot")
    require_exact_keys(owner, {"project_instruction_hash", "owners_read"}, "$.owner_snapshot")
    validate_hash(owner["project_instruction_hash"], "$.owner_snapshot.project_instruction_hash")
    for index, item in enumerate(require_list(owner["owners_read"], "$.owner_snapshot.owners_read", nonempty=True)):
        require_string(item, f"$.owner_snapshot.owners_read[{index}]")
    if inspect:
        require(obj['session_coverage'] is None and not obj['events'] and not obj['observations'] and not obj['project_cards'], 'inspection cannot claim census, discoveries or actions')
        require(status in {'view_ready', 'degraded'}, 'inspection status invalid')
    else:
        (validate_native_session_coverage if native else validate_session_coverage)(obj["session_coverage"], "$.session_coverage", status)
    sources = require_list(obj["evidence_sources"], "$.evidence_sources", nonempty=True)
    source_statuses: dict[str, str] = {}
    for index, raw in enumerate(sources):
        path = f"$.evidence_sources[{index}]"
        item = require_object(raw, path)
        require_exact_keys(item, {"kind", "status", "coverage", "refs", "uncovered"}, path)
        kind = require_string(item["kind"], f"{path}.kind")
        require(kind not in source_statuses, f"{path}.kind must be unique")
        require(item["status"] in {"available", "degraded", "unavailable", "not_applicable"}, f"{path}.status invalid")
        source_statuses[kind] = item["status"]
        require_string(item["coverage"], f"{path}.coverage")
    require("sessions" in source_statuses, "$.evidence_sources must include sessions")
    if native and not inspect:
        require(source_statuses['sessions'] in {'degraded', 'unavailable'}, 'native history cannot claim full availability')
        refs = {r['ref'] for s in sources if s['kind'] == 'sessions' for r in s['refs']}
        require(all(set(scope['evidence_refs']) <= refs for scope in obj['session_coverage']['scopes']), 'native scopes must resolve declared Session evidence')
    discovery_methods = set() if inspect else set(obj["session_coverage"]["discovery_methods"])
    if inspect:
        require(source_statuses['sessions'] == 'not_applicable', 'inspection must not claim Session coverage')
        require(source_statuses.get('owners') in {'available', 'degraded'}, 'inspection needs current project sources')
    if "native_thread_pages_terminal_failure" in discovery_methods:
        require(source_statuses["sessions"] == "degraded", "$.evidence_sources sessions must be degraded after a thread-page terminal failure")
    if discovery_methods & {"native_index_terminal_failure", "execution_protocol_failed"}:
        require(source_statuses["sessions"] == "unavailable", "$.evidence_sources sessions must be unavailable after an index/protocol failure")
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
        require_exact_keys(item, {"observation_id", "evidence_level", "summary", "direct_evidence", "event_ids", "disposition"}, path)
        require_string(item["observation_id"], f"{path}.observation_id")
        require_string(item["evidence_level"], f"{path}.evidence_level")
        require(item["evidence_level"] in {"E1", "E2", "E3"}, f"{path}.evidence_level invalid")
        require_string(item["summary"], f"{path}.summary")
        validate_evidence_refs(item["direct_evidence"], f"{path}.direct_evidence")
    cards = require_list(obj["project_cards"], "$.project_cards")
    require(not native or all(c.get('kind') == 'engineering' for c in cards), 'native-session candidate supports engineering advice only; rule Owner migration is unqualified')
    require(obj["contract_version"] in {NATIVE_PROJECT_CONTRACT, PROJECT_CONTRACT} or all("kind" not in c for c in cards), "engineering cards require Project v7 or v8")
    validate_card_hierarchy(cards)
    hashes = [validate_project_card(card, f"$.project_cards[{index}]")["project_claim_hash"] for index, card in enumerate(cards)]
    require(len(hashes) == len(set(hashes)), "$.project_cards contains duplicate claim hashes")
    validate_discovery_trace(obj)
    validate_read_only_proof(obj["read_only_proof"], "$.read_only_proof", status, window["kind"])
    limitations = require_list(obj["limitations"], "$.limitations")
    for index, item in enumerate(limitations):
        require_string(item, f"$.limitations[{index}]")
    coverage = None if inspect else obj["session_coverage"]["status"]
    if status == "ok":
        require(cards and coverage in {"complete", "bounded"}, "ok requires cards and complete or bounded coverage")
    elif status == "degraded":
        require(bool(limitations), "degraded requires explicit limitations")
    elif status == "no_material_delta":
        require(not cards and coverage in {"complete", "bounded"}, "no_material_delta requires no cards and complete or bounded coverage")
    else:
        require(not cards, f"{status} must not contain Project Cards")
    if mapped:
        if status in {'failed', 'output_budget_exceeded'}:
            require(obj['project_map'] is None, 'failed review must not expose a partial map')
        else:
            from project_map import validate_map
            validate_map(obj)
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
    require_exact_keys(obj, {"global_relation", "research", "owner_comparison", "before_after", "globalization_risk", "repeat_status", "supersedes"}, path)
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
    supersedes = [require_string(item, f"{path}.supersedes[{index}]") for index, item in enumerate(require_list(obj["supersedes"], f"{path}.supersedes"))]
    require(supersedes == sorted(set(supersedes)), f"{path}.supersedes must be sorted and unique")
    require(all(re.fullmatch(r"rule_[0-9a-f]{12}", item) is not None for item in supersedes), f"{path}.supersedes contains an invalid rule ID")
    relation = obj["global_relation"]
    require(relation != "add" or not supersedes, f"{path} add cannot supersede rules")
    require(relation != "replace" or len(supersedes) == 1, f"{path} replace requires one superseded rule")
    require(relation != "consolidate" or len(supersedes) >= 2, f"{path} consolidate requires multiple superseded rules")


def selection_token(
    *,
    card_id: str,
    project_claim_hash: str,
    proposal: dict[str, Any],
    supersedes: list[str],
    target_before_sha256: str,
) -> str:
    proposal_json = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical = json.dumps(
        {
            "card_id": card_id,
            "contract_version": "review_selection_token_v1",
            "instruction_target": proposal["instruction_target"],
            "project_claim_hash": project_claim_hash,
            "proposal_sha256": hashlib.sha256(proposal_json.encode("utf-8")).hexdigest(),
            "supersedes": sorted(supersedes),
            "target_before_sha256": target_before_sha256,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def global_mutation_candidate(card: dict[str, Any], relation: str, parity_status: str) -> bool:
    return (parity_status == "matched" and card["owner_recommendation"] == "global_agents"
            and relation in {"add", "replace", "consolidate"})


def review_bundle(pack: dict[str, Any]) -> dict[str, Any] | None:
    items = []
    for card, review in zip(pack["project_result"]["project_cards"], pack["review_cards"]):
        if card.get("kind") == "engineering": continue
        preview = review["integration_preview"]
        if not global_mutation_candidate(card, preview["global_relation"], pack["owner_parity"]["status"]):
            continue
        items.append({
            "card_id": card["card_id"], "project_claim_hash": card["project_claim_hash"],
            "proposal": card["rule_payload"], "supersedes": preview["supersedes"],
            "selection_token": selection_token(card_id=card["card_id"], project_claim_hash=card["project_claim_hash"],
                proposal=card["rule_payload"], supersedes=preview["supersedes"],
                target_before_sha256=pack["owner_parity"]["canonical_source_hash"]),
        })
    return ({"contract_version": "rule_revision_bundle_v2",
             "target_before_sha256": pack["owner_parity"]["canonical_source_hash"],
             "items": sorted(items, key=lambda item: item["card_id"])} if items else None)


def validate_capacity_projection(item: dict[str, Any], result: dict[str, Any]) -> None:
    capacity = item["capacity"]
    if capacity is None:
        require(item["status"] == "blocked" and item["error_code"] != "instruction_capacity_exceeded",
                "ready or capacity-blocked Core projection needs capacity measurements")
        return
    require_object(capacity, "Core capacity")
    require_exact_keys(capacity, {"rules", "managed_block"}, "Core capacity")
    rules = require_list(capacity["rules"], "Core rule capacity", nonempty=True)
    rule_ids = []
    for rule in rules:
        require_object(rule, "Core rule capacity")
        require_exact_keys(rule, {"rule_id", "actual_bytes", "budget_bytes", "exceeded"}, "Core rule capacity")
        require(isinstance(rule["rule_id"], str) and re.fullmatch(r"rule_[0-9a-f]{12}", rule["rule_id"]), "Core capacity rule ID invalid")
        require(type(rule["actual_bytes"]) is int and rule["actual_bytes"] > 0, "Core rule bytes invalid")
        require(type(rule["budget_bytes"]) is int and rule["budget_bytes"] > 0, "Core rule budget invalid")
        require(type(rule["exceeded"]) is bool and rule["exceeded"] == (rule["actual_bytes"] > rule["budget_bytes"]), "Core rule capacity flag inconsistent")
        rule_ids.append(rule["rule_id"])
    require(len(rule_ids) == len(set(rule_ids)), "Core capacity contains duplicate rule IDs")
    block = require_object(capacity["managed_block"], "Core block capacity")
    require_exact_keys(block, {"before_bytes", "projected_bytes", "budget_bytes", "exceeded"}, "Core block capacity")
    for key, expected in (("before_bytes", result["before_bytes"]), ("projected_bytes", item["projected_bytes"]), ("budget_bytes", result["budget_bytes"])):
        require(type(block[key]) is int and block[key] == expected, "Core block capacity disagrees with projection")
    require(type(block["exceeded"]) is bool and block["exceeded"] == (block["projected_bytes"] > block["budget_bytes"]), "Core block capacity flag inconsistent")
    exceeded = block["exceeded"] or any(rule["exceeded"] for rule in rules)
    require((item["status"] == "ready" and not exceeded) or
            (item["status"] == "blocked" and item["error_code"] == "instruction_capacity_exceeded" and exceeded),
            "Core projection status disagrees with capacity")


def validate_selection_preview(pack: dict[str, Any], *, required: bool) -> dict[str, Any] | None:
    preview = pack["selection_preview"]
    bundle = review_bundle(pack)
    if bundle is None:
        require(preview is None, "selection preview must be null without proposed global mutations")
        return None
    if preview is None and not required:
        return None
    require(isinstance(preview, dict), "global candidates require a Core selection preview before rendering")
    require_exact_keys(preview, {"core_artifact_sha256", "result", "error_code"}, "$.selection_preview")
    digest = preview["core_artifact_sha256"]
    require(digest is None or isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "Core artifact identity invalid")
    result = preview["result"]
    if result is None:
        require_string(preview["error_code"], "selection preview error_code")
        return None
    require(digest is not None and preview["error_code"] is None, "Core receipt needs its actual artifact identity")
    require_object(result, "selection preview result")
    require_exact_keys(result, {"contract_version", "target_before_sha256", "bundle_sha256", "before_bytes", "budget_bytes", "items", "combined"}, "selection preview result")
    require(result["contract_version"] in {"rule_bundle_preview_v1", "rule_bundle_preview_v2"}, "Core preview contract invalid")
    require(result["target_before_sha256"] == bundle["target_before_sha256"], "Core preview before hash mismatch")
    require(result["bundle_sha256"] == canonical_hash(bundle), "Core preview bundle hash mismatch")
    require(type(result["before_bytes"]) is int and result["before_bytes"] >= 0, "Core preview before bytes invalid")
    require(type(result["budget_bytes"]) is int and result["budget_bytes"] > 0, "Core preview budget invalid")
    expected_ids = [item["card_id"] for item in bundle["items"]]
    items = require_list(result["items"], "Core preview items")
    require(len(items) == len(expected_ids), "Core preview item count mismatch")
    for item in items:
        require_object(item, "Core preview item")
    require([item.get("card_id") for item in items if isinstance(item, dict)] == expected_ids, "Core preview must conserve exact card IDs")
    combined = require_object(result["combined"], "Core preview combined")
    combined_ids = require_list(combined.get("card_ids"), "Core combined card IDs", nonempty=True)
    require(all(isinstance(card_id, str) for card_id in combined_ids), "Core combined card ID invalid")
    require(combined_ids == sorted(set(combined_ids)) and set(combined_ids).issubset(expected_ids), "Core combined selection mismatch")
    for item in [*items, combined]:
        keys = {"card_ids"} if item is combined else {"card_id"}
        if result["contract_version"] == "rule_bundle_preview_v2":
            keys.add("capacity")
        require_exact_keys(item, keys | {"status", "projected_bytes", "target_after_sha256", "error_code"}, "Core projection")
        size = item["projected_bytes"]
        require(size is None or type(size) is int and size >= 0, "Core projected bytes invalid")
        if item["status"] == "ready":
            require(size is not None and size <= result["budget_bytes"] and item["error_code"] is None, "ready Core projection exceeds budget or has an error")
            require(isinstance(item["target_after_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", item["target_after_sha256"]), "ready Core projection needs exact after hash")
        else:
            require(item["status"] == "blocked" and item["target_after_sha256"] is None, "blocked Core projection invalid")
            require_string(item["error_code"], "Core projection error")
        if result["contract_version"] == "rule_bundle_preview_v2":
            validate_capacity_projection(item, result)
    return result


def expected_action_policy(card: dict[str, Any], parity_status: str, relation: str | None = None,
                           projection_ready: bool = True) -> tuple[str, list[str]]:
    relation = relation or ("already_covered_exact" if card["classification"] == "already_covered" else card["classification"])
    if global_mutation_candidate(card, relation, parity_status):
        return ("confirm", copy.deepcopy(ALL_ACTIONS)) if projection_ready else ("edit", copy.deepcopy(READ_ONLY_ACTIONS))
    if card["owner_recommendation"] == "no_persistence":
        return "ignore", []
    if relation in {"globalization_challenged", "needs_project_clarification"}:
        return "edit", copy.deepcopy(READ_ONLY_ACTIONS)
    if card["classification"] == "route_to_owner" and card["owner_recommendation"] in {"project_owner", "skill"}:
        action = "keep_project" if card["owner_recommendation"] == "project_owner" else "make_skill"
        return action, copy.deepcopy(READ_ONLY_ACTIONS)
    if relation == "already_covered_exact":
        return "ignore", []
    if card["owner_recommendation"] == "skill":
        return "make_skill", copy.deepcopy(READ_ONLY_ACTIONS)
    if card["classification"] == "route_to_owner" or card["owner_recommendation"] == "project_owner":
        return "keep_project", copy.deepcopy(READ_ONLY_ACTIONS)
    return "edit", copy.deepcopy(READ_ONLY_ACTIONS)


def validate_review_pack(value: Any, *, require_preview: bool = True) -> dict[str, Any]:
    obj = require_object(value, "$")
    require_exact_keys(
        obj,
        REVIEW_INPUT_KEYS,
        "$",
    )
    require(obj["contract_version"] in {NATIVE_REVIEW_PACK_CONTRACT, REVIEW_PACK_CONTRACT, MAP_REVIEW_PACK_CONTRACT, LEGACY_REVIEW_PACK_CONTRACT}, "$.contract_version invalid")
    require(obj["mode"] == "review_pack", "$.mode invalid")
    require(obj["display_locale"] == DISPLAY_LOCALE, f"$.display_locale must be {DISPLAY_LOCALE}")
    require(obj["skill_version"] == SKILL_VERSION, "$.skill_version invalid")
    project = validate_project(obj["project_result"])
    require({NATIVE_REVIEW_PACK_CONTRACT: NATIVE_PROJECT_CONTRACT, REVIEW_PACK_CONTRACT: PROJECT_CONTRACT, MAP_REVIEW_PACK_CONTRACT: MAP_PROJECT_CONTRACT, LEGACY_REVIEW_PACK_CONTRACT: LEGACY_PROJECT_CONTRACT}[obj['contract_version']] == project['contract_version'], 'pack and project generations differ')
    require(obj["status"] == project["status"], "$.status must match project_result.status")
    if project.get('purpose') == 'inspect':
        require(obj['owner_parity'] is None and not obj['review_cards'] and obj['selection_preview'] is None, 'inspection cannot use Owner integration or approval')
        parity = None
    elif project["contract_version"] == NATIVE_PROJECT_CONTRACT:
        require(obj["owner_parity"] is None, "native review does not require Global Owner")
        parity = None
    elif project["contract_version"] == PROJECT_CONTRACT and bool(project["project_cards"]) and all(c.get("kind") == "engineering" for c in project["project_cards"]):
        require(obj["owner_parity"] is None, "engineering advice does not require Global Owner")
        parity = None
    elif project["contract_version"] == PROJECT_CONTRACT and not project["project_cards"]:
        parity = validate_owner_parity(obj["owner_parity"], "$.owner_parity") if obj["owner_parity"] is not None else None
    else:
        parity = validate_owner_parity(obj["owner_parity"], "$.owner_parity")
    cards = require_list(obj["review_cards"], "$.review_cards")
    project_cards = project["project_cards"]
    require(len(cards) == len(project_cards), "$.review_cards must conserve every Project Card")
    for index, raw in enumerate(cards):
        if project_cards[index].get("kind") != "engineering":
            validate_integration_preview(require_object(raw, "review card").get("integration_preview"), f"$.review_cards[{index}].integration_preview")
    result = validate_selection_preview(obj, required=require_preview)
    individual = {item["card_id"]: item for item in result["items"]} if result else {}
    combined_ready = bool(result and result["combined"]["status"] == "ready")
    combined_ids = set(result["combined"]["card_ids"]) if combined_ready else set()
    for index, raw in enumerate(cards):
        path = f"$.review_cards[{index}]"
        item = require_object(raw, path)
        require_exact_keys(
            item,
            {
                "project_claim_hash",
                "selection_token",
                "recommended_action",
                "recommended_action_reason",
                "integration_preview",
                "expected_behavior_change",
                "allowed_actions",
            },
            path,
        )
        require(item["project_claim_hash"] == project_cards[index]["project_claim_hash"], f"{path} Project Card order or identity changed")
        card = project_cards[index]
        if card.get("kind") == "engineering":
            require(item["recommended_action"] == "discuss" and item["allowed_actions"] == [] and item["integration_preview"] is None and item["selection_token"] is None, f"{path}: engineering advice cannot grant rule actions")
            validate_zh_cn_text(item["recommended_action_reason"], f"{path}.recommended_action_reason", max_chars=240, require_han=True)
            require_string(item["expected_behavior_change"], f"{path}.expected_behavior_change")
            continue
        relation = item["integration_preview"]["global_relation"]
        ready = (individual.get(card["card_id"], {}).get("status") == "ready"
                 if require_preview or obj["selection_preview"] is not None else True)
        recommended, expected_actions = expected_action_policy(card, parity["status"], relation, ready)
        require(item["recommended_action"] == recommended, f"{path}.recommended_action violates owner routing")
        validate_zh_cn_text(item["recommended_action_reason"], f"{path}.recommended_action_reason", max_chars=240, require_han=True)
        validate_integration_preview(item["integration_preview"], f"{path}.integration_preview")
        require_string(item["expected_behavior_change"], f"{path}.expected_behavior_change")
        require(
            require_list(item["allowed_actions"], f"{path}.allowed_actions") == expected_actions,
            f"{path}.allowed_actions must exactly match owner and parity policy",
        )
        require(item["recommended_action"] in item["allowed_actions"] or (recommended == "ignore" and not expected_actions), f"{path}.recommended_action must be allowed")
        if "confirm" in expected_actions or card["card_id"] in combined_ids:
            token = require_string(item["selection_token"], f"{path}.selection_token")
            expected_token = selection_token(
                card_id=project_cards[index]["card_id"],
                project_claim_hash=item["project_claim_hash"],
                proposal=project_cards[index]["rule_payload"],
                supersedes=item["integration_preview"]["supersedes"],
                target_before_sha256=parity["canonical_source_hash"],
            )
            require(token == expected_token, f"{path}.selection_token is not deterministic")
        else:
            require(item["selection_token"] is None, f"{path}.selection_token must be null when confirm is unavailable")
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


def __getattr__(name: str) -> Any:
    if name in {
        "sha",
        "valid_model",
        "valid_read_only",
        "build_card",
        "valid_project",
        "valid_parity",
        "valid_review_pack",
        "expect_invalid",
        "run_self_test",
    }:
        import validate_output_selftest as _selftest

        return getattr(_selftest, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_stdin_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Validate Global Owner Scout 5.20.2 JSON contracts from stdin.")
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
            sys.modules.setdefault("validate_output", sys.modules[__name__])
            from validate_output_selftest import run_self_test

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
    except (ContractError, AssertionError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
