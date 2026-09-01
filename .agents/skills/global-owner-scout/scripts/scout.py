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
    render_opened_receipt,
    render_queued_receipt,
    render_terminal_receipt,
    validate_delivery_manifest,
    verify_final_receipt,
)
from render_review import render_review_pack
from resolve_owner_parity import resolve
from utf8_stdio import configure_utf8_stdio
from validate_output import ContractError, validate_project, validate_review_pack
from verify_visible_output import verify_visible_output


PREFLIGHT_CONTRACT = "global_owner_scout_preflight_v1"
GIT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")
GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_stdin_json() -> Any:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"stdin is not valid JSON: {exc}") from exc


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_output(cwd: Path, *args: str) -> bytes:
    env = os.environ.copy()
    env.update(GIT_ENV)
    try:
        result = subprocess.run(
            ["git", "--no-pager", "-c", "core.fsmonitor=false", *args],
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
        if stat.S_ISREG(observed.st_mode) and not candidate.is_symlink():
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


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run one active Global Owner Scout helper operation.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect-context")
    commands.add_parser("validate-project")
    commands.add_parser("validate-review-pack")
    commands.add_parser("resolve-owner-parity")
    render = commands.add_parser("render-review")
    render.add_argument("--surface", choices=("interactive", "scheduled"), required=True)
    visible = commands.add_parser("verify-visible")
    visible.add_argument("--surface", choices=("interactive", "scheduled"), required=True)
    prepare = commands.add_parser("prepare-delivery")
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--protected-root", action="append", type=Path, required=True)
    receipt = commands.add_parser("render-receipt")
    receipt.add_argument("outcome", choices=("open_succeeded", "open_queued", "open_failed"))
    receipt.add_argument("--artifact-path", type=Path)
    receipt.add_argument("--artifact-root", type=Path)
    commands.add_parser("render-terminal")
    verify_final = commands.add_parser("verify-final")
    verify_final.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "inspect-context":
            print(json.dumps(inspect_git_context(Path.cwd()), separators=(",", ":")))
        elif args.command == "validate-project":
            validated = validate_project(load_stdin_json())
            result = {"status": "ok", "mode": "project_scout", "contract_version": validated["contract_version"]}
            print(json.dumps(result, separators=(",", ":")))
        elif args.command == "validate-review-pack":
            validated = validate_review_pack(load_stdin_json())
            result = {"status": "ok", "mode": "review_pack", "contract_version": validated["contract_version"]}
            print(json.dumps(result, separators=(",", ":")))
        elif args.command == "resolve-owner-parity":
            configured = os.environ.get("CODEX_HOME")
            codex_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
            print(json.dumps(resolve(codex_home), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "render-review":
            print(render_review_pack(load_stdin_json(), surface=args.surface), end="")
        elif args.command == "verify-visible":
            print(json.dumps(verify_visible_output(sys.stdin.read(), surface=args.surface), ensure_ascii=False, separators=(",", ":")))
        elif args.command == "prepare-delivery":
            manifest, _ = prepare_delivery(load_stdin_json(), artifact_dir=args.artifact_dir, protected_roots=args.protected_root)
            print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "render-receipt":
            manifest = validate_delivery_manifest(load_stdin_json())
            if args.outcome == "open_failed":
                print(render_blocked_receipt(manifest), end="")
            else:
                require(args.artifact_path is not None, "--artifact-path is required")
                require(args.artifact_root is not None, "--artifact-root is required")
                renderer = render_opened_receipt if args.outcome == "open_succeeded" else render_queued_receipt
                print(renderer(manifest, artifact_path=args.artifact_path, artifact_root=args.artifact_root), end="")
        elif args.command == "render-terminal":
            print(render_terminal_receipt(load_stdin_json()), end="")
        else:
            print(json.dumps(verify_final_receipt(sys.stdin.read(), artifact_root=args.artifact_root), ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ContractError, AssertionError, OSError, UnicodeError, ValueError) as exc:
        message = "git_context_unavailable" if args.command == "inspect-context" else str(exc)
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
