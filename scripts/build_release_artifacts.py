from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "agent_memory_public_release_manifest_v1"
SOURCE_CONTRACT = "agent_memory_source_manifest_v1"
EXPORT_CONTRACT = "public_source_export_v1"
AUTHORITY_CONTRACT = "agent_memory_public_authority_v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$")
GITHUB_REPOSITORY = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
ZIP_TIME = (2020, 1, 1, 0, 0, 0)
NOISE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
NOISE_SUFFIXES = {".pyc", ".pyo", ".log"}


class ReleaseError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ReleaseError(code)


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 300,
) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            input=input_text,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReleaseError(f"release_command_timeout:{command[0]}") from exc
    require(
        len(result.stdout) <= 1_048_576 and len(result.stderr) <= 1_048_576,
        "release_command_output_too_large",
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1] if detail else ""
        raise ReleaseError(f"release_command_failed:{command[0]}:{suffix}")
    return result.stdout.strip()


def git(args: list[str], *, root: Path = ROOT) -> str:
    return run(["git", *args], cwd=root)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def version_facts(root: Path = ROOT) -> dict[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    core = str(project["version"])
    init_text = (root / "src" / "agent_memory_sidecar" / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    require(init_match is not None and init_match.group(1) == core, "release_core_version_mismatch")
    plugin = json.loads(
        (root / "plugins" / "agent-memory-sidecar" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    bootstrap_text = (
        root / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "managed_sources.py"
    ).read_text(encoding="utf-8")
    bootstrap_match = re.search(r'^BOOTSTRAP_VERSION\s*=\s*"([^"]+)"', bootstrap_text, re.MULTILINE)
    managed_scout_match = re.search(r'^SCOUT_VERSION\s*=\s*"([^"]+)"', bootstrap_text, re.MULTILINE)
    enrollment_text = (
        root / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "enrollment.py"
    ).read_text(encoding="utf-8")
    enrollment_bootstrap_match = re.search(r'^BOOTSTRAP_VERSION\s*=\s*"([^"]+)"', enrollment_text, re.MULTILINE)
    enrollment_scout_match = re.search(r'^SCOUT_VERSION\s*=\s*"([^"]+)"', enrollment_text, re.MULTILINE)
    bootstrap_skill_text = (
        root / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "SKILL.md"
    ).read_text(encoding="utf-8")
    bootstrap_skill_match = re.search(r"Skill version:\s*`([^`]+)`", bootstrap_skill_text)
    scout_text = (root / ".agents" / "skills" / "global-owner-scout" / "SKILL.md").read_text(encoding="utf-8")
    scout_match = re.search(r"Skill version:\s*`([^`]+)`", scout_text)
    require(
        all(match is not None for match in (
            bootstrap_match, managed_scout_match, enrollment_bootstrap_match,
            enrollment_scout_match, bootstrap_skill_match, scout_match,
        )),
        "release_component_version_missing",
    )
    require(
        len({bootstrap_match.group(1), enrollment_bootstrap_match.group(1), bootstrap_skill_match.group(1)}) == 1,
        "release_bootstrap_version_mismatch",
    )
    require(
        len({managed_scout_match.group(1), enrollment_scout_match.group(1), scout_match.group(1)}) == 1,
        "release_scout_version_mismatch",
    )
    facts = {
        "core": core,
        "plugin": str(plugin),
        "bootstrap": bootstrap_match.group(1),
        "scout": scout_match.group(1),
    }
    require(all(VERSION.fullmatch(value) is not None for value in facts.values()), "release_component_version_invalid")
    compatibility = (root / "COMPATIBILITY.md").read_text(encoding="utf-8")
    expected_row = f"| Unreleased public candidate | {core} | {facts['plugin']} | {facts['bootstrap']} | {facts['scout']} | v4 | 3.11–3.13 |"
    require(compatibility.count(expected_row) == 1, "release_compatibility_mismatch")
    return facts


def _repository_identity(remote: str) -> str:
    value = remote.strip().rstrip("/")
    if value.casefold().endswith(".git"):
        value = value[:-4]
    require(GITHUB_REPOSITORY.fullmatch(value) is not None, "release_origin_invalid")
    return value.casefold()


def validate_release_source(
    *,
    repository_url: str | None = None,
    source_ref: str | None = None,
    root: Path = ROOT,
) -> tuple[str, dict[str, str]]:
    commit = git(["rev-parse", "HEAD"], root=root).casefold()
    require(SHA40.fullmatch(commit) is not None, "release_source_commit_invalid")
    require(git(["status", "--porcelain", "--untracked-files=all"], root=root) == "", "release_source_dirty")
    validate_tracked_noise(root=root)
    require((root / "LICENSE").is_file(), "release_license_missing")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    require(isinstance(project.get("license"), str) and project["license"].strip(), "release_license_expression_missing")
    require(project.get("license-files") == ["LICENSE"], "release_license_files_invalid")
    versions = version_facts(root)
    if repository_url is not None or source_ref is not None:
        require(repository_url is not None and source_ref is not None, "release_source_identity_incomplete")
        require(_repository_identity(git(["remote", "get-url", "origin"], root=root)) == _repository_identity(repository_url), "release_origin_mismatch")
        require(source_ref == f"v{versions['core']}", "release_version_ref_mismatch")
        try:
            ref_commit = git(["rev-parse", "--verify", f"{source_ref}^{{commit}}"], root=root).casefold()
        except ReleaseError as exc:
            raise ReleaseError("release_source_ref_unresolved") from exc
        require(ref_commit == commit, "release_source_ref_mismatch")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        require(re.search(rf"^## {re.escape(versions['core'])}(?:\s|$)", changelog, re.MULTILINE) is not None, "release_changelog_missing")
    return commit, versions


def validate_tracked_noise(*, root: Path) -> None:
    tracked = git(["ls-files", "-z"], root=root)
    for raw in tracked.split("\0"):
        if not raw:
            continue
        relative = Path(raw)
        require(
            not any(part in NOISE_PARTS for part in relative.parts)
            and relative.suffix.casefold() not in NOISE_SUFFIXES,
            "release_tracked_noise_forbidden",
        )


def validate_export_receipt(
    *,
    root: Path,
    repository_url: str,
    require_snapshot_match: bool = True,
) -> dict[str, Any]:
    path = root / "PUBLIC_EXPORT_RECEIPT.json"
    require(path.is_file(), "release_export_receipt_missing")
    _assert_physical(root, path, regular_file=True)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("release_export_receipt_invalid") from exc
    require(
        isinstance(receipt, dict)
        and receipt.get("contract_version") == EXPORT_CONTRACT
        and receipt.get("status") == "public_repository_commit_required"
        and SHA40.fullmatch(str(receipt.get("source_commit", ""))) is not None
        and str(receipt.get("repository", "")).rstrip("/").casefold() == repository_url.rstrip("/").casefold()
        and isinstance(receipt.get("files"), list),
        "release_export_receipt_invalid",
    )
    expected: list[dict[str, Any]] = []
    for item in receipt["files"]:
        require(isinstance(item, dict) and set(item) == {"path", "bytes", "sha256"}, "release_export_receipt_invalid")
        relative = Path(str(item["path"]))
        require(
            not relative.is_absolute()
            and str(relative) not in {"", "."}
            and ".." not in relative.parts
            and isinstance(item["bytes"], int)
            and item["bytes"] >= 0
            and SHA64.fullmatch(str(item["sha256"])) is not None,
            "release_export_receipt_invalid",
        )
        if require_snapshot_match:
            file = root / relative
            _assert_physical(root, file, regular_file=True)
            require(file.stat().st_size == item["bytes"] and digest(file) == item["sha256"], "release_export_snapshot_drift")
        expected.append(item)
    require(receipt.get("file_count") == len(expected), "release_export_receipt_invalid")
    require(hashlib.sha256(canonical(expected)).hexdigest() == receipt.get("source_snapshot_sha256"), "release_export_receipt_invalid")
    listed = {str(item["path"]) for item in expected}
    require(len(listed) == len(expected), "release_export_receipt_invalid")
    if require_snapshot_match:
        tracked = set(filter(None, git(["ls-files"], root=root).splitlines()))
        require(tracked == listed | {"PUBLIC_EXPORT_RECEIPT.json"}, "release_export_snapshot_unregistered")
    return receipt


def resolve_release_authority(
    *,
    root: Path,
    repository_url: str,
    source_ref: str,
    commit: str,
) -> dict[str, Any]:
    require(SHA40.fullmatch(commit) is not None, "release_source_commit_invalid")
    marker_path = root / "PUBLIC_AUTHORITY.json"
    if not marker_path.exists():
        receipt = validate_export_receipt(root=root, repository_url=repository_url)
        return {
            "authority_epoch": "private_engineering",
            "engineering_source_commit": receipt["source_commit"],
            "initial_public_release": {
                "ref": source_ref,
                "commit": commit,
                "snapshot_sha256": receipt["source_snapshot_sha256"],
            },
            "activated_at": None,
        }

    _assert_physical(root, marker_path, regular_file=True)
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("release_authority_marker_invalid") from exc
    require(isinstance(marker, dict), "release_authority_marker_invalid")
    try:
        marker_repository = _repository_identity(str(marker.get("repository", "")))
    except ReleaseError as exc:
        raise ReleaseError("release_authority_marker_invalid") from exc
    require(
        set(marker) == {
            "contract_version",
            "status",
            "repository",
            "engineering_source_commit",
            "initial_public_release",
            "activated_at",
        }
        and marker.get("contract_version") == AUTHORITY_CONTRACT
        and marker.get("status") == "public_active"
        and marker_repository == _repository_identity(repository_url)
        and SHA40.fullmatch(str(marker.get("engineering_source_commit", ""))) is not None,
        "release_authority_marker_invalid",
    )
    initial = marker.get("initial_public_release")
    require(
        isinstance(initial, dict)
        and set(initial) == {"ref", "commit", "snapshot_sha256"}
        and SAFE_REF.fullmatch(str(initial.get("ref", ""))) is not None
        and str(initial.get("ref", "")).startswith("v")
        and ".." not in str(initial.get("ref", ""))
        and "//" not in str(initial.get("ref", ""))
        and "@{" not in str(initial.get("ref", ""))
        and not str(initial.get("ref", "")).endswith(("/", ".", ".lock"))
        and SHA40.fullmatch(str(initial.get("commit", ""))) is not None
        and SHA64.fullmatch(str(initial.get("snapshot_sha256", ""))) is not None,
        "release_authority_marker_invalid",
    )
    activated_at = str(marker.get("activated_at", ""))
    try:
        datetime.strptime(activated_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ReleaseError("release_authority_marker_invalid") from exc
    tracked = set(filter(None, git(["ls-files"], root=root).splitlines()))
    require("PUBLIC_AUTHORITY.json" in tracked, "release_authority_marker_untracked")
    try:
        initial_commit = git(["rev-parse", "--verify", f"{initial['ref']}^{{commit}}"], root=root).casefold()
    except ReleaseError as exc:
        raise ReleaseError("release_authority_initial_ref_unresolved") from exc
    require(initial_commit == initial["commit"], "release_authority_initial_ref_mismatch")
    require(initial_commit != commit, "release_authority_cutover_not_after_release")
    try:
        git(["merge-base", "--is-ancestor", initial_commit, commit], root=root)
    except ReleaseError as exc:
        raise ReleaseError("release_authority_ancestry_invalid") from exc
    receipt_path = root / "PUBLIC_EXPORT_RECEIPT.json"
    if receipt_path.exists():
        receipt = validate_export_receipt(
            root=root,
            repository_url=repository_url,
            require_snapshot_match=False,
        )
        require(
            receipt["source_commit"] == marker["engineering_source_commit"]
            and receipt["source_snapshot_sha256"] == initial["snapshot_sha256"],
            "release_authority_provenance_mismatch",
        )
    return {
        "authority_epoch": "public_active",
        "engineering_source_commit": marker["engineering_source_commit"],
        "initial_public_release": initial,
        "activated_at": activated_at,
    }


def _is_reparse(value: os.stat_result) -> bool:
    return bool(getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _assert_physical(root: Path, path: Path, *, regular_file: bool) -> None:
    logical_root = Path(os.path.abspath(root))
    logical = Path(os.path.abspath(path))
    try:
        relative = logical.relative_to(logical_root)
    except ValueError as exc:
        raise ReleaseError("release_path_escaped") from exc
    cursor = logical_root
    root_stat = cursor.lstat()
    require(stat.S_ISDIR(root_stat.st_mode) and not stat.S_ISLNK(root_stat.st_mode) and not _is_reparse(root_stat), "release_root_unsafe")
    for index, part in enumerate(relative.parts):
        cursor = cursor / part
        value = cursor.lstat()
        last = index == len(relative.parts) - 1
        require(not stat.S_ISLNK(value.st_mode) and not _is_reparse(value), "release_alias_forbidden")
        if last and regular_file:
            require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, "release_file_unsafe")
        else:
            require(stat.S_ISDIR(value.st_mode), "release_directory_unsafe")
    require(logical.resolve().is_relative_to(logical_root.resolve()), "release_path_escaped")


def _archive_files(paths: Iterable[Path], root: Path) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        _assert_physical(root, path, regular_file=path.is_file())
        if path.is_dir():
            candidates: list[Path] = []

            def failed(exc: OSError) -> None:
                raise ReleaseError("release_directory_unreadable") from exc

            for current_raw, directory_names, file_names in os.walk(
                path,
                topdown=True,
                onerror=failed,
                followlinks=False,
            ):
                current = Path(current_raw)
                _assert_physical(root, current, regular_file=False)
                retained_directories: list[str] = []
                for name in sorted(directory_names):
                    if name in NOISE_PARTS:
                        continue
                    _assert_physical(root, current / name, regular_file=False)
                    retained_directories.append(name)
                directory_names[:] = retained_directories
                candidates.extend(
                    current / name
                    for name in sorted(file_names)
                    if (current / name).suffix.casefold() not in NOISE_SUFFIXES
                )
        else:
            candidates = [path]
        for candidate in candidates:
            relative = candidate.relative_to(root)
            _assert_physical(root, candidate, regular_file=True)
            require(not any(part in NOISE_PARTS for part in relative.parts), "release_noise_forbidden")
            require(relative.suffix.casefold() not in NOISE_SUFFIXES, "release_noise_forbidden")
            files.append(candidate)
    return sorted(set(files), key=lambda item: item.relative_to(root).as_posix())


def deterministic_zip(*, output: Path, root: Path, files: Iterable[Path], generated: dict[str, bytes]) -> None:
    entries = [(path.relative_to(root).as_posix(), path.read_bytes()) for path in _archive_files(files, root)]
    entries.extend((name, data) for name, data in generated.items())
    names = [name for name, _ in entries]
    require(len(names) == len(set(names)), "release_archive_duplicate")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def _python_in_venv(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def smoke_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _python_in_venv(environment)
        run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], cwd=environment)
        output = run([str(python), "-m", "agent_memory_sidecar", "--help"], cwd=environment)
        require("agent-memory" in output and "rule" in output and "doctor" in output, "release_cli_smoke_failed")


def smoke_install_sdist(sdist: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _python_in_venv(environment)
        run([str(python), "-m", "pip", "install", "--no-deps", str(sdist)], cwd=environment)
        output = run([str(python), "-m", "agent_memory_sidecar", "--help"], cwd=environment)
        require("agent-memory" in output and "doctor" in output, "release_sdist_smoke_failed")


def inspect_core_archives(wheel: Path, sdist: Path, version: str) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        require(any(name.endswith("agent_memory_sidecar/cli.py") for name in names), "release_wheel_core_missing")
        require(not any("global-owner-scout" in name or "plugins/" in name for name in names), "release_wheel_boundary_invalid")
        metadata_name = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        require(metadata_name is not None, "release_wheel_metadata_missing")
        metadata = archive.read(metadata_name).decode("utf-8", errors="replace")
        require(f"Version: {version}" in metadata, "release_wheel_version_mismatch")
        require("License-Expression:" in metadata and "License-File: LICENSE" in metadata, "release_wheel_license_missing")
    import tarfile

    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        require(any(name.endswith("/LICENSE") for name in names), "release_sdist_license_missing")
        require(any(name.endswith("/src/agent_memory_sidecar/cli.py") for name in names), "release_sdist_core_missing")
        forbidden = ("/tests/", "/plugins/", "/.agents/", "/docs/", "/scripts/", "/specs/")
        require(not any(any(token in f"/{name}" for token in forbidden) for name in names), "release_sdist_boundary_invalid")


def build_core_archives(*, root: Path, output: Path, source_date_epoch: str) -> None:
    index = [line for line in git(["ls-files", "-s"], root=root).splitlines() if line]
    require(not any(line.startswith("120000 ") for line in index), "release_tracked_symlink_forbidden")
    tracked = [line.split("\t", 1)[1] for line in index]
    require(tracked, "release_tracked_source_missing")
    with tempfile.TemporaryDirectory() as temporary:
        build_root = Path(temporary) / "source"
        for raw in tracked:
            relative = Path(raw)
            source = root / relative
            if not source.is_file():
                continue
            _assert_physical(root, source, regular_file=True)
            target = build_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        env = dict(os.environ)
        env.update({"SOURCE_DATE_EPOCH": source_date_epoch, "PYTHONHASHSEED": "0"})
        run(
            [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(output)],
            cwd=build_root, env=env,
        )
        sdists = list(output.glob("*.tar.gz"))
        require(len(sdists) == 1, "release_sdist_count_invalid")
        normalize_sdist(sdists[0], source_date_epoch=int(source_date_epoch))


def normalize_sdist(path: Path, *, source_date_epoch: int) -> None:
    import tarfile

    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:gz") as source:
        for member in sorted(source.getmembers(), key=lambda item: item.name):
            require(member.isfile() or member.isdir(), "release_sdist_link_forbidden")
            data = source.extractfile(member).read() if member.isfile() else None
            member.mtime = source_date_epoch
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {}
            member.mode = 0o644 if member.isfile() else 0o755
            entries.append((member, data))
    temporary = path.with_name(path.name + ".normalize")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=source_date_epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for member, data in entries:
                        archive.addfile(member, io.BytesIO(data) if data is not None else None)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def tree_digest(root: Path) -> str:
    payload: list[tuple[str, str]] = []
    for path in _archive_files([root], root.parent):
        payload.append((path.relative_to(root).as_posix(), digest(path)))
    return hashlib.sha256(canonical(payload)).hexdigest()


def inspect_portable(
    *,
    portable: Path,
    source_manifest: dict[str, Any],
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        extracted = Path(temporary) / "portable"
        extracted.mkdir()
        with zipfile.ZipFile(portable) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), "release_portable_duplicate")
            for name in names:
                relative = Path(name)
                require(not relative.is_absolute() and ".." not in relative.parts, "release_portable_path_invalid")
            required = {
                "source-manifest.json",
                "plugins/agent-memory-sidecar/source-manifest.json",
                "specs/public-authority-cutover-v1.md",
                ".agents/skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py",
                ".agents/skills/agent-memory-workstation-bootstrap/scripts/enrollment.py",
                ".agents/skills/global-owner-scout/scripts/validate_output.py",
            }
            require(required.issubset(names), "release_portable_content_missing")
            require(
                json.loads(archive.read("source-manifest.json")) == source_manifest
                and json.loads(archive.read("plugins/agent-memory-sidecar/source-manifest.json")) == source_manifest,
                "release_portable_manifest_mismatch",
            )
            archive.extractall(extracted)
        managed = extracted / ".agents/skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py"
        enrollment = extracted / ".agents/skills/agent-memory-workstation-bootstrap/scripts/enrollment.py"
        run([sys.executable, "-B", str(managed), "validate-source-manifest", "--path", str(extracted / "source-manifest.json")], cwd=extracted)
        run([sys.executable, "-B", str(managed), "self-test"], cwd=extracted)
        run([sys.executable, "-B", str(enrollment), "self-test"], cwd=extracted)
        scout_scripts = extracted / ".agents/skills/global-owner-scout/scripts"
        for name in ("validate_output.py", "render_review.py", "verify_visible_output.py", "resolve_owner_parity.py"):
            run([sys.executable, "-B", str(scout_scripts / name), "--self-test"], cwd=scout_scripts)


def _spdx_package(
    *,
    name: str,
    spdx_id: str,
    version: str,
    checksum: str,
    repository_url: str,
    commit: str,
    license_expression: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "SPDXID": spdx_id,
        "versionInfo": version,
        "downloadLocation": f"{repository_url}/tree/{commit}",
        "filesAnalyzed": False,
        "checksums": [{"algorithm": "SHA256", "checksumValue": checksum}],
        "licenseConcluded": license_expression,
        "licenseDeclared": license_expression,
        "copyrightText": "NOASSERTION",
    }


def build(
    *,
    output: Path,
    repository_url: str,
    source_ref: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    require(not output.exists(), "release_output_exists")
    require(GITHUB_REPOSITORY.fullmatch(repository_url.rstrip("/")) is not None, "release_repository_url_invalid")
    require(
        SAFE_REF.fullmatch(source_ref) is not None
        and ".." not in source_ref
        and "//" not in source_ref
        and "@{" not in source_ref
        and not source_ref.endswith(("/", ".", ".lock")),
        "release_source_ref_invalid",
    )
    commit, versions = validate_release_source(
        repository_url=repository_url.rstrip("/"),
        source_ref=source_ref,
        root=root,
    )
    authority = resolve_release_authority(
        root=root,
        repository_url=repository_url.rstrip("/"),
        source_ref=source_ref,
        commit=commit,
    )
    source_date_epoch = git(["show", "-s", "--format=%ct", commit], root=root)
    output.mkdir(parents=True)
    try:
        run([sys.executable, "-B", "scripts/check_doc_links.py"], cwd=root)
        core_dir = output / "core"
        core_dir.mkdir()
        build_core_archives(root=root, output=core_dir, source_date_epoch=source_date_epoch)
        wheels = sorted(core_dir.glob("*.whl"))
        sdists = sorted(core_dir.glob("*.tar.gz"))
        require(len(wheels) == 1 and len(sdists) == 1, "release_core_artifact_count_invalid")
        wheel, sdist = wheels[0], sdists[0]
        inspect_core_archives(wheel, sdist, versions["core"])
        smoke_install(wheel)
        smoke_install_sdist(sdist)
        with tempfile.TemporaryDirectory() as temporary:
            repeat_dir = Path(temporary) / "repeat"
            repeat_dir.mkdir()
            build_core_archives(root=root, output=repeat_dir, source_date_epoch=source_date_epoch)
            repeated = sorted(repeat_dir.iterdir(), key=lambda item: item.name)
            original = sorted(core_dir.iterdir(), key=lambda item: item.name)
            require(
                [item.name for item in repeated] == [item.name for item in original]
                and [digest(item) for item in repeated] == [digest(item) for item in original],
                "release_core_not_reproducible",
            )

        source_manifest = {
            "contract_version": SOURCE_CONTRACT,
            "distribution": "release",
            "sidecar": {
                "remote": repository_url.rstrip("/") + ".git",
                "ref": source_ref,
                "commit": commit,
            },
            "canonical_owner": None,
        }
        portable = output / f"agent-memory-portable-{versions['core']}.zip"
        deterministic_zip(
            output=portable,
            root=root,
            files=[
                root / ".agents" / "skills" / "agent-memory-bootstrap-anchor",
                root / ".agents" / "skills" / "agent-memory-workstation-bootstrap",
                root / ".agents" / "skills" / "global-owner-scout",
                root / "plugins" / "agent-memory-sidecar",
                root / "docs" / "specs",
                root / "specs" / "agent-memory-core-v1.md",
                root / "specs" / "public-distribution-v1.md",
                root / "specs" / "public-authority-cutover-v1.md",
                root / "COMPATIBILITY.md",
                root / "LICENSE",
            ],
            generated={
                "source-manifest.json": canonical(source_manifest) + b"\n",
                "plugins/agent-memory-sidecar/source-manifest.json": canonical(source_manifest) + b"\n",
                f"core/{wheel.name}": wheel.read_bytes(),
                f"core/{sdist.name}": sdist.read_bytes(),
            },
        )
        inspect_portable(portable=portable, source_manifest=source_manifest)

        license_expression = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["license"]
        repository = repository_url.rstrip("/")
        created = datetime.fromtimestamp(int(source_date_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"agent-memory-sidecar-{versions['core']}",
            "documentNamespace": f"{repository}/releases/{source_ref}/{commit}/sbom",
            "creationInfo": {"created": created, "creators": ["Tool: agent-memory-release-builder"]},
            "packages": [
                _spdx_package(name="agent-memory-portable", spdx_id="SPDXRef-Package-Portable", version=versions["core"], checksum=digest(portable), repository_url=repository, commit=commit, license_expression=license_expression),
                _spdx_package(name="agent-memory-sidecar", spdx_id="SPDXRef-Package-Core", version=versions["core"], checksum=digest(wheel), repository_url=repository, commit=commit, license_expression=license_expression),
                _spdx_package(name="agent-memory-plugin", spdx_id="SPDXRef-Package-Plugin", version=versions["plugin"], checksum=tree_digest(root / "plugins/agent-memory-sidecar"), repository_url=repository, commit=commit, license_expression=license_expression),
                _spdx_package(name="agent-memory-bootstrap", spdx_id="SPDXRef-Package-Bootstrap", version=versions["bootstrap"], checksum=tree_digest(root / ".agents/skills/agent-memory-workstation-bootstrap"), repository_url=repository, commit=commit, license_expression=license_expression),
                _spdx_package(name="global-owner-scout", spdx_id="SPDXRef-Package-Scout", version=versions["scout"], checksum=tree_digest(root / ".agents/skills/global-owner-scout"), repository_url=repository, commit=commit, license_expression=license_expression),
            ],
            "relationships": [
                {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-Portable"},
                *[
                    {"spdxElementId": "SPDXRef-Package-Portable", "relationshipType": "CONTAINS", "relatedSpdxElement": child}
                    for child in ("SPDXRef-Package-Core", "SPDXRef-Package-Plugin", "SPDXRef-Package-Bootstrap", "SPDXRef-Package-Scout")
                ],
            ],
        }
        sbom_path = output / "agent-memory-sidecar.spdx.json"
        sbom_path.write_bytes(canonical(sbom) + b"\n")
        source_manifest_path = output / "source-manifest.json"
        source_manifest_path.write_bytes(canonical(source_manifest) + b"\n")

        artifact_paths = [wheel, sdist, portable, sbom_path, source_manifest_path]
        artifacts = [
            {"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
            for path in sorted(artifact_paths, key=lambda item: item.relative_to(output).as_posix())
        ]
        manifest = {
            "contract_version": CONTRACT,
            "status": "public_artifact_verified",
            "source": {
                "repository": repository_url.rstrip("/"),
                "ref": source_ref,
                "commit": commit,
                "authority_epoch": authority["authority_epoch"],
                "engineering_source_commit": authority["engineering_source_commit"],
                "initial_public_release": authority["initial_public_release"],
                "authority_activated_at": authority["activated_at"],
            },
            "versions": versions,
            "artifacts": artifacts,
            "verification": {
                "core_archive_inspected": True,
                "wheel_clean_install": True,
                "sdist_clean_install": True,
                "core_reproducible_rebuild": True,
                "portable_archive_inspected": True,
                "source_manifest_validated": True,
                "engineering_authority_verified": True,
                "skill_self_tests": True,
                "document_links": True,
            },
        }
        manifest_path = output / "release-manifest.json"
        manifest_path.write_bytes(canonical(manifest) + b"\n")
        checksum_paths = [*artifact_paths, manifest_path]
        (output / "SHA256SUMS").write_text(
            "".join(f"{digest(path)}  {path.relative_to(output).as_posix()}\n" for path in checksum_paths),
            encoding="utf-8",
            newline="\n",
        )
        return manifest
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args()
    try:
        manifest = build(
            output=Path(args.output).expanduser().resolve(),
            repository_url=args.repository_url,
            source_ref=args.source_ref,
        )
        print(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ReleaseError, OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"contract_version": CONTRACT, "status": "public_export_blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
