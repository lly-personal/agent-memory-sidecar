from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar import cli, config_sync as sync
from agent_memory_sidecar.errors import CoreError


class ConfigSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "config.toml"
        self.original = b'# fixture\r\napproval_policy = "never" # keep\r\nunknown = [1, 2]\r\n[windows]\r\nsandbox = "old"\r\n'
        self.target.write_bytes(self.original)
        self.policy = {"contract_version": sync.POLICY, "owner": "codex-instructions",
                       "platforms": ["windows"], "codex_versions": ["fixture-1"],
                       "fields": [self.field(["approval_policy"], "on-request"),
                                  self.field(["windows", "sandbox"], "fixture-review")]}
        self.bundle = {"policy": self.policy, "commit": "a" * 40, "file": "policy.json",
                       "sha256": sync._digest(self.policy), "source_identity": "b" * 64}
        self.kw = {"bundle": self.bundle, "target": self.target,
                   "platform": "windows", "codex_version": "fixture-1"}

    @staticmethod
    def field(path, value):
        return {"path": path, "value": value, "non_secret": True,
                "rationale": "Explicit fixture enrollment", "risk": "Requires separate actual user approval"}

    def apply(self):
        plan = sync.preview(**self.kw)
        return sync.apply(**self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture-only-approval")

    def error(self, code, function, **kwargs):
        with self.assertRaises(CoreError) as caught:
            function(**kwargs)
        self.assertEqual("config_" + code, caught.exception.code)

    def test_preview_readonly_and_exact_delta(self):
        before = list(self.root.iterdir())
        plan = sync.preview(**self.kw)
        self.assertEqual(before, list(self.root.iterdir()))
        self.assertEqual(self.original, self.target.read_bytes())
        self.assertEqual("authorization_required", plan["status"])
        self.assertEqual("never", plan["fields"][0]["observed"]["value"])
        self.assertEqual(plan, sync.preview(**self.kw))
        self.assertEqual("unknown", plan["effective_values"])

    def test_apply_preserves_unmanaged_bytes_and_no_whole_file_backup(self):
        result = self.apply()
        expected = self.original.replace(b'"never"', b'"on-request"').replace(b'"old"', b'"fixture-review"')
        self.assertEqual(expected, self.target.read_bytes())
        self.assertEqual("file_applied", result["status"])
        self.assertEqual("external_reference_not_verified", result["authorization_evidence_verification"])
        journal = sync._journal_path(self.target).read_bytes()
        self.assertNotIn(b"unknown =", journal)
        self.assertNotIn(b"# fixture", journal)
        self.assertEqual("no_change", sync.preview(**self.kw)["status"])
        self.assertEqual("after", sync.reconcile(target=self.target)["file_position"])

    def test_approval_and_policy_target_drift_bindings(self):
        plan = sync.preview(**self.kw)
        self.error("authorization_required", sync.apply, **self.kw, plan_hash=plan["plan_hash"], approval_ref="")
        self.policy["fields"][0]["risk"] = "Changed risk"
        self.error("authorization_required", sync.apply, **self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
        plan = sync.preview(**self.kw)
        self.target.write_bytes(self.original + b"# concurrent\n")
        self.error("authorization_required", sync.apply, **self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual(self.original + b"# concurrent\n", self.target.read_bytes())

    def test_exact_platform_version_and_nonsecret_enrollment(self):
        self.error("applicability_unknown", sync.preview, **{**self.kw, "platform": "macos"})
        self.error("applicability_unknown", sync.preview, **{**self.kw, "codex_version": "fixture-2"})
        for bad in (False, "yes"):
            self.policy["fields"][0]["non_secret"] = bad
            self.error("policy_invalid", sync.preview, **self.kw)

    def test_inactive_owner_template_never_enrolls_or_creates_state(self):
        template = {"contract_version": sync.POLICY, "owner": "codex-instructions",
                    "platforms": [], "codex_versions": [], "fields": []}
        before = list(self.root.iterdir())
        self.error("policy_invalid", sync.validate_policy, policy=template)
        self.error("policy_invalid", sync.preview, **{**self.kw, "bundle": {**self.bundle, "policy": template}})
        self.assertEqual(before, list(self.root.iterdir()))
        self.assertEqual(self.original, self.target.read_bytes())

    def test_overlapping_unknown_policy_and_nonscalar_rejected(self):
        for field in (self.field(["windows"], "x"), self.field(["approval_policy"], "x")):
            policy = copy.deepcopy(self.policy)
            policy["fields"].append(field)
            self.error("policy_invalid", sync.validate_policy, policy=policy)
        self.policy["fields"][0]["value"] = {"secret": "not enrolled"}
        self.error("policy_invalid", sync.preview, **self.kw)

    def test_add_missing_fields_and_restore_without_unrelated_drift_loss(self):
        self.policy["fields"] = [self.field(["new_key"], True), self.field(["windows", "new_key"], 4)]
        self.apply()
        self.target.write_bytes(self.target.read_bytes().replace(b"[1, 2]", b"[3, 4]") + b"# user addition\n")
        plan = sync.preview_restore(target=self.target)
        sync.restore(target=self.target, plan_hash=plan["plan_hash"], approval_ref="fixture-restore")
        self.assertEqual(self.original.replace(b"[1, 2]", b"[3, 4]") + b"# user addition\n", self.target.read_bytes())
        self.assertEqual("restored", sync.reconcile(target=self.target)["status"])
        self.error("recovery_unavailable", sync.preview_restore, target=self.target)

    def test_restore_exact_literal_and_conflict_atomicity(self):
        self.target.write_bytes(self.original.replace(b'"never"', b"'never'"))
        original = self.target.read_bytes()
        self.apply()
        self.target.write_bytes(self.target.read_bytes().replace(b'"fixture-review"', b'"user-choice"'))
        before = self.target.read_bytes()
        self.error("recovery_conflict", sync.preview_restore, target=self.target)
        self.assertEqual(before, self.target.read_bytes())
        self.target.write_bytes(before.replace(b'"user-choice"', b'"fixture-review"'))
        plan = sync.preview_restore(target=self.target)
        self.target.write_bytes(self.target.read_bytes() + b"# drift\n")
        self.error("authorization_required", sync.restore, target=self.target, plan_hash=plan["plan_hash"], approval_ref="fixture")
        plan = sync.preview_restore(target=self.target)
        sync.restore(target=self.target, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual(original + b"# drift\n", self.target.read_bytes())

    def test_failures_before_and_after_replacement_reconcile_without_replay(self):
        real_write = sync.atomic_write
        for after_replace in (False, True):
            with self.subTest(after_replace=after_replace):
                sync._journal_path(self.target).unlink(missing_ok=True)
                self.target.write_bytes(self.original)
                def fail(path, data):
                    if path == self.target:
                        if after_replace:
                            real_write(path, data)
                        raise OSError("fixture write interruption")
                    real_write(path, data)
                plan = sync.preview(**self.kw)
                with patch.object(sync, "atomic_write", side_effect=fail):
                    with self.assertRaises(OSError):
                        sync.apply(**self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
                state = sync.reconcile(target=self.target)
                self.assertEqual("prepared", state["status"])
                self.assertEqual("after" if after_replace else "before", state["file_position"])
                self.assertFalse(state["automatic_replay"])
                self.error("recovery_required", sync.preview, **self.kw)
                restore = sync.preview_restore(target=self.target)
                sync.restore(target=self.target, plan_hash=restore["plan_hash"], approval_ref="fixture")
                self.assertEqual(self.original, self.target.read_bytes())

    def test_drift_after_journal_is_not_overwritten(self):
        real_write = sync.atomic_write
        def drift(path, data):
            real_write(path, data)
            if path == sync._journal_path(self.target):
                self.target.write_bytes(self.original + b"# independent edit\n")
        plan = sync.preview(**self.kw)
        with patch.object(sync, "atomic_write", side_effect=drift):
            self.error("concurrent_drift", sync.apply, **self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual(self.original + b"# independent edit\n", self.target.read_bytes())

    def test_drift_between_planning_and_snapshot_never_gains_authorization(self):
        plan = sync.preview(**self.kw)
        real_preview = sync.preview
        def drift(**kwargs):
            result = real_preview(**kwargs)
            self.target.write_bytes(self.target.read_bytes() + b"# racing edit\n")
            return result
        with patch.object(sync, "preview", side_effect=drift):
            self.error("concurrent_drift", sync.apply, **self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual(self.original + b"# racing edit\n", self.target.read_bytes())
        self.assertFalse(sync._journal_path(self.target).exists())
        self.apply()
        plan = sync.preview_restore(target=self.target)
        real_restore_preview = sync.preview_restore
        def restore_drift(**kwargs):
            result = real_restore_preview(**kwargs)
            self.target.write_bytes(self.target.read_bytes() + b"# another edit\n")
            return result
        with patch.object(sync, "preview_restore", side_effect=restore_drift):
            self.error("concurrent_drift", sync.restore, target=self.target,
                       plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertIn(b'"on-request"', self.target.read_bytes())

    def test_restore_inserted_field_keeps_user_added_comment(self):
        self.policy["fields"] = [self.field(["added"], "fixture")]
        self.apply()
        self.target.write_bytes(self.target.read_bytes().replace(b'added = "fixture"\r\n',
                                                                b'added = "fixture" # user note\r\n'))
        plan = sync.preview_restore(target=self.target)
        sync.restore(target=self.target, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual(b"# user note\r\n" + self.original, self.target.read_bytes())

    def test_successful_replace_then_journal_failure_is_recoverable(self):
        real_write = sync.atomic_write
        def fail(path, data):
            if path == sync._journal_path(self.target) and json.loads(data)["status"] == "applied":
                raise OSError("fixture journal unavailable")
            real_write(path, data)
        plan = sync.preview(**self.kw)
        with patch.object(sync, "atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                sync.apply(**self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture")
        self.assertEqual("after", sync.reconcile(target=self.target)["file_position"])
        self.error("recovery_required", sync.preview, **self.kw)
        recovery = sync.preview_restore(target=self.target)
        sync.restore(target=self.target, plan_hash=recovery["plan_hash"], approval_ref="fixture")
        self.assertEqual(self.original, self.target.read_bytes())

    def test_interrupted_restoration_blocks_new_apply_until_reconciled(self):
        real_write = sync.atomic_write
        for after_replace in (False, True):
            with self.subTest(after_replace=after_replace):
                self.apply()
                plan = sync.preview_restore(target=self.target)
                def fail(path, data):
                    if path == self.target:
                        if after_replace:
                            real_write(path, data)
                        raise OSError("fixture restore interruption")
                    real_write(path, data)
                with patch.object(sync, "atomic_write", side_effect=fail):
                    with self.assertRaises(OSError):
                        sync.restore(target=self.target, plan_hash=plan["plan_hash"], approval_ref="fixture")
                state = sync.reconcile(target=self.target)
                self.assertEqual("restore_prepared", state["status"])
                self.assertEqual("before" if after_replace else "after", state["file_position"])
                self.assertFalse(state["automatic_replay"])
                self.error("recovery_required", sync.preview, **self.kw)
                recovery = sync.preview_restore(target=self.target)
                sync.restore(target=self.target, plan_hash=recovery["plan_hash"], approval_ref="fixture")
                self.assertEqual(self.original, self.target.read_bytes())
                self.assertEqual("restored", sync.reconcile(target=self.target)["status"])

    def test_unsupported_toml_never_rewrites(self):
        for data in (b'approval_policy = """never"""\n', b'"approval_policy" = "never"\n',
                     b'windows = { sandbox = "old" }\napproval_policy = "never"\n',
                     b'approval_policy = "never"\napproval_policy = "never"\n'):
            with self.subTest(data=data):
                self.target.write_bytes(data)
                with self.assertRaises(CoreError):
                    sync.preview(**self.kw)
                self.assertEqual(data, self.target.read_bytes())
        # Header-looking text inside a multiline string must not attract a patch.
        self.target.write_bytes(b'blob = """\n[windows]\nsandbox = "old"\n"""\napproval_policy = "never"\n')
        with self.assertRaises(CoreError):
            sync.preview(**self.kw)

    def test_type_sensitive_recovery_and_unknown_datetime_preservation(self):
        self.target.write_bytes(b'enabled = true\nunknown_date = 2026-10-27\nunknown_float = nan\n')
        self.policy["fields"] = [self.field(["enabled"], 1)]
        self.apply()
        self.assertIn(b"enabled = 1", self.target.read_bytes())
        self.target.write_bytes(self.target.read_bytes().replace(b"enabled = 1", b"enabled = false"))
        self.error("recovery_conflict", sync.preview_restore, target=self.target)

    def test_physical_aliases_and_journal_tamper_rejected(self):
        alias = self.root / "alias"
        os.link(self.target, alias)
        with self.assertRaises(CoreError):
            sync.preview(**self.kw)
        alias.unlink()
        self.apply()
        journal = sync._journal_path(self.target)
        state = json.loads(journal.read_bytes())
        state["changes"][0]["before"]["value"] = "tampered"
        journal.write_text(json.dumps(state), encoding="utf-8")
        self.error("journal_invalid", sync.preview_restore, target=self.target)

    def test_next_revision_explicitly_supersedes_latest_delta(self):
        self.apply()
        old = sync._journal_path(self.target).read_bytes()
        self.policy["fields"][0]["value"] = "next-fixture-value"
        plan = sync.preview(**self.kw)
        self.assertEqual(sync._hash(old), plan["previous_transaction_sha256"])
        sync.apply(**self.kw, plan_hash=plan["plan_hash"], approval_ref="fixture-next")
        restore = sync.preview_restore(target=self.target)
        sync.restore(target=self.target, plan_hash=restore["plan_hash"], approval_ref="fixture-restore")
        self.assertIn(b'approval_policy = "on-request"', self.target.read_bytes())

    def test_effective_observation_is_bound_and_distinct_from_file_values(self):
        self.apply()
        result = sync.verify(**self.kw)
        self.assertEqual("match", result["file_values"])
        self.assertEqual("unknown", result["effective_values"])
        observation = {"target_sha256": result["target_sha256"], "platform": "windows", "codex_version": "fixture-1",
                       "entrypoint": "isolated fixture consumer", "evidence_ref": "fixture-readback",
                       "fields": [{"path": f["path"], "value": f["value"]} for f in self.policy["fields"]]}
        self.assertEqual("reported_match", sync.verify(**self.kw, observation=observation)["effective_values"])
        observation["fields"][0]["value"] = "override"
        self.assertEqual("reported_differ", sync.verify(**self.kw, observation=observation)["effective_values"])
        observation["target_sha256"] = "0" * 64
        self.error("observation_stale", sync.verify, **self.kw, observation=observation)
        self.error("observation_invalid", sync.verify, **self.kw, observation=[])
        observation["target_sha256"] = result["target_sha256"]
        observation["fields"] = ["malformed", "malformed"]
        self.error("observation_incomplete", sync.verify, **self.kw, observation=observation)

    def test_cli_interruption_reports_uncertain_outcome_instead_of_false_zero_effect(self):
        output = io.StringIO()
        with (patch.object(sync, "load_policy", return_value=self.bundle),
              patch.object(sync, "apply", side_effect=OSError("fixture interruption")),
              redirect_stdout(output)):
            code = cli.main(["config", "apply", "--source", str(self.root), "--source-commit", "a" * 40,
                             "--policy-file", "fixture.json", "--target-file", str(self.target),
                             "--platform", "windows", "--codex-version", "fixture-1", "--plan-hash", "fixture",
                             "--approval-ref", "fixture"])
        self.assertEqual(1, code)
        error = json.loads(output.getvalue())["error"]
        self.assertEqual("config_transaction_interrupted", error["code"])
        self.assertEqual("unknown", error["details"]["mutation_outcome"])
        self.assertTrue(error["details"]["reconciliation_required"])
        self.assertNotIn("without completing", error["message"])

    def test_git_bound_cli_discovery_apply_and_restore(self):
        source = self.root / "policy-source"
        source.mkdir()
        def git(*args):
            return subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True).stdout.decode().strip()
        git("init")
        git("config", "core.autocrlf", "false")
        (source / "policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        git("add", "policy.json")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
        commit = git("rev-parse", "HEAD")
        # Dirty working bytes are not policy authority; only the selected committed blob is read.
        (source / "policy.json").write_text("uncommitted", encoding="utf-8")
        base = ["--target-file", str(self.target), "--source", str(source), "--source-commit", commit,
                "--policy-file", "policy.json", "--platform", "windows", "--codex-version", "fixture-1"]
        def run(args):
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(["config", *args])
            value = json.loads(output.getvalue())
            self.assertEqual(0, code, value)
            return value["data"]
        plan = run(["preview", *base])
        applied = run(["apply", *base, "--plan-hash", plan["plan_hash"], "--approval-ref", "fixture"])
        self.assertEqual("file_applied", applied["status"])
        observed = run(["verify", *base])
        self.assertEqual("match", observed["file_values"])
        self.assertEqual("unknown", observed["effective_values"])
        state = run(["reconcile", "--target-file", str(self.target)])
        self.assertEqual("applied", state["status"])
        self.assertEqual("after", state["file_position"])
        recovery = run(["restore-preview", "--target-file", str(self.target)])
        run(["restore", "--target-file", str(self.target), "--plan-hash", recovery["plan_hash"], "--approval-ref", "fixture"])
        self.assertEqual(self.original, self.target.read_bytes())
        self.error("source_invalid", sync.load_policy, source=source, commit=commit, policy_file="../policy.json")
        # Exercise the actual module entrance with fixture-only home and no installation.
        env = {**os.environ, "PYTHONPATH": str(Path(sync.__file__).parents[1]),
               "CODEX_HOME": str(self.root / "isolated-home")}
        result = subprocess.run([sys.executable, "-m", "agent_memory_sidecar", "config", "preview", *base],
                                env=env, capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("authorization_required", json.loads(result.stdout)["data"]["status"])
        self.assertFalse((self.root / "isolated-home").exists())


if __name__ == "__main__":
    unittest.main()
