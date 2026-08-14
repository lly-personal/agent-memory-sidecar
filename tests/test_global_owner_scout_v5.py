from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_memory_sidecar.proposal import (
    RuleProposal,
    review_selection_token,
)


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "enrollment.py"
MANAGED_SOURCES = ROOT / ".agents" / "skills" / "agent-memory-workstation-bootstrap" / "scripts" / "managed_sources.py"
SCOUT_SCRIPTS = ROOT / ".agents" / "skills" / "global-owner-scout" / "scripts"
SCOUT_VALIDATOR = SCOUT_SCRIPTS / "validate_output.py"
SCOUT_RENDERER = SCOUT_SCRIPTS / "render_review.py"
SCOUT_VISIBLE_VERIFIER = SCOUT_SCRIPTS / "verify_visible_output.py"
SCOUT_OWNER_RESOLVER = SCOUT_SCRIPTS / "resolve_owner_parity.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GlobalOwnerScoutV55Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = load_module("workstation_enrollment", BOOTSTRAP)
        cls.managed_sources = load_module("workstation_managed_sources", MANAGED_SOURCES)
        sys.path.insert(0, str(SCOUT_SCRIPTS))
        try:
            cls.scout_validator = load_module(
                "scout_validator_v55",
                SCOUT_VALIDATOR,
            )
        finally:
            sys.path.pop(0)

    def bind_managed_owner(
        self,
        codex_home: Path,
        *,
        source_root: Path,
        source_commit: str,
    ) -> None:
        store = codex_home / "agent-memory-sidecar" / "memory.sqlite"
        store.parent.mkdir(parents=True, exist_ok=True)
        connection = self.managed_sources.sqlite3.connect(store)
        try:
            connection.execute(
                """
                CREATE TABLE global_instruction_binding (
                    singleton INTEGER PRIMARY KEY,
                    source_root TEXT NOT NULL,
                    source_commit TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO global_instruction_binding VALUES (1, ?, ?)",
                (str(source_root.resolve()), source_commit),
            )
            connection.commit()
        finally:
            connection.close()

    def test_skill_chain_only_tolerates_os_owned_top_level_aliases(self) -> None:
        predicate = getattr(self.bootstrap, "_is_trusted_host_directory_alias")
        root_owned_link = SimpleNamespace(st_mode=0o120777, st_uid=0)
        user_owned_link = SimpleNamespace(st_mode=0o120777, st_uid=1000)
        self.assertTrue(predicate(Path("/var"), root_owned_link, platform="posix"))
        self.assertFalse(predicate(Path("/var"), user_owned_link, platform="posix"))
        self.assertFalse(predicate(Path("/tmp/user-alias"), root_owned_link, platform="posix"))

    def test_selection_token_matches_core_operation_identity(self) -> None:
        pack = self.scout_validator.valid_review_pack(
            self.scout_validator.valid_project(card_count=1)
        )
        card = pack["project_result"]["project_cards"][0]
        review = pack["review_cards"][0]
        proposal = RuleProposal.from_payload(card["rule_payload"])
        self.assertEqual(
            review["selection_token"],
            review_selection_token(
                card_id=card["card_id"],
                project_claim_hash=card["project_claim_hash"],
                proposal=proposal,
                supersedes=tuple(
                    review["integration_preview"]["supersedes"]
                ),
                instruction_target=proposal.instruction_target,
                target_before_sha256=pack["owner_parity"][
                    "canonical_source_hash"
                ],
            ),
        )

    def test_bootstrap_contract_self_test(self) -> None:
        for script in (BOOTSTRAP, MANAGED_SOURCES):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "self-test"], cwd=ROOT, capture_output=True,
                text=True, encoding="utf-8", check=True,
            )
            self.assertEqual("ok", json.loads(result.stdout)["status"])

    def test_managed_source_sync_is_idempotent_and_rejects_dirty_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.managed_sources.create_remote(root, "sidecar")
            second = self.managed_sources.create_remote(root, "owner")
            specs = (
                self.managed_sources.SourceSpec("sidecar", str(first)),
                self.managed_sources.SourceSpec("canonical_owner", str(second)),
            )
            codex_home = root / "codex-home"
            installed = self.managed_sources.sync_sources(codex_home, specs)
            self.assertEqual({"synced"}, {item["status"] for item in installed["sources"].values()})
            unchanged = self.managed_sources.sync_sources(codex_home, specs)
            self.assertEqual({"unchanged"}, {item["status"] for item in unchanged["sources"].values()})

            dirty_file = codex_home / "agent-memory" / "sources" / "sidecar" / "README.md"
            dirty_file.write_text("user-owned dirty state", encoding="utf-8")
            with self.assertRaises(self.managed_sources.BootstrapError):
                self.managed_sources.sync_sources(codex_home, specs)
            self.assertEqual("user-owned dirty state", dirty_file.read_text(encoding="utf-8"))

    def test_release_source_manifest_binds_commit_and_allows_public_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = self.managed_sources.create_remote(root, "sidecar")
            commit = self.managed_sources.run_git(
                ["rev-parse", "HEAD"], cwd=root / "sidecar-work"
            )
            manifest = {
                "contract_version": "agent_memory_source_manifest_v1",
                "distribution": "release",
                "sidecar": {
                    "remote": str(remote),
                    "ref": "main",
                    "commit": commit,
                },
                "canonical_owner": None,
            }
            specs = self.managed_sources.validate_source_manifest(manifest)
            self.assertEqual(["sidecar"], [item.name for item in specs])
            receipt = self.managed_sources.sync_sources(root / "codex-home", specs)
            self.assertEqual("synced", receipt["sources"]["sidecar"]["status"])

            manifest["sidecar"]["commit"] = "f" * 40
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "managed_source_commit_mismatch",
            ):
                self.managed_sources.sync_sources(
                    root / "other-home",
                    self.managed_sources.validate_source_manifest(manifest),
                )

    def test_source_manifest_rejects_url_query_credentials(self) -> None:
        manifest = {
            "contract_version": "agent_memory_source_manifest_v1",
            "distribution": "release",
            "sidecar": {
                "remote": "https://example.invalid/sidecar.git?access_token=secret",
                "ref": "v0.3.0",
                "commit": "a" * 40,
            },
            "canonical_owner": None,
        }
        with self.assertRaisesRegex(
            self.managed_sources.BootstrapError,
            "query or fragment",
        ):
            self.managed_sources.validate_source_manifest(manifest)

    def test_public_core_refuses_to_hide_existing_global_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            remote = self.managed_sources.create_remote(codex_home, "sidecar")
            commit = self.managed_sources.run_git(
                ["rev-parse", "HEAD"], cwd=codex_home / "sidecar-work"
            )
            store = codex_home / "agent-memory-sidecar" / "memory.sqlite"
            store.parent.mkdir(parents=True)
            connection = self.managed_sources.sqlite3.connect(store)
            try:
                connection.execute("CREATE TABLE global_instruction_binding(value TEXT)")
                connection.execute("INSERT INTO global_instruction_binding VALUES ('bound')")
                connection.commit()
            finally:
                connection.close()
            specs = (
                self.managed_sources.SourceSpec(
                    "sidecar", str(remote), "main", commit
                ),
            )
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_owner_state_ambiguous",
            ):
                self.managed_sources.plan_source_cutover(codex_home, specs)
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "public_core_existing_global_binding",
            ):
                self.managed_sources.materialize_host(codex_home, specs)

    def test_public_core_materialization_omits_global_owner_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            sidecar = codex_home / "agent-memory" / "sources" / "sidecar"
            enrollment = (
                sidecar
                / ".agents"
                / "skills"
                / "agent-memory-workstation-bootstrap"
                / "scripts"
                / "enrollment.py"
            )
            enrollment.parent.mkdir(parents=True)
            enrollment.write_text("# fixture\n", encoding="utf-8")
            calls = []

            def successful(command, *, cwd, env):
                calls.append(command)
                if "install-skill" in command:
                    version = command[command.index("--version") + 1]
                    return {"status": "installed", "version": version, "hash": "a" * 64}
                return {
                    "contract_version": "agent_memory_result_v1",
                    "operation": "setup",
                    "status": "ok",
                    "scope": None,
                    "target": None,
                    "data": {
                        "status": "ok",
                        "doctor": {"status": "ok"},
                    },
                    "error": None,
                }

            specs = (
                self.managed_sources.SourceSpec(
                    "sidecar", "https://example.invalid/sidecar.git", "v0.3.0", "a" * 40
                ),
            )
            with mock.patch.object(
                self.managed_sources, "inspect_checkout", return_value="a" * 40
            ), mock.patch.object(
                self.managed_sources, "run_json", side_effect=successful
            ):
                result = self.managed_sources.materialize_host(codex_home, specs)
            setup_command = next(command for command in calls if "setup" in command)
            self.assertNotIn("--global-rules-source", setup_command)
            self.assertNotIn("--rebind-global-rules-source", setup_command)
            self.assertEqual("unavailable", result["global_binding"])

    def test_reconcile_materialization_reuses_only_exact_preserved_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            source_root = codex_home / "agent-memory" / "sources"
            sidecar = source_root / "sidecar"
            owner = source_root / "canonical_owner"
            enrollment = (
                sidecar / ".agents" / "skills" / "agent-memory-workstation-bootstrap"
                / "scripts" / "enrollment.py"
            )
            enrollment.parent.mkdir(parents=True)
            enrollment.write_text("# fixture\n", encoding="utf-8")
            owner.mkdir(parents=True)
            owner_commit = "b" * 40
            self.bind_managed_owner(
                codex_home,
                source_root=owner,
                source_commit=owner_commit,
            )
            calls = []

            def successful(command, *, cwd, env):
                calls.append(command)
                if "install-skill" in command:
                    version = command[command.index("--version") + 1]
                    return {"status": "installed", "version": version, "hash": "a" * 64}
                return {
                    "contract_version": "agent_memory_result_v1",
                    "operation": "setup",
                    "status": "ok",
                    "scope": None,
                    "target": None,
                    "data": {"status": "ok", "doctor": {"status": "ok"}},
                    "error": None,
                }

            specs = (
                self.managed_sources.SourceSpec(
                    "sidecar", "https://example.invalid/sidecar.git", "v0.3.4", "a" * 40
                ),
            )
            with mock.patch.object(
                self.managed_sources, "inspect_checkout", return_value="a" * 40
            ), mock.patch.object(
                self.managed_sources,
                "inspect_existing_checkout",
                return_value={"remote_sha256": "c" * 64, "commit": owner_commit},
            ), mock.patch.object(
                self.managed_sources, "run_json", side_effect=successful
            ):
                result = self.managed_sources.materialize_host(
                    codex_home,
                    specs,
                    preserve_existing_owner=True,
                )
            setup_command = next(command for command in calls if "setup" in command)
            self.assertIn("--global-rules-source", setup_command)
            self.assertIn("--rebind-global-rules-source", setup_command)
            self.assertEqual("verified", result["global_binding"])

    def test_managed_source_swap_failure_restores_both_previous_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.managed_sources.create_remote(root, "sidecar")
            second = self.managed_sources.create_remote(root, "owner")
            specs = (
                self.managed_sources.SourceSpec("sidecar", str(first)),
                self.managed_sources.SourceSpec("canonical_owner", str(second)),
            )
            codex_home = root / "codex-home"
            self.managed_sources.sync_sources(codex_home, specs)
            source_root = codex_home / "agent-memory" / "sources"
            before = {
                item.name: self.managed_sources.inspect_checkout(item, spec)
                for item, spec in ((source_root / "sidecar", specs[0]), (source_root / "canonical_owner", specs[1]))
            }
            for name, remote in (("sidecar", first), ("owner", second)):
                work = root / f"{name}-work"
                self.managed_sources.run_git(["remote", "add", "origin", str(remote)], cwd=work)
                (work / "README.md").write_text(name + " updated", encoding="utf-8")
                self.managed_sources.run_git(["add", "README.md"], cwd=work)
                self.managed_sources.run_git(["commit", "-q", "-m", "update"], cwd=work)
                self.managed_sources.run_git(["push", "-q", "origin", "main"], cwd=work)

            original_replace = self.managed_sources.os.replace

            def fail_second_swap(source, target):
                source_path = Path(source)
                target_path = Path(target)
                if source_path.name.startswith(".canonical_owner.stage-") and target_path.name == "canonical_owner":
                    raise OSError("simulated second swap failure")
                return original_replace(source, target)

            with mock.patch.object(self.managed_sources.os, "replace", side_effect=fail_second_swap):
                with self.assertRaises(OSError):
                    self.managed_sources.sync_sources(codex_home, specs)
            after = {
                item.name: self.managed_sources.inspect_checkout(item, spec)
                for item, spec in ((source_root / "sidecar", specs[0]), (source_root / "canonical_owner", specs[1]))
            }
            self.assertEqual(before, after)

    def test_first_install_swap_failure_removes_partial_new_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.managed_sources.create_remote(root, "sidecar")
            second = self.managed_sources.create_remote(root, "owner")
            specs = (
                self.managed_sources.SourceSpec("sidecar", str(first)),
                self.managed_sources.SourceSpec("canonical_owner", str(second)),
            )
            codex_home = root / "codex-home"
            original_replace = self.managed_sources.os.replace

            def fail_second_swap(source, target):
                source_path = Path(source)
                target_path = Path(target)
                if source_path.name.startswith(".canonical_owner.stage-") and target_path.name == "canonical_owner":
                    raise OSError("simulated first-install second swap failure")
                return original_replace(source, target)

            with mock.patch.object(
                self.managed_sources.os,
                "replace",
                side_effect=fail_second_swap,
            ):
                with self.assertRaises(OSError):
                    self.managed_sources.sync_sources(codex_home, specs)
            source_root = codex_home / "agent-memory" / "sources"
            self.assertFalse((source_root / "sidecar").exists())
            self.assertFalse((source_root / "canonical_owner").exists())

    def test_source_cutover_requires_fresh_plan_and_preserves_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_sidecar = self.managed_sources.create_remote(root, "old-sidecar")
            public_sidecar = self.managed_sources.create_remote(root, "public-sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            old_specs = (
                self.managed_sources.SourceSpec("sidecar", str(old_sidecar)),
                self.managed_sources.SourceSpec("canonical_owner", str(owner)),
            )
            self.managed_sources.sync_sources(codex_home, old_specs)
            desired_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar",
                    str(public_sidecar),
                    "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "public-sidecar-work"),
                ),
                self.managed_sources.SourceSpec(
                    "canonical_owner",
                    str(owner),
                    "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "owner-work"),
                ),
            )
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "managed_source_identity_mismatch",
            ):
                self.managed_sources.sync_sources(codex_home, desired_specs)
            plan = self.managed_sources.plan_source_cutover(codex_home, desired_specs)
            self.assertEqual("keep_owner", plan["owner_action"])
            self.assertEqual(["sidecar:replace"], plan["changes"])
            self.assertNotIn(str(root), json.dumps(plan))
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_plan_stale",
            ):
                self.managed_sources.apply_source_cutover(
                    codex_home, desired_specs, plan_hash="f" * 64,
                )
            with mock.patch.object(
                self.managed_sources,
                "materialize_host",
                return_value={"status": "ok", "doctor": "verified"},
            ):
                receipt = self.managed_sources.apply_source_cutover(
                    codex_home, desired_specs, plan_hash=plan["plan_hash"],
                )
            self.assertEqual("applied", receipt["status"])
            self.assertEqual("keep_owner", receipt["owner_action"])
            source_root = codex_home / "agent-memory" / "sources"
            self.assertEqual(
                desired_specs[0].expected_commit,
                self.managed_sources.inspect_checkout(source_root / "sidecar", desired_specs[0]),
            )
            self.assertEqual(
                desired_specs[1].expected_commit,
                self.managed_sources.inspect_checkout(source_root / "canonical_owner", desired_specs[1]),
            )
            persisted = json.loads(
                (codex_home / "agent-memory" / "source-cutover-receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["plan_hash"], persisted["plan_hash"])
            help_result = subprocess.run(
                [sys.executable, "-B", str(MANAGED_SOURCES), "source-cutover", "--help"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertIn("--dry-run", help_result.stdout)
            self.assertIn("--apply", help_result.stdout)
            self.assertNotIn("--force", help_result.stdout)

    def test_public_manifest_cutover_preserves_exact_existing_owner_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_sidecar = self.managed_sources.create_remote(root, "old-sidecar")
            public_sidecar = self.managed_sources.create_remote(root, "public-sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            self.managed_sources.sync_sources(
                codex_home,
                (
                    self.managed_sources.SourceSpec("sidecar", str(old_sidecar)),
                    self.managed_sources.SourceSpec("canonical_owner", str(owner)),
                ),
            )
            source_root = codex_home / "agent-memory" / "sources"
            owner_commit = self.managed_sources.run_git(
                ["rev-parse", "HEAD"], cwd=source_root / "canonical_owner"
            )
            owner_remote_before = self.managed_sources.run_git(
                ["remote", "get-url", "origin"], cwd=source_root / "canonical_owner"
            )
            self.bind_managed_owner(
                codex_home,
                source_root=source_root / "canonical_owner",
                source_commit=owner_commit,
            )
            desired_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar",
                    str(public_sidecar),
                    "main",
                    self.managed_sources.run_git(
                        ["rev-parse", "HEAD"], cwd=root / "public-sidecar-work"
                    ),
                ),
            )
            plan = self.managed_sources.plan_source_cutover(codex_home, desired_specs)
            self.assertEqual("agent_memory_source_cutover_plan_v2", plan["contract_version"])
            self.assertEqual("keep_owner", plan["owner_action"])
            self.assertEqual("preserved", plan["desired"]["canonical_owner"]["ref"])
            self.assertEqual(["sidecar:replace"], plan["changes"])
            rendered = self.managed_sources.render_source_cutover_plan(plan)
            self.assertIn("确认更新", rendered)
            self.assertIn("保持本机已精确绑定的私有 Owner", rendered)
            self.assertNotIn(plan["plan_hash"], rendered)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("http", rendered)
            with mock.patch.object(
                self.managed_sources,
                "materialize_host",
                return_value={"status": "ok", "doctor": "verified"},
            ) as materialize:
                receipt = self.managed_sources.apply_source_cutover(
                    codex_home,
                    desired_specs,
                    plan_hash=plan["plan_hash"],
                )
            materialize.assert_called_once_with(
                codex_home,
                desired_specs,
                preserve_existing_owner=True,
            )
            self.assertEqual("agent_memory_source_cutover_receipt_v2", receipt["contract_version"])
            self.assertEqual("preserved", receipt["sources"]["canonical_owner"]["ref"])
            self.assertEqual(
                self.managed_sources.normalize_remote(owner_remote_before),
                self.managed_sources.normalize_remote(
                    self.managed_sources.run_git(
                        ["remote", "get-url", "origin"], cwd=source_root / "canonical_owner"
                    )
                ),
            )

    def test_public_manifest_cutover_rejects_ambiguous_owner_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sidecar = self.managed_sources.create_remote(root, "sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            self.managed_sources.sync_sources(
                codex_home,
                (
                    self.managed_sources.SourceSpec("sidecar", str(sidecar)),
                    self.managed_sources.SourceSpec("canonical_owner", str(owner)),
                ),
            )
            sidecar_commit = self.managed_sources.run_git(
                ["rev-parse", "HEAD"], cwd=root / "sidecar-work"
            )
            public_specs = (
                self.managed_sources.SourceSpec("sidecar", str(sidecar), "main", sidecar_commit),
            )
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_owner_state_ambiguous",
            ):
                self.managed_sources.plan_source_cutover(codex_home, public_specs)

    def test_explicit_owner_identity_replacement_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sidecar = self.managed_sources.create_remote(root, "sidecar")
            old_owner = self.managed_sources.create_remote(root, "old-owner")
            new_owner = self.managed_sources.create_remote(root, "new-owner")
            codex_home = root / "codex-home"
            self.managed_sources.sync_sources(
                codex_home,
                (
                    self.managed_sources.SourceSpec("sidecar", str(sidecar)),
                    self.managed_sources.SourceSpec("canonical_owner", str(old_owner)),
                ),
            )
            desired_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar",
                    str(sidecar),
                    "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "sidecar-work"),
                ),
                self.managed_sources.SourceSpec(
                    "canonical_owner",
                    str(new_owner),
                    "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "new-owner-work"),
                ),
            )
            plan = self.managed_sources.plan_source_cutover(codex_home, desired_specs)
            self.assertEqual(["canonical_owner:replace"], plan["changes"])
            rendered = self.managed_sources.render_source_cutover_plan(plan)
            self.assertIn("确认更新", rendered)
            self.assertIn("切换到显式提供且已验证的私有 Owner", rendered)

    def test_public_manifest_cutover_rejects_dirty_or_mismatched_owner_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sidecar = self.managed_sources.create_remote(root, "sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            self.managed_sources.sync_sources(
                codex_home,
                (
                    self.managed_sources.SourceSpec("sidecar", str(sidecar)),
                    self.managed_sources.SourceSpec("canonical_owner", str(owner)),
                ),
            )
            source_root = codex_home / "agent-memory" / "sources"
            owner_commit = self.managed_sources.run_git(
                ["rev-parse", "HEAD"], cwd=source_root / "canonical_owner"
            )
            self.bind_managed_owner(
                codex_home,
                source_root=source_root / "canonical_owner",
                source_commit="f" * 40,
            )
            public_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar",
                    str(sidecar),
                    "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "sidecar-work"),
                ),
            )
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_owner_state_ambiguous",
            ):
                self.managed_sources.plan_source_cutover(codex_home, public_specs)

            connection = self.managed_sources.sqlite3.connect(
                codex_home / "agent-memory-sidecar" / "memory.sqlite"
            )
            try:
                connection.execute(
                    "UPDATE global_instruction_binding SET source_commit = ? WHERE singleton = 1",
                    (owner_commit,),
                )
                connection.commit()
            finally:
                connection.close()
            (source_root / "canonical_owner" / "README.md").write_text(
                "dirty owner",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_owner_state_ambiguous",
            ):
                self.managed_sources.plan_source_cutover(codex_home, public_specs)

    def test_source_cutover_materialization_failure_restores_sources_and_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_sidecar = self.managed_sources.create_remote(root, "old-sidecar")
            public_sidecar = self.managed_sources.create_remote(root, "public-sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            old_specs = (
                self.managed_sources.SourceSpec("sidecar", str(old_sidecar)),
                self.managed_sources.SourceSpec("canonical_owner", str(owner)),
            )
            self.managed_sources.sync_sources(codex_home, old_specs)
            skill_root = codex_home / "skills"
            for name in ("agent-memory-workstation-bootstrap", "global-owner-scout"):
                target = skill_root / name
                target.mkdir(parents=True)
                (target / "marker.txt").write_text("before", encoding="utf-8")
            desired_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar", str(public_sidecar), "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "public-sidecar-work"),
                ),
                self.managed_sources.SourceSpec(
                    "canonical_owner", str(owner), "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "owner-work"),
                ),
            )
            plan = self.managed_sources.plan_source_cutover(codex_home, desired_specs)

            def fail_materialization(*_args, **_kwargs):
                for name in ("agent-memory-workstation-bootstrap", "global-owner-scout"):
                    (skill_root / name / "marker.txt").write_text("after", encoding="utf-8")
                raise self.managed_sources.BootstrapError("simulated_materialization_failure")

            with mock.patch.object(
                self.managed_sources, "materialize_host", side_effect=fail_materialization
            ):
                with self.assertRaisesRegex(
                    self.managed_sources.BootstrapError,
                    "simulated_materialization_failure",
                ):
                    self.managed_sources.apply_source_cutover(
                        codex_home, desired_specs, plan_hash=plan["plan_hash"],
                    )
            source_root = codex_home / "agent-memory" / "sources"
            self.assertEqual(
                self.managed_sources.normalize_remote(str(old_sidecar)),
                self.managed_sources.normalize_remote(
                    self.managed_sources.run_git(["remote", "get-url", "origin"], cwd=source_root / "sidecar")
                ),
            )
            for name in ("agent-memory-workstation-bootstrap", "global-owner-scout"):
                self.assertEqual("before", (skill_root / name / "marker.txt").read_text(encoding="utf-8"))
            self.assertFalse((codex_home / "agent-memory" / "source-cutover-receipt.json").exists())

    def test_source_cutover_rejects_unsafe_installed_skill_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary)
            target = codex_home / "skills" / "agent-memory-workstation-bootstrap"
            target.mkdir(parents=True)
            first = target / "first.txt"
            second = target / "second.txt"
            first.write_text("managed", encoding="utf-8")
            try:
                second.hardlink_to(first)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "installed_skill_target_invalid",
            ):
                self.managed_sources._snapshot_skill_targets(codex_home)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_source_cutover_preflights_receipt_before_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_sidecar = self.managed_sources.create_remote(root, "old-sidecar")
            public_sidecar = self.managed_sources.create_remote(root, "public-sidecar")
            owner = self.managed_sources.create_remote(root, "owner")
            codex_home = root / "codex-home"
            old_specs = (
                self.managed_sources.SourceSpec("sidecar", str(old_sidecar)),
                self.managed_sources.SourceSpec("canonical_owner", str(owner)),
            )
            self.managed_sources.sync_sources(codex_home, old_specs)
            desired_specs = (
                self.managed_sources.SourceSpec(
                    "sidecar", str(public_sidecar), "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "public-sidecar-work"),
                ),
                self.managed_sources.SourceSpec(
                    "canonical_owner", str(owner), "main",
                    self.managed_sources.run_git(["rev-parse", "HEAD"], cwd=root / "owner-work"),
                ),
            )
            plan = self.managed_sources.plan_source_cutover(codex_home, desired_specs)
            receipt_target = codex_home / "agent-memory" / "source-cutover-receipt.json"
            receipt_target.mkdir()
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "source_cutover_receipt_target_invalid",
            ):
                self.managed_sources.apply_source_cutover(
                    codex_home, desired_specs, plan_hash=plan["plan_hash"],
                )
            source_root = codex_home / "agent-memory" / "sources"
            self.assertEqual(
                self.managed_sources.normalize_remote(str(old_sidecar)),
                self.managed_sources.normalize_remote(
                    self.managed_sources.run_git(["remote", "get-url", "origin"], cwd=source_root / "sidecar")
                ),
            )

    def test_managed_source_root_rejects_directory_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            codex_home.mkdir()
            external = root / "external"
            external.mkdir()
            alias = codex_home / "agent-memory"
            try:
                alias.symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symbolic links unavailable: {exc}")
            with self.assertRaisesRegex(
                self.managed_sources.BootstrapError,
                "managed_directory_alias_forbidden",
            ):
                self.managed_sources.sync_sources(codex_home, ())
            self.assertEqual([], list(external.iterdir()))

    def test_deployment_pack_keeps_proof_layers_separate(self) -> None:
        pack = self.managed_sources.valid_pack()
        validated = self.managed_sources.validate_pack(pack)
        self.assertEqual("1.8.0", validated["bootstrap_version"])
        rendered = self.managed_sources.render_pack(pack)
        for label in ("可移植分发", "能力源同步", "主机物化", "项目启用"):
            self.assertIn(label, rendered)
        self.assertIn("真实第二台设备", rendered)

    def test_materialization_wrapper_accepts_success_with_null_error(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["example"], returncode=0,
            stdout=json.dumps({"status": "ok", "error": None}), stderr="",
        )
        with mock.patch.object(self.managed_sources.subprocess, "run", return_value=completed):
            result = self.managed_sources.run_json(["example"], cwd=ROOT, env={})
        self.assertEqual("ok", result["status"])

    def test_core_setup_result_rejects_mock_only_raw_shape(self) -> None:
        with self.assertRaisesRegex(
            self.managed_sources.BootstrapError,
            "core_setup_result_invalid",
        ):
            self.managed_sources.core_setup_data(
                {"status": "ok", "doctor": {"status": "ok"}}
            )

    def test_cold_start_anchor_and_plugin_do_not_embed_host_identity(self) -> None:
        portable_paths = (
            ROOT / ".agents" / "skills" / "agent-memory-bootstrap-anchor" / "SKILL.md",
            ROOT / "plugins" / "agent-memory-sidecar" / "skills" / "agent-memory-bootstrap-anchor" / "SKILL.md",
        )
        for path in portable_paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?:^|[\"'\s])[A-Za-z]:[\\/]")
            self.assertNotIn("projectId", text)
            self.assertNotIn("pdg-multi-level-partition-infra", text)
            self.assertNotIn("feishu-agent-lab", text)
            self.assertIn("source-cutover --dry-run", text)
            self.assertIn("do not defer host deployment", text)
            self.assertNotIn("In that task, invoke", text)
        marketplace = ROOT / ".agents" / "plugins" / "marketplace.json"
        if marketplace.is_file():
            text = marketplace.read_text(encoding="utf-8")
            self.assertIn('"installation": "AVAILABLE"', text)
            value = self.managed_sources.validate_marketplace(
                json.loads(text),
                expected_remote="https://github.com/lly-personal/agent-memory-sidecar.git",
            )
            self.assertEqual("v0.3.5", value["plugins"][0]["source"]["ref"])
        else:
            self.assertTrue(
                (ROOT / "PUBLIC_EXPORT_RECEIPT.json").is_file()
                or (ROOT / "PUBLIC_AUTHORITY.json").is_file()
            )
            self.assertTrue((ROOT / "LICENSE").is_file())

    def test_scout_validator_renderer_and_visible_verifier_self_tests(self) -> None:
        for script in (SCOUT_VALIDATOR, SCOUT_RENDERER, SCOUT_VISIBLE_VERIFIER, SCOUT_OWNER_RESOLVER):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--self-test"], cwd=SCOUT_SCRIPTS,
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            self.assertEqual("ok", json.loads(result.stdout)["status"])

    def test_installed_v4_contract_remains_accepted_during_migration(self) -> None:
        command = (
            "import json,sys; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0,sys.argv[1]); "
            "import validate_output_v4 as old; print(json.dumps(old.valid_review_pack(),ensure_ascii=False))"
        )
        legacy = subprocess.run(
            [sys.executable, "-c", command, str(SCOUT_SCRIPTS)], capture_output=True,
            text=True, encoding="utf-8", check=True
        ).stdout
        validated = subprocess.run(
            [sys.executable, str(SCOUT_VALIDATOR), "--mode", "review_pack"], input=legacy,
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        self.assertEqual("global_owner_scout_review_pack_v2", json.loads(validated.stdout)["contract_version"])

    def test_content_identity_is_path_independent_and_remote_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            identities = []
            for name, remote in (
                ("first", "https://example.invalid/owner/repo.git"),
                ("second", "git@example.invalid:owner/repo.git"),
                ("other", "https://example.invalid/owner/other.git"),
            ):
                repo = base / name
                repo.mkdir()
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", remote], check=True)
                identities.append(self.bootstrap.inspect_project(repo, name, f"host-{name}")["content_identity_hash"])
            self.assertEqual(identities[0], identities[1])
            self.assertNotEqual(identities[0], identities[2])

    def test_same_name_different_remote_is_not_merged(self) -> None:
        first = self.bootstrap.opaque("pci", self.bootstrap.normalize_remote("https://one.invalid/team/tool.git") + "\n.")
        second = self.bootstrap.opaque("pci", self.bootstrap.normalize_remote("https://two.invalid/team/tool.git") + "\n.")
        self.assertNotEqual(first, second)

    def test_non_git_project_is_visible_but_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.bootstrap.inspect_project(Path(temporary), "本地资料", "host-local")
        self.assertEqual("host_local", result["identity_kind"])
        self.assertEqual("ineligible", result["eligibility"])

    def test_atomic_skill_install_excludes_python_bytecode_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            (source / "scripts" / "__pycache__").mkdir(parents=True)
            (source / "SKILL.md").write_text("---\nname: example\ndescription: example\n---\n", encoding="utf-8")
            (source / "scripts" / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "scripts" / "__pycache__" / "helper.pyc").write_bytes(b"generated")
            result = self.bootstrap.install_skill(source, target)
            self.assertEqual("installed", result["status"])
            self.assertTrue((target / "scripts" / "helper.py").is_file())
            self.assertFalse((target / "scripts" / "__pycache__").exists())

    def test_skill_install_rejects_hardlinked_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            skill = source / "SKILL.md"
            skill.write_text("---\nname: example\ndescription: example\n---\n", encoding="utf-8")
            alias = root / "alias.md"
            try:
                alias.hardlink_to(skill)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            with self.assertRaisesRegex(self.bootstrap.ContractError, "unsafe file"):
                self.bootstrap.install_skill(source, root / "target")

    def test_skill_install_rejects_target_directory_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("---\nname: example\ndescription: example\n---\n", encoding="utf-8")
            physical = root / "physical-target"
            physical.mkdir()
            marker = physical / "owner.txt"
            marker.write_text("preserve", encoding="utf-8")
            alias = root / "target-alias"
            try:
                alias.symlink_to(physical, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symbolic links unavailable: {exc}")
            with self.assertRaisesRegex(self.bootstrap.ContractError, "physical directory"):
                self.bootstrap.install_skill(source, alias)
            self.assertEqual("preserve", marker.read_text(encoding="utf-8"))

    def test_v5_prompt_has_no_fixed_binding(self) -> None:
        prompt = (
            "Use $global-owner-scout in project_scout mode for the current bound project; rolling 72 hours; "
            "Skill 5.5.0; global_owner_scout_project_v4; global_owner_scout_review_pack_v4; "
            "gpt-5.6-sol; medium; read-only."
        )
        self.bootstrap.validate_prompt(prompt)
        for forbidden in ("project_key=fixed", "projectId=abc", r"C:\\repo\\project"):
            with self.assertRaises(self.bootstrap.ContractError):
                self.bootstrap.validate_prompt(forbidden)

    def test_active_skill_source_has_no_historical_project_allowlist(self) -> None:
        historical_names = ("pdg-multi-level-partition-infra", "feishu-agent-lab")
        for path in (ROOT / ".agents" / "skills").rglob("*"):
            if not path.is_file() or path.name.endswith("_v4.py") or path.suffix in {".pyc", ".pyo"}:
                continue
            text = path.read_text(encoding="utf-8")
            for name in historical_names:
                self.assertNotIn(name, text, f"fixed project name leaked into {path}")

    def _review_pack_json(self, card_count: int, *, surface: str = "interactive") -> str:
        status = "no_material_delta" if card_count == 0 else "ok"
        window_kind = "rolling_72h" if surface == "scheduled" else "manual_30d"
        code = (
            "import json,sys; sys.stdout.reconfigure(encoding='utf-8'); "
            "sys.path.insert(0,sys.argv[1]); import validate_output as v; "
            "project=v.valid_project(status=sys.argv[2],card_count=int(sys.argv[3]),window_kind=sys.argv[4]); "
            "print(json.dumps(v.valid_review_pack(project),ensure_ascii=False))"
        )
        return subprocess.run(
            [sys.executable, "-B", "-c", code, str(SCOUT_SCRIPTS), status, str(card_count), window_kind],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout

    def test_direct_renderer_and_visible_verifier_conserve_both_surfaces(self) -> None:
        for surface in ("interactive", "scheduled"):
            for count in (0, 1, 3, 24):
                rendered = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_RENDERER), "--surface", surface],
                    cwd=SCOUT_SCRIPTS,
                    input=self._review_pack_json(count, surface=surface),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                ).stdout
                verified = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_VISIBLE_VERIFIER), "--surface", surface],
                    cwd=SCOUT_SCRIPTS,
                    input=rendered,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )
                receipt = json.loads(verified.stdout)
                self.assertEqual(count, receipt["project_cards"])
                self.assertEqual(count, receipt["visible_cards"])
                self.assertEqual(count, len(receipt["visible_action_counts"]))
                self.assertEqual(receipt["visible_actions"], sum(receipt["visible_action_counts"]))
                self.assertEqual(1 if count > 1 else 0, receipt["bundle_action_count"])
                self.assertEqual(1 if surface == "scheduled" else 0, receipt["wrapper_count"])
                if surface == "interactive":
                    self.assertNotIn("::inbox-item{", rendered)
                    self.assertNotIn("今日需要判断", rendered)
                    self.assertNotIn("14 次", rendered)
                else:
                    self.assertEqual(1, rendered.count("::inbox-item{"))
                if count > 1:
                    self.assertIn("一次确认多张", rendered)
                    self.assertIn("全部成功，或整包零写入", rendered)

    def test_visible_verifier_rejects_manual_body_rewrite(self) -> None:
        rendered = subprocess.run(
            [sys.executable, "-B", str(SCOUT_RENDERER), "--surface", "interactive"],
            cwd=SCOUT_SCRIPTS,
            input=self._review_pack_json(1),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        tampered = rendered.replace("项目里发生了什么", "项目发生了什么", 1)
        verified = subprocess.run(
            [sys.executable, "-B", str(SCOUT_VISIBLE_VERIFIER), "--surface", "interactive"],
            cwd=SCOUT_SCRIPTS,
            input=tampered,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(0, verified.returncode)
        self.assertIn("visible body SHA-256 mismatch", verified.stderr)

    def test_surface_cross_use_and_manual_model_mismatch_are_rejected(self) -> None:
        rendered = subprocess.run(
            [sys.executable, "-B", str(SCOUT_RENDERER), "--surface", "interactive"], cwd=SCOUT_SCRIPTS,
            input=self._review_pack_json(1), capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
        crossed = subprocess.run(
            [sys.executable, "-B", str(SCOUT_VISIBLE_VERIFIER), "--surface", "scheduled"], cwd=SCOUT_SCRIPTS,
            input=rendered, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertNotEqual(0, crossed.returncode)

        code = (
            "import copy,sys; sys.path.insert(0,sys.argv[1]); import validate_output as v; "
            "p=v.valid_project(); p['model_observation']['actual_model']='different'; v.validate_project(p)"
        )
        mismatch = subprocess.run(
            [sys.executable, "-B", "-c", code, str(SCOUT_SCRIPTS)], capture_output=True, text=True, encoding="utf-8",
        )
        self.assertNotEqual(0, mismatch.returncode)

    def test_active_owner_contract_has_dynamic_support_and_terminal_execution_gate(self) -> None:
        active_docs = (
            ROOT / "docs" / "specs" / "axioms.md",
            ROOT / "docs" / "specs" / "topology.md",
            ROOT / "docs" / "specs" / "interface.md",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in active_docs)
        self.assertNotIn("1/3 projects", combined)
        self.assertIn("execution_protocol_failed", combined)
        self.assertIn("verify_visible_output.py", combined)
        self.assertIn("automation-source canary", combined)
        self.assertIn("production_blocked", combined)
        self.assertIn("$global-owner-scout 复盘当前项目", combined)
        self.assertIn("interactive_project_scout", combined)
        self.assertIn("冷启动", combined)
        self.assertIn("agent_memory_workstation_deployment_pack_v1", combined)

        skill = (ROOT / ".agents" / "skills" / "global-owner-scout" / "SKILL.md").read_text(encoding="utf-8")
        protocol = (ROOT / ".agents" / "skills" / "global-owner-scout" / "references" / "deep-review-protocol.md").read_text(encoding="utf-8")
        self.assertIn("turnLimit=10", skill + protocol)
        self.assertIn("maxOutputCharsPerItem=20000", skill + protocol)
        self.assertIn("invoke no other Skill or tool", skill)
        self.assertIn("python -B", skill + protocol)

    def test_owner_resolver_uses_installed_binding_without_path_output(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(SCOUT_OWNER_RESOLVER), "--self-test"],
            cwd=SCOUT_SCRIPTS,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual("ok", json.loads(result.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
