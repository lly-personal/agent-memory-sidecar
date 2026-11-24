#!/usr/bin/env python3
"""Unified, idempotent 4-host deployment orchestrator consuming one verified immutable Release.

Delegates strictly to each host's native installer / safe bounded projection without
cross-host cache tampering or L3 write expansion (ADR 0083).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ALL_HOSTS = ("codex", "pi", "claude", "antigravity")
ANTIGRAVITY_SKILLS = ("global-owner-scout", "engineering-contract-review")
RECEIPT_CONTRACT = "agent_memory_multihost_deploy_v1"
REPO_URL = "https://github.com/lly-personal/agent-memory-sidecar"
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class MultiHostDeployError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise MultiHostDeployError(code)


def _is_alias(path: Path) -> bool:
    try:
        st = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _is_trusted_posix_root_alias(path: Path, st: os.stat_result, *, platform: str | None = None) -> bool:
    """Mirror file_security._is_trusted_host_directory_alias (e.g. macOS /var -> /private/var)."""
    effective_platform = os.name if platform is None else platform
    return bool(
        effective_platform == "posix"
        and stat.S_ISLNK(st.st_mode)
        and getattr(st, "st_uid", -1) == 0
        and path.parent == Path(path.anchor)
    )


def _assert_physical_dir(path: Path, *, label: str) -> None:
    _require(path.exists() and path.is_dir() and not _is_alias(path), f"{label}_dir_unsafe")
    for parent in path.parents:
        if parent == Path(parent.anchor) or str(parent) == parent.anchor:
            break
        try:
            st = parent.lstat()
        except OSError as exc:
            raise MultiHostDeployError(f"{label}_ancestor_stat_failed") from exc
        if _is_alias(parent) and not _is_trusted_posix_root_alias(parent, st):
            raise MultiHostDeployError(f"{label}_ancestor_alias_forbidden")


def _tree_digest(root: Path) -> str:
    items: list[tuple[str, str]] = []
    for item in sorted(root.rglob("*")):
        if "__pycache__" in item.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        _require(not _is_alias(item), f"tree_alias_forbidden:{item.name}")
        if item.is_file():
            items.append((item.relative_to(root).as_posix(), hashlib.sha256(item.read_bytes()).hexdigest()))
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _copy_tree_clean(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=False)
    for item in sorted(src.rglob("*")):
        if "__pycache__" in item.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        _require(not _is_alias(item), f"source_alias_forbidden:{item.name}")
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)


def _default_run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _resolve_antigravity_home(codex_home: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser()
    state_file = codex_home / "agent-memory-sidecar" / "instruction-sync-state.json"
    if state_file.is_file() and not _is_alias(state_file):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        enrolled = data.get("antigravity", {}).get("home") or data.get("hosts", {}).get("antigravity", {}).get("home")
        if isinstance(enrolled, str) and enrolled.strip():
            return Path(enrolled)
    return None


def _deploy_codex(
    *,
    portable: Path,
    release_manifest: Path,
    codex_home: Path,
    apply: bool,
    confirm_source_change: bool,
    runner: CommandRunner,
) -> dict[str, Any]:
    ms = portable / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "managed_sources.py"
    sm = portable / "source-manifest.json"
    dry = runner(
        [
            sys.executable, "-B", str(ms), "workstation-reconcile", "--dry-run",
            "--codex-home", str(codex_home), "--source-manifest", str(sm), "--release-manifest", str(release_manifest),
        ]
    )
    if dry.returncode != 0:
        return {"host": "codex", "status": "blocked", "error": (dry.stderr or dry.stdout).strip()[:400]}
    plan = json.loads(dry.stdout)
    plan_status = str(plan.get("status") or "")
    blockers = plan.get("blockers") or []
    if blockers or plan_status not in {"noop", "ready", "confirmation_required"}:
        return {
            "host": "codex",
            "status": "blocked",
            "plan_status": plan_status or "unknown",
            "blockers": blockers,
            "changes": plan.get("changes", []),
            "error": f"codex_reconcile_blocked:{plan_status or 'unknown'}",
        }
    if plan_status == "noop":
        return {"host": "codex", "status": "noop", "changes": [], "session_loading": "unverified", "adoption": "unverified"}
    if not apply:
        return {
            "host": "codex",
            "status": "planned",
            "plan_status": plan_status,
            "changes": plan.get("changes", []),
            "confirmation_required": bool(plan.get("confirmation_required")),
            "plan_hash": plan.get("plan_hash"),
        }
    if plan.get("confirmation_required") and not confirm_source_change:
        return {
            "host": "codex",
            "status": "confirmation_required",
            "changes": plan.get("changes", []),
            "plan_hash": plan.get("plan_hash"),
            "error": "codex_source_identity_change_requires_explicit_confirmation",
        }
    appl = runner(
        [
            sys.executable, "-B", str(ms), "workstation-reconcile", "--apply",
            "--codex-home", str(codex_home), "--source-manifest", str(sm),
            "--release-manifest", str(release_manifest), "--plan-hash", plan["plan_hash"],
        ]
    )
    if appl.returncode != 0:
        return {"host": "codex", "status": "blocked", "error": (appl.stderr or appl.stdout).strip()[:400]}
    rec = json.loads(appl.stdout)
    rec_status = str(rec.get("status") or "")
    if rec_status not in {"applied", "reload_required", "noop", "ready"}:
        return {
            "host": "codex",
            "status": "blocked",
            "plan_status": rec_status or "unknown",
            "blockers": rec.get("blockers", []),
            "error": f"codex_reconcile_apply_blocked:{rec_status or 'unknown'}",
        }
    pack = rec.get("deployment_pack", {})
    return {
        "host": "codex",
        "status": rec_status,
        "core_version": pack.get("host_materialization", {}).get("core", {}).get("version"),
        "plugin_version": pack.get("distribution", {}).get("plugin", {}).get("version"),
        "doctor": pack.get("host_materialization", {}).get("doctor"),
        "session_loading": "unverified",
        "adoption": "unverified",
    }


def _inspect_pi_registration(pi_exe: str, runner: CommandRunner) -> tuple[bool, str | None, Path | None, str | None]:
    """Return (ok, registered_ref, checkout_path, error) parsed from `pi list`."""
    listed = runner([pi_exe, "list"])
    if listed.returncode != 0:
        return False, None, None, f"pi_list_failed:{(listed.stderr or listed.stdout).strip()[:200]}"
    lines = listed.stdout.splitlines()
    registered_ref: str | None = None
    checkout: Path | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if "agent-memory-sidecar" not in stripped.lower():
            continue
        for token in stripped.split():
            cleaned = token.strip("()[]<>\"',")
            if "agent-memory-sidecar" in cleaned.lower() and "@" in cleaned:
                registered_ref = cleaned.rsplit("@", 1)[1]
            candidate = Path(cleaned)
            if candidate.is_dir() and (candidate / ".git").exists():
                checkout = candidate
        if checkout is None and idx + 1 < len(lines):
            next_line = lines[idx + 1].strip().strip("\"'")
            if next_line:
                candidate = Path(next_line)
                if candidate.is_dir() and (candidate / ".git").exists():
                    checkout = candidate
        if registered_ref is not None or checkout is not None:
            break
    return True, registered_ref, checkout, None


def _deploy_pi(
    *,
    tag: str,
    commit: str,
    apply: bool,
    runner: CommandRunner,
    pi_executable: str | None = None,
) -> dict[str, Any]:
    pi_exe = pi_executable or shutil.which("pi") or shutil.which("pi.cmd")
    if not pi_exe:
        return {"host": "pi", "status": "unavailable", "error": "pi_cli_not_found"}

    list_ok, registered_ref, checkout, list_err = _inspect_pi_registration(pi_exe, runner)
    if not list_ok:
        return {"host": "pi", "status": "blocked", "error": list_err}

    disk_checkout = checkout
    if disk_checkout is None:
        standard = Path.home() / ".pi" / "agent" / "git" / "github.com" / "lly-personal" / "agent-memory-sidecar"
        if standard.is_dir() and (standard / ".git").exists():
            disk_checkout = standard

    current_head = None
    dirty = False
    incomplete_marker = False
    preserved_untracked: dict[str, str] = {}
    if disk_checkout is not None:
        marker = disk_checkout.parent / ".agent-memory-sidecar.pi-update-incomplete"
        incomplete_marker = marker.exists()
        st = runner(["git", "-C", str(disk_checkout), "status", "--porcelain", "--untracked-files=all"])
        if st.returncode != 0:
            dirty = True
        else:
            for line in st.stdout.splitlines():
                if not line.strip():
                    continue
                # Preserve harmless Pi-generated root package-lock.json only when no tracked changes exist.
                if line == "?? package-lock.json" and (disk_checkout / "package-lock.json").is_file() and not _is_alias(disk_checkout / "package-lock.json"):
                    preserved_untracked["package-lock.json"] = hashlib.sha256((disk_checkout / "package-lock.json").read_bytes()).hexdigest()
                else:
                    dirty = True
        hd = runner(["git", "-C", str(disk_checkout), "rev-parse", "HEAD"])
        current_head = hd.stdout.strip().casefold() if hd.returncode == 0 else None

    if incomplete_marker or dirty:
        return {
            "host": "pi",
            "status": "blocked",
            "error": "pi_checkout_dirty_or_incomplete_preserved",
            "current_commit": current_head,
            "registered_ref": registered_ref,
            "desired_commit": commit,
        }

    registered_matches = bool(
        registered_ref
        and (registered_ref.casefold() == commit or (registered_ref == tag and current_head == commit))
    )
    if checkout is not None and current_head == commit and registered_matches:
        return {
            "host": "pi",
            "status": "noop",
            "commit": current_head,
            "registered_ref": registered_ref,
            "tag": tag,
            "preserved_untracked": sorted(preserved_untracked),
            "session_loading": "unverified",
            "adoption": "unverified",
        }
    if not apply:
        return {
            "host": "pi",
            "status": "planned",
            "action": "pin_register_only" if current_head == commit else ("fetch_detach_and_pin" if disk_checkout else "pi_install"),
            "current_commit": current_head,
            "registered_ref": registered_ref,
            "desired_commit": commit,
            "preserved_untracked": sorted(preserved_untracked),
            "tag": tag,
        }

    # Safe update path per README: fetch exact tag -> verify commit -> check no untracked collision -> detach -> pi install commit pin
    if disk_checkout is not None and current_head != commit:
        fetch = runner(["git", "-C", str(disk_checkout), "fetch", "--no-tags", "origin", f"refs/tags/{tag}"])
        if fetch.returncode != 0:
            return {"host": "pi", "status": "blocked", "error": f"pi_git_fetch_failed:{fetch.stderr.strip()[:200]}"}
        fh = runner(["git", "-C", str(disk_checkout), "rev-parse", "FETCH_HEAD^{commit}"])
        if fh.returncode != 0 or fh.stdout.strip().casefold() != commit:
            return {"host": "pi", "status": "blocked", "error": "pi_fetch_commit_mismatch"}
        for rel in preserved_untracked:
            col = runner(["git", "-C", str(disk_checkout), "ls-tree", commit, "--", rel])
            if col.returncode != 0 or col.stdout.strip():
                return {"host": "pi", "status": "blocked", "error": f"pi_untracked_collision:{rel}"}
        sw = runner(["git", "-C", str(disk_checkout), "switch", "--detach", commit])
        if sw.returncode != 0:
            return {"host": "pi", "status": "blocked", "error": f"pi_git_switch_failed:{sw.stderr.strip()[:200]}"}

    pin_spec = f"git:github.com/lly-personal/agent-memory-sidecar@{commit}"
    inst = runner([pi_exe, "install", pin_spec])
    if inst.returncode != 0:
        return {"host": "pi", "status": "blocked", "error": f"pi_install_failed:{(inst.stderr or inst.stdout).strip()[:300]}"}

    after_ok, reg_after, checkout_after, after_err = _inspect_pi_registration(pi_exe, runner)
    if not after_ok:
        return {"host": "pi", "status": "blocked", "error": after_err}
    effective_checkout = checkout_after or disk_checkout
    observed_head = None
    if effective_checkout is not None:
        hd = runner(["git", "-C", str(effective_checkout), "rev-parse", "HEAD"])
        observed_head = hd.stdout.strip().casefold() if hd.returncode == 0 else None
        for rel, expected_sha in preserved_untracked.items():
            p = effective_checkout / rel
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != expected_sha:
                return {"host": "pi", "status": "blocked", "error": f"pi_preserved_file_changed:{rel}"}
    if observed_head != commit or not reg_after or reg_after.casefold() != commit:
        return {
            "host": "pi",
            "status": "blocked",
            "error": "pi_readback_mismatch",
            "observed_commit": observed_head,
            "registered_ref": reg_after,
            "desired_commit": commit,
        }
    return {
        "host": "pi",
        "status": "applied",
        "tag": tag,
        "commit": observed_head,
        "registered_ref": reg_after,
        "pin_spec": pin_spec,
        "preserved_untracked": sorted(preserved_untracked),
        "session_loading": "unverified",
        "adoption": "unverified",
    }


def _deploy_claude(
    *,
    tag: str,
    plugin_version: str,
    apply: bool,
    runner: CommandRunner,
    claude_executable: str | None = None,
    claude_home: Path | None = None,
) -> dict[str, Any]:
    claude_exe = claude_executable or shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_exe:
        return {"host": "claude", "status": "unavailable", "error": "claude_cli_not_found"}

    active_claude_home = (claude_home or (Path.home() / ".claude")).expanduser()
    known_mk_path = active_claude_home / "plugins" / "known_marketplaces.json"
    desired_git_url = f"{REPO_URL}.git"

    def _read_marketplace_source() -> dict[str, Any] | None:
        if not known_mk_path.is_file() or _is_alias(known_mk_path):
            return None
        try:
            data = json.loads(known_mk_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        entry = data.get("agent-memory")
        if isinstance(entry, dict) and isinstance(entry.get("source"), dict):
            return entry["source"]
        return None

    def _marketplace_restore_spec(src: dict[str, Any] | None) -> str | None:
        if not isinstance(src, dict):
            return None
        if src.get("source") == "git" and isinstance(src.get("url"), str):
            ref = src.get("ref")
            return f"{src['url']}#{ref}" if isinstance(ref, str) and ref else src["url"]
        if src.get("source") == "github" and isinstance(src.get("repo"), str):
            return src["repo"]
        return None

    def _read_installed_entry() -> tuple[bool, dict[str, Any] | None, str | None]:
        listed = runner([claude_exe, "plugin", "list", "--json"])
        if listed.returncode != 0:
            return False, None, f"claude_plugin_list_failed:{(listed.stderr or listed.stdout).strip()[:200]}"
        try:
            items = json.loads(listed.stdout)
        except json.JSONDecodeError:
            return False, None, "claude_plugin_list_invalid_json"
        entries = items if isinstance(items, list) else items.get("plugins", [])
        if not isinstance(entries, list):
            return False, None, "claude_plugin_list_invalid_shape"
        for item in entries:
            if not isinstance(item, dict):
                continue
            if item.get("id") == "agent-memory-sidecar@agent-memory" and item.get("scope", "user") == "user":
                return True, item, None
        return True, None, None

    list_ok, entry_before, list_err = _read_installed_entry()
    if not list_ok:
        return {"host": "claude", "status": "blocked", "error": list_err}

    mk_before = _read_marketplace_source()
    observed_version = str(entry_before.get("version")) if isinstance(entry_before, dict) and entry_before.get("version") else None
    enabled_before = entry_before.get("enabled") if isinstance(entry_before, dict) else None
    if entry_before is not None and enabled_before is False:
        return {
            "host": "claude",
            "status": "blocked",
            "error": "claude_plugin_explicitly_disabled",
            "current_plugin_version": observed_version,
        }

    mk_matches = bool(
        isinstance(mk_before, dict)
        and mk_before.get("source") == "git"
        and str(mk_before.get("url") or "").casefold() == desired_git_url.casefold()
        and mk_before.get("ref") == tag
    )
    if observed_version == plugin_version and enabled_before is True and mk_matches:
        return {
            "host": "claude",
            "status": "noop",
            "plugin_version": observed_version,
            "tag": tag,
            "session_loading": "unverified",
            "adoption": "unverified",
        }
    if not apply:
        return {
            "host": "claude",
            "status": "planned",
            "current_plugin_version": observed_version,
            "current_marketplace_ref": mk_before.get("ref") if isinstance(mk_before, dict) else None,
            "desired_plugin_version": plugin_version,
            "tag": tag,
        }

    prior_restore_spec = _marketplace_restore_spec(mk_before)

    def _rollback_marketplace() -> dict[str, Any]:
        if not prior_restore_spec:
            return {"rollback_attempted": False, "rollback_succeeded": None}
        runner([claude_exe, "plugin", "marketplace", "remove", "agent-memory"])
        rb = runner([claude_exe, "plugin", "marketplace", "add", prior_restore_spec])
        return {"rollback_attempted": True, "rollback_succeeded": rb.returncode == 0, "rollback_spec": prior_restore_spec}

    # Native Claude CLI workflow: remove & re-add tagged marketplace ref (with rollback if add/install fails), then install plugin
    if mk_before is not None:
        runner([claude_exe, "plugin", "marketplace", "remove", "agent-memory"])
    add = runner([claude_exe, "plugin", "marketplace", "add", f"{desired_git_url}#{tag}"])
    if add.returncode != 0:
        rb_info = _rollback_marketplace()
        return {
            "host": "claude",
            "status": "blocked",
            "error": f"claude_marketplace_add_failed:{(add.stderr or add.stdout).strip()[:300]}",
            **rb_info,
        }
    inst = runner([claude_exe, "plugin", "install", "agent-memory-sidecar@agent-memory", "--scope", "user"])
    if inst.returncode != 0:
        rb_info = _rollback_marketplace()
        return {
            "host": "claude",
            "status": "blocked",
            "error": f"claude_plugin_install_failed:{(inst.stderr or inst.stdout).strip()[:300]}",
            **rb_info,
        }

    after_ok, entry_after, after_err = _read_installed_entry()
    mk_after = _read_marketplace_source()
    observed_after = str(entry_after.get("version")) if isinstance(entry_after, dict) and entry_after.get("version") else None
    enabled_after = entry_after.get("enabled") if isinstance(entry_after, dict) else None
    mk_after_ok = (
        mk_after is None
        or (
            mk_after.get("source") == "git"
            and str(mk_after.get("url") or "").casefold() == desired_git_url.casefold()
            and mk_after.get("ref") == tag
        )
    )
    if not after_ok or observed_after != plugin_version or enabled_after is not True or not mk_after_ok:
        return {
            "host": "claude",
            "status": "blocked",
            "error": after_err or "claude_readback_mismatch",
            "observed_plugin_version": observed_after,
            "observed_enabled": enabled_after,
            "observed_marketplace_ref": mk_after.get("ref") if isinstance(mk_after, dict) else None,
            "desired_plugin_version": plugin_version,
        }
    return {
        "host": "claude",
        "status": "applied",
        "tag": tag,
        "plugin_version": observed_after,
        "session_loading": "unverified",
        "adoption": "unverified",
    }


ANTIGRAVITY_MANAGED_SIGNATURES: dict[str, tuple[str, ...]] = {
    "global-owner-scout": ("SKILL.md", "scripts/scout.py", "scripts/validate_output.py"),
    "engineering-contract-review": (
        "SKILL.md",
        "references/design.md",
        "references/verify.md",
        "references/recover.md",
        "references/performance.md",
    ),
}


def _is_managed_antigravity_skill(name: str, dst: Path) -> bool:
    """Confirm an existing Antigravity skill directory matches our shipped layout before replacing it."""
    required_files = ANTIGRAVITY_MANAGED_SIGNATURES.get(name)
    if not required_files:
        return False
    for rel in required_files:
        p = dst / rel
        if not p.is_file() or _is_alias(p):
            return False
    try:
        head = (dst / "SKILL.md").read_text(encoding="utf-8")[:512]
    except OSError:
        return False
    return f"name: {name}" in head


def _deploy_antigravity(
    *,
    portable: Path,
    antigravity_home: Path | None,
    apply: bool,
    allow_replace_unmanaged: bool = False,
) -> dict[str, Any]:
    if antigravity_home is None:
        return {
            "host": "antigravity",
            "status": "blocked",
            "error": "antigravity_home_not_provided_or_enrolled",
        }
    config_dir = antigravity_home / "config"
    skills_root = config_dir / "skills"
    sources = {
        "global-owner-scout": portable / ".agents" / "skills" / "global-owner-scout",
        "engineering-contract-review": portable / "plugins" / "agent-memory-sidecar" / "skills" / "engineering-contract-review",
    }
    for name, src in sources.items():
        _require(src.is_dir() and not _is_alias(src), f"antigravity_portable_source_missing:{name}")

    # Validate every existing component down to skills_root, including intermediate `config` even when `skills` is absent.
    _assert_physical_dir(antigravity_home, label="antigravity_home")
    if config_dir.exists() or _is_alias(config_dir):
        _assert_physical_dir(config_dir, label="antigravity_config_dir")
    if skills_root.exists() or _is_alias(skills_root):
        _assert_physical_dir(skills_root, label="antigravity_skills_root")

    plan_items: dict[str, dict[str, Any]] = {}
    any_change = False
    for name, src in sources.items():
        desired_sha = _tree_digest(src)
        dst = skills_root / name
        if dst.exists() or _is_alias(dst):
            _require(dst.is_dir() and not _is_alias(dst), f"antigravity_target_unsafe:{name}")
            current_sha = _tree_digest(dst)
            if current_sha != desired_sha and not allow_replace_unmanaged:
                _require(_is_managed_antigravity_skill(name, dst), f"antigravity_unmanaged_skill_conflict:{name}")
        else:
            current_sha = None
        action = "noop" if current_sha == desired_sha else ("install" if current_sha is None else "replace")
        any_change = any_change or (action != "noop")
        plan_items[name] = {
            "action": action,
            "current_sha256": current_sha,
            "desired_sha256": desired_sha,
        }

    if not any_change:
        return {
            "host": "antigravity",
            "status": "noop",
            "skills": plan_items,
            "session_loading": "unverified",
            "adoption": "unverified",
        }
    if not apply:
        return {"host": "antigravity", "status": "planned", "skills": plan_items}

    skills_root.mkdir(parents=True, exist_ok=True)
    _assert_physical_dir(skills_root, label="antigravity_skills_root")
    backups: list[tuple[Path, Path | None]] = []
    staged_dirs: list[Path] = []
    try:
        for name, src in sources.items():
            if plan_items[name]["action"] == "noop":
                continue
            dst = skills_root / name
            stage = Path(tempfile.mkdtemp(prefix=f".stage-{name}-", dir=str(skills_root)))
            shutil.rmtree(stage)
            staged_dirs.append(stage)
            _copy_tree_clean(src, stage)
            _require(_tree_digest(stage) == plan_items[name]["desired_sha256"], f"antigravity_stage_hash_mismatch:{name}")
            if dst.exists():
                backup = Path(tempfile.mkdtemp(prefix=f".backup-{name}-", dir=str(skills_root)))
                shutil.rmtree(backup)
                os.replace(dst, backup)
                backups.append((dst, backup))
            else:
                backups.append((dst, None))
            os.replace(stage, dst)
            staged_dirs.remove(stage)

        # Exact post-write readback
        readback: dict[str, str] = {}
        for name in ANTIGRAVITY_SKILLS:
            dst = skills_root / name
            _require(dst.is_dir() and not _is_alias(dst), f"antigravity_readback_missing:{name}")
            actual = _tree_digest(dst)
            _require(actual == plan_items[name]["desired_sha256"], f"antigravity_readback_drift:{name}")
            readback[name] = actual
    except Exception:
        for stage in staged_dirs:
            if stage.parent == skills_root and stage.name.startswith(".stage-") and stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
        for dst, backup in reversed(backups):
            if dst.parent == skills_root and dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            if backup is not None and backup.parent == skills_root and backup.name.startswith(".backup-") and backup.exists():
                os.replace(backup, dst)
        raise
    else:
        for _, backup in backups:
            if backup is not None and backup.parent == skills_root and backup.name.startswith(".backup-") and backup.exists():
                shutil.rmtree(backup, ignore_errors=False)

    return {
        "host": "antigravity",
        "status": "applied",
        "skills": {name: {"sha256": sha} for name, sha in readback.items()},
        "session_loading": "unverified",
        "adoption": "unverified",
    }


def deploy_multihost(
    *,
    root: Path = ROOT,
    version: str | None = None,
    hosts: tuple[str, ...] = ALL_HOSTS,
    codex_home: Path | None = None,
    antigravity_home: Path | None = None,
    claude_home: Path | None = None,
    apply: bool = False,
    confirm_source_change: bool = False,
    allow_replace_unmanaged: bool = False,
    runner: CommandRunner = _default_run,
    resolved_dir: Path | None = None,
) -> dict[str, Any]:
    for host in hosts:
        _require(host in ALL_HOSTS, f"unsupported_host:{host}")

    active_codex_home = (codex_home or (Path.home() / ".codex")).expanduser()
    resolved_ag_home = _resolve_antigravity_home(active_codex_home, antigravity_home)

    owns_temp = resolved_dir is None
    stage_parent: Path | None = None
    if resolved_dir is None:
        temp_parent = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" if os.name == "nt" else Path(tempfile.gettempdir())
        temp_parent.mkdir(parents=True, exist_ok=True)
        stage_parent = Path(tempfile.mkdtemp(prefix="ams-multihost-", dir=str(temp_parent)))
        stage_dir = stage_parent / "resolved"
    else:
        stage_dir = resolved_dir

    receipt: dict[str, Any] | None = None
    try:
        if owns_temp:
            resolver = root / "plugins" / "agent-memory-sidecar" / "skills" / "agent-memory-bootstrap-anchor" / "scripts" / "resolve_release.py"
            cmd = [sys.executable, "-B", str(resolver), "--output", str(stage_dir)]
            if version:
                cmd.extend(["--version", version])
            res = runner(cmd)
            _require(res.returncode == 0, f"release_resolution_failed:{(res.stderr or res.stdout).strip()[:300]}")
            resolved = json.loads(res.stdout)
        else:
            resolved = json.loads((stage_dir / "resolution.json").read_text(encoding="utf-8"))

        _require(resolved.get("status") == "verified", "release_resolution_unverified")
        tag = str(resolved["tag"])
        commit = str(resolved["commit"]).casefold()
        portable = stage_dir / str(resolved["portable_root"])
        release_manifest_path = stage_dir / "release-manifest.json"
        release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        plugin_version = str(release_manifest["versions"]["plugin"])

        results: dict[str, Any] = {}
        for host in hosts:
            try:
                if host == "codex":
                    results[host] = _deploy_codex(
                        portable=portable,
                        release_manifest=release_manifest_path,
                        codex_home=active_codex_home,
                        apply=apply,
                        confirm_source_change=confirm_source_change,
                        runner=runner,
                    )
                elif host == "pi":
                    results[host] = _deploy_pi(tag=tag, commit=commit, apply=apply, runner=runner)
                elif host == "claude":
                    results[host] = _deploy_claude(
                        tag=tag,
                        plugin_version=plugin_version,
                        apply=apply,
                        runner=runner,
                        claude_home=claude_home,
                    )
                elif host == "antigravity":
                    results[host] = _deploy_antigravity(
                        portable=portable,
                        antigravity_home=resolved_ag_home,
                        apply=apply,
                        allow_replace_unmanaged=allow_replace_unmanaged,
                    )
            except MultiHostDeployError as exc:
                results[host] = {"host": host, "status": "blocked", "error": str(exc)}

        ok_states = {"planned", "noop", "applied", "reload_required"}
        overall = "ok" if all(item.get("status") in ok_states for item in results.values()) else "partial_or_blocked"
        receipt = {
            "contract_version": RECEIPT_CONTRACT,
            "mode": "apply" if apply else "dry_run",
            "status": overall,
            "release": {
                "tag": tag,
                "commit": commit,
                "versions": release_manifest.get("versions", {}),
            },
            "hosts": results,
            "limitations": [
                "Installation and file/CLI readback do not prove live session reload or natural model adoption.",
                "L3 rule approval and writes remain Codex-only (ADR 0083); Pi, Claude Code, and Antigravity remain L1/L2 only.",
            ],
        }
        return receipt
    finally:
        if owns_temp and stage_parent is not None and stage_parent.exists():
            try:
                shutil.rmtree(stage_parent, ignore_errors=False)
                if stage_parent.exists():
                    raise OSError("multihost_temp_cleanup_incomplete")
            except OSError as exc:
                if receipt is not None:
                    receipt["cleanup_error"] = f"multihost_temp_cleanup_failed:{exc}"
                    receipt["status"] = "partial_or_blocked"
                else:
                    raise MultiHostDeployError("multihost_temp_cleanup_failed") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve one immutable Release and preview/apply deployment across Codex, Pi, Claude Code, and Antigravity."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--version", default=None, help="Release tag (e.g. v0.7.6); defaults to latest stable.")
    parser.add_argument("--hosts", default=",".join(ALL_HOSTS), help="Comma-separated subset of codex,pi,claude,antigravity.")
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--antigravity-home", type=Path, default=None)
    parser.add_argument("--confirm-source-change", action="store_true")
    parser.add_argument("--allow-replace-unmanaged", action="store_true")
    args = parser.parse_args(argv)
    hosts = tuple(item.strip().lower() for item in args.hosts.split(",") if item.strip())
    try:
        receipt = deploy_multihost(
            root=ROOT,
            version=args.version,
            hosts=hosts,
            codex_home=args.codex_home,
            antigravity_home=args.antigravity_home,
            apply=args.apply,
            confirm_source_change=args.confirm_source_change,
            allow_replace_unmanaged=args.allow_replace_unmanaged,
        )
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
        return 0 if receipt["status"] == "ok" else 1
    except (MultiHostDeployError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"contract_version": RECEIPT_CONTRACT, "status": "error", "error": str(exc)}, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
