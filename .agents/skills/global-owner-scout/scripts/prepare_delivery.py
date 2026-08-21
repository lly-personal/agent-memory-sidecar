#!/usr/bin/env python3
"""Prepare and externally verify a task-scoped Global Owner Scout Review Pack artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from render_review import render_review_pack
from utf8_stdio import configure_utf8_stdio
from validate_output import ContractError, valid_project, valid_review_pack
from verify_visible_output import verify_visible_output


DELIVERY_CONTRACT = "global_owner_scout_delivery_v1"
DELIVERY_SURFACE = "task_artifact"
DELIVERY_STATUS = "prepared"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_NAME_RE = re.compile(r"^global-owner-scout-review-pack-(?P<prefix>[0-9a-f]{16})\.md$")
FINAL_RECEIPT_PREFIX = (
    r"^# Global Owner Scout · 完整审阅包\n\n"
    r"\[打开完整 Review Pack\]\(<(?P<path>[^>\r\n]+)>\)\n\n"
    r"交付回执：`contract=global_owner_scout_delivery_v1`；"
    r"`status=prepared`；`delivery_surface=task_artifact`；"
    rf"`delivery_manifest_sha256=(?P<manifest>{HASH_RE.pattern[1:-1]})`；"
    rf"`artifact_sha256=(?P<artifact>{HASH_RE.pattern[1:-1]})`；"
    r"`artifact_bytes=(?P<bytes>\d+)`；"
    rf"`review_pack_hash=(?P<pack>{HASH_RE.pattern[1:-1]})`；"
    rf"`visible_body_sha256=(?P<body>{HASH_RE.pattern[1:-1]})`；"
    r"`project_cards=(?P<project>\d+)`；`visible_cards=(?P<visible>\d+)`；"
    r"`visible_action_counts=(?P<action_counts>none|\d+(?:,\d+)*)`；"
    r"`visible_actions=(?P<actions>\d+)`；"
    r"`bundle_action_count=(?P<bundle>[01])`；`wrapper_count=(?P<wrapper>[01])`；"
)
FINAL_OPENED_RECEIPT_RE = re.compile(
    FINAL_RECEIPT_PREFIX +
    r"`surface_observation=open_succeeded`；`confirmation_eligible=true`。\n$"
)
FINAL_QUEUED_RECEIPT_RE = re.compile(
    FINAL_RECEIPT_PREFIX +
    r"`surface_observation=open_queued`；`confirmation_eligible=false`。\n$"
)
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def delivery_manifest_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("delivery_manifest_sha256", None)
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def is_reparse(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_existing_directory(value: Path, *, label: str) -> Path:
    require(value.is_absolute(), f"{label} must be an absolute path")
    try:
        raw_stat = value.lstat()
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"{label} is unavailable: {exc}") from exc
    require(not value.is_symlink() and not is_reparse(raw_stat), f"{label} must not be a link or reparse point")
    require(stat.S_ISDIR(raw_stat.st_mode), f"{label} must be an existing directory")
    return resolved


def validate_output_root(artifact_dir: Path, protected_roots: Iterable[Path]) -> Path:
    resolved_dir = safe_existing_directory(artifact_dir, label="artifact-dir")
    roots = [safe_existing_directory(root, label="protected-root") for root in protected_roots]
    require(bool(roots), "at least one protected-root is required")
    for root in roots:
        require(not is_within(resolved_dir, root), "artifact-dir must be outside every protected-root")
    return resolved_dir


def safe_artifact_bytes(path: Path) -> bytes:
    try:
        result = path.lstat()
    except OSError as exc:
        raise ContractError(f"artifact is unavailable: {exc}") from exc
    require(stat.S_ISREG(result.st_mode), "artifact must be a regular file")
    require(not path.is_symlink() and not is_reparse(result), "artifact must not be a link or reparse point")
    require(result.st_nlink == 1, "artifact must have exactly one hard link")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ContractError(f"artifact cannot be read: {exc}") from exc


def make_artifact_read_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IREAD)
        result = path.lstat()
    except OSError as exc:
        raise ContractError(f"artifact cannot be made read-only: {exc}") from exc
    require_artifact_read_only(path)


def require_artifact_read_only(path: Path) -> None:
    try:
        result = path.lstat()
    except OSError as exc:
        raise ContractError(f"artifact is unavailable: {exc}") from exc
    require(stat.S_IMODE(result.st_mode) & 0o222 == 0, "artifact must be read-only")


def write_immutable_artifact(path: Path, expected: bytes) -> None:
    if path.exists() or path.is_symlink():
        require(safe_artifact_bytes(path) == expected, "existing artifact bytes do not match the deterministic Review Pack")
        require_artifact_read_only(path)
        return

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(path, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise ContractError(f"artifact creation failed: {exc}") from exc
    make_artifact_read_only(path)
    require(safe_artifact_bytes(path) == expected, "artifact readback does not match the deterministic Review Pack")


def validate_delivery_manifest(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "delivery manifest must be an object")
    expected_keys = {
        "contract_version",
        "status",
        "delivery_surface",
        "artifact_name",
        "artifact_sha256",
        "artifact_bytes",
        "review_pack_hash",
        "visible_body_sha256",
        "project_cards",
        "visible_cards",
        "visible_action_counts",
        "visible_actions",
        "bundle_action_count",
        "wrapper_count",
        "delivery_manifest_sha256",
    }
    require(set(value) == expected_keys, "delivery manifest fields are invalid")
    require(value["contract_version"] == DELIVERY_CONTRACT, "delivery manifest contract is invalid")
    require(value["status"] == DELIVERY_STATUS, "delivery manifest status is invalid")
    require(value["delivery_surface"] == DELIVERY_SURFACE, "delivery manifest surface is invalid")
    name_match = ARTIFACT_NAME_RE.fullmatch(value["artifact_name"]) if isinstance(value["artifact_name"], str) else None
    require(name_match is not None, "delivery artifact name is invalid")
    for field in ("artifact_sha256", "review_pack_hash", "visible_body_sha256", "delivery_manifest_sha256"):
        require(isinstance(value[field], str) and HASH_RE.fullmatch(value[field]) is not None, f"{field} is invalid")
    require(name_match.group("prefix") == value["review_pack_hash"][:16], "artifact name does not bind the Review Pack hash")
    for field in ("artifact_bytes", "project_cards", "visible_cards", "visible_actions"):
        require(isinstance(value[field], int) and not isinstance(value[field], bool) and value[field] >= 0, f"{field} is invalid")
    require(isinstance(value["visible_action_counts"], list), "visible_action_counts must be an array")
    require(
        all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in value["visible_action_counts"]),
        "visible_action_counts is invalid",
    )
    require(value["bundle_action_count"] in {0, 1}, "bundle_action_count is invalid")
    require(value["wrapper_count"] == 0, "task artifact wrapper_count must be zero")
    require(value["project_cards"] == value["visible_cards"] == len(value["visible_action_counts"]), "card counts do not conserve")
    require(value["visible_actions"] == sum(value["visible_action_counts"]), "action counts do not conserve")
    require(value["delivery_manifest_sha256"] == delivery_manifest_sha256(value), "delivery manifest SHA-256 mismatch")
    return value


def prepare_delivery(pack: dict[str, Any], *, artifact_dir: Path, protected_roots: Iterable[Path]) -> tuple[dict[str, Any], Path]:
    output_root = validate_output_root(artifact_dir, protected_roots)
    rendered = render_review_pack(pack, surface="interactive")
    rendered_bytes = rendered.encode("utf-8")
    visible = verify_visible_output(rendered, surface="interactive")
    artifact_name = f"global-owner-scout-review-pack-{visible['review_pack_hash'][:16]}.md"
    artifact_path = output_root / artifact_name
    write_immutable_artifact(artifact_path, rendered_bytes)
    require_artifact_read_only(artifact_path)
    readback = safe_artifact_bytes(artifact_path)
    require(readback == rendered_bytes, "artifact changed after deterministic creation")
    verified_readback = verify_visible_output(readback.decode("utf-8"), surface="interactive")
    require(verified_readback == visible, "artifact verification changed after readback")
    manifest: dict[str, Any] = {
        "contract_version": DELIVERY_CONTRACT,
        "status": DELIVERY_STATUS,
        "delivery_surface": DELIVERY_SURFACE,
        "artifact_name": artifact_name,
        "artifact_sha256": sha256_bytes(readback),
        "artifact_bytes": len(readback),
        "review_pack_hash": visible["review_pack_hash"],
        "visible_body_sha256": visible["visible_body_sha256"],
        "project_cards": visible["project_cards"],
        "visible_cards": visible["visible_cards"],
        "visible_action_counts": visible["visible_action_counts"],
        "visible_actions": visible["visible_actions"],
        "bundle_action_count": visible["bundle_action_count"],
        "wrapper_count": visible["wrapper_count"],
    }
    manifest["delivery_manifest_sha256"] = delivery_manifest_sha256(manifest)
    return validate_delivery_manifest(manifest), artifact_path


def markdown_path(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


def validate_manifest_artifact(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> Path:
    manifest = validate_delivery_manifest(manifest)
    root = safe_existing_directory(artifact_root, label="artifact-root")
    require(artifact_path.is_absolute(), "artifact path must be absolute")
    require(artifact_path.name == manifest["artifact_name"], "artifact path does not match manifest")
    try:
        parent = artifact_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"artifact parent is unavailable: {exc}") from exc
    require(parent == root, "artifact path must be a direct child of artifact-root")
    require_artifact_read_only(artifact_path)
    data = safe_artifact_bytes(artifact_path)
    require(len(data) == manifest["artifact_bytes"], "artifact byte count does not match manifest")
    require(sha256_bytes(data) == manifest["artifact_sha256"], "artifact SHA-256 does not match manifest")
    visible = verify_visible_output(data.decode("utf-8"), surface="interactive")
    for field in (
        "review_pack_hash",
        "visible_body_sha256",
        "project_cards",
        "visible_cards",
        "visible_action_counts",
        "visible_actions",
        "bundle_action_count",
        "wrapper_count",
    ):
        require(visible[field] == manifest[field], f"artifact {field} does not match manifest")
    return artifact_path


def render_opened_receipt(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> str:
    manifest = validate_delivery_manifest(manifest)
    artifact_path = validate_manifest_artifact(manifest, artifact_path=artifact_path, artifact_root=artifact_root)
    action_counts = ",".join(str(item) for item in manifest["visible_action_counts"]) or "none"
    return (
        "# Global Owner Scout · 完整审阅包\n\n"
        f"[打开完整 Review Pack](<{markdown_path(artifact_path)}>)\n\n"
        f"交付回执：`contract={DELIVERY_CONTRACT}`；`status={manifest['status']}`；"
        f"`delivery_surface={manifest['delivery_surface']}`；"
        f"`delivery_manifest_sha256={manifest['delivery_manifest_sha256']}`；"
        f"`artifact_sha256={manifest['artifact_sha256']}`；`artifact_bytes={manifest['artifact_bytes']}`；"
        f"`review_pack_hash={manifest['review_pack_hash']}`；"
        f"`visible_body_sha256={manifest['visible_body_sha256']}`；"
        f"`project_cards={manifest['project_cards']}`；`visible_cards={manifest['visible_cards']}`；"
        f"`visible_action_counts={action_counts}`；`visible_actions={manifest['visible_actions']}`；"
        f"`bundle_action_count={manifest['bundle_action_count']}`；`wrapper_count={manifest['wrapper_count']}`；"
        "`surface_observation=open_succeeded`；`confirmation_eligible=true`。\n"
    )


def render_queued_receipt(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> str:
    manifest = validate_delivery_manifest(manifest)
    artifact_path = validate_manifest_artifact(manifest, artifact_path=artifact_path, artifact_root=artifact_root)
    action_counts = ",".join(str(item) for item in manifest["visible_action_counts"]) or "none"
    return (
        "# Global Owner Scout · 完整审阅包\n\n"
        f"[打开完整 Review Pack](<{markdown_path(artifact_path)}>)\n\n"
        f"交付回执：`contract={DELIVERY_CONTRACT}`；`status={manifest['status']}`；"
        f"`delivery_surface={manifest['delivery_surface']}`；"
        f"`delivery_manifest_sha256={manifest['delivery_manifest_sha256']}`；"
        f"`artifact_sha256={manifest['artifact_sha256']}`；`artifact_bytes={manifest['artifact_bytes']}`；"
        f"`review_pack_hash={manifest['review_pack_hash']}`；"
        f"`visible_body_sha256={manifest['visible_body_sha256']}`；"
        f"`project_cards={manifest['project_cards']}`；`visible_cards={manifest['visible_cards']}`；"
        f"`visible_action_counts={action_counts}`；`visible_actions={manifest['visible_actions']}`；"
        f"`bundle_action_count={manifest['bundle_action_count']}`；`wrapper_count={manifest['wrapper_count']}`；"
        "`surface_observation=open_queued`；`confirmation_eligible=false`。\n"
    )


def render_blocked_receipt(manifest: dict[str, Any]) -> str:
    manifest = validate_delivery_manifest(manifest)
    return (
        "# Global Owner Scout · 交付阻断\n\n"
        "完整 Review Pack 已准备，但当前任务宿主未证明同任务可见表面；没有显示部分卡片，确认入口保持关闭。\n\n"
        f"交付失败：`status=interactive_host_blocked`；"
        f"`delivery_manifest_sha256={manifest['delivery_manifest_sha256']}`；"
        "`surface_observation=open_failed`；`confirmation_eligible=false`。\n"
    )


def verify_final_receipt(value: str, *, artifact_root: Path) -> dict[str, Any]:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n\n") and not text.endswith("\n\n\n"):
        text = text[:-1]
    match = FINAL_OPENED_RECEIPT_RE.fullmatch(text)
    surface_status = "surface_observed"
    confirmation_eligible = True
    if match is None:
        match = FINAL_QUEUED_RECEIPT_RE.fullmatch(text)
        surface_status = "surface_pending"
        confirmation_eligible = False
    require(match is not None, "actual task final is not an exact opened or queued Delivery receipt")
    root = safe_existing_directory(artifact_root, label="artifact-root")
    artifact_path = Path(match.group("path"))
    require(artifact_path.is_absolute(), "actual task final artifact path must be absolute")
    try:
        raw_stat = artifact_path.lstat()
        parent = artifact_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"actual task artifact is unavailable: {exc}") from exc
    require(not artifact_path.is_symlink() and not is_reparse(raw_stat), "actual task artifact must not be a link or reparse point")
    require(parent == root, "actual task final artifact must be a direct child of artifact-root")
    require_artifact_read_only(artifact_path)
    data = safe_artifact_bytes(artifact_path)
    action_counts = [] if match.group("action_counts") == "none" else [int(item) for item in match.group("action_counts").split(",")]
    manifest: dict[str, Any] = {
        "contract_version": DELIVERY_CONTRACT,
        "status": DELIVERY_STATUS,
        "delivery_surface": DELIVERY_SURFACE,
        "artifact_name": artifact_path.name,
        "artifact_sha256": match.group("artifact"),
        "artifact_bytes": int(match.group("bytes")),
        "review_pack_hash": match.group("pack"),
        "visible_body_sha256": match.group("body"),
        "project_cards": int(match.group("project")),
        "visible_cards": int(match.group("visible")),
        "visible_action_counts": action_counts,
        "visible_actions": int(match.group("actions")),
        "bundle_action_count": int(match.group("bundle")),
        "wrapper_count": int(match.group("wrapper")),
        "delivery_manifest_sha256": match.group("manifest"),
    }
    validate_delivery_manifest(manifest)
    require(len(data) == manifest["artifact_bytes"], "actual task artifact byte count mismatch")
    require(sha256_bytes(data) == manifest["artifact_sha256"], "actual task artifact SHA-256 mismatch")
    visible = verify_visible_output(data.decode("utf-8"), surface="interactive")
    for field in (
        "review_pack_hash",
        "visible_body_sha256",
        "project_cards",
        "visible_cards",
        "visible_action_counts",
        "visible_actions",
        "bundle_action_count",
        "wrapper_count",
    ):
        require(visible[field] == manifest[field], f"actual task artifact {field} does not match Delivery receipt")
    return {
        "status": surface_status,
        "delivery_manifest_sha256": manifest["delivery_manifest_sha256"],
        "artifact_sha256": manifest["artifact_sha256"],
        "artifact_bytes": manifest["artifact_bytes"],
        "project_cards": manifest["project_cards"],
        "visible_cards": manifest["visible_cards"],
        "visible_actions": manifest["visible_actions"],
        "confirmation_eligible": confirmation_eligible,
    }


def run_self_test() -> None:
    tests = 0
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        protected = root / "project"
        artifact_dir = root / "task-output"
        protected.mkdir()
        artifact_dir.mkdir()
        for count in (0, 1, 3, 6, 7, 8, 24):
            status = "no_material_delta" if count == 0 else "ok"
            pack = valid_review_pack(valid_project(status=status, card_count=count))
            manifest, artifact_path = prepare_delivery(pack, artifact_dir=artifact_dir, protected_roots=[protected])
            receipt = render_opened_receipt(manifest, artifact_path=artifact_path, artifact_root=artifact_dir)
            observed = verify_final_receipt(receipt, artifact_root=artifact_dir)
            assert observed["status"] == "surface_observed"
            assert observed["visible_cards"] == count
            assert "confirmation_eligible=true" in receipt
            queued_receipt = render_queued_receipt(manifest, artifact_path=artifact_path, artifact_root=artifact_dir)
            pending = verify_final_receipt(queued_receipt, artifact_root=artifact_dir)
            assert pending["status"] == "surface_pending"
            assert pending["visible_cards"] == count
            assert pending["confirmation_eligible"] is False
            host_enveloped = verify_final_receipt(queued_receipt + "\n", artifact_root=artifact_dir)
            assert host_enveloped == pending
            assert "confirmation_eligible=false" in render_blocked_receipt(manifest)
            tests += 1

        pack = valid_review_pack(valid_project(card_count=1))
        try:
            prepare_delivery(pack, artifact_dir=protected, protected_roots=[protected])
        except ContractError:
            tests += 1
        else:
            raise AssertionError("protected artifact root was accepted")

        manifest, artifact_path = prepare_delivery(pack, artifact_dir=artifact_dir, protected_roots=[protected])
        artifact_path.chmod(stat.S_IREAD | stat.S_IWRITE)
        artifact_path.write_text("tampered", encoding="utf-8")
        try:
            prepare_delivery(pack, artifact_dir=artifact_dir, protected_roots=[protected])
        except ContractError:
            tests += 1
        else:
            raise AssertionError("conflicting artifact bytes were accepted")

        invalid_manifest = dict(manifest)
        invalid_manifest["artifact_bytes"] += 1
        try:
            validate_delivery_manifest(invalid_manifest)
        except ContractError:
            tests += 1
        else:
            raise AssertionError("tampered delivery manifest was accepted")

    print(json.dumps({"status": "ok", "tests": tests, "delivery": DELIVERY_CONTRACT}, separators=(",", ":")))


def load_stdin_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Prepare or externally verify a task-scoped Global Owner Scout delivery.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--protected-root", action="append", type=Path, default=[])
    parser.add_argument("--render-receipt", choices=("open_succeeded", "open_queued", "open_failed"))
    parser.add_argument("--artifact-path", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--verify-final", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            run_self_test()
        elif args.verify_final:
            require(args.artifact_root is not None, "--artifact-root is required with --verify-final")
            print(json.dumps(verify_final_receipt(sys.stdin.read(), artifact_root=args.artifact_root), ensure_ascii=False, separators=(",", ":")))
        elif args.render_receipt is not None:
            manifest = validate_delivery_manifest(load_stdin_json())
            if args.render_receipt == "open_succeeded":
                require(args.artifact_path is not None, "--artifact-path is required for an opened receipt")
                require(args.artifact_root is not None, "--artifact-root is required for an opened receipt")
                print(render_opened_receipt(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root), end="")
            elif args.render_receipt == "open_queued":
                require(args.artifact_path is not None, "--artifact-path is required for a queued receipt")
                require(args.artifact_root is not None, "--artifact-root is required for a queued receipt")
                print(render_queued_receipt(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root), end="")
            else:
                print(render_blocked_receipt(manifest), end="")
        else:
            require(args.artifact_dir is not None, "--artifact-dir is required")
            manifest, _ = prepare_delivery(load_stdin_json(), artifact_dir=args.artifact_dir, protected_roots=args.protected_root)
            print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
