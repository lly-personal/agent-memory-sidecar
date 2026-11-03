from __future__ import annotations

import copy
import importlib
import json
import hashlib
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
v = importlib.import_module('validate_output')


def map_project(purpose='inspect'):
    p = v.valid_project(status='no_material_delta')
    p.update(contract_version='global_owner_scout_project_v6', purpose=purpose)
    ref = 'owner:current'
    claim = {'layer': 'design', 'environment': '适用环境', 'statement': '从明确入口执行并验收结果。', 'evidence_refs': [ref]}
    p['project_map'] = {
        'title': '示例工程', 'goal': '让用户完成目标。', 'boundary': '仅覆盖本工程。',
        'observed_at': p['evidence_window']['end'], 'source_revision': p['read_only_proof']['after_head'],
        'nodes': [dict(id=i, label=label, kind='能力', summary=label+'承担明确职责。', owner='项目规范',
                       evidence_refs=[ref], claims=[copy.deepcopy(claim)], card_ids=[])
                  for i, label in [('entry', '用户入口'), ('consumer', '实际消费者')]],
        'edges': [dict(id='handoff', source='entry', target='consumer', label='传递上下文', evidence_refs=[ref], claims=[copy.deepcopy(claim)], card_ids=[])],
        'journeys': [dict(id='ordinary', label='普通任务', entry='entry', edge_ids=['handoff'], outcome='消费者取得结果。', recovery='失败时恢复当前任务。', evidence_refs=[ref], card_ids=[])],
        'coverage': [dict(dimension='真实入口', status='partial', explanation='规范已核实，真实采用未知。', evidence_refs=[ref])],
    }
    if purpose == 'inspect':
        p.update(status='view_ready', session_coverage=None, events=[], observations=[])
        p['evidence_window']['kind'] = 'current'
        p['evidence_sources'][0] = dict(kind='sessions', status='not_applicable', coverage='本次查看不做会话普查。', refs=[], uncovered=[])
    return p


def map_pack(purpose='inspect'):
    pack = v.valid_review_pack()
    p = map_project(purpose)
    pack.update(contract_version='global_owner_scout_review_pack_v7', project_result=p,
                status=p['status'], review_cards=[], selection_preview=None, limitations=p['limitations'])
    if purpose == 'inspect':
        pack['owner_parity'] = None
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    return pack


class ScoutProjectMapTests(unittest.TestCase):
    def test_inspect_has_no_census_or_owner_resolution(self):
        import prepare_review
        with mock.patch.object(prepare_review, 'resolve', side_effect=AssertionError('must not resolve')):
            self.assertEqual(map_pack(), prepare_review.prepare_review(map_pack(), codex_home=Path('unused')))

    def test_connected_paths_declared_evidence_and_scope_are_required(self):
        v.validate_project(map_project())
        for path, replacement in [
            (('edges', 0, 'target'), 'absent'), (('nodes', 0, 'evidence_refs'), ['undeclared']),
            (('journeys', 0, 'entry'), 'consumer'), (('nodes', 0, 'card_ids'), ['invented']),
            (('source_revision',), 'b' * 40),
        ]:
            p = map_project(); obj = p['project_map']
            for key in path[:-1]: obj = obj[key]
            obj[path[-1]] = replacement
            with self.subTest(path=path), self.assertRaises(v.ContractError): v.validate_project(p)

    def test_two_projections_and_old_recovery(self):
        import prepare_delivery as d
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pack in [v.valid_review_pack(), map_pack(), map_pack('review')]:
                manifest, artifact = d.prepare_delivery(pack, artifact_dir=root, protected_roots=[SCRIPTS])
                original = artifact.read_bytes()
                receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome='not_requested')
                recovered = d.verify_final_receipt(receipt, artifact_root=root)
                self.assertEqual(original, artifact.read_bytes())
                self.assertFalse(recovered['confirmation_eligible'])
                if pack['contract_version'].endswith('v7'):
                    self.assertEqual('global_owner_scout_delivery_v2', manifest['contract_version'])
                    self.assertEqual('verified', recovered['visual_status'])
                    self.assertIn('工程全貌', original.decode())
                    visual = root / manifest['visual_name']
                    visual.chmod(0o600); visual.write_text('changed')
                    self.assertEqual('unavailable', d.verify_final_receipt(receipt, artifact_root=root)['visual_status'])
                    self.assertEqual(original, artifact.read_bytes())

    def test_render_escapes_source_content_and_never_executes_a_tool(self):
        from project_map import render_visual, map_context
        p = map_pack(); p['project_result']['project_map']['nodes'][0]['label'] = '</script><script>alert(1)</script>'
        context = map_context(p)
        html = render_visual(context, p['review_pack_hash'])
        self.assertNotIn('</script><script>alert', html)
        self.assertIn('sendFollowUpMessage', html)
        self.assertNotIn('callTool(', html)
        self.assertNotIn('fetch(', html)

    def test_caller_cannot_rebind_the_frozen_visual(self):
        import prepare_delivery as d
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifact = d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS])
            visual = root / manifest['visual_name']
            visual.chmod(0o600); visual.write_bytes(b'other content'); visual.chmod(0o400)
            forged = dict(manifest, visual_bytes=13, visual_sha256=hashlib.sha256(b'other content').hexdigest())
            forged['delivery_manifest_sha256'] = d.delivery_manifest_sha256(forged)
            with self.assertRaisesRegex(v.ContractError, 'visual descriptor'):
                d.render_delivery_receipt(forged, artifact_path=artifact, artifact_root=root, outcome='not_requested')

    def test_pointer_and_markdown_tampering_are_rejected(self):
        import prepare_delivery as d
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifact = d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS])
            receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome='not_requested')
            with self.assertRaisesRegex(v.ContractError, 'visual pointer'):
                d.verify_final_receipt(receipt.replace(manifest['visual_name'], 'another.html'), artifact_root=root)
            (root / manifest['visual_name']).chmod(0o600)
            (root / manifest['visual_name']).unlink()
            recovered = d.verify_final_receipt(receipt, artifact_root=root)
            self.assertEqual('unavailable', recovered['visual_status'])
            self.assertEqual(map_pack()['project_result']['project_identity'], recovered['project_map_bundle']['context']['project_identity'])
            self.assertEqual(map_pack()['project_result']['read_only_proof']['after_context_snapshot_hash'], recovered['project_map_bundle']['context']['context_snapshot_hash'])
            artifact.chmod(0o600)
            artifact.write_text(artifact.read_text().replace('让用户完成目标。', '改写用户目标。'))
            artifact.chmod(0o400)
            with self.assertRaises(v.ContractError): d.verify_final_receipt(receipt, artifact_root=root)

    def test_legacy_recovery_does_not_depend_on_current_template(self):
        import prepare_delivery as d
        import project_map
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifact = d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS])
            receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome='not_requested')
            with mock.patch.object(project_map, 'render_visual', side_effect=AssertionError('must not regenerate')):
                self.assertEqual('verified', d.verify_final_receipt(receipt, artifact_root=root)['visual_status'])

    def test_reopen_checks_dirty_untracked_and_unavailable_sources(self):
        import prepare_delivery as d
        from scout import inspect_git_context
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'project'; repo.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.test')
            source = repo / 'design.md'; source.write_text('original')
            git('add', 'design.md'); git('commit', '-m', 'test source')
            snapshot = inspect_git_context(repo)
            pack = map_pack(); p = pack['project_result']; proof = p['read_only_proof']
            for name in ['before_head', 'after_head']: proof[name] = snapshot['head']
            for name in ['before_context_snapshot_hash', 'after_context_snapshot_hash']: proof[name] = snapshot['context_snapshot_sha256']
            p['project_map']['source_revision'] = snapshot['head']
            pack['review_pack_hash'] = v.review_pack_hash(pack)
            manifest, artifact = d.prepare_delivery(pack, artifact_dir=root, protected_roots=[repo])
            receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome='not_requested')
            def recover(path=repo):
                result = subprocess.run([sys.executable, '-B', str(SCRIPTS/'scout.py'), 'verify-final', '--artifact-root', str(root), '--project-root', str(path)], input=receipt, text=True, encoding='utf-8', capture_output=True, check=True)
                return json.loads(result.stdout)
            self.assertEqual('unchanged', recover()['source_status'])
            source.write_text('modified'); self.assertEqual('changed', recover()['source_status'])
            source.write_text('original'); (repo/'new.txt').write_text('new evidence')
            self.assertEqual('changed', recover()['source_status'])
            missing = recover(root/'missing')
            self.assertEqual('unavailable', missing['source_status'])
            self.assertEqual('verified', missing['visual_status'])


if __name__ == '__main__': unittest.main()
