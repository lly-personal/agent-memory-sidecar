from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .authorization import Approval, AuthorizationLedger
from .database import CoreDatabase
from .errors import CoreError
from .identity import ProjectIdentity
from .installation import InstallationRegistry
from .instructions import (
    ConfirmedRule,
    FilePlan,
    InstructionRepository,
    PlannedRuleMutation,
    RuleView,
    assert_physical_directory,
    atomic_write,
    normalize_supersedes,
    read_document,
    restore_file,
)
from .proposal import RuleBundle, RuleProposal
from .runtime_ledger import ProposalToken, RuntimeLedger


@dataclass(frozen=True)
class MutationResult:
    action: str
    rule: ConfirmedRule
    plans: tuple[FilePlan, ...]
    publication_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "user_status": (
                "已停用" if self.action == "revoked" else "生效中"
            ),
            "rule": self.rule.to_dict(),
            "files": [plan.to_dict() for plan in self.plans],
            "publication_required": self.publication_required,
        }


@dataclass(frozen=True)
class BundleMutationResult:
    items: tuple[PlannedRuleMutation, ...]
    plans: tuple[FilePlan, ...]
    revision_sha256: str
    publication_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": "bundle_deployed",
            "user_status": "生效中",
            "items": [item.to_dict() for item in self.items],
            "files": [plan.to_dict() for plan in self.plans],
            "revision_sha256": f"sha256:{self.revision_sha256}",
            "publication_required": self.publication_required,
        }


@dataclass(frozen=True)
class RuleRevision:
    proposal_sha256: str
    target_before_sha256: str
    supersedes: tuple[str, ...]
    supersedes_sha256: str
    revision_sha256: str

    @classmethod
    def create(
        cls,
        *,
        proposal: RuleProposal,
        target_before: bytes,
        supersedes: tuple[str, ...],
    ) -> "RuleRevision":
        proposal_sha256 = proposal.proposal_sha256
        target_before_sha256 = _sha256(target_before)
        supersedes_json = json.dumps(
            list(supersedes),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        supersedes_sha256 = _sha256(supersedes_json.encode("utf-8"))
        canonical = json.dumps(
            {
                "contract_version": "rule_revision_v1",
                "instruction_target": proposal.instruction_target,
                "proposal_sha256": proposal_sha256,
                "supersedes": list(supersedes),
                "target_document_sha256": target_before_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            proposal_sha256=proposal_sha256,
            target_before_sha256=target_before_sha256,
            supersedes=supersedes,
            supersedes_sha256=supersedes_sha256,
            revision_sha256=_sha256(canonical.encode("utf-8")),
        )

    @property
    def token_binding(self) -> str:
        return ":".join(
            (
                "r1",
                self.proposal_sha256,
                self.target_before_sha256,
                self.supersedes_sha256,
                self.revision_sha256,
            )
        )


@dataclass(frozen=True)
class RuleBundleRevision:
    bundle_sha256: str
    target_before_sha256: str
    target_after_sha256: str
    revision_sha256: str

    @classmethod
    def create(
        cls,
        *,
        bundle: RuleBundle,
        target_before: bytes,
        target_after: bytes,
    ) -> "RuleBundleRevision":
        before_sha256 = _sha256(target_before)
        after_sha256 = _sha256(target_after)
        canonical = json.dumps(
            {
                "contract_version": "rule_revision_bundle_v2",
                "bundle_sha256": bundle.bundle_sha256,
                "instruction_target": bundle.instruction_target,
                "target_after_sha256": after_sha256,
                "target_before_sha256": before_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            bundle_sha256=bundle.bundle_sha256,
            target_before_sha256=before_sha256,
            target_after_sha256=after_sha256,
            revision_sha256=_sha256(canonical.encode("utf-8")),
        )


class FileTransactionCoordinator:
    def __init__(
        self,
        *,
        db: CoreDatabase,
        authorization: AuthorizationLedger,
        repository: InstructionRepository,
    ) -> None:
        self.db = db
        self.authorization = authorization
        self.repository = repository
        self.journal_root = db.path.parent / "transactions"

    def recover(self) -> list[str]:
        if not self.journal_root.exists():
            return []
        recovered: list[str] = []
        for directory in sorted(self.journal_root.iterdir()):
            if not directory.is_dir():
                continue
            manifest_path = directory / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                transaction_id = str(manifest["transaction_id"])
                files = list(manifest["files"])
                if (
                    manifest.get("contract_version")
                    != "instruction_transaction_v1"
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
                )
                committed = self.authorization.transaction_committed(
                    transaction_id
                )
                with self.repository.lock_paths(paths):
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
                shutil.rmtree(directory)
                recovered.append(transaction_id)
            except CoreError:
                raise
            except Exception as exc:
                raise CoreError(
                    "instruction_recovery_failed",
                    "an incomplete instruction transaction could not be recovered",
                    journal=str(directory),
                ) from exc
        if self.journal_root.exists() and not any(self.journal_root.iterdir()):
            self.journal_root.rmdir()
        return recovered

    def _validate_journal_files(
        self,
        *,
        directory: Path,
        files: list[Any],
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
            if (
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
    ) -> str:
        self.recover()
        transaction_id = f"tx_{uuid.uuid4().hex}"
        paths = [plan.path for plan in plans]
        with self.repository.lock_paths(paths):
            self._assert_unchanged(plans)
            journal = self._write_journal(
                transaction_id=transaction_id,
                plans=plans,
            )
            committed = False
            try:
                for plan in plans:
                    if plan.after != plan.before:
                        atomic_write(plan.path, plan.after)
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
                shutil.rmtree(journal)
                if (
                    self.journal_root.exists()
                    and not any(self.journal_root.iterdir())
                ):
                    self.journal_root.rmdir()
                return transaction_id
            except BaseException:
                if not committed:
                    for plan in reversed(plans):
                        restore_file(
                            path=plan.path,
                            existed=plan.existed,
                            data=plan.before,
                        )
                    shutil.rmtree(journal, ignore_errors=True)
                    if (
                        self.journal_root.exists()
                        and not any(self.journal_root.iterdir())
                    ):
                        self.journal_root.rmdir()
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
    ) -> Path:
        self.journal_root.mkdir(parents=True, exist_ok=True)
        directory = self.journal_root / transaction_id
        directory.mkdir(exist_ok=False)
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
                "contract_version": "instruction_transaction_v1",
                "transaction_id": transaction_id,
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
            shutil.rmtree(directory, ignore_errors=True)
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


class RuleService:
    def __init__(
        self,
        *,
        db: CoreDatabase,
        identity: ProjectIdentity,
        repository: InstructionRepository | None = None,
    ) -> None:
        self.db = db
        self.identity = identity
        self.repository = repository or InstructionRepository()
        self.runtime = RuntimeLedger(db)
        self.authorization = AuthorizationLedger(db, self.runtime)
        self.installation = InstallationRegistry(db)
        self.coordinator = FileTransactionCoordinator(
            db=db,
            authorization=self.authorization,
            repository=self.repository,
        )

    def list(self, *, target: str | None = None) -> dict[str, Any]:
        self.coordinator.recover()
        if target not in {None, "global_agents", "project_agents"}:
            raise CoreError(
                "invalid_request",
                "target must be global_agents or project_agents",
                target=target,
            )
        snapshots = self.repository.list_targets(
            identity=self.identity,
            target=target,
        )
        views = [
            RuleView(
                rule=rule,
                path=snapshot.path,
                shadowed=snapshot.shadowed,
            )
            for snapshot in snapshots
            for rule in snapshot.rules
        ]
        pending_count = self.runtime.pending_count(
            scope_key=self.identity.scope_key
        )
        return {
            "pending_count": pending_count,
            "rules": [view.to_dict() for view in views],
            "targets": [snapshot.capacity_dict() for snapshot in snapshots],
            "state_counts": {
                "待确认": pending_count,
                "生效中": sum(not view.shadowed for view in views),
                "已停用": sum(view.shadowed for view in views),
            },
        }

    def create_proposal(
        self,
        *,
        source_event_ref: str,
        proposal: RuleProposal,
        supersedes: str | Sequence[str] | None = None,
        replace: bool = False,
    ) -> tuple[ProposalToken, RuleRevision]:
        _normalized, plans, revision = self._prepare_deploy(
            proposal=proposal,
            supersedes=supersedes,
        )
        if all(plan.action == "noop" for plan in plans):
            raise CoreError(
                "rule_already_covered",
                "the exact confirmed rule already exists in the selected target",
                rule_id=plans[0].rule.rule_id,
            )
        token = self.runtime.create_proposal(
            source_event_ref=source_event_ref,
            identity=self.identity,
            proposal=proposal,
            proposal_sha256=revision.token_binding,
            replace=replace,
        )
        return token, revision

    def deploy(
        self,
        *,
        proposal: RuleProposal,
        approval_ref: str,
        supersedes: str | Sequence[str] | None = None,
        pending: ProposalToken | None = None,
    ) -> MutationResult:
        approval = self.authorization.validate(
            approval_ref=approval_ref,
            identity=self.identity,
        )
        normalized, plans, revision = self._prepare_deploy(
            proposal=proposal,
            supersedes=supersedes,
        )
        if pending is not None:
            if (
                pending.source_session != approval.event.source_session
                or pending.scope_key != approval.event.scope_key
                or pending.scope != proposal.scope
                or pending.instruction_target != proposal.instruction_target
            ):
                raise CoreError(
                    "proposal_invalid",
                    "pending proposal does not match the approving prompt",
                )
            _assert_pending_revision(
                pending=pending,
                proposal=proposal,
                revision=revision,
                supersedes=normalized,
            )
        rule = plans[0].rule
        action = plans[0].action

        def commit(transaction_id: str) -> None:
            if pending is not None:
                self.runtime.delete_proposal(pending.token_id)
            self.authorization.consume(
                approval=approval,
                operation=(
                    "proposal.confirm"
                    if pending is not None
                    else "rule.deploy"
                ),
                request_sha256=revision.revision_sha256,
                result_rule_id=rule.rule_id,
                transaction_id=transaction_id,
            )
            if proposal.scope == "global":
                self._update_global_binding_after(plans)

        self.coordinator.apply(plans=plans, database_commit=commit)
        return MutationResult(
            action=action,
            rule=rule,
            plans=plans,
            publication_required=proposal.scope == "global",
        )

    def deploy_bundle(
        self,
        *,
        bundle: RuleBundle,
        approval_ref: str,
    ) -> BundleMutationResult:
        approval = self.authorization.validate(
            approval_ref=approval_ref,
            identity=self.identity,
        )
        plans, items, revision = self._prepare_bundle_deploy(bundle=bundle)
        self.authorization.validate_prompt_content(
            approval=approval,
            expected_prompt=bundle.confirmation_text,
        )

        def commit(transaction_id: str) -> None:
            self.authorization.consume(
                approval=approval,
                operation="rule.deploy_bundle",
                request_sha256=revision.revision_sha256,
                result_rule_id=None,
                transaction_id=transaction_id,
            )
            if bundle.scope == "global":
                self._update_global_binding_after(plans)

        self.coordinator.apply(plans=plans, database_commit=commit)
        return BundleMutationResult(
            items=items,
            plans=plans,
            revision_sha256=revision.revision_sha256,
            publication_required=bundle.scope == "global",
        )

    def revoke(
        self,
        *,
        rule_id: str,
        approval_ref: str,
    ) -> MutationResult:
        approval = self.authorization.validate(
            approval_ref=approval_ref,
            identity=self.identity,
        )
        view = self.repository.find_rule(
            rule_id=rule_id,
            identity=self.identity,
        )
        plans = self._revoke_plans(rule=view.rule)

        def commit(transaction_id: str) -> None:
            self.authorization.consume(
                approval=approval,
                operation="rule.revoke",
                request_sha256=view.rule.content_sha256,
                result_rule_id=view.rule.rule_id,
                transaction_id=transaction_id,
            )
            if view.rule.target == "global_agents":
                self._update_global_binding_after(plans)

        self.coordinator.apply(plans=plans, database_commit=commit)
        return MutationResult(
            action="revoked",
            rule=view.rule,
            plans=plans,
            publication_required=view.rule.target == "global_agents",
        )

    def confirm_proposal(
        self,
        *,
        proposal: RuleProposal,
        approval_ref: str,
        supersedes: str | Sequence[str] | None = None,
    ) -> MutationResult:
        _approval, token = self.runtime.pending_for_approval(
            approval_ref=approval_ref,
            identity=self.identity,
            proposal=None,
        )
        return self.deploy(
            proposal=proposal,
            approval_ref=approval_ref,
            supersedes=supersedes,
            pending=token,
        )

    def discard_proposal(self, *, approval_ref: str) -> dict[str, Any]:
        approval, token = self.runtime.pending_for_approval(
            approval_ref=approval_ref,
            identity=self.identity,
            proposal=None,
        )
        with self.db.transaction():
            self.runtime.delete_proposal(token.token_id)
            self.authorization.consume(
                approval=Approval(
                    approval_ref=approval_ref,
                    approval_ref_sha256=hashlib.sha256(
                        approval_ref.encode("utf-8")
                    ).hexdigest(),
                    event=approval,
                ),
                operation="proposal.discard",
                request_sha256=token.proposal_sha256,
                result_rule_id=None,
                transaction_id=None,
            )
        return {"discarded": True}

    def _deploy_plans(
        self,
        *,
        proposal: RuleProposal,
        supersedes: tuple[str, ...],
    ) -> tuple[FilePlan, ...]:
        if proposal.scope == "project":
            return (
                self.repository.plan_deploy(
                    proposal=proposal,
                    identity=self.identity,
                    supersedes=supersedes,
                ),
            )
        source, target = self._global_paths_and_assert_parity()
        source_plan = self.repository.plan_deploy(
            proposal=proposal,
            identity=self.identity,
            supersedes=supersedes,
            path=source,
        )
        target_plan = self.repository.plan_deploy(
            proposal=proposal,
            identity=self.identity,
            supersedes=supersedes,
            path=target,
        )
        self._assert_same_global_plan(source_plan, target_plan)
        return source_plan, target_plan

    def _deploy_bundle_plans(
        self,
        *,
        bundle: RuleBundle,
    ) -> tuple[tuple[FilePlan, ...], tuple[PlannedRuleMutation, ...]]:
        if bundle.scope == "project":
            plan, items = self.repository.plan_deploy_bundle(
                items=bundle.items,
                identity=self.identity,
            )
            return (plan,), items
        source, target = self._global_paths_and_assert_parity()
        source_plan, source_items = self.repository.plan_deploy_bundle(
            items=bundle.items,
            identity=self.identity,
            path=source,
        )
        target_plan, target_items = self.repository.plan_deploy_bundle(
            items=bundle.items,
            identity=self.identity,
            path=target,
        )
        self._assert_same_global_plan(source_plan, target_plan)
        if source_items != target_items:
            raise CoreError(
                "global_instruction_plan_mismatch",
                "global source and local target produced different bundle items",
            )
        return (source_plan, target_plan), source_items

    def _prepare_deploy(
        self,
        *,
        proposal: RuleProposal,
        supersedes: str | Sequence[str] | None,
    ) -> tuple[tuple[str, ...], tuple[FilePlan, ...], RuleRevision]:
        normalized = normalize_supersedes(supersedes)
        plans = self._deploy_plans(
            proposal=proposal,
            supersedes=normalized,
        )
        revision = RuleRevision.create(
            proposal=proposal,
            target_before=plans[0].before,
            supersedes=normalized,
        )
        return normalized, plans, revision

    def _prepare_bundle_deploy(
        self,
        *,
        bundle: RuleBundle,
    ) -> tuple[
        tuple[FilePlan, ...],
        tuple[PlannedRuleMutation, ...],
        RuleBundleRevision,
    ]:
        plans, items = self._deploy_bundle_plans(bundle=bundle)
        actual_before_sha256 = _sha256(plans[0].before)
        if actual_before_sha256 != bundle.target_before_sha256:
            raise CoreError(
                "rule_revision_stale",
                "instruction target changed after the Review Pack selection was rendered",
                expected_target_before_sha256=bundle.target_before_sha256,
                actual_target_before_sha256=actual_before_sha256,
            )
        revision = RuleBundleRevision.create(
            bundle=bundle,
            target_before=plans[0].before,
            target_after=plans[0].after,
        )
        return plans, items, revision

    def _revoke_plans(
        self, *, rule: ConfirmedRule
    ) -> tuple[FilePlan, ...]:
        if rule.target == "project_agents":
            return (
                self.repository.plan_revoke(
                    rule_id=rule.rule_id,
                    identity=self.identity,
                ),
            )
        source, target = self._global_paths_and_assert_parity()
        source_plan = self.repository.plan_revoke(
            rule_id=rule.rule_id,
            identity=self.identity,
            path=source,
            target="global_agents",
        )
        target_plan = self.repository.plan_revoke(
            rule_id=rule.rule_id,
            identity=self.identity,
            path=target,
            target="global_agents",
        )
        self._assert_same_global_plan(source_plan, target_plan)
        return source_plan, target_plan

    def _global_paths_and_assert_parity(self) -> tuple[Path, Path]:
        binding = self.installation.global_binding()
        if binding is None:
            raise CoreError(
                "global_binding_missing",
                "global rules require a configured portable source",
            )
        assert_physical_directory(binding.source_root)
        source = binding.source_file
        target = self.repository.target_path(
            target="global_agents",
            identity=self.identity,
        )
        source_snapshot = read_document(
            path=source,
            target="global_agents",
        )
        target_snapshot = self.repository.read_target(
            target="global_agents",
            identity=self.identity,
        )
        if target_snapshot.shadowed:
            raise CoreError(
                "instruction_target_shadowed",
                "global target is shadowed by AGENTS.override.md",
            )
        if (
            source_snapshot.data != target_snapshot.data
            or source_snapshot.file_sha256 != binding.source_file_sha256
            or target_snapshot.file_sha256 != binding.target_file_sha256
        ):
            raise CoreError(
                "global_instruction_drift",
                "global source, binding, and local target do not have full-document parity",
                source_path=str(source),
                target_path=str(target),
            )
        return source, target

    def _assert_same_global_plan(
        self, source: FilePlan, target: FilePlan
    ) -> None:
        if (
            source.after != target.after
            or source.after_rules != target.after_rules
            or source.action != target.action
        ):
            raise CoreError(
                "global_instruction_plan_mismatch",
                "global source and local target produced different mutations",
            )

    def _update_global_binding_after(
        self, plans: tuple[FilePlan, ...]
    ) -> None:
        binding = self.installation.global_binding()
        if binding is None or len(plans) != 2:
            raise CoreError(
                "global_binding_missing",
                "global binding disappeared during mutation",
            )
        digest = _sha256(plans[0].after)
        self.installation.bind_global(
            source_root=binding.source_root,
            source_commit=binding.source_commit,
            source_file_sha256=digest,
            target_file_sha256=digest,
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


def _assert_pending_revision(
    *,
    pending: ProposalToken,
    proposal: RuleProposal,
    revision: RuleRevision,
    supersedes: tuple[str, ...],
) -> None:
    stored = pending.proposal_sha256
    if stored == proposal.proposal_sha256:
        if supersedes:
            raise CoreError(
                "rule_revision_invalid",
                "a legacy add-only proposal cannot acquire superseded rules",
            )
        return
    parts = stored.split(":")
    if len(parts) != 5 or parts[0] != "r1":
        raise CoreError(
            "proposal_invalid",
            "pending proposal hash contract is not recognized",
        )
    _, proposal_sha256, before_sha256, supersedes_sha256, revision_sha256 = parts
    if proposal_sha256 != revision.proposal_sha256:
        raise CoreError(
            "proposal_invalid",
            "proposal content does not match the pending token",
        )
    if before_sha256 != revision.target_before_sha256:
        raise CoreError(
            "rule_revision_stale",
            "instruction target changed after proposal creation",
        )
    if (
        supersedes_sha256 != revision.supersedes_sha256
        or revision_sha256 != revision.revision_sha256
    ):
        raise CoreError(
            "rule_revision_invalid",
            "superseded rules do not match the pending revision",
        )
