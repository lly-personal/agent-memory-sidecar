from __future__ import annotations

import io
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar import cli, runtime_package
from agent_memory_sidecar.ambient_capability import (
    MAX_AMBIENT_CAPABILITY_BYTES,
    build_ambient_capability,
)
from agent_memory_sidecar.codex_integration import (
    _global_materialization_plan,
    doctor,
    setup,
)
from agent_memory_sidecar.database import CoreDatabase
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.identity import ProjectIdentity, resolve_identity
from agent_memory_sidecar.proposal import (
    RuleBundle,
    RuleProposal,
    review_selection_token,
)
from agent_memory_sidecar.runtime_ledger import RuntimeLedger
from agent_memory_sidecar.runtime_package import (
    build_runtime_artifact,
    desired_hooks_document,
    install_runtime_artifact,
    runtime_commands,
    self_test_artifact,
)
from agent_memory_sidecar.skill import (
    SkillPlan,
    build_skill_files,
    install_skill,
    installed_skill_sha256,
    skill_package_sha256,
)


class CliAndPackageTests(unittest.TestCase):
    def test_public_help_only_advertises_new_surface(self) -> None:
        help_text = cli.build_parser().format_help()
        self.assertIn("{rule,setup,doctor}", help_text)
        self.assertNotIn("remember", help_text)
        self.assertNotIn("forget", help_text)
        self.assertNotIn("status", help_text)

    def test_supersedes_is_repeatable_for_deploy_and_proposals(self) -> None:
        parser = cli.build_parser()
        first = "rule_000000000001"
        second = "rule_000000000002"
        deploy = parser.parse_args(
            [
                "rule",
                "deploy",
                "--from-json",
                "{}",
                "--approval-ref",
                "opaque",
                "--supersedes",
                first,
                "--supersedes",
                second,
            ]
        )
        self.assertEqual(deploy.supersedes, [first, second])
        create = parser.parse_args(
            [
                "proposal",
                "create",
                "--source-event",
                "opaque",
                "--from-json",
                "{}",
                "--supersedes",
                first,
                "--supersedes",
                second,
            ]
        )
        self.assertEqual(create.supersedes, [first, second])

    def test_rule_bundle_and_target_scoped_list_are_public(self) -> None:
        parser = cli.build_parser()
        listing = parser.parse_args(
            ["rule", "list", "--target", "global_agents"]
        )
        self.assertEqual(listing.target, "global_agents")
        bundle = parser.parse_args(
            [
                "rule",
                "deploy-bundle",
                "--from-json",
                '{"contract_version":"rule_revision_bundle_v2","target_before_sha256":"' + ("0" * 64) + '","items":[]}',
                "--approval-ref",
                "opaque",
            ]
        )
        self.assertEqual(bundle.operation, "rule.deploy_bundle")

    def test_unknown_legacy_command_returns_result_v1_and_exit_one(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["status"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(
            payload["contract_version"],
            "agent_memory_result_v1",
        )
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertNotIn("proposal", payload["error"]["message"])
        self.assertNotIn("maintenance", payload["error"]["message"])

    def test_doctor_failure_is_json_and_exit_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"CODEX_HOME": directory}),
                redirect_stdout(output),
            ):
                code = cli.main(["doctor"])
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(payload["operation"], "doctor")
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["code"], "doctor_failed")

    def test_rule_list_returns_uniform_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            project = root / "project"
            project.mkdir()
            with CoreDatabase(
                store,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(root / "codex")}),
                redirect_stdout(output),
            ):
                code = cli.main(
                    [
                        "--store",
                        str(store),
                        "--cwd",
                        str(project),
                        "rule",
                        "list",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["operation"], "rule.list")
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["rules"], [])
            self.assertEqual(len(payload["data"]["targets"]), 2)
            for target in payload["data"]["targets"]:
                self.assertEqual(
                    target["managed_block_budget_bytes"],
                    8192,
                )
                self.assertEqual(target["remaining_bytes"], 8192)

    def test_rule_deploy_bundle_cli_applies_one_atomic_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            project = root / "project"
            project.mkdir()
            codex = root / "codex"
            codex.mkdir()
            identity = resolve_identity(project)
            proposal = {
                "trigger": "When reviewing repository changes.",
                "skip_boundary": "Skip for prose-only work.",
                "scope": "project",
                "why": "Avoid repeat regressions.",
                "evidence": "The user selected both cards.",
                "instruction_target": "project_agents",
            }
            target_before_sha256 = hashlib.sha256(b"").hexdigest()
            items = []
            for index, action in enumerate(
                (
                    "Apply first selected behavior.",
                    "Apply second selected behavior.",
                ),
                start=1,
            ):
                parsed = RuleProposal.from_payload(
                    {**proposal, "action": action}
                )
                card_id = f"card-{index:04d}"
                claim = hashlib.sha256(
                    f"claim-{index}".encode("utf-8")
                ).hexdigest()
                items.append(
                    {
                        "card_id": card_id,
                        "project_claim_hash": claim,
                        "proposal": parsed.to_dict(),
                        "supersedes": [],
                        "selection_token": review_selection_token(
                            card_id=card_id,
                            project_claim_hash=claim,
                            proposal=parsed,
                            supersedes=(),
                            instruction_target="project_agents",
                            target_before_sha256=target_before_sha256,
                        ),
                    }
                )
            parsed_bundle = RuleBundle.from_payload(
                {
                    "contract_version": "rule_revision_bundle_v2",
                    "target_before_sha256": target_before_sha256,
                    "items": items,
                }
            )
            bundle = parsed_bundle.to_dict()
            with CoreDatabase(
                store,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ) as db:
                event = RuntimeLedger(db).capture_prompt(
                    identity=identity,
                    source_session="session",
                    prompt=parsed_bundle.confirmation_text,
                    metadata={},
                )
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                redirect_stdout(output),
            ):
                code = cli.main(
                    [
                        "--store",
                        str(store),
                        "--cwd",
                        str(project),
                        "rule",
                        "deploy-bundle",
                        "--from-json",
                        json.dumps(bundle),
                        "--approval-ref",
                        f"user_prompt:{event.event_id}",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["operation"], "rule.deploy_bundle")
            self.assertEqual(payload["data"]["action"], "bundle_deployed")
            self.assertEqual(len(payload["data"]["items"]), 2)
            deployed = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Apply first selected behavior.", deployed)
            self.assertIn("Apply second selected behavior.", deployed)

    def test_zipapp_is_deterministic_and_self_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "memory.sqlite"
            with CoreDatabase(
                store,
                create=True,
                now="2026-07-24T00:00:00+00:00",
            ):
                pass
            first = build_runtime_artifact()
            second = build_runtime_artifact()
            self.assertEqual(first.data, second.data)
            with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
                names = set(archive.namelist())
            self.assertIn(
                "agent_memory_sidecar/runtime_hook.py",
                names,
            )
            self.assertNotIn(
                "agent_memory_sidecar/core_cutover.py",
                names,
            )
            self.assertNotIn(
                "agent_memory_sidecar/rule_service.py",
                names,
            )
            artifact = install_runtime_artifact(
                artifact=first,
                runtime_root=root / "runtime",
            )
            result = self_test_artifact(
                artifact_path=artifact,
                store_path=store,
            )
            self.assertEqual(result["status"], "ok")
            with CoreDatabase(store) as db:
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM prompt_events"
                    ).fetchone()[0],
                    0,
                )
            self.assertTrue(
                str(artifact).endswith(f"{first.sha256[:16]}.pyz")
            )

    def test_zipapp_is_independent_of_checkout_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf_root = root / "lf"
            crlf_root = root / "crlf"
            lf_root.mkdir()
            crlf_root.mkdir()
            package_root = Path(runtime_package.__file__).parent
            for name in runtime_package._RUNTIME_MODULES:
                source = (package_root / name).read_bytes()
                canonical = source.replace(b"\r\n", b"\n").replace(
                    b"\r", b"\n"
                )
                (lf_root / name).write_bytes(canonical)
                (crlf_root / name).write_bytes(
                    canonical.replace(b"\n", b"\r\n")
                )

            lf_artifact = build_runtime_artifact(package_dir=lf_root)
            crlf_artifact = build_runtime_artifact(package_dir=crlf_root)

            self.assertEqual(lf_artifact.sha256, crlf_artifact.sha256)
            self.assertEqual(lf_artifact.data, crlf_artifact.data)

    def test_setup_uses_immutable_runtime_and_doctor_verifies_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            project = root / "project"
            codex.mkdir()
            project.mkdir()
            identity = ProjectIdentity(
                cwd=str(project),
                repo_root=str(project),
                branch="main",
                scope_key=str(project.resolve()),
            )
            fake_skill = SkillPlan(
                path=root / "skills" / "agent-memory",
                action="noop",
                canonical_sha256="a" * 64,
                installed_sha256="a" * 64,
            )
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.codex_integration.plan_skill_install",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.install_skill",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.installed_skill_sha256",
                    return_value="a" * 64,
                ),
            ):
                preview = setup(apply=False, identity=identity)
                self.assertEqual(preview["status"], "ready")
                applied = setup(apply=True, identity=identity)
                self.assertEqual(applied["status"], "ok")
                runtime = Path(
                    applied["runtime"]["artifact_path"]
                )
                self.assertTrue(runtime.exists())
                self.assertEqual(runtime.suffix, ".pyz")
                hooks = json.loads(
                    (codex / "hooks.json").read_text(encoding="utf-8")
                )
                command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0][
                    "commandWindows"
                ]
                self.assertIn(str(runtime), command)
                self.assertNotIn("-m agent_memory_sidecar.runtime_hook", command)
                self.assertEqual(doctor(identity=identity)["status"], "ok")

    def test_setup_self_test_failure_does_not_activate_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            project = root / "project"
            codex.mkdir()
            project.mkdir()
            hooks_path = codex / "hooks.json"
            original_hooks = b'{"hooks":{"PostToolUse":[]}}\n'
            hooks_path.write_bytes(original_hooks)
            identity = ProjectIdentity(
                cwd=str(project),
                repo_root=str(project),
                branch="main",
                scope_key=str(project.resolve()),
            )
            fake_skill = SkillPlan(
                path=root / "skills" / "agent-memory",
                action="noop",
                canonical_sha256="a" * 64,
                installed_sha256="a" * 64,
            )
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.codex_integration.plan_skill_install",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.self_test_artifact",
                    side_effect=CoreError(
                        "runtime_artifact_self_test_failed",
                        "injected runtime policy failure",
                    ),
                ),
            ):
                with self.assertRaises(CoreError) as raised:
                    setup(apply=True, identity=identity)
            self.assertEqual(
                raised.exception.code,
                "runtime_artifact_self_test_failed",
            )
            self.assertEqual(hooks_path.read_bytes(), original_hooks)
            self.assertFalse(
                (
                    codex
                    / "agent-memory-sidecar"
                    / "memory.sqlite"
                ).exists()
            )

    def test_hook_generation_preserves_unrelated_entries(self) -> None:
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "other-tool",
                                "commandWindows": "other-tool.exe",
                            }
                        ]
                    }
                ],
                "PostCompact": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python -m agent_memory_sidecar.runtime_hook",
                                "commandWindows": "python -m agent_memory_sidecar.runtime_hook",
                            }
                        ]
                    }
                ],
            }
        }
        commands = runtime_commands(artifact_path=Path("runtime.pyz"))
        desired = desired_hooks_document(
            existing=existing,
            commands=commands,
        )
        user_entries = desired["hooks"]["UserPromptSubmit"]
        self.assertEqual(user_entries[0], existing["hooks"]["UserPromptSubmit"][0])
        self.assertEqual(len(user_entries), 2)
        self.assertNotIn("PostCompact", desired["hooks"])

    def test_setup_failure_restores_existing_registry_and_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            project = root / "project"
            codex.mkdir()
            project.mkdir()
            identity = ProjectIdentity(
                cwd=str(project),
                repo_root=str(project),
                branch="main",
                scope_key=str(project.resolve()),
            )
            fake_skill = SkillPlan(
                path=root / "skills" / "agent-memory",
                action="noop",
                canonical_sha256="a" * 64,
                installed_sha256="a" * 64,
            )
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.codex_integration.plan_skill_install",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.install_skill",
                    return_value=fake_skill,
                ),
                patch(
                    "agent_memory_sidecar.codex_integration.installed_skill_sha256",
                    return_value="a" * 64,
                ),
            ):
                setup(apply=True, identity=identity)
                store = codex / "agent-memory-sidecar" / "memory.sqlite"
                with CoreDatabase(store) as db:
                    before = {
                        table: dict(
                            db.conn.execute(
                                f"SELECT * FROM {table}"
                            ).fetchone()
                        )
                        for table in (
                            "runtime_installation",
                            "global_instruction_binding",
                        )
                        if db.conn.execute(
                            f"SELECT 1 FROM {table}"
                        ).fetchone()
                        is not None
                    }
                hook_bytes = (codex / "hooks.json").read_bytes()
                with patch(
                    "agent_memory_sidecar.codex_integration.doctor",
                    return_value={
                        "status": "error",
                        "errors": [{"code": "injected"}],
                    },
                ):
                    with self.assertRaises(CoreError):
                        setup(apply=True, identity=identity)
                with CoreDatabase(store) as db:
                    after = {
                        table: dict(
                            db.conn.execute(
                                f"SELECT * FROM {table}"
                            ).fetchone()
                        )
                        for table in (
                            "runtime_installation",
                            "global_instruction_binding",
                        )
                        if db.conn.execute(
                            f"SELECT 1 FROM {table}"
                        ).fetchone()
                        is not None
                    }
                self.assertEqual(after, before)
                self.assertEqual(
                    (codex / "hooks.json").read_bytes(),
                    hook_bytes,
                )

    def test_bound_global_source_can_advance_without_overwriting_local_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            source = root / "source"
            (source / "global").mkdir(parents=True)
            codex.mkdir()
            old = b"# old\n"
            new = b"# new\n"
            (codex / "AGENTS.md").write_bytes(old)
            (source / "global" / "AGENTS.md").write_bytes(new)
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch="main",
                scope_key=str(root.resolve()),
            )
            binding = {
                "source_root": str(source),
                "target_file_sha256": "sha256:"
                + hashlib.sha256(old).hexdigest(),
            }
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.codex_integration._git_identity",
                    return_value=("f" * 40, True),
                ),
            ):
                plan = _global_materialization_plan(
                    identity=identity,
                    source_root=source,
                    existing_binding=binding,
                )
            self.assertIsNotNone(plan)
            self.assertTrue(plan["materialize"])

    def test_explicit_global_source_rebind_preserves_drift_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            old_source = root / "old-source"
            new_source = root / "new-source"
            (old_source / "global").mkdir(parents=True)
            (new_source / "global").mkdir(parents=True)
            codex.mkdir()
            old = b"# old\n"
            new = b"# new\n"
            (codex / "AGENTS.md").write_bytes(old)
            (old_source / "global" / "AGENTS.md").write_bytes(old)
            (new_source / "global" / "AGENTS.md").write_bytes(new)
            identity = ProjectIdentity(
                cwd=str(root),
                repo_root=str(root),
                branch="main",
                scope_key=str(root.resolve()),
            )
            binding = {
                "source_root": str(old_source),
                "target_file_sha256": "sha256:"
                + hashlib.sha256(old).hexdigest(),
            }
            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
                patch(
                    "agent_memory_sidecar.codex_integration._git_identity",
                    return_value=("f" * 40, True),
                ),
            ):
                plan = _global_materialization_plan(
                    identity=identity,
                    source_root=new_source,
                    existing_binding=binding,
                    allow_source_rebind=True,
                )
                (codex / "AGENTS.md").write_bytes(b"# user drift\n")
                with self.assertRaisesRegex(
                    CoreError,
                    "local global target changed after the last binding",
                ):
                    _global_materialization_plan(
                        identity=identity,
                        source_root=new_source,
                        existing_binding=binding,
                        allow_source_rebind=True,
                    )
            self.assertIsNotNone(plan)
            self.assertTrue(plan["materialize"])
            self.assertEqual(str(new_source), plan["source_root"])

    def test_generated_skill_only_uses_core_v1_commands(self) -> None:
        skill = build_skill_files()["SKILL.md"]
        self.assertIn("agent-memory rule deploy", skill)
        self.assertIn("agent-memory rule deploy-bundle", skill)
        self.assertIn("agent-memory rule list --target", skill)
        self.assertIn("The bundle succeeds completely or changes no Owner bytes", skill)
        self.assertIn("agent-memory proposal confirm", skill)
        self.assertIn("already_covered", skill)
        self.assertIn("consolidate", skill)
        self.assertIn("[--supersedes <rule-id>]...", skill)
        self.assertNotIn("agent-memory remember", skill)
        self.assertNotIn("agent-memory suggestion", skill)

    def test_ambient_capability_requires_a_terminal_artifact_within_budget(self) -> None:
        capability = build_ambient_capability("evt_" + "a" * 32)
        self.assertLessEqual(
            len(capability.encode("utf-8")),
            MAX_AMBIENT_CAPABILITY_BYTES,
        )
        self.assertIn("explicit remember or memory audit", capability)
        self.assertIn("final reply must end with one real", capability)
        self.assertIn("future-tense promises do not count", capability)

    def test_generated_skill_enforces_conditional_visible_terminal_outcomes(self) -> None:
        skill = build_skill_files()["SKILL.md"]
        self.assertIn("## Task boundary and visibility", skill)
        self.assertIn("## Terminal outcomes", skill)
        self.assertIn("an explicit audit of whether memory triggered", skill)
        self.assertIn("Commentary, capability delivery", skill)
        self.assertIn("do not silently exit after `rule list`", skill)
        self.assertIn(
            "记忆检查：已完成｜结论：没有合格的可复用规则｜动作：未创建建议｜长期状态：未变更",
            skill,
        )
        self.assertIn(
            "记忆检查：已完成｜结论：当前规则已经覆盖｜动作：未创建建议｜长期状态：未变更",
            skill,
        )
        self.assertIn(
            "记忆检查：已完成｜结论：内容应归入{正式 owner}｜动作：未创建长期规则｜长期状态：未变更",
            skill,
        )
        self.assertIn(
            "记忆检查：执行失败｜结论：{已证明事实}｜动作：未保存｜长期状态：未变更",
            skill,
        )
        self.assertLess(
            skill.index("agent-memory proposal create"),
            skill.index("**记忆建议**"),
        )
        self.assertIn("do not ask twice", skill)
        self.assertNotIn(
            "For explicit remember, say it is already covered; otherwise remain silent",
            skill,
        )

    def test_skill_install_recovers_an_interrupted_previous_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "agent-memory"
            target.mkdir()
            (target / "old.txt").write_text("old", encoding="utf-8")
            backup = root / ".agent-memory.previous"
            os.replace(target, backup)
            result = install_skill(root=root)
            self.assertEqual(result.action, "noop")
            self.assertFalse(backup.exists())
            self.assertEqual(
                installed_skill_sha256(target),
                skill_package_sha256(),
            )

    def test_skill_install_rejects_ancestor_directory_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = root / "physical"
            target_root = physical / "existing"
            target_root.mkdir(parents=True)
            alias = root / "alias"
            try:
                alias.symlink_to(physical, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symbolic links unavailable: {exc}")
            with self.assertRaises(CoreError) as raised:
                install_skill(root=alias / "existing")
            self.assertEqual("skill_target_unsafe", raised.exception.code)
            self.assertFalse((target_root / "agent-memory").exists())
