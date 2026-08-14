from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectIdentity:
    cwd: str
    repo_root: str | None
    branch: str | None
    scope_key: str


def resolve_identity(cwd: str | None = None) -> ProjectIdentity:
    path = Path(cwd or os.getcwd()).resolve()
    repo_root = _git_value(["rev-parse", "--show-toplevel"], path)
    branch = _git_value(["branch", "--show-current"], path) if repo_root else None
    scope_key = repo_root or str(path)
    return ProjectIdentity(
        cwd=str(path),
        repo_root=_normalize_path(repo_root) if repo_root else None,
        branch=branch or None,
        scope_key=_normalize_path(scope_key),
    )


def default_store_path(cwd: str | None = None) -> Path:
    identity = resolve_identity(cwd)
    return Path(identity.scope_key) / ".agent-memory" / "memory.sqlite"


def _git_value(args: list[str], cwd: Path) -> str | None:
    # Warm Quiet Runtime prompts use their cached session identity and never
    # call this function. Keep the relatively expensive process module out of
    # that per-prompt import path.
    import subprocess

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _normalize_path(value: str) -> str:
    return str(Path(value).resolve())
