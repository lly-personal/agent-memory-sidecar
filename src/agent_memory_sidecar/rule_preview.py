from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .errors import CoreError
from .instructions import (
    MAX_MANAGED_BLOCK_BYTES,
    FilePlan,
    _nonempty,
    normalize_supersedes,
    plan_deploy,
    plan_deploy_bundle,
    read_document,
)
from .proposal import RuleBundle, RuleProposal


PREVIEW_CONTRACT = "rule_bundle_preview_v2"


def _projection(planner: Callable[[], FilePlan]) -> dict[str, Any]:
    try:
        plan = planner()
    except CoreError as exc:
        return {
            "status": "blocked",
            "projected_bytes": exc.details.get("projected_bytes"),
            "target_after_sha256": None,
            "error_code": exc.code,
            "capacity": exc.details.get("capacity"),
        }
    return {
        "status": "ready",
        "projected_bytes": plan.to_dict()["projected_managed_block_bytes"],
        "target_after_sha256": hashlib.sha256(plan.after).hexdigest(),
        "error_code": None,
        "capacity": plan.capacity_dict(),
    }


def preview_rule(*, proposal: RuleProposal, target_file: Path,
                 supersedes: str | Sequence[str] | None = None) -> dict[str, Any]:
    """Bind a scalar preflight to the exact proposal, replacement set and observed file."""
    snapshot = read_document(
        path=target_file,
        target=proposal.instruction_target,
        shadowed=_nonempty(target_file.with_name("AGENTS.override.md")),
    )
    selected = normalize_supersedes(supersedes)
    return {
        "contract_version": "rule_preview_v1",
        "instruction_target": proposal.instruction_target,
        "target_before_sha256": snapshot.file_sha256,
        "proposal_sha256": proposal.proposal_sha256,
        "supersedes": list(selected),
        "before_bytes": snapshot.managed_block_bytes,
        "budget_bytes": MAX_MANAGED_BLOCK_BYTES,
        **_projection(lambda: plan_deploy(snapshot=snapshot, proposal=proposal, supersedes=selected)),
    }


def preview_bundle(*, bundle: RuleBundle, target_file: Path,
                   selected_card_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Use the deployment planner without opening a Store or writing any state."""
    snapshot = read_document(
        path=target_file,
        target=bundle.instruction_target,
        shadowed=_nonempty(target_file.with_name("AGENTS.override.md")),
    )
    if hashlib.sha256(snapshot.data).hexdigest() != bundle.target_before_sha256:
        raise CoreError("rule_revision_stale", "preview target differs from the selected before bytes")
    selected = {item.card_id for item in bundle.items} if selected_card_ids is None else set(selected_card_ids)
    known = {item.card_id for item in bundle.items}
    if not selected or not selected.issubset(known) or selected_card_ids is not None and len(selected) != len(selected_card_ids):
        raise CoreError("invalid_rule_bundle", "preview selection must contain unique known card IDs")
    combined_items = tuple(item for item in bundle.items if item.card_id in selected)
    return {
        "contract_version": PREVIEW_CONTRACT,
        "target_before_sha256": bundle.target_before_sha256,
        "bundle_sha256": bundle.bundle_sha256,
        "before_bytes": snapshot.managed_block_bytes,
        "budget_bytes": MAX_MANAGED_BLOCK_BYTES,
        "items": [
            {"card_id": item.card_id, **_projection(lambda: plan_deploy_bundle(snapshot=snapshot, items=(item,))[0])}
            for item in bundle.items
        ],
        "combined": {
            "card_ids": [item.card_id for item in combined_items],
            **_projection(lambda: plan_deploy_bundle(snapshot=snapshot, items=combined_items)[0]),
        },
    }


def main(argv: Sequence[str] | None = None, *, single: bool = False) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview exact rules without writing state.")
    parser.add_argument("--target-file", type=Path, required=True)
    parser.add_argument("--supersedes" if single else "--select-card", action="append")
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if single:
            result = preview_rule(proposal=RuleProposal.from_payload(payload), target_file=args.target_file, supersedes=args.supersedes)
        else:
            result = preview_bundle(bundle=RuleBundle.from_payload(payload), target_file=args.target_file, selected_card_ids=args.select_card)
    except (CoreError, OSError, UnicodeError, ValueError) as exc:
        error = exc.code if isinstance(exc, CoreError) else "preview_input_unavailable"
        print(json.dumps({"status": "error", "error_code": error}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
