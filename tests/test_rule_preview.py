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
from agent_memory_sidecar.instructions import ConfirmedRule, managed_block_bytes, render_rule
from agent_memory_sidecar.proposal import RuleBundle, RuleProposal, review_selection_token
from agent_memory_sidecar.rule_preview import preview_bundle, preview_rule
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

    def test_single_and_block_overflow_are_reported_together(self) -> None:
        entries = [(proposal(i, length=600), []) for i in range(12)]
        entries.append(({**proposal(12), "action": "保留条件和例外😀" * 80}, []))
        result = preview_bundle(bundle=bundle_for(self.target, entries), target_file=self.target)
        self.assertEqual(result["contract_version"], "rule_bundle_preview_v2")
        combined = result["combined"]
        self.assertEqual(combined["status"], "blocked")
        self.assertIsNone(combined["target_after_sha256"])
        capacity = combined["capacity"]
        self.assertEqual(len(capacity["rules"]), 13)
        self.assertEqual(sum(item["exceeded"] for item in capacity["rules"]), 1)
        self.assertTrue(capacity["managed_block"]["exceeded"])
        self.assertEqual(combined["projected_bytes"], capacity["managed_block"]["projected_bytes"])
        oversized = next(item for item in capacity["rules"] if item["exceeded"])
        self.assertEqual(result["items"][-1]["capacity"]["rules"][0], oversized)
        self.assertFalse(result["items"][-1]["capacity"]["managed_block"]["exceeded"])
        self.assertEqual(self.target.read_bytes(), b"# User owned guidance\r\n")

    def test_scalar_cli_and_runtime_return_same_read_only_capacity_receipt(self) -> None:
        previous = tuple(ConfirmedRule.from_proposal(RuleProposal.from_payload(proposal(i))) for i in (2, 3))
        self.target.write_bytes(b"# User owned guidance\r\n\r\n" + managed_block_bytes(previous, newline="\r\n"))
        supersedes = [rule.rule_id for rule in previous]
        artifact = build_runtime_artifact()
        runtime = self.root / artifact.file_name
        runtime.write_bytes(artifact.data)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONIOENCODING": "ascii", "CODEX_HOME": str(self.root / "absent-home")}
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for action, status in (("保留例外😀", "ready"), ("保留例外😀" * 200, "blocked")):
            payload = {**proposal(1), "action": action}
            receipts = []
            for command in (
                [sys.executable, "-B", "-X", "utf8=0", "-m", "agent_memory_sidecar", "rule", "preview", "--from-json", "-"],
                [sys.executable, "-I", "-B", "-X", "utf8=0", str(runtime), "preview"],
            ):
                selection = [arg for rule_id in supersedes for arg in ("--supersedes", rule_id)]
                result = subprocess.run(command + ["--target-file", str(self.target)] + selection,
                    input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root)
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                value = json.loads(result.stdout)
                receipts.append(value.get("data", value))
            self.assertEqual(receipts[0], receipts[1])
            receipt = receipts[0]
            self.assertEqual(receipt["contract_version"], "rule_preview_v1")
            self.assertEqual(receipt["status"], status)
            self.assertEqual(receipt["target_before_sha256"], hashlib.sha256(self.target.read_bytes()).hexdigest())
            self.assertEqual(receipt["supersedes"], sorted(supersedes))
            self.assertEqual(receipt["proposal_sha256"], RuleProposal.from_payload(payload).proposal_sha256)
            self.assertEqual(receipt["capacity"]["rules"][0]["exceeded"], status == "blocked")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertFalse((self.root / "absent-home").exists())

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

    def test_unicode_rule_boundary_is_normalized_lf_for_both_newlines(self) -> None:
        payload = {**proposal(0), "action": "中文😀"}
        base = ConfirmedRule.from_proposal(RuleProposal.from_payload(payload))
        payload["action"] += "x" * (1024 - len(render_rule(base, newline="\n").encode("utf-8")))
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline):
                self.target.write_bytes(("# Guidance" + newline).encode())
                before = self.target.read_bytes()
                result = preview_rule(proposal=RuleProposal.from_payload(payload), target_file=self.target)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["capacity"]["rules"][0]["actual_bytes"], 1024)
                rule = ConfirmedRule.from_proposal(RuleProposal.from_payload(payload))
                self.assertEqual(result["projected_bytes"], len(managed_block_bytes((rule,), newline=newline)))
                over = preview_rule(proposal=RuleProposal.from_payload({**payload, "action": payload["action"] + "x"}), target_file=self.target)
                self.assertEqual(over["status"], "blocked")
                self.assertEqual(over["capacity"]["rules"][0]["actual_bytes"], 1025)
                self.assertFalse(over["capacity"]["managed_block"]["exceeded"])
                self.assertIsNone(over["target_after_sha256"])
                self.assertEqual(self.target.read_bytes(), before)

    def test_exact_block_boundary_uses_physical_newlines_and_excludes_outside(self) -> None:
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline):
                payloads = [{**proposal(i), "action": "x"} for i in range(8)]
                rules = [ConfirmedRule.from_proposal(RuleProposal.from_payload(p)) for p in payloads]
                remaining = 8192 - len(managed_block_bytes(tuple(rules), newline=newline))
                for index, rule in enumerate(rules):
                    extra = min(remaining, 1024 - len(render_rule(rule, newline="\n").encode("utf-8")))
                    payloads[index]["action"] += "x" * extra
                    rules[index] = ConfirmedRule.from_proposal(RuleProposal.from_payload(payloads[index]))
                    remaining -= extra
                self.assertEqual(remaining, 0)
                outside = ("# " + "z" * 40000 + newline * 2).encode()
                before = outside + managed_block_bytes(tuple(rules[:-1]), newline=newline)
                self.target.write_bytes(before)
                result = preview_rule(proposal=RuleProposal.from_payload(payloads[-1]), target_file=self.target)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["projected_bytes"], 8192)
                expected_after = outside + managed_block_bytes(tuple(rules), newline=newline)
                self.assertEqual(result["target_after_sha256"], hashlib.sha256(expected_after).hexdigest())
                over = {**payloads[-1], "action": payloads[-1]["action"] + "x"}
                rejected = preview_rule(proposal=RuleProposal.from_payload(over), target_file=self.target)
                self.assertEqual(rejected["status"], "blocked")
                self.assertEqual(rejected["projected_bytes"], 8193)
                self.assertTrue(all(not item["exceeded"] for item in rejected["capacity"]["rules"]))
                self.assertEqual(self.target.read_bytes(), before)

    def test_scalar_missing_supersedes_and_override_cannot_claim_ready(self) -> None:
        candidate = RuleProposal.from_payload(proposal(0))
        result = preview_rule(proposal=candidate, target_file=self.target, supersedes=["rule_" + "a" * 12])
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["capacity"])
        self.assertIsNone(result["target_after_sha256"])
        override = self.root / "AGENTS.override.md"
        override.write_text("# Authoritative override\n", encoding="utf-8")
        result = preview_rule(proposal=candidate, target_file=self.target)
        self.assertEqual(result["error_code"], "instruction_target_shadowed")
        self.assertIsNone(result["capacity"])
        absent = self.root / "absent" / "AGENTS.md"
        self.assertEqual(preview_rule(proposal=candidate, target_file=absent)["status"], "ready")
        self.assertFalse(absent.parent.exists())

    def test_scout_v2_rejects_inconsistent_capacity_and_accepts_legacy_receipt(self) -> None:
        codex_home = self.install_fixture()
        pack = self.preparer.prepare_review(self.draft(codex_home, count=1), codex_home=codex_home)
        self.validator.validate_selection_preview(pack, required=True)
        for mutation in ("rule_over", "false_flag", "missing", "block_mismatch"):
            invalid = json.loads(json.dumps(pack))
            capacity = invalid["selection_preview"]["result"]["combined"]["capacity"]
            if mutation in {"rule_over", "false_flag"}:
                capacity["rules"][0]["actual_bytes"] = capacity["rules"][0]["budget_bytes"] + 1
                capacity["rules"][0]["exceeded"] = mutation == "rule_over"
            elif mutation == "missing":
                invalid["selection_preview"]["result"]["combined"]["capacity"] = None
            else:
                capacity["managed_block"]["projected_bytes"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(self.validator.ContractError):
                self.validator.validate_selection_preview(invalid, required=True)
        legacy = json.loads(json.dumps(pack))
        result = legacy["selection_preview"]["result"]
        result["contract_version"] = "rule_bundle_preview_v1"
        for item in [*result["items"], result["combined"]]:
            del item["capacity"]
        self.validator.validate_selection_preview(legacy, required=True)

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

    def draft(self, codex_home: Path, *, count: int = 41, rule_length: int = 600) -> dict:
        project = self.validator.valid_project(card_count=count)
        for index, card in enumerate(project["project_cards"]):
            card["rule_payload"].update(proposal(index, length=rule_length))
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

    def test_scout_render_distinguishes_rule_block_and_combined_capacity_failures(self) -> None:
        codex_home = self.install_fixture()
        for count, length, rule_over, block_over in ((1, 1100, True, False), (12, 600, False, True), (8, 1100, True, True)):
            with self.subTest(count=count, length=length):
                pack = self.preparer.prepare_review(self.draft(codex_home, count=count, rule_length=length), codex_home=codex_home)
                combined = pack["selection_preview"]["result"]["combined"]
                self.assertEqual(combined["error_code"], "instruction_capacity_exceeded")
                rendered = self.renderer.render_review_pack(pack, surface="interactive")
                self.assertEqual("超过单条预算" in rendered, rule_over)
                self.assertEqual("超过整块预算" in rendered, block_over)
                self.assertNotIn("**一次确认命令**", rendered)
                self.assertEqual(self.visible.verify_visible_output(rendered, surface="interactive")["visible_cards"], count)
                capacity = combined["capacity"]
                self.assertIn(str(capacity["managed_block"]["projected_bytes"]), rendered)
                if rule_over:
                    self.assertIn(str(max(item["actual_bytes"] for item in capacity["rules"])), rendered)
                legacy = json.loads(json.dumps(pack))
                result = legacy["selection_preview"]["result"]
                result["contract_version"] = "rule_bundle_preview_v1"
                for item in [*result["items"], result["combined"]]:
                    del item["capacity"]
                    if rule_over:
                        item["projected_bytes"] = None
                legacy["review_pack_hash"] = self.validator.review_pack_hash(legacy)
                rendered_legacy = self.renderer.render_review_pack(legacy, surface="interactive")
                self.assertNotIn("超过单条预算", rendered_legacy)
                self.assertEqual("超过整块预算" in rendered_legacy, block_over and not rule_over)
                self.assertEqual(self.visible.verify_visible_output(rendered_legacy, surface="interactive")["visible_cards"], count)

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
