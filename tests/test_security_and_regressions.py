from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from agent_memory_sidecar import cli
from agent_memory_sidecar.codex_integration import setup
from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.file_security import run_safe_git, safe_git_executable
from agent_memory_sidecar.identity import resolve_identity

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BOOTSTRAP_SCRIPTS = ROOT / "skills" / "agent-memory-workstation-bootstrap" / "scripts"
SCOUT_SCRIPTS = ROOT / "skills" / "global-owner-scout" / "scripts"


def _add_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


_add_path(SCRIPTS)
_add_path(BOOTSTRAP_SCRIPTS)
_add_path(SCOUT_SCRIPTS)

import build_release_artifacts  # noqa: E402
import bootstrap_security  # noqa: E402
import history_import  # noqa: E402
import managed_sources  # noqa: E402
import prepare_delivery  # noqa: E402
import render_review  # noqa: E402
import scout  # noqa: E402
import scout_security  # noqa: E402
from validate_output import ContractError  # noqa: E402
from validate_output_selftest import valid_project, valid_review_pack  # noqa: E402


def _make_dir_alias(alias: Path, target: Path, testcase: unittest.TestCase) -> None:
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            testcase.skipTest(f"directory junction unavailable: {proc.stderr or proc.stdout}")
        return
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        testcase.skipTest(f"directory symlink unavailable: {exc}")


class CliDailyOnlyAndReleaseVersionTests(unittest.TestCase):
    def test_cli_daily_only_unknown_command_returns_result_parser_error(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["setup"], daily_only=True)
        self.assertEqual(1, code)
        payload = json.loads(buf.getvalue())
        self.assertEqual("agent_memory_result_v1", payload["contract_version"])
        self.assertEqual("error", payload["status"])
        self.assertEqual("invalid_request", payload["error"]["code"])
        self.assertEqual("unknown command; expected rule or doctor", payload["error"]["message"])

    def test_release_version_facts_detects_validate_output_skill_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp) / "repo"
            for rel in (
                "pyproject.toml",
                "src/agent_memory_sidecar/__init__.py",
                "plugins/agent-memory-sidecar/.codex-plugin/plugin.json",
                "plugins/agent-memory-sidecar/.claude-plugin/plugin.json",
                ".claude-plugin/marketplace.json",
                "COMPATIBILITY.md",
                "skills/agent-memory-workstation-bootstrap/SKILL.md",
                "skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py",
                "skills/agent-memory-workstation-bootstrap/scripts/enrollment.py",
                "skills/global-owner-scout/SKILL.md",
                "skills/global-owner-scout/scripts/validate_output.py",
            ):
                dst = fake_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, dst)

            # Baseline copy passes version_facts
            facts = build_release_artifacts.version_facts(fake_root)
            self.assertEqual("5.20.2", facts["scout"])

            # Perturb validate_output.py SKILL_VERSION only
            vo_path = fake_root / "skills" / "global-owner-scout" / "scripts" / "validate_output.py"
            text = vo_path.read_text(encoding="utf-8")
            self.assertIn('SKILL_VERSION = "5.20.2"', text)
            vo_path.write_text(text.replace('SKILL_VERSION = "5.20.2"', 'SKILL_VERSION = "5.99.0"', 1), encoding="utf-8")

            with self.assertRaisesRegex(build_release_artifacts.ReleaseError, "release_scout_version_mismatch"):
                build_release_artifacts.version_facts(fake_root)


class CoreAndBootstrapSecurityRegressionTests(unittest.TestCase):
    def test_core_safe_git_rejects_workspace_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "workspace"
            bin_dir = ws / "evil-bin"
            (ws / ".git").mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            exe_name = "git.exe" if os.name == "nt" else "git"
            evil_git = bin_dir / exe_name
            evil_git.write_bytes(b"#!/bin/sh\nexit 0\n")
            if os.name != "nt":
                evil_git.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": str(bin_dir)}):
                self.assertIsNone(safe_git_executable(workspace=ws))
                with self.assertRaises(CoreError) as ctx:
                    run_safe_git(ws, "status")
                self.assertEqual("git_unavailable", ctx.exception.code)

    def test_core_setup_rejects_alias_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_home = root / "real-home"
            real_home.mkdir()
            alias_home = root / "alias-home"
            _make_dir_alias(alias_home, real_home, self)
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(alias_home)}):
                with self.assertRaises(CoreError) as ctx:
                    setup(apply=False, identity=resolve_identity(str(root)))
                self.assertEqual("store_unsafe", ctx.exception.code)

    def test_bootstrap_rejects_alias_binding_store_and_workspace_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_store_dir = root / "real-store-dir"
            real_store_dir.mkdir()
            codex_home = root / "codex-home"
            codex_home.mkdir()
            _make_dir_alias(codex_home / "agent-memory-sidecar", real_store_dir, self)
            (real_store_dir / "memory.sqlite").write_bytes(b"not-a-db")

            with self.assertRaisesRegex(bootstrap_security.BootstrapError, "public_core_binding_check_failed"):
                managed_sources._has_existing_global_binding(codex_home)
            with self.assertRaises(bootstrap_security.BootstrapError):
                managed_sources._existing_global_binding(codex_home)

            ws = root / "repo"
            (ws / ".git").mkdir(parents=True)
            evil_bin = ws / "bin"
            evil_bin.mkdir()
            exe = evil_bin / ("git.exe" if os.name == "nt" else "git")
            exe.write_bytes(b"fake")
            if os.name != "nt":
                exe.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": str(evil_bin)}):
                with self.assertRaisesRegex(bootstrap_security.BootstrapError, "source_git_failed"):
                    bootstrap_security.run_git(["status"], cwd=ws)


class ScoutPreflightAndSecurityTests(unittest.TestCase):
    def test_preflight_summary_deterministic_read_only_and_path_free(self) -> None:
        expected_matrix = {
            ("codex", "review"): ("global_owner_scout_project_v7", "global_owner_scout_review_pack_v8", ["project", "review"], "manual_30d"),
            ("codex", "inspect"): ("global_owner_scout_project_v7", "global_owner_scout_review_pack_v8", ["project", "review"], "current"),
            ("pi", "review"): ("global_owner_scout_project_v8", "global_owner_scout_review_pack_v9", ["native-project", "native-review"], "manual_30d"),
            ("pi", "inspect"): ("global_owner_scout_project_v8", "global_owner_scout_review_pack_v9", ["native-project", "native-review"], "current"),
            ("claude", "review"): ("global_owner_scout_project_v8", "global_owner_scout_review_pack_v9", ["native-project", "native-review"], "manual_30d"),
            ("claude", "inspect"): ("global_owner_scout_project_v8", "global_owner_scout_review_pack_v9", ["native-project", "native-review"], "current"),
        }
        with tempfile.TemporaryDirectory() as isolated:
            iso_path = Path(isolated)
            for (host, purpose), (proj_c, pack_c, kinds, window) in expected_matrix.items():
                proc = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "preflight-summary", "--host", host, "--purpose", purpose],
                    cwd=iso_path,
                    env={**os.environ, "CODEX_HOME": str(iso_path / "nonexistent-codex-home")},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )
                data = json.loads(proc.stdout)
                self.assertEqual("global_owner_scout_preflight_summary_v1", data["contract_version"])
                self.assertEqual("5.20.2", data["skill_version"])
                self.assertEqual(host, data["host"])
                self.assertEqual(purpose, data["purpose"])
                self.assertEqual(proj_c, data["project_contract"])
                self.assertEqual(pack_c, data["review_pack_contract"])
                self.assertEqual("global_owner_scout_delivery_v2", data["delivery_contract"])
                self.assertEqual("global_owner_scout_terminal_v1", data["terminal_contract"])
                self.assertEqual(kinds, data["describe_input_kinds"])
                self.assertEqual(window, data["evidence_window_kind"])
                self.assertTrue(isinstance(data["command_order"], list) and len(data["command_order"]) >= 6)
                expected_codex_owner_steps = host == "codex" and purpose == "review"
                self.assertEqual(expected_codex_owner_steps, "resolve-owner-parity" in data["command_order"])
                self.assertEqual(expected_codex_owner_steps, "prepare-review" in data["command_order"])
                raw = proc.stdout
                self.assertNotIn(str(ROOT), raw)
                self.assertNotIn(str(iso_path), raw)
                self.assertEqual(data, scout.build_preflight_summary(host, purpose))
            self.assertEqual([], list(iso_path.iterdir()))

    def test_scout_security_rejects_ancestor_alias_and_workspace_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            (real_parent / "child").mkdir()
            alias_parent = root / "alias-parent"
            _make_dir_alias(alias_parent, real_parent, self)
            protected = root / "protected"
            protected.mkdir()

            with self.assertRaisesRegex(ContractError, "history_output_ancestor_alias"):
                scout_security.validate_output_root(
                    alias_parent / "child",
                    [protected],
                    ancestor_error="history_output_ancestor_alias",
                )

            ws = root / "ws"
            (ws / ".git").mkdir(parents=True)
            evil_bin = ws / "tools"
            evil_bin.mkdir()
            exe = evil_bin / ("git.exe" if os.name == "nt" else "git")
            exe.write_bytes(b"fake")
            if os.name != "nt":
                exe.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": str(evil_bin)}):
                with self.assertRaisesRegex(ContractError, "git_context_executable_unavailable"):
                    scout_security.safe_git_executable(ws)

        # POSIX uid==0 top-level alias helper unit check (e.g. /var -> /private/var)
        fake_stat = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)
        self.assertTrue(
            scout_security.is_trusted_posix_root_alias(Path("/var"), fake_stat, Path("/var/folders/out"))
            if os.name == "posix"
            else not scout_security.is_trusted_posix_root_alias(Path("C:/var"), fake_stat, Path("C:/var/out"))
        )


class HighFidelityReplayAndMalformedNativeTests(unittest.TestCase):
    def test_2026_11_04_replay_collapsed_edges_brief_order_and_verify_final(self) -> None:
        # 1) HTML collapsed group retains descendant edges via projectRelations
        html = (ROOT / "skills" / "global-owner-scout" / "assets" / "project-map.html").read_text(encoding="utf-8")
        self.assertIn("function projectRelations(visible,relations)", html)
        self.assertIn("groups.get(key).edges.push(r)", html)
        if shutil.which("node"):
            snippet = (
                "const nodeMap = new Map(["
                "['root', {id:'root', parents:[]}],"
                "['g1', {id:'g1', parents:['root']}],"
                "['g2', {id:'g2', parents:['root']}],"
                "['c1', {id:'c1', parents:['g1']}],"
                "['c2', {id:'c2', parents:['g2']}]"
                "]);"
                "const node = id => nodeMap.get(id);"
                + "function projectRelations(visible,relations){"
                + html.split("function projectRelations(visible,relations){", 1)[1].split("function groupDetails", 1)[0]
                + "const groups = projectRelations([node('g1'), node('g2')], [{id:'e1', from:'c1', to:'c2', type:'handoff', kind:'handoff'}]);"
                + "console.log(JSON.stringify(groups));"
            )
            run = subprocess.run(
                [shutil.which("node"), "-e", snippet],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            groups = json.loads(run.stdout)
            self.assertEqual(1, len(groups))
            self.assertEqual("g1", groups[0]["from"])
            self.assertEqual("g2", groups[0]["to"])
            self.assertEqual(["e1"], [e["id"] for e in groups[0]["edges"]])

        # 2) verify_final_receipt rejects missing manifest hash binding
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "project"
            out = root / "output"
            proj.mkdir()
            out.mkdir()
            pack = valid_review_pack(valid_project(status="ok", card_count=1))
            manifest, artifact_path = prepare_delivery.prepare_delivery(pack, artifact_dir=out, protected_roots=[proj])
            receipt = prepare_delivery.render_delivery_receipt(
                manifest, artifact_path=artifact_path, artifact_root=out, outcome="not_requested"
            )
            # Brief order starts with summary overview, routing counts, then first actionable recommendation
            brief = render_review.extract_conversation_brief((out / manifest["artifact_name"]).read_text(encoding="utf-8"))
            self.assertIsNotNone(brief)
            self.assertIn("本次有 1 项建议可继续讨论", brief)
            self.assertLess(brief.index("去向："), brief.index("**首项建议："))
            # Missing delivery_manifest_sha256 binding must fail closed
            broken_receipt = receipt.replace(f"delivery_manifest_sha256={manifest['delivery_manifest_sha256']}", "delivery_manifest_sha256=missing")
            with self.assertRaises(ContractError):
                prepare_delivery.verify_final_receipt(broken_receipt, artifact_root=out)

    def test_clipped_but_succeeded_vs_tool_error_native_history_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "project"
            out = root / "output"
            proj.mkdir()
            out.mkdir()

            clipped = {
                "schemaVersion": 1,
                "thread": {"id": "thr-1", "kind": "codex", "cwd": str(proj)},
                "page": {"limit": 1},
                "turns": [
                    {
                        "id": "turn-1",
                        "items": [
                            {"id": "it-1", "type": "agentMessage", "text": "partial...", "textTruncated": True},
                        ],
                    }
                ],
            }
            imported = history_import.import_history(
                clipped, project_root=proj, session_id="thr-1", artifact_dir=out, protected_roots=[proj]
            )
            self.assertEqual("imported", imported["status"])
            self.assertEqual(["$.turns[0].items[0].textTruncated"], imported["truncation_paths"])

            errored = {"content": [{"type": "text", "text": json.dumps(clipped)}], "isError": True}
            with self.assertRaisesRegex(ContractError, "native_history_tool_failed"):
                history_import.import_history(
                    errored, project_root=proj, session_id="thr-1", artifact_dir=out, protected_roots=[proj]
                )

    def test_malformed_pi_and_claude_snapshots_and_native_context_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "project"
            out = root / "output"
            proj.mkdir()
            out.mkdir()

            bad_pi = {
                "contract_version": "global_owner_scout_native_session_v1",
                "native_host": "pi",
                "session": {"type": "session", "version": 2, "id": "pi-1", "cwd": str(proj)},
                "entries": [],
            }
            with self.assertRaisesRegex(ContractError, "native_history_session_header_unsupported"):
                history_import.import_history(
                    bad_pi, project_root=proj, session_id="pi-1", artifact_dir=out, protected_roots=[proj]
                )

            dup_pi = {
                "contract_version": "global_owner_scout_native_session_v1",
                "native_host": "pi",
                "session": {"type": "session", "version": 3, "id": "pi-1", "cwd": str(proj)},
                "entries": [
                    {"id": "e1", "type": "message"},
                    {"id": "e1", "type": "message"},
                ],
            }
            with self.assertRaisesRegex(ContractError, "native_history_duplicate_entry"):
                history_import.import_history(
                    dup_pi, project_root=proj, session_id="pi-1", artifact_dir=out, protected_roots=[proj]
                )

            bad_claude_page = {
                "contract_version": "global_owner_scout_native_page_v1",
                "native_host": "claude",
                "session": {"sessionId": "cl-1", "cwd": str(proj)},
                "messages": [{"type": "user", "uuid": "u1", "session_id": "cl-1"}],
                "page_request": {"offset": -1, "limit": 10, "includeSystemMessages": True},
            }
            with self.assertRaisesRegex(ContractError, "native_history_page_request_invalid"):
                history_import.import_history(
                    bad_claude_page, project_root=proj, session_id="cl-1", artifact_dir=out, protected_roots=[proj]
                )

            bad_pi_ctx = {
                "contract_version": "global_owner_scout_native_context_v1",
                "native_host": "pi",
                "context": {
                    "cwd": str(proj),
                    "session_id": "pi-1",
                    "session": {"type": "session", "version": 3, "id": "pi-1", "cwd": str(proj)},
                    "mode": "invalid-mode",
                },
            }
            with self.assertRaisesRegex(ContractError, "native_context_mismatch"):
                scout.inspect_native_context(bad_pi_ctx, proj)

            bad_claude_ctx = {
                "contract_version": "global_owner_scout_native_context_v1",
                "native_host": "claude",
                "context": {"type": "user", "subtype": "other", "session_id": "cl-1", "cwd": str(proj)},
            }
            with self.assertRaisesRegex(ContractError, "native_context_mismatch"):
                scout.inspect_native_context(bad_claude_ctx, proj)

    def test_wave_a_malformed_window_legacy_eligibility_and_terminal_recovery(self) -> None:
        import validate_output

        # 1) Malformed evidence_window raises ContractError cleanly and stays inside CLI error envelope.
        for bad_window in ({}, None, "manual_30d", ["bad"]):
            broken = valid_project(status="no_material_delta", card_count=0)
            broken["evidence_window"] = bad_window
            with self.subTest(bad_window=bad_window):
                with self.assertRaises(ContractError):
                    validate_output.validate_project(broken)
                proc = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "validate-project"],
                    input=json.dumps(broken),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(1, proc.returncode)
                err = json.loads(proc.stderr)
                self.assertEqual("error", err["status"])
                self.assertNotIn("Traceback", proc.stderr)

        # 2) Legacy no-brief open_succeeded without recovery_bundle never marks confirmation_eligible=true.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "project"
            out = root / "output"
            proj.mkdir()
            out.mkdir()
            pack = valid_review_pack(valid_project(status="no_material_delta", card_count=0))
            manifest, artifact = prepare_delivery.prepare_delivery(pack, artifact_dir=out, protected_roots=[proj])
            with mock.patch.object(prepare_delivery, "extract_conversation_brief", return_value=None):
                receipt = prepare_delivery.render_delivery_receipt(
                    manifest, artifact_path=artifact, artifact_root=out, outcome="open_succeeded"
                )
            self.assertIn("confirmation_eligible=false", receipt)
            self.assertNotIn("confirmation_eligible=true", receipt)

        # 3) Every terminal receipt includes concrete recovery guidance and folds technical fields.
        for reason_code, (status, phase, states, _, recovery) in prepare_delivery.TERMINAL_REASON_MAPPINGS.items():
            terminal = {
                "contract_version": prepare_delivery.TERMINAL_CONTRACT,
                "status": status,
                "phase": phase,
                "reason_code": reason_code,
                "project_state": sorted(states)[0],
                "confirmation_eligible": False,
            }
            rendered = prepare_delivery.render_terminal_receipt(terminal)
            self.assertIn("**下一步建议**：" + recovery, rendered)
            self.assertIn("<details>\n<summary>技术诊断详情</summary>", rendered)

    def test_wave_b_seal_project_and_seal_delivery_composite_fast_path(self) -> None:
        from tests.test_scout_native_protocol import native_pack

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "project"
            out = root / "output"
            proj.mkdir()
            out.mkdir()

            draft_pack = native_pack("antigravity")
            draft_project = draft_pack["project_result"]
            draft_project["project_cards"][0]["normalized_evidence_hash"] = ""
            draft_project["project_cards"][0]["project_claim_hash"] = ""
            draft_project_file = root / "draft-project.json"
            sealed_project_file = out / "sealed-project.json"
            draft_project_file.write_text(json.dumps(draft_project, ensure_ascii=False), encoding="utf-8")

            # --output-file rejects missing boundary flags, protected paths, and overwriting existing files
            for bad_args in (
                ["--output-file", str(sealed_project_file)],
                ["--output-file", str(proj / "leak.json"), "--artifact-dir", str(proj), "--protected-root", str(proj)],
            ):
                bad = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-project",
                     "--input-file", str(draft_project_file), *bad_args],
                    capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(1, bad.returncode)

            seal_proj = subprocess.run(
                [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-project",
                 "--input-file", str(draft_project_file), "--output-file", str(sealed_project_file),
                 "--artifact-dir", str(out), "--protected-root", str(proj)],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            self.assertEqual("ok", json.loads(seal_proj.stdout)["status"])
            sealed_proj = json.loads(sealed_project_file.read_text(encoding="utf-8"))
            self.assertEqual(64, len(sealed_proj["project_cards"][0]["project_claim_hash"]))

            # Existing output file must fail closed (O_EXCL)
            overwrite = subprocess.run(
                [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-project",
                 "--input-file", str(draft_project_file), "--output-file", str(sealed_project_file),
                 "--artifact-dir", str(out), "--protected-root", str(proj)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(1, overwrite.returncode)

            draft_pack["project_result"] = draft_project
            draft_pack["review_cards"][0]["project_claim_hash"] = ""
            draft_pack["review_pack_hash"] = ""
            draft_pack_file = root / "draft-pack.json"
            draft_pack_file.write_text(json.dumps(draft_pack, ensure_ascii=False), encoding="utf-8")

            # Host mismatch must fail closed before writing
            for wrong_host in ("pi", "codex"):
                mismatch = subprocess.run(
                    [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-delivery",
                     "--artifact-dir", str(out), "--protected-root", str(proj),
                     "--host", wrong_host, "--input-file", str(draft_pack_file)],
                    capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(1, mismatch.returncode, wrong_host)

            # Native host must also reject a Codex rule pack
            codex_rule_pack = valid_review_pack(valid_project(status="ok", card_count=1))
            codex_rule_file = root / "codex-rule-pack.json"
            codex_rule_file.write_text(json.dumps(codex_rule_pack, ensure_ascii=False), encoding="utf-8")
            bad_pi_rule = subprocess.run(
                [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-delivery",
                 "--artifact-dir", str(out), "--protected-root", str(proj),
                 "--host", "pi", "--outcome", "open_succeeded", "--input-file", str(codex_rule_file)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(1, bad_pi_rule.returncode)

            # Codex draft with null selection_preview & null selection_token auto-derives token for prepare_review
            draft_codex_rule = json.loads(json.dumps(codex_rule_pack))
            draft_codex_rule["selection_preview"] = None
            draft_codex_rule["review_cards"][0]["selection_token"] = None
            draft_codex_rule["review_pack_hash"] = ""
            with mock.patch.object(scout, "prepare_review", side_effect=lambda p, **_: codex_rule_pack) as mock_pr:
                codex_out = root / "codex-out"
                codex_out.mkdir()
                res = scout.seal_delivery_payload(
                    draft_codex_rule, artifact_dir=codex_out, protected_roots=[proj], host="codex", with_visual=True,
                )
                self.assertEqual("ok", res["status"])
                passed_pack = mock_pr.call_args.args[0]
                self.assertIsNotNone(passed_pack["review_cards"][0]["selection_token"])

            # --with-visual without explicit --host codex never emits PUA visualize token
            seal_deliv = subprocess.run(
                [sys.executable, "-B", str(SCOUT_SCRIPTS / "scout.py"), "seal-delivery",
                 "--artifact-dir", str(out), "--protected-root", str(proj),
                 "--host", "antigravity", "--with-visual", "--input-file", str(draft_pack_file)],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            payload = json.loads(seal_deliv.stdout)
            self.assertEqual("ok", payload["status"])
            self.assertTrue(Path(payload["artifact_path"]).is_file())
            self.assertNotIn("visualize", payload["receipt"])
            self.assertIn("<details>\n<summary>技术校验信息</summary>", payload["receipt"])
            recovered = prepare_delivery.verify_final_receipt(payload["receipt"], artifact_root=out)
            self.assertEqual("artifact_verified", recovered["status"])
            self.assertFalse(recovered["confirmation_eligible"])


if __name__ == "__main__":
    unittest.main()
