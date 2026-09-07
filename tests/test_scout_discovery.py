from __future__ import annotations

import copy
import importlib.util
import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / ".agents/skills/global-owner-scout/scripts"


class ScoutDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            spec = importlib.util.spec_from_file_location("discovery_validator", SCRIPTS / "validate_output.py")
            cls.validator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.validator)
        finally:
            sys.path.pop(0)

    def test_empty_discovery_cannot_prove_no_delta(self) -> None:
        v = self.validator
        for coverage in ("complete", "bounded"):
            with self.subTest(coverage=coverage):
                project = v.valid_project(status="no_material_delta", coverage=coverage)
                project["events"] = []
                project["observations"] = []
                project["evidence_sources"] = [s for s in project["evidence_sources"] if s["kind"] == "sessions"]
                with self.assertRaises(v.ContractError):
                    v.validate_review_pack(v.valid_review_pack(project))

    def test_event_cannot_disappear_before_card_freeze(self) -> None:
        v = self.validator
        project = v.valid_project()
        project["events"].append({
            "event_id": "event:omitted", "order": len(project["events"]) + 1,
            "summary": "正式验收已经记录重要经验。", "before_belief": "之前推断完成。",
            "observed_change": "真实结果与推断不同。", "accepted_result": "修订已正式接受。",
            "direct_evidence": copy.deepcopy(project["project_cards"][0]["direct_evidence"]),
        })
        with self.assertRaises(v.ContractError):
            v.validate_project(project)

    def test_card_cannot_cite_undeclared_evidence(self) -> None:
        v = self.validator
        project = v.valid_project()
        card = project["project_cards"][0]
        card["direct_evidence"][0]["ref"] = "source:not-read"
        card["normalized_evidence_hash"] = v.canonical_hash(card["direct_evidence"])
        card["project_claim_hash"] = v.project_claim_hash(card)
        with self.assertRaises(v.ContractError):
            v.validate_project(project)

    def test_no_delta_needs_observations_even_with_all_sources(self) -> None:
        v = self.validator
        project = v.valid_project(status="no_material_delta")
        v.validate_project(project)
        project["events"] = []
        project["observations"] = []
        with self.assertRaisesRegex(v.ContractError, "evidenced observations"):
            v.validate_project(project)

    def test_existing_owner_exclusion_requires_exact_evidence(self) -> None:
        v = self.validator
        project = v.valid_project(status="no_material_delta")
        observation = project["observations"][0]
        observation["evidence_level"] = "E2"
        observation["disposition"]["kind"] = "already_covered"
        with self.assertRaisesRegex(v.ContractError, "exact Owner refs"):
            v.validate_project(project)
        owner = next(s for s in project["evidence_sources"] if s["kind"] == "owners")["refs"][0]
        observation["disposition"]["owner_refs"] = [owner["ref"]]
        with self.assertRaisesRegex(v.ContractError, "Owner evidence"):
            v.validate_project(project)
        observation["direct_evidence"].append(copy.deepcopy(owner))
        observation["disposition"]["portable_delta"] = "该行为的触发、动作与例外均已由具名 Owner 覆盖，没有独立增量。"
        v.validate_project(project)

    def test_missing_project_sources_degrade_without_losing_supported_cards(self) -> None:
        v = self.validator
        project = v.valid_project()
        source = next(s for s in project["evidence_sources"] if s["kind"] == "failures")
        source.update(status="unavailable", refs=[], uncovered=["失败记录暂时无法读取。"])
        with self.assertRaisesRegex(v.ContractError, "require degraded"):
            v.validate_project(project)
        project["status"] = "degraded"
        project["limitations"] = ["失败记录缺失，其余验收独立支持当前卡片。"]
        v.validate_review_pack(v.valid_review_pack(project))
        self.assertEqual(2, len(project["project_cards"]))

    def test_cards_require_a_unique_disposition_and_bound_evidence_hash(self) -> None:
        v = self.validator
        project = v.valid_project()
        project["observations"].pop()
        with self.assertRaisesRegex(v.ContractError, "every (card|event)"):
            v.validate_project(project)
        project = v.valid_project()
        card = project["project_cards"][0]
        card["direct_evidence"][0]["summary"] = "改变了原有证据摘要。"
        card["project_claim_hash"] = v.project_claim_hash(card)
        with self.assertRaisesRegex(v.ContractError, "normalized_evidence_hash mismatch"):
            v.validate_project(project)

    def test_output_preflight_is_path_free_and_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, output = root / "project", root / "output"
            project.mkdir()
            output.mkdir()
            for target, expected in ((output, 0), (project, 1), (root / "missing", 1)):
                result = subprocess.run(
                    [sys.executable, "-B", str(SCRIPTS / "scout.py"), "inspect-output", "--artifact-dir", str(target),
                     "--protected-root", str(project)], capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(expected, result.returncode)
                self.assertNotIn(str(root), result.stdout + result.stderr)
                if expected == 0:
                    self.assertFalse(json.loads(result.stdout)["writes_performed"])
                else:
                    self.assertEqual("output_preflight_unavailable", json.loads(result.stderr)["message"])
            self.assertEqual([], list(output.iterdir()))
            self.assertEqual([], list(project.iterdir()))

    def test_candidate_evidence_must_flow_through_linked_events(self) -> None:
        v = self.validator
        project = v.valid_project()
        for observation in project["observations"]:
            if observation["disposition"]["kind"] == "candidate":
                observation["event_ids"] = []
        project["events"] = project["events"][:1]
        with self.assertRaisesRegex(v.ContractError, "candidate requires linked events"):
            v.validate_project(project)
        project = v.valid_project()
        project["events"] = project["events"][:1]
        for observation in project["observations"][1:]:
            observation["event_ids"] = [project["events"][0]["event_id"]]
            observation["direct_evidence"] += copy.deepcopy(project["events"][0]["direct_evidence"])
        with self.assertRaisesRegex(v.ContractError, "card evidence bypasses linked events"):
            v.validate_project(project)

    def test_evidence_identity_cannot_change_between_source_and_card(self) -> None:
        v = self.validator
        project = v.valid_project()
        card = project["project_cards"][0]
        card["direct_evidence"][0].update(type="failure", summary="与源记录不同的结论。")
        card["normalized_evidence_hash"] = v.canonical_hash(card["direct_evidence"])
        card["project_claim_hash"] = v.project_claim_hash(card)
        with self.assertRaisesRegex(v.ContractError, "evidence differs from declared source"):
            v.validate_project(project)

    def test_session_degradation_requires_independent_card_evidence(self) -> None:
        v = self.validator
        project = v.valid_project(thread_pages_terminal_failure=True)
        for source in project["evidence_sources"]:
            if source["kind"] == "acceptance":
                accepted = source["refs"].pop()
        next(s for s in project["evidence_sources"] if s["kind"] == "sessions")["refs"].append(accepted)
        with self.assertRaisesRegex(v.ContractError, "non-Session evidence"):
            v.validate_project(project)

    def test_nested_discriminators_return_contract_error_through_cli(self) -> None:
        for field in ("evidence_level", "disposition"):
            with self.subTest(field=field):
                project = self.validator.valid_project()
                if field == "disposition":
                    project["observations"][0][field]["kind"] = []
                else:
                    project["observations"][0][field] = []
                result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "scout.py"), "validate-project"],
                                        input=json.dumps(project), capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(1, result.returncode)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIsInstance(json.loads(result.stderr), dict)

    def test_long_logical_owner_refs_are_not_misclassified_as_english_prose(self) -> None:
        v = self.validator
        project = v.valid_project(status="no_material_delta")
        owner = next(s for s in project["evidence_sources"] if s["kind"] == "owners")["refs"][0]
        owner["ref"] = "owner:0079-project-session-front-door-and-scout-terminal-contract"
        observation = project["observations"][0]
        observation["direct_evidence"].append(copy.deepcopy(owner))
        observation["disposition"].update(kind="already_covered", owner_refs=[owner["ref"]])
        v.validate_review_pack(v.valid_review_pack(project))

    def render_via_dispatcher(self, pack: dict, surface: str = "interactive") -> str:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "scout.py"), "render-review", "--surface", surface],
            input=json.dumps(pack), capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def test_decisions_and_scope_are_available_before_technical_evidence(self) -> None:
        v = self.validator
        pack = v.valid_review_pack()
        rendered = self.render_via_dispatcher(pack)
        front = rendered.split("## 决策卡 ", 1)[0]
        self.assertIn("本次规则变更**：无", front)
        self.assertNotIn("Owner parity", front)
        for ordinal, card in enumerate(pack["project_result"]["project_cards"], start=1):
            block = rendered.split(f"## 决策卡 {ordinal}：", 1)[1].split("## 决策卡 ", 1)[0]
            decision = block.split("### 完整核对依据", 1)[0]
            self.assertIn("建议范围", decision)
            self.assertIn(f"忽略 {card['card_id']}", decision)
            self.assertIn(f"修改 {card['card_id']}", decision)
            self.assertIn("| 接受前 | 接受后 |", decision)

    def test_blocked_confirmation_is_explained_without_protocol_terms(self) -> None:
        v = self.validator
        pack = v.valid_review_pack(v.valid_project(status="degraded", coverage="degraded"), parity_status="unavailable")
        rendered = self.render_via_dispatcher(pack)
        front = rendered.split("## 决策卡 ", 1)[0]
        self.assertIn("暂不能确认", front)
        self.assertNotIn("degraded", front)
        self.assertNotIn("canonical", front)
        self.assertNotIn("- `确认 ", rendered)
        self.assertEqual(len(pack["review_cards"]), rendered.count("## 决策卡 "))

    def test_scheduled_no_delta_does_not_claim_complete_project_census(self) -> None:
        v = self.validator
        pack = v.valid_review_pack(v.valid_project(status="no_material_delta", coverage="bounded", window_kind="rolling_72h"))
        rendered = self.render_via_dispatcher(pack, "scheduled")
        wrapper = rendered.split("::inbox-item", 1)[1]
        self.assertIn("已核查范围", wrapper)
        self.assertIn("未覆盖", wrapper)
        self.assertNotIn("事实普查已完成", wrapper)


if __name__ == "__main__":
    unittest.main()
