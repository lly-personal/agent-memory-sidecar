#!/usr/bin/env python3
"""Single-source deterministic synchronizer for component versions and dual Anchor copies."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$")
PLUGIN_ANCHOR_REL = Path("plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor")
REPO_ANCHOR_REL = Path(".agents/skills/agent-memory-bootstrap-anchor")


class VersionSyncError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VersionSyncError(message)


def read_current_versions(root: Path = ROOT) -> dict[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = str(project["version"])
    codex_plugin = json.loads(
        (root / "plugins/agent-memory-sidecar/.codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    plugin = str(codex_plugin["version"])
    bootstrap_text = (
        root / "skills/agent-memory-workstation-bootstrap/scripts/bootstrap_contracts.py"
    ).read_text(encoding="utf-8")
    b_match = re.search(r'^BOOTSTRAP_VERSION\s*=\s*"([^"]+)"', bootstrap_text, re.MULTILINE)
    s_match = re.search(r'^SCOUT_VERSION\s*=\s*"([^"]+)"', bootstrap_text, re.MULTILINE)
    _require(b_match is not None and s_match is not None, "bootstrap_or_scout_version_missing")
    return {
        "core": core,
        "plugin": plugin,
        "bootstrap": b_match.group(1),
        "scout": s_match.group(1),
    }


def _sub_once(text: str, pattern: str, replacement: str, label: str, *, flags: int = re.MULTILINE) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    _require(count == 1, f"pattern_not_found:{label}")
    return updated


def _sub_all(text: str, pattern: str, replacement: str, label: str, *, flags: int = re.MULTILINE) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    _require(count >= 1, f"pattern_not_found:{label}")
    return updated


def _update_compatibility_table(text: str, versions: dict[str, str], review_contract: str) -> str:
    core = versions["core"]
    row = (
        f"| v{core} | {core} | {versions['plugin']} | {versions['bootstrap']} "
        f"| {versions['scout']} | {review_contract} | 3.11–3.13 |"
    )
    existing = re.compile(rf"^\| v{re.escape(core)} \|.*$", re.MULTILINE)
    if existing.search(text):
        return existing.sub(row, text, count=1)
    header_marker = "|---|---:|---:|---:|---:|---:|---|\n"
    idx = text.find(header_marker)
    _require(idx != -1, "compatibility_table_header_missing")
    insert_at = idx + len(header_marker)
    return text[:insert_at] + row + "\n" + text[insert_at:]


def compute_expected_files(
    root: Path,
    *,
    core: str,
    plugin: str,
    bootstrap: str,
    scout: str,
) -> dict[Path, bytes]:
    for name, value in (("core", core), ("plugin", plugin), ("bootstrap", bootstrap), ("scout", scout)):
        _require(SEMVER_RE.fullmatch(value) is not None, f"invalid_version:{name}:{value}")

    versions = {"core": core, "plugin": plugin, "bootstrap": bootstrap, "scout": scout}
    expected: dict[Path, bytes] = {}

    def text_of(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8")

    def put_text(rel: str, content: str) -> None:
        expected[root / rel] = content.replace("\r\n", "\n").encode("utf-8")

    # 1. Core package metadata & __init__.py
    put_text(
        "pyproject.toml",
        _sub_once(text_of("pyproject.toml"), r'^version\s*=\s*"[^"]+"', f'version = "{core}"', "pyproject.version"),
    )
    put_text(
        "src/agent_memory_sidecar/__init__.py",
        _sub_once(
            text_of("src/agent_memory_sidecar/__init__.py"),
            r'^__version__\s*=\s*"[^"]+"',
            f'__version__ = "{core}"',
            "init.__version__",
        ),
    )

    # 2. Plugin & marketplace manifests
    for rel in (
        "plugins/agent-memory-sidecar/.codex-plugin/plugin.json",
        "plugins/agent-memory-sidecar/.claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    ):
        put_text(rel, _sub_once(text_of(rel), r'"version"\s*:\s*"[^"]+"', f'"version": "{plugin}"', rel))

    put_text(
        ".agents/plugins/marketplace.json",
        _sub_once(
            text_of(".agents/plugins/marketplace.json"),
            r'"ref"\s*:\s*"v[^"]+"',
            f'"ref": "v{core}"',
            ".agents/plugins/marketplace.json",
        ),
    )

    # 3. Bootstrap version constants & Skill docs
    for rel in (
        "skills/agent-memory-workstation-bootstrap/scripts/bootstrap_contracts.py",
        "skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py",
        "skills/agent-memory-workstation-bootstrap/scripts/enrollment.py",
    ):
        body = text_of(rel)
        body = _sub_once(body, r'^BOOTSTRAP_VERSION\s*=\s*"[^"]+"', f'BOOTSTRAP_VERSION = "{bootstrap}"', f"{rel}:bootstrap")
        body = _sub_once(body, r'^SCOUT_VERSION\s*=\s*"[^"]+"', f'SCOUT_VERSION = "{scout}"', f"{rel}:scout")
        if rel.endswith("enrollment.py"):
            body = _sub_once(body, r"Bootstrap [0-9]+\.[0-9]+\.[0-9]+", f"Bootstrap {bootstrap}", f"{rel}:doc")
        put_text(rel, body)

    bs_skill = text_of("skills/agent-memory-workstation-bootstrap/SKILL.md")
    bs_skill = _sub_once(bs_skill, r"Skill version:\s*`[^`]+`", f"Skill version: `{bootstrap}`", "bootstrap SKILL version")
    bs_skill = _sub_once(
        bs_skill,
        r"Validate Bootstrap `[^`]+`, Scout `[^`]+`",
        f"Validate Bootstrap `{bootstrap}`, Scout `{scout}`",
        "bootstrap SKILL validate",
    )
    put_text("skills/agent-memory-workstation-bootstrap/SKILL.md", bs_skill)

    bs_contracts = text_of("skills/agent-memory-workstation-bootstrap/references/contracts.md")
    bs_contracts = _sub_all(
        bs_contracts,
        r"`bootstrap_version`:\s*`[^`]+`",
        f"`bootstrap_version`: `{bootstrap}`",
        "bootstrap contracts.md",
    )
    put_text("skills/agent-memory-workstation-bootstrap/references/contracts.md", bs_contracts)

    # 4. Scout version constants & Skill docs
    scout_skill = text_of("skills/global-owner-scout/SKILL.md")
    scout_skill = _sub_once(scout_skill, r"Skill version:\s*`[^`]+`", f"Skill version: `{scout}`", "scout SKILL version")
    review_match = re.search(r"User review:\s*`global_owner_scout_review_pack_(v\d+)`", scout_skill)
    _require(review_match is not None, "scout_review_contract_missing")
    put_text("skills/global-owner-scout/SKILL.md", scout_skill)

    validator = text_of("skills/global-owner-scout/scripts/validate_output.py")
    validator = _sub_once(validator, r'^SKILL_VERSION\s*=\s*"[^"]+"', f'SKILL_VERSION = "{scout}"', "validate_output.SKILL_VERSION")
    validator = _sub_all(validator, r"Global Owner Scout [0-9]+\.[0-9]+\.[0-9]+", f"Global Owner Scout {scout}", "validate_output.doc")
    put_text("skills/global-owner-scout/scripts/validate_output.py", validator)

    for rel in (
        "skills/global-owner-scout/scripts/render_review.py",
        "skills/global-owner-scout/scripts/verify_visible_output.py",
    ):
        put_text(rel, _sub_once(text_of(rel), r"Global Owner Scout [0-9]+\.[0-9]+\.[0-9]+", f"Global Owner Scout {scout}", rel))

    # 5. COMPATIBILITY.md table row
    put_text("COMPATIBILITY.md", _update_compatibility_table(text_of("COMPATIBILITY.md"), versions, review_match.group(1)))

    # 6. README.md release install refs & Bootstrap version
    readme = text_of("README.md")
    readme = _sub_once(
        readme,
        r"(codex plugin marketplace add lly-personal/agent-memory-sidecar --ref )v[0-9]+\.[0-9]+\.[0-9]+",
        rf"\g<1>v{core}",
        "README codex ref",
    )
    readme = _sub_once(
        readme,
        r"(pi install git:github\.com/lly-personal/agent-memory-sidecar@)v[0-9]+\.[0-9]+\.[0-9]+",
        rf"\g<1>v{core}",
        "README pi ref",
    )
    readme = _sub_once(
        readme,
        r"(claude plugin marketplace add https://github\.com/lly-personal/agent-memory-sidecar\.git#)v[0-9]+\.[0-9]+\.[0-9]+",
        rf"\g<1>v{core}",
        "README claude ref",
    )
    readme = _sub_once(
        readme,
        r"(agent_memory_sidecar-)[0-9]+\.[0-9]+\.[0-9]+(-py3-none-any\.whl)",
        rf"\g<1>{core}\g<2>",
        "README wheel version",
    )
    readme = _sub_once(
        readme,
        r"Workstation Bootstrap [0-9]+\.[0-9]+\.[0-9]+",
        f"Workstation Bootstrap {bootstrap}",
        "README bootstrap version",
    )
    put_text("README.md", readme)

    # 6b. Active L2/L3 spec Bootstrap version mentions
    put_text(
        "docs/specs/topology.md",
        _sub_once(text_of("docs/specs/topology.md"), r"Bootstrap [0-9]+\.[0-9]+\.[0-9]+ 先通过", f"Bootstrap {bootstrap} 先通过", "topology.md bootstrap"),
    )
    put_text(
        "docs/specs/interface.md",
        _sub_once(
            text_of("docs/specs/interface.md"),
            r"`agent-memory-workstation-bootstrap` Skill [0-9]+\.[0-9]+\.[0-9]+ 提供三个显式模式",
            f"`agent-memory-workstation-bootstrap` Skill {bootstrap} 提供三个显式模式",
            "interface.md bootstrap",
        ),
    )

    # 7. Dual Anchor single-source projection: plugins/.../anchor -> .agents/skills/anchor
    plugin_anchor = root / PLUGIN_ANCHOR_REL
    repo_anchor = root / REPO_ANCHOR_REL
    _require(plugin_anchor.is_dir(), "plugin_anchor_missing")
    for src in sorted(plugin_anchor.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts or src.suffix in {".pyc", ".pyo"}:
            continue
        rel_in_anchor = src.relative_to(plugin_anchor)
        expected[repo_anchor / rel_in_anchor] = src.read_bytes()

    return expected


def sync_versions(
    root: Path = ROOT,
    *,
    core: str | None = None,
    plugin: str | None = None,
    bootstrap: str | None = None,
    scout: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    current = read_current_versions(root)
    desired = {
        "core": core or current["core"],
        "plugin": plugin or current["plugin"],
        "bootstrap": bootstrap or current["bootstrap"],
        "scout": scout or current["scout"],
    }
    expected = compute_expected_files(root, **desired)
    drifted: list[str] = []
    extra_repo_anchor: list[Path] = []

    repo_anchor = root / REPO_ANCHOR_REL
    if repo_anchor.is_dir():
        for path in sorted(repo_anchor.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path not in expected:
                extra_repo_anchor.append(path)
                drifted.append(path.relative_to(root).as_posix())

    for path, content in sorted(expected.items()):
        rel = path.relative_to(root).as_posix()
        if not path.exists() or path.read_bytes() != content:
            drifted.append(rel)
            if apply:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

    if apply:
        for stale in extra_repo_anchor:
            stale.unlink()

    return {
        "status": "ok" if (apply or not drifted) else "drifted",
        "mode": "apply" if apply else "check",
        "versions": desired,
        "changed_or_drifted": sorted(set(drifted)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or synchronize single-source release versions and dual Anchor files.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify all versioned files and dual Anchor copies agree.")
    mode.add_argument("--apply", action="store_true", help="Write synchronized versions and dual Anchor copies.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--core", default=None)
    parser.add_argument("--plugin", default=None)
    parser.add_argument("--bootstrap", default=None)
    parser.add_argument("--scout", default=None)
    args = parser.parse_args(argv)
    try:
        result = sync_versions(
            args.root.resolve(),
            core=args.core,
            plugin=args.plugin,
            bootstrap=args.bootstrap,
            scout=args.scout,
            apply=args.apply,
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0 if result["status"] == "ok" else 1
    except (VersionSyncError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
