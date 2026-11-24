from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SyncReleaseVersionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync = _load("test_sync_release_versions_mod", "scripts/sync_release_versions.py")
        cls.builder = _load("test_builder_for_sync_mod", "scripts/build_release_artifacts.py")

    def _copy_sync_surface(self, dst: Path) -> None:
        files = (
            "pyproject.toml",
            "src/agent_memory_sidecar/__init__.py",
            "plugins/agent-memory-sidecar/.codex-plugin/plugin.json",
            "plugins/agent-memory-sidecar/.claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            ".agents/plugins/marketplace.json",
            "COMPATIBILITY.md",
            "README.md",
            "docs/specs/topology.md",
            "docs/specs/interface.md",
            "skills/agent-memory-workstation-bootstrap/SKILL.md",
            "skills/agent-memory-workstation-bootstrap/references/contracts.md",
            "skills/agent-memory-workstation-bootstrap/scripts/bootstrap_contracts.py",
            "skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py",
            "skills/agent-memory-workstation-bootstrap/scripts/enrollment.py",
            "skills/global-owner-scout/SKILL.md",
            "skills/global-owner-scout/scripts/validate_output.py",
            "skills/global-owner-scout/scripts/render_review.py",
            "skills/global-owner-scout/scripts/verify_visible_output.py",
        )
        for rel in files:
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        for anchor in (
            "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor",
            ".agents/skills/agent-memory-bootstrap-anchor",
        ):
            shutil.copytree(ROOT / anchor, dst / anchor, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def test_repo_check_passes_cleanly(self) -> None:
        result = self.sync.sync_versions(ROOT, apply=False)
        self.assertEqual("ok", result["status"], result)
        self.assertEqual([], result["changed_or_drifted"])

    def test_apply_synchronizes_all_versions_and_dual_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "repo"
            self._copy_sync_surface(fake)
            # Introduce drift in repo anchor
            (fake / ".agents/skills/agent-memory-bootstrap-anchor/SKILL.md").write_text("drifted\n", encoding="utf-8")
            drifted = self.sync.sync_versions(fake, apply=False)
            self.assertEqual("drifted", drifted["status"])
            self.assertIn(".agents/skills/agent-memory-bootstrap-anchor/SKILL.md", drifted["changed_or_drifted"])

            applied = self.sync.sync_versions(
                fake,
                core="0.9.1",
                plugin="1.15.0",
                bootstrap="2.7.0",
                scout="5.21.0",
                apply=True,
            )
            self.assertEqual("ok", applied["status"])
            rechecked = self.sync.sync_versions(fake, apply=False)
            self.assertEqual("ok", rechecked["status"], rechecked)
            self.assertEqual(
                {"core": "0.9.1", "plugin": "1.15.0", "bootstrap": "2.7.0", "scout": "5.21.0"},
                self.builder.version_facts(fake),
            )
            self.assertEqual(
                (fake / "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/SKILL.md").read_bytes(),
                (fake / ".agents/skills/agent-memory-bootstrap-anchor/SKILL.md").read_bytes(),
            )


class VerifyReleaseSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = _load("test_verify_release_sandbox_mod", "scripts/verify_release_sandbox.py")

    def _make_fake_runner(
        self,
        *,
        exit_code: int = 0,
        envelope: dict | None = None,
        prose_only: bool = False,
        mutate_agents: Path | None = None,
        captured_env: list[dict[str, str] | None] | None = None,
    ):
        commit = "a" * 40
        entry_holder: dict[str, Path] = {}

        def fake_run(
            command: list[str],
            *,
            cwd: Path | None = None,
            input_text: str | None = None,
            env: dict[str, str] | None = None,
            timeout: int = 120,
        ):
            del cwd, timeout
            if command[:3] == ["git", "-C", str(self.fake_root)] and "status" in command:
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ["git", "-C", str(self.fake_root)] and "rev-parse" in command:
                return subprocess.CompletedProcess(command, 0, commit + "\n", "")
            if command[:3] == ["git", "-C", str(self.fake_root)] and "archive" in command:
                out = Path(command[command.index("-o") + 1])
                out.write_bytes(b"tar")
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "tar":
                return subprocess.CompletedProcess(command, 0, "", "")
            if "-m" in command and "build" in command:
                outdir = Path(command[command.index("--outdir") + 1])
                (outdir / "agent_memory_sidecar-0.7.5-py3-none-any.whl").write_bytes(b"fake-wheel")
                return subprocess.CompletedProcess(command, 0, "", "")
            if "-m" in command and "pip" in command:
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "icacls":
                return subprocess.CompletedProcess(command, 0, "", "")
            if "-c" in command and "install_skill" in command[command.index("-c") + 1]:
                skill_root = Path(command[-1])
                entry = skill_root / "agent-memory" / "scripts" / "agent-memory.py"
                entry.parent.mkdir(parents=True, exist_ok=True)
                entry.write_text("# entry\n", encoding="utf-8")
                entry_holder["entry"] = entry
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "fake-codex":
                assert "--json" in command and input_text and "rule list" in input_text
                if captured_env is not None:
                    captured_env.append(env)
                if mutate_agents is not None:
                    mutate_agents.write_text("tampered\n", encoding="utf-8")
                if prose_only:
                    fake_msg = json.dumps({
                        "type": "item.completed",
                        "item": {"id": "item_1", "type": "agent_message", "text": json.dumps({"candidate_rc": 0, "status": "ok", "rules_count": 3})},
                    })
                    return subprocess.CompletedProcess(command, 0, fake_msg + "\n", "")
                if envelope is None:
                    return subprocess.CompletedProcess(command, 1, "", "sandbox crash")
                cmd_text = str(entry_holder["entry"]).replace("\\", "\\\\")
                cmd_event = json.dumps({
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "command_execution",
                        "command": f'"pwsh.exe" -Command "python -B -S \\"{cmd_text}\\" rule list"',
                        "aggregated_output": json.dumps(envelope),
                        "exit_code": exit_code,
                        "status": "completed",
                    },
                })
                return subprocess.CompletedProcess(command, 0, cmd_event + "\n", "")
            raise AssertionError(f"unexpected command: {command}")

        return fake_run

    def test_sandbox_gate_passes_and_rejects_prose_spoofing_mutation_or_failure(self) -> None:
        valid_envelope = {
            "contract_version": "agent_memory_result_v1",
            "operation": "rule.list",
            "status": "ok",
            "data": {
                "rules": [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}],
                "pending_count": None,
                "pending_status": "store_access_restricted",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.fake_root = base / "repo"
            self.fake_root.mkdir()
            (self.fake_root / "AGENTS.md").write_text("# proj\n", encoding="utf-8")
            codex_home = base / "codex_home"
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("# global\n", encoding="utf-8")

            captured_env: list[dict[str, str] | None] = []
            ok_receipt = self.gate.verify_candidate_in_codex_sandbox(
                root=self.fake_root,
                codex_home=codex_home,
                runner=self._make_fake_runner(envelope=valid_envelope, captured_env=captured_env),
                codex_executable="fake-codex",
            )
            self.assertEqual("passed", ok_receipt["status"])
            self.assertEqual("a" * 40, ok_receipt["commit"])
            self.assertEqual(3, ok_receipt["observed"]["rules_count"])
            self.assertEqual("codex_exec_json_command_execution", ok_receipt["observed"]["verified_via"])
            self.assertTrue(ok_receipt["protected_targets_unchanged"])
            self.assertEqual(str(codex_home), captured_env[0]["CODEX_HOME"])

            with self.assertRaisesRegex(self.gate.SandboxGateError, "sandbox_gate_command_not_executed"):
                self.gate.verify_candidate_in_codex_sandbox(
                    root=self.fake_root,
                    codex_home=codex_home,
                    runner=self._make_fake_runner(prose_only=True),
                    codex_executable="fake-codex",
                )

            with self.assertRaisesRegex(self.gate.SandboxGateError, "sandbox_gate_candidate_nonzero_exit"):
                self.gate.verify_candidate_in_codex_sandbox(
                    root=self.fake_root,
                    codex_home=codex_home,
                    runner=self._make_fake_runner(exit_code=1, envelope={"status": "error"}),
                    codex_executable="fake-codex",
                )

            with self.assertRaisesRegex(self.gate.SandboxGateError, "sandbox_gate_global_agents_mutated"):
                self.gate.verify_candidate_in_codex_sandbox(
                    root=self.fake_root,
                    codex_home=codex_home,
                    runner=self._make_fake_runner(envelope=valid_envelope, mutate_agents=codex_home / "AGENTS.md"),
                    codex_executable="fake-codex",
                )


class PublishReleaseEnhancementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.promotion = _load("test_publish_release_enh_mod", "scripts/publish_release.py")
        cls.promo_tests = _load("test_release_promo_helpers", "tests/test_release_promotion.py")

    def test_download_draft_verifies_draft_flag_digests_and_path_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_dir = self.promo_tests.make_fixture(root)
            out_dir = root / "downloaded"

            def make_runner(*, is_draft: bool = True, tamper_sums: str | None = None):
                def fake_download(command: list[str], cwd: Path) -> str:
                    del cwd
                    if command[:3] == ["gh", "release", "view"]:
                        return json.dumps({
                            "assets": [],
                            "isDraft": is_draft,
                            "isImmutable": not is_draft,
                            "isPrerelease": False,
                            "name": self.promo_tests.TAG,
                            "publishedAt": "" if is_draft else "2026-11-24T00:00:00Z",
                            "tagName": self.promo_tests.TAG,
                            "url": "https://example.invalid/r",
                        })
                    assert command[:3] == ["gh", "release", "download"]
                    dst = Path(command[command.index("--dir") + 1])
                    for f in fixture_dir.rglob("*"):
                        if f.is_file():
                            shutil.copyfile(f, dst / f.name)
                    if tamper_sums is not None:
                        (dst / "SHA256SUMS").write_text(tamper_sums, encoding="utf-8")
                    return ""

                return fake_download

            result = self.promotion.download_draft_assets(
                root=root,
                repository=self.promo_tests.REPOSITORY,
                tag=self.promo_tests.TAG,
                output_dir=out_dir,
                runner=make_runner(is_draft=True),
            )
            self.assertEqual("draft_assets_downloaded", result["status"])
            self.assertTrue((out_dir / "core/agent_memory_sidecar-0.3.7-py3-none-any.whl").is_file())

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_release_not_draft"):
                self.promotion.download_draft_assets(
                    root=root,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    output_dir=root / "published_rejected",
                    runner=make_runner(is_draft=False),
                )

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_checksums_invalid"):
                self.promotion.download_draft_assets(
                    root=root,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    output_dir=root / "backslash_rejected",
                    runner=make_runner(tamper_sums="0" * 64 + "  ..\\escape.whl\n"),
                )
            self.assertFalse((root / "backslash_rejected").exists())

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_checksum_mismatch"):
                self.promotion.download_draft_assets(
                    root=root,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    output_dir=root / "digest_rejected",
                    runner=make_runner(tamper_sums="0" * 64 + "  core/agent_memory_sidecar-0.3.7-py3-none-any.whl\n"),
                )
            self.assertFalse((root / "digest_rejected").exists())

    def test_allow_ancestor_main_accepts_ancestor_and_rejects_non_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = self.promo_tests.make_fixture(root)
            base_runner = self.promo_tests.FakeRunner(self.promotion, asset_dir)
            newer_main = "c" * 40
            unrelated_main = "d" * 40

            def make_ancestor_runner(remote_main_sha: str, is_ancestor: bool):
                def ancestor_runner(command: list[str], cwd: Path) -> str:
                    if command[:3] == ["git", "ls-remote", "origin"] and "refs/heads/main" in command:
                        return f"{remote_main_sha}\trefs/heads/main"
                    if command[:3] == ["git", "merge-base", "--is-ancestor"]:
                        if is_ancestor and command[3] == self.promo_tests.COMMIT and command[4] == remote_main_sha:
                            return ""
                        raise self.promotion.PromotionError("promotion_command_failed:git:not ancestor")
                    return base_runner(command, cwd)

                return ancestor_runner

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_remote_main_mismatch"):
                self.promotion.inspect_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    expected_commit=self.promo_tests.COMMIT,
                    runner=make_ancestor_runner(newer_main, True),
                    allow_ancestor_main=False,
                )

            plan = self.promotion.inspect_plan(
                root=root,
                asset_dir=asset_dir,
                repository=self.promo_tests.REPOSITORY,
                tag=self.promo_tests.TAG,
                expected_commit=self.promo_tests.COMMIT,
                runner=make_ancestor_runner(newer_main, True),
                allow_ancestor_main=True,
            )
            self.assertEqual("authorization_required", plan["status"])

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_command_failed:git:not ancestor"):
                self.promotion.inspect_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    expected_commit=self.promo_tests.COMMIT,
                    runner=make_ancestor_runner(unrelated_main, False),
                    allow_ancestor_main=True,
                )


class ScoutRuntimeDecouplingTests(unittest.TestCase):
    def test_normal_scout_modules_import_without_selftest_fixture_module(self) -> None:
        scout_scripts = str(ROOT / "skills" / "global-owner-scout" / "scripts")
        script = (
            "import sys\n"
            f"sys.path.insert(0, {scout_scripts!r})\n"
            "sys.modules['validate_output_selftest'] = None\n"
            "import validate_output, render_review, verify_visible_output, prepare_delivery, scout\n"
            "assert scout.canonical_json is validate_output.canonical_json\n"
            "assert scout.sha256_bytes is prepare_delivery.sha256_bytes\n"
            "assert scout.build_preflight_summary('codex', 'inspect')['host'] == 'codex'\n"
            "print('DECOUPLED_OK')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-B", "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, proc.returncode, f"stdout={proc.stdout}\nstderr={proc.stderr}")
        self.assertIn("DECOUPLED_OK", proc.stdout)


class DeployMultiHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.deploy = _load("test_deploy_multihost_mod", "scripts/deploy_multihost.py")

    def _make_resolved_fixture(self, base: Path) -> Path:
        resolved_dir = base / "resolved"
        portable = resolved_dir / "portable"
        fixtures = {
            ".agents/skills/global-owner-scout/SKILL.md": "---\nname: global-owner-scout\n---\n# fixture\n",
            ".agents/skills/global-owner-scout/scripts/scout.py": "# scout\n",
            ".agents/skills/global-owner-scout/scripts/validate_output.py": "# validator\n",
            "plugins/agent-memory-sidecar/skills/engineering-contract-review/SKILL.md": "---\nname: engineering-contract-review\n---\n# fixture\n",
            "plugins/agent-memory-sidecar/skills/engineering-contract-review/references/design.md": "# design\n",
            "plugins/agent-memory-sidecar/skills/engineering-contract-review/references/verify.md": "# verify\n",
            "plugins/agent-memory-sidecar/skills/engineering-contract-review/references/recover.md": "# recover\n",
            "plugins/agent-memory-sidecar/skills/engineering-contract-review/references/performance.md": "# perf\n",
            ".agents/skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py": "# bootstrap\n",
        }
        for rel, body in fixtures.items():
            p = portable / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        (portable / "source-manifest.json").write_text('{"sidecar":{"ref":"v0.7.6"}}\n', encoding="utf-8")
        (resolved_dir / "release-manifest.json").write_text(
            json.dumps({"versions": {"core": "0.7.6", "plugin": "1.12.6", "bootstrap": "2.6.3", "scout": "5.20.3"}}),
            encoding="utf-8",
        )
        (resolved_dir / "resolution.json").write_text(
            json.dumps({
                "status": "verified",
                "tag": "v0.7.6",
                "commit": "b" * 40,
                "portable_root": "portable",
            }),
            encoding="utf-8",
        )
        return resolved_dir

    def test_antigravity_atomic_projection_ownership_guard_and_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            resolved_dir = self._make_resolved_fixture(base)
            ag_home = base / "antigravity"
            ag_home.mkdir()

            plan = self.deploy.deploy_multihost(
                hosts=("antigravity",),
                antigravity_home=ag_home,
                apply=False,
                resolved_dir=resolved_dir,
            )
            self.assertEqual("ok", plan["status"])
            self.assertEqual("planned", plan["hosts"]["antigravity"]["status"])

            applied = self.deploy.deploy_multihost(
                hosts=("antigravity",),
                antigravity_home=ag_home,
                apply=True,
                resolved_dir=resolved_dir,
            )
            self.assertEqual("ok", applied["status"])
            self.assertEqual("applied", applied["hosts"]["antigravity"]["status"])
            self.assertTrue((ag_home / "config/skills/global-owner-scout/SKILL.md").is_file())
            self.assertTrue((ag_home / "config/skills/engineering-contract-review/SKILL.md").is_file())
            # Guard against sentinel bug: fresh install must never touch CWD or repo root.
            self.assertTrue((ROOT / ".claude-plugin/marketplace.json").is_file())
            self.assertTrue((ROOT / ".agents/plugins/marketplace.json").is_file())

            noop = self.deploy.deploy_multihost(
                hosts=("antigravity",),
                antigravity_home=ag_home,
                apply=True,
                resolved_dir=resolved_dir,
            )
            self.assertEqual("noop", noop["hosts"]["antigravity"]["status"])

            # Independent unmanaged skill with the same name must block replacement by default.
            custom_home = base / "antigravity_custom"
            custom_skill = custom_home / "config" / "skills" / "global-owner-scout"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text("---\nname: custom-user-skill\n---\n", encoding="utf-8")
            blocked = self.deploy.deploy_multihost(
                hosts=("antigravity",),
                antigravity_home=custom_home,
                apply=True,
                resolved_dir=resolved_dir,
            )
            self.assertEqual("partial_or_blocked", blocked["status"])
            self.assertEqual("blocked", blocked["hosts"]["antigravity"]["status"])
            self.assertIn("antigravity_unmanaged_skill_conflict:global-owner-scout", blocked["hosts"]["antigravity"]["error"])
            self.assertIn("custom-user-skill", (custom_skill / "SKILL.md").read_text(encoding="utf-8"))

    def test_trusted_posix_root_alias_accepts_only_root_owned_top_level_symlink(self) -> None:
        root_link = types.SimpleNamespace(st_mode=0o120777, st_uid=0)
        user_link = types.SimpleNamespace(st_mode=0o120777, st_uid=501)
        self.assertTrue(self.deploy._is_trusted_posix_root_alias(Path("/var"), root_link, platform="posix"))
        self.assertFalse(self.deploy._is_trusted_posix_root_alias(Path("/var/tmp"), root_link, platform="posix"))
        self.assertFalse(self.deploy._is_trusted_posix_root_alias(Path("/var"), user_link, platform="posix"))
        self.assertFalse(self.deploy._is_trusted_posix_root_alias(Path("/var"), root_link, platform="nt"))

    def test_codex_blocked_propagates_and_pi_requires_matching_registration_for_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            resolved_dir = self._make_resolved_fixture(base)
            pi_checkout = base / "pi-repo"
            (pi_checkout / ".git").mkdir(parents=True)

            def codex_blocked_runner(command: list[str], *, cwd: Path | None = None, timeout: int = 180):
                del cwd, timeout
                assert "workstation-reconcile" in command and "--dry-run" in command
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps({
                        "status": "distribution_reconcile_blocked",
                        "blockers": ["plugin_disabled"],
                        "changes": [],
                        "confirmation_required": False,
                        "plan_hash": "f" * 64,
                    }),
                    "",
                )

            dry_blocked = self.deploy.deploy_multihost(
                hosts=("codex",),
                codex_home=base / "codex",
                apply=False,
                runner=codex_blocked_runner,
                resolved_dir=resolved_dir,
            )
            self.assertEqual("partial_or_blocked", dry_blocked["status"])
            self.assertEqual("blocked", dry_blocked["hosts"]["codex"]["status"])
            self.assertEqual(["plugin_disabled"], dry_blocked["hosts"]["codex"]["blockers"])

            # Pi: HEAD already equals desired commit, but `pi list` still points to old ref -> must NOT report noop.
            pi_calls: list[list[str]] = []
            registered = {"ref": "a" * 40}

            def pi_retry_runner(command: list[str], *, cwd: Path | None = None, timeout: int = 180):
                del cwd, timeout
                pi_calls.append(command)
                if command == ["fake-pi", "list"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        f"User packages:\n  git:github.com/lly-personal/agent-memory-sidecar@{registered['ref']}\n    {pi_checkout}\n",
                        "",
                    )
                if command[:3] == ["git", "-C", str(pi_checkout)] and "status" in command:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[:3] == ["git", "-C", str(pi_checkout)] and "rev-parse" in command:
                    return subprocess.CompletedProcess(command, 0, "b" * 40 + "\n", "")
                if command[:2] == ["fake-pi", "install"]:
                    registered["ref"] = "b" * 40
                    return subprocess.CompletedProcess(command, 0, "installed\n", "")
                raise AssertionError(f"unexpected command: {command}")

            pi_plan = self.deploy._deploy_pi(tag="v0.7.6", commit="b" * 40, apply=False, runner=pi_retry_runner, pi_executable="fake-pi")
            self.assertEqual("planned", pi_plan["status"])
            self.assertEqual("pin_register_only", pi_plan["action"])

            pi_apply = self.deploy._deploy_pi(tag="v0.7.6", commit="b" * 40, apply=True, runner=pi_retry_runner, pi_executable="fake-pi")
            self.assertEqual("applied", pi_apply["status"])
            self.assertEqual("b" * 40, pi_apply["registered_ref"])

            pi_noop = self.deploy._deploy_pi(tag="v0.7.6", commit="b" * 40, apply=False, runner=pi_retry_runner, pi_executable="fake-pi")
            self.assertEqual("noop", pi_noop["status"])

    def test_claude_exact_identity_check_and_marketplace_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp) / ".claude"
            plugins_dir = claude_home / "plugins"
            plugins_dir.mkdir(parents=True)
            mk_file = plugins_dir / "known_marketplaces.json"
            mk_file.write_text(
                json.dumps({
                    "agent-memory": {
                        "source": {
                            "source": "git",
                            "url": "https://github.com/lly-personal/agent-memory-sidecar.git",
                            "ref": "v0.7.5",
                        }
                    }
                }),
                encoding="utf-8",
            )
            commands: list[list[str]] = []

            def rollback_runner(command: list[str], *, cwd: Path | None = None, timeout: int = 180):
                del cwd, timeout
                commands.append(command)
                if command[1:] == ["plugin", "list", "--json"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        json.dumps([{"id": "agent-memory-sidecar@agent-memory", "version": "1.12.6", "scope": "user", "enabled": True}]),
                        "",
                    )
                if command[1:4] == ["plugin", "marketplace", "remove"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[1:4] == ["plugin", "marketplace", "add"]:
                    if command[4].endswith("#v0.7.6"):
                        return subprocess.CompletedProcess(command, 1, "", "network error")
                    return subprocess.CompletedProcess(command, 0, "restored", "")
                raise AssertionError(f"unexpected command: {command}")

            # Same version 1.12.6 but marketplace ref is v0.7.5 -> NOT noop!
            plan = self.deploy._deploy_claude(
                tag="v0.7.6", plugin_version="1.12.6", apply=False, runner=rollback_runner, claude_executable="fake-claude", claude_home=claude_home
            )
            self.assertEqual("planned", plan["status"])

            # Failed marketplace add triggers rollback to prior v0.7.5 ref!
            failed = self.deploy._deploy_claude(
                tag="v0.7.6", plugin_version="1.12.6", apply=True, runner=rollback_runner, claude_executable="fake-claude", claude_home=claude_home
            )
            self.assertEqual("blocked", failed["status"])
            self.assertTrue(failed["rollback_attempted"])
            self.assertTrue(failed["rollback_succeeded"])
            self.assertIn(
                ["fake-claude", "plugin", "marketplace", "add", "https://github.com/lly-personal/agent-memory-sidecar.git#v0.7.5"],
                commands,
            )

    def test_codex_confirmation_guard_and_pi_dirty_checkout_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            resolved_dir = self._make_resolved_fixture(base)
            pi_checkout = base / "pi-repo"
            (pi_checkout / ".git").mkdir(parents=True)

            def fake_runner(command: list[str], *, cwd: Path | None = None, timeout: int = 180):
                del cwd, timeout
                if "workstation-reconcile" in command and "--dry-run" in command:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        json.dumps({
                            "status": "confirmation_required",
                            "confirmation_required": True,
                            "changes": ["source:sidecar:replace"],
                            "plan_hash": "e" * 64,
                        }),
                        "",
                    )
                if command[0] == "fake-pi" and command[1:] == ["list"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        f"User packages:\n  git:github.com/lly-personal/agent-memory-sidecar@{'a' * 40}\n    {pi_checkout}\n",
                        "",
                    )
                if command[:3] == ["git", "-C", str(pi_checkout)] and "status" in command:
                    return subprocess.CompletedProcess(command, 0, " M dirty.txt\n", "")
                if command[:3] == ["git", "-C", str(pi_checkout)] and "rev-parse" in command:
                    return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
                raise AssertionError(f"unexpected command: {command}")

            codex_res = self.deploy._deploy_codex(
                portable=resolved_dir / "portable",
                release_manifest=resolved_dir / "release-manifest.json",
                codex_home=base / "codex",
                apply=True,
                confirm_source_change=False,
                runner=fake_runner,
            )
            self.assertEqual("confirmation_required", codex_res["status"])

            pi_res = self.deploy._deploy_pi(
                tag="v0.7.6",
                commit="b" * 40,
                apply=True,
                runner=fake_runner,
                pi_executable="fake-pi",
            )
            self.assertEqual("blocked", pi_res["status"])
            self.assertEqual("pi_checkout_dirty_or_incomplete_preserved", pi_res["error"])


if __name__ == "__main__":
    unittest.main()
