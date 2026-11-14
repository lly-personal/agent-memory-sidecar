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

from render_review import extract_conversation_brief, render_review_pack
from utf8_stdio import configure_utf8_stdio
from validate_output import ContractError, valid_project, valid_review_pack
from verify_visible_output import verify_visible_output


DELIVERY_CONTRACT = "global_owner_scout_delivery_v2"
LEGACY_DELIVERY_CONTRACT = "global_owner_scout_delivery_v1"
TERMINAL_CONTRACT = "global_owner_scout_terminal_v1"
DELIVERY_SURFACE = "task_artifact"
DELIVERY_STATUS = "prepared"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_NAME_RE = re.compile(r"^global-owner-scout-review-pack-(?P<prefix>[0-9a-f]{16})\.md$")
VISUAL_FIELDS = {"visual_name", "visual_sha256", "visual_bytes"}
VISUAL_DIRECTIVE_RE = re.compile(r'\nvisualize(?P<payload>[^\n]+)\n?$')
OPENED_COPY = "完整建议已打开，现有规则未改变。仅可确认文件中已通过预演的准确选择；写入前仍会核对当前规则。"
LEGACY_QUEUED_COPY = "完整建议已准备，打开请求仍在排队。可先审阅；文件中的确认命令暂不可执行，现有规则未改变。"
QUEUED_COPY = "文件已校验并提供链接，打开请求仍在排队，尚未证明实际展示。审阅后回复准确选择即可恢复文件核验与规则预演，无需重复复盘。现有规则未改变。"
FINAL_RECEIPT_PREFIX = (
    r"^# Global Owner Scout · 完整审阅包\n\n"
    r"\[打开完整审阅包\]\(<(?P<path>[^>\r\n]+)>\)\n\n"
)
FINAL_RECEIPT_BINDING = rf"\n\n交付回执：`delivery_manifest_sha256=(?P<manifest>{HASH_RE.pattern[1:-1]})`；"
FINAL_OPENED_RECEIPT_RE = re.compile(
    FINAL_RECEIPT_PREFIX + re.escape(OPENED_COPY) + FINAL_RECEIPT_BINDING +
    r"`surface_observation=open_succeeded`；`confirmation_eligible=true`。\n$"
)
FINAL_QUEUED_RECEIPT_RE = re.compile(
    FINAL_RECEIPT_PREFIX + "(?:" + re.escape(QUEUED_COPY) + "|" + re.escape(LEGACY_QUEUED_COPY) + ")" + FINAL_RECEIPT_BINDING +
    r"`surface_observation=open_queued`；`confirmation_eligible=false`。\n$"
)
ADVICE_RECEIPT_RE = re.compile(
    r"^# Global Owner Scout · 复盘结论与建议\n\n[\s\S]+?\n\n"
    r"\[完整依据\]\(<(?P<path>[^>\r\n]+)>\)\n\n[\s\S]+?" + FINAL_RECEIPT_BINDING +
    r"`surface_observation=(?P<surface>not_requested|open_succeeded|open_queued|open_failed)`；"
    r"`confirmation_eligible=(?P<eligible>true|false)`。\n$"
)
SURFACE_COPY = {
    "not_requested": "完整依据已校验，按需打开；文件交付不代表已展示、理解或采用。",
    "open_succeeded": "文件打开请求已成功；实际理解与后续采用仍需分别观察。",
    "open_queued": "文件打开请求仍在排队；可继续讨论以上建议，无需重复复盘或切换窗口。",
    "open_failed": "文件预览未成功；已验证的建议和文件链接仍可使用，展示情况未证。",
}
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
TERMINAL_REASON_MAPPINGS = {
    "project_binding_unavailable": (
        "interactive_entry_blocked",
        "preflight",
        {"unverified"},
        "当前任务没有可验证的目标工程绑定。",
    ),
    "git_worktree_ineligible": (
        "interactive_entry_blocked",
        "preflight",
        {"unverified"},
        "当前目标不是可投影到隔离执行快照的 Git 工程。",
    ),
    "worktree_projection_unavailable": (
        "interactive_entry_blocked",
        "preflight",
        {"unchanged", "unverified"},
        "当前宿主无法把本次调用自动投影到隔离 worktree 任务。",
    ),
    "execution_protocol_failed": (
        "failed",
        "session_census",
        {"unchanged", "unverified"},
        "复盘所需的证据获取、封存或执行流程未完成。本次复盘失败；具体原因以原生记录和未完成范围为准。",
    ),
    "read_only_violation": (
        "failed",
        "project_review",
        {"changed"},
        "复盘前后项目只读指纹不一致。",
    ),
    "privacy_or_contract_failed": (
        "failed",
        "project_review",
        {"unchanged", "unverified"},
        "项目结果或 Review Pack 未通过隐私与契约校验。",
    ),
    "output_preflight_unavailable": (
        "interactive_host_blocked",
        "preflight",
        {"unchanged", "unverified"},
        "深挖前输出根检查未通过，当前无法生成审阅文件。",
    ),
    "output_root_unavailable": (
        "interactive_host_blocked",
        "delivery",
        {"unchanged", "unverified"},
        "当前任务的输出根目录不可用，当前无法生成审阅文件。",
    ),
    "render_integrity_failed": (
        "render_integrity_failed",
        "delivery",
        {"unchanged", "unverified"},
        "Review Pack 渲染或字节守恒校验失败。",
    ),
    "output_budget_exceeded": (
        "output_budget_exceeded",
        "project_review",
        {"unchanged", "unverified"},
        "完整 Review Pack 超出当前输出预算。",
    ),
}
TERMINAL_STATUSES = {mapping[0] for mapping in TERMINAL_REASON_MAPPINGS.values()}
TERMINAL_PHASES = {mapping[1] for mapping in TERMINAL_REASON_MAPPINGS.values()}
TERMINAL_PROJECT_STATES = {state for mapping in TERMINAL_REASON_MAPPINGS.values() for state in mapping[2]}


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


def validate_terminal_result(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "terminal result must be an object")
    expected_keys = {
        "contract_version",
        "status",
        "phase",
        "reason_code",
        "project_state",
        "confirmation_eligible",
    }
    require(set(value) == expected_keys, "terminal result fields are invalid")
    require(value["contract_version"] == TERMINAL_CONTRACT, "terminal result contract is invalid")
    require(value["status"] in TERMINAL_STATUSES, "terminal result status is invalid")
    require(value["phase"] in TERMINAL_PHASES, "terminal result phase is invalid")
    require(value["reason_code"] in TERMINAL_REASON_MAPPINGS, "terminal result reason_code is invalid")
    require(value["project_state"] in TERMINAL_PROJECT_STATES, "terminal result project_state is invalid")
    require(value["confirmation_eligible"] is False, "terminal result cannot enable confirmation")
    expected_status, expected_phase, allowed_project_states, _ = TERMINAL_REASON_MAPPINGS[value["reason_code"]]
    require(value["status"] == expected_status, "terminal result status does not match reason_code")
    require(value["phase"] == expected_phase, "terminal result phase does not match reason_code")
    require(value["project_state"] in allowed_project_states, "terminal result project_state does not match reason_code")
    return value


def terminal_result_sha256(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(validate_terminal_result(value)).encode("utf-8"))


def render_terminal_receipt(value: dict[str, Any]) -> str:
    value = validate_terminal_result(value)
    return (
        "# Global Owner Scout · 未形成完整审阅包\n\n"
        f"{TERMINAL_REASON_MAPPINGS[value['reason_code']][3]} 本次未展示部分卡片，确认入口保持关闭。\n\n"
        f"终态回执：`contract={TERMINAL_CONTRACT}`；`status={value['status']}`；"
        f"`phase={value['phase']}`；`reason_code={value['reason_code']}`；"
        f"`project_state={value['project_state']}`；`confirmation_eligible=false`；"
        f"`terminal_result_sha256={terminal_result_sha256(value)}`。\n"
    )


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
    mapped = value.get("contract_version") == DELIVERY_CONTRACT
    require(set(value) == expected_keys | (VISUAL_FIELDS if mapped else set()), "delivery manifest fields are invalid")
    require(value["contract_version"] in {DELIVERY_CONTRACT, LEGACY_DELIVERY_CONTRACT}, "delivery manifest contract is invalid")
    require(value["status"] == DELIVERY_STATUS, "delivery manifest status is invalid")
    require(value["delivery_surface"] == DELIVERY_SURFACE, "delivery manifest surface is invalid")
    name_match = ARTIFACT_NAME_RE.fullmatch(value["artifact_name"]) if isinstance(value["artifact_name"], str) else None
    require(name_match is not None, "delivery artifact name is invalid")
    for field in ("artifact_sha256", "review_pack_hash", "visible_body_sha256", "delivery_manifest_sha256"):
        require(isinstance(value[field], str) and HASH_RE.fullmatch(value[field]) is not None, f"{field} is invalid")
    require(name_match.group("prefix") == value["review_pack_hash"][:16], "artifact name does not bind the Review Pack hash")
    if mapped:
        require(value["visual_name"] == f"scout-project-map-{value['review_pack_hash'][:16]}.html", "visual name does not bind the Review Pack")
        require(isinstance(value["visual_sha256"], str) and HASH_RE.fullmatch(value["visual_sha256"]) is not None, "visual SHA-256 is invalid")
        require(type(value["visual_bytes"]) is int and value["visual_bytes"] > 0, "visual bytes are invalid")
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


def artifact_manifest(data: bytes, artifact_name: str) -> dict[str, Any]:
    visible = verify_visible_output(data.decode("utf-8"), surface="interactive")
    manifest: dict[str, Any] = {
        "contract_version": DELIVERY_CONTRACT if visible["project_map_bundle"] else LEGACY_DELIVERY_CONTRACT,
        "status": DELIVERY_STATUS,
        "delivery_surface": DELIVERY_SURFACE,
        "artifact_name": artifact_name,
        "artifact_sha256": sha256_bytes(data),
        "artifact_bytes": len(data),
        **{field: visible[field] for field in (
            "review_pack_hash", "visible_body_sha256", "project_cards", "visible_cards",
            "visible_action_counts", "visible_actions", "bundle_action_count", "wrapper_count",
        )},
    }
    if visible["project_map_bundle"]:
        manifest.update(visible["project_map_bundle"]["visual"])
    manifest["delivery_manifest_sha256"] = delivery_manifest_sha256(manifest)
    return validate_delivery_manifest(manifest)


def prepare_delivery(pack: dict[str, Any], *, artifact_dir: Path, protected_roots: Iterable[Path], visual_input: Path | None = None) -> tuple[dict[str, Any], Path]:
    output_root = validate_output_root(artifact_dir, protected_roots)
    visual_text = None
    if visual_input is not None:
        require(visual_input.is_absolute() and visual_input.parent.resolve(strict=True) == output_root,
                "visual-input must be a direct child of artifact-dir")
        visual_text = safe_artifact_bytes(visual_input).decode('utf-8')
        require(bool(visual_text.strip()), "visual-input must not be empty")
        require(pack['project_result'].get('project_map') is not None, "visual-input requires bound project context")
    rendered = render_review_pack(pack, surface="interactive", visual=visual_text)
    rendered_bytes = rendered.encode("utf-8")
    visible = verify_visible_output(rendered, surface="interactive")
    artifact_name = f"global-owner-scout-review-pack-{visible['review_pack_hash'][:16]}.md"
    artifact_path = output_root / artifact_name
    if visible["project_map_bundle"]:
        from project_map import render_visual
        bundle = visible["project_map_bundle"]
        visual = (render_visual(bundle["context"], visible["review_pack_hash"]) if visual_text is None else visual_text).encode("utf-8")
        require(sha256_bytes(visual) == bundle["visual"]["visual_sha256"], "visual does not match frozen map")
        write_immutable_artifact(output_root / bundle["visual"]["visual_name"], visual)
    write_immutable_artifact(artifact_path, rendered_bytes)
    require_artifact_read_only(artifact_path)
    readback = safe_artifact_bytes(artifact_path)
    require(readback == rendered_bytes, "artifact changed after deterministic creation")
    return artifact_manifest(readback, artifact_name), artifact_path


def markdown_path(path: Path) -> str:
    return path.absolute().as_posix()


def validate_manifest_artifact(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> bytes:
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
    bundle = visible["project_map_bundle"]
    require((bundle is not None) == (manifest["contract_version"] == DELIVERY_CONTRACT), "manifest generation does not match artifact")
    if bundle:
        require(bundle["visual"] == {field: manifest[field] for field in VISUAL_FIELDS}, "visual descriptor does not match artifact")
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
    return data


def visual_result(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    if manifest["contract_version"] == LEGACY_DELIVERY_CONTRACT:
        return {"visual_status": "not_available_in_legacy_report"}
    path = root.resolve(strict=True) / manifest["visual_name"]
    try:
        require_artifact_read_only(path)
        data = safe_artifact_bytes(path)
        require(len(data) == manifest["visual_bytes"] and sha256_bytes(data) == manifest["visual_sha256"], "visual bytes differ from frozen report")
    except ContractError as exc:
        return {"visual_status": "unavailable", "visual_reason": str(exc)}
    return {"visual_status": "verified", "visual_path": markdown_path(path)}


def render_delivery_receipt(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path, outcome: str, text_only: bool = False) -> str:
    manifest = validate_delivery_manifest(manifest)
    data = validate_manifest_artifact(manifest, artifact_path=artifact_path, artifact_root=artifact_root)
    require(outcome in SURFACE_COPY, "unknown file surface outcome")
    body = data.decode("utf-8")
    brief = extract_conversation_brief(body)
    if brief is None and outcome in {"open_succeeded", "open_queued"}:
        copy = OPENED_COPY if outcome == "open_succeeded" else QUEUED_COPY
        eligible = outcome == "open_succeeded"
        return (
            "# Global Owner Scout · 完整审阅包\n\n"
            f"[打开完整审阅包](<{markdown_path(artifact_path)}>)\n\n"
            f"{copy}\n\n交付回执："
            f"`delivery_manifest_sha256={manifest['delivery_manifest_sha256']}`；"
            f"`surface_observation={outcome}`；`confirmation_eligible={str(eligible).lower()}`。\n"
        )
    if brief is None:
        brief = "原报告已校验。此历史文件没有首项摘要，可在当前对话依据原文件继续讨论；现有规则未改变。"
    eligible = outcome == "open_succeeded" and bool(verify_visible_output(body, surface="interactive")["recovery_bundle"])
    receipt = (
        "# Global Owner Scout · 复盘结论与建议\n\n"
        f"{brief}\n\n[完整依据](<{markdown_path(artifact_path)}>)\n\n"
        f"{SURFACE_COPY[outcome]}\n\n交付回执："
        f"`delivery_manifest_sha256={manifest['delivery_manifest_sha256']}`；"
        f"`surface_observation={outcome}`；`confirmation_eligible={str(eligible).lower()}`。\n"
    )
    visual = visual_result(manifest, artifact_root)
    if visual["visual_status"] == "verified" and not text_only:
        receipt += '\nvisualize' + json.dumps({"path": visual["visual_path"]}, ensure_ascii=False) + '\n'
    return receipt


def render_opened_receipt(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> str:
    return render_delivery_receipt(manifest, artifact_path=artifact_path, artifact_root=artifact_root, outcome="open_succeeded")


def render_queued_receipt(manifest: dict[str, Any], *, artifact_path: Path, artifact_root: Path) -> str:
    return render_delivery_receipt(manifest, artifact_path=artifact_path, artifact_root=artifact_root, outcome="open_queued")


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
    if not text.endswith("\n"):
        text += "\n"
    # A real final may include engineering closeout and host annotations. Only the
    # unique receipt is evidence; never choose between reports or trim its advice.
    starts = list(re.finditer(r"(?m)^# Global Owner Scout · (?:完整审阅包|复盘结论与建议)\n", text))
    ends = list(re.finditer(r"(?m)^交付回执：`delivery_manifest_sha256=[^\n]*\n", text))
    require(len(starts) == len(ends) == 1 and starts[0].start() < ends[0].start(),
            "actual task final must contain exactly one complete Delivery receipt")
    # Only the immediately following visual belongs to this receipt. Other task
    # visuals and other products' receipts are outside Scout's evidence boundary.
    following_line = text[ends[0].end():].lstrip().split("\n", 1)[0].rstrip()
    directive = None
    if following_line.startswith('visualize'):
        directive = VISUAL_DIRECTIVE_RE.fullmatch("\n" + following_line + "\n")
        require(directive is not None, "invalid native visual pointer")
        try:
            visual_pointer = json.loads(directive.group("payload"))
        except ValueError as exc:
            raise ContractError("invalid native visual pointer") from exc
    text = text[starts[0].start():ends[0].end()]
    match = FINAL_OPENED_RECEIPT_RE.fullmatch(text)
    surface_status = "surface_observed"
    confirmation_eligible = True
    if match is None:
        match = FINAL_QUEUED_RECEIPT_RE.fullmatch(text)
        surface_status = "surface_pending"
        confirmation_eligible = False
    advice = None
    if match is None:
        advice = ADVICE_RECEIPT_RE.fullmatch(text)
        match = advice
        if advice:
            surface_status = {"not_requested": "artifact_verified", "open_succeeded": "surface_observed",
                              "open_queued": "surface_pending", "open_failed": "surface_unavailable"}[advice.group("surface")]
            confirmation_eligible = advice.group("eligible") == "true"
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
    manifest = artifact_manifest(data, artifact_path.name)
    require(manifest["delivery_manifest_sha256"] == match.group("manifest"), "actual task artifact does not match Delivery receipt")
    if directive:
        require(manifest["contract_version"] == DELIVERY_CONTRACT and visual_pointer == {"path": markdown_path(root / manifest["visual_name"])}, "native visual pointer does not bind the report")
    if advice:
        expected = render_delivery_receipt(manifest, artifact_path=artifact_path, artifact_root=root, outcome=advice.group("surface"))
        expected = VISUAL_DIRECTIVE_RE.sub("", expected)
        require(text == expected, "actual task final is not an exact opened or queued Delivery receipt or verified advice receipt")
    return {
        "status": surface_status,
        "manifest": manifest,
        "delivery_manifest_sha256": manifest["delivery_manifest_sha256"],
        "artifact_sha256": manifest["artifact_sha256"],
        "artifact_bytes": manifest["artifact_bytes"],
        "project_cards": manifest["project_cards"],
        "visible_cards": manifest["visible_cards"],
        "visible_actions": manifest["visible_actions"],
        "confirmation_eligible": confirmation_eligible,
        "recovery_bundle": verify_visible_output(data.decode("utf-8"), surface="interactive")["recovery_bundle"],
        "project_map_bundle": verify_visible_output(data.decode("utf-8"), surface="interactive")["project_map_bundle"],
        **visual_result(manifest, root),
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
            assert observed["confirmation_eligible"] == (count > 0)
            queued_receipt = render_queued_receipt(manifest, artifact_path=artifact_path, artifact_root=artifact_dir)
            pending = verify_final_receipt(queued_receipt, artifact_root=artifact_dir)
            assert pending["status"] == "surface_pending"
            assert pending["visible_cards"] == count
            assert pending["confirmation_eligible"] is False
            host_enveloped = verify_final_receipt(queued_receipt + "\n", artifact_root=artifact_dir)
            assert host_enveloped == pending
            assert verify_final_receipt(queued_receipt.removesuffix("\n"), artifact_root=artifact_dir) == pending
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

        terminal = {
            "contract_version": TERMINAL_CONTRACT,
            "status": "interactive_host_blocked",
            "phase": "delivery",
            "reason_code": "output_root_unavailable",
            "project_state": "unchanged",
            "confirmation_eligible": False,
        }
        terminal_receipt = render_terminal_receipt(terminal)
        assert TERMINAL_CONTRACT in terminal_receipt
        assert terminal_result_sha256(terminal) in terminal_receipt
        assert "confirmation_eligible=false" in terminal_receipt
        tests += 1

        for reason_code, (status, phase, project_states, _) in TERMINAL_REASON_MAPPINGS.items():
            candidate = {
                "contract_version": TERMINAL_CONTRACT,
                "status": status,
                "phase": phase,
                "reason_code": reason_code,
                "project_state": sorted(project_states)[0],
                "confirmation_eligible": False,
            }
            validate_terminal_result(candidate)
            invalid = dict(candidate)
            invalid["phase"] = next(item for item in TERMINAL_PHASES if item != phase)
            try:
                validate_terminal_result(invalid)
            except ContractError:
                pass
            else:
                raise AssertionError(f"terminal mapping accepted an invalid phase for {reason_code}")
        tests += 1

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
    parser.add_argument("--render-receipt", choices=tuple(SURFACE_COPY))
    parser.add_argument("--render-terminal", action="store_true")
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
        elif args.render_terminal:
            print(render_terminal_receipt(load_stdin_json()), end="")
        elif args.render_receipt is not None:
            manifest = validate_delivery_manifest(load_stdin_json())
            if args.render_receipt == "open_failed" and args.artifact_path is None and args.artifact_root is None:
                print(render_blocked_receipt(manifest), end="")
            else:
                require(args.artifact_path is not None, "--artifact-path is required")
                require(args.artifact_root is not None, "--artifact-root is required")
                print(render_delivery_receipt(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root,
                                              outcome=args.render_receipt), end="")
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
