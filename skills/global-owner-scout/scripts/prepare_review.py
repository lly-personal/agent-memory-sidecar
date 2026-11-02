#!/usr/bin/env python3
"""Bind confirmation actions to the installed Core's read-only planner."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from resolve_owner_parity import CORE_STATE_DIR, is_physical_directory, is_physical_file, resolve
from validate_output import (
    ContractError, expected_action_policy, review_bundle, review_pack_hash,
    validate_review_pack, validate_selection_preview,
)


def installed_core(codex_home: Path) -> tuple[Path, str]:
    store = codex_home / CORE_STATE_DIR / "memory.sqlite"
    if not is_physical_directory(store.parent) or not is_physical_file(store):
        raise ContractError("core_preview_unavailable")
    with closing(sqlite3.connect(store.absolute().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        row = db.execute(
            "SELECT identity_version, artifact_path, artifact_sha256 FROM runtime_installation WHERE singleton = 1"
        ).fetchone()
    if row is None or row[0] != "runtime_installation_v1":
        raise ContractError("core_preview_unavailable")
    path = Path(row[1])
    digest = str(row[2]).removeprefix("sha256:")
    if not path.is_absolute() or not is_physical_file(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ContractError("core_preview_identity_mismatch")
    return path, digest


def prepare_review(value: Any, *, codex_home: Path, selected_card_ids: list[str] | None = None) -> dict[str, Any]:
    pack = copy.deepcopy(validate_review_pack(value, require_preview=False))
    if resolve(codex_home) != pack["owner_parity"]:
        raise ContractError("owner_parity_changed_before_preview")
    bundle = review_bundle(pack)
    receipt = None
    if bundle:
        receipt = {"core_artifact_sha256": None, "result": None, "error_code": None}
        try:
            artifact, digest = installed_core(codex_home)
            receipt["core_artifact_sha256"] = digest
            selection_args = [part for card_id in selected_card_ids or [] for part in ("--select-card", card_id)]
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(artifact), "preview-bundle", "--target-file", str(codex_home / "AGENTS.md"), *selection_args],
                input=json.dumps(bundle, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8",
            )
            if process.returncode:
                error = json.loads(process.stderr)
                receipt["error_code"] = error.get("error_code", "core_preview_failed")
            else:
                receipt["result"] = json.loads(process.stdout)
                pack["selection_preview"] = receipt
                validate_selection_preview(pack, required=True)
                expected_ids = sorted(selected_card_ids) if selected_card_ids is not None else [item["card_id"] for item in bundle["items"]]
                if receipt["result"]["combined"]["card_ids"] != expected_ids:
                    raise ContractError("core_preview_selection_mismatch")
        except (ContractError, sqlite3.Error, OSError, UnicodeError, ValueError) as exc:
            receipt["result"] = None
            receipt["error_code"] = str(exc) if isinstance(exc, ContractError) else "core_preview_unavailable"
    pack["selection_preview"] = receipt
    result = receipt["result"] if receipt else None
    individual = {item["card_id"]: item for item in result["items"]} if result else {}
    combined_ready = bool(result and result["combined"]["status"] == "ready")
    combined_ids = set(result["combined"]["card_ids"]) if combined_ready else set()
    selected = {item["card_id"]: item for item in bundle["items"]} if bundle else {}
    for card, review in zip(pack["project_result"]["project_cards"], pack["review_cards"]):
        ready = individual.get(card["card_id"], {}).get("status") == "ready"
        recommendation, actions = expected_action_policy(
            card, pack["owner_parity"]["status"], review["integration_preview"]["global_relation"], ready,
        )
        if card["card_id"] in combined_ids and not ready:
            review["recommended_action_reason"] = "此项仅与所选整合方案一起通过预演，可使用上方完整组合确认；单独接受需先修改并重新预演。"
        elif recommendation != review["recommended_action"]:
            review["recommended_action_reason"] = (
                "当前建议需先整理或补齐规则预演；原项目证据保留，本次没有规则生效。"
                if recommendation == "edit" else "按当前全局关系与准确规则预演判断；本次没有规则生效。"
            )
        review["recommended_action"] = recommendation
        review["allowed_actions"] = actions
        item = selected.get(card["card_id"])
        review["selection_token"] = item["selection_token"] if item and (ready or card["card_id"] in combined_ids) else None
    pack["review_pack_hash"] = review_pack_hash(pack)
    return validate_review_pack(pack)
