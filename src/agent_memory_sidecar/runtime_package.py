from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CoreError


ARTIFACT_FORMAT = "agent_memory_zipapp_v1"
_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
_RUNTIME_MODULES = frozenset(
    {
        "__init__.py",
        "ambient_capability.py",
        "database.py",
        "errors.py",
        "event_policy.py",
        "file_security.py",
        "identity.py",
        "proposal.py",
        "runtime_hook.py",
        "runtime_ledger.py",
        "runtime_selftest.py",
        "store_lifecycle.py",
    }
)


@dataclass(frozen=True)
class RuntimeArtifact:
    data: bytes
    sha256: str
    file_name: str

    def to_dict(self) -> dict[str, object]:
        return {
            "format": ARTIFACT_FORMAT,
            "file_name": self.file_name,
            "sha256": f"sha256:{self.sha256}",
            "bytes": len(self.data),
        }


def build_runtime_artifact(
    *, package_dir: Path | str | None = None
) -> RuntimeArtifact:
    root = Path(
        package_dir if package_dir is not None else Path(__file__).parent
    ).resolve()
    files = sorted(
        path
        for path in root.glob("*.py")
        if path.is_file() and path.name in _RUNTIME_MODULES
    )
    missing = sorted(
        _RUNTIME_MODULES - {path.name for path in files}
    )
    if missing:
        raise CoreError(
            "runtime_artifact_build_failed",
            "Agent Memory runtime sources are incomplete",
            package_dir=str(root),
            missing=missing,
        )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        _write_zip_entry(
            archive,
            "__main__.py",
            (
                "import sys\n"
                "if sys.argv[1:2] == ['runtime-hook']:\n"
                "    from agent_memory_sidecar.runtime_hook import main\n"
                "    raise SystemExit(main(sys.argv[2:]))\n"
                "if sys.argv[1:2] == ['self-test']:\n"
                "    from agent_memory_sidecar.runtime_selftest import main\n"
                "    raise SystemExit(main(sys.argv[2:]))\n"
                "raise SystemExit(0)\n"
            ).encode("utf-8"),
        )
        for path in files:
            _write_zip_entry(
                archive,
                f"agent_memory_sidecar/{path.name}",
                _canonical_python_source(path),
            )
    data = output.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return RuntimeArtifact(
        data=data,
        sha256=digest,
        file_name=f"agent-memory-{digest[:16]}.pyz",
    )


def install_runtime_artifact(
    *,
    artifact: RuntimeArtifact,
    runtime_root: Path | str,
) -> Path:
    root = Path(runtime_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / artifact.file_name
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise CoreError(
                "runtime_artifact_drift",
                "existing immutable runtime artifact has different bytes",
                path=str(path),
            )
        return path
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=root,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(artifact.data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
        path.unlink(missing_ok=True)
        raise CoreError(
            "runtime_artifact_install_failed",
            "installed runtime artifact failed checksum verification",
            path=str(path),
        )
    return path


def runtime_commands(
    *,
    artifact_path: Path | str,
    official_memory_mode: str = "complement",
) -> dict[str, str]:
    path = str(Path(artifact_path).resolve())
    arguments = [
        str(Path(sys.executable).resolve()),
        path,
        "runtime-hook",
        "--official-memory-mode",
        official_memory_mode,
    ]
    windows = subprocess.list2cmdline(arguments)
    posix = " ".join(shlex.quote(item) for item in arguments)
    return {
        "command": posix,
        "commandWindows": windows,
        "platform_command_sha256": hashlib.sha256(
            windows.encode("utf-8")
        ).hexdigest(),
    }


def desired_hooks_document(
    *,
    existing: dict[str, Any] | None,
    commands: dict[str, str],
) -> dict[str, Any]:
    document = dict(existing or {})
    hooks_value = document.get("hooks")
    hooks = dict(hooks_value) if isinstance(hooks_value, dict) else {}
    for event_name, entries in tuple(hooks.items()):
        filtered = _without_sidecar_hooks(entries)
        if filtered:
            hooks[event_name] = filtered
        else:
            hooks.pop(event_name, None)
    command = {
        "type": "command",
        "command": commands["command"],
        "commandWindows": commands["commandWindows"],
        "timeout": 30,
    }
    hooks.setdefault("UserPromptSubmit", []).append(
        {"hooks": [dict(command)]}
    )
    hooks.setdefault("SessionStart", []).append(
        {"matcher": "^compact$", "hooks": [dict(command)]}
    )
    document["hooks"] = hooks
    return document


def _without_sidecar_hooks(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return [value]
    kept: list[Any] = []
    for entry in value:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        commands = entry.get("hooks")
        if not isinstance(commands, list):
            kept.append(entry)
            continue
        remaining = [
            command
            for command in commands
            if not _is_sidecar_command(command)
        ]
        if remaining:
            kept.append({**entry, "hooks": remaining})
    return kept


def _is_sidecar_command(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    command = " ".join(
        str(value.get(key) or "")
        for key in ("command", "commandWindows")
    ).casefold()
    legacy = (
        "agent_memory_sidecar.runtime_hook" in command
        or "agent-memory-sidecar" in command
    )
    immutable = (
        "agent-memory-" in command
        and ".pyz" in command
        and "runtime-hook" in command
    )
    return legacy or immutable


def hooks_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sidecar_hooks_sha256(document: dict[str, Any]) -> str:
    hooks = document.get("hooks")
    selected: dict[str, list[dict[str, Any]]] = {}
    if isinstance(hooks, dict):
        for event_name, entries in hooks.items():
            if not isinstance(entries, list):
                continue
            selected_entries: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                commands = entry.get("hooks")
                if not isinstance(commands, list):
                    continue
                sidecar = [
                    command
                    for command in commands
                    if _is_sidecar_command(command)
                ]
                if sidecar:
                    selected_entries.append({**entry, "hooks": sidecar})
            if selected_entries:
                selected[str(event_name)] = selected_entries
    return hashlib.sha256(
        hooks_bytes({"hooks": selected})
    ).hexdigest()


def self_test_artifact(
    *,
    artifact_path: Path | str,
    store_path: Path | str,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                str(Path(sys.executable).resolve()),
                str(Path(artifact_path).resolve()),
                "self-test",
                "--store",
                str(Path(store_path).resolve()),
            ],
            cwd=str(Path(store_path).resolve().parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CoreError(
            "runtime_artifact_self_test_failed",
            "immutable runtime self-test could not run",
        ) from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CoreError(
            "runtime_artifact_self_test_failed",
            "immutable runtime self-test returned invalid JSON",
            stderr=completed.stderr[-512:],
        ) from exc
    if completed.returncode != 0 or payload.get("status") != "ok":
        raise CoreError(
            "runtime_artifact_self_test_failed",
            "immutable runtime self-test failed",
            result=payload,
        )
    return payload


def _write_zip_entry(
    archive: zipfile.ZipFile, name: str, data: bytes
) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def _canonical_python_source(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(
        b"\r", b"\n"
    )
