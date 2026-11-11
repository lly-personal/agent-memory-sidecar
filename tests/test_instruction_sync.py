from __future__ import annotations

import io
import json
import os
import shutil
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
        env = patch.dict(os.environ, {"CODEX_HOME": str(self.codex), "PI_CODING_AGENT_DIR": str(self.pi),
                                      "CLAUDE_CONFIG_DIR": ""})
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

    def test_claude_requires_explicit_enrollment_and_reuses_it(self):
        claude = self.root / "claude"
        claude.mkdir()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude)}):
            self.assertEqual({"codex", "pi"}, {row["host"] for row in sync.synchronize(**self.kw)["hosts"]})
            self.assert_error("instruction_target_rebind_required", claude_home=self.root / "other")
            self.deploy(claude_home=claude)
            self.assertEqual((self.source / "global" / "AGENTS.md").read_bytes(), (claude / "CLAUDE.md").read_bytes())
            self.assertFalse((claude / "AGENTS.md").exists())
            self.assertEqual({"codex", "pi", "claude"}, {row["host"] for row in sync.synchronize(**self.kw)["hosts"]})
            self.assert_error("instruction_target_rebind_required", claude_home=self.root / "other")

    def test_claude_first_enrollment_and_subsequent_drift_fail_closed(self):
        claude = self.root / "claude"
        claude.mkdir()
        target = claude / "CLAUDE.md"
        target.write_bytes(b"existing instructions\n")
        self.assert_error("global_instruction_drift", claude_home=claude)
        self.assertFalse(self.codex.exists())
        self.deploy(claude_home=claude, adopt_existing=["claude=" + sync._hash(target.read_bytes())])
        old_codex = (self.codex / "AGENTS.md").read_bytes()
        target.write_bytes(b"local edit\n")
        self.publish()
        self.assert_error("global_instruction_drift", claude_home=claude)
        self.assertEqual(old_codex, (self.codex / "AGENTS.md").read_bytes())
        self.assertEqual(b"local edit\n", target.read_bytes())

    def test_claude_write_failure_rolls_back_other_hosts(self):
        claude = self.root / "claude"
        claude.mkdir()
        self.deploy(claude_home=claude)
        homes = {self.codex: "AGENTS.md", self.pi: "AGENTS.md", claude: "CLAUDE.md"}
        before = {home: (home / name).read_bytes() for home, name in homes.items()}
        bindings = {home: sync._binding(home) for home in homes}
        self.publish()
        write = sync.atomic_write
        failed = False
        def fail_once(path, data, **kwargs):
            nonlocal failed
            if path == claude / "CLAUDE.md" and not failed:
                failed = True
                raise OSError("fixture write failure")
            return write(path, data, **kwargs)
        with patch.object(sync, "atomic_write", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.deploy(claude_home=claude)
        for home, name in homes.items():
            self.assertEqual(before[home], (home / name).read_bytes())
            self.assertEqual(bindings[home], sync._binding(home))
        self.assertFalse((self.state / "instruction-sync-recovery.json").exists())

    def test_published_update_and_revert_reach_all_three_hosts(self):
        claude = self.root / "claude"
        claude.mkdir()
        self.deploy(claude_home=claude)
        original = (claude / "CLAUDE.md").read_bytes()
        updated = self.publish()
        self.deploy(claude_home=claude)
        homes = {self.codex: "AGENTS.md", self.pi: "AGENTS.md", claude: "CLAUDE.md"}
        for home, name in homes.items():
            self.assertEqual(updated, (home / name).read_bytes())
        self.git(self.source, "revert", "--no-edit", "HEAD")
        self.git(self.source, "push")
        self.deploy(claude_home=claude)
        for home, name in homes.items():
            self.assertEqual(original, (home / name).read_bytes())

    def test_claude_linked_instruction_file_is_rejected(self):
        claude = self.root / "claude"
        claude.mkdir()
        original = self.root / "external"
        original.write_text("user content\n")
        try:
            (claude / "CLAUDE.md").symlink_to(original)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(CoreError):
            sync.synchronize(**self.kw, claude_home=claude)
        self.assertEqual("user content\n", original.read_text())
        self.assertFalse(self.codex.exists())

    def test_cli_claude_target_and_changed_plan(self):
        claude = self.root / "claude"
        claude.mkdir()
        args = ["instructions", "sync", "--source", str(self.source), "--codex-home", str(self.codex),
                "--pi-agent-dir", str(self.pi), "--claude-home", str(claude), "--state-dir", str(self.state)]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(args))
        plan = json.loads(output.getvalue())["data"]
        self.publish()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(1, cli.main([*args, "--apply", "--plan-hash", plan["plan_hash"]]))
        self.assertEqual("instruction_sync_stale_plan", json.loads(output.getvalue())["error"]["code"])
        self.assertFalse((claude / "CLAUDE.md").exists())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(args))
        plan = json.loads(output.getvalue())["data"]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main([*args, "--apply", "--plan-hash", plan["plan_hash"]]))
        self.assertEqual((self.source / "global" / "AGENTS.md").read_bytes(), (claude / "CLAUDE.md").read_bytes())

    def test_claude_enrollment_requires_existing_host_directory(self):
        self.assert_error("instruction_targets_missing", claude_home=self.root / "not-a-host")
        self.assertFalse(self.codex.exists())

    def enroll_claude(self):
        home = self.root / "claude"
        home.mkdir()
        self.deploy(claude_home=home)
        return home

    def exit_claude(self):
        plan = sync.unenroll_claude(state_dir=self.state)
        return sync.unenroll_claude(state_dir=self.state, apply=True, plan_hash=plan["plan_hash"])

    def test_claude_exit_cli_preview_and_apply_preserve_other_state(self):
        home = self.enroll_claude()
        target, config = home / "CLAUDE.md", self.state / "instruction-sync.json"
        settings = home / "settings.json"
        settings.write_text('{"user":"content"}')
        paths = [target, config, sync._store(home), self.codex / "AGENTS.md", self.pi / "AGENTS.md",
                 sync._store(self.codex), sync._store(self.pi), settings]
        before = {path: path.read_bytes() for path in paths}
        args = ["instructions", "sync", "--unenroll-claude", "--state-dir", str(self.state)]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(args))
        plan = json.loads(output.getvalue())["data"]
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertFalse((self.state / "instruction-sync-recovery.json").exists())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main([*args, "--apply", "--plan-hash", plan["plan_hash"]]))
        result = json.loads(output.getvalue())["data"]
        self.assertEqual("unenrolled", result["status"])
        self.assertEqual({"contract_version", "host", "plan_hash", "remaining_hosts", "applied", "adoption", "status"}, set(result))
        self.assertEqual(["codex", "pi"], result["remaining_hosts"])
        self.assertFalse(target.exists())
        self.assertIsNone(sync._binding(home))
        self.assertTrue(sync._store(home).is_file())
        for path in paths[3:]:
            self.assertEqual(before[path], path.read_bytes())
        self.assertEqual({"codex", "pi"}, set(json.loads(config.read_bytes())["targets"]))
        # A second exit must never remove an independently created user document.
        target.write_text("new user content")
        with self.assertRaises(CoreError) as caught:
            self.exit_claude()
        self.assertEqual("instruction_host_not_enrolled", caught.exception.code)
        self.assertEqual("new user content", target.read_text())

    def test_claude_exit_drift_context_and_stale_plan_are_blocked(self):
        home = self.enroll_claude()
        target = home / "CLAUDE.md"
        plan = sync.unenroll_claude(state_dir=self.state)
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root / "other")}):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
            self.assertEqual("instruction_target_rebind_required", caught.exception.code)
        binding = sync._binding(home)
        sync._set_binding(home, {**binding, "updated_at": "2026-01-02T00:00:00Z"})
        with self.assertRaises(CoreError) as caught:
            sync.unenroll_claude(state_dir=self.state, apply=True, plan_hash=plan["plan_hash"])
        self.assertEqual("instruction_sync_stale_plan", caught.exception.code)
        target.write_text("user edit")
        with self.assertRaises(CoreError) as caught:
            self.exit_claude()
        self.assertEqual("global_instruction_drift", caught.exception.code)
        self.assertEqual("user edit", target.read_text())
        target.unlink()
        with self.assertRaises(CoreError) as caught:
            self.exit_claude()
        self.assertEqual("global_instruction_drift", caught.exception.code)

    def test_claude_exit_is_offline_and_preserves_runtime_registry(self):
        home = self.enroll_claude()
        with CoreDatabase(sync._store(home)) as db:
            registry = InstallationRegistry(db)
            registry.bind_runtime(artifact_path=self.root / "runtime", artifact_sha256="a" * 64,
                                  hook_config_sha256="b" * 64, platform_command_sha256="c" * 64,
                                  source_commit=None, source_tree_clean=True, skill_sha256=None)
            db.conn.commit()
            runtime = registry.runtime().to_dict()
        self.remote.rename(self.root / "offline.git")
        with patch.object(sync, "_git", side_effect=AssertionError("exit must not call Git")):
            self.assertEqual("unenrolled", self.exit_claude()["status"])
        with CoreDatabase(sync._store(home)) as db:
            self.assertEqual(runtime, InstallationRegistry(db).runtime().to_dict())

    def test_claude_exit_write_failure_restores_projection_binding_and_config(self):
        home = self.enroll_claude()
        target, config = home / "CLAUDE.md", self.state / "instruction-sync.json"
        before, binding, config_before = target.read_bytes(), sync._binding(home), config.read_bytes()
        write = sync.atomic_write
        failed = False
        def fail_once(path, data, **kwargs):
            nonlocal failed
            if path == config and not failed:
                failed = True
                raise OSError("fixture enrollment write failure")
            return write(path, data, **kwargs)
        with patch.object(sync, "atomic_write", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.exit_claude()
        self.assertEqual(before, target.read_bytes())
        self.assertEqual(binding, sync._binding(home))
        self.assertEqual(config_before, config.read_bytes())
        self.assertFalse((self.state / "instruction-sync-recovery.json").exists())

    def test_claude_exit_preserves_concurrent_edit_and_retains_recovery(self):
        home = self.enroll_claude()
        target = home / "CLAUDE.md"
        set_binding = sync._replace_exit_binding
        def fail_after_binding(db, expected, value):
            set_binding(db, expected, value)
            if value is None:
                target.write_text("concurrent user edit")
                raise OSError("fixture failure after binding removal")
        with patch.object(sync, "_replace_exit_binding", side_effect=fail_after_binding):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertEqual("concurrent user edit", target.read_text())
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())
        with self.assertRaises(CoreError) as caught:
            self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)

    def test_claude_exit_does_not_restore_a_file_it_did_not_remove(self):
        home = self.enroll_claude()
        target, journal = home / "CLAUDE.md", self.state / "instruction-sync-recovery.json"
        write = sync.atomic_write
        def delete_before_removal(path, data, **kwargs):
            write(path, data, **kwargs)
            if path == journal:
                target.unlink()
        with patch.object(sync, "atomic_write", side_effect=delete_before_removal):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertFalse(target.exists())

    def test_claude_exit_does_not_recreate_a_concurrently_removed_store(self):
        home = self.enroll_claude()
        set_binding = sync._replace_exit_binding
        removed = refused = False
        def remove_store_after_binding(db, expected, value):
            nonlocal removed, refused
            set_binding(db, expected, value)
            if value is None:
                try:
                    sync._store(home).unlink()
                    removed = True
                except PermissionError:
                    refused = True
                    raise
                raise OSError("fixture concurrent Store removal")
        with patch.object(sync, "_replace_exit_binding", side_effect=remove_store_after_binding):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertTrue(removed or refused)
        self.assertEqual(refused, sync._store(home).exists())
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())

    def test_claude_exit_committed_cleanup_failure_is_not_rolled_back(self):
        home = self.enroll_claude()
        journal = self.state / "instruction-sync-recovery.json"
        unlink = os.unlink
        def fail_journal(path, *args, **kwargs):
            if path in (str(journal), journal.name):
                raise OSError("fixture journal cleanup failure")
            return unlink(path, *args, **kwargs)
        with patch.object(os, "unlink", fail_journal):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_cleanup_required", caught.exception.code)
        self.assertTrue(caught.exception.details["operation_committed"])
        self.assertFalse((home / "CLAUDE.md").exists())
        self.assertIsNone(sync._binding(home))
        self.assertNotIn("claude", json.loads((self.state / "instruction-sync.json").read_bytes())["targets"])
        self.assertTrue(journal.is_file())

    @unittest.skipIf(os.name == "nt", "Windows held ancestors prohibit the directory replacement")
    def test_exit_cannot_mutate_a_replacement_store(self):
        home = self.enroll_claude()
        moved = self.root / "original-home"
        binding = sync._binding(home)
        replace = sync._replace_exit_binding
        swapped = False
        def replace_parent(db, expected, value):
            nonlocal swapped
            if value is None and not swapped:
                swapped = True
                home.rename(moved)
                sync._store(home).parent.mkdir(parents=True)
                shutil.copyfile(sync._store(moved), sync._store(home))
            replace(db, expected, value)
        with patch.object(sync, "_replace_exit_binding", side_effect=replace_parent):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertEqual(binding, sync._binding(home))
        self.assertEqual(binding, sync._binding(moved))
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())

    def test_exit_preserves_a_concurrent_binding_update(self):
        home = self.enroll_claude()
        binding = sync._binding(home)
        updated = {**binding, "updated_at": "2026-01-02T00:00:00Z"}
        replace = sync._replace_exit_binding
        changed = False
        def update_binding(db, expected, value):
            nonlocal changed
            if value is None and not changed:
                changed = True
                sync._set_binding(home, updated)
            replace(db, expected, value)
        with patch.object(sync, "_replace_exit_binding", side_effect=update_binding):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertEqual(updated, sync._binding(home))
        self.assertTrue((home / "CLAUDE.md").is_file())
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())

    def test_exit_does_not_restore_a_concurrent_binding_removal(self):
        home = self.enroll_claude()
        replace = sync._replace_exit_binding
        changed = False
        def remove_binding(db, expected, value):
            nonlocal changed
            if value is None and not changed:
                changed = True
                sync._set_binding(home, None)
            replace(db, expected, value)
        with patch.object(sync, "_replace_exit_binding", side_effect=remove_binding):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertIsNone(sync._binding(home))
        self.assertTrue((home / "CLAUDE.md").is_file())
        self.assertTrue((self.state / "instruction-sync-recovery.json").is_file())

    @unittest.skipIf(os.name == "nt", "Windows held ancestors prohibit the directory replacement")
    def test_exit_preserves_a_replacement_state_directory(self):
        self.check_exit_state_move(replacement=True)

    @unittest.skipIf(os.name == "nt", "Windows held ancestors prohibit the directory replacement")
    def test_exit_retains_recovery_when_state_directory_disappears(self):
        self.check_exit_state_move(replacement=False)

    def check_exit_state_move(self, *, replacement):
        home = self.enroll_claude()
        config = self.state / "instruction-sync.json"
        saved, binding = config.read_bytes(), sync._binding(home)
        moved = self.root / "original-state"
        foreign = b'{"foreign":"user-state"}'
        write = sync.atomic_write
        swapped = False
        def replace_state(path, data, **kwargs):
            nonlocal swapped
            if path == config and not swapped:
                swapped = True
                self.state.rename(moved)
                if replacement:
                    self.state.mkdir()
                    config.write_bytes(foreign)
            return write(path, data, **kwargs)
        with patch.object(sync, "atomic_write", side_effect=replace_state):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        if replacement:
            self.assertEqual(foreign, config.read_bytes())
        else:
            self.assertFalse(self.state.exists())
        self.assertEqual(saved, (moved / config.name).read_bytes())
        self.assertEqual(binding, sync._binding(home))
        self.assertTrue((home / "CLAUDE.md").is_file())
        self.assertTrue((moved / "instruction-sync-recovery.json").is_file())

    def test_claude_exit_rolled_back_cleanup_failure_retains_blocker(self):
        home = self.enroll_claude()
        target, journal, config = home / "CLAUDE.md", self.state / "instruction-sync-recovery.json", self.state / "instruction-sync.json"
        before, binding, saved = target.read_bytes(), sync._binding(home), config.read_bytes()
        write, unlink = sync.atomic_write, os.unlink
        def fail_config(path, data, **kwargs):
            if path == config:
                raise OSError("fixture config write failure")
            return write(path, data, **kwargs)
        def fail_journal(path, *args, **kwargs):
            if path in (str(journal), journal.name):
                raise OSError("fixture journal cleanup failure")
            return unlink(path, *args, **kwargs)
        with patch.object(sync, "atomic_write", side_effect=fail_config), patch.object(os, "unlink", fail_journal):
            with self.assertRaises(CoreError) as caught:
                self.exit_claude()
        self.assertEqual("instruction_sync_recovery_required", caught.exception.code)
        self.assertFalse(caught.exception.details["operation_committed"])
        self.assertEqual(before, target.read_bytes())
        self.assertEqual(binding, sync._binding(home))
        self.assertEqual(saved, config.read_bytes())
        self.assertTrue(journal.is_file())

    def test_claude_exit_rejects_combined_source_options(self):
        self.enroll_claude()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(1, cli.main(["instructions", "sync", "--unenroll-claude", "--source", str(self.source),
                                          "--state-dir", str(self.state)]))
        self.assertEqual("invalid_request", json.loads(output.getvalue())["error"]["code"])

    def test_hosts_cannot_share_a_store_through_trusted_os_aliases(self):
        self.deploy()
        alternate = self.codex.resolve()
        if alternate == self.codex:
            self.skipTest("host has no trusted alternate root spelling")
        self.assertTrue(alternate.samefile(self.codex))
        self.assert_error("instruction_target_alias", claude_home=alternate)
        self.assertIsNotNone(sync._binding(self.codex))

    def test_exit_keeps_a_user_save_at_the_removal_boundary(self):
        home = self.enroll_claude()
        target = home / "CLAUDE.md"
        unlink, replace = Path.unlink, os.replace
        injected = False
        def save():
            nonlocal injected
            if not injected:
                target.write_text("new user content")
                injected = True
        def race_unlink(path, *args, **kwargs):
            if path == target:
                save()
            return unlink(path, *args, **kwargs)
        def race_replace(src, dst, *args, **kwargs):
            if str(src) in (target.name, str(target)) and Path(dst).name == "instruction":
                save()
            return replace(src, dst, *args, **kwargs)
        with patch.object(Path, "unlink", race_unlink), patch.object(os, "replace", race_replace):
            with self.assertRaises(CoreError):
                self.exit_claude()
        self.assertTrue(injected)
        candidates = [target, *home.glob(".agent-memory-exit-*/instruction")]
        self.assertTrue(any(path.exists() and path.read_text() == "new user content" for path in candidates))
        self.assertTrue((self.state / "instruction-sync-recovery.json").exists())

    @unittest.skipIf(os.name == "nt", "Windows rename denial is covered by the held-directory native test")
    def test_exit_parent_swap_cannot_delete_an_unrelated_instruction(self):
        home = self.enroll_claude()
        target = home / "CLAUDE.md"
        other, moved = self.root / "other-home", self.root / "moved-home"
        other.mkdir()
        unrelated = other / "CLAUDE.md"
        unrelated.write_text("unrelated user content")
        unlink, replace = Path.unlink, os.replace
        injected = False
        def swap():
            nonlocal injected
            if not injected:
                home.rename(moved)
                home.symlink_to(other, target_is_directory=True)
                injected = True
        def race_unlink(path, *args, **kwargs):
            if path == target:
                swap()
            return unlink(path, *args, **kwargs)
        def race_replace(src, dst, *args, **kwargs):
            if str(src) == target.name and str(dst) == "instruction":
                swap()
            return replace(src, dst, *args, **kwargs)
        with patch.object(Path, "unlink", race_unlink), patch.object(os, "replace", race_replace):
            with self.assertRaises(CoreError):
                self.exit_claude()
        self.assertTrue(injected)
        self.assertEqual("unrelated user content", unrelated.read_text())

    def test_exit_secures_recovery_before_writing_private_contents(self):
        self.enroll_claude()
        journal = self.state / "instruction-sync-recovery.json"
        write, secure = sync.atomic_write, sync.secure_store_location
        secured = False
        def secure_location(path, **kwargs):
            nonlocal secured
            result = secure(path, **kwargs)
            if path == journal:
                secured = True
            return result
        def write_journal(path, data, **kwargs):
            if path == journal:
                self.assertTrue(secured, "private recovery must be secured before serialization")
                if os.name != "nt":
                    self.assertEqual(0o700, self.state.stat().st_mode & 0o777)
            return write(path, data, **kwargs)
        with patch.object(sync, "secure_store_location", side_effect=secure_location), patch.object(sync, "atomic_write", side_effect=write_journal):
            self.assertEqual("unenrolled", self.exit_claude()["status"])

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
        def edit_other_host(path, data, **kwargs):
            result = write(path, data, **kwargs)
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
        def fail_pi(path, data, **kwargs):
            if path == self.pi / "AGENTS.md":
                raise OSError("unavailable throughout rollback")
            return write(path, data, **kwargs)
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
        def write(path, data, **kwargs):
            nonlocal failed
            if path == self.pi / "AGENTS.md" and not failed:
                failed = True
                raise OSError("fixture write failure")
            return real_write(path, data, **kwargs)
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
        script = project / "skills/agent-memory-workstation-bootstrap/scripts/sync_instructions.py"
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
        claude = self.root / "portable-claude"
        claude.mkdir()
        args = [sys.executable, "-B", str(script), "--portable-root", str(portable), "--source", str(self.source),
                "--state-dir", str(self.state), "--codex-home", str(self.codex), "--pi-agent-dir", str(self.pi),
                "--claude-home", str(claude)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plan = json.loads(result.stdout)["data"]
        result = subprocess.run([*args, "--apply", "--plan-hash", plan["plan_hash"]], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("reload_required", json.loads(result.stdout)["data"]["status"])
        self.assertEqual((self.source / "global" / "AGENTS.md").read_bytes(), (claude / "CLAUDE.md").read_bytes())
        exit_args = [sys.executable, "-B", str(script), "--portable-root", str(portable), "--unenroll-claude",
                     "--state-dir", str(self.state)]
        result = subprocess.run(exit_args, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        exit_plan = json.loads(result.stdout)["data"]
        result = subprocess.run([*exit_args, "--apply", "--plan-hash", exit_plan["plan_hash"]], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("unenrolled", json.loads(result.stdout)["data"]["status"])
        self.assertFalse((claude / "CLAUDE.md").exists())
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
