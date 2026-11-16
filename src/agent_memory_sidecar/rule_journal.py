from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from .authorization import AuthorizationLedger
from .database import CoreDatabase
from .errors import CoreError
from .instructions import (
    FilePlan,
    InstructionRepository,
    assert_physical_directory,
    atomic_write,
    read_document,
    restore_file,
)


class FileTransactionCoordinator:
    def __init__(
        self,
        *,
        db: CoreDatabase,
        authorization: AuthorizationLedger,
        repository: InstructionRepository,
        atomic_writer: Callable[[Path, bytes], None] | None = None,
        rmtree: Callable[..., None] | None = None,
    ) -> None:
        self.db = db
        self.authorization = authorization
        self.repository = repository
        self._atomic_write = atomic_writer or atomic_write
        self._rmtree = rmtree or shutil.rmtree
        self.journal_root = db.path.parent / "transactions"

    def recover(self) -> list[str]:
        assert_physical_directory(self.journal_root, allow_missing=True)
        try:
            directories = sorted(self.journal_root.iterdir())
        except FileNotFoundError:
            return []
        recovered: list[str] = []
        for directory in directories:
            if not directory.is_dir():
                continue
            manifest_path = directory / "manifest.json"
            try:
                assert_physical_directory(directory, allow_missing=True)
                if directory.name.startswith(".cleanup-tx_"):
                    self._delete_retired_journal(directory)
                    recovered.append(directory.name.removeprefix(".cleanup-"))
                    continue
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                transaction_id = str(manifest["transaction_id"])
                files = list(manifest["files"])
                if (
                    manifest.get("contract_version")
                    not in {"instruction_transaction_v1", "instruction_transaction_v2"}
                    or directory.name != transaction_id
                    or manifest.get("state")
                    not in {"prepared", "files_written", "committed"}
                    or not 1 <= len(files) <= 2
                ):
                    raise CoreError(
                        "instruction_recovery_invalid",
                        "instruction transaction journal is malformed",
                        journal=str(directory),
                    )
                paths = self._validate_journal_files(
                    directory=directory,
                    files=files,
                    verify_snapshots=False,
                )
                with self.repository.lock_paths(paths):
                    if not directory.exists():
                        continue
                    fresh = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if (
                        {key: value for key, value in fresh.items() if key != "state"}
                        != {key: value for key, value in manifest.items() if key != "state"}
                        or fresh.get("state") not in {"prepared", "files_written", "committed"}
                    ):
                        raise CoreError("instruction_recovery_invalid", "journal identity changed while acquiring locks")
                    self._validate_journal_files(directory=directory, files=files)
                    event_id = fresh.get("source_event_id")
                    if event_id is not None and (not isinstance(event_id, str) or not event_id):
                        raise CoreError("instruction_recovery_invalid", "journal source event is malformed")
                    evidence = self.db.conn.execute(
                        """
                        SELECT EXISTS(SELECT 1 FROM approval_consumptions WHERE transaction_id = ?),
                               EXISTS(SELECT 1 FROM prompt_events WHERE event_id = ?)
                        """,
                        (transaction_id, event_id),
                    ).fetchone()
                    committed = fresh["state"] == "committed" or bool(evidence[0])
                    if not committed:
                        if not evidence[1]:
                            raise CoreError(
                                "instruction_recovery_unproven",
                                "retained evidence cannot prove commit state; targets and journal were preserved",
                                recovery_required=True,
                                transaction_id=transaction_id,
                            )
                    for index, (item, path) in enumerate(zip(files, paths)):
                        before = (directory / f"{index}.before").read_bytes()
                        after = (directory / f"{index}.after").read_bytes()
                        target = str(item.get("target") or "")
                        if target not in {"project_agents", "global_agents"}:
                            raise CoreError(
                                "instruction_recovery_invalid",
                                "instruction transaction target type is invalid",
                            )
                        snapshot = read_document(path=path, target=target)
                        actual_state = (snapshot.existed, snapshot.data)
                        valid_states = {
                            (bool(item["before_existed"]), before),
                            (bool(item["after_existed"]), after),
                        }
                        if actual_state not in valid_states:
                            raise CoreError(
                                "instruction_recovery_drift",
                                "instruction target changed outside the incomplete transaction",
                                path=str(path),
                            )
                        restore_file(
                            path=path,
                            existed=(
                                bool(item["after_existed"])
                                if committed
                                else bool(item["before_existed"])
                            ),
                            data=after if committed else before,
                        )
                    self._discard_journal(directory)
                    recovered.append(transaction_id)
            except CoreError:
                raise
            except FileNotFoundError as exc:
                if not directory.exists():
                    continue
                raise CoreError(
                    "instruction_recovery_failed",
                    "an incomplete instruction transaction could not be read",
                    journal=str(directory),
                ) from exc
            except Exception as exc:
                raise CoreError(
                    "instruction_recovery_failed",
                    "an incomplete instruction transaction could not be recovered",
                    journal=str(directory),
                ) from exc
        self._remove_empty_journal_root()
        return recovered

    def _discard_journal(self, directory: Path, *, ignore_errors: bool = False) -> None:
        cleanup = directory.with_name(f".cleanup-{directory.name}")
        try:
            assert_physical_directory(directory, allow_missing=True)
            directory.rename(cleanup)
            self._delete_retired_journal(cleanup, ignore_errors=ignore_errors)
        except FileNotFoundError:
            if not ignore_errors and (directory.exists() or cleanup.exists()):
                raise
        except OSError:
            if not ignore_errors:
                raise

    def _delete_retired_journal(self, directory: Path, *, ignore_errors: bool = False) -> None:
        assert_physical_directory(directory, allow_missing=True)

        def onerror(function, path, exc_info):
            error = exc_info[1]
            if not (isinstance(error, FileNotFoundError) and Path(path) != directory):
                raise error

        self._rmtree(directory, ignore_errors=ignore_errors, onerror=onerror)

    def _remove_empty_journal_root(self) -> None:
        try:
            self.journal_root.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                raise

    def _validate_journal_files(
        self,
        *,
        directory: Path,
        files: list[Any],
        verify_snapshots: bool = True,
    ) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                raise CoreError(
                    "instruction_recovery_invalid",
                    "instruction transaction file entry is malformed",
                    journal=str(directory),
                )
            path = Path(str(item.get("path") or ""))
            key = str(path.resolve(strict=False)).casefold()
            if (
                not path.is_absolute()
                or path.name != "AGENTS.md"
                or key in seen
            ):
                raise CoreError(
                    "instruction_recovery_invalid",
                    "instruction transaction target is invalid",
                    journal=str(directory),
                )
            before = directory / f"{index}.before"
            after = directory / f"{index}.after"
            if verify_snapshots and (
                not before.is_file()
                or not after.is_file()
                or _sha256(before.read_bytes())
                != str(item.get("before_sha256") or "")
                or _sha256(after.read_bytes())
                != str(item.get("after_sha256") or "")
            ):
                raise CoreError(
                    "instruction_recovery_invalid",
                    "instruction transaction snapshots failed checksum validation",
                    journal=str(directory),
                )
            seen.add(key)
            paths.append(path)
        return paths

    def apply(
        self,
        *,
        plans: tuple[FilePlan, ...],
        database_commit: Callable[[str], None],
        source_event_id: str,
    ) -> str:
        self.recover()
        transaction_id = f"tx_{uuid.uuid4().hex}"
        paths = [plan.path for plan in plans]
        committed = False
        try:
            with self.repository.lock_paths(paths):
                self._assert_unchanged(plans)
                journal = self._write_journal(
                    transaction_id=transaction_id,
                    plans=plans,
                    source_event_id=source_event_id,
                )
                try:
                    for plan in plans:
                        if plan.after != plan.before:
                            self._atomic_write(plan.path, plan.after)
                        actual = read_document(
                            path=plan.path,
                            target=plan.target,
                        )
                        if actual.data != plan.after:
                            raise CoreError(
                                "instruction_write_verification_failed",
                                "instruction target did not match planned bytes",
                                path=str(plan.path),
                            )
                    self._set_journal_state(journal, "files_written")
                    with self.db.transaction():
                        database_commit(transaction_id)
                    committed = True
                    self._set_journal_state(journal, "committed")
                    self._discard_journal(journal)
                    self._remove_empty_journal_root()
                    return transaction_id
                except BaseException:
                    if not committed:
                        for plan in reversed(plans):
                            restore_file(
                                path=plan.path,
                                existed=plan.existed,
                                data=plan.before,
                            )
                        self._discard_journal(journal, ignore_errors=True)
                        self._remove_empty_journal_root()
                    raise
        except BaseException as exc:
            if committed:
                raise CoreError(
                    "instruction_cleanup_required",
                    "instruction operation committed; transaction cleanup is incomplete",
                    operation_committed=True,
                    approval_consumed=True,
                    recovery_required=True,
                    transaction_id=transaction_id,
                ) from exc
            raise

    def _assert_unchanged(self, plans: tuple[FilePlan, ...]) -> None:
        for plan in plans:
            actual = read_document(path=plan.path, target=plan.target)
            if actual.data != plan.before or actual.existed != plan.existed:
                raise CoreError(
                    "instruction_drift",
                    "instruction target changed after planning",
                    path=str(plan.path),
                )

    def _write_journal(
        self,
        *,
        transaction_id: str,
        plans: tuple[FilePlan, ...],
        source_event_id: str,
    ) -> Path:
        assert_physical_directory(self.journal_root.parent)
        self.journal_root.mkdir(parents=True, exist_ok=True)
        assert_physical_directory(self.journal_root)
        directory = self.journal_root / transaction_id
        directory.mkdir(exist_ok=False)
        assert_physical_directory(directory)
        files: list[dict[str, object]] = []
        try:
            for index, plan in enumerate(plans):
                before = directory / f"{index}.before"
                after = directory / f"{index}.after"
                _durable_write(before, plan.before)
                _durable_write(after, plan.after)
                files.append(
                    {
                        "path": str(plan.path),
                        "target": plan.target,
                        "before_existed": plan.existed,
                        "after_existed": True if plan.after else plan.existed,
                        "before_sha256": _sha256(plan.before),
                        "after_sha256": _sha256(plan.after),
                    }
                )
            manifest = {
                "contract_version": "instruction_transaction_v2",
                "transaction_id": transaction_id,
                "source_event_id": source_event_id,
                "state": "prepared",
                "files": files,
            }
            _durable_write(
                directory / "manifest.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
            return directory
        except BaseException:
            self._rmtree(directory, ignore_errors=True)
            raise

    def _set_journal_state(self, directory: Path, state: str) -> None:
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state"] = state
        _durable_write(
            manifest_path,
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )


def _durable_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
