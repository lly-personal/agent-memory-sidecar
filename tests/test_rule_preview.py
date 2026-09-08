from __future__ import annotations

import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.instructions import ConfirmedRule, managed_block_bytes
from agent_memory_sidecar.proposal import RuleBundle, RuleProposal, review_selection_token
from agent_memory_sidecar.rule_preview import preview_bundle
from agent_memory_sidecar.runtime_package import build_runtime_artifact


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/global-owner-scout/scripts"


def bundle_for(target: Path, entries: list[tuple[dict, list[str]]]) -> RuleBundle:
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    items = []
    for index, (payload, supersedes) in enumerate(entries):
        card_id = f"card-{index:02d}"
        proposal = RuleProposal.from_payload(payload)
        items.append({
            "card_id": card_id, "project_claim_hash": "a" * 64, "proposal": payload, "supersedes": supersedes,
            "selection_token": review_selection_token(card_id=card_id, project_claim_hash="a" * 64,
                proposal=proposal, supersedes=tuple(supersedes), instruction_target="global_agents", target_before_sha256=before),
        })
    return RuleBundle.from_payload({"contract_version": "rule_revision_bundle_v2", "target_before_sha256": before, "items": items})


def proposal(index: int, *, length: int = 30) -> dict:
    return {"trigger": f"When scenario {index} occurs.", "action": "Follow the agreed behavior. " + "x" * length,
            "skip_boundary": "Skip outside that scenario.", "scope": "global", "instruction_target": "global_agents",
            "why": "Preserve the agreed behavior.", "evidence": "A synthetic acceptance fixture."}


class RulePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            cls.validator = importlib.import_module("validate_output")
            cls.preparer = importlib.import_module("prepare_review")
            cls.resolver = importlib.import_module("resolve_owner_parity")
            cls.renderer = importlib.import_module("render_review")
            cls.visible = importlib.import_module("verify_visible_output")
        finally:
            sys.path.pop(0)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "AGENTS.md"
        self.target.write_bytes(b"# User owned guidance\r\n")

    def test_cli_and_immutable_runtime_preview_without_store_or_file_mutation(self) -> None:
        chinese = {**proposal(1), "trigger": "当用户请求复盘时。", "action": "保留已证结果与准确例外。", "skip_boundary": "不适用于没有复盘要求的任务。"}
        bundle = bundle_for(self.target, [(chinese, []), (proposal(2), [])])
        artifact = build_runtime_artifact()
        runtime = self.root / artifact.file_name
        runtime.write_bytes(artifact.data)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        expected = preview_bundle(bundle=bundle, target_file=self.target)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "ascii", "CODEX_HOME": str(self.root / "absent-home")}
        commands = [
            [sys.executable, "-B", "-X", "utf8=0", "-m", "agent_memory_sidecar", "rule", "preview-bundle", "--from-json", "-"],
            [sys.executable, "-I", "-B", "-X", "utf8=0", str(runtime), "preview-bundle"],
        ]
        for command in commands:
            result = subprocess.run(command + ["--target-file", str(self.target)], input=json.dumps(bundle.to_dict(), ensure_ascii=False),
                capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            observed = json.loads(result.stdout)
            self.assertEqual(observed.get("data", observed), expected)
            selected = subprocess.run(command + ["--target-file", str(self.target), "--select-card", "card-00"],
                input=json.dumps(bundle.to_dict(), ensure_ascii=False), capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            selected_value = json.loads(selected.stdout)
            self.assertEqual(selected_value.get("data", selected_value), preview_bundle(bundle=bundle, target_file=self.target, selected_card_ids=["card-00"]))
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertFalse((self.root / "absent-home").exists())

    def test_aggregate_capacity_failure_preserves_each_valid_projection(self) -> None:
        bundle = bundle_for(self.target, [(proposal(i, length=600), []) for i in range(41)])
        result = preview_bundle(bundle=bundle, target_file=self.target)
        self.assertEqual(len(result["items"]), 41)
        self.assertTrue(all(item["status"] == "ready" for item in result["items"]))
        self.assertEqual(result["combined"]["error_code"], "instruction_capacity_exceeded")
        self.assertGreater(result["combined"]["projected_bytes"], result["budget_bytes"])
        self.assertEqual(self.target.read_bytes(), b"# User owned guidance\r\n")

    def test_actual_before_change_and_overlap_are_rejected(self) -> None:
        old = ConfirmedRule.from_proposal(RuleProposal.from_payload(proposal(0)))
        self.target.write_bytes(managed_block_bytes((old,), newline="\n"))
        bundle = bundle_for(self.target, [(proposal(1), [old.rule_id]), (proposal(2), [old.rule_id])])
        result = preview_bundle(bundle=bundle, target_file=self.target)
        self.assertTrue(all(item["status"] == "ready" for item in result["items"]))
        self.assertEqual(result["combined"]["status"], "blocked")
        self.target.write_bytes(self.target.read_bytes() + b"\nChanged outside text\n")
        with self.assertRaises(CoreError) as caught:
            preview_bundle(bundle=bundle, target_file=self.target)
        self.assertEqual(caught.exception.code, "rule_revision_stale")

    def install_fixture(self) -> Path:
        codex_home = self.root / "codex-home"
        store = codex_home / "agent-memory-sidecar/memory.sqlite"
        store.parent.mkdir(parents=True)
        owner_root = self.root / "owner"
        (owner_root / "global").mkdir(parents=True)
        for target in (codex_home / "AGENTS.md", owner_root / "global/AGENTS.md"):
            target.write_bytes(self.target.read_bytes())
        artifact = build_runtime_artifact()
        runtime = self.root / artifact.file_name
        runtime.write_bytes(artifact.data)
        db = sqlite3.connect(store)
        try:
            db.execute("CREATE TABLE global_instruction_binding (singleton INTEGER PRIMARY KEY, binding_version TEXT, source_root TEXT)")
            db.execute("INSERT INTO global_instruction_binding VALUES (1, ?, ?)", (self.resolver.BINDING_VERSION, str(owner_root)))
            db.execute("CREATE TABLE runtime_installation (singleton INTEGER PRIMARY KEY, identity_version TEXT, artifact_path TEXT, artifact_sha256 TEXT)")
            db.execute("INSERT INTO runtime_installation VALUES (1, ?, ?, ?)", ("runtime_installation_v1", str(runtime), "sha256:" + artifact.sha256))
            db.commit()
        finally:
            db.close()
        return codex_home

    def draft(self, codex_home: Path, *, count: int = 41) -> dict:
        project = self.validator.valid_project(card_count=count)
        for index, card in enumerate(project["project_cards"]):
            card["rule_payload"].update(proposal(index, length=600))
            card["project_claim_hash"] = self.validator.project_claim_hash(card)
        pack = self.validator.valid_review_pack(project)
        pack["owner_parity"] = self.resolver.resolve(codex_home)
        pack["selection_preview"] = None
        bundle = self.validator.review_bundle(pack)
        tokens = {item["card_id"]: item["selection_token"] for item in bundle["items"]}
        for card, review in zip(project["project_cards"], pack["review_cards"]):
            review["selection_token"] = tokens[card["card_id"]]
        pack["review_pack_hash"] = self.validator.review_pack_hash(pack)
        return pack

    def test_scout_installed_core_removes_infeasible_all_command_without_losing_cards(self) -> None:
        codex_home = self.install_fixture()
        draft = self.draft(codex_home)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        env = {**os.environ, "CODEX_HOME": str(codex_home), "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.run([sys.executable, "-B", str(SCRIPTS / "scout.py"), "prepare-review"],
            input=json.dumps(draft), capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root)
        self.assertEqual(process.returncode, 0, process.stderr)
        pack = json.loads(process.stdout)
        self.assertEqual(pack["project_result"], draft["project_result"])
        self.assertEqual(pack["selection_preview"]["result"]["combined"]["error_code"], "instruction_capacity_exceeded")
        rendered = self.renderer.render_review_pack(pack, surface="interactive")
        self.assertNotIn("**一次确认命令**", rendered)
        self.assertIn("组合需先整理", rendered)
        self.assertEqual(self.visible.verify_visible_output(rendered, surface="interactive")["visible_cards"], 41)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        chosen = [draft["project_result"]["project_cards"][i]["card_id"] for i in (0, 8)]
        selected = self.preparer.prepare_review(pack, codex_home=codex_home, selected_card_ids=chosen)
        self.assertEqual(selected["project_result"], draft["project_result"])
        self.assertEqual(selected["selection_preview"]["result"]["combined"]["card_ids"], sorted(chosen))
        self.assertEqual(selected["selection_preview"]["result"]["combined"]["status"], "ready")
        selected_render = self.renderer.render_review_pack(selected, surface="interactive")
        command = self.visible.BUNDLE_ACTION_RE.search(selected_render).group("ids")
        self.assertEqual({item.split("@")[0] for item in command.split("、")}, set(chosen))
        self.assertEqual(self.visible.verify_visible_output(selected_render, surface="interactive")["visible_cards"], 41)

    def test_missing_core_removes_confirmation_and_exact_global_coverage_overrides_project_add(self) -> None:
        codex_home = self.install_fixture()
        draft = self.draft(codex_home, count=1)
        for runtime in self.root.glob("*.pyz"):
            runtime.unlink()
        prepared = self.preparer.prepare_review(draft, codex_home=codex_home)
        self.assertNotIn("confirm", prepared["review_cards"][0]["allowed_actions"])
        self.assertIsNone(prepared["review_cards"][0]["selection_token"])
        review = draft["review_cards"][0]
        review["integration_preview"]["global_relation"] = "already_covered_exact"
        review["recommended_action"] = "ignore"
        review["allowed_actions"] = list(self.validator.READ_ONLY_ACTIONS)
        review["selection_token"] = None
        draft["review_pack_hash"] = self.validator.review_pack_hash(draft)
        prepared = self.preparer.prepare_review(draft, codex_home=codex_home)
        self.assertEqual(prepared["review_cards"][0]["recommended_action"], "ignore")
        self.assertEqual(prepared["project_result"]["project_cards"][0]["classification"], "add")
        self.assertIsNone(prepared["selection_preview"])

    def test_valid_combination_can_require_a_consolidation_before_an_addition(self) -> None:
        old = tuple(ConfirmedRule.from_proposal(RuleProposal.from_payload(proposal(i + 100, length=710))) for i in range(9))
        self.target.write_bytes(managed_block_bytes(old, newline="\n"))
        codex_home = self.install_fixture()
        draft = self.draft(codex_home, count=2)
        review = draft["review_cards"][1]
        review["integration_preview"]["global_relation"] = "consolidate"
        review["integration_preview"]["supersedes"] = sorted(rule.rule_id for rule in old[:2])
        bundle = self.validator.review_bundle(draft)
        tokens = {item["card_id"]: item["selection_token"] for item in bundle["items"]}
        for card, review in zip(draft["project_result"]["project_cards"], draft["review_cards"]):
            review["selection_token"] = tokens[card["card_id"]]
        draft["review_pack_hash"] = self.validator.review_pack_hash(draft)
        prepared = self.preparer.prepare_review(draft, codex_home=codex_home)
        result = prepared["selection_preview"]["result"]
        self.assertEqual(result["items"][0]["status"], "blocked")
        self.assertEqual(result["combined"]["status"], "ready")
        self.assertNotIn("confirm", prepared["review_cards"][0]["allowed_actions"])
        rendered = self.renderer.render_review_pack(prepared, surface="interactive")
        self.assertIn("**一次确认命令**", rendered)
        self.assertIn("**组合确认标识**", rendered)
        self.assertEqual(self.visible.verify_visible_output(rendered, surface="interactive")["bundle_action_count"], 1)


if __name__ == "__main__":
    unittest.main()
