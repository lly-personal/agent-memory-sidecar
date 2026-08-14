#!/usr/bin/env python3
"""Atomic managed-source sync and deployment-pack contracts for Bootstrap 1.6."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BOOTSTRAP_VERSION = "1.6.0"
SCOUT_VERSION = "5.5.0"
PACK_VERSION = "agent_memory_workstation_deployment_pack_v1"
SOURCE_MANIFEST_VERSION = "agent_memory_source_manifest_v1"
SOURCE_MANIFEST_FIELDS = {
    "contract_version", "distribution", "sidecar", "canonical_owner",
}
SOURCE_FIELDS = {"remote", "ref", "commit"}
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
PACK_FIELDS = {
    "contract_version", "status", "display_locale", "bootstrap_version", "generated_at",
    "portable_distribution", "source_sync", "host_materialization", "project_activation",
    "limitations", "pack_hash",
}
DISTRIBUTION_FIELDS = {"repo_anchor", "plugin", "marketplace"}
SOURCE_SYNC_FIELDS = {"sidecar", "canonical_owner"}
SOURCE_RECEIPT_FIELDS = {"status", "ref", "commit"}
MATERIALIZATION_FIELDS = {
    "core_setup", "global_binding", "doctor", "bootstrap_skill", "scout_skill",
    "bootstrap_skill_version", "scout_skill_version",
}
ACTIVATION_FIELDS = {"interactive_entry", "scheduled"}
MARKETPLACE_FIELDS = {"name", "interface", "plugins"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|opt|mnt)/)", re.IGNORECASE)
RAW_URL = re.compile(r"(?:https?|ssh|git)://|git@[^\s:]+:", re.IGNORECASE)


class BootstrapError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    remote: str
    ref: str = "main"
    expected_commit: str | None = None


def validate_source_manifest(value: Any) -> tuple[SourceSpec, ...]:
    exact(value, SOURCE_MANIFEST_FIELDS, "$")
    require(
        value["contract_version"] == SOURCE_MANIFEST_VERSION,
        "source_manifest_contract_invalid",
    )
    distribution = value["distribution"]
    require(distribution in {"development", "release"}, "source_manifest_distribution_invalid")
    specs: list[SourceSpec] = []
    for name in ("sidecar", "canonical_owner"):
        source = value[name]
        if source is None:
            require(name == "canonical_owner", "source_manifest_sidecar_required")
            continue
        exact(source, SOURCE_FIELDS, f"$.{name}")
        remote = str(source["remote"]).strip()
        ref = str(source["ref"]).strip()
        commit_value = source["commit"]
        commit = str(commit_value).strip().casefold() if commit_value is not None else None
        require(
            remote and not remote.startswith("-") and not re.search(r"[\r\n]", remote),
            f"source_manifest_{name}_remote_invalid",
        )
        normalize_remote(remote)
        require(
            SAFE_REF.fullmatch(ref) is not None
            and ".." not in ref
            and "//" not in ref
            and "@{" not in ref
            and not ref.endswith(("/", ".", ".lock")),
            f"source_manifest_{name}_ref_invalid",
        )
        require(commit is None or SHA40.fullmatch(commit) is not None, f"source_manifest_{name}_commit_invalid")
        if distribution == "release":
            require(commit is not None, f"source_manifest_{name}_commit_required")
        specs.append(SourceSpec(name, remote, ref, commit))
    return tuple(specs)


def load_source_manifest(path: Path | str) -> tuple[SourceSpec, ...]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("source_manifest_unreadable") from exc
    return validate_source_manifest(value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BootstrapError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(value: dict[str, Any], field: str) -> str:
    copied = dict(value)
    copied.pop(field, None)
    return hashlib.sha256(canonical(copied)).hexdigest()


def exact(value: Any, fields: set[str], path: str) -> None:
    require(isinstance(value, dict), f"{path} must be an object")
    require(set(value) == fields, f"{path} fields invalid")


def safe_text(value: Any, path: str, limit: int = 400) -> None:
    require(isinstance(value, str) and value.strip(), f"{path} must be non-empty text")
    require(len(value) <= limit, f"{path} too long")
    require(ABSOLUTE_PATH.search(value) is None, f"{path} leaks an absolute path")
    require(RAW_URL.search(value) is None, f"{path} leaks a source URL")


def normalize_remote(remote: str) -> str:
    remote = remote.strip()
    require(remote and not re.search(r"[\r\n]", remote), "source remote invalid")
    if re.match(r"^[A-Za-z]:[\\/]", remote) or Path(remote).is_absolute():
        normalized = str(Path(remote).resolve()).replace("\\", "/")
    elif re.match(r"^[^@\s]+@[^:\s]+:.+$", remote):
        require("?" not in remote and "#" not in remote, "source remote contains query or fragment")
        host_path = remote.split("@", 1)[1]
        host, path = host_path.split(":", 1)
        normalized = f"{host.lower()}/{path.strip('/')}"
    else:
        parsed = urlsplit(remote)
        require(parsed.scheme in {"https", "ssh", "file"} or parsed.scheme == "", "source remote scheme invalid")
        require(parsed.username is None and parsed.password is None, "source remote contains credentials")
        require(not parsed.query and not parsed.fragment, "source remote contains query or fragment")
        if parsed.scheme:
            normalized = urlunsplit((parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.path.rstrip("/"), "", ""))
        else:
            normalized = str(Path(remote).resolve()).replace("\\", "/")
    return normalized[:-4] if normalized.lower().endswith(".git") else normalized


def run_git(args: list[str], *, cwd: Path | None = None) -> str:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError("source_git_timeout") from exc
    if result.returncode:
        raise BootstrapError("source_git_failed")
    return result.stdout.strip()


def ensure_managed_child(root: Path, child: Path) -> None:
    root = root.resolve()
    resolved = child.resolve()
    require(resolved.parent == root, "managed source target escaped its root")


def safe_remove(root: Path, path: Path) -> None:
    if not path.exists():
        return
    ensure_managed_child(root, path)
    require(path.name.startswith("."), "only staged managed paths may be removed")
    if path.is_dir() and not path.is_symlink():
        def remove_readonly(function: Any, target: str, _: Any) -> None:
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(path, onerror=remove_readonly)
    else:
        path.unlink()


def inspect_checkout(path: Path, spec: SourceSpec) -> str:
    require(path.is_dir() and not path.is_symlink(), "managed_source_invalid")
    require((path / ".git").exists(), "managed_source_not_git")
    actual_remote = run_git(["remote", "get-url", "origin"], cwd=path)
    require(normalize_remote(actual_remote) == normalize_remote(spec.remote), "managed_source_identity_mismatch")
    require(run_git(["status", "--porcelain"], cwd=path) == "", "managed_source_dirty")
    commit = run_git(["rev-parse", "HEAD"], cwd=path).lower()
    require(SHA40.fullmatch(commit) is not None, "managed_source_commit_invalid")
    require(
        spec.expected_commit is None or commit == spec.expected_commit,
        "managed_source_commit_mismatch",
    )
    return commit


def sync_sources(codex_home: Path, specs: tuple[SourceSpec, ...]) -> dict[str, Any]:
    root = codex_home.resolve() / "agent-memory" / "sources"
    root.mkdir(parents=True, exist_ok=True)
    prepared: dict[str, tuple[SourceSpec, Path, str]] = {}
    swapped: list[tuple[Path, Path | None]] = []
    receipts: dict[str, Any] = {}
    try:
        for spec in specs:
            require(re.fullmatch(r"[a-z][a-z0-9_]*", spec.name) is not None, "source name invalid")
            target = root / spec.name
            ensure_managed_child(root, target)
            staged = root / f".{spec.name}.stage-{uuid.uuid4().hex}"
            ensure_managed_child(root, staged)
            run_git([
                "clone", "--quiet", "--depth", "1", "--single-branch",
                "--branch", spec.ref, "--", spec.remote, str(staged),
            ])
            staged_commit = inspect_checkout(staged, spec)
            if target.exists():
                current_commit = inspect_checkout(target, spec)
                if current_commit == staged_commit:
                    safe_remove(root, staged)
                    receipts[spec.name] = {"status": "unchanged", "ref": spec.ref, "commit": staged_commit}
                    continue
            prepared[spec.name] = (spec, staged, staged_commit)

        for name, (spec, staged, commit) in prepared.items():
            target = root / name
            rollback: Path | None = None
            if target.exists():
                rollback = root / f".{name}.rollback-{uuid.uuid4().hex}"
                ensure_managed_child(root, rollback)
                os.replace(target, rollback)
            swapped.append((target, rollback))
            os.replace(staged, target)
            require(inspect_checkout(target, spec) == commit, "managed_source_post_swap_mismatch")
            receipts[name] = {"status": "synced", "ref": spec.ref, "commit": commit}

        for _, rollback in swapped:
            if rollback is not None:
                safe_remove(root, rollback)
        return {"status": "ok", "sources": receipts}
    except Exception:
        for target, rollback in reversed(swapped):
            if rollback is not None and rollback.exists():
                if target.exists():
                    staged_failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
                    os.replace(target, staged_failed)
                    safe_remove(root, staged_failed)
                os.replace(rollback, target)
            elif rollback is None and target.exists():
                staged_failed = root / f".{target.name}.failed-{uuid.uuid4().hex}"
                os.replace(target, staged_failed)
                safe_remove(root, staged_failed)
        raise
    finally:
        for _, staged, _ in prepared.values():
            if staged.exists():
                safe_remove(root, staged)
        for child in root.glob(".*.stage-*"):
            safe_remove(root, child)


def run_json(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError("host_materialization_timeout") from exc
    require(len(result.stdout) <= 1_048_576 and len(result.stderr) <= 1_048_576, "host_materialization_output_too_large")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError("host_materialization_output_invalid") from exc
    require(isinstance(payload, dict), "host_materialization_output_invalid")
    if result.returncode:
        error = payload.get("error")
        code = error.get("code", "host_materialization_failed") if isinstance(error, dict) else "host_materialization_failed"
        raise BootstrapError(str(code))
    return payload


def materialize_host(codex_home: Path, specs: tuple[SourceSpec, ...]) -> dict[str, Any]:
    codex_home = codex_home.resolve()
    root = codex_home / "agent-memory" / "sources"
    by_name = {spec.name: spec for spec in specs}
    require(set(by_name).issubset({"sidecar", "canonical_owner"}), "managed_source_name_invalid")
    require("sidecar" in by_name, "managed_sidecar_source_missing")
    require(len(by_name) == len(specs), "managed_source_name_duplicate")
    if "canonical_owner" not in by_name:
        require(
            not _has_existing_global_binding(codex_home),
            "public_core_existing_global_binding",
        )
    for spec in specs:
        inspect_checkout(root / spec.name, spec)
    sidecar = root / "sidecar"
    canonical_owner = root / "canonical_owner" if "canonical_owner" in by_name else None
    enrollment = sidecar / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "enrollment.py"
    require(enrollment.is_file(), "managed_bootstrap_missing")
    skill_root = codex_home / "skills"
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(sidecar / "src") + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    bootstrap_result = run_json([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / ".agents" / "skills" / "agent-memory-workstation-bootstrap"),
        "--target", str(skill_root / "agent-memory-workstation-bootstrap"), "--version", BOOTSTRAP_VERSION,
    ], cwd=sidecar, env=env)
    scout_result = run_json([
        sys.executable, "-B", str(enrollment), "install-skill",
        "--source", str(sidecar / ".agents" / "skills" / "global-owner-scout"),
        "--target", str(skill_root / "global-owner-scout"), "--version", SCOUT_VERSION,
    ], cwd=sidecar, env=env)
    setup_command = [
        sys.executable, "-B", "-m", "agent_memory_sidecar", "--cwd", str(sidecar), "setup", "--apply",
    ]
    if canonical_owner is not None:
        setup_command.extend([
            "--global-rules-source", str(canonical_owner), "--rebind-global-rules-source",
        ])
    setup = run_json(setup_command, cwd=sidecar, env=env)
    require(setup.get("status") == "ok", "core_setup_failed")
    doctor = run_json([
        sys.executable, "-B", "-m", "agent_memory_sidecar", "--cwd", str(sidecar), "doctor",
    ], cwd=sidecar, env=env)
    require(doctor.get("status") == "ok", "doctor_failed")
    return {
        "status": "ok",
        "core_setup": "verified",
        "global_binding": "verified" if canonical_owner is not None else "unavailable",
        "doctor": "verified",
        "bootstrap_skill": bootstrap_result["status"],
        "bootstrap_skill_version": bootstrap_result["version"],
        "bootstrap_skill_hash": bootstrap_result["hash"],
        "scout_skill": scout_result["status"],
        "scout_skill_version": scout_result["version"],
        "scout_skill_hash": scout_result["hash"],
    }


def _has_existing_global_binding(codex_home: Path) -> bool:
    store = codex_home.resolve() / "agent-memory-sidecar" / "memory.sqlite"
    if not store.exists():
        return False
    try:
        connection = sqlite3.connect(f"file:{store.as_posix()}?mode=ro", uri=True)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='global_instruction_binding'"
            ).fetchone()
            if table is None:
                return False
            return connection.execute(
                "SELECT 1 FROM global_instruction_binding LIMIT 1"
            ).fetchone() is not None
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise BootstrapError("public_core_binding_check_failed") from exc


def validate_pack(value: Any) -> dict[str, Any]:
    exact(value, PACK_FIELDS, "$")
    require(value["contract_version"] == PACK_VERSION, "deployment pack contract invalid")
    require(value["display_locale"] == "zh-CN", "deployment pack locale invalid")
    require(value["bootstrap_version"] == BOOTSTRAP_VERSION, "deployment pack Bootstrap version invalid")
    require(value["status"] in {"ready", "reload_required", "source_sync_blocked", "host_materialization_blocked"}, "deployment pack status invalid")
    safe_text(value["generated_at"], "$.generated_at", 80)

    distribution = value["portable_distribution"]
    exact(distribution, DISTRIBUTION_FIELDS, "$.portable_distribution")
    for field in DISTRIBUTION_FIELDS:
        require(distribution[field] in {"verified", "installed", "unavailable", "failed"}, f"portable distribution {field} invalid")

    source_sync = value["source_sync"]
    exact(source_sync, SOURCE_SYNC_FIELDS, "$.source_sync")
    for name in SOURCE_SYNC_FIELDS:
        receipt = source_sync[name]
        exact(receipt, SOURCE_RECEIPT_FIELDS, f"$.source_sync.{name}")
        require(receipt["status"] in {"synced", "unchanged", "unavailable", "failed"}, f"source {name} status invalid")
        safe_text(receipt["ref"], f"$.source_sync.{name}.ref", 80)
        require(receipt["commit"] == "unavailable" or SHA40.fullmatch(receipt["commit"]) is not None, f"source {name} commit invalid")

    material = value["host_materialization"]
    exact(material, MATERIALIZATION_FIELDS, "$.host_materialization")
    for field in ("core_setup", "global_binding", "doctor", "bootstrap_skill", "scout_skill"):
        require(material[field] in {"verified", "installed", "unchanged", "unavailable", "failed"}, f"materialization {field} invalid")
    require(material["bootstrap_skill_version"] == BOOTSTRAP_VERSION, "materialized Bootstrap version invalid")
    require(material["scout_skill_version"] == SCOUT_VERSION, "materialized Scout version invalid")

    activation = value["project_activation"]
    exact(activation, ACTIVATION_FIELDS, "$.project_activation")
    require(activation["interactive_entry"] in {"available_next_turn", "verified", "blocked"}, "interactive activation invalid")
    require(activation["scheduled"] in {"paused", "not_configured", "unchanged"}, "scheduled activation invalid")
    require(isinstance(value["limitations"], list), "$.limitations must be a list")
    for index, item in enumerate(value["limitations"]):
        safe_text(item, f"$.limitations[{index}]", 300)
    require(value["pack_hash"] == object_hash(value, "pack_hash"), "deployment pack hash mismatch")
    return value


def validate_marketplace(
    value: Any,
    *,
    require_immutable: bool = False,
    expected_remote: str | None = None,
) -> dict[str, Any]:
    exact(value, MARKETPLACE_FIELDS, "$")
    require(value["name"] == "agent-memory", "marketplace name invalid")
    require(value["interface"] == {"displayName": "Agent Memory"}, "marketplace interface invalid")
    require(isinstance(value["plugins"], list) and len(value["plugins"]) == 1, "marketplace plugin count invalid")
    entry = value["plugins"][0]
    exact(entry, {"name", "source", "policy", "category"}, "$.plugins[0]")
    require(entry["name"] == "agent-memory-sidecar", "marketplace plugin name invalid")
    require(entry["category"] == "Productivity", "marketplace category invalid")
    require(entry["policy"] == {"installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_INSTALL"}, "marketplace policy invalid")
    source = entry["source"]
    exact(source, {"source", "url", "path", "ref"}, "$.plugins[0].source")
    require(source["source"] == "git-subdir", "marketplace source kind invalid")
    remote = str(source["url"]).strip()
    ref = str(source["ref"]).strip().casefold()
    normalize_remote(remote)
    if expected_remote is not None:
        require(normalize_remote(remote) == normalize_remote(expected_remote), "marketplace source identity invalid")
    require(source["path"] == "./plugins/agent-memory-sidecar", "marketplace plugin path invalid")
    require(
        SAFE_REF.fullmatch(ref) is not None
        and ".." not in ref
        and "//" not in ref
        and "@{" not in ref
        and not ref.endswith(("/", ".", ".lock")),
        "marketplace ref invalid",
    )
    if require_immutable:
        require(SHA40.fullmatch(ref) is not None, "marketplace immutable ref required")
    return value


def render_pack(value: Any) -> str:
    pack = validate_pack(value)
    status = {
        "ready": "本机能力已对齐",
        "reload_required": "能力已安装，需在下一任务加载",
        "source_sync_blocked": "远端能力源同步受阻",
        "host_materialization_blocked": "本机能力物化受阻",
    }[pack["status"]]
    sources = pack["source_sync"]
    material = pack["host_materialization"]
    activation = pack["project_activation"]
    lines = [
        "# Agent Memory 本机部署结果",
        "",
        f"> **{status}**。本次没有创建或恢复 Scheduled Task，也没有修改任何项目 Owner。",
        "",
        "| 能力层 | 结果 | 说明 |",
        "|---|---|---|",
        f"| 可移植分发 | Anchor `{pack['portable_distribution']['repo_anchor']}` / Plugin `{pack['portable_distribution']['plugin']}` | 当前工程可发现冷启动入口 |",
        f"| 能力源同步 | Sidecar `{sources['sidecar']['status']}` / Global Owner `{sources['canonical_owner']['status']}` | 只更新本机受管缓存，不清理活跃工程 |",
        f"| 主机物化 | Core `{material['core_setup']}` / Doctor `{material['doctor']}` / Scout `{material['scout_skill']}` | Bootstrap {material['bootstrap_skill_version']}；Scout {material['scout_skill_version']} |",
        f"| 项目启用 | 交互入口 `{activation['interactive_entry']}` / Scheduled `{activation['scheduled']}` | 项目集合仍由当前主机和用户决定 |",
    ]
    if pack["limitations"]:
        lines.extend(["", "## 尚未证明", ""])
        lines.extend(f"> {item}" for item in pack["limitations"])
    lines.extend([
        "",
        "下一步：在目标工程的新任务中发送 `$global-owner-scout 复盘当前项目`；若本次刚安装插件或 Skill，请使用下一任务加载。",
        "",
        f"校验回执：`{PACK_VERSION}`｜Pack `{pack['pack_hash'][:12]}`",
    ])
    return "\n".join(lines) + "\n"


def valid_pack() -> dict[str, Any]:
    pack = {
        "contract_version": PACK_VERSION,
        "status": "ready",
        "display_locale": "zh-CN",
        "bootstrap_version": BOOTSTRAP_VERSION,
        "generated_at": "2026-08-12T12:00:00+08:00",
        "portable_distribution": {"repo_anchor": "verified", "plugin": "installed", "marketplace": "verified"},
        "source_sync": {
            "sidecar": {"status": "synced", "ref": "main", "commit": "a" * 40},
            "canonical_owner": {"status": "unchanged", "ref": "main", "commit": "b" * 40},
        },
        "host_materialization": {
            "core_setup": "verified", "global_binding": "verified", "doctor": "verified",
            "bootstrap_skill": "installed", "scout_skill": "installed",
            "bootstrap_skill_version": BOOTSTRAP_VERSION, "scout_skill_version": SCOUT_VERSION,
        },
        "project_activation": {"interactive_entry": "verified", "scheduled": "paused"},
        "limitations": ["真实第二台设备的首次部署与项目续接仍需独立验收。"],
        "pack_hash": "",
    }
    pack["pack_hash"] = object_hash(pack, "pack_hash")
    return pack


def create_remote(parent: Path, name: str) -> Path:
    work = parent / f"{name}-work"
    remote = parent / f"{name}.git"
    work.mkdir()
    run_git(["init", "-q", "-b", "main"], cwd=work)
    run_git(["config", "user.name", "Bootstrap Test"], cwd=work)
    run_git(["config", "user.email", "bootstrap@example.invalid"], cwd=work)
    (work / "README.md").write_text(name, encoding="utf-8")
    run_git(["add", "README.md"], cwd=work)
    run_git(["commit", "-q", "-m", "seed"], cwd=work)
    run_git(["clone", "--quiet", "--bare", str(work), str(remote)])
    return remote


def self_test() -> None:
    pack = valid_pack()
    validate_pack(pack)
    require("真实第二台设备" in render_pack(pack), "deployment renderer lost proof boundary")
    marketplace = {
        "name": "agent-memory", "interface": {"displayName": "Agent Memory"},
        "plugins": [{
            "name": "agent-memory-sidecar",
            "source": {"source": "git-subdir", "url": "https://github.com/example/agent-memory-sidecar.git", "path": "./plugins/agent-memory-sidecar", "ref": "main"},
            "policy": {"installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }],
    }
    validate_marketplace(marketplace)
    marketplace["plugins"][0]["source"]["ref"] = "a" * 40
    validate_marketplace(
        marketplace,
        require_immutable=True,
        expected_remote="https://github.com/example/agent-memory-sidecar.git",
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = create_remote(root, "sidecar")
        second = create_remote(root, "owner")
        first_commit = run_git(["rev-parse", "HEAD"], cwd=root / "sidecar-work")
        second_commit = run_git(["rev-parse", "HEAD"], cwd=root / "owner-work")
        release_manifest = {
            "contract_version": SOURCE_MANIFEST_VERSION,
            "distribution": "release",
            "sidecar": {"remote": str(first), "ref": "main", "commit": first_commit},
            "canonical_owner": {"remote": str(second), "ref": "main", "commit": second_commit},
        }
        specs = validate_source_manifest(release_manifest)
        receipt = sync_sources(root / "codex-home", specs)
        require({item["status"] for item in receipt["sources"].values()} == {"synced"}, "first sync did not install both sources")
        again = sync_sources(root / "codex-home", specs)
        require({item["status"] for item in again["sources"].values()} == {"unchanged"}, "second sync was not idempotent")
        public_manifest = dict(release_manifest)
        public_manifest["canonical_owner"] = None
        public_specs = validate_source_manifest(public_manifest)
        require([item.name for item in public_specs] == ["sidecar"], "public manifest retained a private Owner")
        wrong = json.loads(json.dumps(public_manifest))
        wrong["sidecar"]["commit"] = "f" * 40
        try:
            sync_sources(root / "other-home", validate_source_manifest(wrong))
        except BootstrapError as exc:
            require(str(exc) == "managed_source_commit_mismatch", "wrong commit did not fail closed")
        else:
            raise BootstrapError("wrong commit was accepted")
    print(json.dumps({"status": "ok", "tests": 9}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync-sources")
    sync.add_argument("--codex-home", required=True)
    sync.add_argument("--source-manifest", required=True)
    materialize = sub.add_parser("materialize-host")
    materialize.add_argument("--codex-home", required=True)
    materialize.add_argument("--source-manifest", required=True)
    validate_source = sub.add_parser("validate-source-manifest")
    validate_source.add_argument("--path", required=True)
    sub.add_parser("validate-pack")
    sub.add_parser("render-pack")
    sub.add_parser("validate-marketplace")
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "sync-sources":
            specs = load_source_manifest(args.source_manifest)
            print(json.dumps(sync_sources(Path(args.codex_home), specs), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "materialize-host":
            specs = load_source_manifest(args.source_manifest)
            print(json.dumps(materialize_host(Path(args.codex_home), specs), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "validate-source-manifest":
            specs = load_source_manifest(args.path)
            print(json.dumps({"status": "ok", "sources": [item.name for item in specs]}, separators=(",", ":")))
        elif args.command == "validate-pack":
            pack = validate_pack(json.load(sys.stdin))
            print(json.dumps({"status": "ok", "contract_version": pack["contract_version"]}, separators=(",", ":")))
        elif args.command == "render-pack":
            sys.stdout.write(render_pack(json.load(sys.stdin)))
        elif args.command == "validate-marketplace":
            validate_marketplace(json.load(sys.stdin))
            print(json.dumps({"status": "ok", "contract": "agent-memory-marketplace-v1"}, separators=(",", ":")))
        else:
            self_test()
        return 0
    except (BootstrapError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
