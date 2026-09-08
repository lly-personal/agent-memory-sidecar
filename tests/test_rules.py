from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar.database import CoreDatabase
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.identity import ProjectIdentity
from agent_memory_sidecar.installation import InstallationRegistry
from agent_memory_sidecar.instructions import (
    ConfirmedRule,
    DocumentSnapshot,
    InstructionRepository,
    MAX_MANAGED_BLOCK_BYTES,
    MAX_RENDERED_RULE_BYTES,
    managed_block_bytes,
    plan_replace,
    render_rule,
)
from agent_memory_sidecar.proposal import (
    RuleBundle,
    RuleProposal,
    review_selection_token,
)
from agent_memory_sidecar.rule_service import RuleService
from agent_memory_sidecar.rule_preview import preview_bundle
from agent_memory_sidecar.runtime_ledger import RuntimeLedger


class RuleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.codex = self.root / "codex"
        self.codex.mkdir()
        self.store = self.root / "memory.sqlite"
        self.identity = ProjectIdentity(
            cwd=str(self.project),
            repo_root=str(self.project),
            branch="main",
            scope_key=str(self.project.resolve()),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_project_deploy_list_and_revoke_use_actual_target(self) -> None:
        original = b"# User-owned guidance\r\n\r\n- Keep this byte-for-byte.\r\n"
        target = self.project / "AGENTS.md"
        target.write_bytes(original)
        with self._database() as db:
            service = self._service(db)
            proposal = _proposal()
            deploy_ref = self._prompt(db, "remember")
            result = service.deploy(
                proposal=proposal,
                approval_ref=deploy_ref,
            )
            self.assertEqual(result.action, "deployed")
            self.assertFalse(result.publication_required)
            self.assertTrue(result.plans[0].outside_unchanged)
            self.assertIn(original, target.read_bytes())
            listing = service.list()
            self.assertEqual(listing["state_counts"]["生效中"], 1)
            rule_id = listing["rules"][0]["id"]
            revoke_ref = self._prompt(db, "revoke")
            revoked = service.revoke(
                rule_id=rule_id,
                approval_ref=revoke_ref,
            )
            self.assertEqual(revoked.action, "revoked")
            self.assertEqual(service.list()["rules"], [])
            self.assertEqual(target.read_bytes(), original)

    def test_rule_list_reports_capacity_for_both_actual_targets(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project\r\n")
        with self._database() as db:
            service = self._service(db)
            service.deploy(
                proposal=_proposal(),
                approval_ref=self._prompt(db, "remember"),
            )
            listing = service.list()
        capacities = {
            item["instruction_target"]: item
            for item in listing["targets"]
        }
        project = capacities["project_agents"]
        self.assertEqual(project["managed_block_budget_bytes"], 8192)
        self.assertEqual(
            project["remaining_bytes"],
            8192 - project["managed_block_bytes"],
        )
        self.assertEqual(project["document_bytes"], len(target.read_bytes()))
        self.assertEqual(project["rule_count"], 1)
        self.assertEqual(
            capacities["global_agents"]["managed_block_bytes"],
            0,
        )

    def test_target_scoped_list_is_not_blocked_by_unrelated_invalid_target(self) -> None:
        (self.codex / "AGENTS.md").write_bytes(b"# Global owner\n")
        (self.project / "AGENTS.md").write_text(
            "<!-- agent-memory:confirmed-rules:start -->\n"
            "## Confirmed collaboration rules\n\n"
            "### rule_000000000000\n"
            "- When: Invalid project rule.\n"
            "- Do: Fail parsing.\n"
            "- Skip: Never.\n"
            "<!-- agent-memory:confirmed-rules:end -->\n",
            encoding="utf-8",
        )
        with self._database() as db:
            service = self._service(db)
            scoped = service.list(target="global_agents")
            self.assertEqual(len(scoped["targets"]), 1)
            self.assertEqual(
                scoped["targets"][0]["instruction_target"],
                "global_agents",
            )
            with self.assertRaises(CoreError):
                service.list()

    def test_approval_aliases_and_legacy_hashes_cannot_reuse_one_event(self) -> None:
        with self._database() as db:
            service = self._service(db)
            approval = self._prompt(db, "remember")
            service.deploy(proposal=_proposal(), approval_ref=approval)
            target = self.project / "AGENTS.md"
            before = target.read_bytes()
            # A pre-fix Store may contain a noncanonical hash for this event.
            db.conn.execute(
                "UPDATE approval_consumptions SET approval_ref_sha256 = ?",
                (hashlib.sha256(f" {approval} ".encode()).hexdigest(),),
            )
            for alias in (approval, f" {approval} ", approval.replace(":", ": ", 1)):
                with self.subTest(alias=alias):
                    with self.assertRaises(CoreError) as caught:
                        service.deploy(proposal=_proposal(action="A different rule."), approval_ref=alias)
                    self.assertEqual(caught.exception.code, "approval_invalid")
                    self.assertEqual(before, target.read_bytes())
            self.assertEqual(1, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_consumption_rechecks_event_after_two_validations(self) -> None:
        with self._database() as db:
            service = self._service(db)
            ref = self._prompt(db, "remember")
            first = service.authorization.validate(approval_ref=ref, identity=self.identity)
            second = service.authorization.validate(approval_ref=f" {ref} ", identity=self.identity)
            with db.transaction():
                service.authorization.consume(approval=first, operation="test", request_sha256=None,
                                              result_rule_id=None, transaction_id=None)
            with self.assertRaises(CoreError), db.transaction():
                service.authorization.consume(approval=second, operation="test", request_sha256=None,
                                              result_rule_id=None, transaction_id=None)
            self.assertEqual(1, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_scoped_list_never_recovers_an_uncommitted_project_journal(self) -> None:
        with self._database() as db:
            service = self._service(db)
            plan = service._deploy_plans(proposal=_proposal(), supersedes=())
            journal = service.coordinator._write_journal(transaction_id="tx_read_only", plans=plan,
                                                         source_event_id=self._prompt(db, "interrupted").split(":", 1)[1])
            plan[0].path.write_bytes(plan[0].after)
            before = {p.name: p.read_bytes() for p in journal.iterdir()}
            service.list(target="global_agents")
            self.assertEqual(plan[0].after, plan[0].path.read_bytes())
            self.assertEqual(before, {p.name: p.read_bytes() for p in journal.iterdir()})
            self.assertEqual(0, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_post_commit_cleanup_error_preserves_result_and_reports_commit(self) -> None:
        with self._database() as db:
            service = self._service(db)
            ref = self._prompt(db, "remember")
            with patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=PermissionError("busy")):
                with self.assertRaises(CoreError) as caught:
                    service.deploy(proposal=_proposal(), approval_ref=ref)
            self.assertEqual("instruction_cleanup_required", caught.exception.code)
            for field in ("operation_committed", "approval_consumed", "recovery_required"):
                self.assertIs(True, caught.exception.details[field])
            after = (self.project / "AGENTS.md").read_bytes()
            self.assertEqual(1, service.list(target="project_agents")["state_counts"]["生效中"])
            self.assertEqual(1, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])
            with self.assertRaises(CoreError):
                service.deploy(proposal=_proposal(), approval_ref=ref)
            service.coordinator.recover()
            self.assertEqual(after, (self.project / "AGENTS.md").read_bytes())
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_authorized_global_deploy_recovers_before_parity_planning(self) -> None:
        source_root = self.root / "global-source"
        source_file = source_root / "global" / "AGENTS.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_bytes(b"# Global\n")
        target = self.codex / "AGENTS.md"
        target.write_bytes(source_file.read_bytes())
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(source_root=source_root, source_commit="a" * 40,
                                                    source_file_sha256=digest, target_file_sha256=digest)
            service = self._service(db)
            proposal = _proposal(scope="global", target="global_agents")
            plans = service._deploy_plans(proposal=proposal, supersedes=())
            journal = service.coordinator._write_journal(transaction_id="tx_interrupted_global", plans=plans,
                                                         source_event_id=self._prompt(db, "interrupted").split(":", 1)[1])
            for plan in plans:
                plan.path.write_bytes(plan.after)
            before = [plan.path.read_bytes() for plan in plans]
            service.list(target="global_agents")
            with self.assertRaises(CoreError):
                service.deploy(proposal=proposal, approval_ref="invalid")
            self.assertEqual(before, [plan.path.read_bytes() for plan in plans])
            self.assertTrue(journal.is_dir())
            result = service.deploy(proposal=proposal, approval_ref=self._prompt(db, "recover and deploy"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(source_file.read_bytes(), target.read_bytes())
            self.assertFalse(journal.exists())
            self.assertEqual(1, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_partial_committed_cleanup_remains_retryable(self) -> None:
        with self._database() as db:
            service = self._service(db)

            def partial_cleanup(directory, *args, **kwargs):
                (Path(directory) / "0.before").unlink()
                raise PermissionError("cleanup stopped after its first file")

            with patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=partial_cleanup):
                with self.assertRaises(CoreError) as caught:
                    service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertEqual("instruction_cleanup_required", caught.exception.code)
            after = (self.project / "AGENTS.md").read_bytes()
            self.assertEqual(1, service.list()["state_counts"]["生效中"])
            result = service.deploy(proposal=_proposal(action="A second behavior."),
                                    approval_ref=self._prompt(db, "add a second behavior"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(2, service.list()["state_counts"]["生效中"])
            self.assertEqual(2, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])
            self.assertNotEqual(after, (self.project / "AGENTS.md").read_bytes())
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_recovery_waits_before_checking_snapshots_removed_by_another_executor(self) -> None:
        with self._database() as db:
            service = self._service(db)
            plans = service._deploy_plans(proposal=_proposal(), supersedes=())
            journal = service.coordinator._write_journal(transaction_id="tx_concurrent_cleanup", plans=plans,
                source_event_id=self._prompt(db, "interrupted").split(":", 1)[1])
            validate = service.coordinator._validate_journal_files

            def retire_before_validation(**kwargs):
                journal.rename(journal.with_name(f".cleanup-{journal.name}"))
                return validate(**kwargs)

            with patch.object(service.coordinator, "_validate_journal_files", side_effect=retire_before_validation):
                service.coordinator.recover()
            self.assertFalse((self.project / "AGENTS.md").exists())
            service.coordinator.recover()
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_partial_cleanup_after_rollback_preserves_before_state(self) -> None:
        with self._database() as db:
            service = self._service(db)

            def partial_cleanup(directory, *args, **kwargs):
                (Path(directory) / "0.before").unlink()
                raise PermissionError("cleanup stopped")

            with patch.object(service.authorization, "consume", side_effect=RuntimeError("commit rejected")):
                with patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=partial_cleanup):
                    with self.assertRaisesRegex(RuntimeError, "commit rejected"):
                        service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertFalse((self.project / "AGENTS.md").exists())
            self.assertEqual(0, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])
            result = service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "retry"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(1, service.list()["state_counts"]["生效中"])
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_cleanup_completed_by_another_executor_reports_success(self) -> None:
        with self._database() as db:
            service = self._service(db)
            remove = shutil.rmtree

            def concurrent_cleanup(directory, *args, **kwargs):
                remove(directory, *args, **kwargs)
                raise FileNotFoundError("another executor already completed cleanup")

            with patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=concurrent_cleanup):
                result = service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(1, service.list()["state_counts"]["生效中"])
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_recovery_rejects_an_aliased_journal_root_without_deleting_external_data(self) -> None:
        external = self.root / "outside-journal-owner"
        garbage = external / (".cleanup-tx_" + "a" * 32)
        garbage.mkdir(parents=True)
        sentinel = garbage / "user-data.txt"
        sentinel.write_bytes(b"outside the journal owner")
        with self._database() as db:
            service = self._service(db)
            alias = service.coordinator.journal_root
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(external)],
                               check=True, capture_output=True)
            else:
                alias.symlink_to(external, target_is_directory=True)
            with self.assertRaises(CoreError) as caught:
                service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertEqual("instruction_target_unsafe", caught.exception.code)
            self.assertEqual(b"outside the journal owner", sentinel.read_bytes())
            self.assertFalse((self.project / "AGENTS.md").exists())
            self.assertEqual(0, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_cleanup_removed_before_physical_recheck_is_complete(self) -> None:
        with self._database() as db:
            service = self._service(db)
            rename = Path.rename

            def cleanup_after_rename(path, target):
                result = rename(path, target)
                if Path(target).name.startswith(".cleanup-tx_"):
                    shutil.rmtree(target)
                return result

            with patch.object(Path, "rename", new=cleanup_after_rename):
                result = service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(1, service.list()["state_counts"]["生效中"])
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_cleanup_tolerates_a_concurrently_removed_child_on_older_python(self) -> None:
        with self._database() as db:
            service = self._service(db)
            remove = shutil.rmtree

            def older_python_cleanup(directory, *args, **kwargs):
                child = Path(directory) / "0.before"
                child.unlink()
                error = FileNotFoundError("another executor removed this child")
                handler = kwargs.get("onerror")
                if handler is None:
                    raise error
                handler(os.unlink, str(child), (FileNotFoundError, error, None))
                remove(directory, *args, **kwargs)

            with patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=older_python_cleanup):
                result = service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            self.assertEqual("deployed", result.action)
            self.assertEqual(1, service.list()["state_counts"]["生效中"])
            self.assertFalse(service.coordinator.journal_root.exists())

    def test_committed_cleanup_recovery_survives_runtime_event_retention(self) -> None:
        self._assert_recovery_after_event_retention(committed_marker=True)

    def test_recovery_preserves_unknown_commit_after_event_retention(self) -> None:
        self._assert_recovery_after_event_retention(committed_marker=False)

    def test_legacy_committed_journal_survives_runtime_retention(self) -> None:
        self._assert_recovery_after_event_retention(committed_marker=True, legacy=True)

    def test_legacy_unproven_journal_preserves_targets(self) -> None:
        self._assert_recovery_after_event_retention(committed_marker=False, legacy=True)

    def _assert_recovery_after_event_retention(self, *, committed_marker: bool, legacy: bool = False) -> None:
        with self._database() as db:
            service = self._service(db)
            set_state = service.coordinator._set_journal_state

            def fail_committed_marker(directory: Path, state: str) -> None:
                if state == "committed":
                    raise PermissionError("busy")
                set_state(directory, state)

            fault = (patch("agent_memory_sidecar.rule_service.shutil.rmtree", side_effect=PermissionError("busy"))
                     if committed_marker else patch.object(service.coordinator, "_set_journal_state", side_effect=fail_committed_marker))
            with fault, self.assertRaises(CoreError):
                service.deploy(proposal=_proposal(), approval_ref=self._prompt(db, "remember"))
            if legacy:
                manifest_path = next(service.coordinator.journal_root.glob("*/manifest.json"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["contract_version"] = "instruction_transaction_v1"
                del manifest["source_event_id"]
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            target = self.project / "AGENTS.md"
            after = target.read_bytes()
            RuntimeLedger(db).capture_prompt(identity=self.identity, source_session="later", prompt="a later task", metadata={},
                                            now=(datetime.now(UTC) + timedelta(days=8)).isoformat())
            self.assertEqual(0, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])
            if committed_marker:
                service.coordinator.recover()
                self.assertFalse(service.coordinator.journal_root.exists())
            else:
                with self.assertRaises(CoreError) as raised:
                    service.coordinator.recover()
                self.assertEqual("instruction_recovery_unproven", raised.exception.code)
                self.assertTrue(service.coordinator.journal_root.exists())
            self.assertEqual(after, target.read_bytes())

    def test_recovery_rechecks_commit_after_acquiring_file_locks(self) -> None:
        with self._database() as db:
            service = self._service(db)
            ref = self._prompt(db, "remember")
            approval = service.authorization.validate(approval_ref=ref, identity=self.identity)
            plans = service._deploy_plans(proposal=_proposal(), supersedes=())
            transaction_id = "tx_concurrent_commit"
            journal = service.coordinator._write_journal(transaction_id=transaction_id, plans=plans,
                                                         source_event_id=approval.event.event_id)
            plans[0].path.write_bytes(plans[0].after)
            lock_paths = service.repository.lock_paths

            @contextmanager
            def commit_before_lock_is_acquired(paths):
                with lock_paths(paths):
                    with db.transaction():
                        service.authorization.consume(approval=approval, operation="rule.deploy", request_sha256=None,
                                                      result_rule_id=plans[0].rule.rule_id, transaction_id=transaction_id)
                    service.coordinator._set_journal_state(journal, "committed")
                    yield

            with patch.object(service.repository, "lock_paths", commit_before_lock_is_acquired):
                service.coordinator.recover()
            self.assertEqual(plans[0].after, plans[0].path.read_bytes())
            self.assertEqual(1, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_consumption_rejects_a_prompt_replaced_after_validation(self) -> None:
        with self._database() as db:
            service = self._service(db)
            ref = self._prompt(db, "remember")
            prepare = service._prepare_deploy

            def replace_prompt_then_plan(**kwargs):
                self._prompt(db, "a later request")
                return prepare(**kwargs)

            with patch.object(service, "_prepare_deploy", side_effect=replace_prompt_then_plan):
                with self.assertRaises(CoreError) as raised:
                    service.deploy(proposal=_proposal(), approval_ref=ref)
            self.assertEqual("approval_invalid", raised.exception.code)
            self.assertFalse((self.project / "AGENTS.md").exists())
            self.assertEqual(0, db.conn.execute("SELECT count(*) FROM approval_consumptions").fetchone()[0])

    def test_recovery_empty_root_cleanup_is_idempotent(self) -> None:
        with self._database() as db:
            service = self._service(db)
            rmdir = Path.rmdir

            def removed_by_other_executor(path):
                rmdir(path)
                raise FileNotFoundError("another executor already removed the empty root")

            for method in ("iterdir", "rmdir"):
                with self.subTest(method=method):
                    service.coordinator.journal_root.mkdir()
                    with patch.object(Path, method, removed_by_other_executor):
                        self.assertEqual([], service.coordinator.recover())
                    self.assertFalse(service.coordinator.journal_root.exists())

    def test_approval_is_current_scope_bound_and_single_use(self) -> None:
        with self._database() as db:
            service = self._service(db)
            approval = self._prompt(db, "remember")
            service.deploy(
                proposal=_proposal(),
                approval_ref=approval,
            )
            with self.assertRaises(CoreError) as reused:
                service.deploy(
                    proposal=_proposal(),
                    approval_ref=approval,
                )
            self.assertEqual(reused.exception.code, "approval_invalid")
            other = ProjectIdentity(
                cwd=str(self.root / "secondary"),
                repo_root=str(self.root / "secondary"),
                branch="main",
                scope_key=str((self.root / "secondary").resolve()),
            )
            with self.assertRaises(CoreError) as mismatch:
                RuleService(
                    db=db,
                    identity=other,
                    repository=self._repository(),
                ).deploy(
                    proposal=_proposal(action="Another action."),
                    approval_ref=self._prompt(db, "new"),
                )
            self.assertEqual(mismatch.exception.code, "scope_mismatch")

    def test_project_target_is_primary_scope_even_without_git(self) -> None:
        primary = self.root / "plain-primary"
        secondary = self.root / "secondary-resource"
        primary.mkdir()
        secondary.mkdir()
        identity = ProjectIdentity(
            cwd=str(secondary),
            repo_root=None,
            branch=None,
            scope_key=str(primary.resolve()),
        )
        with self._database() as db:
            event = RuntimeLedger(db).capture_prompt(
                identity=identity,
                source_session="plain-folder",
                prompt="remember in primary",
                metadata={},
            )
            result = RuleService(
                db=db,
                identity=identity,
                repository=self._repository(),
            ).deploy(
                proposal=_proposal(),
                approval_ref=f"user_prompt:{event.event_id}",
            )
        self.assertTrue(
            result.plans[0].path.samefile(primary / "AGENTS.md")
        )
        self.assertTrue((primary / "AGENTS.md").is_file())
        self.assertFalse((secondary / "AGENTS.md").exists())

    def test_proposal_body_is_not_persisted_and_confirm_is_hash_bound(self) -> None:
        with self._database() as db:
            ledger = RuntimeLedger(db)
            proposal = _proposal()
            source = self._prompt(db, "source")
            token = ledger.create_proposal(
                source_event_ref=source,
                identity=self.identity,
                proposal=proposal,
            )
            row_text = str(
                dict(
                    db.conn.execute(
                        "SELECT * FROM proposal_tokens"
                    ).fetchone()
                )
            )
            self.assertNotIn(proposal.why, row_text)
            self.assertNotIn(proposal.evidence, row_text)
            confirm = self._prompt(db, "confirm")
            with self.assertRaises(CoreError) as changed:
                self._service(db).confirm_proposal(
                    proposal=_proposal(action="Changed action."),
                    approval_ref=confirm,
                )
            self.assertEqual(changed.exception.code, "proposal_invalid")
            confirm2 = self._prompt(db, "confirm again")
            result = self._service(db).confirm_proposal(
                proposal=proposal,
                approval_ref=confirm2,
            )
            self.assertEqual(result.action, "deployed")
            self.assertIsNotNone(token.token_id)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM proposal_tokens"
                ).fetchone()[0],
                0,
            )

    def test_replaced_and_expired_proposal_tokens_cannot_deploy(self) -> None:
        with self._database() as db:
            ledger = RuntimeLedger(db)
            original = _proposal()
            revised = _proposal(action="Use the revised action.")
            source = self._prompt(db, "source")
            old = ledger.create_proposal(
                source_event_ref=source,
                identity=self.identity,
                proposal=original,
            )
            current = ledger.create_proposal(
                source_event_ref=source,
                identity=self.identity,
                proposal=revised,
                replace=True,
            )
            self.assertNotEqual(old.token_id, current.token_id)
            confirm = self._prompt(db, "confirm old card")
            with self.assertRaises(CoreError) as replaced:
                self._service(db).confirm_proposal(
                    proposal=original,
                    approval_ref=confirm,
                )
            self.assertEqual(replaced.exception.code, "proposal_invalid")

            db.conn.execute(
                """
                UPDATE proposal_tokens
                SET expires_at = '2000-01-01T00:00:00+00:00'
                WHERE token_id = ?
                """,
                (current.token_id,),
            )
            db.conn.commit()
            expired_confirm = self._prompt(db, "confirm expired card")
            with self.assertRaises(CoreError) as expired:
                self._service(db).confirm_proposal(
                    proposal=revised,
                    approval_ref=expired_confirm,
                )
            self.assertEqual(expired.exception.code, "proposal_invalid")
            self.assertFalse((self.project / "AGENTS.md").exists())

    def test_global_deploy_updates_source_and_target_or_restores_both(self) -> None:
        source_root = self.root / "global-source"
        source_file = source_root / "global" / "AGENTS.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("# Global\n", encoding="utf-8", newline="\n")
        target = self.codex / "AGENTS.md"
        target.write_bytes(source_file.read_bytes())
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(
                    source_root=source_root,
                    source_commit="a" * 40,
                    source_file_sha256=digest,
                    target_file_sha256=digest,
                )
            service = self._service(db)
            proposal = _proposal(
                scope="global",
                target="global_agents",
            )
            approval = self._prompt(db, "remember globally")
            result = service.deploy(
                proposal=proposal,
                approval_ref=approval,
            )
            self.assertTrue(result.publication_required)
            self.assertEqual(source_file.read_bytes(), target.read_bytes())

            before = source_file.read_bytes()
            approval2 = self._prompt(db, "edit globally")
            calls = 0

            def fail_second(path: Path, data: bytes) -> None:
                nonlocal calls
                from agent_memory_sidecar.instructions import atomic_write

                calls += 1
                if calls == 2:
                    raise CoreError("injected_failure", "second write failed")
                atomic_write(path, data)

            with patch(
                "agent_memory_sidecar.rule_service.atomic_write",
                side_effect=fail_second,
            ):
                with self.assertRaises(CoreError):
                    service.deploy(
                        proposal=_proposal(
                            scope="global",
                            target="global_agents",
                            action="Use the edited global rule.",
                        ),
                        approval_ref=approval2,
                        supersedes=result.rule.rule_id,
                    )
            self.assertEqual(source_file.read_bytes(), before)
            self.assertEqual(target.read_bytes(), before)

    def test_multiple_rules_are_consolidated_atomically_in_stable_order(self) -> None:
        original = b"# User-owned guidance\n\n"
        target = self.project / "AGENTS.md"
        target.write_bytes(original)
        with self._database() as db:
            service = self._service(db)
            first = service.deploy(
                proposal=_proposal(action="First behavior."),
                approval_ref=self._prompt(db, "first"),
            ).rule
            second = service.deploy(
                proposal=_proposal(action="Second behavior."),
                approval_ref=self._prompt(db, "second"),
            ).rule
            third = service.deploy(
                proposal=_proposal(action="Third behavior."),
                approval_ref=self._prompt(db, "third"),
            ).rule
            merged_proposal = _proposal(action="Merged first and second behavior.")
            merged = service.deploy(
                proposal=merged_proposal,
                approval_ref=self._prompt(db, "merge"),
                supersedes=[second.rule_id, first.rule_id],
            )
            self.assertEqual(merged.action, "consolidated")
            rules = service.repository.read_target(
                target="project_agents",
                identity=self.identity,
            ).rules
            self.assertEqual(
                [rule.rule_id for rule in rules],
                [merged.rule.rule_id, third.rule_id],
            )
            self.assertIn(original, target.read_bytes())
            request_hash = str(
                db.conn.execute(
                    """
                    SELECT request_sha256 FROM approval_consumptions
                    WHERE result_rule_id = ?
                    """,
                    (merged.rule.rule_id,),
                ).fetchone()[0]
            )
            self.assertEqual(len(request_hash), 64)
            self.assertNotEqual(request_hash, merged_proposal.proposal_sha256)

    def test_rule_bundle_deploys_multiple_rules_with_one_approval(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project owner\n")
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="First bundled behavior."),
                _proposal(action="Second bundled behavior."),
            )
            preview = preview_bundle(bundle=bundle, target_file=target)
            self.assertEqual(preview["combined"]["status"], "ready")
            result = service.deploy_bundle(
                bundle=bundle,
                approval_ref=self._prompt(db, bundle.confirmation_text),
            )
            self.assertEqual(preview["combined"]["target_after_sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(
                [item.action for item in result.items],
                ["deployed", "deployed"],
            )
            self.assertEqual(len(result.plans), 1)
            self.assertFalse(result.publication_required)
            listing = service.list(target="project_agents")
            self.assertEqual(
                [rule["action"] for rule in listing["rules"]],
                [
                    rule.action
                    for rule in sorted(
                        (
                            ConfirmedRule.from_proposal(item.proposal)
                            for item in bundle.items
                        ),
                        key=lambda rule: rule.rule_id,
                    )
                ],
            )
            consumption = db.conn.execute(
                "SELECT operation, request_sha256, result_rule_id "
                "FROM approval_consumptions"
            ).fetchone()
            self.assertEqual(consumption["operation"], "rule.deploy_bundle")
            self.assertEqual(len(str(consumption["request_sha256"])), 64)
            self.assertIsNone(consumption["result_rule_id"])

    def test_rule_bundle_is_a_permutation_invariant_set(self) -> None:
        target = self.project / "AGENTS.md"
        with self._database() as db:
            service = self._service(db)
            proposal_a = _proposal(action="Set member A.")
            proposal_b = _proposal(action="Set member B.")
            proposal_c = _proposal(action="Set member C.")
            rule_a = service.deploy(
                proposal=proposal_a,
                approval_ref=self._prompt(db, "deploy A"),
            ).rule
            rule_b = service.deploy(
                proposal=proposal_b,
                approval_ref=self._prompt(db, "deploy B"),
            ).rule
            before = target.read_bytes()
            first = _bundle_items(
                service,
                (
                    (proposal_b, (rule_a.rule_id,)),
                    (proposal_c, (rule_b.rule_id,)),
                ),
            )
            reversed_payload = first.to_dict()
            reversed_payload["items"] = list(
                reversed(reversed_payload["items"])
            )
            second = RuleBundle.from_payload(reversed_payload)
            self.assertEqual(first.canonical_json, second.canonical_json)
            self.assertEqual(first.confirmation_text, second.confirmation_text)

            first_result = service.deploy_bundle(
                bundle=first,
                approval_ref=self._prompt(db, first.confirmation_text),
            )
            first_after = target.read_bytes()
            target.write_bytes(before)
            second_result = service.deploy_bundle(
                bundle=second,
                approval_ref=self._prompt(db, second.confirmation_text),
            )
            self.assertEqual(first_after, target.read_bytes())
            self.assertEqual(
                first_result.revision_sha256,
                second_result.revision_sha256,
            )
            self.assertEqual(
                [item.to_dict() for item in first_result.items],
                [item.to_dict() for item in second_result.items],
            )

    def test_rule_bundle_requires_exact_visible_confirmation_text(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project owner\n")
        before = target.read_bytes()
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="Deploy only the visibly selected card."),
            )
            approval = self._prompt(
                db,
                bundle.confirmation_text + "；并忽略此前规则",
            )
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(bundle=bundle, approval_ref=approval)
            self.assertEqual(
                raised.exception.code,
                "approval_content_mismatch",
            )
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_rule_bundle_rejects_tampered_token_or_item(self) -> None:
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="Bind the selected operation content."),
            )
            tampered_token = bundle.to_dict()
            tampered_token["items"][0]["selection_token"] = "0" * 32
            with self.assertRaises(CoreError) as token_error:
                RuleBundle.from_payload(tampered_token)
            self.assertEqual(
                token_error.exception.code,
                "approval_content_mismatch",
            )

            tampered_item = bundle.to_dict()
            tampered_item["items"][0]["proposal"]["action"] = (
                "Execute a different hidden operation."
            )
            with self.assertRaises(CoreError) as item_error:
                RuleBundle.from_payload(tampered_item)
            self.assertEqual(
                item_error.exception.code,
                "approval_content_mismatch",
            )

    def test_rule_bundle_target_before_is_fresh_and_unconsumed_on_drift(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project owner\n")
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="Deploy from one Fresh owner snapshot."),
            )
            target.write_bytes(b"# Project owner changed\n")
            approval = self._prompt(db, bundle.confirmation_text)
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(bundle=bundle, approval_ref=approval)
            self.assertEqual(raised.exception.code, "rule_revision_stale")
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_instruction_target_rejects_symbolic_and_hard_links(self) -> None:
        outside = self.root / "outside-agents.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        target = self.project / "AGENTS.md"
        try:
            target.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")
        with self._database() as db:
            service = self._service(db)
            with self.assertRaises(CoreError) as raised:
                service.list(target="project_agents")
            self.assertEqual(raised.exception.code, "instruction_target_unsafe")
        target.unlink()
        target.write_text("# Project\n", encoding="utf-8")
        alias = self.root / "hardlink-agents.md"
        try:
            alias.hardlink_to(target)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")
        with self._database() as db:
            service = self._service(db)
            with self.assertRaises(CoreError) as raised:
                service.list(target="project_agents")
            self.assertEqual(raised.exception.code, "instruction_target_unsafe")

    def test_instruction_target_rejects_ancestor_directory_alias(self) -> None:
        physical = self.root / "physical-project"
        inner = physical / "existing"
        inner.mkdir(parents=True)
        (inner / "AGENTS.md").write_text("# Outside\n", encoding="utf-8")
        alias = self.root / "project-alias"
        try:
            alias.symlink_to(physical, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symbolic links unavailable: {exc}")
        original = self.identity
        logical_project = alias / "existing"
        self.identity = ProjectIdentity(
            cwd=str(logical_project),
            repo_root=str(logical_project),
            branch="main",
            scope_key=str(logical_project),
        )
        try:
            with self._database() as db:
                service = self._service(db)
                with self.assertRaises(CoreError) as raised:
                    service.list(target="project_agents")
                self.assertEqual(raised.exception.code, "instruction_target_unsafe")
        finally:
            self.identity = original

    def test_global_instruction_source_root_rejects_symbolic_alias(self) -> None:
        physical = self.root / "physical-source"
        source = physical / "global" / "AGENTS.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Global\n", encoding="utf-8")
        alias = self.root / "source-alias"
        try:
            alias.symlink_to(physical, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symbolic links unavailable: {exc}")
        target = self.codex / "AGENTS.md"
        target.write_bytes(source.read_bytes())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(
                    source_root=alias,
                    source_commit="a" * 40,
                    source_file_sha256=digest,
                    target_file_sha256=digest,
                )
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(
                    action="Do not follow a global source alias.",
                    scope="global",
                    target="global_agents",
                ),
            )
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(
                    bundle=bundle,
                    approval_ref=self._prompt(db, bundle.confirmation_text),
                )
            self.assertEqual(raised.exception.code, "instruction_target_unsafe")

    def test_rule_bundle_rejects_duplicate_proposals(self) -> None:
        proposal = _proposal(action="Duplicate selected behavior.")
        with self.assertRaises(CoreError) as raised:
            _bundle_from_before(b"", ((proposal, ()), (proposal, ())))
        self.assertEqual(raised.exception.code, "invalid_rule_bundle")

    def test_single_card_uses_the_same_rule_bundle_path(self) -> None:
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="One selected card."),
            )
            result = service.deploy_bundle(
                bundle=bundle,
                approval_ref=self._prompt(db, bundle.confirmation_text),
            )
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].action, "deployed")
            self.assertEqual(
                service.list(target="project_agents")["rules"][0]["action"],
                "One selected card.",
            )

    def test_rule_bundle_replaces_and_consolidates_in_one_revision(self) -> None:
        with self._database() as db:
            service = self._service(db)
            first = service.deploy(
                proposal=_proposal(action="First original behavior."),
                approval_ref=self._prompt(db, "confirm first original"),
            ).rule
            second = service.deploy(
                proposal=_proposal(action="Second original behavior."),
                approval_ref=self._prompt(db, "confirm second original"),
            ).rule
            third = service.deploy(
                proposal=_proposal(action="Third original behavior."),
                approval_ref=self._prompt(db, "confirm third original"),
            ).rule
            bundle = _bundle_items(
                service,
                (
                    (
                        _proposal(action="First revised behavior."),
                        (first.rule_id,),
                    ),
                    (
                        _proposal(
                            action="Second and third combined behavior."
                        ),
                        (third.rule_id, second.rule_id),
                    ),
                ),
            )
            result = service.deploy_bundle(
                bundle=bundle,
                approval_ref=self._prompt(db, bundle.confirmation_text),
            )
            self.assertEqual(
                [item.action for item in result.items],
                ["replaced", "consolidated"],
            )
            self.assertEqual(
                [
                    rule["action"]
                    for rule in service.list(target="project_agents")["rules"]
                ],
                [
                    "First revised behavior.",
                    "Second and third combined behavior.",
                ],
            )

    def test_invalid_rule_bundle_is_all_or_nothing_and_keeps_approval(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project owner\n")
        before = target.read_bytes()
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle_items(
                service,
                (
                    (_proposal(action="Valid first behavior."), ()),
                    (
                        _proposal(action="Invalid second behavior."),
                        ("rule_000000000001",),
                    ),
                ),
            )
            approval = self._prompt(db, bundle.confirmation_text)
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(bundle=bundle, approval_ref=approval)
            self.assertEqual(raised.exception.code, "rule_revision_stale")
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_rule_bundle_rejects_overlapping_supersedes_without_mutation(self) -> None:
        with self._database() as db:
            service = self._service(db)
            existing = service.deploy(
                proposal=_proposal(action="Existing behavior."),
                approval_ref=self._prompt(db, "confirm existing behavior"),
            ).rule
            target = self.project / "AGENTS.md"
            before = target.read_bytes()
            bundle = _bundle_items(
                service,
                (
                    (
                        _proposal(action="First competing replacement."),
                        (existing.rule_id,),
                    ),
                    (
                        _proposal(action="Second competing replacement."),
                        (existing.rule_id,),
                    ),
                ),
            )
            approval = self._prompt(db, bundle.confirmation_text)
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(bundle=bundle, approval_ref=approval)
            self.assertEqual(raised.exception.code, "invalid_rule_bundle")
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions "
                    "WHERE operation = 'rule.deploy_bundle'"
                ).fetchone()[0],
                0,
            )

    def test_rule_bundle_capacity_failure_is_all_or_nothing(self) -> None:
        proposals = [
            _proposal(action=f"Capacity behavior {index}: " + ("x" * 700))
            for index in range(20)
        ]
        rules = [ConfirmedRule.from_proposal(proposal) for proposal in proposals]
        maximum_fit = max(
            count
            for count in range(1, len(rules))
            if len(managed_block_bytes(tuple(rules[:count]), newline="\n"))
            <= MAX_MANAGED_BLOCK_BYTES
        )
        self.assertGreater(maximum_fit, 1)
        self.assertGreater(
            len(
                managed_block_bytes(
                    tuple(rules[: maximum_fit + 1]),
                    newline="\n",
                )
            ),
            MAX_MANAGED_BLOCK_BYTES,
        )
        target = self.project / "AGENTS.md"
        target.write_bytes(
            managed_block_bytes(tuple(rules[: maximum_fit - 1]), newline="\n")
        )
        before = target.read_bytes()
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                proposals[maximum_fit - 1],
                proposals[maximum_fit],
            )
            approval = self._prompt(db, bundle.confirmation_text)
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(
                    bundle=bundle,
                    approval_ref=approval,
                )
            self.assertEqual(
                raised.exception.code,
                "instruction_capacity_exceeded",
            )
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_global_rule_bundle_restores_both_targets_on_write_failure(self) -> None:
        source_root = self.root / "global-source"
        source_file = source_root / "global" / "AGENTS.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("# Global\n", encoding="utf-8", newline="\n")
        target = self.codex / "AGENTS.md"
        target.write_bytes(source_file.read_bytes())
        before = source_file.read_bytes()
        digest = hashlib.sha256(before).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(
                    source_root=source_root,
                    source_commit="a" * 40,
                    source_file_sha256=digest,
                    target_file_sha256=digest,
                )
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(
                    action="First global bundled behavior.",
                    scope="global",
                    target="global_agents",
                ),
                _proposal(
                    action="Second global bundled behavior.",
                    scope="global",
                    target="global_agents",
                ),
            )
            calls = 0

            def fail_second(path: Path, data: bytes) -> None:
                nonlocal calls
                from agent_memory_sidecar.instructions import atomic_write

                calls += 1
                if calls == 2:
                    raise CoreError("injected_failure", "second write failed")
                atomic_write(path, data)

            with patch(
                "agent_memory_sidecar.rule_service.atomic_write",
                side_effect=fail_second,
            ):
                with self.assertRaises(CoreError):
                    service.deploy_bundle(
                        bundle=bundle,
                        approval_ref=self._prompt(db, bundle.confirmation_text),
                    )
            self.assertEqual(source_file.read_bytes(), before)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_global_rule_bundle_fails_closed_on_owner_parity_drift(self) -> None:
        source_root = self.root / "global-source"
        source_file = source_root / "global" / "AGENTS.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("# Canonical global\n", encoding="utf-8")
        target = self.codex / "AGENTS.md"
        target.write_text("# Drifted local global\n", encoding="utf-8")
        source_digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        target_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(
                    source_root=source_root,
                    source_commit="a" * 40,
                    source_file_sha256=source_digest,
                    target_file_sha256=target_digest,
                )
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(
                    action="Global behavior that must not deploy.",
                    scope="global",
                    target="global_agents",
                ),
            )
            approval = self._prompt(db, bundle.confirmation_text)
            with self.assertRaises(CoreError) as raised:
                service.deploy_bundle(
                    bundle=bundle,
                    approval_ref=approval,
                )
            self.assertEqual(raised.exception.code, "global_instruction_drift")
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_rule_bundle_restores_target_on_database_failure(self) -> None:
        target = self.project / "AGENTS.md"
        target.write_bytes(b"# Project owner\n")
        before = target.read_bytes()
        with self._database() as db:
            service = self._service(db)
            bundle = _bundle(
                service,
                _proposal(action="First transient behavior."),
                _proposal(action="Second transient behavior."),
            )
            approval = self._prompt(db, bundle.confirmation_text)
            with patch.object(
                service.authorization,
                "consume",
                side_effect=CoreError(
                    "injected_failure",
                    "database commit failed",
                ),
            ):
                with self.assertRaises(CoreError) as raised:
                    service.deploy_bundle(
                        bundle=bundle,
                        approval_ref=approval,
                    )
            self.assertEqual(raised.exception.code, "injected_failure")
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_global_consolidation_updates_both_complete_documents(self) -> None:
        source_root = self.root / "global-source"
        source_file = source_root / "global" / "AGENTS.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("# Global\n", encoding="utf-8", newline="\n")
        target = self.codex / "AGENTS.md"
        target.write_bytes(source_file.read_bytes())
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        with self._database() as db:
            with db.transaction():
                InstallationRegistry(db).bind_global(
                    source_root=source_root,
                    source_commit="a" * 40,
                    source_file_sha256=digest,
                    target_file_sha256=digest,
                )
            service = self._service(db)
            first = service.deploy(
                proposal=_proposal(
                    action="First global behavior.",
                    scope="global",
                    target="global_agents",
                ),
                approval_ref=self._prompt(db, "first global"),
            ).rule
            second = service.deploy(
                proposal=_proposal(
                    action="Second global behavior.",
                    scope="global",
                    target="global_agents",
                ),
                approval_ref=self._prompt(db, "second global"),
            ).rule
            merged = service.deploy(
                proposal=_proposal(
                    action="Merged global behavior.",
                    scope="global",
                    target="global_agents",
                ),
                approval_ref=self._prompt(db, "merge global"),
                supersedes=[second.rule_id, first.rule_id],
            )
            self.assertEqual(merged.action, "consolidated")
            self.assertTrue(merged.publication_required)
            self.assertEqual(source_file.read_bytes(), target.read_bytes())
            parsed = service.repository.read_target(
                target="global_agents",
                identity=self.identity,
            )
            self.assertEqual(
                [rule.rule_id for rule in parsed.rules],
                [merged.rule.rule_id],
            )

    def test_invalid_superseded_sets_do_not_consume_approval(self) -> None:
        with self._database() as db:
            service = self._service(db)
            existing = service.deploy(
                proposal=_proposal(action="Existing behavior."),
                approval_ref=self._prompt(db, "existing"),
            ).rule
            approval = self._prompt(db, "invalid duplicate merge")
            with self.assertRaises(CoreError) as duplicate:
                service.deploy(
                    proposal=_proposal(action="Replacement."),
                    approval_ref=approval,
                    supersedes=[existing.rule_id, existing.rule_id],
                )
            self.assertEqual(duplicate.exception.code, "rule_revision_invalid")
            self.assertEqual(
                db.conn.execute(
                    """
                    SELECT COUNT(*) FROM approval_consumptions
                    WHERE approval_ref_sha256 = ?
                    """,
                    (
                        hashlib.sha256(approval.encode("utf-8")).hexdigest(),
                    ),
                ).fetchone()[0],
                0,
            )
            with self.assertRaises(CoreError) as missing:
                service.deploy(
                    proposal=_proposal(action="Replacement."),
                    approval_ref=approval,
                    supersedes=["rule_000000000000"],
                )
            self.assertEqual(missing.exception.code, "rule_revision_invalid")

    def test_revision_token_binds_superseded_set_and_target_before_hash(self) -> None:
        with self._database() as db:
            service = self._service(db)
            first = service.deploy(
                proposal=_proposal(action="First behavior."),
                approval_ref=self._prompt(db, "first"),
            ).rule
            second = service.deploy(
                proposal=_proposal(action="Second behavior."),
                approval_ref=self._prompt(db, "second"),
            ).rule
            revised = _proposal(action="Merged behavior.")
            token, revision = service.create_proposal(
                source_event_ref=self._prompt(db, "proposal"),
                proposal=revised,
                supersedes=[second.rule_id, first.rule_id],
            )
            self.assertTrue(token.proposal_sha256.startswith("r1:"))
            self.assertEqual(len(revision.revision_sha256), 64)

            with self.assertRaises(CoreError) as changed_set:
                service.confirm_proposal(
                    proposal=revised,
                    approval_ref=self._prompt(db, "confirm changed set"),
                    supersedes=[first.rule_id],
                )
            self.assertEqual(
                changed_set.exception.code,
                "rule_revision_invalid",
            )

            target = self.project / "AGENTS.md"
            target.write_bytes(target.read_bytes() + b"\n# Outside drift\n")
            with self.assertRaises(CoreError) as stale:
                service.confirm_proposal(
                    proposal=revised,
                    approval_ref=self._prompt(db, "confirm stale"),
                    supersedes=[first.rule_id, second.rule_id],
                )
            self.assertEqual(stale.exception.code, "rule_revision_stale")
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM proposal_tokens"
                ).fetchone()[0],
                1,
            )

    def test_exactly_covered_candidate_does_not_create_proposal_token(self) -> None:
        with self._database() as db:
            service = self._service(db)
            proposal = _proposal(action="Existing behavior.")
            service.deploy(
                proposal=proposal,
                approval_ref=self._prompt(db, "existing"),
            )
            with self.assertRaises(CoreError) as raised:
                service.create_proposal(
                    source_event_ref=self._prompt(db, "duplicate proposal"),
                    proposal=proposal,
                )
            self.assertEqual(
                raised.exception.code,
                "rule_already_covered",
            )
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM proposal_tokens"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(len(service.list()["rules"]), 1)

    def test_legacy_add_token_cannot_acquire_a_superseded_rule(self) -> None:
        with self._database() as db:
            service = self._service(db)
            existing = service.deploy(
                proposal=_proposal(action="Existing behavior."),
                approval_ref=self._prompt(db, "existing"),
            ).rule
            revised = _proposal(action="Revised behavior.")
            RuntimeLedger(db).create_proposal(
                source_event_ref=self._prompt(db, "legacy proposal"),
                identity=self.identity,
                proposal=revised,
            )
            with self.assertRaises(CoreError) as raised:
                service.confirm_proposal(
                    proposal=revised,
                    approval_ref=self._prompt(db, "confirm legacy edit"),
                    supersedes=[existing.rule_id],
                )
            self.assertEqual(raised.exception.code, "rule_revision_invalid")

    def test_override_blocks_effective_state(self) -> None:
        (self.project / "AGENTS.override.md").write_text(
            "override",
            encoding="utf-8",
        )
        with self._database() as db:
            approval = self._prompt(db, "remember")
            with self.assertRaises(CoreError) as raised:
                self._service(db).deploy(
                    proposal=_proposal(),
                    approval_ref=approval,
                )
            self.assertEqual(
                raised.exception.code,
                "instruction_target_shadowed",
            )

    def test_managed_block_has_deterministic_eight_kib_limit(self) -> None:
        repository = self._repository()
        snapshot = DocumentSnapshot(
            target="project_agents",
            path=self.project / "AGENTS.md",
            existed=False,
            data=b"",
            rules=(),
            outside=b"",
            shadowed=False,
        )
        rules = tuple(
            ConfirmedRule.from_proposal(
                _proposal(
                    action=f"{index} " + ("x" * 850),
                )
            )
            for index in range(10)
        )
        with self.assertRaises(CoreError) as raised:
            plan_replace(
                snapshot=snapshot,
                rules=rules,
                rule=rules[-1],
                action="deployed",
            )
        self.assertEqual(
            raised.exception.code,
            "instruction_capacity_exceeded",
        )
        self.assertEqual(raised.exception.details["before_bytes"], 0)
        self.assertGreater(
            raised.exception.details["projected_bytes"],
            raised.exception.details["budget_bytes"],
        )
        self.assertEqual(MAX_MANAGED_BLOCK_BYTES, 8192)
        self.assertIsNotNone(repository)

    def test_capacity_failure_does_not_consume_approval(self) -> None:
        rules: list[ConfirmedRule] = []
        index = 0
        while True:
            candidate = ConfirmedRule.from_proposal(
                _proposal(action=f"{index} " + ("x" * 850))
            )
            projected = (*rules, candidate)
            if len(managed_block_bytes(projected, newline="\n")) > 8192:
                break
            rules.append(candidate)
            index += 1
        target = self.project / "AGENTS.md"
        target.write_bytes(managed_block_bytes(tuple(rules), newline="\n"))
        with self._database() as db:
            service = self._service(db)
            approval = self._prompt(db, "overflow")
            with self.assertRaises(CoreError) as raised:
                service.deploy(
                    proposal=_proposal(action="y" * 850),
                    approval_ref=approval,
                )
            self.assertEqual(
                raised.exception.code,
                "instruction_capacity_exceeded",
            )
            self.assertEqual(
                raised.exception.details["before_bytes"],
                len(managed_block_bytes(tuple(rules), newline="\n")),
            )
            self.assertEqual(
                db.conn.execute(
                    "SELECT COUNT(*) FROM approval_consumptions"
                ).fetchone()[0],
                0,
            )

    def test_rendered_rule_has_exact_one_kib_limit(self) -> None:
        one_character = ConfirmedRule.from_proposal(
            _proposal(action="x")
        )
        fixed_bytes = len(
            render_rule(one_character, newline="\n").encode("utf-8")
        ) - 1
        maximum_action_bytes = MAX_RENDERED_RULE_BYTES - fixed_bytes
        boundary = ConfirmedRule.from_proposal(
            _proposal(action="x" * maximum_action_bytes)
        )
        self.assertEqual(
            len(render_rule(boundary, newline="\n").encode("utf-8")),
            MAX_RENDERED_RULE_BYTES,
        )
        with self.assertRaises(CoreError) as raised:
            ConfirmedRule.from_proposal(
                _proposal(action="x" * (maximum_action_bytes + 1))
            )
        self.assertEqual(
            raised.exception.code,
            "instruction_capacity_exceeded",
        )

    def test_recovery_refuses_to_overwrite_unrelated_post_crash_edits(self) -> None:
        with self._database() as db:
            service = self._service(db)
            plans = service._deploy_plans(  # noqa: SLF001
                proposal=_proposal(),
                supersedes=None,
            )
            service.coordinator._write_journal(  # noqa: SLF001
                transaction_id="tx_" + ("a" * 32),
                plans=plans,
                source_event_id=self._prompt(db, "interrupted").split(":", 1)[1],
            )
            target = self.project / "AGENTS.md"
            target.write_text("user edit after crash\n", encoding="utf-8")
            with self.assertRaises(CoreError) as raised:
                service.coordinator.recover()
            self.assertEqual(
                raised.exception.code,
                "instruction_recovery_drift",
            )
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "user edit after crash\n",
            )

    def _database(self) -> CoreDatabase:
        return CoreDatabase(
            self.store,
            create=not self.store.exists(),
            now=(
                "2026-07-24T00:00:00+00:00"
                if not self.store.exists()
                else None
            ),
        )

    def _repository(self) -> InstructionRepository:
        return InstructionRepository(
            codex_home=self.codex,
            lock_root=self.root / "locks",
        )

    def _service(self, db: CoreDatabase) -> RuleService:
        return RuleService(
            db=db,
            identity=self.identity,
            repository=self._repository(),
        )

    def _prompt(self, db: CoreDatabase, prompt: str) -> str:
        event = RuntimeLedger(db).capture_prompt(
            identity=self.identity,
            source_session="session",
            prompt=prompt,
            metadata={},
        )
        return f"user_prompt:{event.event_id}"


def _proposal(
    *,
    action: str = "Run the relevant tests before reporting completion.",
    scope: str = "project",
    target: str = "project_agents",
) -> RuleProposal:
    return RuleProposal.from_payload(
        {
            "trigger": "When reviewing repository changes.",
            "action": action,
            "skip_boundary": "Skip for prose-only work.",
            "scope": scope,
            "why": "Avoid repeat regressions.",
            "evidence": "The user explicitly required verified completion.",
            "instruction_target": target,
        }
    )


def _bundle(
    service: RuleService, *proposals: RuleProposal
) -> RuleBundle:
    return _bundle_items(
        service,
        tuple((proposal, ()) for proposal in proposals),
    )


def _bundle_items(
    service: RuleService,
    items: tuple[tuple[RuleProposal, tuple[str, ...]], ...],
) -> RuleBundle:
    snapshot = service.repository.read_target(
        target=items[0][0].instruction_target,
        identity=service.identity,
    )
    return _bundle_from_before(snapshot.data, items)


def _bundle_from_before(
    target_before: bytes,
    items: tuple[tuple[RuleProposal, tuple[str, ...]], ...],
) -> RuleBundle:
    target_before_sha256 = hashlib.sha256(target_before).hexdigest()
    raw_items = []
    for index, (proposal, supersedes) in enumerate(items, start=1):
        card_id = f"card-{index:04d}"
        project_claim_hash = hashlib.sha256(
            f"claim:{index}:{proposal.proposal_sha256}".encode("utf-8")
        ).hexdigest()
        normalized = tuple(sorted(supersedes))
        raw_items.append(
            {
                "card_id": card_id,
                "project_claim_hash": project_claim_hash,
                "proposal": proposal.to_dict(),
                "supersedes": list(normalized),
                "selection_token": review_selection_token(
                    card_id=card_id,
                    project_claim_hash=project_claim_hash,
                    proposal=proposal,
                    supersedes=normalized,
                    instruction_target=proposal.instruction_target,
                    target_before_sha256=target_before_sha256,
                ),
            }
        )
    return RuleBundle.from_payload(
        {
            "contract_version": "rule_revision_bundle_v2",
            "target_before_sha256": target_before_sha256,
            "items": raw_items,
        }
    )
