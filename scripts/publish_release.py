from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PLAN_CONTRACT = "agent_memory_release_promotion_plan_v1"
RECEIPT_CONTRACT = "agent_memory_release_promotion_receipt_v1"
RELEASE_MANIFEST_CONTRACT = "agent_memory_public_release_manifest_v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$")
Runner = Callable[[list[str], Path], str]


class PromotionError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PromotionError(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _is_alias(path: Path) -> bool:
    value = path.lstat()
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def run(command: list[str], cwd: Path = ROOT) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise PromotionError(f"promotion_command_timeout:{command[0]}") from exc
    require(
        len(result.stdout) <= 1_048_576 and len(result.stderr) <= 1_048_576,
        "promotion_command_output_too_large",
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1] if detail else ""
        raise PromotionError(f"promotion_command_failed:{command[0]}:{suffix}")
    return result.stdout.strip()


def _json_output(runner: Runner, command: list[str], root: Path, code: str) -> Any:
    try:
        return json.loads(runner(command, root))
    except (json.JSONDecodeError, TypeError) as exc:
        raise PromotionError(code) from exc


def _normalize_repository(value: str) -> str:
    normalized = value.strip().removesuffix(".git")
    for prefix in ("https://github.com/", "git@github.com:"):
        if normalized.casefold().startswith(prefix.casefold()):
            normalized = normalized[len(prefix) :]
            break
    require(REPOSITORY.fullmatch(normalized) is not None, "promotion_repository_invalid")
    return normalized


def _release_files(asset_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    require(asset_dir.is_dir() and not _is_alias(asset_dir), "promotion_asset_directory_invalid")
    files: dict[str, Path] = {}
    relative_files: dict[str, Path] = {}
    for current, directories, names in os.walk(asset_dir, topdown=True, followlinks=False):
        current_path = Path(current)
        require(not _is_alias(current_path), "promotion_asset_alias_forbidden")
        for name in directories:
            require(not _is_alias(current_path / name), "promotion_asset_alias_forbidden")
        for name in names:
            path = current_path / name
            value = path.lstat()
            require(
                path.is_file() and not _is_alias(path) and value.st_nlink == 1,
                "promotion_asset_file_invalid",
            )
            require(path.name not in files, "promotion_asset_basename_collision")
            files[path.name] = path
            relative_files[path.relative_to(asset_dir).as_posix()] = path

    sums_path = files.get("SHA256SUMS")
    manifest_path = files.get("release-manifest.json")
    require(sums_path is not None and manifest_path is not None, "promotion_release_metadata_missing")
    expected: dict[str, str] = {}
    for raw in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        require(match is not None, "promotion_checksums_invalid")
        relative = match.group(2)
        parsed = PurePosixPath(relative)
        require(
            relative == parsed.as_posix()
            and not parsed.is_absolute()
            and all(part not in {"", ".", ".."} for part in parsed.parts)
            and relative in relative_files,
            "promotion_checksums_invalid",
        )
        name = parsed.name
        require(name not in expected, "promotion_checksums_duplicate")
        expected[name] = match.group(1)
    require(set(files) == set(expected) | {"SHA256SUMS"}, "promotion_asset_set_mismatch")
    for name, expected_digest in expected.items():
        require(digest(files[name]) == expected_digest, "promotion_local_asset_digest_mismatch")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionError("promotion_release_manifest_invalid") from exc
    require(
        isinstance(manifest, dict)
        and manifest.get("contract_version") == RELEASE_MANIFEST_CONTRACT
        and manifest.get("status") == "public_artifact_verified",
        "promotion_release_manifest_invalid",
    )
    manifest_artifacts = manifest.get("artifacts")
    require(isinstance(manifest_artifacts, list), "promotion_release_manifest_invalid")
    manifest_names: set[str] = set()
    for item in manifest_artifacts:
        require(isinstance(item, dict) and set(item) == {"path", "bytes", "sha256"}, "promotion_release_manifest_invalid")
        relative = str(item["path"])
        require(relative in relative_files, "promotion_release_manifest_asset_mismatch")
        path = relative_files[relative]
        require(
            item["bytes"] == path.stat().st_size
            and item["sha256"] == digest(path),
            "promotion_release_manifest_asset_mismatch",
        )
        manifest_names.add(PurePosixPath(relative).name)
    require(
        len(manifest_names) == len(manifest_artifacts)
        and manifest_names == set(expected) - {"release-manifest.json"},
        "promotion_release_manifest_asset_mismatch",
    )
    assets = [
        {"name": name, "bytes": path.stat().st_size, "sha256": digest(path)}
        for name, path in sorted(files.items())
    ]
    return assets, files


def _git_identity(
    *, root: Path, repository: str, tag: str, expected_commit: str, runner: Runner
) -> None:
    require(runner(["git", "status", "--porcelain", "--untracked-files=all"], root) == "", "promotion_source_dirty")
    require(runner(["git", "rev-parse", "HEAD"], root).casefold() == expected_commit, "promotion_head_mismatch")
    require(
        runner(["git", "rev-parse", "--verify", f"{tag}^{{commit}}"], root).casefold() == expected_commit,
        "promotion_tag_mismatch",
    )
    require(runner(["git", "cat-file", "-t", tag], root) == "tag", "promotion_tag_not_annotated")
    origin = _normalize_repository(runner(["git", "remote", "get-url", "origin"], root))
    require(origin.casefold() == repository.casefold(), "promotion_origin_mismatch")
    remote_main = runner(["git", "ls-remote", "origin", "refs/heads/main"], root).split()
    require(remote_main and remote_main[0].casefold() == expected_commit, "promotion_remote_main_mismatch")
    refs = runner(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"], root
    ).splitlines()
    remote_commits = {
        line.split()[0].casefold()
        for line in refs
        if line.strip() and (line.endswith("^{}") or len(refs) == 1)
    }
    require(remote_commits == {expected_commit}, "promotion_remote_tag_mismatch")


def _release_state(*, repository: str, tag: str, root: Path, runner: Runner) -> dict[str, Any]:
    state = _json_output(
        runner,
        [
            "gh", "release", "view", tag, "--repo", repository, "--json",
            "assets,isDraft,isImmutable,isPrerelease,name,publishedAt,tagName,url",
        ],
        root,
        "promotion_release_state_invalid",
    )
    require(isinstance(state, dict) and state.get("tagName") == tag, "promotion_release_state_invalid")
    return state


def _validate_remote_assets(local_assets: list[dict[str, Any]], state: dict[str, Any]) -> None:
    remote_assets: list[dict[str, Any]] = []
    for item in state.get("assets", []):
        require(isinstance(item, dict), "promotion_remote_asset_invalid")
        remote_digest = str(item.get("digest", ""))
        require(remote_digest.startswith("sha256:"), "promotion_remote_asset_digest_missing")
        require(item.get("state") == "uploaded", "promotion_remote_asset_not_uploaded")
        remote_assets.append(
            {
                "name": str(item.get("name", "")),
                "bytes": item.get("size"),
                "sha256": remote_digest.removeprefix("sha256:"),
            }
        )
    require(sorted(remote_assets, key=lambda item: item["name"]) == local_assets, "promotion_remote_asset_mismatch")


def inspect_plan(
    *,
    root: Path,
    asset_dir: Path,
    repository: str,
    tag: str,
    expected_commit: str,
    runner: Runner = run,
) -> dict[str, Any]:
    repository = _normalize_repository(repository)
    expected_commit = expected_commit.casefold()
    require(TAG.fullmatch(tag) is not None, "promotion_tag_invalid")
    require(SHA40.fullmatch(expected_commit) is not None, "promotion_expected_commit_invalid")
    local_assets, _ = _release_files(asset_dir)
    try:
        manifest = json.loads(next(path for path in asset_dir.rglob("release-manifest.json")).read_text(encoding="utf-8"))
    except (StopIteration, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionError("promotion_release_manifest_invalid") from exc
    source = manifest.get("source", {})
    require(
        isinstance(source, dict)
        and _normalize_repository(str(source.get("repository", ""))) == repository
        and source.get("ref") == tag
        and str(source.get("commit", "")).casefold() == expected_commit,
        "promotion_release_source_mismatch",
    )
    _git_identity(root=root, repository=repository, tag=tag, expected_commit=expected_commit, runner=runner)

    version = tag.removeprefix("v")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section_match = re.search(
        rf"^## {re.escape(version)}(?:\s|$)(.*?)(?=^##\s|\Z)", changelog, re.MULTILINE | re.DOTALL
    )
    require(section_match is not None, "promotion_changelog_section_missing")
    require(re.search(r"\bunreleased\b", section_match.group(1), re.IGNORECASE) is None, "promotion_stale_release_copy")

    policy = _json_output(
        runner,
        [
            "gh", "api", f"repos/{repository}/immutable-releases",
            "--header", "X-GitHub-Api-Version:2026-03-10",
        ],
        root,
        "promotion_immutable_policy_invalid",
    )
    require(isinstance(policy, dict) and policy.get("enabled") is True, "promotion_immutable_policy_disabled")
    state = _release_state(repository=repository, tag=tag, root=root, runner=runner)
    require(state.get("isDraft") is True, "promotion_release_not_draft")
    require(state.get("isImmutable") is False, "promotion_draft_already_immutable")
    require(state.get("isPrerelease") is False, "promotion_release_prerelease")
    require(state.get("publishedAt") is None, "promotion_draft_already_published")
    _validate_remote_assets(local_assets, state)

    plan: dict[str, Any] = {
        "contract_version": PLAN_CONTRACT,
        "status": "authorization_required",
        "operation": "publish_verified_draft",
        "repository": repository,
        "tag": tag,
        "source_commit": expected_commit,
        "immutable_releases_enabled": True,
        "assets": local_assets,
        "target": {"is_draft": False, "is_immutable": True},
    }
    plan["plan_hash"] = hashlib.sha256(canonical(plan)).hexdigest()
    return plan


def apply_plan(
    *,
    root: Path,
    asset_dir: Path,
    repository: str,
    tag: str,
    expected_commit: str,
    plan_hash: str,
    runner: Runner = run,
    wait: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    require(SHA64.fullmatch(plan_hash.casefold()) is not None, "promotion_plan_hash_invalid")
    plan = inspect_plan(
        root=root,
        asset_dir=asset_dir,
        repository=repository,
        tag=tag,
        expected_commit=expected_commit,
        runner=runner,
    )
    require(plan["plan_hash"] == plan_hash.casefold(), "promotion_plan_stale")
    runner(["gh", "release", "edit", tag, "--repo", repository, "--draft=false"], root)

    state: dict[str, Any] = {}
    for attempt in range(10):
        state = _release_state(repository=repository, tag=tag, root=root, runner=runner)
        if state.get("isDraft") is False and state.get("isImmutable") is True and state.get("publishedAt"):
            break
        if attempt < 9:
            wait(3)
    require(state.get("isDraft") is False, "promotion_publish_readback_draft")
    require(state.get("isImmutable") is True, "promotion_publish_readback_mutable")
    require(bool(state.get("publishedAt")), "promotion_publish_timestamp_missing")
    local_assets, files = _release_files(asset_dir)
    _validate_remote_assets(local_assets, state)
    runner(["gh", "release", "verify", tag, "--repo", repository, "--format", "json"], root)
    for name, path in sorted(files.items()):
        runner(["gh", "release", "verify-asset", tag, str(path), "--repo", repository, "--format", "json"], root)
    return {
        "contract_version": RECEIPT_CONTRACT,
        "status": "public_published",
        "repository": _normalize_repository(repository),
        "tag": tag,
        "source_commit": expected_commit.casefold(),
        "plan_hash": plan["plan_hash"],
        "published_at": state["publishedAt"],
        "release_url": state.get("url"),
        "asset_count": len(local_assets),
        "release_attestation_verified": True,
        "asset_attestations_verified": True,
        "is_draft": False,
        "is_immutable": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or apply one immutable GitHub Release promotion.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "apply"):
        current = subparsers.add_parser(command)
        current.add_argument("--asset-dir", required=True)
        current.add_argument("--repository", required=True)
        current.add_argument("--tag", required=True)
        current.add_argument("--expected-commit", required=True)
        if command == "apply":
            current.add_argument("--plan-hash", required=True)
    args = parser.parse_args()
    inputs = {
        "root": ROOT,
        "asset_dir": Path(os.path.abspath(Path(args.asset_dir).expanduser())),
        "repository": args.repository,
        "tag": args.tag,
        "expected_commit": args.expected_commit,
    }
    try:
        result = inspect_plan(**inputs) if args.command == "inspect" else apply_plan(**inputs, plan_hash=args.plan_hash)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (PromotionError, OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        print(
            json.dumps(
                {"contract_version": PLAN_CONTRACT, "status": "release_promotion_blocked", "error": str(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
