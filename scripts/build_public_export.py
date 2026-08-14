from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "specs" / "public-export-allowlist-v1.json"
CONTRACT = "public_source_export_v1"
ALLOWLIST_CONTRACT = "public_export_allowlist_v1"
SPDX = re.compile(r"^[A-Za-z0-9.+-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9().+-]+)*$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPOSITORY = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PRIVATE_PATTERNS = (
    ("windows_user_home", re.compile(r"\b[A-Za-z]:[\\/]Users[\\/](?!Public(?:[\\/]|$)|Default(?:[\\/]|$)|<user>(?:[\\/]|$))[^\\/\s\"'<>]+", re.IGNORECASE)),
    ("workspace_absolute_path", re.compile(r"\b[A-Za-z]:[\\/](?:\.?GitRepo|workspaces?)[\\/]", re.IGNORECASE)),
    ("codex_thread_uri", re.compile("codex" + r"://threads/", re.IGNORECASE)),
    ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@(?![A-Z0-9.-]+\.invalid\b)[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[ps]_[A-Za-z0-9]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
NOISE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
NOISE_SUFFIXES = {".pyc", ".pyo", ".log"}


class ExportError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ExportError(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_reparse(value: os.stat_result) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _assert_physical(root: Path, path: Path, *, regular_file: bool) -> None:
    logical_root = Path(os.path.abspath(root))
    logical = Path(os.path.abspath(path))
    try:
        relative = logical.relative_to(logical_root)
    except ValueError as exc:
        raise ExportError("public_export_path_escaped") from exc
    root_stat = logical_root.lstat()
    require(
        stat.S_ISDIR(root_stat.st_mode)
        and not stat.S_ISLNK(root_stat.st_mode)
        and not _is_reparse(root_stat),
        "public_export_root_unsafe",
    )
    cursor = logical_root
    for index, part in enumerate(relative.parts):
        cursor = cursor / part
        value = cursor.lstat()
        is_last = index == len(relative.parts) - 1
        require(not stat.S_ISLNK(value.st_mode) and not _is_reparse(value), "public_export_alias_forbidden")
        if is_last and regular_file:
            require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, "public_export_file_unsafe")
        else:
            require(stat.S_ISDIR(value.st_mode), "public_export_directory_unsafe")
    require(logical.resolve().is_relative_to(logical_root.resolve()), "public_export_path_escaped")


def git(args: list[str], root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise ExportError("public_export_git_failed")
    return result.stdout.strip()


def validate_source(*, source_commit: str, require_clean: bool = True) -> None:
    require(SHA40.fullmatch(source_commit) is not None, "public_export_source_commit_invalid")
    require(git(["rev-parse", "HEAD"]).casefold() == source_commit, "public_export_source_commit_mismatch")
    if require_clean:
        require(git(["status", "--porcelain", "--untracked-files=all"]) == "", "public_export_source_dirty")


def load_allowlist(path: Path = ALLOWLIST) -> tuple[tuple[str, ...], dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError("public_export_allowlist_invalid") from exc
    require(
        set(value) == {"contract_version", "copy", "map"}
        and value["contract_version"] == ALLOWLIST_CONTRACT,
        "public_export_allowlist_invalid",
    )
    copy = value["copy"]
    mapping = value["map"]
    require(isinstance(copy, list) and copy and len(copy) == len(set(copy)), "public_export_allowlist_invalid")
    require(isinstance(mapping, dict) and mapping, "public_export_allowlist_invalid")
    return tuple(str(item) for item in copy), {str(k): str(v) for k, v in mapping.items()}


def _safe_relative(path: Path) -> Path:
    require(not path.is_absolute() and ".." not in path.parts, "public_export_path_invalid")
    require(not any(part in NOISE_PARTS for part in path.parts), "public_export_noise_forbidden")
    require(path.suffix.casefold() not in NOISE_SUFFIXES, "public_export_noise_forbidden")
    return path


def _is_noise(path: Path) -> bool:
    return any(part in NOISE_PARTS for part in path.parts) or path.suffix.casefold() in NOISE_SUFFIXES


def _physical_tree_files(root: Path, base: Path) -> list[Path]:
    _assert_physical(root, base, regular_file=False)
    matches: list[Path] = []

    def failed(exc: OSError) -> None:
        raise ExportError(
            f"public_export_directory_unreadable:{base.relative_to(root).as_posix()}"
        ) from exc

    for current_raw, directory_names, file_names in os.walk(
        base,
        topdown=True,
        onerror=failed,
        followlinks=False,
    ):
        current = Path(current_raw)
        _assert_physical(root, current, regular_file=False)
        for name in sorted(directory_names):
            _assert_physical(root, current / name, regular_file=False)
        for name in sorted(file_names):
            candidate = current / name
            _assert_physical(root, candidate, regular_file=True)
            matches.append(candidate)
    return sorted(matches)


def _recursive_allowlist_files(root: Path, pattern: str) -> list[Path]:
    normalized = pattern.replace("\\", "/")
    require(normalized.endswith("/**"), "public_export_allowlist_invalid")
    base_text = normalized[:-3].rstrip("/")
    require(base_text not in {"", "."}, "public_export_allowlist_invalid")
    base_relative = _safe_relative(Path(base_text))
    base = root / base_relative
    require(base.exists(), f"public_export_allowlist_empty:{pattern}")
    return [
        path
        for path in _physical_tree_files(root, base)
        if not _is_noise(path.relative_to(root))
    ]


def resolve_files(root: Path = ROOT) -> dict[Path, Path]:
    _assert_physical(root, root, regular_file=False)
    patterns, mapping = load_allowlist(root / ALLOWLIST.relative_to(ROOT))
    selected: dict[Path, Path] = {}
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        require(
            "**" not in normalized_pattern or normalized_pattern.endswith("/**"),
            "public_export_allowlist_invalid",
        )
        if normalized_pattern.endswith("/**"):
            matches = _recursive_allowlist_files(root, pattern)
        else:
            matches = sorted(
                path for path in root.glob(pattern)
                if path.is_file() and not _is_noise(path.relative_to(root))
            )
        require(bool(matches), f"public_export_allowlist_empty:{pattern}")
        for source in matches:
            relative = _safe_relative(source.relative_to(root))
            _assert_physical(root, source, regular_file=True)
            selected[source] = relative
    for raw_source, raw_target in mapping.items():
        source_relative = _safe_relative(Path(raw_source))
        target_relative = _safe_relative(Path(raw_target))
        source = root / source_relative
        require(source.is_file(), f"public_export_map_missing:{raw_source}")
        _assert_physical(root, source, regular_file=True)
        require(target_relative not in selected.values(), f"public_export_map_conflict:{raw_target}")
        selected[source] = target_relative
    return selected


def scan_private_content(root: Path, *, deny_literals: tuple[str, ...] = ()) -> None:
    failures: list[str] = []
    for path in _physical_tree_files(root, root):
        relative = path.relative_to(root).as_posix()
        _assert_physical(root, path, regular_file=True)
        data = path.read_bytes()
        require(b"\x00" not in data, f"public_export_binary_forbidden:{relative}")
        text = data.decode("utf-8", errors="replace")
        for name, pattern in PRIVATE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{relative}:{name}")
        for literal in deny_literals:
            require(literal and len(literal) >= 4, "public_export_deny_literal_invalid")
            if literal.casefold() in text.casefold():
                failures.append(f"{relative}:private_literal")
    require(not failures, "public_export_privacy_failed:" + ",".join(failures))


def normalize_public_text(data: bytes, *, label: str) -> bytes:
    require(b"\x00" not in data, f"public_export_binary_forbidden:{label}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportError(f"public_export_binary_forbidden:{label}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def inject_license_metadata(pyproject: Path, expression: str) -> None:
    require(SPDX.fullmatch(expression) is not None, "public_export_license_expression_invalid")
    text = pyproject.read_text(encoding="utf-8")
    require("\nlicense = " not in text and "\nlicense-files = " not in text, "public_export_license_already_declared")
    marker = 'readme = "README.md"\n'
    require(marker in text, "public_export_pyproject_invalid")
    replacement = marker + f'license = "{expression}"\nlicense-files = ["LICENSE"]\n'
    pyproject.write_text(text.replace(marker, replacement, 1), encoding="utf-8", newline="\n")


def _github_identity(repository_url: str) -> str:
    value = repository_url.rstrip("/")
    require(GITHUB_REPOSITORY.fullmatch(value) is not None, "public_export_repository_url_invalid")
    return value.casefold()


def validate_repository_destination(*, root: Path, repository_url: str) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    current_url = str(project["urls"]["Homepage"]).rstrip("/")
    require(
        _github_identity(repository_url) != _github_identity(current_url),
        "public_export_repository_url_invalid",
    )
    return current_url


def rewrite_public_repository(*, output: Path, repository_url: str) -> None:
    public_url = repository_url.rstrip("/")
    current_url = validate_repository_destination(root=output, repository_url=public_url)
    for relative in (
        Path("pyproject.toml"),
        Path("plugins/agent-memory-sidecar/.codex-plugin/plugin.json"),
    ):
        path = output / relative
        text = path.read_text(encoding="utf-8")
        require(current_url in text, f"public_export_repository_template_missing:{relative.as_posix()}")
        path.write_text(
            text.replace(current_url, public_url),
            encoding="utf-8",
            newline="\n",
        )


def prepare_export(
    *,
    output: Path,
    source_commit: str,
    repository_url: str,
    license_expression: str,
    license_file: Path,
    require_clean: bool = True,
    root: Path = ROOT,
    deny_literals: tuple[str, ...] = (),
) -> dict[str, Any]:
    require(not output.exists(), "public_export_output_exists")
    require(license_file.is_file() and not license_file.is_symlink(), "public_export_license_missing")
    raw_license = license_file.read_bytes()
    require(raw_license, "public_export_license_invalid")
    try:
        license_bytes = normalize_public_text(raw_license, label="LICENSE")
    except ExportError as exc:
        raise ExportError("public_export_license_invalid") from exc
    if root == ROOT:
        validate_source(source_commit=source_commit, require_clean=require_clean)
    validate_repository_destination(root=root, repository_url=repository_url)
    selected = resolve_files(root)
    output.mkdir(parents=True)
    try:
        for source, relative in selected.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                normalize_public_text(source.read_bytes(), label=relative.as_posix())
            )
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        (output / "LICENSE").write_bytes(license_bytes)
        inject_license_metadata(output / "pyproject.toml", license_expression)
        rewrite_public_repository(output=output, repository_url=repository_url)
        scan_private_content(output, deny_literals=deny_literals)
        files = [
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in _physical_tree_files(output, output)
        ]
        receipt = {
            "contract_version": CONTRACT,
            "status": "public_repository_commit_required",
            "source_commit": source_commit,
            "source_snapshot_sha256": hashlib.sha256(canonical(files)).hexdigest(),
            "repository": repository_url.rstrip("/"),
            "license_expression": license_expression,
            "file_count": len(files),
            "files": files,
        }
        (output / "PUBLIC_EXPORT_RECEIPT.json").write_bytes(canonical(receipt) + b"\n")
        return receipt
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--license-expression", required=True)
    parser.add_argument("--license-file", required=True)
    parser.add_argument("--deny-literal", action="append", default=[])
    args = parser.parse_args()
    try:
        receipt = prepare_export(
            output=Path(args.output).expanduser().resolve(),
            source_commit=str(args.source_commit).casefold(),
            repository_url=args.repository_url,
            license_expression=str(args.license_expression),
            license_file=Path(args.license_file).expanduser().resolve(),
            deny_literals=tuple(args.deny_literal),
        )
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ExportError, OSError, UnicodeError) as exc:
        print(json.dumps({"contract_version": CONTRACT, "status": "public_export_blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
