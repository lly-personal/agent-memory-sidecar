from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import sys
import zipfile
import hashlib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar import cli, instruction_sync as sync
from agent_memory_sidecar.database import CoreDatabase
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.installation import InstallationRegistry


class InstructionSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.remote = self.root / "remote.git"
        self.codex = self.root / "codex"
        self.pi = self.root / "pi"
        self.state = self.root / "state"
        self.source.mkdir()
        self.git(self.source, "init", "-b", "main")
        self.git(self.source, "config", "user.name", "Fixture")
        self.git(self.source, "config", "user.email", "fixture@example.invalid")
        self.git(self.source, "config", "core.autocrlf", "false")
        (self.source / "global").mkdir()
        (self.source / "global" / "AGENTS.md").write_bytes(b"# Fixture rules\nUse evidence.\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "initial")
        self.git(self.root, "init", "--bare", str(self.remote))
        self.git(self.source, "remote", "add", "origin", str(self.remote))
        self.git(self.source, "push", "-u", "origin", "main")
        env = patch.dict(os.environ, {"CODEX_HOME": str(self.codex), "PI_CODING_AGENT_DIR": str(self.pi)})
        env.start()
        self.addCleanup(env.stop)
        self.kw = dict(source=self.source, codex_home=self.codex, pi_agent_dir=self.pi, state_dir=self.state)

    @staticmethod
    def git(root, *args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def deploy(self, **kwargs):
        options = {**self.kw, **kwargs}
        plan = sync.synchronize(**options)
        return sync.synchronize(**options, apply=True, plan_hash=plan["plan_hash"])

    def assert_error(self, code, **kwargs):
        with self.assertRaises(CoreError) as raised:
            sync.synchronize(**{**self.kw, **kwargs})
        self.assertEqual(code, raised.exception.code)

    def publish(self, data=b"# Fixture rules\nVerify actual entrypoints.\n"):
        (self.source / "global" / "AGENTS.md").write_bytes(data)
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "update")
        self.git(self.source, "push")
        return data

    def test_preview_has_no_persistent_writes(self):
        result = sync.synchronize(**self.kw)
        self.assertEqual("planned", result["status"])
        for path in (self.codex, self.pi, self.state):
            self.assertFalse(path.exists())
        self.assertEqual("", self.git(self.source, "status", "--porcelain"))

    def test_cli_entry_deploys_both_hosts_and_is_idempotent(self):
        args = ["instructions", "sync", "--source", str(self.source), "--codex-home", str(self.codex),
                "--pi-agent-dir", str(self.pi), "--state-dir", str(self.state)]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(args))
        plan = json.loads(output.getvalue())["data"]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main([*args, "--apply", "--plan-hash", plan["plan_hash"]]))
        receipt = json.loads(output.getvalue())["data"]
        self.assertEqual("reload_required", receipt["status"])
        self.assertEqual("unverified", receipt["adoption"])
        expected = (self.source / "global" / "AGENTS.md").read_bytes()
        bindings = {}
        for home in (self.codex, self.pi):
            self.assertEqual(expected, (home / "AGENTS.md").read_bytes())
            bindings[home] = sync._binding(home)
        self.deploy()
        self.assertEqual(bindings, {home: sync._binding(home) for home in bindings})
        self.assertFalse((self.state / "instruction-sync-recovery.json").exists())

    def test_persisted_targets_and_source_allow_path_free_repeat(self):
        self.deploy()
        with patch.dict(os.environ, {"CODEX_HOME": "", "PI_CODING_AGENT_DIR": ""}):
            plan = sync.synchronize(state_dir=self.state)
            result = sync.synchronize(state_dir=self.state, apply=True, plan_hash=plan["plan_hash"])
        self.assertEqual({"pi", "codex"}, {row["host"] for row in result["hosts"]})

    def test_remote_update_does_not_pull_active_checkout(self):
        self.deploy()
        old_commit = self.git(self.source, "rev-parse", "HEAD")
        writer = self.root / "writer"
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(writer))
        self.git(writer, "config", "user.name", "Fixture")
        self.git(writer, "config", "user.email", "fixture@example.invalid")
        expected = b"# Other workstation\nSame authority.\n"
        (writer / "global" / "AGENTS.md").write_bytes(expected)
        self.git(writer, "add", ".")
        self.git(writer, "commit", "-m", "other workstation")
        self.git(writer, "push")
        self.deploy()
        self.assertEqual(old_commit, self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual(expected, (self.pi / "AGENTS.md").read_bytes())

    def test_two_workstations_exchange_published_versions(self):
        self.deploy()
        second = self.root / "second"
        second.mkdir()
        other_source = second / "source"
        self.git(second, "clone", "--branch", "main", str(self.remote), str(other_source))
        options = dict(source=other_source, codex_home=second / "codex", pi_agent_dir=second / "pi", state_dir=second / "state")
        plan = sync.synchronize(**options)
        sync.synchronize(**options, apply=True, plan_hash=plan["plan_hash"])
        self.git(other_source, "config", "user.name", "Fixture")
        self.git(other_source, "config", "user.email", "fixture@example.invalid")
        expected = b"# Approved on second workstation\nVerify outcomes.\n"
        (other_source / "global" / "AGENTS.md").write_bytes(expected)
        self.git(other_source, "add", ".")
        self.git(other_source, "commit", "-m", "second publication")
        self.git(other_source, "push")
        plan = sync.synchronize(**options)
        sync.synchronize(**options, apply=True, plan_hash=plan["plan_hash"])
        self.deploy()
        for home in (self.codex, self.pi, second / "codex", second / "pi"):
            self.assertEqual(expected, (home / "AGENTS.md").read_bytes())

    def test_absent_unenrolled_host_is_not_installed(self):
        self.codex.mkdir()
        with patch.object(Path, "home", return_value=self.root), patch.dict(os.environ, {"PI_CODING_AGENT_DIR": ""}):
            plan = sync.synchronize(source=self.source, state_dir=self.state)
        self.assertEqual(["codex"], [row["host"] for row in plan["hosts"]])
        self.assertFalse(self.pi.exists())

    def test_changed_target_after_lock_wait_is_rejected(self):
        from contextlib import contextmanager
        self.deploy()
        plan = sync.synchronize(**self.kw)
        @contextmanager
        def mutate_during_lock(*args):
            (self.pi / "AGENTS.md").write_bytes(b"Concurrent user edit\n")
            yield
        with patch.object(sync.InstructionRepository, "lock_paths", mutate_during_lock):
            self.assert_error("instruction_sync_stale_plan", apply=True, plan_hash=plan["plan_hash"])
        self.assertEqual(b"Concurrent user edit\n", (self.pi / "AGENTS.md").read_bytes())

    def test_concurrent_edit_between_host_writes_is_not_overwritten(self):
        self.deploy()
        old = (self.codex / "AGENTS.md").read_bytes()
        updated = self.publish()
        write = sync.atomic_write
        def edit_other_host(path, data):
            result = write(path, data)
            if path == self.codex / "AGENTS.md" and data == updated:
                (self.pi / "AGENTS.md").write_bytes(b"Concurrent local edit\n")
            return result
        with patch.object(sync, "atomic_write", side_effect=edit_other_host):
            with self.assertRaises(CoreError) as error:
                self.deploy()
        self.assertEqual("instruction_sync_stale_plan", error.exception.code)
        self.assertEqual(old, (self.codex / "AGENTS.md").read_bytes())
        self.assertEqual(b"Concurrent local edit\n", (self.pi / "AGENTS.md").read_bytes())

    def test_failed_rollback_retains_recovery_material(self):
        self.deploy()
        self.publish()
        write = sync.atomic_write
        def fail_pi(path, data):
            if path == self.pi / "AGENTS.md":
                raise OSError("unavailable throughout rollback")
            return write(path, data)
        with patch.object(sync, "atomic_write", side_effect=fail_pi):
            with self.assertRaises(CoreError) as error:
                self.deploy()
        self.assertEqual("instruction_sync_recovery_required", error.exception.code)
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())
        self.assert_error("instruction_sync_recovery_required")

    def test_first_use_difference_blocks_every_target(self):
        self.pi.mkdir()
        (self.pi / "AGENTS.md").write_bytes(b"Local rules\n")
        self.assert_error("global_instruction_drift")
        self.assertFalse(self.codex.exists())
        self.assertEqual(b"Local rules\n", (self.pi / "AGENTS.md").read_bytes())

    def test_first_enrollment_can_adopt_only_exact_reviewed_bytes(self):
        self.pi.mkdir()
        original = b"Reviewed older instructions\n"
        (self.pi / "AGENTS.md").write_bytes(original)
        self.assert_error("global_instruction_drift")
        accepted = ["pi=" + sync._hash(original)]
        self.deploy(adopt_existing=accepted)
        self.assertEqual((self.source / "global" / "AGENTS.md").read_bytes(), (self.pi / "AGENTS.md").read_bytes())
        self.assert_error("instruction_adoption_invalid", adopt_existing=accepted)

    def test_changed_first_enrollment_bytes_reject_reviewed_hash(self):
        self.pi.mkdir()
        (self.pi / "AGENTS.md").write_bytes(b"Changed after review\n")
        self.assert_error("instruction_sync_stale_plan", adopt_existing=["pi=" + sync._hash(b"Reviewed\n")])
        self.assertFalse(self.codex.exists())

    def test_drift_after_deployment_blocks_all_updates(self):
        self.deploy()
        old = (self.codex / "AGENTS.md").read_bytes()
        (self.pi / "AGENTS.md").write_bytes(b"Local edit\n")
        self.publish()
        self.assert_error("global_instruction_drift")
        self.assertEqual(old, (self.codex / "AGENTS.md").read_bytes())

    def test_override_even_empty_is_a_blocker(self):
        self.pi.mkdir()
        (self.pi / "AGENTS.override.md").write_bytes(b"")
        self.assert_error("instruction_target_shadowed")

    def test_stale_plan_after_remote_update(self):
        plan = sync.synchronize(**self.kw)
        self.publish()
        self.assert_error("instruction_sync_stale_plan", apply=True, plan_hash=plan["plan_hash"])
        self.assertFalse(self.codex.exists())

    def test_unpublished_source_is_not_silently_discarded(self):
        (self.source / "global" / "AGENTS.md").write_bytes(b"Unpublished\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "not pushed")
        self.assert_error("instruction_source_unpublished")

    def test_dirty_source_is_blocked(self):
        (self.source / "untracked").write_text("local work")
        self.assert_error("instruction_source_dirty")

    def test_published_revert_updates_both_hosts(self):
        self.deploy()
        original = (self.pi / "AGENTS.md").read_bytes()
        self.publish()
        self.deploy()
        self.git(self.source, "revert", "--no-edit", "HEAD")
        self.git(self.source, "push")
        self.deploy()
        self.assertEqual(original, (self.codex / "AGENTS.md").read_bytes())
        self.assertEqual(original, (self.pi / "AGENTS.md").read_bytes())

    def test_source_identity_change_is_blocked(self):
        self.deploy()
        self.git(self.source, "remote", "set-url", "origin", str(self.root / "different.git"))
        self.assert_error("instruction_source_rebind_required")

    def test_remote_failure_preserves_targets(self):
        self.deploy()
        old = (self.pi / "AGENTS.md").read_bytes()
        moved = self.root / "offline.git"
        self.remote.rename(moved)
        self.assert_error("instruction_source_unavailable")
        self.assertEqual(old, (self.pi / "AGENTS.md").read_bytes())

    def test_duplicate_host_target_rejected(self):
        self.assert_error("instruction_target_alias", pi_agent_dir=self.codex)

    def test_hardlinked_target_rejected(self):
        self.pi.mkdir()
        original = self.root / "original"
        original.write_bytes(b"Linked\n")
        os.link(original, self.pi / "AGENTS.md")
        self.assert_error("instruction_target_unsafe")

    def test_existing_registry_runtime_is_preserved(self):
        store = sync._store(self.codex)
        with CoreDatabase(store, create=True, now="2026-01-01T00:00:00Z") as db:
            registry = InstallationRegistry(db)
            registry.bind_runtime(artifact_path=self.root / "runtime", artifact_sha256="a" * 64,
                                  hook_config_sha256="b" * 64, platform_command_sha256="c" * 64,
                                  source_commit=None, source_tree_clean=True, skill_sha256=None)
            db.conn.commit()
            before = registry.runtime().to_dict()
        self.deploy()
        with CoreDatabase(store) as db:
            self.assertEqual(before, InstallationRegistry(db).runtime().to_dict())

    def test_second_target_failure_restores_files_and_bindings(self):
        self.deploy()
        old_files = {home: (home / "AGENTS.md").read_bytes() for home in (self.codex, self.pi)}
        old_rows = {home: sync._binding(home) for home in old_files}
        self.publish()
        real_write = sync.atomic_write
        failed = False
        def write(path, data):
            nonlocal failed
            if path == self.pi / "AGENTS.md" and not failed:
                failed = True
                raise OSError("fixture write failure")
            return real_write(path, data)
        with patch.object(sync, "atomic_write", side_effect=write):
            with self.assertRaises(OSError):
                self.deploy()
        for home, data in old_files.items():
            self.assertEqual(data, (home / "AGENTS.md").read_bytes())
            self.assertEqual(old_rows[home], sync._binding(home))
        self.assertFalse((self.state / "instruction-sync-recovery.json").exists())

    def test_recovery_journal_blocks_subsequent_apply(self):
        self.state.mkdir()
        (self.state / "instruction-sync-recovery.json").write_text("{}")
        self.assert_error("instruction_sync_recovery_required")

    def test_bootstrap_preserves_the_multihost_owner_snapshot(self):
        from tests.test_global_owner_scout_v5 import load_module, MANAGED_SOURCES
        managed = load_module("instruction_sync_bootstrap", MANAGED_SOURCES)
        self.deploy()
        bound = Path(sync._binding(self.codex)["source_root"])
        self.assertEqual(bound, managed._current_owner_root(self.codex))
        observed = managed.inspect_existing_checkout(bound)
        preserved = managed._preserved_owner_identity(self.codex, observed)
        self.assertEqual(observed["commit"], preserved["commit"])
        specs = (managed.SourceSpec("sidecar", str(self.remote), "main", observed["commit"]),)
        plan = managed._source_cutover_state(self.codex, specs)
        self.assertEqual("keep_owner", plan["owner_action"])
        self.assertFalse(any(change.startswith("canonical_owner:") for change in plan["changes"]))
        self.assertEqual(observed["commit"], plan["desired"]["canonical_owner"]["commit"])
        # Tampered enrollment cannot qualify a different Codex home.
        config_path = self.state / "instruction-sync.json"
        config = json.loads(config_path.read_bytes())
        config["targets"]["codex"] = str(self.root / "other-home")
        config_path.write_text(json.dumps(config))
        with self.assertRaises(managed.BootstrapError):
            managed._preserved_owner_identity(self.codex, observed)

    def test_portable_entry_uses_verified_wheel_not_ambient_package(self):
        project = Path(__file__).resolve().parents[1]
        script = project / ".agents/skills/agent-memory-workstation-bootstrap/scripts/sync_instructions.py"
        resolved = self.root / "resolved"
        portable = resolved / "portable"
        (portable / "core").mkdir(parents=True)
        wheel = portable / "core" / "agent_memory_sidecar-fixture.whl"
        built_wheel = os.environ.get("AGENT_MEMORY_SYNC_TEST_WHEEL")
        if built_wheel:
            wheel.write_bytes(Path(built_wheel).read_bytes())
        else:
            with zipfile.ZipFile(wheel, "w") as archive:
                for source in (project / "src/agent_memory_sidecar").glob("*.py"):
                    archive.write(source, "agent_memory_sidecar/" + source.name)
        archive_path = resolved / "agent-memory-portable-fixture.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(wheel, "core/" + wheel.name)
        (resolved / "resolution.json").write_text(json.dumps({"status": "verified", "portable_root": "portable",
            "assets": {archive_path.name: {"sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest()}}}))
        args = [sys.executable, "-B", str(script), "--portable-root", str(portable), "--source", str(self.source),
                "--state-dir", str(self.state), "--codex-home", str(self.codex), "--pi-agent-dir", str(self.pi)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plan = json.loads(result.stdout)["data"]
        result = subprocess.run([*args, "--apply", "--plan-hash", plan["plan_hash"]], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("reload_required", json.loads(result.stdout)["data"]["status"])
        wheel.write_bytes(b"tampered")
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertEqual("instruction_sync_release_unverified", json.loads(result.stdout)["error"])

    def test_existing_binding_admits_old_content_and_migrates_without_hooks(self):
        self.codex.mkdir()
        previous = (self.source / "global" / "AGENTS.md").read_bytes()
        (self.codex / "AGENTS.md").write_bytes(previous)
        with CoreDatabase(sync._store(self.codex), create=True, now="2026-01-01T00:00:00Z") as db:
            InstallationRegistry(db).bind_global(source_root=self.source,
                source_commit=self.git(self.source, "rev-parse", "HEAD"),
                source_file_sha256=sync._hash(previous), target_file_sha256=sync._hash(previous))
            db.conn.commit()
        updated = self.publish()
        self.deploy()
        self.assertEqual(updated, (self.codex / "AGENTS.md").read_bytes())
        self.assertFalse((self.pi / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()
