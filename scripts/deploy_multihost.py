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
    if not apply:
        return {
            "host": "codex",
            "status": "planned",
            "plan_status": plan.get("status"),
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
    if plan.get("status") == "noop":
        return {"host": "codex", "status": "noop", "changes": [], "session_loading": "unverified", "adoption": "unverified"}
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
    pack = rec.get("deployment_pack", {})
    return {
        "host": "codex",
        "status": rec.get("status", "applied"),
        "core_version": pack.get("host_materialization", {}).get("core", {}).get("version"),
        "plugin_version": pack.get("distribution", {}).get("plugin", {}).get("version"),
        "doctor": pack.get("host_materialization", {}).get("doctor"),
        "session_loading": "unverified",
        "adoption": "unverified",
    }


def _find_pi_checkout(pi_exe: str, runner: CommandRunner) -> Path | None:
    listed = runner([pi_exe, "list"])
    if listed.returncode != 0:
        return None
    for line in listed.stdout.splitlines():
        if "agent-memory-sidecar" not in line.lower():
            continue
        for token in line.split():
            candidate = Path(token.strip("()[]<>\"',"))
            if candidate.is_dir() and (candidate / ".git").exists():
                return candidate
    # Check standard Pi npm/git package location
    standard = Path.home() / ".pi" / "agent" / "git" / "github.com" / "lly-personal" / "agent-memory-sidecar"
    if standard.is_dir() and (standard / ".git").exists():
        return standard
    return None


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

    checkout = _find_pi_checkout(pi_exe, runner)
    current_head = None
    dirty = False
    incomplete_marker = False
    preserved_untracked: dict[str, str] = {}
    if checkout is not None:
        marker = checkout.parent / ".agent-memory-sidecar.pi-update-incomplete"
        incomplete_marker = marker.exists()
        st = runner(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"])
        if st.returncode != 0:
            dirty = True
        else:
            for line in st.stdout.splitlines():
                if not line.strip():
                    continue
                # Preserve harmless Pi-generated root package-lock.json only when no tracked changes exist.
                if line == "?? package-lock.json" and (checkout / "package-lock.json").is_file() and not _is_alias(checkout / "package-lock.json"):
                    preserved_untracked["package-lock.json"] = hashlib.sha256((checkout / "package-lock.json").read_bytes()).hexdigest()
                else:
                    dirty = True
        hd = runner(["git", "-C", str(checkout), "rev-parse", "HEAD"])
        current_head = hd.stdout.strip().casefold() if hd.returncode == 0 else None

    if incomplete_marker or dirty:
        return {
            "host": "pi",
            "status": "blocked",
            "error": "pi_checkout_dirty_or_incomplete_preserved",
            "current_commit": current_head,
            "desired_commit": commit,
        }
    if current_head == commit:
        return {
            "host": "pi",
            "status": "noop",
            "commit": current_head,
            "tag": tag,
            "preserved_untracked": sorted(preserved_untracked),
            "session_loading": "unverified",
            "adoption": "unverified",
        }
    if not apply:
        return {
            "host": "pi",
            "status": "planned",
            "action": "fetch_detach_and_pin" if checkout else "pi_install",
            "current_commit": current_head,
            "desired_commit": commit,
            "preserved_untracked": sorted(preserved_untracked),
            "tag": tag,
        }

    # Safe update path per README: fetch exact tag -> verify commit -> check no untracked collision -> detach -> pi install commit pin
    if checkout is not None:
        fetch = runner(["git", "-C", str(checkout), "fetch", "--no-tags", "origin", f"refs/tags/{tag}"])
        if fetch.returncode != 0:
            return {"host": "pi", "status": "blocked", "error": f"pi_git_fetch_failed:{fetch.stderr.strip()[:200]}"}
        fh = runner(["git", "-C", str(checkout), "rev-parse", "FETCH_HEAD^{commit}"])
        if fh.returncode != 0 or fh.stdout.strip().casefold() != commit:
            return {"host": "pi", "status": "blocked", "error": "pi_fetch_commit_mismatch"}
        for rel in preserved_untracked:
            col = runner(["git", "-C", str(checkout), "ls-tree", commit, "--", rel])
            if col.returncode != 0 or col.stdout.strip():
                return {"host": "pi", "status": "blocked", "error": f"pi_untracked_collision:{rel}"}
        sw = runner(["git", "-C", str(checkout), "switch", "--detach", commit])
        if sw.returncode != 0:
            return {"host": "pi", "status": "blocked", "error": f"pi_git_switch_failed:{sw.stderr.strip()[:200]}"}

    pin_spec = f"git:github.com/lly-personal/agent-memory-sidecar@{commit}"
    inst = runner([pi_exe, "install", pin_spec])
    if inst.returncode != 0:
        return {"host": "pi", "status": "blocked", "error": f"pi_install_failed:{(inst.stderr or inst.stdout).strip()[:300]}"}

    checkout_after = _find_pi_checkout(pi_exe, runner) or checkout
    observed_head = None
    if checkout_after is not None:
        hd = runner(["git", "-C", str(checkout_after), "rev-parse", "HEAD"])
        observed_head = hd.stdout.strip().casefold() if hd.returncode == 0 else None
        for rel, expected_sha in preserved_untracked.items():
            p = checkout_after / rel
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != expected_sha:
                return {"host": "pi", "status": "blocked", "error": f"pi_preserved_file_changed:{rel}"}
    if observed_head != commit:
        return {
            "host": "pi",
            "status": "blocked",
            "error": "pi_readback_commit_mismatch",
            "observed_commit": observed_head,
            "desired_commit": commit,
        }
    return {
        "host": "pi",
        "status": "applied",
        "tag": tag,
        "commit": observed_head,
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
) -> dict[str, Any]:
    claude_exe = claude_executable or shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_exe:
        return {"host": "claude", "status": "unavailable", "error": "claude_cli_not_found"}

    def _read_installed_version() -> str | None:
        listed = runner([claude_exe, "plugin", "list", "--json"])
        if listed.returncode == 0:
            try:
                items = json.loads(listed.stdout)
                entries = items if isinstance(items, list) else items.get("plugins", [])
                for item in entries:
                    if isinstance(item, dict) and str(item.get("id", item.get("name", ""))).startswith("agent-memory-sidecar"):
                        return str(item.get("version")) if item.get("version") else None
            except json.JSONDecodeError:
                pass
        installed_json = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
        if installed_json.is_file() and not _is_alias(installed_json):
            try:
                data = json.loads(installed_json.read_text(encoding="utf-8"))
                entry = data.get("plugins", {}).get("agent-memory-sidecar@agent-memory", [])
                if isinstance(entry, list) and entry and isinstance(entry[0], dict):
                    return str(entry[0].get("version")) if entry[0].get("version") else None
            except (OSError, json.JSONDecodeError):
                pass
        return None

    observed_before = _read_installed_version()
    if observed_before == plugin_version:
        return {
            "host": "claude",
            "status": "noop",
            "plugin_version": observed_before,
            "tag": tag,
            "session_loading": "unverified",
            "adoption": "unverified",
        }
    if not apply:
        return {
            "host": "claude",
            "status": "planned",
            "current_plugin_version": observed_before,
            "desired_plugin_version": plugin_version,
            "tag": tag,
        }

    # Native Claude CLI workflow: remove & re-add tagged marketplace ref (no manual JSON mutation), then install plugin
    runner([claude_exe, "plugin", "marketplace", "remove", "agent-memory"])
    add = runner([claude_exe, "plugin", "marketplace", "add", f"{REPO_URL}.git#{tag}"])
    if add.returncode != 0:
        return {"host": "claude", "status": "blocked", "error": f"claude_marketplace_add_failed:{(add.stderr or add.stdout).strip()[:300]}"}
    inst = runner([claude_exe, "plugin", "install", "agent-memory-sidecar@agent-memory", "--scope", "user"])
    if inst.returncode != 0:
        return {"host": "claude", "status": "blocked", "error": f"claude_plugin_install_failed:{(inst.stderr or inst.stdout).strip()[:300]}"}

    observed_after = _read_installed_version()
    if observed_after != plugin_version:
        return {
            "host": "claude",
            "status": "blocked",
            "error": "claude_readback_version_mismatch",
            "observed_plugin_version": observed_after,
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


def _deploy_antigravity(
    *,
    portable: Path,
    antigravity_home: Path | None,
    apply: bool,
) -> dict[str, Any]:
    if antigravity_home is None:
        return {
            "host": "antigravity",
            "status": "blocked",
            "error": "antigravity_home_not_provided_or_enrolled",
        }
    skills_root = antigravity_home / "config" / "skills"
    sources = {
        "global-owner-scout": portable / ".agents" / "skills" / "global-owner-scout",
        "engineering-contract-review": portable / "plugins" / "agent-memory-sidecar" / "skills" / "engineering-contract-review",
    }
    for name, src in sources.items():
        _require(src.is_dir() and not _is_alias(src), f"antigravity_portable_source_missing:{name}")

    _assert_physical_dir(antigravity_home, label="antigravity_home")
    if skills_root.exists():
        _assert_physical_dir(skills_root, label="antigravity_skills_root")

    plan_items: dict[str, dict[str, Any]] = {}
    any_change = False
    for name, src in sources.items():
        desired_sha = _tree_digest(src)
        dst = skills_root / name
        if dst.exists():
            _require(dst.is_dir() and not _is_alias(dst), f"antigravity_target_unsafe:{name}")
            current_sha = _tree_digest(dst)
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
    apply: bool = False,
    confirm_source_change: bool = False,
    runner: CommandRunner = _default_run,
    resolved_dir: Path | None = None,
) -> dict[str, Any]:
    for host in hosts:
        _require(host in ALL_HOSTS, f"unsupported_host:{host}")

    active_codex_home = (codex_home or (Path.home() / ".codex")).expanduser()
    resolved_ag_home = _resolve_antigravity_home(active_codex_home, antigravity_home)

    owns_temp = resolved_dir is None
    if resolved_dir is None:
        temp_parent = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" if os.name == "nt" else Path(tempfile.gettempdir())
        temp_parent.mkdir(parents=True, exist_ok=True)
        stage_dir = temp_parent / f"ams-multihost-{os.getpid()}"
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
    else:
        stage_dir = resolved_dir

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
                    results[host] = _deploy_claude(tag=tag, plugin_version=plugin_version, apply=apply, runner=runner)
                elif host == "antigravity":
                    results[host] = _deploy_antigravity(portable=portable, antigravity_home=resolved_ag_home, apply=apply)
            except MultiHostDeployError as exc:
                results[host] = {"host": host, "status": "blocked", "error": str(exc)}

        ok_states = {"planned", "noop", "applied"}
        overall = "ok" if all(item.get("status") in ok_states for item in results.values()) else "partial_or_blocked"
        return {
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
    finally:
        if owns_temp and stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=False)
            _require(not stage_dir.exists(), "multihost_temp_cleanup_failed")


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
