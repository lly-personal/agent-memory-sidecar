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
        self.assertEqual(len(examples), 1)
        shell = shutil.which('pwsh') or shutil.which('powershell') if os.name == 'nt' else '/bin/sh'
        if not shell: self.skipTest('native command shell unavailable')
        harness = r'''
const fs=require('node:fs'), cp=require('node:child_process');
const p=JSON.parse(fs.readFileSync(0,'utf8'));let emitted,child,closed,ready,output='',stderr='',exit;
const source=p.page, load=()=>source, text=x=>{emitted=x;}, saved=new Map(),store=(k,v)=>saved.set(k,v);
let legacyCommandProbe=null;
if(p.windows){
 const literal="'"+JSON.stringify(source).replaceAll("'","''")+"'";
 const command='$null = '+literal;
 const probe=cp.spawnSync(p.shell,['-NoProfile','-NonInteractive','-Command',command],{encoding:'utf8'});
 legacyCommandProbe={command_characters:command.length,exit_code:probe.status,
                     error:probe.error?{code:probe.error.code,message:probe.error.message}:null};
}
const take=()=>{const value={output,stderr,...(exit===undefined?{session_id:1}:{exit_code:exit})};output='';return value;};
const tools={exec_command:async ({cmd,tty})=>{
 if(!tty||cmd.includes('large evidence'))throw new Error('payload was placed in the command');
 const args=p.windows?['-NoProfile','-NonInteractive','-Command',cmd]:['-c',cmd];
 child=cp.spawn(p.shell,args,{cwd:p.cwd,stdio:['pipe','pipe','pipe']});
 let readyResolve,closeResolve;ready=new Promise(r=>readyResolve=r);closed=new Promise(r=>closeResolve=r);
 child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
 child.stdout.on('data',data=>{output+=data;if(output.includes('"status":"awaiting_native_object"'))readyResolve();});
 child.stderr.on('data',data=>stderr+=data);
 child.stdin.on('error',error=>stderr+=error.code+': '+error.message);
 child.on('error',error=>{stderr+=error.code+': '+error.message;exit=-1;readyResolve();closeResolve();});
 const timer=setTimeout(()=>{stderr+='owned test process guard expired';child.kill();},15000);
 child.on('close',code=>{exit=code;clearTimeout(timer);child.stdin.destroy();readyResolve();closeResolve();});
 await ready;return take();
},write_stdin:async ({session_id,chars})=>{
 if(session_id!==1)throw new Error('wrong owned session');
 if(chars)child.stdin.write(chars); // Intentionally keep stdin open: capture must not wait for EOF.
 await closed;return take();
}};
(async()=>{
 const run=new (Object.getPrototypeOf(async function(){}).constructor)(
 'load','store','text','tools','pythonExecutable','scoutScript','artifactRoot','projectRoot','commandShell',p.code);
 await run(load,store,text,tools,p.python,p.script,p.output,p.project,p.windows?'powershell':'posix');
 const acceptedOutput=emitted;
 let failedStartRetainsSource=false;
 const unavailable={exec_command:async()=>({exit_code:1,output:'controlled native startup failure'}),
                    write_stdin:async()=>{throw new Error('must not send input after failed startup');}};
 try{await run(load,store,text,unavailable,p.python,p.script,p.output,p.project,p.windows?'powershell':'posix');}
 catch(error){failedStartRetainsSource=JSON.stringify(source)===JSON.stringify(p.page);}
 console.log(JSON.stringify({emitted:acceptedOutput,source_unchanged:JSON.stringify(source)===JSON.stringify(p.page),
                            failed_start_retains_source:failedStartRetainsSource,legacy_command_probe:legacyCommandProbe,
                            owned_session_closed:saved.get('scout-capture-session')===null}));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        request = dict(page=self.returned, code=examples[0], windows=os.name == 'nt',
                       shell=shell, cwd=str(self.root), python=sys.executable, script=str(SCRIPTS/'scout.py'),
                       output=str(self.output), project=str(self.project))
        result = subprocess.run([shutil.which('node'), '-e', harness], input=json.dumps(request, ensure_ascii=False),
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        self.assertTrue(actual['source_unchanged'])
        self.assertTrue(actual['failed_start_retains_source'])
        self.assertTrue(actual['owned_session_closed'])
        if actual['legacy_command_probe']:
            print('native command-size observation: '+json.dumps(actual['legacy_command_probe']))
        self.assertEqual(actual['emitted']['exit_code'], 0, actual['emitted'].get('stderr', actual))
        receipt = json.loads(actual['emitted']['output'].strip().splitlines()[-1])
        self.assertEqual(json.loads(Path(receipt['raw_file']).read_bytes()), self.returned)
        self.assertFalse((self.root/'injected').exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX owned terminal behavior')
    def test_owned_terminal_accepts_large_frame_and_restores_mode(self):
        import pty
        import termios
        master, slave = pty.openpty()
        previous = termios.tcgetattr(slave)
        child = subprocess.Popen([sys.executable, '-B', str(SCRIPTS/'scout.py'), 'capture-native', '--input-line',
            '--artifact-dir', str(self.output), '--protected-root', str(self.project)], stdin=slave,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(json.loads(child.stdout.readline())['status'], 'awaiting_native_object')
            self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
            data = memoryview((json.dumps(self.returned, ensure_ascii=False)+'\n').encode('utf-8'))
            while data: data = data[os.write(master, data):]
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, stderr)
            receipt = json.loads(stdout)
            self.assertEqual(json.loads(Path(receipt['raw_file']).read_bytes()), self.returned)
            observed = termios.tcgetattr(slave)
            # macOS sets PENDIN when canonical mode resumes, even in a standalone
            # tcsetattr control. It is pending-input state, not a changed setting.
            observed[3] &= ~getattr(termios, 'PENDIN', 0)
            previous[3] &= ~getattr(termios, 'PENDIN', 0)
            self.assertEqual(observed, previous)
        finally:
            if child.poll() is None: child.kill(); child.wait()
            os.close(master); os.close(slave)

    @unittest.skipUnless(os.name == 'posix', 'POSIX owned terminal cancellation')
    def test_owned_terminal_cancellation_restores_mode_without_a_capture(self):
        import pty
        import signal
        import termios
        for cancellation in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=cancellation):
                master, slave = pty.openpty()
                previous = termios.tcgetattr(slave)
                child = subprocess.Popen([sys.executable, '-B', str(SCRIPTS/'scout.py'), 'capture-native', '--input-line',
                    '--artifact-dir', str(self.output), '--protected-root', str(self.project)], stdin=slave,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    self.assertEqual(json.loads(child.stdout.readline())['status'], 'awaiting_native_object')
                    child.send_signal(cancellation)
                    child.communicate(timeout=15)
                    self.assertNotEqual(child.returncode, 0)
                    observed = termios.tcgetattr(slave)
                    observed[3] &= ~getattr(termios, 'PENDIN', 0)
                    previous[3] &= ~getattr(termios, 'PENDIN', 0)
                    self.assertEqual(observed, previous)
                    self.assertEqual(list(self.output.iterdir()), [])
                finally:
                    if child.poll() is None: child.kill(); child.wait()
                    termios.tcsetattr(slave, termios.TCSANOW, previous)
                    os.close(master); os.close(slave)
