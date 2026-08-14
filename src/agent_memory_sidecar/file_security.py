from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from .errors import CoreError


def logical_absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


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


def _validate_physical_directory_chain(path: Path) -> None:
    logical = logical_absolute(path)
    cursor = Path(logical.anchor)
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except OSError as exc:
            raise CoreError(
                "store_unsafe",
                "Core Store ancestor metadata is unavailable",
                path=str(cursor),
            ) from exc
        alias = stat.S_ISLNK(value.st_mode) or _is_reparse_point(value)
        if alias and _is_trusted_host_directory_alias(cursor, value):
            try:
                resolved = cursor.resolve(strict=True)
                resolved_value = resolved.stat()
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
            continue
        if not stat.S_ISDIR(value.st_mode) or alias:
            raise CoreError(
                "store_unsafe",
                "Core Store ancestor must be a physical directory",
                path=str(cursor),
            )


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
    path: Path | str, *, allow_missing: bool
) -> Path:
    target, _ = _validated_store_location(
        path,
        allow_missing=allow_missing,
    )
    return target


def _validated_store_location(
    path: Path | str, *, allow_missing: bool
) -> tuple[Path, os.stat_result | None]:
    target = logical_absolute(path)
    parent = target.parent
    _validate_physical_directory_chain(parent)

    file_stat: os.stat_result | None
    try:
        file_stat = target.lstat()
    except FileNotFoundError:
        file_stat = None
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
        if not advapi32.SetFileSecurityW(str(path), flags, descriptor):
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
    advapi32.GetFileSecurityW(str(path), flags, None, 0, ctypes.byref(required))
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi32.GetFileSecurityW(
        str(path), flags, buffer, required, ctypes.byref(required)
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
