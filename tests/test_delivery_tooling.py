from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
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

    def _make_fake_runner(self, *, codex_payload: dict | None, mutate_agents: Path | None = None):
        commit = "a" * 40

        def fake_run(command: list[str], *, cwd: Path | None = None, input_text: str | None = None, timeout: int = 120):
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
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "fake-codex":
                assert input_text and "rule list" in input_text
                if mutate_agents is not None:
                    mutate_agents.write_text("tampered\n", encoding="utf-8")
                if codex_payload is None:
                    return subprocess.CompletedProcess(command, 1, "", "sandbox crash")
                return subprocess.CompletedProcess(command, 0, json.dumps(codex_payload), "")
            raise AssertionError(f"unexpected command: {command}")

        return fake_run

    def test_sandbox_gate_passes_and_rejects_mutation_or_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.fake_root = base / "repo"
            self.fake_root.mkdir()
            (self.fake_root / "AGENTS.md").write_text("# proj\n", encoding="utf-8")
            codex_home = base / "codex_home"
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("# global\n", encoding="utf-8")

            ok_receipt = self.gate.verify_candidate_in_codex_sandbox(
                root=self.fake_root,
                codex_home=codex_home,
                runner=self._make_fake_runner(
                    codex_payload={
                        "candidate_rc": 0,
                        "status": "ok",
                        "rules_count": 3,
                        "pending_count": None,
                        "pending_status": "store_access_restricted",
                        "stderr_tail": "",
                    }
                ),
                codex_executable="fake-codex",
            )
            self.assertEqual("passed", ok_receipt["status"])
            self.assertEqual("a" * 40, ok_receipt["commit"])
            self.assertTrue(ok_receipt["protected_targets_unchanged"])

            with self.assertRaisesRegex(self.gate.SandboxGateError, "sandbox_gate_candidate_nonzero_exit"):
                self.gate.verify_candidate_in_codex_sandbox(
                    root=self.fake_root,
                    codex_home=codex_home,
                    runner=self._make_fake_runner(
                        codex_payload={"candidate_rc": 1, "status": "error", "rules_count": 0}
                    ),
                    codex_executable="fake-codex",
                )

            with self.assertRaisesRegex(self.gate.SandboxGateError, "sandbox_gate_global_agents_mutated"):
                self.gate.verify_candidate_in_codex_sandbox(
                    root=self.fake_root,
                    codex_home=codex_home,
                    runner=self._make_fake_runner(
                        codex_payload={
                            "candidate_rc": 0,
                            "status": "ok",
                            "rules_count": 3,
                            "pending_count": None,
                            "pending_status": "store_access_restricted",
                        },
                        mutate_agents=codex_home / "AGENTS.md",
                    ),
                    codex_executable="fake-codex",
                )


class PublishReleaseEnhancementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.promotion = _load("test_publish_release_enh_mod", "scripts/publish_release.py")
        cls.promo_tests = _load("test_release_promo_helpers", "tests/test_release_promotion.py")

    def test_download_draft_reconstructs_nested_core_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_dir = self.promo_tests.make_fixture(root)
            out_dir = root / "downloaded"

            def fake_download(command: list[str], cwd: Path) -> str:
                del cwd
                assert command[:3] == ["gh", "release", "download"]
                dst = Path(command[command.index("--dir") + 1])
                for f in fixture_dir.rglob("*"):
                    if f.is_file():
                        shutil.copyfile(f, dst / f.name)
                return ""

            result = self.promotion.download_draft_assets(
                root=root,
                repository=self.promo_tests.REPOSITORY,
                tag=self.promo_tests.TAG,
                output_dir=out_dir,
                runner=fake_download,
            )
            self.assertEqual("draft_assets_downloaded", result["status"])
            self.assertTrue((out_dir / "core/agent_memory_sidecar-0.3.7-py3-none-any.whl").is_file())

    def test_allow_ancestor_main_accepts_ancestor_and_rejects_non_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_dir = self.promo_tests.make_fixture(root)
            base_runner = self.promo_tests.FakeRunner(self.promotion, asset_dir)
            newer_main = "c" * 40

            def ancestor_runner(command: list[str], cwd: Path) -> str:
                if command[:3] == ["git", "ls-remote", "origin"] and "refs/heads/main" in command:
                    return f"{newer_main}\trefs/heads/main"
                if command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    if command[3] == self.promo_tests.COMMIT and command[4] == newer_main:
                        return ""
                    raise self.promotion.PromotionError("promotion_command_failed:git:not ancestor")
                return base_runner(command, cwd)

            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_remote_main_mismatch"):
                self.promotion.inspect_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=self.promo_tests.REPOSITORY,
                    tag=self.promo_tests.TAG,
                    expected_commit=self.promo_tests.COMMIT,
                    runner=ancestor_runner,
                    allow_ancestor_main=False,
                )

            plan = self.promotion.inspect_plan(
                root=root,
                asset_dir=asset_dir,
                repository=self.promo_tests.REPOSITORY,
                tag=self.promo_tests.TAG,
                expected_commit=self.promo_tests.COMMIT,
                runner=ancestor_runner,
                allow_ancestor_main=True,
            )
            self.assertEqual("authorization_required", plan["status"])


if __name__ == "__main__":
    unittest.main()
