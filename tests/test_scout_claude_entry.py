from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/global-owner-scout/scripts'


class ClaudeEntryTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which('node')
        if not self.node:
            self.skipTest('Node unavailable')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / 'project'; self.project.mkdir()
        self.output = self.root / 'granted'; self.output.mkdir()
        self.data = self.root / 'plugins/data/agent-memory-sidecar-agent-memory'
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(['git', '-C', str(self.project), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)

    def js(self, body):
        setup = '''
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const scripts=process.argv[1], cwd=process.cwd(), output=process.argv[2], data=process.argv[3];
const {invokeClaude}=await import(pathToFileURL(path.join(scripts,'claude_native.mjs')));
const {verifyRuntime,prepareRuntime,runtimePath}=await import(pathToFileURL(path.join(scripts,'prepare_claude_runtime.mjs')));
const base={operation:'context',session_id:'caller',project_root:cwd,
  skill_dir:path.dirname(scripts),plugin_root:path.resolve(scripts,'../../..'),plugin_data:data,artifact_dir:output};
'''
        run = subprocess.run([self.node, '--input-type=module', '-e', setup + body, str(SCRIPTS),
                              str(self.output), str(self.data)], cwd=self.project,
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_cli_help_routes_native_preparation_without_loading_a_project(self):
        result = subprocess.run([self.node, str(SCRIPTS / 'claude_native.mjs'), '--help'],
                                cwd=self.output, env=dict(os.environ, PATH=''),
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('context|capture', result.stdout)
        for field in ('session-id', 'project-root', 'skill-dir', 'plugin-root', 'plugin-data',
                      'artifact-dir', 'source-session-id', 'offset', 'limit'):
            self.assertIn('--' + field, result.stdout)
        self.assertIn('describe-input native-project|native-review', result.stdout)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_binding_rejects_wrong_skill_and_unresolved_values_without_history(self):
        self.js('''
const context=await invokeClaude(base);
assert.equal(context.native_binding.binding_scope,'native_skill_substitution_git');
assert.equal(context.native_context.context.source_kind,'claude_skill_substitution');
assert.equal('type' in context.native_context.context,false);
await assert.rejects(invokeClaude({...base,skill_dir:cwd}),/native_context_skill_mismatch/);
await assert.rejects(invokeClaude({...base,session_id:'${CLAUDE_SESSION_ID}'}),/current_substitutions_required/);
assert.deepEqual(await fs.readdir(output),[]);
''')

    def test_output_and_runtime_are_checked_before_sdk_loading(self):
        self.data.mkdir(parents=True)
        self.js('''
const load=()=>{throw Error('SDK_must_not_load')};
await assert.rejects(invokeClaude({...base,operation:'capture',artifact_dir:cwd},load),/output_preflight_unavailable/);
await assert.rejects(invokeClaude({...base,operation:'capture'},load),/claude_runtime_not_prepared/);
const root=runtimePath(data);await fs.mkdir(root,{recursive:true});
await fs.writeFile(path.join(root,'retained.txt'),'partial installation');
await assert.rejects(prepareRuntime(data,'unavailable'),/claude_runtime_incomplete/);
assert.equal(await fs.readFile(path.join(root,'retained.txt'),'utf8'),'partial installation');
assert.deepEqual(await fs.readdir(output),[]);
''')

    def test_startup_project_and_execution_root_must_agree_but_child_directory_is_valid(self):
        other = self.root / 'another'; other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        self.js('''
const child=path.join(cwd,"O'Brien $(echo literal-path)");await fs.mkdir(child);
process.chdir(child);
const context=await invokeClaude({...base,project_root:child});
assert.equal(context.native_binding.project_root,cwd);
assert.equal(context.native_context.context.project_dir,child);
assert.equal(context.native_context.context.cwd,child);
await assert.rejects(invokeClaude({...base,project_root:path.resolve(cwd,'../another')}),/startup_execution_mismatch/);
process.chdir(cwd);
''')

    def test_scoped_capture_uses_formal_writer_and_keeps_caller_distinct(self):
        # Synthetic SDK fixture exercises the complete dispatcher/writer, not a native-use claim.
        self.js('''
const root=runtimePath(data), sdkDir=path.join(root,'node_modules/@anthropic-ai/claude-agent-sdk');
await fs.mkdir(sdkDir,{recursive:true});
const source=path.resolve(scripts,'../runtime/claude');
for(const name of ['package.json','package-lock.json'])await fs.copyFile(path.join(source,name),path.join(root,name));
await fs.writeFile(path.join(sdkDir,'sdk.mjs'),'/* inert SDK fixture */');
await fs.writeFile(path.join(sdkDir,'package.json'),JSON.stringify({version:'0.3.322'}));
const hash=data=>createHash('sha256').update(data).digest('hex');
await fs.writeFile(path.join(root,'INSTALLATION.json'),JSON.stringify({
  contract_version:'global_owner_scout_claude_runtime_v1',sdk_version:'0.3.322',
  lock_sha256:hash(await fs.readFile(path.join(root,'package-lock.json'))),
  entry_sha256:hash(await fs.readFile(path.join(sdkDir,'sdk.mjs')))}));
const calls=[];
const sdk={getSessionInfo:async(id,options)=>{calls.push({id,options});return {sessionId:id,cwd}},
  getSessionMessages:async(id,options)=>{calls.push({id,options});return [{type:'system',uuid:'boundary',session_id:id}]}};
const options={...base,operation:'capture',source_session_id:'historical',limit:2};
const first=await invokeClaude(options,async()=>sdk);
assert.deepEqual(calls.map(c=>c.id),['caller','historical','historical']);
assert.ok(calls.every(c=>c.options.dir===cwd));
assert.equal(first.native_context.context.session_id,'caller');
assert.equal(first.source_session_id,'historical');
const raw=JSON.parse(await fs.readFile(first.capture.native_file,'utf8'));
assert.equal(raw.session.sessionId,'historical');assert.equal(raw.page_request.includeSystemMessages,true);
assert.equal(first.capture.record_count,1);
assert.equal((await invokeClaude(options,async()=>sdk)).capture.status,'reused');
await assert.rejects(invokeClaude(options,async()=>({...sdk,getSessionInfo:async()=>({sessionId:'wrong',cwd})})),/caller_mismatch/);
await assert.rejects(invokeClaude(options,async()=>({...sdk,getSessionMessages:async()=>{throw Error('native_read_failed')}})),/native_read_failed/);
await fs.appendFile(path.join(sdkDir,'sdk.mjs'),'changed');
await assert.rejects(verifyRuntime(data),/identity_mismatch/);
''')

    def test_deployment_preparation_handles_a_long_native_data_path(self):
        # An inert npm fixture verifies process launch and the explicit install contract;
        # separate native consumer evidence uses the real pinned SDK and npm.
        self.js('''
const npm=path.resolve(cwd,'../npm-fixture.mjs');
await fs.writeFile(npm,`
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
const args=process.argv.slice(2);assert.equal(args[0],'ci');
for(const flag of ['--ignore-scripts','--omit=optional','--no-audit','--no-fund'])assert.ok(args.includes(flag));
const root=args[args.indexOf('--prefix')+1],sdk=path.join(root,'node_modules/@anthropic-ai/claude-agent-sdk');
await fs.mkdir(sdk,{recursive:true});await fs.writeFile(path.join(sdk,'sdk.mjs'),'/* inert */');
await fs.writeFile(path.join(sdk,'package.json'),JSON.stringify({version:'0.3.322'}));
`);
const deep=path.resolve(cwd,'..',...Array(12).fill('native-long-path'), 'plugins/data/agent-memory-sidecar-inline');
assert.ok(runtimePath(deep).length>260);
assert.equal((await prepareRuntime(deep,npm)).status,'prepared');
assert.equal((await prepareRuntime(deep,npm)).status,'unchanged');
''')


if __name__ == '__main__':
    unittest.main()
