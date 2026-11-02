from __future__ import annotations

"""Resolve global Owner parity from the installed Core binding without path guessing."""

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from utf8_stdio import configure_utf8_stdio


CANONICAL_REF = "canonical_global_agents"
LOCAL_REF = "host_local_global_agents"
BINDING_VERSION = "global_instruction_binding_v3"
CORE_STATE_DIR = "agent-memory-sidecar"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def parity_result(status: str, canonical_hash_value: str | None, local_hash_value: str | None) -> dict[str, Any]:
    result = {
        "status": status,
        "canonical_source_ref": CANONICAL_REF,
        "canonical_source_hash": canonical_hash_value,
        "local_target_ref": LOCAL_REF,
        "local_target_hash": local_hash_value,
    }
    result["snapshot_id"] = canonical_hash(result)
    return result


def unavailable() -> dict[str, Any]:
    return parity_result("unavailable", None, None)


def is_physical_directory(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    attributes = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISDIR(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and not bool(attributes & reparse)
    )


def is_physical_file(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    attributes = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISREG(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and not bool(attributes & reparse)
        and value.st_nlink == 1
    )


def read_binding(store: Path) -> Path | None:
    if not is_physical_directory(store.parent) or not is_physical_file(store):
        return None
    uri = store.absolute().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        row = connection.execute(
            "SELECT binding_version, source_root FROM global_instruction_binding WHERE singleton = 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None or row[0] != BINDING_VERSION or not isinstance(row[1], str) or not row[1].strip():
        return None
    root = Path(row[1]).expanduser()
    if not root.is_absolute() or not is_physical_directory(root):
        return None
    global_root = root / "global"
    if not is_physical_directory(global_root):
        return None
    return global_root / "AGENTS.md"


def resolve(codex_home: Path) -> dict[str, Any]:
    try:
        if not is_physical_directory(codex_home):
            return unavailable()
        source = read_binding(codex_home / CORE_STATE_DIR / "memory.sqlite")
        target = codex_home / "AGENTS.md"
        if source is None or not is_physical_file(source) or not is_physical_file(target):
            return unavailable()
        source_hash = sha256_bytes(source.read_bytes())
        target_hash = sha256_bytes(target.read_bytes())
        status = "matched" if source_hash == target_hash else "drift"
        return parity_result(status, source_hash, target_hash)
    except (OSError, sqlite3.DatabaseError, ValueError):
        return unavailable()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        codex_home = root / "codex-home"
        source_root = root / "canonical"
        (codex_home / CORE_STATE_DIR).mkdir(parents=True)
        (source_root / "global").mkdir(parents=True)
        source = source_root / "global" / "AGENTS.md"
        target = codex_home / "AGENTS.md"
        source.write_text("same\n", encoding="utf-8")
        target.write_text("same\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("project decoy\n", encoding="utf-8")

        store = codex_home / CORE_STATE_DIR / "memory.sqlite"
        connection = sqlite3.connect(store)
        try:
            connection.execute(
                "CREATE TABLE global_instruction_binding (singleton INTEGER PRIMARY KEY, binding_version TEXT, source_root TEXT)"
            )
            connection.execute(
                "INSERT INTO global_instruction_binding VALUES (1, ?, ?)",
                (BINDING_VERSION, str(source_root)),
            )
            connection.commit()
        finally:
            connection.close()

        matched = resolve(codex_home)
        assert matched["status"] == "matched"
        assert set(matched) == {
            "status", "canonical_source_ref", "canonical_source_hash",
            "local_target_ref", "local_target_hash", "snapshot_id",
        }
        assert str(source_root) not in json.dumps(matched)

        target.write_text("different\n", encoding="utf-8")
        assert resolve(codex_home)["status"] == "drift"

        target.unlink()
        try:
            target.symlink_to(source)
        except OSError:
            target.write_text("different\n", encoding="utf-8")
        else:
            assert resolve(codex_home)["status"] == "unavailable"
            target.unlink()

        store.unlink()
        missing = resolve(codex_home)
        assert missing["status"] == "unavailable"
        assert missing["canonical_source_hash"] is None and missing["local_target_hash"] is None


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"status": "ok", "resolver": "global_owner_parity_v1"}, separators=(",", ":")))
        return 0
    configured = os.environ.get("CODEX_HOME")
    codex_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    print(json.dumps(resolve(codex_home), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
