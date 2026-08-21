from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "domain.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "specs" / "axioms.md",
    ROOT / "docs" / "specs" / "topology.md",
    ROOT / "docs" / "specs" / "interface.md",
    ROOT / "docs" / "knowledge" / "README.md",
    ROOT / "docs" / "user-guide.zh.md",
    ROOT / "docs" / "operator-reference.zh.md",
    ROOT / "docs" / "codex-desktop-setup.md",
    ROOT / "docs" / "context" / "codex-customization-boundaries.md",
    ROOT / "docs" / "evidence" / "README.md",
    ROOT / "docs" / "decisions" / "0057-agent-memory-core-v1.zh.md",
    ROOT / "docs" / "decisions" / "0058-persistent-runtime-journal.zh.md",
    ROOT / "docs" / "decisions" / "0059-bounded-behavior-set-evolution.zh.md",
    ROOT / "docs" / "decisions" / "0060-periodic-global-owner-scout.zh.md",
    ROOT / "docs" / "decisions" / "0063-direct-visible-owner-review-packs.zh.md",
    ROOT / "docs" / "decisions" / "0064-chinese-contextual-dual-projection-review-packs.zh.md",
    ROOT / "docs" / "decisions" / "0065-host-aware-project-enrollment.zh.md",
    ROOT / "docs" / "decisions" / "0066-scout-execution-and-visible-output-integrity.zh.md",
    ROOT / "docs" / "decisions" / "0067-scout-production-source-activation-gate.zh.md",
    ROOT / "docs" / "decisions" / "0068-interactive-project-scout-primary.zh.md",
    ROOT / "docs" / "decisions" / "0069-cross-device-cold-start-continuity.zh.md",
    ROOT / "docs" / "decisions" / "0070-atomic-review-pack-rule-bundles.zh.md",
    ROOT / "docs" / "decisions" / "0071-wysiwys-review-pack-bundles-and-physical-target-containment.zh.md",
    ROOT / "docs" / "decisions" / "0072-allowlisted-public-distribution-lane.zh.md",
    ROOT / "docs" / "decisions" / "0073-public-engineering-authority-cutover.zh.md",
    ROOT / "docs" / "decisions" / "0074-public-operations-closure.zh.md",
    ROOT / "docs" / "decisions" / "0075-unified-workstation-reconcile.zh.md",
    ROOT / "docs" / "decisions" / "0076-task-scoped-review-pack-delivery.zh.md",
    ROOT / "specs" / "README.md",
    ROOT / "specs" / "agent-memory-core-v1.md",
    ROOT / "specs" / "public-distribution-v1.md",
    ROOT / "specs" / "public-authority-cutover-v1.md",
    ROOT / "specs" / "source-authority-cutover-v2.md",
    ROOT / "specs" / "global-owner-scout-delivery-v1.md",
)
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    failures: list[str] = []
    for document in ACTIVE_DOCUMENTS:
        if not document.is_file():
            failures.append(f"missing active document: {document.relative_to(ROOT)}")
            continue
        text = document.read_text(encoding="utf-8")
        for raw in LINK.findall(text):
            value = raw.strip().split("#", 1)[0]
            if not value or "://" in value or value.startswith("mailto:"):
                continue
            target = (document.parent / value).resolve(strict=False)
            if not target.exists():
                failures.append(
                    f"{document.relative_to(ROOT)} -> {raw}"
                )
    if failures:
        print("Broken active-document links:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Checked {len(ACTIVE_DOCUMENTS)} active documents: all links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
