#!/usr/bin/env python3
"""Single active command surface for Global Owner Scout helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import stat
import sys
from pathlib import Path
from typing import Any

from prepare_delivery import (
    prepare_delivery,
    render_blocked_receipt,
    render_delivery_receipt,
    SURFACE_COPY,
    render_terminal_receipt,
    validate_delivery_manifest,
    validate_output_root,
    safe_artifact_bytes,
    verify_final_receipt,
)
from render_review import render_review_pack
from project_map import resolve_selection
from prepare_review import prepare_review
from resolve_owner_parity import resolve
from utf8_stdio import configure_utf8_stdio
from validate_output import ContractError, validate_project, validate_review_pack, describe_input
from verify_visible_output import verify_visible_output
from history_import import import_history


PREFLIGHT_CONTRACT = "global_owner_scout_preflight_v1"
GIT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")
GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}


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


def git_output(cwd: Path, *args: str) -> bytes:
    env = os.environ.copy()
    env.update(GIT_ENV)
    # Windows executable lookup includes cwd; never execute a reviewed project's
    # git.exe (or a PATH entry/symlink into that checkout) during read-only probes.
    workspace = cwd.resolve(strict=True)
    for ancestor in (workspace, *workspace.parents):
        try:
            (ancestor / '.git').lstat()
        except FileNotFoundError:
            continue
        workspace = ancestor
        break
    executable = None
    for directory in os.get_exec_path():
        folder = Path(directory.strip('"') if os.name == 'nt' else directory)
        if not folder.is_absolute():
            continue
        try:
            candidate = (folder / ('git.exe' if os.name == 'nt' else 'git')).resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError):
            continue
        if not candidate.is_relative_to(workspace) and candidate.is_file() and os.access(candidate, os.X_OK):
            executable = str(candidate)
            break
    require(executable is not None, 'git_context_executable_unavailable')
    try:
        result = subprocess.run(
            [executable, "--no-pager", "-c", "core.fsmonitor=false", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        raise ContractError("git_context_unavailable") from exc
    require(result.returncode == 0, "git_context_unavailable")
    return result.stdout


def resolve_git_path(cwd: Path, value: bytes) -> Path:
    text = value.decode("utf-8", errors="strict").strip()
    require(bool(text), "git_context_unavailable")
    candidate = Path(text)
    return (candidate if candidate.is_absolute() else cwd / candidate).resolve(strict=True)


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
        require(context.get('type') == 'system' and context.get('subtype') == 'init', 'native_context_mismatch')
    else:
        raise ContractError('native_context_host_unsupported')
    require(isinstance(context.get('session_id'), str) and bool(context['session_id'])
            and isinstance(context.get('cwd'), str) and Path(context['cwd']).is_absolute(), 'native_context_mismatch')
    cwd = Path(context['cwd']).resolve(strict=True)
    native_root = resolve_git_path(cwd, git_output(cwd, 'rev-parse', '--show-toplevel'))
    require(project_root is None or native_root == project_root.resolve(strict=True), 'native_context_project_mismatch')
    return dict(contract_version='global_owner_scout_native_binding_v1', native_host=host,
                project_root=str(native_root),
                source_sha256=sha256_bytes(canonical_json(value)),
                session_ref_sha256=sha256_bytes(context['session_id'].encode('utf-8')),
                binding_scope='native_current_session_git', git_snapshot=inspect_git_context(native_root))


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run one active Global Owner Scout helper operation.")
    commands = parser.add_subparsers(dest="command", required=True)
    history = commands.add_parser('import-history', help='Freeze native Codex, Pi or Claude source objects without model transcription.')
    history.add_argument('--project-root', type=Path, required=True)
    history.add_argument('--session-id', required=True)
    history.add_argument('--artifact-dir', type=Path, required=True)
    history.add_argument('--protected-root', action='append', type=Path, required=True)
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
    receipt = commands.add_parser("render-receipt")
    receipt.add_argument("outcome", choices=tuple(SURFACE_COPY))
    receipt.add_argument("--artifact-path", type=Path)
    receipt.add_argument("--artifact-root", type=Path)
    receipt.add_argument("--text-only", action="store_true")
    commands.add_parser("render-terminal")
    verify_final = commands.add_parser("verify-final")
    verify_final.add_argument("--artifact-root", type=Path, required=True)
    verify_final.add_argument("--project-root", type=Path)
    verify_final.add_argument("--object", dest="selected_object")
    verify_final.add_argument("--journey")
    for name in ('inspect-native', 'import-history', 'validate-project', 'validate-review-pack', 'prepare-review',
                 'render-review', 'verify-visible', 'prepare-delivery', 'render-receipt', 'render-terminal', 'verify-final'):
        commands.choices[name].add_argument('--input-file', type=Path, help='Consume an existing UTF-8 input instead of serializing it again through stdin.')
    args = parser.parse_args()
    def load_input() -> Any:
        return load_stdin_json(args.input_file)

    try:
        if args.command == 'import-history':
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
        elif args.command == "render-receipt":
            manifest = validate_delivery_manifest(load_input())
            if args.outcome == "open_failed" and args.artifact_path is None and args.artifact_root is None:
                print(render_blocked_receipt(manifest), end="")
            else:
                require(args.artifact_path is not None, "--artifact-path is required")
                require(args.artifact_root is not None, "--artifact-root is required")
                print(render_delivery_receipt(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root,
                                              outcome=args.outcome, text_only=args.text_only), end="")
        elif args.command == "render-terminal":
            print(render_terminal_receipt(load_input()), end="")
        else:
            result = verify_final_receipt(safe_artifact_bytes(args.input_file).decode('utf-8') if args.input_file else sys.stdin.read(), artifact_root=args.artifact_root)
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
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError, OSError, UnicodeError, ValueError) as exc:
        message = ("git_context_unavailable" if args.command == "inspect-context" else
                   "output_preflight_unavailable" if args.command == "inspect-output" else str(exc))
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
