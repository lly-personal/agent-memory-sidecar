from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
import history_import
from validate_output import ContractError


class NativeObjectCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project's 中文"; self.project.mkdir()
        self.output = self.root / "output's 中文"; self.output.mkdir()
        self.page = dict(schemaVersion=1, thread=dict(id='source-chat', kind='codex', cwd=str(self.project)),
                         page=dict(nextCursor='same-source-cursor', hasMore=True),
                         turns=[dict(id='selected', items=[dict(type='commandExecution', outputTruncated=True,
                             text="中文 😀 ' `literal` $(touch injected)\n" + 'large evidence ' * 4096)])])
        self.returned = dict(content=[dict(type='text', text=json.dumps(self.page, ensure_ascii=False))], isError=False)

    def capture(self, value=None):
        return history_import.capture_native(self.returned if value is None else value,
            artifact_dir=self.output, protected_roots=[self.project])

    def cli(self, action, value, *extra):
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'scout.py'), action,
            '--artifact-dir', str(self.output), '--protected-root', str(self.project), *extra],
            input=json.dumps(value, ensure_ascii=False), capture_output=True, text=True, encoding='utf-8')

    def test_cli_captures_full_return_without_printing_it(self):
        first = self.cli('capture-native', self.returned)
        self.assertEqual(first.returncode, 0, first.stderr)
        receipt = json.loads(first.stdout); raw = Path(receipt['raw_file']).read_bytes()
        self.assertEqual(json.loads(raw), self.returned)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['sha256'])
        self.assertLess(len(first.stdout), 1600)
        self.assertNotIn('large evidence', first.stdout)
        self.assertNotIn('native_file', receipt)
        self.assertIn('remain unverified', receipt['evidence_scope'])
        self.assertEqual(self.cli('capture-native', self.returned).returncode, 0)
        self.assertEqual(len(list(self.output.iterdir())), 1)
        imported = self.cli('import-history', self.returned, '--project-root', str(self.project), '--session-id', 'source-chat')
        self.assertEqual(imported.returncode, 0, imported.stderr)
        index = json.loads(imported.stdout)
        self.assertEqual(index['page'], self.page['page'])
        self.assertTrue(index['truncation_paths'])
        self.assertEqual(json.loads(Path(index['native_file']).read_bytes()), self.page)

    def test_capture_error_and_index_does_not_qualify_history(self):
        for value in [dict(isError=True, content=[dict(type='text', text='original failure')]),
                      dict(schemaVersion=4, threads=[], page=dict(nextCursor='older', hasMore=True))]:
            with self.subTest(value=value):
                receipt = self.capture(value)
                self.assertEqual(json.loads(Path(receipt['raw_file']).read_bytes()), value)
                result = self.cli('import-history', value, '--project-root', str(self.project), '--session-id', 'source-chat')
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.output.glob('native-history-*')))
        wrong = self.cli('import-history', self.returned, '--project-root', str(self.project), '--session-id', 'other-chat')
        self.assertNotEqual(wrong.returncode, 0)
        self.assertFalse(list(self.output.glob('native-history-*')))

    def test_conflicts_aliases_and_protected_roots_still_fail(self):
        receipt = self.capture(); raw = Path(receipt['raw_file'])
        raw.chmod(0o600); raw.write_bytes(b'conflicting retained evidence')
        with self.assertRaises(ContractError): self.capture()
        self.assertEqual(raw.read_bytes(), b'conflicting retained evidence')
        raw.unlink(); other = self.root / 'retained.json'; other.write_bytes(b'retained')
        try: raw.symlink_to(other)
        except OSError: self.skipTest('symlink creation unavailable')
        with self.assertRaises((ContractError, OSError)): self.capture()
        self.assertEqual(other.read_bytes(), b'retained')
        with self.assertRaises(ContractError):
            history_import.capture_native(self.returned, artifact_dir=self.project, protected_roots=[self.project])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_directory_replacement_cannot_redirect_capture(self):
        original = history_import.write_native_artifact
        attempted = []
        def replace(root, descriptor, name, data):
            if not attempted:
                attempted.append(True)
                try: self.output.rename(self.root / 'retained-original-output')
                except PermissionError: self.assertEqual(sys.platform, 'win32')
                else: self.output.symlink_to(self.project, target_is_directory=True)
            return original(root, descriptor, name, data)
        with mock.patch.object(history_import, 'write_native_artifact', side_effect=replace):
            if sys.platform == 'win32': self.assertEqual(self.capture()['status'], 'captured')
            else:
                with self.assertRaises(ContractError): self.capture()
        self.assertTrue(attempted)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_interrupted_receipt_preserves_data_for_same_input_recovery(self):
        original = history_import.write_native_artifact
        def interrupt(*args):
            original(*args)
            raise OSError('controlled interruption after durable write')
        with mock.patch.object(history_import, 'write_native_artifact', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'controlled interruption'): self.capture()
        files = list(self.output.iterdir()); self.assertEqual(len(files), 1)
        before = files[0].read_bytes()
        self.assertEqual(self.capture()['status'], 'reused')
        self.assertEqual(files[0].read_bytes(), before)

    def test_failure_copy_does_not_invent_native_call_failure(self):
        terminal = dict(contract_version='global_owner_scout_terminal_v1', status='failed', phase='session_census',
                        reason_code='execution_protocol_failed', project_state='unchanged', confirmation_eligible=False)
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS/'scout.py'), 'render-terminal'],
            input=json.dumps(terminal), capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertNotIn('原生任务调用没有按协议取得可分类终态', result.stdout)
        self.assertIn('本次复盘失败', result.stdout)
        self.assertIn('status=failed', result.stdout)
        self.assertIn('confirmation_eligible=false', result.stdout)

    def test_partial_write_is_retained_and_not_overwritten_on_retry(self):
        def interrupt(root, descriptor, name, data):
            with (root/name).open('xb') as output: output.write(data[:17])
            raise OSError('controlled partial write')
        with mock.patch.object(history_import, 'write_native_artifact', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'controlled partial write'): self.capture()
        partial, = self.output.iterdir()
        before = partial.read_bytes()
        with self.assertRaises(ContractError): self.capture()
        self.assertEqual(partial.read_bytes(), before)
        self.assertEqual(list(self.project.iterdir()), [])

    @unittest.skipUnless(shutil.which('node'), 'Node runs the documented host-code contract; CLI tests remain independent')
    def test_documented_host_transfer_preserves_object_and_shell_literals(self):
        protocol = (SCRIPTS.parent/'references/deep-review-protocol.md').read_text(encoding='utf-8')
        examples = re.findall(r'```javascript\n(.*?)\n```', protocol, re.S)
        self.assertEqual(len(examples), 2)
        shell = shutil.which('pwsh') or shutil.which('powershell') if os.name == 'nt' else '/bin/sh'
        if not shell: self.skipTest('native command shell unavailable')
        harness = r'''
const fs=require('node:fs'), cp=require('node:child_process');
const p=JSON.parse(fs.readFileSync(0,'utf8'));let emitted;
const source=p.page, load=()=>source, text=x=>{emitted=x;};
const tools={exec_command:async ({cmd})=>{
 const args=p.windows?['-NoProfile','-NonInteractive','-Command',cmd]:['-c',cmd];
 const r=cp.spawnSync(p.shell,args,{cwd:p.cwd,encoding:'utf8'});
 return {exit_code:r.status,output:r.stdout,stderr:r.stderr};
}};
(async()=>{
 const run=new (Object.getPrototypeOf(async function(){}).constructor)(
 'load','text','tools','pythonExecutable','scoutScript','artifactRoot','projectRoot',p.code);
 await run(load,text,tools,p.python,p.script,p.output,p.project);
 console.log(JSON.stringify({emitted,source_unchanged:JSON.stringify(source)===JSON.stringify(p.page)}));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        request = dict(page=self.returned, code=examples[1 if os.name == 'nt' else 0], windows=os.name == 'nt',
                       shell=shell, cwd=str(self.root), python=sys.executable, script=str(SCRIPTS/'scout.py'),
                       output=str(self.output), project=str(self.project))
        result = subprocess.run([shutil.which('node'), '-e', harness], input=json.dumps(request, ensure_ascii=False),
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        self.assertTrue(actual['source_unchanged'])
        self.assertEqual(actual['emitted']['exit_code'], 0, actual['emitted']['stderr'])
        receipt = json.loads(actual['emitted']['output'])
        self.assertEqual(json.loads(Path(receipt['raw_file']).read_bytes()), self.returned)
        self.assertFalse((self.root/'injected').exists())
