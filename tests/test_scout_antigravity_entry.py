from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
from antigravity_native import invoke_antigravity
from validate_output import ContractError, NATIVE_PROJECT_CONTRACT, NATIVE_REVIEW_PACK_CONTRACT


class AntigravityEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.output = self.root / 'granted'
        self.output.mkdir()
        self.app_data = self.root / 'antigravity-acp'
        self.app_data.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(
            ['git', '-C', str(self.project), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
             'commit', '--allow-empty', '-qm', 'fixture'],
            check=True,
        )

    def _write_transcript(self, session_id: str, steps: list[dict], filename: str = 'transcript_full.jsonl') -> Path:
        logs = self.app_data / 'brain' / session_id / '.system_generated' / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        path = logs / filename
        path.write_text('\n'.join(json.dumps(s, ensure_ascii=False) for s in steps) + '\n', encoding='utf-8')
        return path

    def test_preflight_summary_supports_antigravity_review_and_inspect(self):
        for purpose in ('review', 'inspect'):
            res = subprocess.run(
                [sys.executable, '-B', str(SCRIPTS / 'scout.py'), 'preflight-summary', '--host', 'antigravity', '--purpose', purpose],
                capture_output=True, text=True, encoding='utf-8',
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertEqual(doc['host'], 'antigravity')
            self.assertEqual(doc['project_contract'], NATIVE_PROJECT_CONTRACT)
            self.assertEqual(doc['review_pack_contract'], NATIVE_REVIEW_PACK_CONTRACT)
            self.assertIn('antigravity_native.py context', doc['command_order'])
            self.assertEqual('antigravity_native.py capture' in doc['command_order'], purpose == 'review')

    def test_cli_help_is_read_only_without_touching_output(self):
        res = subprocess.run(
            [sys.executable, '-B', str(SCRIPTS / 'antigravity_native.py'), '--help'],
            cwd=self.output, capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('describe-input native-project|native-review', res.stdout)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_context_binding_accepts_child_dir_and_rejects_placeholders_and_drift(self):
        child = self.project / 'sub'
        child.mkdir()
        ctx = invoke_antigravity(
            operation='context',
            session_id='conv-123',
            project_root=str(child),
            app_data_dir=str(self.app_data),
            cwd=str(child),
        )
        self.assertEqual(ctx['native_binding']['binding_scope'], 'native_runtime_info_git')
        self.assertEqual(ctx['native_binding']['native_host'], 'antigravity')
        self.assertEqual(Path(ctx['native_binding']['project_root']), self.project)

        other = self.root / 'other'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        with self.assertRaisesRegex(ContractError, 'startup_execution_mismatch'):
            invoke_antigravity(
                operation='context',
                session_id='conv-123',
                project_root=str(other),
                app_data_dir=str(self.app_data),
                cwd=str(child),
            )
        for bad_kwargs in (
            dict(session_id='<conversation-id>', project_root=str(self.project), app_data_dir=str(self.app_data)),
            dict(session_id='conv-123', project_root=str(self.project), app_data_dir='<appDataDir>'),
            dict(session_id='../escape', project_root=str(self.project), app_data_dir=str(self.app_data)),
        ):
            with self.assertRaisesRegex(ContractError, 'runtime_info_required'):
                invoke_antigravity(operation='context', cwd=str(self.project), **bad_kwargs)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_capture_checks_output_boundary_before_transcript_and_seals_steps(self):
        # Reject project-internal or app_data output BEFORE even creating transcript.
        for bad_out in (self.project, self.app_data):
            with self.assertRaises(ContractError):
                invoke_antigravity(
                    operation='capture',
                    session_id='conv-123',
                    project_root=str(self.project),
                    app_data_dir=str(self.app_data),
                    artifact_dir=str(bad_out),
                    cwd=str(self.project),
                )

        steps = [
            {'step_index': 0, 'source': 'USER_EXPLICIT', 'type': 'USER_INPUT', 'status': 'DONE', 'content': '复盘当前项目'},
            {'step_index': 1, 'source': 'MODEL', 'type': 'PLANNER_RESPONSE', 'status': 'DONE', 'content': '已开始', 'truncated_fields': ['content']},
        ]
        self._write_transcript('hist-99', steps, filename='transcript.jsonl')
        first = invoke_antigravity(
            operation='capture',
            session_id='conv-123',
            project_root=str(self.project),
            app_data_dir=str(self.app_data),
            artifact_dir=str(self.output),
            source_session_id='hist-99',
            cwd=str(self.project),
        )
        cap = first['capture']
        self.assertEqual(cap['status'], 'imported')
        self.assertEqual(cap['native_host'], 'antigravity')
        self.assertEqual(cap['record_count'], 2)
        self.assertEqual(cap['truncation_paths'], ['$.steps[1].truncated_fields'])
        self.assertEqual(first['source_session_id'], 'hist-99')
        self.assertEqual(first['transcript_kind'], 'transcript')
        raw = json.loads(Path(cap['native_file']).read_text(encoding='utf-8'))
        self.assertEqual(raw['steps'], steps)

        second = invoke_antigravity(
            operation='capture',
            session_id='conv-123',
            project_root=str(self.project),
            app_data_dir=str(self.app_data),
            artifact_dir=str(self.output),
            source_session_id='hist-99',
            cwd=str(self.project),
        )
        self.assertEqual(second['capture']['status'], 'reused')


if __name__ == '__main__':
    unittest.main()
