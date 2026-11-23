#!/usr/bin/env python3
"""Self-contained filesystem, SQLite binding, and safe Git primitives for Bootstrap."""

from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess


SHA40 = re.compile(r"^[0-9a-f]{40}$")
_GIT_ENV_STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


class BootstrapError(ValueError):
    pass


def logical_absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def is_reparse(value: os.stat_result) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def is_trusted_host_directory_alias(
    path: Path,
    value: os.stat_result,
    *,
    platform: str | None = None,
) -> bool:
    platform = os.name if platform is None else platform
    logical = Path(path)
    return bool(
        platform == "posix"
        and stat.S_ISLNK(value.st_mode)
        and getattr(value, "st_uid", -1) == 0
        and logical.parent == Path(logical.anchor)
    )


def validate_physical_directory_chain(
    path: Path | str,
    *,
    allow_missing_tail: bool = False,
    error_code: str = "managed_directory_alias_forbidden",
    error_cls: type[Exception] = BootstrapError,
) -> os.stat_result | None:
    logical = logical_absolute(path)
    cursor = Path(logical.anchor)
    value: os.stat_result | None = None
    if not logical.parts[1:]:
        try:
            value = cursor.lstat()
        except OSError as exc:
            raise error_cls(error_code) from exc
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or is_reparse(value):
            raise error_cls(error_code)
        return value
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except FileNotFoundError as exc:
            if allow_missing_tail:
                return None
            raise error_cls(error_code) from exc
        except OSError as exc:
            raise error_cls(error_code) from exc
        alias = stat.S_ISLNK(value.st_mode) or is_reparse(value)
        if alias and is_trusted_host_directory_alias(cursor, value):
            try:
                resolved_value = cursor.resolve(strict=True).stat()
            except OSError as exc:
                raise error_cls(error_code) from exc
            if not stat.S_ISDIR(resolved_value.st_mode):
                raise error_cls(error_code)
            value = resolved_value
            continue
        if not stat.S_ISDIR(value.st_mode) or alias:
            raise error_cls(error_code)
    return value


def ensure_physical_directory(
    path: Path | str,
    *,
    create: bool,
    error_code: str = "managed_directory_alias_forbidden",
    error_cls: type[Exception] = BootstrapError,
) -> Path:
    logical = logical_absolute(path)
    validate_physical_directory_chain(
        logical,
        allow_missing_tail=True,
        error_code=error_code,
        error_cls=error_cls,
    )
    if create and not logical.exists() and not logical.is_symlink():
        try:
            logical.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise error_cls(error_code) from exc
    if not logical.exists() and not logical.is_symlink():
        if create:
            raise error_cls(error_code)
        return logical
    validate_physical_directory_chain(
        logical,
        allow_missing_tail=False,
        error_code=error_code,
        error_cls=error_cls,
    )
    return logical


def physical_regular_file(
    path: Path | str,
    *,
    allow_missing: bool = False,
    allow_missing_parent: bool | None = None,
    error_code: str = "managed_file_invalid",
    error_cls: type[Exception] = BootstrapError,
) -> os.stat_result | None:
    logical = logical_absolute(path)
    missing_parent = allow_missing if allow_missing_parent is None else allow_missing_parent
    parent_stat = validate_physical_directory_chain(
        logical.parent,
        allow_missing_tail=missing_parent,
        error_code=error_code,
        error_cls=error_cls,
    )
    if parent_stat is None:
        return None
    try:
        value = logical.lstat()
    except FileNotFoundError as exc:
        if allow_missing:
            return None
        raise error_cls(error_code) from exc
    except OSError as exc:
        raise error_cls(error_code) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or is_reparse(value)
        or value.st_nlink != 1
    ):
        raise error_cls(error_code)
    return value


def physical_file_bytes(
    path: Path | str,
    code: str,
    *,
    limit: int = 1_048_576,
    error_cls: type[Exception] = BootstrapError,
) -> bytes:
    logical = logical_absolute(path)
    before = physical_regular_file(
        logical,
        allow_missing=False,
        allow_missing_parent=False,
        error_code=code,
        error_cls=error_cls,
    )
    assert before is not None
    if not (0 < before.st_size <= limit):
        raise error_cls(code)
    try:
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        binary = getattr(os, "O_BINARY", 0)
        fd = os.open(logical, os.O_RDONLY | no_follow | binary)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise error_cls(code)
            data = handle.read(limit + 1)
    except error_cls:
        raise
    except OSError as exc:
        raise error_cls(code) from exc
    if len(data) != before.st_size or len(data) > limit:
        raise error_cls(code)
    return data


def safe_git_executable(workspace: Path | str | None = None) -> str | None:
    resolved_workspace: Path | None = None
    if workspace is not None:
        try:
            candidate_ws = logical_absolute(workspace).resolve(strict=True)
            for ancestor in (candidate_ws, *candidate_ws.parents):
                try:
                    (ancestor / ".git").lstat()
                except FileNotFoundError:
                    continue
                resolved_workspace = ancestor
                break
            else:
                resolved_workspace = candidate_ws
        except OSError:
            resolved_workspace = logical_absolute(workspace)
    git_name = "git.exe" if os.name == "nt" else "git"
    for directory in os.get_exec_path():
        folder = Path(directory.strip('"') if os.name == "nt" else directory)
        if not folder.is_absolute():
            continue
        try:
            candidate = (folder / git_name).resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        if (
            resolved_workspace is not None
            and candidate.is_relative_to(resolved_workspace)
        ):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    error_code: str = "source_git_failed",
    timeout_code: str = "source_git_timeout",
    error_cls: type[Exception] = BootstrapError,
) -> str:
    executable = safe_git_executable(workspace=cwd)
    if executable is None:
        raise error_cls(error_code)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_STRIP
    }
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    command = [executable]
    if os.name == "nt":
        command.extend(["-c", "core.longpaths=true"])
    effective_cwd = cwd
    if (
        os.name == "nt"
        and cwd is not None
        and len(os.path.abspath(os.fspath(cwd))) >= 240
    ):
        command.extend(["-C", str(cwd)])
        effective_cwd = next(
            (
                parent
                for parent in cwd.parents
                if len(os.path.abspath(os.fspath(parent))) < 240 and parent.is_dir()
            ),
            Path(cwd.anchor) if cwd.anchor else None,
        )
    command.extend(args)
    try:
        result = subprocess.run(
            command,
            cwd=effective_cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise error_cls(timeout_code) from exc
    except OSError as exc:
        raise error_cls(error_code) from exc
    if result.returncode:
        raise error_cls(error_code)
    return result.stdout.strip()


def read_global_instruction_binding(
    codex_home: Path,
    *,
    strict_commit: bool = True,
    allow_any_schema: bool = False,
    error_code: str = "source_cutover_owner_state_ambiguous",
    error_cls: type[Exception] = BootstrapError,
) -> dict[str, str] | None:
    store = logical_absolute(codex_home) / "agent-memory-sidecar" / "memory.sqlite"
    stat_result = physical_regular_file(
        store,
        allow_missing=True,
        allow_missing_parent=True,
        error_code=error_code,
        error_cls=error_cls,
    )
    if stat_result is None:
        return None
    try:
        with closing(sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='global_instruction_binding'"
            ).fetchone()
            if table is None:
                return None
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(global_instruction_binding)")
            }
            if not {"singleton", "source_root", "source_commit"}.issubset(columns):
                if allow_any_schema:
                    has_row = connection.execute(
                        "SELECT 1 FROM global_instruction_binding LIMIT 1"
                    ).fetchone()
                    return {"source_root": "", "source_commit": ""} if has_row is not None else None
                raise error_cls(error_code)
            row = connection.execute(
                "SELECT source_root, source_commit FROM global_instruction_binding WHERE singleton = 1"
            ).fetchone()
            if row is None:
                return None
            source_root = str(row[0]).strip()
            source_commit = str(row[1]).strip().casefold()
            if not source_root or (strict_commit and SHA40.fullmatch(source_commit) is None):
                raise error_cls(error_code)
            return {"source_root": source_root, "source_commit": source_commit}
    except error_cls:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise error_cls(error_code) from exc
