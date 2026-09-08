from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .errors import CoreError
from .instructions import (
    MAX_MANAGED_BLOCK_BYTES,
    DocumentSnapshot,
    _nonempty,
    plan_deploy_bundle,
    read_document,
)
from .proposal import RuleBundle, RuleBundleItem


PREVIEW_CONTRACT = "rule_bundle_preview_v1"


def _projection(snapshot: DocumentSnapshot, items: tuple[RuleBundleItem, ...]) -> dict[str, Any]:
    try:
        plan, _ = plan_deploy_bundle(snapshot=snapshot, items=items)
    except CoreError as exc:
        return {
            "status": "blocked",
            "projected_bytes": exc.details.get("projected_bytes"),
            "target_after_sha256": None,
            "error_code": exc.code,
        }
    return {
        "status": "ready",
        "projected_bytes": plan.to_dict()["projected_managed_block_bytes"],
        "target_after_sha256": hashlib.sha256(plan.after).hexdigest(),
        "error_code": None,
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
            {"card_id": item.card_id, **_projection(snapshot, (item,))}
            for item in bundle.items
        ],
        "combined": {
            "card_ids": [item.card_id for item in combined_items],
            **_projection(snapshot, combined_items),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preview an exact rule bundle without writing state.")
    parser.add_argument("--target-file", type=Path, required=True)
    parser.add_argument("--select-card", action="append")
    args = parser.parse_args(argv)
    try:
        bundle = RuleBundle.from_payload(json.load(sys.stdin))
        result = preview_bundle(bundle=bundle, target_file=args.target_file, selected_card_ids=args.select_card)
    except (CoreError, OSError, UnicodeError, ValueError) as exc:
        error = exc.code if isinstance(exc, CoreError) else "preview_input_unavailable"
        print(json.dumps({"status": "error", "error_code": error}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
