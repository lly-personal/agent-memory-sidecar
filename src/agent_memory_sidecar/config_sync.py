"""Explicit, commit-bound non-secret Codex field reconciliation (outside Core Store)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tomllib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .errors import CoreError
from .file_security import logical_absolute
from .instruction_sync import _git
from .instructions import (
    _acquire_file_lock, _assert_physical_target, _read_regular_bytes, _release_file_lock,
    assert_physical_directory, atomic_write,
)

POLICY = "codex_config_policy_v1"
PLAN = "codex_config_plan_v1"
JOURNAL = "codex_config_transaction_v1"
BARE = r"[A-Za-z0-9_-]+"
SCALAR = r'''(?:"(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*'|true|false|[+-]?[0-9][0-9_]*)'''
ASSIGNMENT = re.compile(rf"^(?P<prefix>\s*(?P<key>{BARE})\s*=\s*)(?P<value>{SCALAR})(?P<tail>\s*(?:#[^\r\n]*)?)(?P<eol>\r?\n)?$")
HEADER = re.compile(rf"^\s*\[\s*({BARE}(?:\s*\.\s*{BARE})*)\s*\]\s*(?:#[^\r\n]*)?(?:\r?\n)?$")


def _fail(code: str, message: str) -> None:
    raise CoreError("config_" + code, message)


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _hash(_json(value))


def _scalar(value: Any) -> bool:
    return type(value) in (str, bool, int)


def _same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return left == right


def load_policy(*, source: Path, commit: str, policy_file: str) -> dict[str, Any]:
    """Read only a committed blob; no fetch, checkout, installation or host discovery."""
    path = PurePosixPath(policy_file)
    if (not re.fullmatch(r"[0-9a-f]{40}", commit) or path.is_absolute()
            or ".." in path.parts or "\\" in policy_file or ":" in policy_file
            or path.as_posix() != policy_file):
        _fail("source_invalid", "Use a full commit and a repository-relative policy path")
    root = logical_absolute(source)
    assert_physical_directory(root)
    if _git(root, "rev-parse", f"{commit}^{{commit}}").decode().strip() != commit:
        _fail("source_invalid", "Policy commit did not resolve exactly")
    mode = _git(root, "ls-tree", commit, "--", policy_file).decode().split()
    if not mode or mode[0] != "100644":
        _fail("source_invalid", "Policy must be a committed regular non-executable blob")
    data = _git(root, "show", f"{commit}:{policy_file}")
    try:
        policy = json.loads(data)
    except (ValueError, UnicodeError):
        _fail("policy_invalid", "Policy must be UTF-8 JSON")
    validate_policy(policy)
    return {"policy": policy, "commit": commit, "file": policy_file, "sha256": _hash(data),
            "source_identity": _hash(str(root).encode())}


def validate_policy(policy: Any) -> None:
    if (not isinstance(policy, dict) or set(policy) != {
        "contract_version", "owner", "platforms", "codex_versions", "fields"
    } or policy["contract_version"] != POLICY or policy["owner"] != "codex-instructions"):
        _fail("policy_invalid", "Unsupported policy contract or owner")
    for key in ("platforms", "codex_versions"):
        if (not isinstance(policy[key], list) or not policy[key]
                or any(not isinstance(v, str) or not v for v in policy[key])):
            _fail("policy_invalid", "Policy requires explicit platform and exact version enrollment")
    if not isinstance(policy["fields"], list) or not policy["fields"]:
        _fail("policy_invalid", "Policy requires explicitly enrolled non-secret fields")
    seen: list[list[str]] = []
    for field in policy["fields"]:
        if (not isinstance(field, dict) or set(field) != {"path", "value", "non_secret", "rationale", "risk"}
                or field["non_secret"] is not True or not _scalar(field["value"])
                or not isinstance(field["path"], list) or not field["path"]
                or any(not isinstance(p, str) or not re.fullmatch(BARE, p) for p in field["path"])
                or not isinstance(field["rationale"], str) or not field["rationale"].strip()
                or not isinstance(field["risk"], str) or not field["risk"].strip()):
            _fail("policy_invalid", "Each field needs a bare-key path, scalar value, non-secret declaration, rationale and risk")
        path = field["path"]
        if any(path[:len(old)] == old or old[:len(path)] == path for old in seen):
            _fail("policy_invalid", "Overlapping or duplicate managed paths")
        seen.append(path)


def _parse(data: bytes) -> dict[str, Any]:
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError):
        _fail("toml_invalid", "Configuration is not valid UTF-8 TOML; contents are not included")


def _value(document: dict[str, Any], path: list[str]) -> dict[str, Any]:
    node: Any = document
    for key in path:
        if not isinstance(node, dict):
            _fail("shape_unsupported", "A managed path crosses a non-table value")
        if key not in node:
            return {"present": False}
        node = node[key]
    if not _scalar(node):
        _fail("shape_unsupported", "Only enrolled scalar fields can be read or edited")
    return {"present": True, "value": node}


def _edit(data: bytes, path: list[str], wanted: dict[str, Any], literal: str | None = None) -> tuple[bytes, str | None]:
    """Patch one literal, then prove the entire TOML tree changed only at that path."""
    original = _parse(data)
    before = _value(original, path)
    lines = data.decode("utf-8").splitlines(keepends=True)
    section: list[str] = []
    matches = []
    headers = []
    for index, line in enumerate(lines):
        header = HEADER.fullmatch(line)
        if header:
            section = [p.strip() for p in header[1].split(".")]
            if section == path[:-1]:
                headers.append(index)
        match = ASSIGNMENT.fullmatch(line)
        if match and section == path[:-1] and match["key"] == path[-1]:
            matches.append((index, match))
    old_literal = None
    rendered = literal if literal is not None else (json.dumps(wanted.get("value"), ensure_ascii=False))
    if before["present"]:
        if len(matches) != 1:
            _fail("syntax_unsupported", "Managed field needs one single-line bare-key scalar assignment")
        index, match = matches[0]
        old_literal = match["value"]
        if wanted["present"]:
            lines[index] = match["prefix"] + rendered + match["tail"] + (match["eol"] or "")
        else:
            # A removed enrollment owns only its generated assignment, not adjacent comments.
            comment = match["tail"].lstrip()
            newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
            lines[index] = comment.rstrip("\r\n") + newline if comment.startswith("#") else ""
    elif wanted["present"]:
        if matches or (path[:-1] and len(headers) != 1):
            _fail("syntax_unsupported", "Missing fields require top level or an existing simple explicit table")
        newline = "\r\n" if b"\r\n" in data else "\n"
        index = headers[0] + 1 if path[:-1] else 0
        if index and not lines[index - 1].endswith("\n"):
            _fail("syntax_unsupported", "Table header must end with a newline before insertion")
        lines.insert(index, f"{path[-1]} = {rendered}{newline}")
    expected = copy.deepcopy(original)
    node = expected
    for key in path[:-1]:
        if key not in node or not isinstance(node[key], dict):
            _fail("syntax_unsupported", "Creating tables is outside this field contract")
        node = node[key]
    if wanted["present"]:
        node[path[-1]] = wanted["value"]
    else:
        node.pop(path[-1], None)
    result = "".join(lines).encode("utf-8")
    if not _same(_parse(result), expected):
        _fail("syntax_unsupported", "Patch could not prove preservation of all unmanaged TOML values")
    return result, old_literal


def _target(path: Path) -> tuple[Path, bytes]:
    target = logical_absolute(path)
    if target.name != "config.toml":
        _fail("target_invalid", "Explicit target must be named config.toml")
    existed, data = _read_regular_bytes(target)
    if not existed:
        _fail("target_missing", "First version requires an existing explicit config.toml")
    _parse(data)
    return target, data


def _journal_path(target: Path) -> Path:
    return target.with_name(".agent-memory-config-transaction.json")


def _journal(target: Path) -> tuple[dict[str, Any] | None, str | None]:
    exists, data = _read_regular_bytes(_journal_path(target))
    if not exists:
        return None, None
    try:
        value = json.loads(data)
        if (value["contract_version"] != JOURNAL or value["target"] != str(target)
                or value["status"] not in {"prepared", "applied", "restore_prepared", "restored"}
                or not isinstance(value["changes"], list)):
            raise ValueError()
        original = {k: v for k, v in value.items() if k not in {
            "plan_hash", "approval_ref", "restore_approval_ref", "restore_plan"}}
        original.update(contract_version=PLAN, status="authorization_required")
        if _digest(original) != value["plan_hash"]:
            raise ValueError()
        if value["status"] == "restore_prepared":
            restore_plan = value["restore_plan"]
            if (restore_plan["target"] != str(target) or restore_plan["operation"] != "restore"
                    or _digest({k: v for k, v in restore_plan.items() if k != "plan_hash"})
                    != restore_plan["plan_hash"]):
                raise ValueError()
    except (ValueError, KeyError, TypeError):
        _fail("journal_invalid", "Transaction metadata is invalid; no target changed")
    return value, _hash(data)


def preview(*, bundle: dict[str, Any], target: Path, platform: str, codex_version: str) -> dict[str, Any]:
    policy = bundle["policy"]
    validate_policy(policy)
    if platform not in policy["platforms"] or codex_version not in policy["codex_versions"]:
        _fail("applicability_unknown", "Platform or exact Codex version is not enrolled by this policy")
    target, before = _target(target)
    journal, journal_hash = _journal(target)
    if journal and journal["status"] in {"prepared", "restore_prepared"}:
        _fail("recovery_required", "Reconcile the interrupted transaction before any new application")
    after = before
    changes = []
    fields = []
    for field in policy["fields"]:
        observed = _value(_parse(before), field["path"])
        fields.append({"path": field["path"], "observed": observed, "desired": field["value"],
                       "rationale": field["rationale"], "risk": field["risk"]})
        if observed["present"] and _same(observed["value"], field["value"]):
            continue
        wanted = {"present": True, "value": field["value"]}
        after, literal = _edit(after, field["path"], wanted)
        changes.append({"path": field["path"], "before": observed, "after": wanted,
                        "before_literal": literal, "rationale": field["rationale"], "risk": field["risk"]})
    plan = {"contract_version": PLAN, "operation": "apply", "target": str(target),
            "source": {k: v for k, v in bundle.items() if k != "policy"},
            "policy_sha256": _digest(policy), "platform": platform, "codex_version": codex_version,
            "before_sha256": _hash(before), "after_sha256": _hash(after),
            "previous_transaction_sha256": journal_hash, "changes": changes, "fields": fields,
            "recovery_scope": "latest_delta_only", "supersedes_previous_recovery": bool(journal),
            "authorization_evidence_verification": "external_reference_not_verified",
            "status": "authorization_required" if changes else "no_change",
            "effective_values": "unknown", "consumer_verification": "unverified"}
    plan["plan_hash"] = _digest(plan)
    return plan


@contextmanager
def _lock(target: Path) -> Iterator[None]:
    lock = target.with_name(".agent-memory-config.lock")
    _assert_physical_target(lock, allow_missing=True)
    with lock.open("a+b") as handle:
        _acquire_file_lock(handle)
        try:
            physical = _assert_physical_target(lock, allow_missing=False)
            opened = os.fstat(handle.fileno())
            if physical is None or (physical.st_dev, physical.st_ino) != (opened.st_dev, opened.st_ino):
                _fail("lock_unsafe", "Transaction lock identity changed")
            yield
        finally:
            _release_file_lock(handle)


def _authorize(plan: dict[str, Any], plan_hash: str, approval_ref: str) -> None:
    if not approval_ref or not approval_ref.strip() or plan_hash != plan["plan_hash"]:
        _fail("authorization_required", "A current explicit approval reference and exact fresh plan hash are required")


def apply(*, bundle: dict[str, Any], target: Path, platform: str, codex_version: str,
          plan_hash: str, approval_ref: str) -> dict[str, Any]:
    target, _ = _target(target)
    with _lock(target):
        plan = preview(bundle=bundle, target=target, platform=platform, codex_version=codex_version)
        _authorize(plan, plan_hash, approval_ref)
        if not plan["changes"]:
            return plan
        _, before = _target(target)
        if _hash(before) != plan["before_sha256"] or _journal(target)[1] != plan["previous_transaction_sha256"]:
            _fail("concurrent_drift", "Target or transaction changed after authorized planning")
        after = before
        for change in plan["changes"]:
            after, _ = _edit(after, change["path"], change["after"])
        if _hash(after) != plan["after_sha256"]:
            _fail("concurrent_drift", "Candidate differs from the authorized result")
        journal = {**plan, "contract_version": JOURNAL, "status": "prepared", "approval_ref": approval_ref}
        atomic_write(_journal_path(target), _json(journal))
        # Recheck after durable intent and immediately before replacement. No blind retry on failure.
        if _target(target)[1] != before:
            _fail("concurrent_drift", "Target changed after preparation; reconcile without replay")
        atomic_write(target, after)
        if _target(target)[1] != after:
            _fail("readback_failed", "File readback differs; transaction remains prepared for reconciliation")
        journal["status"] = "applied"
        atomic_write(_journal_path(target), _json(journal))
        return {**plan, "status": "file_applied", "effective_values": "unknown",
                "consumer_verification": "unverified"}


def reconcile(*, target: Path) -> dict[str, Any]:
    target, data = _target(target)
    journal, digest = _journal(target)
    if journal is None:
        return {"status": "no_transaction", "effective_values": "unknown"}
    current = _hash(data)
    position = ("before" if current == journal["before_sha256"] else
                "after" if current == journal["after_sha256"] else "drifted")
    fields = [{"path": c["path"], "position":
               "before" if _same(_value(_parse(data), c["path"]), c["before"]) else
               "after" if _same(_value(_parse(data), c["path"]), c["after"]) else "conflict"}
              for c in journal["changes"]]
    return {"status": journal["status"], "file_position": position, "fields": fields,
            "transaction_sha256": digest, "automatic_replay": False,
            "effective_values": "unknown", "consumer_verification": "unverified"}


def preview_restore(*, target: Path) -> dict[str, Any]:
    target, before = _target(target)
    journal, journal_hash = _journal(target)
    if journal is None or journal["status"] == "restored":
        _fail("recovery_unavailable", "No outstanding latest field delta to restore")
    after = before
    changes = []
    for change in reversed(journal["changes"]):
        observed = _value(_parse(after), change["path"])
        if _same(observed, change["before"]):
            continue  # Interrupted before mutation, or already restored: never replay.
        if not _same(observed, change["after"]):
            _fail("recovery_conflict", "A managed field changed since application; no fields restored")
        after, _ = _edit(after, change["path"], change["before"], change["before_literal"])
        changes.append({"path": change["path"], "before": observed, "after": change["before"]})
    plan = {"contract_version": PLAN, "operation": "restore", "target": str(target),
            "source": journal["source"], "applied_plan_hash": journal["plan_hash"],
            "platform": journal["platform"], "codex_version": journal["codex_version"],
            "transaction_sha256": journal_hash, "before_sha256": _hash(before),
            "after_sha256": _hash(after), "changes": changes, "status": "authorization_required",
            "authorization_evidence_verification": "external_reference_not_verified"}
    plan["plan_hash"] = _digest(plan)
    return plan


def restore(*, target: Path, plan_hash: str, approval_ref: str) -> dict[str, Any]:
    target, _ = _target(target)
    with _lock(target):
        plan = preview_restore(target=target)
        _authorize(plan, plan_hash, approval_ref)
        journal, journal_hash = _journal(target)
        assert journal is not None
        _, before = _target(target)
        if _hash(before) != plan["before_sha256"] or journal_hash != plan["transaction_sha256"]:
            _fail("concurrent_drift", "Target or transaction changed after restoration planning")
        after = before
        for change in reversed(journal["changes"]):
            if _same(_value(_parse(after), change["path"]), change["after"]):
                after, _ = _edit(after, change["path"], change["before"], change["before_literal"])
        if _hash(after) != plan["after_sha256"]:
            _fail("concurrent_drift", "Restoration differs from the authorized result")
        journal["status"] = "restore_prepared"
        journal["restore_plan"] = plan
        journal["restore_approval_ref"] = approval_ref
        atomic_write(_journal_path(target), _json(journal))
        if _target(target)[1] != before:
            _fail("concurrent_drift", "Target changed before restoration")
        atomic_write(target, after)
        if _target(target)[1] != after:
            _fail("readback_failed", "Restoration readback differs; reconcile before retry")
        journal["status"] = "restored"
        atomic_write(_journal_path(target), _json(journal))
        return {**plan, "status": "fields_restored", "effective_values": "unknown",
                "consumer_verification": "unverified"}


def verify(*, bundle: dict[str, Any], target: Path, platform: str, codex_version: str,
           observation: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = preview(bundle=bundle, target=target, platform=platform, codex_version=codex_version)
    result = {"file_values": "match" if not plan["changes"] else "differ",
              "effective_values": "unknown", "consumer_verification": "unverified",
              "unobserved_sources": ["managed policy", "profile", "CLI overrides", "session overrides"],
              "target_sha256": plan["before_sha256"]}
    if observation is None:
        return result
    if not isinstance(observation, dict):
        _fail("observation_invalid", "Observation must be an object")
    if (observation.get("target_sha256") != plan["before_sha256"]
            or observation.get("platform") != platform or observation.get("codex_version") != codex_version
            or not isinstance(observation.get("entrypoint"), str) or not observation["entrypoint"].strip()
            or not isinstance(observation.get("evidence_ref"), str) or not observation["evidence_ref"].strip()):
        _fail("observation_stale", "Consumer observation must bind target bytes, platform, version, entrypoint and evidence")
    observed = observation.get("fields", [])
    expected = bundle["policy"]["fields"]
    if (not isinstance(observed, list) or len(observed) != len(expected)
            or any(not isinstance(f, dict) or not isinstance(f.get("path"), list)
                   or any(not isinstance(p, str) for p in f["path"])
                   or not _scalar(f.get("value")) for f in observed)
            or {tuple(f.get("path", [])) for f in observed} != {tuple(f["path"]) for f in expected}):
        _fail("observation_incomplete", "Consumer observation requires the exact enrolled field set")
    matches = all(any(f["path"] == row["path"] and _same(f["value"], row.get("value"))
                      for row in observed) for f in expected)
    result.update(effective_values="reported_match" if matches else "reported_differ",
                  consumer_verification="externally_reported", entrypoint=observation["entrypoint"],
                  evidence_ref=observation["evidence_ref"])
    return result
