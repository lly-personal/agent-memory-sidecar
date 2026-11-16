#!/usr/bin/env python3
"""Self-contained filesystem, containment, pinned-directory, and safe Git helpers for Scout."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from validate_output import ContractError

FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
GIT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")
GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
_GIT_ENV_STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def is_reparse(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_trusted_posix_root_alias(ancestor: Path, observed: os.stat_result, target: Path) -> bool:
    return bool(
        os.name == "posix"
        and stat.S_ISLNK(observed.st_mode)
        and getattr(observed, "st_uid", -1) == 0
        and ancestor.parent == Path(ancestor.anchor)
        and ancestor != target
    )


def validate_physical_directory_chain(
    value: Path,
    *,
    label: str = "directory",
    ancestor_error: str | None = None,
) -> Path:
    require(value.is_absolute(), f"{label} must be an absolute path")
    try:
        raw_stat = value.lstat()
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"{label} is unavailable: {exc}") from exc
    require(
        not value.is_symlink() and not is_reparse(raw_stat),
        f"{label} must not be a link or reparse point",
    )
    require(stat.S_ISDIR(raw_stat.st_mode), f"{label} must be an existing directory")
    for ancestor in value.parents:
        try:
            observed = ancestor.lstat()
        except OSError as exc:
            raise ContractError(ancestor_error or f"{label} is unavailable: {exc}") from exc
        if is_trusted_posix_root_alias(ancestor, observed, value):
            continue
        require(
            not ancestor.is_symlink() and not is_reparse(observed),
            ancestor_error or f"{label} ancestor must not be a link or reparse point",
        )
    return resolved


def safe_existing_directory(
    value: Path,
    *,
    label: str,
    ancestor_error: str | None = None,
) -> Path:
    return validate_physical_directory_chain(
        value,
        label=label,
        ancestor_error=ancestor_error,
    )


def validate_output_root(
    artifact_dir: Path,
    protected_roots: Iterable[Path],
    *,
    ancestor_error: str | None = None,
) -> Path:
    resolved_dir = safe_existing_directory(
        artifact_dir,
        label="artifact-dir",
        ancestor_error=ancestor_error,
    )
    roots = [
        safe_existing_directory(
            root,
            label="protected-root",
            ancestor_error=ancestor_error,
        )
        for root in protected_roots
    ]
    require(bool(roots), "at least one protected-root is required")
    for root in roots:
        require(not is_within(resolved_dir, root), "artifact-dir must be outside every protected-root")
    return resolved_dir


def is_physical_directory(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or is_reparse(value):
        return False
    for ancestor in path.parents:
        try:
            observed = ancestor.lstat()
        except OSError:
            return False
        if is_trusted_posix_root_alias(ancestor, observed, path):
            continue
        if ancestor.is_symlink() or is_reparse(observed):
            return False
    return True


def is_physical_file(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or is_reparse(value)
        or value.st_nlink != 1
    ):
        return False
    return is_physical_directory(path.parent)


def safe_artifact_bytes(path: Path) -> bytes:
    try:
        result = path.lstat()
    except OSError as exc:
        raise ContractError(f"artifact is unavailable: {exc}") from exc
    require(stat.S_ISREG(result.st_mode), "artifact must be a regular file")
    require(not path.is_symlink() and not is_reparse(result), "artifact must not be a link or reparse point")
    require(result.st_nlink == 1, "artifact must have exactly one hard link")
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    binary = getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, os.O_RDONLY | no_follow | binary)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            require(
                stat.S_ISREG(opened.st_mode)
                and not is_reparse(opened)
                and opened.st_nlink == 1
                and (opened.st_dev, opened.st_ino) == (result.st_dev, result.st_ino),
                "artifact must remain the same regular file",
            )
            return stream.read()
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError(f"artifact cannot be read: {exc}") from exc


def safe_git_executable(workspace: Path) -> str:
    # Windows executable lookup includes cwd; never execute a reviewed project's
    # git.exe (or a PATH entry/symlink into that checkout) during read-only probes.
    resolved_workspace = workspace.resolve(strict=True)
    git_root = resolved_workspace
    for ancestor in (resolved_workspace, *resolved_workspace.parents):
        try:
            (ancestor / ".git").lstat()
        except FileNotFoundError:
            continue
        git_root = ancestor
        break
    logical_root = Path(os.path.abspath(os.fspath(git_root)))
    git_name = "git.exe" if os.name == "nt" else "git"
    for directory in os.get_exec_path():
        folder = Path(directory.strip('"') if os.name == "nt" else directory)
        if not folder.is_absolute():
            continue
        raw_exe = Path(os.path.abspath(os.fspath(folder / git_name)))
        if raw_exe.is_relative_to(git_root) or raw_exe.is_relative_to(logical_root):
            continue
        try:
            resolved_dir = folder.resolve(strict=True)
            candidate = (folder / git_name).resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        if (
            resolved_dir.is_relative_to(git_root)
            or resolved_dir.is_relative_to(logical_root)
            or candidate.is_relative_to(git_root)
            or candidate.is_relative_to(logical_root)
        ):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise ContractError("git_context_executable_unavailable")


def git_output(cwd: Path, *args: str) -> bytes:
    executable = safe_git_executable(cwd)
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV_STRIP}
    env.update(GIT_ENV)
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


@contextmanager
def pinned_directory(root: Path):
    before = root.stat()
    handles = []
    descriptor = None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
    try:
        if os.name == "nt":
            # Deny WRITE and DELETE sharing: prevent rename and in-place reparse mutation.
            for directory in reversed([root, *root.parents]):
                handle = create(str(directory), 0x80000000, 0x1, None, 3, 0x02000000 | 0x00200000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                handles.append(handle)
                observed = directory.lstat()
                require(stat.S_ISDIR(observed.st_mode) and not is_reparse(observed), "history_output_changed")
        else:
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened = os.fstat(descriptor)
            require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), "history_output_changed")
        current = root.lstat()
        require(
            not is_reparse(current)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino),
            "history_output_changed",
        )
        require(root.resolve(strict=True) == root, "history_output_ancestor_changed")
        yield descriptor
        current = root.lstat()
        require(
            not is_reparse(current)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino),
            "history_output_changed",
        )
        require(root.resolve(strict=True) == root, "history_output_ancestor_changed")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.name == "nt":
            for handle in reversed(handles):
                close(handle)
