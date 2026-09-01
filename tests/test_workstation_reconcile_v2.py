from __future__ import annotations

import importlib.util
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MANAGED_SOURCES = (
    ROOT
    / ".agents"
    / "skills"
    / "agent-memory-workstation-bootstrap"
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

    def desired_bundle(self) -> dict[str, object]:
        return {
            "release_ref": "v0.3.10",
            "source_commit": "a" * 40,
            "core_version": "0.3.10",
            "plugin_version": "1.5.1",
            "plugin_sha256": "b" * 64,
            "bootstrap_version": "2.2.0",
            "bootstrap_sha256": "c" * 64,
            "scout_version": "5.7.0",
            "scout_sha256": "d" * 64,
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
                "status": "unchanged", "version": "2.2.0", "content_sha256": "c" * 64,
            },
            "scout_skill": {
                "status": "unchanged", "version": "5.7.0", "content_sha256": "d" * 64,
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

    def test_consumer_scope_detects_stale_project_skill_without_mutation_or_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "active-project"
            skill = project / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("# Bootstrap\n\n- Skill version: `1.9.0`\n", encoding="utf-8")
            before = skill_file.read_bytes()

            scope = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Active Project", project)),
                desired=self.desired_bundle(),
            )

            self.assertEqual("drifted", scope["status"])
            self.assertEqual("drifted", scope["projects"][0]["skills"][0]["relation"])
            self.assertEqual(before, skill_file.read_bytes())
            self.assertNotIn(str(project), json.dumps(scope, ensure_ascii=False))

    def test_consumer_scope_requires_complete_inventory_and_exact_skill_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            bounded = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project), status="bounded"),
                desired=self.desired_bundle(),
            )
            self.assertEqual("bounded", bounded["status"])

            exact = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project)),
                desired=self.desired_bundle(),
            )
            self.assertEqual("exact", exact["status"])
            self.assertEqual(0, exact["matching_skill_count"])

    def test_consumer_scope_distinguishes_exact_bytes_from_same_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            skill = project / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("# Bootstrap\n\n- Skill version: `2.2.0`\n", encoding="utf-8")
            desired = self.desired_bundle()
            desired["bootstrap_sha256"] = self.reconcile.physical_tree_hash(skill)

            exact = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project)), desired=desired,
            )
            self.assertEqual("exact", exact["status"])

            skill_file.write_text("# Bootstrap\n\n- Skill version: `2.2.0`\n\nChanged.\n", encoding="utf-8")
            drifted = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project)), desired=desired,
            )
            self.assertEqual("drifted", drifted["status"])
            self.assertEqual("2.2.0", drifted["projects"][0]["skills"][0]["version"])

    def test_consumer_scope_fails_bounded_on_project_skill_parent_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            external = root / "external-agents"
            (external / "skills").mkdir(parents=True)
            try:
                (project / ".agents").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symbolic links unavailable: {exc}")

            scope = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project)), desired=self.desired_bundle(),
            )

            self.assertEqual("bounded", scope["status"])
            self.assertEqual("bounded", scope["projects"][0]["status"])
            self.assertEqual([], scope["projects"][0]["skills"])

    def test_consumer_scope_counts_remote_or_unavailable_project_as_bounded(self) -> None:
        inventory = {
            "contract_version": "agent_memory_desktop_project_inventory_v1",
            "inventory_status": "complete",
            "projects": [{
                "display_name": "Remote Project", "path": None, "is_git_repository": True,
            }],
        }

        scope = self.reconcile.observe_consumer_scope(inventory, desired=self.desired_bundle())

        self.assertEqual("bounded", scope["status"])
        self.assertEqual(1, scope["desktop_project_count"])
        self.assertEqual(0, scope["scanned_project_count"])
        self.assertEqual("Remote Project", scope["projects"][0]["display_name"])

    def test_consumer_scope_scans_from_primary_folder_to_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            primary = repository / "nested" / "primary"
            primary.mkdir(parents=True)
            self.reconcile.run_git(["init", "-q", "-b", "main"], cwd=repository)
            skill = repository / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "# Bootstrap\n\n- Skill version: `1.9.0`\n", encoding="utf-8",
            )
            inventory = {
                "contract_version": "agent_memory_desktop_project_inventory_v1",
                "inventory_status": "complete",
                "projects": [{
                    "display_name": "Nested Project", "path": str(primary), "is_git_repository": True,
                }],
            }

            scope = self.reconcile.observe_consumer_scope(inventory, desired=self.desired_bundle())

            self.assertEqual("drifted", scope["status"])
            self.assertEqual(2, scope["projects"][0]["skills"][0]["scope_level"])

    def test_consumer_scope_bounds_project_controlled_skill_tree_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            skill = project / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "# Bootstrap\n\n- Skill version: `2.2.0`\n", encoding="utf-8",
            )
            for index in range(self.reconcile.CONSUMER_SKILL_MAX_ENTRIES):
                (skill / f"extra-{index:03d}.txt").write_text("x", encoding="utf-8")

            scope = self.reconcile.observe_consumer_scope(
                self.desktop_inventory(("Project", project)), desired=self.desired_bundle(),
            )

            self.assertEqual("bounded", scope["status"])
            self.assertEqual("unreadable", scope["projects"][0]["skills"][0]["relation"])

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

        drifted_scope = {
            **exact_scope,
            "status": "drifted", "desktop_project_count": 1, "scanned_project_count": 1,
            "matching_skill_count": 1,
            "projects": [{
                "project_ref": "desktop-project-example", "display_name": "<Project>|Name", "status": "drifted",
                "skills": [{
                    "name": "agent-memory-workstation-bootstrap", "version": "1.9.0",
                    "scope_level": 0, "content_sha256": "9" * 64, "relation": "drifted",
                }],
            }],
        }
        drifted = self.reconcile.build_deployment_pack(**common, consumer_scope=drifted_scope)
        self.assertEqual("consumer_scope_drift", drifted["status"])
        self.assertEqual("ambiguous", drifted["consumer_activation"]["interactive_entry"])
        rendered = self.reconcile.render_pack(drifted)
        self.assertIn("&lt;Project&gt;\\|Name", rendered)
        self.assertNotIn("<Project>", rendered)

        bounded_scope = {
            **exact_scope,
            "status": "bounded", "inventory_status": "bounded",
            "limitations": ["Desktop 项目清单不完整；未枚举的消费者范围保持未知。"],
        }
        bounded = self.reconcile.build_deployment_pack(**common, consumer_scope=bounded_scope)
        self.assertEqual("consumer_scope_bounded", bounded["status"])
        self.assertEqual("unproven", bounded["consumer_activation"]["interactive_entry"])

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
                "version": "2.2.0",
                "content_sha256": "c" * 64,
            },
            "scout_skill": {
                "status": "unchanged",
                "version": "5.7.0",
                "content_sha256": "d" * 64,
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

    def test_unverified_consumer_always_requires_one_refresh(self) -> None:
        materialization = {
            "core": {
                "status": "verified", "version": "0.3.10", "source_commit": "a" * 40,
                "artifact_sha256": "2" * 64,
            },
            "global_binding": "verified",
            "doctor": "verified",
            "bootstrap_skill": {
                "status": "unchanged", "version": "2.2.0", "content_sha256": "c" * 64,
            },
            "scout_skill": {
                "status": "unchanged", "version": "5.7.0", "content_sha256": "d" * 64,
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
                "# Bootstrap\n\n- Skill version: `2.2.0`\n", encoding="utf-8",
            )
            (scout / "SKILL.md").write_text(
                "# Scout\n\n- Skill version: `5.7.0`\n", encoding="utf-8",
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
                    "bootstrap": "2.2.0", "scout": "5.7.0",
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

            desired, sidecar, source_hash = self.reconcile.load_desired_bundle(
                source_path, release_path,
            )

            self.assertEqual("v0.3.10", desired["release_ref"])
            self.assertEqual("1.5.1", desired["plugin_version"])
            self.assertEqual("2.2.0", desired["bootstrap_version"])
            self.assertEqual("a" * 40, sidecar.expected_commit)
            self.assertRegex(source_hash, r"^[0-9a-f]{64}$")
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
                ("agent-memory-workstation-bootstrap", "2.2.0"),
                ("global-owner-scout", "5.7.0"),
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
            self.assertEqual("2.2.0", observed["bootstrap_skill"]["version"])
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
            ):
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
