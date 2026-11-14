from __future__ import annotations

import importlib.util
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MANAGED_SOURCES = (
    ROOT
    / "skills" / "agent-memory-workstation-bootstrap"
    / "scripts"
    / "managed_sources.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WorkstationReconcileV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reconcile = load_module("workstation_reconcile_v2", MANAGED_SOURCES)

    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.fixture_root = Path(self.fixture.name).resolve()
        self.native_entries = []
        self.native_hashes = {}
        for name, version in (("agent-memory-workstation-bootstrap", "2.5.7"), ("global-owner-scout", "5.19.4")):
            root = self.fixture_root / "codex" / "skills" / name
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Fixture\n---\n# Fixture\n- Skill version: `{version}`\n")
            self.native_hashes[name] = self.reconcile.physical_tree_hash(root)
            self.native_entries.append({"name": name, "path": str(root / "SKILL.md"), "scope": "user", "enabled": True})
        review_root = (self.fixture_root / "codex" / "plugins" / "cache" / "agent-memory" /
                       "agent-memory-sidecar" / "1.5.1" / "skills" / "engineering-contract-review")
        review_root.mkdir(parents=True)
        (review_root / "SKILL.md").write_text("---\nname: engineering-contract-review\ndescription: Review fixture\n---\n# Review\n")
        self.review_hash = self.reconcile.physical_tree_hash(review_root)
        self.native_entries.append({"name": "agent-memory-sidecar:engineering-contract-review",
                                    "path": str(review_root / "SKILL.md"), "scope": "user", "enabled": True})
        self.native_patch = mock.patch.object(self.reconcile, "native_skill_catalog", side_effect=self.catalog)
        self.native_mock = self.native_patch.start()
        self.addCleanup(self.native_patch.stop)

    def catalog(self, codex_home, roots):
        return [{"cwd": str(root), "skills": self.native_entries, "errors": []} for root in roots]

    def scope(self, *, inventory=None):
        project = self.fixture_root / "project"
        project.mkdir(exist_ok=True)
        return self.reconcile.observe_consumer_scope(
            inventory or self.desktop_inventory(("Project", project)), desired=self.desired_bundle(),
            codex_home=self.fixture_root / "codex", expected_review_sha256=self.review_hash,
        )

    def extra_candidate(self, *, enabled=True, stale=True):
        entry = dict(self.native_entries[0])
        root = self.fixture_root / "project" / ".agents" / "skills" / entry["name"]
        root.mkdir(parents=True)
        shutil.copyfile(entry["path"], root / "SKILL.md")
        if stale:
            with (root / "SKILL.md").open("a") as stream: stream.write("Old source.\n")
        entry.update(path=str(root / "SKILL.md"), scope="repo", enabled=enabled)
        self.native_entries.insert(0, entry)
        return root

    def desired_bundle(self) -> dict[str, object]:
        return {
            "release_ref": "v0.3.10",
            "source_commit": "a" * 40,
            "core_version": "0.3.10",
            "plugin_version": "1.5.1",
            "plugin_sha256": "b" * 64,
            "bootstrap_version": "2.5.7",
            "bootstrap_sha256": self.native_hashes["agent-memory-workstation-bootstrap"],
            "scout_version": "5.19.4",
            "scout_sha256": self.native_hashes["global-owner-scout"],
        }

    def exact_distribution(self) -> dict[str, object]:
        return {
            "marketplace": {
                "status": "present",
                "source_sha256": "e" * 64,
                "ref": "v0.3.10",
                "commit": "a" * 40,
            },
            "plugin": {
                "status": "installed",
                "source_sha256": "e" * 64,
                "ref": "v0.3.10",
                "version": "1.5.1",
                "content_sha256": "b" * 64,
                "enabled": True,
            },
        }

    def source_plan(self) -> dict[str, object]:
        current_sidecar = {"remote_sha256": "e" * 64, "commit": "a" * 40}
        desired_sidecar = {**current_sidecar, "ref": "v0.3.10"}
        plan = {
            "contract_version": self.reconcile.SOURCE_CUTOVER_PLAN_VERSION,
            "bootstrap_version": self.reconcile.BOOTSTRAP_VERSION,
            "status": "noop",
            "owner_action": "keep_owner",
            "current": {"sidecar": current_sidecar, "canonical_owner": None},
            "desired": {"sidecar": desired_sidecar, "canonical_owner": None},
            "changes": [],
            "plan_hash": "",
        }
        plan["plan_hash"] = self.reconcile.object_hash(plan, "plan_hash")
        return plan

    def exact_host(self) -> dict[str, object]:
        return {
            "core": {
                "status": "verified", "version": "0.3.10", "source_commit": "a" * 40,
                "artifact_sha256": "2" * 64,
            },
            "global_binding": "unavailable",
            "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged", "version": "2.5.7", "content_sha256": self.native_hashes["agent-memory-workstation-bootstrap"],
            },
            "scout_skill": {
                "status": "unchanged", "version": "5.19.4", "content_sha256": self.native_hashes["global-owner-scout"],
            },
        }

    def desktop_inventory(self, *projects: tuple[str, Path], status: str = "complete") -> dict[str, object]:
        return {
            "contract_version": "agent_memory_desktop_project_inventory_v1",
            "inventory_status": status,
            "projects": [
                {"display_name": display_name, "path": str(path), "is_git_repository": False}
                for display_name, path in projects
            ],
        }

    def test_consumer_scope_uses_native_enablement_and_preserves_disabled_source(self):
        source = self.extra_candidate(enabled=False)
        before = (source / "SKILL.md").read_bytes()
        scope = self.scope()
        self.assertEqual("exact", scope["status"])
        self.assertEqual("disabled", scope["projects"][0]["skills"][0]["relation"])
        self.assertEqual(before, (source / "SKILL.md").read_bytes())
        self.assertNotIn(str(self.fixture_root), json.dumps(scope))
        self.native_mock.assert_called_once()

    def test_consumer_scope_rejects_duplicate_enabled_entries_even_matching_bytes(self):
        self.extra_candidate(stale=False)
        scope = self.scope()
        self.assertEqual("drifted", scope["status"])
        self.assertEqual(2, sum(item["relation"] == "drifted" for item in scope["projects"][0]["skills"]))

    def test_consumer_scope_detects_enabled_content_drift(self):
        path = Path(self.native_entries[0]["path"])
        with path.open("a") as stream: stream.write("Changed.\n")
        self.assertEqual("drifted", self.scope()["status"])

    def test_consumer_scope_does_not_ignore_missing_engineering_review(self):
        self.native_entries.pop()
        self.assertEqual("bounded", self.scope()["status"])

    def test_consumer_scope_does_not_replace_missing_managed_review_with_identical_copy(self):
        managed = self.native_entries.pop()
        root = self.fixture_root / "standalone-only"
        root.mkdir()
        shutil.copyfile(managed["path"], root / "SKILL.md")
        self.native_entries.append({"name": "engineering-contract-review", "path": str(root / "SKILL.md"),
                                    "scope": "user", "enabled": True})
        self.assertEqual("bounded", self.scope()["status"])

    def test_consumer_scope_rejects_managed_name_at_wrong_path(self):
        root = self.fixture_root / "wrong-managed-path"
        root.mkdir()
        shutil.copyfile(self.native_entries[-1]["path"], root / "SKILL.md")
        self.native_entries[-1]["path"] = str(root / "SKILL.md")
        self.assertEqual("bounded", self.scope()["status"])

    def test_consumer_scope_does_not_ignore_duplicate_engineering_review(self):
        root = self.fixture_root / "standalone"
        root.mkdir()
        shutil.copyfile(self.native_entries[-1]["path"], root / "SKILL.md")
        self.native_entries.append({"name": "engineering-contract-review", "path": str(root / "SKILL.md"),
                                    "scope": "user", "enabled": True})
        scope = self.scope()
        self.assertEqual("drifted", scope["status"])

    def test_consumer_scope_preserves_disabled_review_entries_without_reading_them(self):
        root = self.fixture_root / "disabled"
        root.mkdir()
        standalone = root / "SKILL.md"
        standalone.write_text("User modifications.\n")
        self.native_entries.append({"name": "engineering-contract-review", "path": str(standalone),
                                    "scope": "user", "enabled": False})
        before = standalone.read_bytes()
        real_path_check = self.reconcile._consumer_skill_path
        def reject_disabled_candidate(path):
            self.assertNotEqual(os.path.normcase(str(standalone)), os.path.normcase(str(path)))
            return real_path_check(path)
        with mock.patch.object(self.reconcile, "_consumer_skill_path", side_effect=reject_disabled_candidate):
            scope = self.scope()
        self.assertEqual("exact", scope["status"])
        disabled = next(item for item in scope["projects"][0]["skills"] if not item["enabled"])
        self.assertEqual(("disabled", "unavailable", "unavailable"),
                         (disabled["relation"], disabled["version"], disabled["content_sha256"]))
        self.assertEqual(before, standalone.read_bytes())
        self.assertEqual("1.5.1", scope["projects"][0]["skills"][2]["version"])

    def test_consumer_scope_allows_only_explicitly_disabled_managed_review(self):
        self.native_entries[-1]["enabled"] = False
        Path(self.native_entries[-1]["path"]).unlink()
        scope = self.scope()
        self.assertEqual("exact", scope["status"])
        self.assertTrue(any("停用" in item for item in scope["limitations"]))
        self.native_entries[-1]["path"] = str(self.fixture_root / "elsewhere" / "SKILL.md")
        self.assertEqual("bounded", self.scope()["status"])

    def test_consumer_scope_reports_managed_review_disabled_with_matching_enabled_copy(self):
        root = self.fixture_root / "standalone-enabled"
        root.mkdir()
        shutil.copyfile(self.native_entries[-1]["path"], root / "SKILL.md")
        self.native_entries[-1]["enabled"] = False
        self.native_entries.append({"name": "engineering-contract-review", "path": str(root / "SKILL.md"),
                                    "scope": "user", "enabled": True})
        scope = self.scope()
        self.assertEqual("exact", scope["status"])
        self.assertTrue(any("停用" in item for item in scope["limitations"]))
        self.assertEqual("exact", scope["projects"][0]["skills"][-1]["relation"])

    def test_disabled_review_notice_cannot_be_dropped_from_scope_or_pack(self):
        import copy
        self.native_entries[-1]["enabled"] = False
        scope = self.scope()
        missing_notice = copy.deepcopy(scope)
        missing_notice["limitations"] = []
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "disabled review.*notice"):
            self.reconcile.validate_consumer_scope(missing_notice)
        pack = self.reconcile.build_deployment_pack(
            desired=self.desired_bundle(), observed_distribution=self.exact_distribution(), desired_source_sha256="e" * 64,
            source_sync=self.reconcile._source_sync_from_exact_plan(self.source_plan()), host_materialization=self.exact_host(),
            requires_reload=False, consumer_verified=True, generated_at="2026-11-13T00:00:00Z", consumer_scope=scope,
        )
        self.assertIn("停用", self.reconcile.render_pack(pack))
        pack["limitations"] = [item for item in pack["limitations"] if "停用" not in item]
        pack["pack_hash"] = self.reconcile.object_hash(pack, "pack_hash")
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "consumer scope limitations"):
            self.reconcile.validate_pack(pack)

    def test_consumer_scope_reports_review_drift_without_inventing_version(self):
        with Path(self.native_entries[-1]["path"]).open("a") as stream:
            stream.write("Modified.\n")
        scope = self.scope()
        self.assertEqual("drifted", scope["status"])
        review = scope["projects"][0]["skills"][-1]
        self.assertEqual(("drifted", "unavailable"), (review["relation"], review["version"]))

    def test_consumer_scope_groups_other_plugin_namespace_as_same_capability(self):
        root = self.fixture_root / "other-plugin"
        root.mkdir()
        shutil.copyfile(self.native_entries[-1]["path"], root / "SKILL.md")
        self.native_entries.append({"name": "other-plugin:engineering-contract-review", "path": str(root / "SKILL.md"),
                                    "scope": "user", "enabled": True})
        self.assertEqual("drifted", self.scope()["status"])

    def test_expected_review_hash_is_bound_to_verified_plugin_contents(self):
        portable = self.fixture_root / "portable"
        plugin = portable / "plugins" / "agent-memory-sidecar"
        shutil.copytree(ROOT / "plugins" / "agent-memory-sidecar", plugin)
        for name in ("agent-memory-workstation-bootstrap", "global-owner-scout"):
            (portable / ".agents" / "skills" / name).mkdir(parents=True)
        desired = {**self.desired_bundle(), "plugin_sha256": self.reconcile.physical_tree_hash(
            plugin, excluded_relatives={"source-manifest.json"})}
        expected = self.reconcile.physical_tree_hash(plugin / "skills" / "engineering-contract-review")
        archive_path = self.fixture_root / "agent-memory-portable-0.3.10.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("plugins/agent-memory-sidecar/skills/engineering-contract-review/", b"")
            for file in (plugin / "skills" / "engineering-contract-review").rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(portable).as_posix())
        archive_bytes = archive_path.read_bytes()
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        self.assertEqual(expected, self.reconcile._expected_review_hash(self.fixture_root / "release.json", desired, archive_sha256))
        with (plugin / "skills" / "engineering-contract-review" / "SKILL.md").open("a") as stream:
            stream.write("Changed after verification.\n")
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "verified_plugin_content_changed"):
            self.reconcile._expected_review_hash(self.fixture_root / "release.json", desired, archive_sha256)
        # A change before desired-bundle construction must not redefine the verified archive's expected bytes.
        desired["plugin_sha256"] = self.reconcile.physical_tree_hash(plugin, excluded_relatives={"source-manifest.json"})
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "verified_review_content_mismatch"):
            self.reconcile._expected_review_hash(self.fixture_root / "release.json", desired, archive_sha256)
        shutil.copyfile(ROOT / "plugins" / "agent-memory-sidecar" / "skills" / "engineering-contract-review" / "SKILL.md",
                        plugin / "skills" / "engineering-contract-review" / "SKILL.md")
        desired["plugin_sha256"] = self.reconcile.physical_tree_hash(plugin, excluded_relatives={"source-manifest.json"})
        with archive_path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "release_resolution_asset_mismatch:portable"):
            self.reconcile._expected_review_hash(self.fixture_root / "release.json", desired, archive_sha256)

    def test_consumer_scope_requires_native_catalog_and_each_enabled_capability(self):
        for response in ([], [{"cwd": str(self.fixture_root / "project"), "skills": [], "errors": []}],
                         [{"cwd": str(self.fixture_root / "project"), "skills": [], "errors": [{"message": "unreadable"}]}]):
            with self.subTest(response=response), mock.patch.object(self.reconcile, "native_skill_catalog", return_value=response):
                self.assertEqual("bounded", self.scope()["status"])
        self.native_entries[0]["enabled"] = False
        self.assertEqual("bounded", self.scope()["status"])
        with mock.patch.object(self.reconcile, "native_skill_catalog", side_effect=self.reconcile.BootstrapError("unavailable")):
            self.assertEqual("bounded", self.scope()["status"])

    def test_consumer_scope_preserves_incomplete_or_remote_inventory(self):
        project = self.fixture_root / "project"
        project.mkdir()
        inventory = self.desktop_inventory(("Project", project), status="bounded")
        self.assertEqual("bounded", self.scope(inventory=inventory)["status"])
        inventory["projects"].append({"display_name": "Remote", "path": None, "is_git_repository": True})
        scope = self.scope(inventory=inventory)
        self.assertEqual("bounded", scope["status"])
        self.assertEqual(1, scope["scanned_project_count"])

    def test_consumer_scope_bounds_alias_and_oversized_enabled_tree(self):
        root = Path(self.native_entries[0]["path"]).parent
        alias = self.fixture_root / "alias"
        try: alias.symlink_to(root, target_is_directory=True)
        except OSError as exc: self.skipTest(str(exc))
        self.native_entries[0]["path"] = str(alias / "SKILL.md")
        self.assertEqual("bounded", self.scope()["status"])
        self.native_entries[0]["path"] = str(root / "SKILL.md")
        with mock.patch.object(self.reconcile, "CONSUMER_SKILL_MAX_BYTES", 1):
            self.assertEqual("bounded", self.scope()["status"])

    def test_pack_validator_rejects_forged_exact_duplicates_or_missing_entry(self):
        import copy
        scope = self.scope()
        duplicate = copy.deepcopy(scope)
        duplicate["projects"][0]["skills"].append(dict(duplicate["projects"][0]["skills"][0]))
        duplicate["matching_skill_count"] += 1
        missing = copy.deepcopy(scope)
        missing["projects"][0]["skills"].pop()
        missing["matching_skill_count"] -= 1
        wrong_scope = copy.deepcopy(scope)
        wrong_scope["projects"][0]["skills"][-1]["scope"] = "repo"
        omitted = {**scope, "projects": [], "matching_skill_count": 0}
        with self.assertRaisesRegex(self.reconcile.BootstrapError, "every project"):
            self.reconcile.validate_consumer_scope(omitted)
        for forged in (duplicate, missing, wrong_scope):
            with self.assertRaisesRegex(self.reconcile.BootstrapError, "unique and exact|each enabled capability|managed review entry"):
                self.reconcile.validate_consumer_scope(forged)

    def test_native_catalog_deadline_covers_blocked_request_write(self):
        server = self.fixture_root / "stalled_server.py"
        server.write_text(
            "import sys, json, time\n"
            "json.loads(sys.stdin.readline())\n"
            "print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
            "time.sleep(60)\n",
        )
        # Official npm launchers on Windows retain a parent and inherit child pipes.
        launcher = self.fixture_root / "launcher.py"
        launcher.write_text(
            "import subprocess, sys\n"
            "raise SystemExit(subprocess.call([sys.executable, sys.argv[1]]))\n",
        )
        real_popen = subprocess.Popen
        def stalled_process(arguments, **kwargs):
            if arguments[0] == "taskkill":
                return real_popen(arguments, **kwargs)
            return real_popen([sys.executable, str(launcher), str(server)], **kwargs)
        started = time.monotonic()
        self.native_patch.stop()
        with mock.patch.object(self.reconcile.shutil, "which", return_value=sys.executable), \
             mock.patch.object(self.reconcile.subprocess, "Popen", side_effect=stalled_process), \
             mock.patch.object(self.reconcile, "NATIVE_SKILLS_TIMEOUT_SECONDS", 1):
            with self.assertRaises((OSError, self.reconcile.BootstrapError)):
                self.reconcile.native_skill_catalog(self.fixture_root / "codex", [self.fixture_root / ("x" * 500)] * 500)
        self.assertLess(time.monotonic() - started, 5)

    def test_development_sources_are_outside_automatic_discovery(self):
        for name in self.reconcile.CONSUMER_SKILLS:
            source = ROOT / "plugins" / "agent-memory-sidecar" / "skills" if name == "engineering-contract-review" else ROOT / "skills"
            self.assertTrue((source / name / "SKILL.md").is_file())
            # Native discovery requires SKILL.md, not a directory left by historical
            # bytecode/cache state. Preserve unrelated local state; reject any actual
            # discoverable development entry, including a nested one.
            self.assertFalse(any((ROOT / ".agents" / "skills" / name).rglob("SKILL.md")))

    @unittest.skipUnless(shutil.which("codex"), "native Codex CLI unavailable")
    def test_real_native_catalog_disabled_source_and_single_installed_entry(self):
        self.native_patch.stop()
        project = self.fixture_root / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        codex_home = self.fixture_root / "codex"
        source = self.extra_candidate(stale=False)
        real_catalog = self.reconcile.native_skill_catalog
        def catalog_with_managed_review(home, roots):
            result = real_catalog(home, roots)
            for entry in result:
                entry["skills"].append(self.native_entries[-1])
            return result
        # Bootstrap discovery and enablement use the real native server; the managed Plugin entry is a fixture.
        with mock.patch.object(self.reconcile, "native_skill_catalog", side_effect=catalog_with_managed_review):
            self.assertEqual("drifted", self.scope()["status"])
            (codex_home / "config.toml").write_text(
                "[[skills.config]]\npath = " + json.dumps(str(source / "SKILL.md")) + "\nenabled = false\n",
            )
            self.assertEqual("exact", self.scope()["status"])
            source.rename(project / "development-source")
            scope = self.scope()
            self.assertEqual("exact", scope["status"])
            self.assertEqual(3, scope["matching_skill_count"])

    def test_pack_revokes_ready_for_drifted_or_bounded_consumer_scope(self) -> None:
        exact_scope = {
            "status": "exact", "inventory_status": "complete",
            "desktop_project_count": 0, "scanned_project_count": 0,
            "matching_skill_count": 0, "projects": [], "limitations": [],
        }
        source_sync = {
            "sidecar": {"status": "unchanged", "ref": "v0.3.10", "commit": "a" * 40},
            "canonical_owner": {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"},
        }
        common = {
            "desired": self.desired_bundle(),
            "observed_distribution": self.exact_distribution(),
            "desired_source_sha256": "e" * 64,
            "source_sync": source_sync,
            "host_materialization": self.exact_host(),
            "requires_reload": False,
            "consumer_verified": True,
            "generated_at": "2026-09-01T12:00:00+08:00",
        }
        ready = self.reconcile.build_deployment_pack(**common, consumer_scope=exact_scope)
        self.assertEqual("ready", ready["status"])
        rendered_ready = self.reconcile.render_pack(ready)
        self.assertIn("入口检查 `verified`", rendered_ready)
        self.assertIn("仅表示安装与项目范围检查通过", rendered_ready)
        self.assertIn("Scout 实际运行 | 本次未运行", rendered_ready)
        self.assertIn("不判断其他运行的验收结果", rendered_ready)
        self.assertIn("模型自动加载、自然采用和实际体验仍未证明", rendered_ready)
        self.assertNotIn("新任务中发送", rendered_ready)
        result = subprocess.run(
            [sys.executable, "-B", str(MANAGED_SOURCES), "render-pack"],
            input=json.dumps(ready), capture_output=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(rendered_ready, result.stdout)

        drifted_scope = {
            **exact_scope,
            "status": "drifted", "desktop_project_count": 1, "scanned_project_count": 1,
            "matching_skill_count": 3,
            "projects": [{
                "project_ref": "desktop-project-example", "display_name": "<Project>|Name", "status": "drifted",
                "skills": [{
                    "name": "agent-memory-workstation-bootstrap", "version": "1.9.0",
                    "scope": "repo", "enabled": True, "content_sha256": "9" * 64, "relation": "drifted",
                }, {
                    "name": "global-owner-scout", "version": "5.19.4", "scope": "user", "enabled": True,
                    "content_sha256": self.native_hashes["global-owner-scout"], "relation": "exact",
                }, {
                    "name": "agent-memory-sidecar:engineering-contract-review", "version": "1.5.1", "scope": "user", "enabled": True,
                    "content_sha256": self.review_hash, "relation": "exact",
                }],
            }],
        }
        drifted = self.reconcile.build_deployment_pack(**common, consumer_scope=drifted_scope)
        self.assertEqual("consumer_scope_drift", drifted["status"])
        self.assertEqual("ambiguous", drifted["consumer_activation"]["interactive_entry"])
        rendered = self.reconcile.render_pack(drifted)
        self.assertIn("&lt;Project&gt;\\|Name", rendered)
        self.assertNotIn("<Project>", rendered)
        self.assertIn("入口检查 `ambiguous`", rendered)
        self.assertIn("Scout 实际运行 | 本次未运行", rendered)

        bounded_scope = {
            **exact_scope,
            "status": "bounded", "inventory_status": "bounded",
            "limitations": ["Desktop 项目清单不完整；未枚举的消费者范围保持未知。"],
        }
        bounded = self.reconcile.build_deployment_pack(**common, consumer_scope=bounded_scope)
        self.assertEqual("consumer_scope_bounded", bounded["status"])
        rendered = self.reconcile.render_pack(bounded)
        self.assertIn("只读消费者检查", rendered)
        self.assertIn("无需重复部署", rendered)
        self.assertNotIn("同一句部署入口", rendered)
        self.assertEqual("unproven", bounded["consumer_activation"]["interactive_entry"])

    def test_requested_consumer_check_reads_scope_without_session_gate_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            protected = project / "AGENTS.md"
            protected.write_text("Keep the project rules.\n", encoding="utf-8")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps(self.desktop_inventory(("Example", project))), encoding="utf-8")
            context = {
                "desired": self.desired_bundle(), "observed": self.exact_distribution(),
                "source_sha256": "e" * 64, "archive_sha256": "f" * 64, "source_plan": self.source_plan(),
                "observed_host": self.exact_host(),
            }
            # The host observer is the boundary substitute; scope observation, CLI dispatch,
            # rendering and project I/O are real. No session-loading assertion is supplied.
            with mock.patch.object(self.reconcile, "_workstation_reconcile_context", return_value=({"status": "noop"}, context)), \
                 mock.patch.object(self.reconcile, "_expected_review_hash", return_value=self.review_hash):
                output = io.StringIO()
                argv = [
                    str(MANAGED_SOURCES), "workstation-reconcile", "--verify-consumer", "--codex-home", str(self.fixture_root / "codex"),
                    "--source-manifest", str(root / "source.json"),
                    "--release-manifest", str(root / "release.json"),
                    "--desktop-project-inventory", str(inventory),
                ]
                with contextlib.redirect_stdout(output), mock.patch.object(sys, "argv", argv):
                    code = self.reconcile.main()
            self.assertEqual(0, code)
            pack = json.loads(output.getvalue())
            self.assertEqual("ready", pack["status"])
            self.assertEqual(1, pack["consumer_scope"]["scanned_project_count"])
            self.assertIn("模型自动加载、自然采用和实际体验仍未证明", self.reconcile.render_pack(pack))
            self.assertEqual("Keep the project rules.\n", protected.read_text(encoding="utf-8"))
            self.assertFalse((root / "codex").exists())

            with mock.patch.object(self.reconcile, "_workstation_reconcile_context", return_value=({"status": "ready"}, context)):
                with self.assertRaisesRegex(self.reconcile.BootstrapError, "consumer_verification_requires_exact_host"):
                    self.reconcile.verify_workstation_consumer(root / "codex", root / "source.json", root / "release.json", inventory)

    def test_real_regression_detects_stale_marketplace_and_plugin(self) -> None:
        observed = self.exact_distribution()
        observed["marketplace"] = {
            **observed["marketplace"],
            "ref": "v0.3.5",
            "commit": "f" * 40,
        }
        observed["plugin"] = {
            **observed["plugin"],
            "ref": "v0.3.5",
            "version": "1.3.0",
            "content_sha256": "1" * 64,
        }

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            observed,
            desired_source_sha256="e" * 64,
            source_plan=self.source_plan(),
            host_materialization=self.exact_host(),
        )

        self.assertEqual("ready", plan["status"])
        self.assertEqual(
            ["marketplace:replace", "plugin:replace"],
            plan["changes"],
        )
        self.assertTrue(plan["requires_reload"])

    def test_disabled_plugin_fails_closed_instead_of_claiming_ready(self) -> None:
        observed = self.exact_distribution()
        observed["plugin"] = {**observed["plugin"], "enabled": False}

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            observed,
            desired_source_sha256="e" * 64,
            source_plan=self.source_plan(),
            host_materialization=self.exact_host(),
        )

        self.assertEqual("distribution_reconcile_blocked", plan["status"])
        self.assertEqual(["plugin:disabled"], plan["blockers"])
        self.assertFalse(plan["confirmation_required"])

    def test_distribution_blocker_defers_source_confirmation(self) -> None:
        observed = self.exact_distribution()
        observed["plugin"] = {**observed["plugin"], "enabled": False}
        source_plan = self.source_plan()
        source_plan["status"] = "ready"
        source_plan["current"]["sidecar"]["remote_sha256"] = "9" * 64
        source_plan["changes"] = ["sidecar:replace"]
        source_plan["plan_hash"] = self.reconcile.object_hash(source_plan, "plan_hash")

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            observed,
            desired_source_sha256="e" * 64,
            source_plan=source_plan,
            host_materialization=self.exact_host(),
        )

        self.assertEqual("distribution_reconcile_blocked", plan["status"])
        self.assertFalse(plan["confirmation_required"])

    def test_same_source_version_update_needs_no_extra_confirmation(self) -> None:
        source_plan = self.source_plan()
        source_plan["status"] = "ready"
        source_plan["current"]["sidecar"]["commit"] = "f" * 40
        source_plan["changes"] = ["sidecar:replace"]
        source_plan["plan_hash"] = self.reconcile.object_hash(source_plan, "plan_hash")

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_plan=source_plan,
            host_materialization=self.exact_host(),
        )

        self.assertIn("source:sidecar:replace", plan["changes"])
        self.assertFalse(plan["confirmation_required"])

    def test_source_remote_replacement_still_requires_confirmation(self) -> None:
        source_plan = self.source_plan()
        source_plan["status"] = "ready"
        source_plan["current"]["sidecar"]["remote_sha256"] = "9" * 64
        source_plan["changes"] = ["sidecar:replace"]
        source_plan["plan_hash"] = self.reconcile.object_hash(source_plan, "plan_hash")

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_plan=source_plan,
            host_materialization=self.exact_host(),
        )

        self.assertTrue(plan["confirmation_required"])

    def test_stale_or_missing_scout_prevents_noop_and_ready(self) -> None:
        host = self.exact_host()
        host["scout_skill"] = {
            "status": "unavailable", "version": "unavailable",
            "content_sha256": "unavailable",
        }

        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_plan=self.source_plan(),
            host_materialization=host,
        )

        self.assertEqual("ready", plan["status"])
        self.assertEqual(["host:materialize"], plan["changes"])
        self.assertTrue(plan["requires_reload"])

    def test_deployment_pack_is_built_from_exact_readback(self) -> None:
        materialization = {
            "core": {
                "status": "verified",
                "version": "0.3.10",
                "source_commit": "a" * 40,
                "artifact_sha256": "2" * 64,
            },
            "global_binding": "verified",
            "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged",
                "version": "2.5.7",
                "content_sha256": self.native_hashes["agent-memory-workstation-bootstrap"],
            },
            "scout_skill": {
                "status": "unchanged",
                "version": "5.19.4",
                "content_sha256": self.native_hashes["global-owner-scout"],
            },
        }
        source_sync = {
            "sidecar": {"status": "unchanged", "ref": "v0.3.10", "commit": "a" * 40},
            "canonical_owner": {"status": "unchanged", "ref": "preserved", "commit": "3" * 40},
        }

        pack = self.reconcile.build_deployment_pack(
            desired=self.desired_bundle(),
            observed_distribution=self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_sync=source_sync,
            host_materialization=materialization,
            requires_reload=True,
            consumer_verified=False,
            generated_at="2026-08-21T12:00:00+08:00",
        )

        self.assertEqual("reload_required", pack["status"])
        self.assertEqual("required", pack["consumer_activation"]["desktop_reload"])
        self.assertEqual("available_next_task", pack["consumer_activation"]["interactive_entry"])
        self.reconcile.validate_pack(pack)
        rendered = self.reconcile.render_pack(pack)
        self.assertIn("本次安装交付到此完成", rendered)
        self.assertIn("同一主机、同一聊天完成只读消费者检查", rendered)
        self.assertNotIn("再次发送", rendered)
        self.assertNotIn("完成采用验收", rendered)

    def test_installation_pack_preserves_unverified_consumer_state(self) -> None:
        materialization = {
            "core": {
                "status": "verified", "version": "0.3.10", "source_commit": "a" * 40,
                "artifact_sha256": "2" * 64,
            },
            "global_binding": "verified",
            "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged", "version": "2.5.7", "content_sha256": self.native_hashes["agent-memory-workstation-bootstrap"],
            },
            "scout_skill": {
                "status": "unchanged", "version": "5.19.4", "content_sha256": self.native_hashes["global-owner-scout"],
            },
        }
        source_sync = {
            "sidecar": {"status": "unchanged", "ref": "v0.3.10", "commit": "a" * 40},
            "canonical_owner": {"status": "unchanged", "ref": "preserved", "commit": "3" * 40},
        }

        pack = self.reconcile.build_deployment_pack(
            desired=self.desired_bundle(),
            observed_distribution=self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_sync=source_sync,
            host_materialization=materialization,
            requires_reload=False,
            consumer_verified=False,
            generated_at="2026-08-21T12:00:00+08:00",
        )

        self.assertEqual("reload_required", pack["status"])
        self.assertEqual("required", pack["consumer_activation"]["desktop_reload"])
        self.assertEqual("available_next_task", pack["consumer_activation"]["interactive_entry"])

    def test_blocked_pack_never_sends_user_to_refresh_or_scout(self) -> None:
        distribution = self.exact_distribution()
        distribution["plugin"] = {
            **distribution["plugin"], "version": "1.3.0", "content_sha256": "1" * 64,
        }
        source_sync = {
            "sidecar": {"status": "unchanged", "ref": "v0.3.10", "commit": "a" * 40},
            "canonical_owner": {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"},
        }

        pack = self.reconcile.build_deployment_pack(
            desired=self.desired_bundle(),
            observed_distribution=distribution,
            desired_source_sha256="e" * 64,
            source_sync=source_sync,
            host_materialization=self.exact_host(),
            requires_reload=False,
            consumer_verified=False,
            generated_at="2026-08-21T12:00:00+08:00",
        )
        rendered = self.reconcile.render_pack(pack)

        self.assertEqual("distribution_reconcile_blocked", pack["status"])
        self.assertEqual("not_required", pack["consumer_activation"]["desktop_reload"])
        self.assertEqual("blocked", pack["consumer_activation"]["interactive_entry"])
        self.assertNotIn("$global-owner-scout", rendered)
        self.assertNotIn("刷新一次 Codex Desktop", rendered)

    def test_desired_bundle_comes_from_verified_release_and_portable_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            portable = output / "portable"
            plugin = portable / "plugins" / "agent-memory-sidecar"
            bootstrap = portable / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
            scout = portable / ".agents" / "skills" / "global-owner-scout"
            for root, name in ((plugin, "plugin"), (bootstrap, "bootstrap"), (scout, "scout")):
                root.mkdir(parents=True)
                (root / f"{name}.txt").write_text(name, encoding="utf-8")
            plugin_manifest = plugin / ".codex-plugin" / "plugin.json"
            plugin_manifest.parent.mkdir()
            plugin_manifest.write_text(json.dumps({"version": "1.5.1"}), encoding="utf-8")
            (bootstrap / "SKILL.md").write_text(
                "# Bootstrap\n\n- Skill version: `2.5.7`\n", encoding="utf-8",
            )
            (scout / "SKILL.md").write_text(
                "# Scout\n\n- Skill version: `5.19.4`\n", encoding="utf-8",
            )
            source_manifest = {
                "contract_version": "agent_memory_source_manifest_v1",
                "distribution": "release",
                "sidecar": {
                    "remote": "https://github.com/lly-personal/agent-memory-sidecar.git",
                    "ref": "v0.3.10",
                    "commit": "a" * 40,
                },
                "canonical_owner": None,
            }
            release_manifest = {
                "contract_version": "agent_memory_public_release_manifest_v1",
                "status": "public_artifact_verified",
                "source": {
                    "repository": "https://github.com/lly-personal/agent-memory-sidecar",
                    "ref": "v0.3.10",
                    "commit": "a" * 40,
                    "authority_epoch": "public_active",
                    "engineering_source_commit": "a" * 40,
                    "initial_public_release": None,
                    "authority_activated_at": "2026-08-21T00:00:00Z",
                },
                "versions": {
                    "core": "0.3.10", "plugin": "1.5.1",
                    "bootstrap": "2.5.7", "scout": "5.19.4",
                },
                "artifacts": [],
                "verification": {},
            }
            source_path = output / "source-manifest.json"
            release_path = output / "release-manifest.json"
            source_path.write_text(json.dumps(source_manifest), encoding="utf-8")
            release_path.write_text(json.dumps(release_manifest), encoding="utf-8")
            portable_archive = output / "agent-memory-portable-0.3.10.zip"
            portable_archive.write_bytes(b"verified portable fixture")
            assets = {}
            for path in (source_path, release_path, portable_archive):
                data = path.read_bytes()
                assets[path.name] = {
                    "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                }
            (output / "resolution.json").write_text(json.dumps({
                "contract_version": "agent_memory_release_resolution_v1",
                "status": "verified",
                "repository": "lly-personal/agent-memory-sidecar",
                "tag": "v0.3.10",
                "commit": "a" * 40,
                "portable_root": "portable",
                "assets": assets,
            }), encoding="utf-8")

            desired, sidecar, source_hash, archive_hash = self.reconcile.load_desired_bundle(
                source_path, release_path,
            )

            self.assertEqual("v0.3.10", desired["release_ref"])
            self.assertEqual("1.5.1", desired["plugin_version"])
            self.assertEqual("2.5.7", desired["bootstrap_version"])
            self.assertEqual("a" * 40, sidecar.expected_commit)
            self.assertRegex(source_hash, r"^[0-9a-f]{64}$")
            self.assertEqual(hashlib.sha256(portable_archive.read_bytes()).hexdigest(), archive_hash)
            self.assertRegex(desired["plugin_sha256"], r"^[0-9a-f]{64}$")

            release_path.write_text(
                json.dumps({**release_manifest, "verification": {"tampered": True}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                self.reconcile.BootstrapError, "release_resolution_asset_mismatch",
            ):
                self.reconcile.load_desired_bundle(source_path, release_path)

    def test_observer_reads_codex_json_marketplace_with_or_without_legacy_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            marketplace_root = codex_home / ".tmp" / "marketplaces" / "agent-memory"
            marketplace_root.mkdir(parents=True)
            self.reconcile.run_git(["init", "-q", "-b", "main"], cwd=marketplace_root)
            self.reconcile.run_git(["config", "user.name", "Reconcile Test"], cwd=marketplace_root)
            self.reconcile.run_git(["config", "user.email", "reconcile@example.invalid"], cwd=marketplace_root)
            self.reconcile.run_git(
                ["remote", "add", "origin", "https://github.com/example/agent-memory-sidecar.git"],
                cwd=marketplace_root,
            )
            marketplace = {
                "name": "agent-memory",
                "interface": {"displayName": "Agent Memory"},
                "plugins": [{
                    "name": "agent-memory-sidecar",
                    "source": {
                        "source": "git-subdir",
                        "url": "https://github.com/example/agent-memory-sidecar.git",
                        "path": "./plugins/agent-memory-sidecar",
                        "ref": "v0.3.10",
                    },
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": "Productivity",
                }],
            }
            marketplace_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
            marketplace_path.parent.mkdir(parents=True)
            marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")
            self.reconcile.run_git(["add", ".agents/plugins/marketplace.json"], cwd=marketplace_root)
            self.reconcile.run_git(["commit", "-q", "-m", "marketplace"], cwd=marketplace_root)
            commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=marketplace_root)
            (marketplace_root / ".codex-marketplace-install.json").write_text(
                json.dumps({
                    "source_type": "git",
                    "source": "https://github.com/example/agent-memory-sidecar.git",
                    "ref_name": "v0.3.10",
                    "sparse_paths": [],
                    "revision": commit,
                }),
                encoding="utf-8",
            )
            plugin_root = (
                codex_home / "plugins" / "cache" / "agent-memory"
                / "agent-memory-sidecar" / "1.5.1"
            )
            manifest = plugin_root / ".codex-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"version": "1.5.1"}), encoding="utf-8")
            (plugin_root / "payload.txt").write_text("plugin", encoding="utf-8")

            def codex_json(arguments, *, codex_home):
                if arguments[1:3] == ["marketplace", "list"]:
                    return {
                        "marketplaces": [{
                            "name": "agent-memory",
                            "root": str(marketplace_root),
                            "marketplaceSource": {
                                "sourceType": "git",
                                "source": "https://github.com/example/agent-memory-sidecar.git",
                            },
                        }]
                    }
                return {
                    "installed": [{
                        "pluginId": "agent-memory-sidecar@agent-memory",
                        "version": "1.5.1",
                        "installed": True,
                        "enabled": True,
                        "source": {
                            "source": "git-subdir",
                            "url": "https://github.com/example/agent-memory-sidecar.git",
                            "path": "plugins/agent-memory-sidecar",
                            "ref": "v0.3.10",
                        },
                    }]
                }

            with mock.patch.object(self.reconcile, "run_codex_json", side_effect=codex_json):
                observed = self.reconcile.observe_distribution(codex_home)

            self.assertEqual("present", observed["marketplace"]["status"])
            self.assertEqual(commit, observed["marketplace"]["commit"])
            self.assertEqual("1.5.1", observed["plugin"]["version"])
            self.assertTrue(observed["plugin"]["enabled"])

            metadata_path = marketplace_root / ".codex-marketplace-install.json"
            invalid_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            invalid_metadata["ref_name"] = "v0.3.7"
            metadata_path.write_text(json.dumps(invalid_metadata), encoding="utf-8")
            with mock.patch.object(self.reconcile, "run_codex_json", side_effect=codex_json):
                observed_with_invalid_metadata = self.reconcile.observe_distribution(codex_home)
            self.assertEqual("unavailable", observed_with_invalid_metadata["marketplace"]["status"])

            metadata_path.unlink()
            with mock.patch.object(self.reconcile, "run_codex_json", side_effect=codex_json):
                observed_without_metadata = self.reconcile.observe_distribution(codex_home)

            self.assertEqual("present", observed_without_metadata["marketplace"]["status"])
            self.assertEqual("v0.3.10", observed_without_metadata["marketplace"]["ref"])
            self.assertEqual(commit, observed_without_metadata["marketplace"]["commit"])

    def test_host_observer_reads_live_doctor_and_physical_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = self.reconcile.create_remote(root, "sidecar")
            work = root / "sidecar-work"
            init = work / "src" / "agent_memory_sidecar" / "__init__.py"
            init.parent.mkdir(parents=True)
            init.write_text('__version__ = "0.3.10"\n', encoding="utf-8")
            self.reconcile.run_git(["add", "src/agent_memory_sidecar/__init__.py"], cwd=work)
            self.reconcile.run_git(["commit", "-q", "-m", "core"], cwd=work)
            self.reconcile.run_git(["remote", "add", "origin", str(remote)], cwd=work)
            self.reconcile.run_git(["push", "-q", "origin", "main"], cwd=work)
            commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=work)
            spec = (self.reconcile.SourceSpec("sidecar", str(remote), "main", commit),)
            codex_home = root / "codex-home"
            self.reconcile.sync_sources(codex_home, spec)
            for name, version in (
                ("agent-memory-workstation-bootstrap", "2.5.7"),
                ("global-owner-scout", "5.19.4"),
            ):
                skill = codex_home / "skills" / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"# Skill\n\n- Skill version: `{version}`\n", encoding="utf-8",
                )
            doctor = {
                "contract_version": "agent_memory_result_v1",
                "operation": "doctor",
                "status": "ok",
                "error": None,
                "data": {
                    "status": "ok",
                    "runtime": {
                        "source_commit": commit,
                        "artifact_sha256": "sha256:" + "2" * 64,
                    },
                    "global": None,
                },
            }

            with mock.patch.object(self.reconcile, "run_json", return_value=doctor):
                observed = self.reconcile.observe_host_materialization(
                    codex_home, spec, owner_expected=False,
                )

            self.assertEqual("verified", observed["core"]["status"])
            self.assertEqual(commit, observed["core"]["source_commit"])
            self.assertEqual("verified", observed["doctor"])
            self.assertEqual("2.5.7", observed["bootstrap_skill"]["version"])
            self.assertRegex(observed["scout_skill"]["content_sha256"], r"^[0-9a-f]{64}$")

    def test_distribution_participant_rolls_back_with_source_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_remote = self.reconcile.create_remote(root, "old-sidecar")
            new_remote = self.reconcile.create_remote(root, "new-sidecar")
            old_commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=root / "old-sidecar-work")
            new_commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=root / "new-sidecar-work")
            codex_home = root / "codex-home"
            old_spec = (self.reconcile.SourceSpec("sidecar", str(old_remote), "main", old_commit),)
            self.reconcile.sync_sources(codex_home, old_spec)
            new_spec = (self.reconcile.SourceSpec("sidecar", str(new_remote), "main", new_commit),)
            plan = self.reconcile.plan_source_cutover(codex_home, new_spec)
            distribution = {"value": "old"}

            def apply_distribution() -> None:
                distribution["value"] = "new"

            def rollback_distribution() -> None:
                distribution["value"] = "old"

            with mock.patch.object(
                self.reconcile,
                "materialize_host",
                side_effect=self.reconcile.BootstrapError("doctor_failed"),
            ):
                with self.assertRaisesRegex(self.reconcile.BootstrapError, "doctor_failed"):
                    self.reconcile.apply_source_cutover(
                        codex_home,
                        new_spec,
                        plan_hash=plan["plan_hash"],
                        external_apply=apply_distribution,
                        external_rollback=rollback_distribution,
                    )

            self.assertEqual("old", distribution["value"])
            source_root = codex_home / "agent-memory" / "sources" / "sidecar"
            self.assertEqual(old_commit, self.reconcile.inspect_checkout(source_root, old_spec[0]))

    def test_postcommit_cleanup_failure_never_reverses_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_remote = self.reconcile.create_remote(root, "old-sidecar")
            new_remote = self.reconcile.create_remote(root, "new-sidecar")
            old_commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=root / "old-sidecar-work")
            new_commit = self.reconcile.run_git(["rev-parse", "HEAD"], cwd=root / "new-sidecar-work")
            codex_home = root / "codex-home"
            old_spec = (self.reconcile.SourceSpec("sidecar", str(old_remote), "main", old_commit),)
            self.reconcile.sync_sources(codex_home, old_spec)
            new_spec = (self.reconcile.SourceSpec("sidecar", str(new_remote), "main", new_commit),)
            plan = self.reconcile.plan_source_cutover(codex_home, new_spec)
            distribution = {"value": "old"}
            host = self.exact_host()
            host["core"] = {**host["core"], "source_commit": new_commit}

            with (
                mock.patch.object(self.reconcile, "materialize_host", return_value=host),
                mock.patch.object(
                    self.reconcile,
                    "_discard_skill_snapshots",
                    side_effect=self.reconcile.BootstrapError("cleanup_failed"),
                ),
                self.assertRaisesRegex(
                    self.reconcile.BootstrapError,
                    "source_cutover_postcommit_cleanup_failed",
                ),
            ):
                self.reconcile.apply_source_cutover(
                    codex_home,
                    new_spec,
                    plan_hash=plan["plan_hash"],
                    external_apply=lambda: distribution.update(value="new"),
                    external_rollback=lambda: distribution.update(value="old"),
                )

            self.assertEqual("new", distribution["value"])
            source_root = codex_home / "agent-memory" / "sources" / "sidecar"
            self.assertEqual(new_commit, self.reconcile.inspect_checkout(source_root, new_spec[0]))
            self.assertTrue((codex_home / "agent-memory" / "source-cutover-receipt.json").is_file())

    def test_production_style_valid_pack_fixture_is_removed(self) -> None:
        self.assertFalse(hasattr(self.reconcile, "valid_pack"))

    def test_consumer_verification_uses_live_host_not_historical_receipt(self) -> None:
        source_plan = self.source_plan()
        context = {
            "desired": self.desired_bundle(),
            "observed": self.exact_distribution(),
            "source_sha256": "e" * 64,
            "archive_sha256": "f" * 64,
            "source_plan": source_plan,
            "observed_host": self.exact_host(),
        }
        plan = self.reconcile.build_workstation_reconcile_plan(
            context["desired"],
            context["observed"],
            desired_source_sha256=context["source_sha256"],
            source_plan=source_plan,
            host_materialization=context["observed_host"],
        )
        self.assertEqual("noop", plan["status"])

        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "inventory.json"
            inventory.write_text(
                json.dumps(self.desktop_inventory()), encoding="utf-8",
            )
            with mock.patch.object(
                self.reconcile, "_workstation_reconcile_context", return_value=(plan, context),
            ), mock.patch.object(self.reconcile, "_expected_review_hash", return_value=self.review_hash):
                pack = self.reconcile.verify_workstation_consumer(
                    Path("unused"), Path("source.json"), Path("release.json"), inventory,
                )

        self.assertEqual("ready", pack["status"])
        self.assertEqual("verified", pack["consumer_activation"]["interactive_entry"])
        self.assertEqual("exact", pack["consumer_scope"]["status"])

    def test_apply_pack_uses_post_materialization_live_host_readback(self) -> None:
        stale_host = self.exact_host()
        stale_host["scout_skill"] = {
            "status": "unavailable", "version": "unavailable",
            "content_sha256": "unavailable",
        }
        source_plan = self.source_plan()
        plan = self.reconcile.build_workstation_reconcile_plan(
            self.desired_bundle(),
            self.exact_distribution(),
            desired_source_sha256="e" * 64,
            source_plan=source_plan,
            host_materialization=stale_host,
        )
        context = {
            "desired": self.desired_bundle(),
            "observed": self.exact_distribution(),
            "source_sha256": "e" * 64,
            "source_plan": source_plan,
            "observed_host": stale_host,
            "private_distribution": {},
            "sidecar": self.reconcile.SourceSpec("sidecar", "https://example.invalid/repo.git", "v0.3.10", "a" * 40),
            "specs": (),
        }
        source_receipt = {
            "sources": {
                "sidecar": {"status": "unchanged", "ref": "v0.3.10", "commit": "a" * 40},
                "canonical_owner": {"status": "unavailable", "ref": "unavailable", "commit": "unavailable"},
            },
            "materialization": stale_host,
        }

        def source_apply(*args, precommit_verify, **kwargs):
            precommit_verify(source_receipt)
            return source_receipt

        with (
            mock.patch.object(self.reconcile, "_workstation_reconcile_context", return_value=(plan, context)),
            mock.patch.object(self.reconcile, "apply_source_cutover", side_effect=source_apply),
            mock.patch.object(self.reconcile, "observe_distribution", return_value=self.exact_distribution()),
            mock.patch.object(self.reconcile, "observe_host_materialization", return_value=self.exact_host()),
        ):
            receipt = self.reconcile.apply_workstation_reconcile(
                Path("unused"), Path("source.json"), Path("release.json"),
                plan_hash=plan["plan_hash"],
            )

        self.assertEqual("reload_required", receipt["deployment_pack"]["status"])
        self.assertEqual("agent_memory_workstation_reconcile_receipt_v3", receipt["contract_version"])
        self.assertEqual("unchanged", receipt["deployment_pack"]["host_materialization"]["scout_skill"]["status"])
        self.assertEqual(self.exact_host(), source_receipt["materialization"])

    def test_published_v1_anchor_source_cutover_command_routes_to_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            resolved = Path(temporary)
            source = resolved / "source-manifest.json"
            release = resolved / "release-manifest.json"
            source.write_text("{}", encoding="utf-8")
            release.write_text("{}", encoding="utf-8")
            (resolved / "resolution.json").write_text("{}", encoding="utf-8")
            (resolved / "portable").mkdir()
            expected = {"contract_version": "agent_memory_workstation_reconcile_plan_v2", "status": "noop"}
            output = io.StringIO()
            argv = [
                "managed_sources.py", "source-cutover",
                "--codex-home", str(resolved / "codex-home"),
                "--source-manifest", str(source),
                "--dry-run",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    self.reconcile, "inspect_workstation_reconcile", return_value=expected,
                ) as inspect,
                contextlib.redirect_stdout(output),
            ):
                code = self.reconcile.main()

            self.assertEqual(0, code)
            inspect.assert_called_once_with(resolved / "codex-home", str(source), release.resolve())
            self.assertEqual(expected, json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
