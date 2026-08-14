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
    ROOT / "docs" / "decisions" / "0072-allowlisted-public-distribution-lane.zh.md",
    ROOT / "specs" / "README.md",
    ROOT / "specs" / "agent-memory-core-v1.md",
    ROOT / "specs" / "public-distribution-v1.md",
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
