from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .file_security import logical_absolute, validate_store_identity


@dataclass(frozen=True)
class CanonicalStoreLocation:
    active_store: Path
    rotation_lock: Path


def canonical_store_location(
    store_path: Path | str | CanonicalStoreLocation,
) -> CanonicalStoreLocation:
    """Resolve one physical active_store and its matching maintenance lock."""

    if isinstance(store_path, CanonicalStoreLocation):
        return store_path

    path = Path(store_path).expanduser()
    if str(path) == ":memory:":
        active_store = path
    else:
        active_store = logical_absolute(path)
        validate_store_identity(active_store, allow_missing=True)
    return CanonicalStoreLocation(
        active_store=active_store,
        rotation_lock=Path(f"{active_store}.rotation.lock"),
    )


def canonical_store_path(
    store_path: Path | str | CanonicalStoreLocation,
) -> Path:
    """Return one physical identity for every file-backed active_store path."""

    return canonical_store_location(store_path).active_store


def clean_store_rotation_lock_path(
    store_path: Path | str | CanonicalStoreLocation,
) -> Path:
    return canonical_store_location(store_path).rotation_lock


def clean_store_rotation_locked(
    store_path: Path | str | CanonicalStoreLocation,
) -> bool:
    return clean_store_rotation_lock_path(store_path).exists()
