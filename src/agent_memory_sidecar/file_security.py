from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import CoreError

_LOCK_TIMEOUT_SECONDS = 5.0
_GIT_ENV_STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def logical_absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def win_long_path(path: Path | str) -> str:
    raw = os.path.abspath(os.fspath(path))
    if os.name != "nt" or raw.startswith("\\\\?\\") or len(raw) < 240:
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def remove_readonly_tree(path: Path | str) -> None:
    target = win_long_path(path)
    if not os.path.lexists(target):
        return

    def _clear_readonly(func, failed_path: str, _exc: BaseException) -> None:
        try:
            os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        func(failed_path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=_clear_readonly)
    else:
        shutil.rmtree(target, onerror=_clear_readonly)


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


def run_safe_git(
    root: Path,
    *args: str,
    cwd: Path | None = None,
    timeout: int = 60,
    error_code: str = "git_unavailable",
    error_message: str = "Git operation failed",
) -> subprocess.CompletedProcess[bytes]:
    executable = safe_git_executable(workspace=cwd or root)
    if executable is None:
        raise CoreError(error_code, error_message)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_STRIP
    }
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    command = [executable]
    if os.name == "nt":
        command.extend(["-c", "core.longpaths=true"])
    command.extend(["-C", str(root), *args])
    effective_cwd: Path | None = cwd or root
    if (
        os.name == "nt"
        and effective_cwd is not None
        and len(os.path.abspath(os.fspath(effective_cwd))) >= 240
    ):
        effective_cwd = next(
            (
                parent
                for parent in effective_cwd.parents
                if len(os.path.abspath(os.fspath(parent))) < 240 and parent.is_dir()
            ),
            Path(effective_cwd.anchor) if effective_cwd.anchor else None,
        )
    try:
        result = subprocess.run(
            command,
            cwd=effective_cwd,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoreError(error_code, error_message, git_reason="execution_error") from exc
    if result.returncode != 0:
        stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
        reason = "filename_too_long" if "Filename too long" in stderr_text else "nonzero_exit"
        raise CoreError(
            error_code,
            error_message,
            git_reason=reason,
            git_exit_code=result.returncode,
        )
    return result


@contextmanager
def hold_physical_directory(path: Path | str) -> Iterator[int | None]:
    """Hold a physical directory without changing its permissions.

    POSIX callers must use the yielded descriptor for relative operations;
    directory renames remain possible. Windows callers use paths while every
    ancestor is held against deletion or renaming. No pathname check runs on
    exit, so callers can finish recovery through the held directory.
    """

    directory = logical_absolute(path)
    if os.name == "nt":
        with _hold_windows_directory_chain(directory):
            yield None
        return

    descriptor = None
    try:
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            cursor = Path(directory.anchor)
            descriptor = os.open(cursor, flags)
            for part in directory.parts[1:]:
                cursor = cursor / part
                before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                trusted_alias = _is_trusted_host_directory_alias(cursor, before)
                if not trusted_alias and (
                    not stat.S_ISDIR(before.st_mode)
                    or _is_reparse_point(before)
                ):
                    raise CoreError(
                        "store_unsafe",
                        "held ancestor must be a physical directory",
                        path=str(cursor),
                    )
                child = os.open(
                    part,
                    flags & ~os.O_NOFOLLOW if trusted_alias else flags,
                    dir_fd=descriptor,
                )
                try:
                    opened = os.fstat(child)
                    expected = (
                        os.stat(part, dir_fd=descriptor)
                        if trusted_alias else before
                    )
                    if not stat.S_ISDIR(opened.st_mode) or (
                        opened.st_dev, opened.st_ino
                    ) != (expected.st_dev, expected.st_ino):
                        raise CoreError(
                            "store_unsafe",
                            "physical directory changed while being held",
                            path=str(cursor),
                        )
                except BaseException:
                    os.close(child)
                    raise
                os.close(descriptor)
                descriptor = child
        except OSError as exc:
            raise CoreError(
                "store_unsafe",
                "physical directory could not be held safely",
                path=str(directory),
            ) from exc
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _hold_windows_directory_chain(directory: Path) -> Iterator[None]:
    import ctypes
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handles = []
    cursor = Path(directory.anchor)
    try:
        for component in (None, *directory.parts[1:]):
            if component is not None:
                cursor = cursor / component
            # FILE_LIST_DIRECTORY participates in sharing checks; attributes-only
            # access does not pin against rename. Opening the reparse point itself
            # lets the handle check reject links and junctions.
            handle = kernel32.CreateFileW(
                win_long_path(cursor), 0x01 | 0x80, 0x01 | 0x02, None,
                3, 0x02000000 | 0x00200000, None,
            )
            if handle == ctypes.c_void_p(-1).value:
                raise CoreError(
                    "store_unsafe",
                    "physical directory could not be held safely",
                    path=str(cursor),
                    windows_error=ctypes.get_last_error(),
                )
            handles.append(handle)
            information = FileAttributeTagInfo()
            if not kernel32.GetFileInformationByHandleEx(
                handle, 9, ctypes.byref(information), ctypes.sizeof(information),
            ):
                raise CoreError(
                    "store_unsafe",
                    "held directory metadata is unavailable",
                    path=str(cursor),
                    windows_error=ctypes.get_last_error(),
                )
            if not information.FileAttributes & 0x10 or (
                information.FileAttributes & 0x400
            ):
                raise CoreError(
                    "store_unsafe",
                    "held ancestor must be a physical directory",
                    path=str(cursor),
                )
        yield
    finally:
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)


def _is_trusted_host_directory_alias(
    path: Path,
    value: os.stat_result,
    *,
    platform: str | None = None,
) -> bool:
    """Accept only OS-owned top-level POSIX directory mappings.

    macOS exposes standard writable locations through root-owned links such as
    ``/var``. Those links sit outside the user-controlled owner boundary. A
    link anywhere deeper, or any Windows reparse point, remains unsafe.
    """

    platform = os.name if platform is None else platform
    logical = Path(path)
    return bool(
        platform == "posix"
        and stat.S_ISLNK(value.st_mode)
        and getattr(value, "st_uid", -1) == 0
        and logical.parent == Path(logical.anchor)
    )


def assert_physical_directory_chain(
    path: Path | str,
    *,
    allow_missing_tail: bool = False,
    missing_code: str = "store_unsafe",
    unsafe_code: str = "store_unsafe",
    permission_denied_code: str | None = None,
    missing_message: str = "Core Store ancestor metadata is unavailable",
    unsafe_message: str = "Core Store ancestor must be a physical directory",
    unavailable_message: str = "Core Store ancestor metadata is unavailable",
) -> os.stat_result | None:
    logical = logical_absolute(path)
    cursor = Path(logical.anchor)
    value: os.stat_result | None = None
    if not logical.parts[1:]:
        try:
            value = cursor.lstat()
        except PermissionError as exc:
            raise CoreError(
                permission_denied_code or unsafe_code,
                unavailable_message,
                path=str(cursor),
            ) from exc
        except OSError as exc:
            raise CoreError(unsafe_code, unavailable_message, path=str(cursor)) from exc
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or _is_reparse_point(value):
            raise CoreError(unsafe_code, unsafe_message, path=str(cursor))
        return value
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except FileNotFoundError as exc:
            if allow_missing_tail:
                return None
            raise CoreError(missing_code, missing_message, path=str(cursor)) from exc
        except PermissionError as exc:
            raise CoreError(
                permission_denied_code or unsafe_code,
                unavailable_message,
                path=str(cursor),
            ) from exc
        except OSError as exc:
            raise CoreError(unsafe_code, unavailable_message, path=str(cursor)) from exc
        alias = stat.S_ISLNK(value.st_mode) or _is_reparse_point(value)
        if alias and _is_trusted_host_directory_alias(cursor, value):
            try:
                resolved = cursor.resolve(strict=True)
                resolved_value = resolved.stat()
            except OSError as exc:
                raise CoreError(
                    unsafe_code,
                    "trusted host directory mapping cannot be resolved",
                    path=str(cursor),
                ) from exc
            if not stat.S_ISDIR(resolved_value.st_mode):
                raise CoreError(
                    unsafe_code,
                    "trusted host directory mapping is not a directory",
                    path=str(cursor),
                )
            value = resolved_value
            continue
        if not stat.S_ISDIR(value.st_mode) or alias:
            raise CoreError(unsafe_code, unsafe_message, path=str(cursor))
    return value


def _validate_physical_directory_chain(
    path: Path, *, permission_denied_code: str | None = None
) -> None:
    assert_physical_directory_chain(
        path,
        allow_missing_tail=False,
        permission_denied_code=permission_denied_code,
    )


def assert_physical_regular_file(
    path: Path | str,
    *,
    allow_missing: bool = True,
    allow_missing_parent: bool | None = None,
    directory_fd: int | None = None,
    missing_code: str = "store_unavailable",
    missing_message: str = "Core Store does not exist",
    parent_missing_code: str | None = None,
    parent_missing_message: str = "physical parent directory does not exist",
    unsafe_code: str = "store_unsafe",
    unsafe_message: str = "file must be one regular, non-link file",
    unavailable_code: str | None = None,
    unavailable_message: str = "file metadata cannot be read",
) -> os.stat_result | None:
    logical = logical_absolute(path)
    missing_parent_allowed = allow_missing if allow_missing_parent is None else allow_missing_parent
    if directory_fd is None:
        parent = assert_physical_directory_chain(
            logical.parent,
            allow_missing_tail=missing_parent_allowed,
            missing_code=parent_missing_code or unsafe_code,
            unsafe_code=unsafe_code,
            missing_message=parent_missing_message,
            unsafe_message=unsafe_message,
            unavailable_message=unavailable_message,
        )
        if parent is None:
            return None
    try:
        value = (
            logical.lstat()
            if directory_fd is None
            else os.stat(logical.name, dir_fd=directory_fd, follow_symlinks=False)
        )
    except FileNotFoundError as exc:
        if allow_missing:
            return None
        raise CoreError(missing_code, missing_message, path=str(logical)) from exc
    except OSError as exc:
        raise CoreError(
            unavailable_code or unsafe_code,
            unavailable_message,
            path=str(logical),
        ) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_point(value)
        or value.st_nlink != 1
    ):
        raise CoreError(
            unsafe_code,
            unsafe_message,
            path=str(logical),
            link_count=value.st_nlink,
        )
    return value


def read_physical_regular_bytes(
    path: Path | str,
    *,
    directory_fd: int | None = None,
    allow_missing_parent: bool = True,
    parent_missing_code: str | None = None,
    parent_missing_message: str = "physical parent directory does not exist",
    unsafe_code: str = "store_unsafe",
    unsafe_message: str = "file must be one regular, non-link file",
    unavailable_code: str | None = None,
    unavailable_message: str = "file cannot be read",
) -> tuple[bool, bytes]:
    logical = logical_absolute(path)
    before = assert_physical_regular_file(
        logical,
        allow_missing=True,
        allow_missing_parent=allow_missing_parent,
        directory_fd=directory_fd,
        parent_missing_code=parent_missing_code,
        parent_missing_message=parent_missing_message,
        unsafe_code=unsafe_code,
        unsafe_message=unsafe_message,
        unavailable_code=unavailable_code,
        unavailable_message=unavailable_message,
    )
    if before is None:
        return False, b""
    try:
        if directory_fd is None:
            no_follow = getattr(os, "O_NOFOLLOW", 0)
            if no_follow:
                fd = os.open(logical, os.O_RDONLY | no_follow)
                handle = os.fdopen(fd, "rb")
            else:
                handle = logical.open("rb")
        else:
            no_follow = getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(logical.name, os.O_RDONLY | no_follow, dir_fd=directory_fd)
            handle = os.fdopen(fd, "rb")
        with handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise CoreError(
                    unsafe_code,
                    "file changed while it was opened",
                    path=str(logical),
                )
            data = handle.read()
    except OSError as exc:
        raise CoreError(
            unavailable_code or unsafe_code,
            unavailable_message,
            path=str(logical),
        ) from exc
    after = assert_physical_regular_file(
        logical,
        allow_missing=False,
        allow_missing_parent=False,
        directory_fd=directory_fd,
        missing_code=unsafe_code,
        missing_message="file disappeared while it was read",
        unsafe_code=unsafe_code,
        unsafe_message=unsafe_message,
        unavailable_code=unavailable_code,
        unavailable_message=unavailable_message,
    )
    assert after is not None
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        raise CoreError(
            unsafe_code,
            "file changed while it was read",
            path=str(logical),
        )
    return True, data


def acquire_file_lock(
    handle: object,
    *,
    timeout_seconds: float = _LOCK_TIMEOUT_SECONDS,
    timeout_code: str = "instruction_lock_timeout",
    timeout_message: str = "timed out waiting for instruction target lock",
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)  # type: ignore[attr-defined]
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
            return
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise CoreError(timeout_code, timeout_message) from exc
            time.sleep(0.05)


def release_file_lock(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def prepare_store_parent(path: Path | str) -> Path:
    target = logical_absolute(path)
    pending: list[Path] = []
    cursor = target.parent
    while True:
        try:
            value = cursor.lstat()
        except FileNotFoundError:
            pending.append(cursor)
            if cursor == cursor.parent:
                raise CoreError(
                    "store_unsafe",
                    "Core Store has no existing physical ancestor",
                    path=str(target),
                )
            cursor = cursor.parent
            continue
        except OSError as exc:
            raise CoreError(
                "store_unsafe",
                "Core Store ancestor metadata is unavailable",
                path=str(cursor),
            ) from exc
        alias = stat.S_ISLNK(value.st_mode) or _is_reparse_point(value)
        if alias and _is_trusted_host_directory_alias(cursor, value):
            try:
                resolved_value = cursor.resolve(strict=True).stat()
            except OSError as exc:
                raise CoreError(
                    "store_unsafe",
                    "trusted host directory mapping cannot be resolved",
                    path=str(cursor),
                ) from exc
            if not stat.S_ISDIR(resolved_value.st_mode):
                raise CoreError(
                    "store_unsafe",
                    "trusted host directory mapping is not a directory",
                    path=str(cursor),
                )
            break
        if not stat.S_ISDIR(value.st_mode) or alias:
            raise CoreError(
                "store_unsafe",
                "Core Store ancestor must be a physical directory",
                path=str(cursor),
            )
        break
    _validate_physical_directory_chain(cursor)
    for directory in reversed(pending):
        try:
            directory.mkdir()
        except OSError as exc:
            raise CoreError(
                "store_unsafe",
                "Core Store directory could not be created safely",
                path=str(directory),
            ) from exc
        value = directory.lstat()
        if (
            not stat.S_ISDIR(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or _is_reparse_point(value)
        ):
            raise CoreError(
                "store_unsafe",
                "Core Store directory became a filesystem alias",
                path=str(directory),
            )
    return target.parent


def secure_store_location(path: Path | str, *, allow_missing: bool) -> Path:
    target, file_stat = _validated_store_location(
        path,
        allow_missing=allow_missing,
    )
    parent = target.parent
    if os.name == "nt":
        _secure_windows(parent, directory=True)
        if file_stat is not None:
            _secure_windows(target, directory=False)
    else:
        os.chmod(parent, 0o700)
        if file_stat is not None:
            os.chmod(target, 0o600)
        if stat.S_IMODE(parent.lstat().st_mode) != 0o700:
            raise CoreError(
                "store_permissions_unsafe",
                "Core Store directory is not private",
                path=str(parent),
            )
        if file_stat is not None and stat.S_IMODE(target.lstat().st_mode) != 0o600:
            raise CoreError(
                "store_permissions_unsafe",
                "Core Store file is not private",
                path=str(target),
            )
    return target


def validate_store_identity(
    path: Path | str,
    *,
    allow_missing: bool,
    permission_denied_code: str | None = None,
) -> Path:
    target, _ = _validated_store_location(
        path,
        allow_missing=allow_missing,
        permission_denied_code=permission_denied_code,
    )
    return target


def _validated_store_location(
    path: Path | str,
    *,
    allow_missing: bool,
    permission_denied_code: str | None = None,
) -> tuple[Path, os.stat_result | None]:
    target = logical_absolute(path)
    parent = target.parent
    _validate_physical_directory_chain(
        parent,
        permission_denied_code=permission_denied_code,
    )

    file_stat: os.stat_result | None
    try:
        file_stat = target.lstat()
    except FileNotFoundError:
        file_stat = None
    except PermissionError as exc:
        raise CoreError(
            permission_denied_code or "store_unsafe",
            (
                "Core Store is not accessible in the current execution context"
                if permission_denied_code
                else "Core Store metadata is unavailable"
            ),
            path=str(target),
        ) from exc
    except OSError as exc:
        raise CoreError(
            "store_unsafe",
            "Core Store metadata is unavailable",
            path=str(target),
        ) from exc
    if file_stat is None:
        if not allow_missing:
            raise CoreError(
                "store_unavailable",
                "Core Store does not exist",
                path=str(target),
            )
    elif (
        not stat.S_ISREG(file_stat.st_mode)
        or stat.S_ISLNK(file_stat.st_mode)
        or _is_reparse_point(file_stat)
        or file_stat.st_nlink != 1
    ):
        raise CoreError(
            "store_unsafe",
            "Core Store must be one regular, non-link file",
            path=str(target),
            link_count=file_stat.st_nlink,
        )

    return target, file_stat


def _is_reparse_point(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _secure_windows(path: Path, *, directory: bool) -> None:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
        wintypes.BOOL
    )
    advapi32.SetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.SetFileSecurityW.restype = wintypes.BOOL
    advapi32.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetFileSecurityW.restype = wintypes.BOOL
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = (
        wintypes.BOOL
    )

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
    ):
        _windows_error("open the current user token", path)
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            1,
            buffer,
            required,
            ctypes.byref(required),
        ):
            _windows_error("read the current user SID", path)
        sid_pointer = ctypes.cast(
            buffer, ctypes.POINTER(ctypes.c_void_p)
        ).contents.value
        sid_text_pointer = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(
            sid_pointer, ctypes.byref(sid_text_pointer)
        ):
            _windows_error("format the current user SID", path)
        try:
            sid = sid_text_pointer.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text_pointer, wintypes.HLOCAL))
    finally:
        kernel32.CloseHandle(token)

    ace = "OICI;FA" if directory else ";FA"
    sddl = f"D:P(A;{ace};;;{sid})(A;{ace};;;SY)"
    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        _windows_error("create a private Store security descriptor", path)
    try:
        flags = 0x00000004 | 0x80000000
        if not advapi32.SetFileSecurityW(win_long_path(path), flags, descriptor):
            _windows_error("apply the private Store ACL", path)
    finally:
        kernel32.LocalFree(ctypes.cast(descriptor, wintypes.HLOCAL))

    actual = _windows_dacl_sddl(path, advapi32=advapi32, kernel32=kernel32)
    _validate_windows_dacl(actual, sid=sid, path=path)


def _validate_windows_dacl(actual: str, *, sid: str, path: Path) -> None:
    aliases = {
        sid.casefold(): "current_user",
        "sy": "system",
        "s-1-5-18": "system",
        "ba": "administrators",
        "s-1-5-32-544": "administrators",
    }
    # SDDL renders the built-in local Administrator account as ``LA``. It is
    # the current user only when the SID we obtained from the process token is
    # that account's well-known RID 500; group membership is not sufficient.
    if sid.rsplit("-", 1)[-1] == "500":
        aliases["la"] = "current_user"
    allowed_ace_types = {"A", "OA", "XA", "ZA"}
    granted: set[str] = set()
    invalid = "D:P" not in actual
    for raw_ace in re.findall(r"\(([^()]*)\)", actual):
        fields = raw_ace.split(";")
        if len(fields) < 6 or fields[0].upper() not in allowed_ace_types:
            continue
        principal = aliases.get(fields[5].casefold())
        if principal is None:
            invalid = True
            continue
        rights = fields[2].casefold()
        full_access = rights == "fa"
        if rights.startswith("0x"):
            try:
                full_access = int(rights, 16) == 0x1F01FF
            except ValueError:
                full_access = False
        if principal in {"current_user", "system"} and not full_access:
            invalid = True
            continue
        granted.add(principal)
    if invalid or not {"current_user", "system"}.issubset(granted):
        raise CoreError(
            "store_permissions_unsafe",
            "Core Store ACL contains an unexpected principal",
            path=str(path),
        )


def _windows_dacl_sddl(path: Path, *, advapi32: object, kernel32: object) -> str:
    import ctypes
    from ctypes import wintypes

    required = wintypes.DWORD()
    flags = 0x00000004
    long_target = win_long_path(path)
    advapi32.GetFileSecurityW(long_target, flags, None, 0, ctypes.byref(required))
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi32.GetFileSecurityW(
        long_target, flags, buffer, required, ctypes.byref(required)
    ):
        _windows_error("verify the private Store ACL", path)
    sddl_pointer = wintypes.LPWSTR()
    if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        buffer, 1, flags, ctypes.byref(sddl_pointer), None
    ):
        _windows_error("format the private Store ACL", path)
    try:
        return str(sddl_pointer.value)
    finally:
        kernel32.LocalFree(ctypes.cast(sddl_pointer, wintypes.HLOCAL))


def _windows_error(action: str, path: Path) -> None:
    import ctypes

    code = ctypes.get_last_error()
    raise CoreError(
        "store_permissions_unsafe",
        f"Core Store could not {action}",
        path=str(path),
        windows_error=code,
    )
