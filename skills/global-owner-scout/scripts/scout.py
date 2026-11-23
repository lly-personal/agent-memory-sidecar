#!/usr/bin/env python3
"""Single active command surface for Global Owner Scout helpers."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from prepare_delivery import (
    DELIVERY_CONTRACT,
    SURFACE_COPY,
    TERMINAL_CONTRACT,
    prepare_delivery,
    recover_delivery,
    render_blocked_receipt,
    render_delivery_receipt,
    render_terminal_receipt,
    validate_delivery_manifest,
    verify_final_receipt,
)
from render_review import render_review_pack
from project_map import resolve_selection
from prepare_review import prepare_review
from resolve_owner_parity import resolve
from scout_security import (
    GIT_ENV,
    GIT_ID_RE,
    git_output,
    resolve_git_path,
    safe_artifact_bytes,
    validate_output_root,
)
from utf8_stdio import configure_utf8_stdio, native_line_input
from validate_output import (
    ContractError,
    NATIVE_PROJECT_CONTRACT,
    NATIVE_REVIEW_PACK_CONTRACT,
    PROJECT_CONTRACT,
    REVIEW_PACK_CONTRACT,
    SKILL_VERSION,
    canonical_hash,
    describe_input,
    project_claim_hash,
    review_pack_hash,
    validate_project,
    validate_review_pack,
)
from verify_visible_output import verify_visible_output
from history_import import capture_native, history_output_root, import_history


PREFLIGHT_CONTRACT = "global_owner_scout_preflight_v1"
PREFLIGHT_SUMMARY_CONTRACT = "global_owner_scout_preflight_summary_v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_stdin_json(input_file: Path | None = None) -> Any:
    try:
        return json.loads(safe_artifact_bytes(input_file).decode('utf-8-sig')) if input_file else json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_preflight_summary(host: str, purpose: str) -> dict[str, Any]:
    require(host in {"codex", "pi", "claude", "antigravity"}, "unsupported host")
    require(purpose in {"review", "inspect"}, "unsupported purpose")
    native_host = host in {"pi", "claude", "antigravity"}
    project_contract = NATIVE_PROJECT_CONTRACT if native_host else PROJECT_CONTRACT
    review_pack_contract = NATIVE_REVIEW_PACK_CONTRACT if native_host else REVIEW_PACK_CONTRACT
    describe_kinds = ["native-project", "native-review"] if native_host else ["project", "review"]

    if host == "codex":
        entry_steps = ["enrollment.py inspect-project", "inspect-context", "inspect-output"]
        history_steps = ["capture-native", "import-history"] if purpose == "review" else []
    elif host == "pi":
        entry_steps = ["global_owner_scout_context", "inspect-native", "inspect-output"]
        history_steps = ["capture_current"] if purpose == "review" else []
    elif host == "antigravity":
        entry_steps = ["antigravity_native.py context", "inspect-native", "inspect-output"]
        history_steps = ["antigravity_native.py capture"] if purpose == "review" else []
    else:
        entry_steps = ["claude_native.mjs context", "inspect-native", "inspect-output"]
        history_steps = ["claude_native.mjs capture"] if purpose == "review" else []

    if purpose == "review":
        review_steps = [
            f"describe-input {describe_kinds[0]}",
            "validate-project",
            *([] if native_host else ["resolve-owner-parity"]),
            f"describe-input {describe_kinds[1]}",
            "validate-review-pack",
            *([] if native_host else ["prepare-review"]),
            "prepare-delivery",
            "render-receipt",
        ]
        purpose_rule = "fail_closed_native_history_capture"
    else:
        review_steps = [
            f"describe-input {describe_kinds[0]}",
            "validate-project",
            f"describe-input {describe_kinds[1]}",
            "validate-review-pack",
            "prepare-delivery",
            "render-receipt",
        ]
        purpose_rule = "skip_history_census_and_owner_resolution"

    return {
        "contract_version": PREFLIGHT_SUMMARY_CONTRACT,
        "skill_version": SKILL_VERSION,
        "host": host,
        "purpose": purpose,
        "project_contract": project_contract,
        "review_pack_contract": review_pack_contract,
        "delivery_contract": DELIVERY_CONTRACT,
        "terminal_contract": TERMINAL_CONTRACT,
        "describe_input_kinds": describe_kinds,
        "evidence_window_kind": "manual_30d" if purpose == "review" else "current",
        "command_order": [*entry_steps, *history_steps, *review_steps],
        "recommended_fast_path": [
            *entry_steps,
            *history_steps,
            "seal-project",
            f"seal-delivery --host {host}",
        ],
        "blocking_rules": [
            "project_binding_required",
            "explicit_external_output_root_required",
            "read_only_snapshot_invariant",
            purpose_rule,
            "terminal_v1_on_preflight_or_protocol_failure",
        ],
        "privacy_rules": [
            "no_project_writes_or_proposals",
            "no_raw_history_transcription",
            "use_python_dash_B",
            "separate_delivery_from_display_and_adoption",
        ],
    }


def inspect_git_context(cwd: Path) -> dict[str, Any]:
    cwd = cwd.resolve(strict=True)
    require(git_output(cwd, "rev-parse", "--is-inside-work-tree").strip() == b"true", "git_context_unavailable")
    repository_root = resolve_git_path(cwd, git_output(cwd, "rev-parse", "--show-toplevel"))
    head = git_output(cwd, "rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    require(GIT_ID_RE.fullmatch(head) is not None, "git_context_unavailable")
    git_dir = resolve_git_path(cwd, git_output(cwd, "rev-parse", "--git-dir"))
    common_dir = resolve_git_path(cwd, git_output(cwd, "rev-parse", "--git-common-dir"))
    untracked_hash = hashlib.sha256()
    untracked_paths = [item for item in git_output(cwd, "ls-files", "--full-name", "--others", "--exclude-standard", "-z").split(b"\0") if item]
    for raw in sorted(untracked_paths):
        relative = Path(os.fsdecode(raw))
        require(not relative.is_absolute() and ".." not in relative.parts, "git_context_unavailable")
        candidate = repository_root / relative
        try:
            observed = candidate.lstat()
        except OSError as exc:
            raise ContractError("git_context_unavailable") from exc
        untracked_hash.update(raw + b"\0" + str(stat.S_IFMT(observed.st_mode)).encode("ascii") + b"\0")
        if stat.S_ISLNK(observed.st_mode):
            untracked_hash.update(os.fsencode(os.readlink(candidate)))
        elif stat.S_ISREG(observed.st_mode):
            untracked_hash.update(candidate.read_bytes())
        untracked_hash.update(b"\0")
    snapshot: dict[str, Any] = {
        "contract_version": PREFLIGHT_CONTRACT,
        "git_repository": True,
        "execution_context": "local" if git_dir == common_dir else "linked_worktree",
        "head": head,
        "status_sha256": sha256_bytes(git_output(cwd, "status", "--porcelain=v2", "--untracked-files=all", "-z")),
        "staged_diff_sha256": sha256_bytes(git_output(cwd, "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv")),
        "unstaged_diff_sha256": sha256_bytes(git_output(cwd, "diff", "--binary", "--no-ext-diff", "--no-textconv")),
        "untracked_files_sha256": untracked_hash.hexdigest(),
    }
    snapshot["context_snapshot_sha256"] = sha256_bytes(canonical_json(snapshot))
    return snapshot


def inspect_native_context(value: Any, project_root: Path | None = None) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == {'contract_version', 'native_host', 'context'}
            and value['contract_version'] == 'global_owner_scout_native_context_v1', 'native_context_invalid')
    host, context = value['native_host'], value['context']
    require(isinstance(context, dict), 'native_context_invalid')
    if host == 'pi':
        require(set(context) == {'cwd', 'session_id', 'session', 'mode'}, 'native_context_invalid')
        header = context['session']
        require(isinstance(header, dict) and header.get('type') == 'session'
                and type(header.get('version')) is int and header['version'] == 3
                and header.get('id') == context.get('session_id') and header.get('cwd') == context.get('cwd')
                and isinstance(context['mode'], str) and context['mode'] in {'tui', 'rpc', 'json', 'print'}, 'native_context_mismatch')
    elif host == 'claude':
        if context.get('source_kind') == 'claude_skill_substitution':
            require(set(context) == {'source_kind', 'cwd', 'project_dir', 'session_id', 'skill_dir', 'plugin_root'}, 'native_context_invalid')
            require(all(isinstance(context[k], str) and Path(context[k]).is_absolute()
                        for k in ('skill_dir', 'plugin_root', 'project_dir')), 'native_context_mismatch')
            skill = Path(context['skill_dir']).resolve(strict=True)
            plugin = Path(context['plugin_root']).resolve(strict=True)
            require(skill == Path(__file__).resolve().parents[1] and skill.is_relative_to(plugin), 'native_context_skill_mismatch')
        else:
            require(context.get('type') == 'system' and context.get('subtype') == 'init', 'native_context_mismatch')
    elif host == 'antigravity':
        require(set(context) == {'source_kind', 'cwd', 'project_dir', 'session_id', 'app_data_dir'}, 'native_context_invalid')
        require(context.get('source_kind') == 'antigravity_runtime_info', 'native_context_mismatch')
        require(all(isinstance(context[k], str) and Path(context[k]).is_absolute()
                    for k in ('project_dir', 'app_data_dir')), 'native_context_mismatch')
    else:
        raise ContractError('native_context_host_unsupported')
    require(isinstance(context.get('session_id'), str) and bool(context['session_id'])
            and isinstance(context.get('cwd'), str) and Path(context['cwd']).is_absolute(), 'native_context_mismatch')
    cwd = Path(context['cwd']).resolve(strict=True)
    native_root = resolve_git_path(cwd, git_output(cwd, 'rev-parse', '--show-toplevel'))
    if context.get('source_kind') in {'claude_skill_substitution', 'antigravity_runtime_info'}:
        startup = Path(context['project_dir']).resolve(strict=True)
        require(native_root == resolve_git_path(startup, git_output(startup, 'rev-parse', '--show-toplevel')),
                'native_context_startup_execution_mismatch')
    require(project_root is None or native_root == project_root.resolve(strict=True), 'native_context_project_mismatch')
    scope = ('native_skill_substitution_git' if context.get('source_kind') == 'claude_skill_substitution'
             else 'native_runtime_info_git' if context.get('source_kind') == 'antigravity_runtime_info'
             else 'native_current_session_git')
    return dict(contract_version='global_owner_scout_native_binding_v1', native_host=host,
                project_root=str(native_root),
                source_sha256=sha256_bytes(canonical_json(value)),
                session_ref_sha256=sha256_bytes(context['session_id'].encode('utf-8')),
                binding_scope=scope, git_snapshot=inspect_git_context(native_root))


def seal_project_payload(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "project payload must be an object")
    project = copy.deepcopy(value)
    cards = project.get("project_cards")
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                if isinstance(card.get("direct_evidence"), list):
                    card["normalized_evidence_hash"] = canonical_hash(card["direct_evidence"])
                card["project_claim_hash"] = project_claim_hash(card)
    return validate_project(project)


def seal_delivery_payload(
    value: Any,
    *,
    artifact_dir: Path,
    protected_roots: list[Path],
    host: str = "codex",
    outcome: str = "not_requested",
    with_visual: bool = False,
    text_only: bool = False,
    visual_input: Path | None = None,
    selected_card_ids: list[str] | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    require(isinstance(value, dict), "review pack payload must be an object")
    require(host in {"codex", "pi", "claude", "antigravity"}, "unsupported host")
    pack = copy.deepcopy(value)
    if isinstance(pack.get("project_result"), dict):
        sealed_project = seal_project_payload(pack["project_result"])
        pack["project_result"] = sealed_project
        review_cards = pack.get("review_cards")
        project_cards = sealed_project.get("project_cards", [])
        if isinstance(review_cards, list) and len(review_cards) == len(project_cards):
            for pcard, rcard in zip(project_cards, review_cards):
                if isinstance(rcard, dict) and not rcard.get("project_claim_hash"):
                    rcard["project_claim_hash"] = pcard["project_claim_hash"]
    pack["review_pack_hash"] = review_pack_hash(pack)
    if host == "codex" and pack.get("owner_parity") is not None and pack.get("project_result", {}).get("purpose") != "inspect":
        home = codex_home
        if home is None:
            configured = os.environ.get("CODEX_HOME")
            home = Path(configured).expanduser() if configured else Path.home() / ".codex"
        pack = prepare_review(pack, codex_home=home, selected_card_ids=selected_card_ids)
    else:
        pack = validate_review_pack(pack)
    manifest, artifact_path = prepare_delivery(
        pack,
        artifact_dir=artifact_dir,
        protected_roots=protected_roots,
        visual_input=visual_input,
    )
    receipt = render_delivery_receipt(
        manifest,
        artifact_path=artifact_path,
        artifact_root=artifact_dir,
        outcome=outcome,
        text_only=text_only,
        host=host,
        with_visual=with_visual,
    )
    return {
        "status": "ok",
        "artifact_path": str(artifact_path),
        "manifest": manifest,
        "receipt": receipt,
    }


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run one active Global Owner Scout helper operation.")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser('capture-native', help='Seal one raw native return object without qualifying its source or success.')
    capture.add_argument('--artifact-dir', type=Path, required=True)
    capture.add_argument('--protected-root', action='append', type=Path, required=True)
    capture_input = capture.add_mutually_exclusive_group()
    capture_input.add_argument('--input-file', type=Path)
    capture_input.add_argument('--input-line', action='store_true', help='Receive one UTF-8 JSON line without waiting for terminal EOF.')
    history = commands.add_parser('import-history', help='Freeze native Codex, Pi, Claude or Antigravity source objects without model transcription.')
    history.add_argument('--project-root', type=Path, required=True)
    history.add_argument('--session-id', required=True)
    history.add_argument('--artifact-dir', type=Path, required=True)
    history.add_argument('--protected-root', action='append', type=Path, required=True)
    summary = commands.add_parser("preflight-summary", help="Return deterministic contract and command-order orientation without reading files or Git.")
    summary.add_argument("--host", choices=("codex", "pi", "claude", "antigravity"), default="codex")
    summary.add_argument("--purpose", choices=("review", "inspect"), default="review")
    description = commands.add_parser('describe-input')
    description.add_argument('kind', choices=('project', 'review', 'native-project', 'native-review'))
    context = commands.add_parser("inspect-context")
    context.add_argument("--project-root", type=Path, required=True)
    native = commands.add_parser('inspect-native', help='Check actual native current-session metadata against the Git root.')
    native.add_argument('--project-root', type=Path)
    output = commands.add_parser("inspect-output")
    output.add_argument("--artifact-dir", type=Path, required=True)
    output.add_argument("--protected-root", action="append", type=Path, required=True)
    commands.add_parser("validate-project")
    seal_proj = commands.add_parser("seal-project", help="Compute card hashes and validate a Project JSON payload in one step.")
    seal_proj.add_argument("--output-file", type=Path)
    commands.add_parser("validate-review-pack")
    preview = commands.add_parser("prepare-review")
    preview.add_argument("--select-card", action="append")
    commands.add_parser("resolve-owner-parity")
    render = commands.add_parser("render-review")
    render.add_argument("--surface", choices=("interactive", "scheduled"), required=True)
    visible = commands.add_parser("verify-visible")
    visible.add_argument("--surface", choices=("interactive", "scheduled"), required=True)
    prepare = commands.add_parser("prepare-delivery")
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--protected-root", action="append", type=Path, required=True)
    prepare.add_argument("--visual-input", type=Path)
    seal_deliv = commands.add_parser("seal-delivery", help="Hash, preview (Codex rule packs), validate, deliver, and render receipt in one step.")
    seal_deliv.add_argument("--artifact-dir", type=Path, required=True)
    seal_deliv.add_argument("--protected-root", action="append", type=Path, required=True)
    seal_deliv.add_argument("--host", choices=("codex", "pi", "claude", "antigravity"), default="codex")
    seal_deliv.add_argument("--outcome", choices=tuple(SURFACE_COPY), default="not_requested")
    seal_deliv.add_argument("--with-visual", action="store_true")
    seal_deliv.add_argument("--text-only", action="store_true")
    seal_deliv.add_argument("--visual-input", type=Path)
    seal_deliv.add_argument("--select-card", action="append")
    receipt = commands.add_parser("render-receipt")
    receipt.add_argument("outcome", choices=tuple(SURFACE_COPY))
    receipt.add_argument("--artifact-path", type=Path)
    receipt.add_argument("--artifact-root", type=Path)
    receipt.add_argument("--host", choices=("codex", "pi", "claude", "antigravity"), default="codex")
    receipt.add_argument("--with-visual", action="store_true")
    receipt.add_argument("--text-only", action="store_true")
    commands.add_parser("render-terminal")
    for command in ("recover-delivery", "verify-final"):
        recovery = commands.add_parser(command)
        recovery.add_argument("--artifact-root", type=Path, required=True)
        recovery.add_argument("--report-hash", help="Review Pack hash from the actual selected report, not the manifest hash.")
        recovery.add_argument("--project-root", type=Path)
        recovery.add_argument("--object", dest="selected_object")
        recovery.add_argument("--journey")
    for name in ('inspect-native', 'import-history', 'validate-project', 'seal-project', 'validate-review-pack', 'prepare-review',
                 'render-review', 'verify-visible', 'prepare-delivery', 'seal-delivery', 'render-receipt', 'render-terminal', 'recover-delivery', 'verify-final'):
        commands.choices[name].add_argument('--input-file', type=Path, help='Consume an existing UTF-8 input instead of serializing it again through stdin.')
    args = parser.parse_args()
    def load_input() -> Any:
        return load_stdin_json(args.input_file)

    try:
        if args.command == 'preflight-summary':
            print(json.dumps(build_preflight_summary(args.host, args.purpose), ensure_ascii=False, separators=(',', ':')))
        elif args.command == 'capture-native':
            if args.input_line:
                history_output_root(args.artifact_dir, args.protected_root)
                with native_line_input():
                    print('{"status":"awaiting_native_object","framing":"one_utf8_json_line"}', flush=True)
                    if os.name == 'nt' and sys.stdin.isatty():
                        # Raw console input returns CR; the text reader can wait for EOF.
                        frame = bytearray()
                        while True:
                            chunk = sys.stdin.buffer.raw.read(io.DEFAULT_BUFFER_SIZE)
                            if not chunk:
                                break
                            frame.extend(chunk)
                            if b'\r' in chunk or b'\n' in chunk:
                                break
                        value = json.loads(bytes(frame).split(b'\r', 1)[0].split(b'\n', 1)[0].decode('utf-8'))
                    else:
                        value = json.loads(sys.stdin.readline())
            else:
                value = load_input()
            print(json.dumps(capture_native(value, artifact_dir=args.artifact_dir,
                protected_roots=args.protected_root), ensure_ascii=False, separators=(',', ':')))
        elif args.command == 'import-history':
            print(json.dumps(import_history(load_input(), project_root=args.project_root, session_id=args.session_id,
                artifact_dir=args.artifact_dir, protected_roots=args.protected_root), ensure_ascii=False, separators=(',', ':')))
        elif args.command == 'describe-input':
            print(json.dumps(describe_input(args.kind), ensure_ascii=False, separators=(',', ':')))
        elif args.command == "inspect-context":
            print(json.dumps(inspect_git_context(args.project_root), separators=(",", ":")))
        elif args.command == 'inspect-native':
            print(json.dumps(inspect_native_context(load_input(), args.project_root), separators=(',', ':')))
        elif args.command == "inspect-output":
            validate_output_root(args.artifact_dir, args.protected_root)
            print(json.dumps({"status": "ok", "output_root_contained": True, "writes_performed": False}))
        elif args.command == "validate-project":
            validated = validate_project(load_input())
            result = {"status": "ok", "mode": "project_scout", "contract_version": validated["contract_version"]}
            print(json.dumps(result, separators=(",", ":")))
        elif args.command == "seal-project":
            sealed = seal_project_payload(load_input())
            serialized = json.dumps(sealed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if args.output_file is not None:
                args.output_file.write_text(serialized + "\n", encoding="utf-8")
                print(json.dumps({"status": "ok", "mode": "project_scout", "contract_version": sealed["contract_version"],
                                  "output_file": str(args.output_file)}, ensure_ascii=False, separators=(",", ":")))
            else:
                print(serialized)
        elif args.command == "validate-review-pack":
            validated = validate_review_pack(load_input())
            result = {"status": "ok", "mode": "review_pack", "contract_version": validated["contract_version"]}
            print(json.dumps(result, separators=(",", ":")))
        elif args.command == "prepare-review":
            configured = os.environ.get("CODEX_HOME")
            codex_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
            print(json.dumps(prepare_review(load_input(), codex_home=codex_home, selected_card_ids=args.select_card), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "resolve-owner-parity":
            configured = os.environ.get("CODEX_HOME")
            codex_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
            print(json.dumps(resolve(codex_home), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "render-review":
            print(render_review_pack(load_input(), surface=args.surface), end="")
        elif args.command == "verify-visible":
            text = safe_artifact_bytes(args.input_file).decode('utf-8-sig') if args.input_file else sys.stdin.read()
            print(json.dumps(verify_visible_output(text, surface=args.surface), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "prepare-delivery":
            manifest, _ = prepare_delivery(load_input(), artifact_dir=args.artifact_dir, protected_roots=args.protected_root,
                                           visual_input=args.visual_input)
            print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "seal-delivery":
            result = seal_delivery_payload(
                load_input(),
                artifact_dir=args.artifact_dir,
                protected_roots=args.protected_root,
                host=args.host,
                outcome=args.outcome,
                with_visual=args.with_visual,
                text_only=args.text_only,
                visual_input=args.visual_input,
                selected_card_ids=args.select_card,
            )
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif args.command == "render-receipt":
            manifest = validate_delivery_manifest(load_input())
            if args.outcome == "open_failed" and args.artifact_path is None and args.artifact_root is None:
                print(render_blocked_receipt(manifest), end="")
            else:
                require(args.artifact_path is not None, "--artifact-path is required")
                require(args.artifact_root is not None, "--artifact-root is required")
                print(render_delivery_receipt(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root,
                                              outcome=args.outcome, text_only=args.text_only,
                                              host=args.host, with_visual=args.with_visual), end="")
        elif args.command == "render-terminal":
            print(render_terminal_receipt(load_input()), end="")
        else:
            result = (recover_delivery(load_input(), artifact_root=args.artifact_root, report_hash=args.report_hash)
                      if args.command == "recover-delivery" else
                      verify_final_receipt(safe_artifact_bytes(args.input_file).decode('utf-8') if args.input_file else sys.stdin.read(),
                                           artifact_root=args.artifact_root, report_hash=args.report_hash))
            result["source_status"] = "not_checked"
            if args.selected_object or args.journey:
                require(result['project_map_bundle'] is not None, 'original report has no map')
                context = result['project_map_bundle']['context']
                result['selected_context'] = resolve_selection(context,
                    args.selected_object or 'project:' + context['project_key'], journey_id=args.journey)
            if args.project_root and result["project_map_bundle"]:
                try:
                    snapshot = inspect_git_context(args.project_root)
                    context = result["project_map_bundle"]["context"]
                    result["source_status"] = "unchanged" if snapshot["context_snapshot_sha256"] == context["context_snapshot_hash"] else "changed"
                except (ContractError, OSError) as exc:
                    result["source_status"] = "unavailable"
                    result["source_reason"] = str(exc)
            if 'selected_context' in result:
                result['selected_context'].update({k: result[k] for k in ('source_status', 'source_reason') if k in result})
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError, OSError, UnicodeError, ValueError) as exc:
        message = ("git_context_unavailable" if args.command == "inspect-context" else
                   "output_preflight_unavailable" if args.command == "inspect-output" else str(exc))
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
