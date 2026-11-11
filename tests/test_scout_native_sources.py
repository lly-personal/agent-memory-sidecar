from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
from history_import import import_history
from validate_output import ContractError


class NativeSessionSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'project'; self.project.mkdir()
        self.output = self.root / 'granted-output'; self.output.mkdir()
        self.source = dict(contract_version='global_owner_scout_native_session_v1', native_host='pi',
                           session=dict(type='session', version=3, id='native-session', cwd=str(self.project)),
                           entries=[dict(type='message', id='native-entry', parentId=None,
                                         message=dict(role='assistant', content=[dict(type='text', text='原生内容')],
                                                      stopReason='stop'))])

    def save(self, source=None, **overrides):
        return import_history(self.source if source is None else source,
                              project_root=self.project, session_id=overrides.get('session_id', 'native-session'),
                              artifact_dir=overrides.get('artifact_dir', self.output), protected_roots=[self.project])

    def test_sdk_snapshot_is_sealed_unchanged_and_never_promoted_to_project_coverage(self):
        first = self.save(); second = self.save()
        self.assertEqual(first['status'], 'imported')
        self.assertEqual(second['status'], 'reused')
        self.assertEqual(json.loads(Path(first['native_file']).read_bytes()), self.source)
        self.assertEqual(first['contract_version'], 'global_owner_scout_history_page_v2')
        self.assertEqual(first['entry_ids'], ['native-entry'])
        self.assertEqual(first['record_count'], 1)
        self.assertIn('remain unverified', first['evidence_scope'])
        self.assertFalse({'turn_ids', 'index_terminals', 'discovery_methods', 'terminal_status'} & first.keys())
        self.assertEqual(len(list(self.output.iterdir())), 2)

    def test_wrong_identity_host_version_and_record_shape_fail_before_writes(self):
        candidates = []
        for host in ('codex', 'claude'):
            bad = copy.deepcopy(self.source); bad['native_host'] = host; candidates.append(bad)
        for field, value in [('version', 99), ('version', True), ('id', 'other-session'), ('cwd', str(self.output))]:
            bad = copy.deepcopy(self.source); bad['session'][field] = value; candidates.append(bad)
        bad = copy.deepcopy(self.source); bad['entries'] = [dict(type='message')]; candidates.append(bad)
        bad = copy.deepcopy(self.source); bad['entries'] *= 2; candidates.append(bad)
        bad = copy.deepcopy(self.source); bad['claimed_complete'] = True; candidates.append(bad)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ContractError):
                self.save(candidate)
        self.assertFalse(list(self.output.iterdir()))

    def test_empty_snapshot_and_native_truncation_keep_their_exact_scope(self):
        empty = copy.deepcopy(self.source); empty['entries'] = []
        self.assertEqual(self.save(empty)['record_count'], 0)
        truncated = copy.deepcopy(self.source)
        truncated['entries'][0]['message']['outputTruncated'] = True
        result = self.save(truncated)
        self.assertEqual(result['truncation_paths'], ['$.entries[0].message.outputTruncated'])
        self.assertEqual(json.loads(Path(result['native_file']).read_bytes()), truncated)

    def test_output_stays_on_the_existing_explicit_grant_boundary(self):
        with self.assertRaises(ContractError):
            self.save(artifact_dir=self.project)
        with self.assertRaises((ContractError, OSError)):
            self.save(artifact_dir=self.root / 'not-granted')
        self.assertFalse(list(self.project.iterdir()))
        self.assertFalse(list(self.output.iterdir()))

    def test_public_export_helper_checks_native_manager_and_detaches_snapshot(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is unavailable; Python import contract checks still execute')
        script = '''
import { pathToFileURL } from 'node:url';
const { exportPiSession } = await import(pathToFileURL(process.argv[1]));
const session = { type: 'session', version: 3, id: 'native-session', cwd: 'native-root' };
const entries = [{ type: 'custom', id: 'entry', data: { unchanged: true } }];
const manager = { getHeader: () => session, getSessionId: () => session.id,
                  getCwd: () => session.cwd, getEntries: () => entries };
const result = exportPiSession(manager);
entries[0].data.unchanged = false;
if (!result.entries[0].data.unchanged) throw new Error('snapshot_not_detached');
for (const bad of [{ ...manager, getSessionId: () => 'other' },
                   { ...manager, getCwd: () => 'other' },
                   { ...manager, getHeader: () => null }]) {
  let rejected = false;
  try { exportPiSession(bad); } catch { rejected = true; }
  if (!rejected) throw new Error('wrong_native_context_accepted');
}
console.log(JSON.stringify(result));
'''
        run = subprocess.run([node, '--input-type=module', '-e', script,
                              str(SCRIPTS / 'native_session_export.mjs')],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['native_host'], 'pi')

    def test_cli_accepts_native_snapshot_without_codex_transcoding(self):
        source = self.root / 'native-sdk-object.json'
        source.write_text(json.dumps(self.source, ensure_ascii=False), encoding='utf-8')
        run = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'scout.py'), 'import-history',
                              '--input-file', str(source), '--project-root', str(self.project),
                              '--session-id', 'native-session', '--artifact-dir', str(self.output),
                              '--protected-root', str(self.project)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['native_host'], 'pi')


if __name__ == '__main__':
    unittest.main()
