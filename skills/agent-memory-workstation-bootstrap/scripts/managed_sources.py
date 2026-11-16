#!/usr/bin/env python3
"""Atomic workstation reconcile and deployment-pack CLI facade for Bootstrap 2.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable
import uuid

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import bootstrap_contracts as _contracts
import bootstrap_security as _security
import deployment_pack as _deployment_pack
import source_cutover as _source_cutover
import workstation_observer as _observer

from bootstrap_contracts import (
    ABSOLUTE_PATH,
    ACTIVATION_FIELDS,
    CONSUMER_PROJECT_FIELDS,
    CONSUMER_SCOPE_FIELDS,
    CONSUMER_SKILLS,
    CONSUMER_SKILL_FIELDS,
    CONSUMER_SKILL_MAX_BYTES,
    CONSUMER_SKILL_MAX_ENTRIES,
    CORE_STATE_FIELDS,
    DESIRED_BUNDLE_FIELDS,
    DESKTOP_PROJECT_INPUT_FIELDS,
    DESKTOP_PROJECT_INVENTORY_FIELDS,
    DESKTOP_PROJECT_INVENTORY_VERSION,
    DESKTOP_PROJECT_MAX_COUNT,
    DISTRIBUTION_FIELDS,
    MANAGED_REVIEW_SKILL,
    MARKETPLACE_FIELDS,
    MARKETPLACE_STATE_FIELDS,
    MATERIALIZATION_FIELDS,
    NATIVE_SKILLS_MAX_BYTES,
    NATIVE_SKILLS_TIMEOUT_SECONDS,
    PACK_FIELDS,
    PACK_VERSION,
    PLUGIN_STATE_FIELDS,
    PUBLIC_REPOSITORY,
    RAW_URL,
    RECONCILE_PLAN_FIELDS,
    RELEASE_ASSET_FIELDS,
    RELEASE_MANIFEST_FIELDS,
    RELEASE_MANIFEST_VERSION,
    RELEASE_RESOLUTION_FIELDS,
    RELEASE_RESOLUTION_VERSION,
    RELEASE_SOURCE_FIELDS,
    RELEASE_VERSION_FIELDS,
    REVIEW_DISABLED_NOTICE,
    REVIEW_SKILL,
    SAFE_REF,
    SEMVER,
    SHA40,
    SHA64,
    SKILL_STATE_FIELDS,
    SOURCE_CUTOVER_PLAN_FIELDS,
    SOURCE_CUTOVER_PLAN_VERSION,
    SOURCE_CUTOVER_RECEIPT_VERSION,
    SOURCE_FIELDS,
    SOURCE_MANIFEST_FIELDS,
    SOURCE_MANIFEST_VERSION,
    SOURCE_RECEIPT_FIELDS,
    SOURCE_SYNC_FIELDS,
    STREAM_CHUNK_BYTES,
    WORKSTATION_RECONCILE_PLAN_VERSION,
    WORKSTATION_RECONCILE_RECEIPT_VERSION,
    SourceSpec,
    _consumer_capability,
    _distribution_is_exact,
    _host_is_exact,
    _load_json_file,
    _physical_file_bytes,
    _unavailable_or_sha40,
    _unavailable_or_sha64,
    _validate_host_materialization,
    _validate_source_sync,
    canonical,
    exact,
    load_source_manifest,
    normalize_remote,
    object_hash,
    require,
    safe_text,
    validate_consumer_scope,
    validate_desired_bundle,
    validate_marketplace,
    validate_observed_distribution,
    validate_pack,
    validate_source_cutover_plan,
    validate_source_manifest,
    validate_workstation_reconcile_plan,
)
from bootstrap_security import BootstrapError, run_git
from deployment_pack import (
    _add_marketplace,
    _add_plugin,
    _apply_distribution_changes,
    _markdown_table_text,
    _remove_marketplace,
    _remove_plugin,
    _restore_distribution,
    _source_sync_from_exact_plan,
    build_deployment_pack,
    build_workstation_reconcile_plan,
    legacy_release_reconcile_manifest,
    render_pack,
    render_workstation_reconcile_plan,
)
from source_cutover import (
    _agent_memory_root,
    _codex_home_root,
    _current_owner_root,
    _discard_skill_snapshots,
    _existing_global_binding,
    _installed_skill_root,
    _is_reparse,
    _managed_source_root,
    _physical_directory,
    _preflight_cutover_receipt,
    _preserved_owner_identity,
    _restore_skill_targets,
    _snapshot_skill_targets,
    _source_cutover_state,
    _validate_cutover_receipt_target,
    _validate_physical_skill_tree,
    _write_cutover_receipt,
    bounded_physical_tree_hash,
    create_remote,
    ensure_managed_child,
    inspect_checkout,
    inspect_existing_checkout,
    inspect_marketplace_checkout,
    physical_tree_hash,
    plan_source_cutover,
    render_source_cutover_plan,
    safe_remove,
    source_identity,
    sync_sources,
    verify_remote_ref,
)
from workstation_observer import (
    _consumer_skill_path,
    _expected_review_hash,
    _has_existing_global_binding,
    _missing_marketplace_state,
    _missing_plugin_state,
    _not_observed_consumer_scope,
    _observe_installed_skill,
    _portable_root_for_release_manifest,
    _skill_version,
    _unavailable_host_materialization,
    _unavailable_marketplace_state,
    _unavailable_plugin_state,
    _unavailable_skill_state,
    core_setup_data,
    load_desired_bundle,
    run_codex_json,
    run_json,
)

BOOTSTRAP_VERSION = "2.5.12"
SCOUT_VERSION = "5.19.9"
assert BOOTSTRAP_VERSION == _contracts.BOOTSTRAP_VERSION
assert SCOUT_VERSION == _contracts.SCOUT_VERSION


def _facade() -> Any:
    return sys.modules[__name__]


def native_skill_catalog(
    codex_home: Path,
    project_roots: list[Path],
    *,
    timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    timeout = NATIVE_SKILLS_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    return _observer.native_skill_catalog(codex_home, project_roots, timeout_seconds=timeout)


def _observe_distribution_with_private(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _observer._observe_distribution_with_private(codex_home, facade=_facade())


def observe_distribution(codex_home: Path) -> dict[str, Any]:
    return _observer.observe_distribution(codex_home, facade=_facade())


def observe_consumer_scope(
    inventory: Any,
    *,
    desired: dict[str, Any],
    codex_home: Path,
    expected_review_sha256: str,
) -> dict[str, Any]:
    return _observer.observe_consumer_scope(
        inventory,
        desired=desired,
        codex_home=codex_home,
        expected_review_sha256=expected_review_sha256,
        facade=_facade(),
    )


def observe_host_materialization(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    owner_expected: bool,
) -> dict[str, Any]:
    return _observer.observe_host_materialization(
        codex_home,
        specs,
        owner_expected=owner_expected,
        facade=_facade(),
    )


def materialize_host(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    preserve_existing_owner: bool = False,
) -> dict[str, Any]:
    return _observer.materialize_host(
        codex_home,
        specs,
        preserve_existing_owner=preserve_existing_owner,
        facade=_facade(),
    )


def apply_source_cutover(
    codex_home: Path,
    specs: tuple[SourceSpec, ...],
    *,
    plan_hash: str,
    materialize_host_fn: Callable[..., dict[str, Any]] | None = None,
    external_apply: Callable[[], None] | None = None,
    external_rollback: Callable[[], None] | None = None,
    precommit_verify: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return _source_cutover.apply_source_cutover(
        codex_home,
        specs,
        plan_hash=plan_hash,
        materialize_host_fn=materialize_host_fn,
        external_apply=external_apply,
        external_rollback=external_rollback,
        precommit_verify=precommit_verify,
        facade=_facade(),
    )


def _workstation_reconcile_context(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _deployment_pack._workstation_reconcile_context(
        codex_home,
        source_manifest_path,
        release_manifest_path,
        facade=_facade(),
    )


def inspect_workstation_reconcile(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
) -> dict[str, Any]:
    return _deployment_pack.inspect_workstation_reconcile(
        codex_home,
        source_manifest_path,
        release_manifest_path,
        facade=_facade(),
    )


def apply_workstation_reconcile(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    *,
    plan_hash: str,
) -> dict[str, Any]:
    return _deployment_pack.apply_workstation_reconcile(
        codex_home,
        source_manifest_path,
        release_manifest_path,
        plan_hash=plan_hash,
        facade=_facade(),
    )


def verify_workstation_consumer(
    codex_home: Path,
    source_manifest_path: Path | str,
    release_manifest_path: Path | str,
    desktop_project_inventory_path: Path | str,
) -> dict[str, Any]:
    return _deployment_pack.verify_workstation_consumer(
        codex_home,
        source_manifest_path,
        release_manifest_path,
        desktop_project_inventory_path,
        facade=_facade(),
    )


def self_test() -> None:
    desired = {
        "release_ref": "v0.3.8", "source_commit": "a" * 40,
        "core_version": "0.3.8", "plugin_version": "1.5.0", "plugin_sha256": "b" * 64,
        "bootstrap_version": BOOTSTRAP_VERSION, "bootstrap_sha256": "c" * 64,
        "scout_version": SCOUT_VERSION, "scout_sha256": "d" * 64,
    }
    source_identity_hash = "e" * 64
    pack = build_deployment_pack(
        desired=desired,
        observed_distribution={
            "marketplace": {
                "status": "present", "source_sha256": source_identity_hash,
                "ref": "v0.3.8", "commit": "a" * 40,
            },
            "plugin": {
                "status": "installed", "source_sha256": source_identity_hash,
                "ref": "v0.3.8", "version": "1.5.0",
                "content_sha256": "b" * 64, "enabled": True,
            },
        },
        desired_source_sha256=source_identity_hash,
        source_sync={
            "sidecar": {"status": "unchanged", "ref": "v0.3.8", "commit": "a" * 40},
            "canonical_owner": {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"},
        },
        host_materialization={
            "core": {
                "status": "verified", "version": "0.3.8",
                "source_commit": "a" * 40, "artifact_sha256": "f" * 64,
            },
            "global_binding": "unavailable", "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged", "version": BOOTSTRAP_VERSION, "content_sha256": "c" * 64,
            },
            "scout_skill": {
                "status": "unchanged", "version": SCOUT_VERSION, "content_sha256": "d" * 64,
            },
        },
        requires_reload=True,
        consumer_verified=False,
        generated_at="2026-08-21T12:00:00+08:00",
    )
    require("其他设备与跨任务连续性仍未证明" in render_pack(pack), "deployment renderer lost proof boundary")
    marketplace = {
        "name": "agent-memory", "interface": {"displayName": "Agent Memory"},
        "plugins": [{
            "name": "agent-memory-sidecar",
            "source": {"source": "git-subdir", "url": "https://github.com/example/agent-memory-sidecar.git", "path": "./plugins/agent-memory-sidecar", "ref": "main"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
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
        new_sidecar = create_remote(root, "public-sidecar")
        new_commit = run_git(["rev-parse", "HEAD"], cwd=root / "public-sidecar-work")
        cutover_manifest = json.loads(json.dumps(release_manifest))
        cutover_manifest["sidecar"] = {
            "remote": str(new_sidecar), "ref": "main", "commit": new_commit,
        }
        cutover_plan = plan_source_cutover(root / "codex-home", validate_source_manifest(cutover_manifest))
        require(cutover_plan["owner_action"] == "keep_owner", "cutover lost Owner boundary")
        require("sidecar:replace" in cutover_plan["changes"], "cutover did not detect source identity change")
    print(json.dumps({"status": "ok", "tests": 11}, ensure_ascii=False))


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict" if stream is sys.stdin else "replace")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync-sources")
    sync.add_argument("--codex-home", required=True)
    sync.add_argument("--source-manifest", required=True)
    materialize = sub.add_parser("materialize-host")
    materialize.add_argument("--codex-home", required=True)
    materialize.add_argument("--source-manifest", required=True)
    cutover = sub.add_parser("source-cutover")
    cutover.add_argument("--codex-home", required=True)
    cutover.add_argument("--source-manifest", required=True)
    cutover_mode = cutover.add_mutually_exclusive_group(required=True)
    cutover_mode.add_argument("--dry-run", action="store_true")
    cutover_mode.add_argument("--apply", action="store_true")
    cutover.add_argument("--plan-hash")
    reconcile = sub.add_parser("workstation-reconcile")
    reconcile.add_argument("--codex-home", required=True)
    reconcile.add_argument("--source-manifest", required=True)
    reconcile.add_argument("--release-manifest", required=True)
    reconcile_mode = reconcile.add_mutually_exclusive_group(required=True)
    reconcile_mode.add_argument("--dry-run", action="store_true")
    reconcile_mode.add_argument("--apply", action="store_true")
    reconcile_mode.add_argument("--verify-consumer", action="store_true")
    reconcile.add_argument("--plan-hash")
    reconcile.add_argument("--desktop-project-inventory")
    validate_source = sub.add_parser("validate-source-manifest")
    validate_source.add_argument("--path", required=True)
    sub.add_parser("validate-pack")
    sub.add_parser("render-pack")
    sub.add_parser("render-cutover-plan")
    sub.add_parser("render-reconcile-plan")
    observe = sub.add_parser("observe-distribution")
    observe.add_argument("--codex-home", required=True)
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
        elif args.command == "source-cutover":
            legacy_release = legacy_release_reconcile_manifest(args.source_manifest)
            if legacy_release is not None:
                if args.dry_run:
                    require(args.plan_hash is None, "source_cutover_plan_hash_unexpected")
                    result = inspect_workstation_reconcile(
                        Path(args.codex_home), args.source_manifest, legacy_release,
                    )
                else:
                    require(args.plan_hash is not None, "source_cutover_plan_hash_required")
                    result = apply_workstation_reconcile(
                        Path(args.codex_home), args.source_manifest, legacy_release,
                        plan_hash=args.plan_hash,
                    )
            else:
                specs = load_source_manifest(args.source_manifest)
                if args.dry_run:
                    require(args.plan_hash is None, "source_cutover_plan_hash_unexpected")
                    result = plan_source_cutover(Path(args.codex_home), specs)
                else:
                    require(args.plan_hash is not None, "source_cutover_plan_hash_required")
                    result = apply_source_cutover(
                        Path(args.codex_home), specs, plan_hash=args.plan_hash,
                    )
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif args.command == "workstation-reconcile":
            if args.dry_run:
                require(args.plan_hash is None, "reconcile_plan_hash_unexpected")
                require(args.desktop_project_inventory is None, "desktop_project_inventory_unexpected")
                result = inspect_workstation_reconcile(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                )
            elif args.apply:
                require(args.plan_hash is not None, "reconcile_plan_hash_required")
                require(args.desktop_project_inventory is None, "desktop_project_inventory_unexpected")
                result = apply_workstation_reconcile(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                    plan_hash=args.plan_hash,
                )
            else:
                require(args.plan_hash is None, "reconcile_plan_hash_unexpected")
                require(args.desktop_project_inventory is not None, "desktop_project_inventory_required")
                result = verify_workstation_consumer(
                    Path(args.codex_home), args.source_manifest, args.release_manifest,
                    args.desktop_project_inventory,
                )
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif args.command == "validate-source-manifest":
            specs = load_source_manifest(args.path)
            print(json.dumps({"status": "ok", "sources": [item.name for item in specs]}, separators=(",", ":")))
        elif args.command == "validate-pack":
            pack = validate_pack(json.load(sys.stdin))
            print(json.dumps({"status": "ok", "contract_version": pack["contract_version"]}, separators=(",", ":")))
        elif args.command == "render-pack":
            sys.stdout.write(render_pack(json.load(sys.stdin)))
        elif args.command == "render-cutover-plan":
            plan = json.load(sys.stdin)
            if plan.get("contract_version") == WORKSTATION_RECONCILE_PLAN_VERSION:
                sys.stdout.write(render_workstation_reconcile_plan(plan))
            else:
                sys.stdout.write(render_source_cutover_plan(plan))
        elif args.command == "render-reconcile-plan":
            sys.stdout.write(render_workstation_reconcile_plan(json.load(sys.stdin)))
        elif args.command == "observe-distribution":
            print(json.dumps(observe_distribution(Path(args.codex_home)), ensure_ascii=False, separators=(",", ":")))
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
