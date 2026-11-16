from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator

from .errors import CoreError
from .file_security import (
    _is_trusted_host_directory_alias,
    acquire_file_lock,
    assert_physical_directory_chain,
    assert_physical_regular_file,
    logical_absolute,
    read_physical_regular_bytes,
    release_file_lock,
)
from .identity import ProjectIdentity
from .instruction_document import (
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_HEADING,
    MANAGED_BLOCK_START,
    MAX_MANAGED_BLOCK_BYTES,
    MAX_RENDERED_RULE_BYTES,
    RULE_ID_PATTERN,
    ConfirmedRule,
    DocumentSnapshot,
    FilePlan,
    InstructionTarget,
    PlannedRuleMutation,
    RuleView,
    _assert_writable,
    _deploy_rules,
    _newline_for_data,
    _parse_document,
    _Parsed,
    _sha256,
    managed_block_bytes,
    measure_capacity,
    normalize_supersedes,
    plan_deploy,
    plan_deploy_bundle,
    plan_replace,
    read_document_bytes,
    render_rule,
    replace_managed_region,
    rule_hash,
    rule_id_for,
    validate_rule_id,
)
from .proposal import RuleBundleItem, RuleProposal


__all__ = [
    "ConfirmedRule",
    "DocumentSnapshot",
    "FilePlan",
    "InstructionRepository",
    "InstructionTarget",
    "MANAGED_BLOCK_END",
    "MANAGED_BLOCK_HEADING",
    "MANAGED_BLOCK_START",
    "MAX_MANAGED_BLOCK_BYTES",
    "MAX_RENDERED_RULE_BYTES",
    "PlannedRuleMutation",
    "RULE_ID_PATTERN",
    "RuleView",
    "assert_physical_directory",
    "atomic_write",
    "managed_block_bytes",
    "measure_capacity",
    "normalize_supersedes",
    "plan_deploy",
    "plan_deploy_bundle",
    "plan_replace",
    "read_document",
    "read_document_bytes",
    "render_rule",
    "replace_managed_region",
    "restore_file",
    "rule_hash",
    "rule_id_for",
    "validate_rule_id",
]


class InstructionRepository:
    def __init__(
        self,
        *,
        codex_home: Path | str | None = None,
        lock_root: Path | str | None = None,
    ) -> None:
        configured = os.environ.get("CODEX_HOME")
        self.codex_home = Path(
            codex_home
            if codex_home is not None
            else configured or Path.home() / ".codex"
        ).expanduser().absolute()
        self.lock_root = Path(
            lock_root
            if lock_root is not None
            else Path(tempfile.gettempdir())
            / "agent-memory-sidecar-instruction-locks"
        ).expanduser().resolve(strict=False)

    def target_path(
        self,
        *,
        target: InstructionTarget,
        identity: ProjectIdentity,
    ) -> Path:
        if target == "global_agents":
            return self.codex_home / "AGENTS.md"
        return _logical_absolute(identity.scope_key) / "AGENTS.md"

    def override_path(
        self,
        *,
        target: InstructionTarget,
        identity: ProjectIdentity,
    ) -> Path:
        return self.target_path(target=target, identity=identity).with_name(
            "AGENTS.override.md"
        )

    def read_target(
        self,
        *,
        target: InstructionTarget,
        identity: ProjectIdentity,
    ) -> DocumentSnapshot:
        path = self.target_path(target=target, identity=identity)
        shadowed = _nonempty(
            self.override_path(target=target, identity=identity)
        )
        return read_document(path=path, target=target, shadowed=shadowed)

    def list_rules(self, *, identity: ProjectIdentity) -> list[RuleView]:
        views: list[RuleView] = []
        for snapshot in self.list_targets(identity=identity):
            views.extend(
                RuleView(rule=rule, path=snapshot.path, shadowed=snapshot.shadowed)
                for rule in snapshot.rules
            )
        return views

    def list_targets(
        self,
        *,
        identity: ProjectIdentity,
        target: InstructionTarget | None = None,
    ) -> tuple[DocumentSnapshot, ...]:
        targets = (target,) if target is not None else (
            "global_agents",
            "project_agents",
        )
        return tuple(
            self.read_target(target=item, identity=identity)
            for item in targets
        )

    def find_rule(
        self, *, rule_id: str, identity: ProjectIdentity
    ) -> RuleView:
        safe = validate_rule_id(rule_id)
        matches = [
            view
            for view in self.list_rules(identity=identity)
            if view.rule.rule_id == safe
        ]
        if not matches:
            raise CoreError(
                "deployed_rule_not_found",
                "confirmed rule does not exist in an actual instruction target",
                rule_id=safe,
            )
        if len(matches) != 1:
            raise CoreError(
                "deployed_rule_ambiguous",
                "confirmed rule exists in multiple targets",
                rule_id=safe,
            )
        return matches[0]

    def plan_deploy(
        self,
        *,
        proposal: RuleProposal,
        identity: ProjectIdentity,
        supersedes: str | Sequence[str] | None = None,
        path: Path | None = None,
    ) -> FilePlan:
        target = proposal.instruction_target
        snapshot = (
            read_document(path=path, target=target, shadowed=False)
            if path is not None
            else self.read_target(target=target, identity=identity)
        )
        return plan_deploy(snapshot=snapshot, proposal=proposal, supersedes=supersedes)

    def plan_deploy_bundle(
        self,
        *,
        items: tuple[RuleBundleItem, ...],
        identity: ProjectIdentity,
        path: Path | None = None,
    ) -> tuple[FilePlan, tuple[PlannedRuleMutation, ...]]:
        if not items:
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle must contain at least one item",
            )
        items = tuple(sorted(items, key=lambda item: item.card_id))
        targets = {item.proposal.instruction_target for item in items}
        if len(targets) != 1:
            raise CoreError(
                "invalid_rule_bundle",
                "every rule bundle item must use the same instruction target",
            )
        target = items[0].proposal.instruction_target
        snapshot = (
            read_document(path=path, target=target, shadowed=False)
            if path is not None
            else self.read_target(target=target, identity=identity)
        )
        return plan_deploy_bundle(snapshot=snapshot, items=items)

    def plan_revoke(
        self,
        *,
        rule_id: str,
        identity: ProjectIdentity,
        path: Path | None = None,
        target: InstructionTarget | None = None,
    ) -> FilePlan:
        if path is None:
            view = self.find_rule(rule_id=rule_id, identity=identity)
            snapshot = self.read_target(
                target=view.rule.target,
                identity=identity,
            )
            rule = view.rule
        else:
            if target is None:
                raise CoreError(
                    "invalid_request",
                    "explicit instruction path requires a target",
                )
            snapshot = read_document(path=path, target=target, shadowed=False)
            safe = validate_rule_id(rule_id)
            found = [rule for rule in snapshot.rules if rule.rule_id == safe]
            if len(found) != 1:
                raise CoreError(
                    "deployed_rule_not_found",
                    "confirmed rule does not exist in the selected target",
                    rule_id=safe,
                )
            rule = found[0]
        _assert_writable(snapshot)
        updated = tuple(
            item for item in snapshot.rules if item.rule_id != rule.rule_id
        )
        return plan_replace(
            snapshot=snapshot,
            rules=updated,
            rule=rule,
            action="revoked",
        )

    @contextmanager
    def lock_paths(self, paths: list[Path]) -> Iterator[None]:
        self.lock_root.mkdir(parents=True, exist_ok=True)
        normalized = sorted(
            {str(_logical_absolute(path)).casefold() for path in paths}
        )
        with ExitStack() as stack:
            for value in normalized:
                digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                lock_path = self.lock_root / f"{digest}.lock"
                handle = stack.enter_context(lock_path.open("a+b"))
                _acquire_file_lock(handle)
                stack.callback(lambda h=handle: _release_file_lock(h))
            yield


def read_document(
    *, path: Path | str, target: InstructionTarget, shadowed: bool = False,
    directory_fd: int | None = None,
) -> DocumentSnapshot:
    logical = _logical_absolute(path)
    try:
        existed, data = _read_regular_bytes(logical, directory_fd=directory_fd)
    except OSError as exc:
        raise CoreError(
            "instruction_file_unreadable",
            "instruction target cannot be read",
            path=str(logical),
        ) from exc
    parsed = _parse_document(data, target=target, path=logical)
    return DocumentSnapshot(
        target=target,
        path=logical,
        existed=existed,
        data=data,
        rules=parsed.rules,
        outside=parsed.outside,
        shadowed=bool(shadowed),
    )


def atomic_write(path: Path, data: bytes, *, directory_fd: int | None = None) -> None:
    path = _logical_absolute(path)
    parent = path.parent
    if directory_fd is None:
        _assert_physical_parent(parent)
    existing = _assert_physical_target(path, allow_missing=True, directory_fd=directory_fd)
    mode: int | None = None
    if existing is not None:
        try:
            mode = stat.S_IMODE(existing.st_mode)
        except OSError:
            mode = None
    temporary: Path | None = None
    try:
        if directory_fd is None:
            handle = tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=parent, delete=False
            )
            temporary = Path(handle.name)
        else:
            candidate = parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
            descriptor = os.open(
                candidate.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            temporary = candidate
            handle = os.fdopen(descriptor, "wb")
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            if mode is not None and directory_fd is not None:
                os.fchmod(handle.fileno(), mode)
        if mode is not None and directory_fd is None:
            os.chmod(temporary, mode)
        _assert_physical_target(temporary, allow_missing=False, directory_fd=directory_fd)
        if directory_fd is None:
            _assert_physical_parent(parent)
        _assert_physical_target(path, allow_missing=True, directory_fd=directory_fd)
        if directory_fd is None:
            os.replace(temporary, path)
        else:
            os.replace(temporary.name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
        _assert_physical_target(path, allow_missing=False, directory_fd=directory_fd)
    except OSError as exc:
        raise CoreError(
            "instruction_write_failed",
            "instruction target could not be atomically replaced",
            path=str(path),
        ) from exc
    finally:
        if temporary is not None:
            if directory_fd is None:
                temporary.unlink(missing_ok=True)
            else:
                os.unlink(temporary.name, dir_fd=directory_fd)


def restore_file(*, path: Path, existed: bool, data: bytes) -> None:
    try:
        if existed:
            atomic_write(path, data)
        else:
            _assert_physical_target(path, allow_missing=True)
            path.unlink(missing_ok=True)
    except OSError as exc:
        raise CoreError(
            "instruction_rollback_failed",
            "failed to restore instruction target",
            path=str(path),
        ) from exc
    actual_existed, actual = _read_regular_bytes(path)
    if actual != data or actual_existed != existed:
        raise CoreError(
            "instruction_rollback_failed",
            "restored instruction bytes do not match the original",
            path=str(path),
        )


def _nonempty(path: Path) -> bool:
    try:
        existed, data = _read_regular_bytes(path)
        return existed and bool(data.strip())
    except OSError as exc:
        raise CoreError(
            "instruction_file_unreadable",
            "instruction override cannot be read",
            path=str(path),
        ) from exc


def _logical_absolute(path: Path | str) -> Path:
    return logical_absolute(path)


def _assert_physical_parent(
    path: Path, *, allow_missing: bool = False
) -> os.stat_result | None:
    return assert_physical_directory_chain(
        path,
        allow_missing_tail=allow_missing,
        missing_code="instruction_parent_unavailable",
        unsafe_code="instruction_target_unsafe",
        missing_message="instruction target parent directory does not exist",
        unsafe_message="instruction target ancestor is a link, reparse point, or non-directory",
        unavailable_message="instruction target parent directory does not exist",
    )


def assert_physical_directory(path: Path | str, *, allow_missing: bool = False) -> None:
    _assert_physical_parent(_logical_absolute(path), allow_missing=allow_missing)


def _assert_physical_target(
    path: Path, *, allow_missing: bool, directory_fd: int | None = None,
) -> os.stat_result | None:
    return assert_physical_regular_file(
        path,
        allow_missing=allow_missing,
        allow_missing_parent=allow_missing,
        directory_fd=directory_fd,
        missing_code="instruction_target_unsafe",
        missing_message="instruction target disappeared",
        parent_missing_code="instruction_parent_unavailable",
        parent_missing_message="instruction target parent directory does not exist",
        unsafe_code="instruction_target_unsafe",
        unsafe_message="instruction target must be one regular, non-link file",
        unavailable_code="instruction_file_unreadable",
        unavailable_message="instruction target metadata cannot be read",
    )


def _read_regular_bytes(path: Path, *, directory_fd: int | None = None) -> tuple[bool, bytes]:
    return read_physical_regular_bytes(
        path,
        directory_fd=directory_fd,
        allow_missing_parent=True,
        parent_missing_code="instruction_parent_unavailable",
        parent_missing_message="instruction target parent directory does not exist",
        unsafe_code="instruction_target_unsafe",
        unsafe_message="instruction target must be one regular, non-link file",
        unavailable_code="instruction_file_unreadable",
        unavailable_message="instruction target metadata cannot be read",
    )


def _acquire_file_lock(handle: object) -> None:
    acquire_file_lock(handle)


def _release_file_lock(handle: object) -> None:
    release_file_lock(handle)
