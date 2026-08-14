from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Iterator, Literal

from .errors import CoreError
from .file_security import _is_trusted_host_directory_alias
from .identity import ProjectIdentity
from .proposal import RuleBundleItem, RuleProposal


InstructionTarget = Literal["global_agents", "project_agents"]

MANAGED_BLOCK_START = "<!-- agent-memory:confirmed-rules:start -->"
MANAGED_BLOCK_END = "<!-- agent-memory:confirmed-rules:end -->"
MANAGED_BLOCK_HEADING = "## Confirmed collaboration rules"
MAX_RENDERED_RULE_BYTES = 1024
MAX_MANAGED_BLOCK_BYTES = 8 * 1024
RULE_ID_PATTERN = re.compile(r"^rule_[0-9a-f]{12}$")
_FIELD_PATTERN = re.compile(r"^- (When|Do|Skip): (.+)$")
_LOCK_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ConfirmedRule:
    target: InstructionTarget
    trigger: str
    action: str
    skip_boundary: str
    rule_id: str

    @classmethod
    def from_proposal(cls, proposal: RuleProposal) -> "ConfirmedRule":
        target: InstructionTarget = proposal.instruction_target
        rule_id = rule_id_for(
            target=target,
            trigger=proposal.trigger,
            action=proposal.action,
            skip_boundary=proposal.skip_boundary,
        )
        value = cls(
            target=target,
            trigger=proposal.trigger,
            action=proposal.action,
            skip_boundary=proposal.skip_boundary,
            rule_id=rule_id,
        )
        if len(render_rule(value, newline="\n").encode("utf-8")) > MAX_RENDERED_RULE_BYTES:
            raise CoreError(
                "instruction_capacity_exceeded",
                "confirmed rule exceeds the 1 KiB instruction budget",
                rule_id=rule_id,
                budget_bytes=MAX_RENDERED_RULE_BYTES,
            )
        return value

    @classmethod
    def create(
        cls,
        *,
        target: InstructionTarget,
        trigger: str,
        action: str,
        skip_boundary: str,
    ) -> "ConfirmedRule":
        proposal = RuleProposal.from_payload(
            {
                "trigger": trigger,
                "action": action,
                "skip_boundary": skip_boundary,
                "scope": (
                    "global" if target == "global_agents" else "project"
                ),
                "why": "persisted instruction parse",
                "evidence": "persisted instruction bytes",
                "instruction_target": target,
            }
        )
        return cls.from_proposal(proposal)

    @property
    def content_sha256(self) -> str:
        return rule_hash(
            target=self.target,
            trigger=self.trigger,
            action=self.action,
            skip_boundary=self.skip_boundary,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.rule_id,
            "instruction_target": self.target,
            "trigger": self.trigger,
            "action": self.action,
            "skip_boundary": self.skip_boundary,
            "content_sha256": f"sha256:{self.content_sha256}",
        }


@dataclass(frozen=True)
class DocumentSnapshot:
    target: InstructionTarget
    path: Path
    existed: bool
    data: bytes
    rules: tuple[ConfirmedRule, ...]
    outside: bytes
    shadowed: bool

    @property
    def file_sha256(self) -> str:
        return _sha256(self.data)

    @property
    def managed_block_sha256(self) -> str:
        return _sha256(managed_block_bytes(self.rules, newline="\n"))

    @property
    def managed_block_bytes(self) -> int:
        return len(
            managed_block_bytes(
                self.rules,
                newline=_newline_for_data(self.data),
            )
        )

    def capacity_dict(self) -> dict[str, object]:
        managed = self.managed_block_bytes
        return {
            "instruction_target": self.target,
            "path": str(self.path),
            "managed_block_bytes": managed,
            "managed_block_budget_bytes": MAX_MANAGED_BLOCK_BYTES,
            "remaining_bytes": max(0, MAX_MANAGED_BLOCK_BYTES - managed),
            "document_bytes": len(self.data),
            "rule_count": len(self.rules),
            "shadowed": self.shadowed,
        }


@dataclass(frozen=True)
class FilePlan:
    target: InstructionTarget
    path: Path
    existed: bool
    before: bytes
    after: bytes
    before_rules: tuple[ConfirmedRule, ...]
    after_rules: tuple[ConfirmedRule, ...]
    rule: ConfirmedRule
    action: str
    outside_unchanged: bool
    affected_rules: tuple[ConfirmedRule, ...] = ()

    def to_dict(self) -> dict[str, object]:
        before_managed = len(
            managed_block_bytes(
                self.before_rules,
                newline=_newline_for_data(self.before),
            )
        )
        after_managed = len(
            managed_block_bytes(
                self.after_rules,
                newline=_newline_for_data(self.after),
            )
        )
        result: dict[str, object] = {
            "action": self.action,
            "path": str(self.path),
            "before_sha256": f"sha256:{_sha256(self.before)}",
            "after_sha256": f"sha256:{_sha256(self.after)}",
            "before_managed_block_bytes": before_managed,
            "projected_managed_block_bytes": after_managed,
            "managed_block_budget_bytes": MAX_MANAGED_BLOCK_BYTES,
            "outside_unchanged": self.outside_unchanged,
            "rule": self.rule.to_dict(),
        }
        if self.affected_rules:
            result["affected_rules"] = [
                rule.to_dict() for rule in self.affected_rules
            ]
        return result


@dataclass(frozen=True)
class PlannedRuleMutation:
    card_id: str
    action: str
    rule: ConfirmedRule

    def to_dict(self) -> dict[str, object]:
        return {
            "card_id": self.card_id,
            "action": self.action,
            "rule": self.rule.to_dict(),
        }


@dataclass(frozen=True)
class RuleView:
    rule: ConfirmedRule
    path: Path
    shadowed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            **self.rule.to_dict(),
            "path": str(self.path),
            "shadowed": self.shadowed,
            "user_status": "已停用" if self.shadowed else "生效中",
            "user_scope": (
                "跨项目"
                if self.rule.target == "global_agents"
                else "本项目"
            ),
        }


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
        rule = ConfirmedRule.from_proposal(proposal)
        target = rule.target
        snapshot = (
            read_document(path=path, target=target, shadowed=False)
            if path is not None
            else self.read_target(target=target, identity=identity)
        )
        _assert_writable(snapshot)
        updated, action = _deploy_rules(
            snapshot.rules,
            rule=rule,
            supersedes=normalize_supersedes(supersedes),
        )
        return plan_replace(snapshot=snapshot, rules=updated, rule=rule, action=action)

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
        _assert_writable(snapshot)
        original_by_id = {rule.rule_id: rule for rule in snapshot.rules}
        original_positions = {
            rule.rule_id: index for index, rule in enumerate(snapshot.rules)
        }
        original_ids = set(original_by_id)
        used_supersedes: set[str] = set()
        new_rule_ids: set[str] = set()
        prepared: list[
            tuple[RuleBundleItem, ConfirmedRule, tuple[str, ...]]
        ] = []
        for item in items:
            rule = ConfirmedRule.from_proposal(item.proposal)
            supersedes = normalize_supersedes(item.supersedes)
            if rule.rule_id in new_rule_ids:
                raise CoreError(
                    "invalid_rule_bundle",
                    "rule bundle produces duplicate confirmed rules",
                    rule_id=rule.rule_id,
                )
            overlap = sorted(used_supersedes.intersection(supersedes))
            if overlap:
                raise CoreError(
                    "invalid_rule_bundle",
                    "rule bundle items cannot supersede the same existing rule",
                    overlapping_rule_ids=overlap,
                )
            missing_from_before = sorted(
                rule_id for rule_id in supersedes if rule_id not in original_ids
            )
            if missing_from_before:
                raise CoreError(
                    "rule_revision_stale",
                    "rule bundle supersedes do not exist in the fresh target snapshot",
                    missing_rule_ids=missing_from_before,
                )
            if not supersedes and rule.rule_id in original_ids:
                raise CoreError(
                    "rule_bundle_not_applicable",
                    "every selected rule must still produce a change",
                    rule_id=rule.rule_id,
                )
            if supersedes == (rule.rule_id,):
                raise CoreError(
                    "rule_bundle_not_applicable",
                    "every selected rule must still produce a change",
                    rule_id=rule.rule_id,
                )
            prepared.append((item, rule, supersedes))
            new_rule_ids.add(rule.rule_id)
            used_supersedes.update(supersedes)
        surviving_ids = original_ids - used_supersedes
        duplicate_survivors = sorted(new_rule_ids.intersection(surviving_ids))
        if duplicate_survivors:
            raise CoreError(
                "instruction_edit_duplicate",
                "rule bundle would duplicate an unaffected confirmed rule",
                rule_ids=duplicate_survivors,
            )

        positioned: list[tuple[int, int, str, ConfirmedRule]] = [
            (index, 0, rule.rule_id, rule)
            for index, rule in enumerate(snapshot.rules)
            if rule.rule_id in surviving_ids
        ]
        mutations: list[PlannedRuleMutation] = []
        affected: list[ConfirmedRule] = []
        for item, rule, supersedes in prepared:
            if supersedes:
                position = min(original_positions[value] for value in supersedes)
                action = "consolidated" if len(supersedes) > 1 else "replaced"
                kind = 1
            else:
                position = len(snapshot.rules)
                action = "deployed"
                kind = 2
            positioned.append((position, kind, rule.rule_id, rule))
            mutations.append(
                PlannedRuleMutation(
                    card_id=item.card_id,
                    action=action,
                    rule=rule,
                )
            )
            affected.append(rule)
        current = tuple(
            value[3]
            for value in sorted(
                positioned,
                key=lambda value: (value[0], value[1], value[2]),
            )
        )
        if len({rule.rule_id for rule in current}) != len(current):
            raise CoreError(
                "invalid_rule_bundle",
                "rule bundle produces duplicate confirmed rules",
            )
        if current == snapshot.rules:
            raise CoreError(
                "rule_bundle_not_applicable",
                "selected rule set does not change the target",
            )
        plan = plan_replace(
            snapshot=snapshot,
            rules=current,
            rule=affected[0],
            action="bundle_deployed",
            affected_rules=tuple(affected),
        )
        return plan, tuple(mutations)

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
                stack.callback(_release_file_lock, handle)
            yield


def read_document(
    *, path: Path | str, target: InstructionTarget, shadowed: bool = False
) -> DocumentSnapshot:
    logical = _logical_absolute(path)
    try:
        existed, data = _read_regular_bytes(logical)
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


def plan_replace(
    *,
    snapshot: DocumentSnapshot,
    rules: tuple[ConfirmedRule, ...],
    rule: ConfirmedRule,
    action: str,
    affected_rules: tuple[ConfirmedRule, ...] = (),
) -> FilePlan:
    if any(item.target != snapshot.target for item in rules):
        raise CoreError(
            "instruction_rule_target_mismatch",
            "every rule must match the selected target",
        )
    after = replace_managed_region(
        snapshot.data,
        target=snapshot.target,
        rules=rules,
        path=snapshot.path,
    )
    verified = read_document_bytes(
        data=after,
        path=snapshot.path,
        target=snapshot.target,
    )
    if verified.rules != rules:
        raise CoreError(
            "instruction_round_trip_failed",
            "planned instruction rules did not round-trip",
        )
    if snapshot.outside != verified.outside:
        raise CoreError(
            "instruction_outside_bytes_changed",
            "planned mutation changed bytes outside the managed block",
            path=str(snapshot.path),
        )
    return FilePlan(
        target=snapshot.target,
        path=snapshot.path,
        existed=snapshot.existed,
        before=snapshot.data,
        after=after,
        before_rules=snapshot.rules,
        after_rules=rules,
        rule=rule,
        action=action,
        outside_unchanged=True,
        affected_rules=affected_rules,
    )


def read_document_bytes(
    *, data: bytes, path: Path, target: InstructionTarget
) -> DocumentSnapshot:
    parsed = _parse_document(data, target=target, path=path)
    return DocumentSnapshot(
        target=target,
        path=path,
        existed=bool(data),
        data=data,
        rules=parsed.rules,
        outside=parsed.outside,
        shadowed=False,
    )


def replace_managed_region(
    data: bytes,
    *,
    target: InstructionTarget,
    rules: tuple[ConfirmedRule, ...],
    path: Path,
) -> bytes:
    parsed = _parse_document(data, target=target, path=path)
    block = managed_block_bytes(rules, newline=parsed.newline)
    if len(block) > MAX_MANAGED_BLOCK_BYTES:
        before_bytes = len(
            managed_block_bytes(parsed.rules, newline=parsed.newline)
        )
        raise CoreError(
            "instruction_capacity_exceeded",
            "managed instruction block exceeds the 8 KiB target budget",
            budget_bytes=MAX_MANAGED_BLOCK_BYTES,
            actual_bytes=len(block),
            before_bytes=before_bytes,
            projected_bytes=len(block),
            path=str(path),
        )
    if parsed.marker_start is None:
        if not rules:
            return data
        separator = parsed.newline.encode("ascii") * 2 if data else b""
        return data + separator + block
    assert parsed.region_start is not None and parsed.region_end is not None
    if not rules:
        return data[: parsed.region_start] + data[parsed.region_end :]
    return data[: parsed.marker_start] + block + data[parsed.region_end :]


def managed_block_bytes(
    rules: tuple[ConfirmedRule, ...], *, newline: str
) -> bytes:
    if not rules:
        return b""
    body = (newline * 2).join(
        [MANAGED_BLOCK_HEADING]
        + [render_rule(rule, newline=newline) for rule in rules]
    )
    return (
        MANAGED_BLOCK_START
        + newline
        + body
        + newline
        + MANAGED_BLOCK_END
        + newline
    ).encode("utf-8")


def render_rule(rule: ConfirmedRule, *, newline: str) -> str:
    return newline.join(
        (
            f"### {rule.rule_id}",
            f"- When: {rule.trigger}",
            f"- Do: {rule.action}",
            f"- Skip: {rule.skip_boundary}",
        )
    )


def atomic_write(path: Path, data: bytes) -> None:
    path = _logical_absolute(path)
    parent = path.parent
    _assert_physical_parent(parent)
    existing = _assert_physical_target(path, allow_missing=True)
    mode: int | None = None
    if existing is not None:
        try:
            mode = stat.S_IMODE(existing.st_mode)
        except OSError:
            mode = None
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        _assert_physical_target(temporary, allow_missing=False)
        _assert_physical_parent(parent)
        _assert_physical_target(path, allow_missing=True)
        os.replace(temporary, path)
        temporary = None
        _assert_physical_target(path, allow_missing=False)
    except OSError as exc:
        raise CoreError(
            "instruction_write_failed",
            "instruction target could not be atomically replaced",
            path=str(path),
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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


def rule_hash(
    *,
    target: InstructionTarget,
    trigger: str,
    action: str,
    skip_boundary: str,
) -> str:
    return hashlib.sha256(
        "\0".join((target, trigger, action, skip_boundary)).encode("utf-8")
    ).hexdigest()


def rule_id_for(
    *,
    target: InstructionTarget,
    trigger: str,
    action: str,
    skip_boundary: str,
) -> str:
    return "rule_" + rule_hash(
        target=target,
        trigger=trigger,
        action=action,
        skip_boundary=skip_boundary,
    )[:12]


def validate_rule_id(value: str) -> str:
    text = str(value or "").strip()
    if not RULE_ID_PATTERN.fullmatch(text):
        raise CoreError("invalid_rule_id", "rule_id is malformed")
    return text


def normalize_supersedes(
    values: str | Sequence[str] | None,
) -> tuple[str, ...]:
    if values is None:
        return ()
    raw = (values,) if isinstance(values, str) else tuple(values)
    normalized = tuple(validate_rule_id(value) for value in raw)
    if len(normalized) != len(set(normalized)):
        raise CoreError(
            "rule_revision_invalid",
            "superseded rule ids must be unique",
            supersedes=list(normalized),
        )
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class _Parsed:
    rules: tuple[ConfirmedRule, ...]
    marker_start: int | None
    region_start: int | None
    region_end: int | None
    newline: str
    outside: bytes


def _parse_document(
    data: bytes, *, target: InstructionTarget, path: Path
) -> _Parsed:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoreError(
            "instruction_encoding_unsupported",
            "instruction target must be UTF-8",
            path=str(path),
        ) from exc
    start = MANAGED_BLOCK_START.encode("ascii")
    end = MANAGED_BLOCK_END.encode("ascii")
    newline = "\r\n" if b"\r\n" in data else "\n"
    if data.count(start) == 0 and data.count(end) == 0:
        return _Parsed((), None, None, None, newline, data)
    if data.count(start) != 1 or data.count(end) != 1:
        raise CoreError(
            "managed_instruction_block_invalid",
            "target must contain zero or one complete managed block",
            path=str(path),
        )
    marker_start = data.index(start)
    marker_end = data.index(end)
    if marker_end <= marker_start:
        raise CoreError(
            "managed_instruction_block_invalid",
            "managed instruction delimiters are out of order",
            path=str(path),
        )
    region_end = marker_end + len(end)
    if data[region_end : region_end + 2] == b"\r\n":
        region_end += 2
    elif data[region_end : region_end + 1] == b"\n":
        region_end += 1
    separator = newline.encode("ascii") * 2
    region_start = (
        marker_start - len(separator)
        if marker_start >= len(separator)
        and data[marker_start - len(separator) : marker_start] == separator
        else marker_start
    )
    lines = (
        data[marker_start + len(start) : marker_end]
        .decode("utf-8")
        .replace("\r\n", "\n")
        .split("\n")
    )
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or lines.pop(0) != MANAGED_BLOCK_HEADING:
        raise CoreError(
            "managed_instruction_block_invalid",
            "managed instruction heading is invalid",
            path=str(path),
        )
    rules: list[ConfirmedRule] = []
    while lines:
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            break
        header = lines.pop(0)
        if not header.startswith("### ") or len(lines) < 3:
            raise CoreError(
                "managed_instruction_block_invalid",
                "managed rule structure is invalid",
                path=str(path),
            )
        stored_id = validate_rule_id(header[4:])
        fields: dict[str, str] = {}
        for expected in ("When", "Do", "Skip"):
            match = _FIELD_PATTERN.fullmatch(lines.pop(0))
            if match is None or match.group(1) != expected:
                raise CoreError(
                    "managed_instruction_block_invalid",
                    f"managed rule field {expected} is invalid",
                    path=str(path),
                )
            fields[expected] = match.group(2)
        rule = ConfirmedRule.create(
            target=target,
            trigger=fields["When"],
            action=fields["Do"],
            skip_boundary=fields["Skip"],
        )
        if rule.rule_id != stored_id:
            raise CoreError(
                "managed_instruction_rule_id_mismatch",
                "managed rule id does not match its content",
                path=str(path),
                rule_id=stored_id,
            )
        rules.append(rule)
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise CoreError(
            "managed_instruction_rule_duplicate",
            "managed block contains duplicate rule ids",
            path=str(path),
        )
    outside = data[:region_start] + data[region_end:]
    return _Parsed(
        tuple(rules),
        marker_start,
        region_start,
        region_end,
        newline,
        outside,
    )


def _deploy_rules(
    existing: tuple[ConfirmedRule, ...],
    *,
    rule: ConfirmedRule,
    supersedes: tuple[str, ...],
) -> tuple[tuple[ConfirmedRule, ...], str]:
    existing_ids = [item.rule_id for item in existing]
    existing_new_indexes = [
        index for index, item in enumerate(existing) if item.rule_id == rule.rule_id
    ]
    if not supersedes:
        if existing_new_indexes:
            return existing, "noop"
        return (*existing, rule), "deployed"

    missing = [rule_id for rule_id in supersedes if rule_id not in existing_ids]
    if missing:
        raise CoreError(
            "rule_revision_invalid",
            "every superseded rule must exist in the selected target",
            missing_rule_ids=missing,
        )
    if existing_new_indexes and rule.rule_id not in supersedes:
        raise CoreError(
            "instruction_edit_duplicate",
            "edited rule already exists outside the superseded set",
            rule_id=rule.rule_id,
        )

    replaced_indexes = [
        index
        for index, item in enumerate(existing)
        if item.rule_id in supersedes
    ]
    insertion_index = min(replaced_indexes)
    updated = [
        item for item in existing if item.rule_id not in supersedes
    ]
    updated.insert(insertion_index, rule)
    result = tuple(updated)
    if result == existing:
        return existing, "noop"
    return (
        result,
        "consolidated" if len(supersedes) > 1 else "replaced",
    )


def _newline_for_data(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"


def _assert_writable(snapshot: DocumentSnapshot) -> None:
    if snapshot.shadowed:
        raise CoreError(
            "instruction_target_shadowed",
            "a non-empty AGENTS.override.md shadows this target",
            path=str(snapshot.path),
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
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _is_reparse_point(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _assert_physical_parent(
    path: Path, *, allow_missing: bool = False
) -> os.stat_result | None:
    logical = _logical_absolute(path)
    cursor = Path(logical.anchor)
    for part in logical.parts[1:]:
        cursor = cursor / part
        try:
            ancestor = cursor.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            raise CoreError(
                "instruction_parent_unavailable",
                "instruction target parent directory does not exist",
                path=str(cursor),
            )
        except OSError as exc:
            raise CoreError(
                "instruction_parent_unavailable",
                "instruction target parent directory does not exist",
                path=str(cursor),
            ) from exc
        alias = stat.S_ISLNK(ancestor.st_mode) or _is_reparse_point(ancestor)
        if alias and _is_trusted_host_directory_alias(cursor, ancestor):
            try:
                resolved_value = cursor.resolve(strict=True).stat()
            except OSError as exc:
                raise CoreError(
                    "instruction_target_unsafe",
                    "trusted host directory mapping cannot be resolved",
                    path=str(cursor),
                ) from exc
            if not stat.S_ISDIR(resolved_value.st_mode):
                raise CoreError(
                    "instruction_target_unsafe",
                    "trusted host directory mapping is not a directory",
                    path=str(cursor),
                )
            continue
        if not stat.S_ISDIR(ancestor.st_mode) or alias:
            raise CoreError(
                "instruction_target_unsafe",
                "instruction target ancestor is a link, reparse point, or non-directory",
                path=str(cursor),
            )
    try:
        value = logical.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise CoreError(
            "instruction_parent_unavailable",
            "instruction target parent directory does not exist",
            path=str(logical),
        )
    except OSError as exc:
        raise CoreError(
            "instruction_parent_unavailable",
            "instruction target parent directory does not exist",
            path=str(logical),
        ) from exc
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_point(value)
    ):
        raise CoreError(
            "instruction_target_unsafe",
            "instruction target parent is a link, reparse point, or non-directory",
            path=str(logical),
        )
    return value


def assert_physical_directory(path: Path | str) -> None:
    _assert_physical_parent(_logical_absolute(path))


def _assert_physical_target(
    path: Path, *, allow_missing: bool
) -> os.stat_result | None:
    logical = _logical_absolute(path)
    parent = _assert_physical_parent(
        logical.parent,
        allow_missing=allow_missing,
    )
    if parent is None:
        return None
    try:
        value = logical.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise CoreError(
            "instruction_target_unsafe",
            "instruction target disappeared",
            path=str(logical),
        )
    except OSError as exc:
        raise CoreError(
            "instruction_file_unreadable",
            "instruction target metadata cannot be read",
            path=str(logical),
        ) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_point(value)
        or value.st_nlink != 1
    ):
        raise CoreError(
            "instruction_target_unsafe",
            "instruction target must be one regular, non-link file",
            path=str(logical),
            link_count=value.st_nlink,
        )
    return value


def _read_regular_bytes(path: Path) -> tuple[bool, bytes]:
    logical = _logical_absolute(path)
    before = _assert_physical_target(logical, allow_missing=True)
    if before is None:
        return False, b""
    with logical.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise CoreError(
                "instruction_target_unsafe",
                "instruction target changed while it was opened",
                path=str(logical),
            )
        data = handle.read()
    after = _assert_physical_target(logical, allow_missing=False)
    assert after is not None
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        raise CoreError(
            "instruction_target_unsafe",
            "instruction target changed while it was read",
            path=str(logical),
        )
    return True, data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _acquire_file_lock(handle: object) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
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
                raise CoreError(
                    "instruction_lock_timeout",
                    "timed out waiting for instruction target lock",
                ) from exc
            time.sleep(0.05)


def _release_file_lock(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
