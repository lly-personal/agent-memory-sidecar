from __future__ import annotations

import unittest
from pathlib import Path

from agent_memory_sidecar.database import CORE_TABLES


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_active_specs_describe_core_v1_and_no_legacy_public_cli(self) -> None:
        specs = "\n".join(
            (ROOT / "docs" / "specs" / name).read_text(encoding="utf-8")
            for name in ("axioms.md", "topology.md", "interface.md")
        )
        self.assertIn("Agent Memory Core v1", specs)
        self.assertIn("agent-memory rule deploy", specs)
        self.assertIn("agent-memory rule deploy-bundle", specs)
        self.assertIn("rule_revision_bundle_v2", specs)
        self.assertIn("一张或多张", specs)
        self.assertNotIn("agent-memory remember", specs)
        self.assertNotIn("agent-memory forget", specs)
        self.assertNotIn("禁止批量确认", specs)
        for table in CORE_TABLES:
            self.assertIn(f"`{table}`", specs)

    def test_retired_production_modules_are_absent(self) -> None:
        package = ROOT / "src" / "agent_memory_sidecar"
        for name in (
            "store.py",
            "release_evidence.py",
            "codex_rollout.py",
            "candidate_quality.py",
            "clean_store_rotation.py",
            "hook_probe.py",
            "skill_impact.py",
            "codex.py",
            "codex_host.py",
            "device_bootstrap.py",
            "hook_transport.py",
            "memory_payload.py",
            "portable_instructions.py",
            "session.py",
        ):
            self.assertFalse((package / name).exists(), name)

    def test_every_legacy_root_contract_is_explicitly_superseded(self) -> None:
        contract_root = ROOT / "specs"
        for path in contract_root.glob("*.md"):
            if path.name in {
                "README.md",
                "agent-memory-core-v1.md",
                "public-distribution-v1.md",
                "public-authority-cutover-v1.md",
            }:
                continue
            heading = "\n".join(
                path.read_text(encoding="utf-8").splitlines()[:5]
            )
            self.assertIn(
                "Current status: Superseded",
                heading,
                path.name,
            )

    def test_public_distribution_contract_is_active_and_fail_closed(self) -> None:
        contract = (ROOT / "specs" / "public-distribution-v1.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: Accepted", contract)
        self.assertIn("agent_memory_source_manifest_v1", contract)
        self.assertIn("public_export_blocked", contract)
        self.assertIn("canonical_owner=null", contract)

    def test_public_authority_cutover_contract_has_one_owner_per_epoch(self) -> None:
        contract = (ROOT / "specs" / "public-authority-cutover-v1.md").read_text(
            encoding="utf-8"
        )
        adr = (
            ROOT
            / "docs"
            / "decisions"
            / "0073-public-engineering-authority-cutover.zh.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Status: Accepted", contract)
        self.assertIn("Exactly one repository", contract)
        self.assertIn("agent_memory_public_authority_v1", contract)
        self.assertIn("public_install_verified", contract)
        self.assertIn("public_published", contract)
        self.assertIn("Status: accepted", adr)
        self.assertIn("不得继续修改或向公开仓库导出同一产品", adr)

    def test_core_adr_is_accepted(self) -> None:
        adr = (
            ROOT
            / "docs"
            / "decisions"
            / "0057-agent-memory-core-v1.zh.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Status: accepted", adr)
        self.assertIn("immutable zipapp", adr)

        evolution = (
            ROOT
            / "docs"
            / "decisions"
            / "0059-bounded-behavior-set-evolution.zh.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Status: accepted", evolution)
        self.assertIn("Implementation authorization: confirmed", evolution)

    def test_session_terminal_contract_stays_at_agent_skill_layer(self) -> None:
        axioms = (ROOT / "docs" / "specs" / "axioms.md").read_text(
            encoding="utf-8"
        )
        topology = (ROOT / "docs" / "specs" / "topology.md").read_text(
            encoding="utf-8"
        )
        interface = (ROOT / "docs" / "specs" / "interface.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("普通、未审计且没有合格候选的任务保持安静", axioms)
        self.assertIn("用户可见终态由 Agent / Skill 负责", axioms)
        self.assertIn("最终答复尾部呈现且只呈现一个真实终态", topology)
        self.assertIn("因此不改变七表拓扑", topology)
        self.assertIn("### 条件可见终态", interface)
        self.assertIn("commentary、内部提醒", interface)
        self.assertIn("长期状态：待确认", interface)
        self.assertIn("长期状态：生效中", interface)
        self.assertIn("长期状态：未变更", interface)
