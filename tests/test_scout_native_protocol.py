from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
from tests.test_scout_project_map import layered_pack
import validate_output as v
from scout import inspect_native_context, inspect_git_context
from prepare_delivery import prepare_delivery, render_delivery_receipt, verify_final_receipt


def native_pack(host='pi'):
    pack = layered_pack(); project = pack['project_result']
    project.update(contract_version=v.NATIVE_PROJECT_CONTRACT, status='degraded',
        session_coverage=dict(native_host=host, scopes=[dict(kind='session_messages', coverage='observed_only',
            record_count=2, evidence_refs=['session:page'])], discovered_task_count=1, selected_task_count=1,
            fully_read_task_count=0, status='degraded', discovery_methods=['native_scoped_sources_observed']),
        limitations=['原生接口不能证明没有丢失记录；仅按实际取得范围复盘。'])
    source = next(s for s in project['evidence_sources'] if s['kind'] == 'sessions')
    source.update(status='degraded', coverage='取得原生消息页，完整历史未知。',
        refs=[dict(type='session', ref='session:page', summary='已封存的原生来源页。')],
        uncovered=['原生接口未提供完整错误和无遗漏证明。'])
    pack.update(contract_version=v.NATIVE_REVIEW_PACK_CONTRACT, status='degraded', limitations=project['limitations'])
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    return pack


class NativeProtocolTests(unittest.TestCase):
    def test_native_review_uses_real_delivery_and_recovery_without_codex_partitions(self):
        for host in ('pi', 'claude'):
            pack = native_pack(host)
            v.validate_review_pack(pack)
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest, artifact = prepare_delivery(pack, artifact_dir=root, protected_roots=[SCRIPTS])
                receipt = render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root,
                                                 outcome='not_requested', text_only=True)
                recovered = verify_final_receipt(receipt, artifact_root=root)
                self.assertEqual(recovered['project_map_bundle']['context']['project_contract'], v.NATIVE_PROJECT_CONTRACT)
                self.assertIn('完整历史仍未知', receipt)
                body = artifact.read_text(encoding='utf-8')
                self.assertIn('完整历史仍未知', body)
                self.assertNotIn('active `', body)
                self.assertNotIn('archived `', body)
                self.assertEqual(recovered['project_map_bundle']['context']['advice'][0]['kind'], 'engineering')
            import prepare_review
            with mock.patch.object(prepare_review, 'resolve', side_effect=AssertionError('unrelated Codex Owner')):
                self.assertEqual(prepare_review.prepare_review(pack, codex_home=Path('unused')), pack)

    def test_empty_native_scope_is_observed_zero_without_becoming_complete(self):
        pack = native_pack(); coverage = pack['project_result']['session_coverage']
        coverage.update(discovered_task_count=0, selected_task_count=0)
        coverage['scopes'][0]['record_count'] = 0
        pack['review_pack_hash'] = v.review_pack_hash(pack)
        v.validate_review_pack(pack)
        coverage['status'] = 'complete'
        with self.assertRaises(v.ContractError): v.validate_project(pack['project_result'])

    def test_overclaims_unresolved_refs_and_fabricated_partitions_are_rejected(self):
        candidates = []
        for key, value in [('native_host', 'codex'), ('fully_read_task_count', 1),
                           ('status', 'complete'), ('discovery_methods', ['native_index_completed']),
                           ('index_terminals', dict(active='eof', archived='eof'))]:
            p = native_pack()['project_result']; p['session_coverage'][key] = value; candidates.append(p)
        for field, value in [('coverage', 'complete'), ('evidence_refs', ['session:unknown']),
                             ('record_count', None)]:
            p = native_pack()['project_result']; p['session_coverage']['scopes'][0][field] = value; candidates.append(p)
        p = native_pack()['project_result']; p['status'] = 'ok'; candidates.append(p)
        p = native_pack()['project_result']; p['project_cards'][0]['direct_evidence'] = p['evidence_sources'][0]['refs']; candidates.append(p)
        for p in candidates:
            with self.subTest(p=p), self.assertRaises(v.ContractError): v.validate_project(p)
        old = layered_pack(); v.validate_review_pack(old)
        old['project_result']['session_coverage'] = native_pack()['project_result']['session_coverage']
        with self.assertRaises(v.ContractError): v.validate_project(old['project_result'])
        rule = native_pack()['project_result']; rule['project_cards'] = [v.build_card()]
        with self.assertRaisesRegex(v.ContractError, 'engineering advice only'): v.validate_project(rule)

    def test_current_native_context_is_bound_to_git_before_history_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); project = root/'project'; project.mkdir()
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit', '--allow-empty', '-qm', 'isolated context'], check=True)
            child = project/'child'; child.mkdir()
            (project/'outside-current-child.txt').write_text('must remain in the whole-project fingerprint', encoding='utf-8')
            contexts = [dict(contract_version='global_owner_scout_native_context_v1', native_host='pi', context=dict(
                cwd=str(child), session_id='native-session', mode='rpc',
                session=dict(type='session', version=3, id='native-session', cwd=str(child)))),
                dict(contract_version='global_owner_scout_native_context_v1', native_host='claude',
                    context=dict(type='system', subtype='init', cwd=str(child), session_id='native-session'))]
            for source in contexts:
                result = inspect_native_context(source, project)
                self.assertEqual(result['binding_scope'], 'native_current_session_git')
                self.assertEqual(result['git_snapshot']['execution_context'], 'local')
                self.assertEqual(result['git_snapshot'], inspect_git_context(project))
                with self.assertRaises(v.ContractError): inspect_native_context(source, root)
                run = subprocess.run([sys.executable, '-B', str(SCRIPTS/'scout.py'), 'inspect-native',
                                      '--project-root', str(project)], input=json.dumps(source),
                                      text=True, encoding='utf-8', capture_output=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout)['source_sha256'], result['source_sha256'])
            bad = copy.deepcopy(contexts[0]); bad['context']['session']['id'] = 'other'
            with self.assertRaises(v.ContractError): inspect_native_context(bad, project)
            historical = dict(contract_version='global_owner_scout_native_context_v1', native_host='claude',
                              context=dict(sessionId='history-only', cwd=str(child)))
            with self.assertRaises(v.ContractError): inspect_native_context(historical, project)

    def test_native_context_and_turn_observers_keep_exact_native_boundaries(self):
        node = shutil.which('node')
        if not node: self.skipTest('Node unavailable')
        script = '''
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const n=await import(pathToFileURL(process.argv[1]));
const cwd=process.cwd(), session={type:'session',version:3,id:'native',cwd};
const ctx={cwd,mode:'rpc',sessionManager:{getHeader:()=>session,getSessionId:()=>session.id,
  getCwd:()=>cwd,getEntries:()=>{throw Error('history read before authorization')}}};
assert.equal(n.exportPiContext(ctx).context.session_id,'native');
assert.throws(()=>n.exportPiContext({...ctx,cwd:cwd+'/other'}));
const init={type:'system',subtype:'init',cwd,session_id:'native'};
assert.equal(n.exportClaudeContext(init).context.cwd,cwd);
const state={sessionId:'native',isStreaming:false,isCompacting:false,pendingMessageCount:0};
const settled=[{type:'agent_end'},{type:'agent_settled',aborted:false}];
assert.equal(n.observePiTurn(state,settled,state).status,'settled');
assert.equal(n.observePiTurn(state,[{type:'agent_end'}],state).status,'open_or_unknown');
assert.equal(n.observePiTurn(state,[...settled,{type:'agent_start'}],state).status,'open_or_unknown');
assert.equal(n.observePiTurn(state,settled,{...state,pendingMessageCount:1}).status,'open_or_unknown');
assert.equal(n.observePiTurn(state,[...settled,{type:'agent_end',willRetry:true}],state).status,'open_or_unknown');
assert.equal(n.observePiTurn(state,[{type:'agent_settled',aborted:true}],state).status,'aborted');
assert.throws(()=>n.observePiTurn(state,settled,{...state,sessionId:'other'}));
const result={type:'result',subtype:'success',is_error:false,session_id:'native'};
assert.equal(n.observeClaudeTurn(init,[init,result]).status,'result_success');
assert.equal(n.observeClaudeTurn(init,[init,result,init]).status,'open_or_unknown');
for(const next of [{type:'system',subtype:'session_state_changed',state:'running'},
                   {type:'system',subtype:'session_state_changed',state:'requires_action'},
                   {type:'system',subtype:'status',status:'requesting'},
                   {type:'system',subtype:'status',status:'compacting'},
                   {type:'conversation_reset',new_conversation_id:'another-conversation'}]) {
  assert.equal(n.observeClaudeTurn(init,[init,result,next]).status,'open_or_unknown');
}
assert.equal(n.observeClaudeTurn(init,[init,result,{type:'assistant',session_id:'native'}]).status,'open_or_unknown');
assert.equal(n.observeClaudeTurn(init,[init,{...result,queued_turn_count:1}]).status,'open_or_unknown');
assert.throws(()=>n.observeClaudeTurn(init,[{...result,session_id:'other'}]));
assert.equal(n.observeClaudeTurn(init,[init,result]).business_success,'unverified');
console.log('native boundaries passed');
'''
        run = subprocess.run([node, '--input-type=module', '-e', script, str(SCRIPTS/'native_session_export.mjs')],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__': unittest.main()
