#!/usr/bin/env python3
"""Resolve and verify one immutable public Agent Memory release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


CONTRACT = "agent_memory_release_resolution_v1"
REPOSITORY = "lly-personal/agent-memory-sidecar"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
SOURCE_CONTRACT = "agent_memory_source_manifest_v1"
RELEASE_CONTRACT = "agent_memory_public_release_manifest_v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
TAG = re.compile(r"^v([0-9]+\.[0-9]+\.[0-9]+)$")
MAX_JSON = 1_048_576
MAX_PORTABLE = 67_108_864


class ResolutionError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ResolutionError(code)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _request(url: str, *, limit: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-memory-release-resolver/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            declared = response.headers.get("Content-Length")
            if declared is not None:
                require(int(declared) <= limit, "release_asset_too_large")
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = response.read(min(1_048_576, limit - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                require(size <= limit, "release_asset_too_large")
                chunks.append(chunk)
            return b"".join(chunks)
    except ResolutionError:
        raise
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ResolutionError("release_resolution_unavailable") from exc


def _get_json(url: str) -> Any:
    try:
        return json.loads(_request(url, limit=MAX_JSON))
    except json.JSONDecodeError as exc:
        raise ResolutionError("release_metadata_invalid") from exc


def _get_bytes(url: str, *, limit: int) -> bytes:
    return _request(url, limit=limit)


def normalize_tag(version: str | None) -> str | None:
    if version is None:
        return None
    value = version.strip()
    if not value.startswith("v"):
        value = "v" + value
    require(TAG.fullmatch(value) is not None, "release_version_invalid")
    return value


def _release_url(tag: str | None) -> str:
    if tag is None:
        return API_ROOT + "/releases/latest"
    return API_ROOT + "/releases/tags/" + urllib.parse.quote(tag, safe="")


def _resolve_tag_commit(tag: str) -> str:
    ref = _get_json(API_ROOT + "/git/ref/tags/" + urllib.parse.quote(tag, safe=""))
    require(isinstance(ref, dict) and isinstance(ref.get("object"), dict), "release_tag_invalid")
    current = ref["object"]
    for _ in range(5):
        kind = current.get("type")
        sha = str(current.get("sha", "")).casefold()
        require(SHA40.fullmatch(sha) is not None, "release_tag_invalid")
        if kind == "commit":
            return sha
        require(kind == "tag", "release_tag_invalid")
        tag_object = _get_json(API_ROOT + "/git/tags/" + sha)
        require(isinstance(tag_object, dict) and isinstance(tag_object.get("object"), dict), "release_tag_invalid")
        current = tag_object["object"]
    raise ResolutionError("release_tag_chain_invalid")


def _asset_map(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = release.get("assets")
    require(isinstance(assets, list), "release_assets_invalid")
    mapped: dict[str, dict[str, Any]] = {}
    for asset in assets:
        require(isinstance(asset, dict) and isinstance(asset.get("name"), str), "release_assets_invalid")
        name = asset["name"]
        require(name not in mapped, "release_asset_duplicate")
        mapped[name] = asset
    return mapped


def _download_asset(asset: dict[str, Any], *, limit: int) -> bytes:
    name = str(asset.get("name", ""))
    url = str(asset.get("browser_download_url", ""))
    expected_digest = str(asset.get("digest", "")).casefold()
    size = asset.get("size")
    require(
        url.startswith(REPOSITORY_URL + "/releases/download/")
        and expected_digest.startswith("sha256:")
        and SHA64.fullmatch(expected_digest[7:]) is not None
        and isinstance(size, int)
        and 0 <= size <= limit,
        f"release_asset_metadata_invalid:{name}",
    )
    value = _get_bytes(url, limit=limit)
    require(len(value) == size, f"release_asset_size_mismatch:{name}")
    require(digest_bytes(value) == expected_digest[7:], f"release_asset_digest_mismatch:{name}")
    return value


def _parse_checksums(value: bytes) -> dict[str, str]:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResolutionError("release_checksums_invalid") from exc
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("  ", 1)
        require(len(parts) == 2 and SHA64.fullmatch(parts[0]) is not None, "release_checksums_invalid")
        name = parts[1]
        require(
            name and name not in result and not Path(name).is_absolute() and ".." not in Path(name).parts,
            "release_checksums_invalid",
        )
        result[name] = parts[0]
    return result


def _validate_source_manifest(value: Any, *, tag: str, commit: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == {
        "contract_version", "distribution", "sidecar", "canonical_owner",
    }, "release_source_manifest_invalid")
    sidecar = value.get("sidecar")
    require(
        value.get("contract_version") == SOURCE_CONTRACT
        and value.get("distribution") == "release"
        and value.get("canonical_owner") is None
        and isinstance(sidecar, dict)
        and set(sidecar) == {"remote", "ref", "commit"}
        and str(sidecar.get("remote", "")).rstrip("/").casefold() == (REPOSITORY_URL + ".git").casefold()
        and sidecar.get("ref") == tag
        and str(sidecar.get("commit", "")).casefold() == commit,
        "release_source_manifest_invalid",
    )
    return value


def _validate_release_manifest(value: Any, *, tag: str, commit: str, checksums: dict[str, str]) -> str:
    require(
        isinstance(value, dict)
        and value.get("contract_version") == RELEASE_CONTRACT
        and value.get("status") == "public_artifact_verified"
        and isinstance(value.get("source"), dict)
        and isinstance(value.get("versions"), dict)
        and isinstance(value.get("artifacts"), list),
        "release_manifest_invalid",
    )
    source = value["source"]
    require(
        str(source.get("repository", "")).rstrip("/").casefold() == REPOSITORY_URL.casefold()
        and source.get("ref") == tag
        and str(source.get("commit", "")).casefold() == commit,
        "release_manifest_invalid",
    )
    match = TAG.fullmatch(tag)
    require(match is not None and value["versions"].get("core") == match.group(1), "release_manifest_version_invalid")
    portable_name = f"agent-memory-portable-{match.group(1)}.zip"
    artifacts: dict[str, str] = {}
    for item in value["artifacts"]:
        require(isinstance(item, dict), "release_manifest_artifact_invalid")
        name = str(item.get("path", ""))
        checksum = str(item.get("sha256", ""))
        require(name and name not in artifacts and SHA64.fullmatch(checksum) is not None, "release_manifest_artifact_invalid")
        artifacts[name] = checksum
    for name in (portable_name, "source-manifest.json"):
        require(artifacts.get(name) == checksums.get(name), "release_manifest_artifact_mismatch")
    return portable_name


def _inspect_portable(value: bytes, *, source_manifest: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "portable.zip"
        path.write_bytes(value)
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)), "release_portable_duplicate")
                for name in names:
                    relative = Path(name)
                    require(not relative.is_absolute() and ".." not in relative.parts, "release_portable_path_invalid")
                required = {
                    "source-manifest.json",
                    "plugins/agent-memory-sidecar/source-manifest.json",
                    ".agents/plugins/marketplace.json",
                    ".agents/skills/agent-memory-bootstrap-anchor/SKILL.md",
                    ".agents/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py",
                    "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/SKILL.md",
                    "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py",
                }
                require(required.issubset(names), "release_portable_content_missing")
                require(
                    json.loads(archive.read("source-manifest.json")) == source_manifest
                    and json.loads(archive.read("plugins/agent-memory-sidecar/source-manifest.json")) == source_manifest,
                    "release_portable_manifest_mismatch",
                )
                require(
                    archive.read(".agents/skills/agent-memory-bootstrap-anchor/SKILL.md")
                    == archive.read("plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/SKILL.md")
                    and
                    archive.read(".agents/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py")
                    == archive.read("plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py"),
                    "release_anchor_parity_mismatch",
                )
                marketplace = json.loads(archive.read(".agents/plugins/marketplace.json"))
                require(
                    isinstance(marketplace, dict)
                    and marketplace.get("name") == "agent-memory"
                    and isinstance(marketplace.get("plugins"), list)
                    and len(marketplace["plugins"]) == 1,
                    "release_marketplace_invalid",
                )
                entry = marketplace["plugins"][0]
                require(isinstance(entry, dict), "release_marketplace_invalid")
                source = entry.get("source")
                require(
                    entry.get("name") == "agent-memory-sidecar"
                    and entry.get("policy") == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
                    and isinstance(source, dict)
                    and set(source) == {"source", "url", "path", "ref"}
                    and source.get("source") == "git-subdir"
                    and str(source.get("url", "")).rstrip("/").casefold()
                    == str(source_manifest["sidecar"]["remote"]).rstrip("/").casefold()
                    and source.get("ref") == source_manifest["sidecar"]["ref"]
                    and source.get("path") == "./plugins/agent-memory-sidecar",
                    "release_marketplace_invalid",
                )
        except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
            raise ResolutionError("release_portable_invalid") from exc


def resolve_release(*, output: Path, version: str | None = None) -> dict[str, Any]:
    output = output.expanduser()
    require(not output.exists() and not output.is_symlink(), "release_resolution_output_exists")
    tag_requested = normalize_tag(version)
    release = _get_json(_release_url(tag_requested))
    require(isinstance(release, dict), "release_metadata_invalid")
    tag = str(release.get("tag_name", ""))
    require(TAG.fullmatch(tag) is not None, "release_tag_invalid")
    require(tag_requested is None or tag == tag_requested, "release_tag_mismatch")
    require(
        release.get("draft") is False
        and release.get("prerelease") is False
        and release.get("immutable") is True,
        "release_not_immutable_stable",
    )
    commit = _resolve_tag_commit(tag)
    assets = _asset_map(release)
    required_names = {"SHA256SUMS", "source-manifest.json", "release-manifest.json"}
    require(required_names.issubset(assets), "release_assets_incomplete")
    downloaded = {
        name: _download_asset(assets[name], limit=MAX_JSON)
        for name in required_names
    }
    checksums = _parse_checksums(downloaded["SHA256SUMS"])
    for name in ("source-manifest.json", "release-manifest.json"):
        require(checksums.get(name) == digest_bytes(downloaded[name]), f"release_checksum_mismatch:{name}")
    try:
        source_manifest = _validate_source_manifest(
            json.loads(downloaded["source-manifest.json"]), tag=tag, commit=commit,
        )
        portable_name = _validate_release_manifest(
            json.loads(downloaded["release-manifest.json"]), tag=tag, commit=commit, checksums=checksums,
        )
    except json.JSONDecodeError as exc:
        raise ResolutionError("release_manifest_invalid") from exc
    require(portable_name in assets and portable_name in checksums, "release_portable_missing")
    portable = _download_asset(assets[portable_name], limit=MAX_PORTABLE)
    require(checksums[portable_name] == digest_bytes(portable), "release_checksum_mismatch:portable")
    _inspect_portable(portable, source_manifest=source_manifest)

    output = Path(os.path.abspath(output))
    require(not output.exists() and not output.is_symlink(), "release_resolution_output_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        downloaded[portable_name] = portable
        for name, value in downloaded.items():
            (staged / name).write_bytes(value)
        result = {
            "contract_version": CONTRACT,
            "status": "verified",
            "repository": REPOSITORY,
            "tag": tag,
            "commit": commit,
            "assets": {
                name: {"sha256": digest_bytes(value), "bytes": len(value)}
                for name, value in sorted(downloaded.items())
            },
        }
        (staged / "resolution.json").write_bytes(canonical(result) + b"\n")
        require(not output.exists() and not output.is_symlink(), "release_resolution_output_exists")
        os.replace(staged, output)
        return result
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--version")
    args = parser.parse_args()
    try:
        result = resolve_release(output=Path(args.output), version=args.version)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ResolutionError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "contract_version": CONTRACT,
            "status": "error",
            "error": "release_resolution_blocked",
            "detail": str(exc),
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
