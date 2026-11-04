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


def layered_pack():
    """A source-backed architectural hypothesis, without a fabricated acceptance event."""
    pack = map_pack('review'); p = pack['project_result']
    p.update(contract_version='global_owner_scout_project_v7', status='ok')
    original = v.build_card()
    card = {k: copy.deepcopy(original[k]) for k in (
        'card_id', 'human_context', 'evidence_level', 'normalized_evidence_hash',
        'owner_recommendation', 'direct_evidence', 'owner_rationale', 'anti_examples',
        'privacy_check', 'unproven')}
    card.update(kind='engineering', parent_card_id=None, evidence_level='E1', owner_recommendation='project_owner',
                direct_evidence=[dict(type='owner', ref='owner:current', summary='执行入口与消费者之间存在可核对的重复职责。')],
                benefit_hypothesis='共享稳定机制可能减少跨入口漂移，收益尚待验证。',
                implementation_cost='需要调整执行边界并保留既有消费者的兼容路径。',
                validation_conditions=['比较当前入口与候选执行边界的结果和恢复成本。'],
                alternatives=[dict(approach='保留当前分工', tradeoff='变更成本较低，但跨入口维护仍然分散。'),
                              dict(approach='重构共享执行边界', tradeoff='统一稳定语义，但迁移和失败隔离需要验证。')])
    card['direct_evidence'] = copy.deepcopy(p['evidence_sources'][1]['refs'])
    card['human_context'].update(decision_title='是否重构共享执行边界？', evidence_refs=['owner:current'],
                                 recommended_outcome='比较保留现状与共享执行边界，先验证跨入口的实际差异。')
    card['normalized_evidence_hash'] = v.canonical_hash(card['direct_evidence'])
    card['project_claim_hash'] = v.canonical_hash(card)
    p.update(events=[], project_cards=[card], observations=[dict(observation_id='architecture', evidence_level='E1',
        summary='从源码与目标之间的关系提出工程假设，无已接受变更。', direct_evidence=card['direct_evidence'], event_ids=[],
        disposition=dict(kind='candidate', reason='交接边界可比较，尚无实施授权。', card_ids=[card['card_id']],
                         owner_refs=['owner:current'], local_scope='本工程执行边界。', portable_delta='暂无新增全局行为义务。'))])
    p['project_map']['edges'][0]['kind'] = 'contains'
    p['project_map']['nodes'][0]['card_ids'] = [card['card_id']]
    pack.update(contract_version='global_owner_scout_review_pack_v8', status='ok', owner_parity=None,
                review_cards=[dict(project_claim_hash=card['project_claim_hash'], selection_token=None,
                    recommended_action='discuss', recommended_action_reason='按项目维护归属讨论，收益仍需验证。',
                    integration_preview=None, expected_behavior_change='可比较共享机制和保留现状。', allowed_actions=[])])
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    return pack


def browser_packs():
    """Public, synthetic cross-project inputs for the native-preview browser check."""
    real = map_pack(); m = real['project_result']['project_map']
    m.update(title='离线校对工具', goal='从导入、校对到下游消费，并能够回滚。')
    template = m['nodes'][0]
    m['nodes'] = [dict(copy.deepcopy(template), id=id_, label=label, owner=owner)
                  for id_, label, owner in [('entry', '导入入口', '导入模块'), ('review', '人工校对', '校对模块'),
                      ('owner', '已确认结果', '结果文件'), ('consumer', '下游消费者', '消费工具'), ('rollback', '回滚入口', '恢复工具')]]
    edge = m['edges'][0]
    m['edges'] = [dict(copy.deepcopy(edge), id=id_, source=source, target=target, label=label)
                  for id_, source, target, label in [('load', 'entry', 'review', '导入内容'),
                      ('accept', 'review', 'owner', '确认结果'), ('adopt', 'owner', 'consumer', '消费与采用'),
                      ('restore', 'rollback', 'owner', '恢复结果')]]
    journey = m['journeys'][0]
    m['journeys'] = [dict(copy.deepcopy(journey), id='ordinary', label='导入并消费', edge_ids=['load', 'accept', 'adopt']),
                      dict(copy.deepcopy(journey), id='revoke', label='回滚与撤销', entry='rollback', edge_ids=['restore', 'adopt'])]
    advice = v.valid_review_pack()
    advice.update(contract_version='global_owner_scout_review_pack_v7')
    advice['project_result'].update(contract_version='global_owner_scout_project_v6', purpose='review', project_map=map_project()['project_map'])
    advice['project_result']['project_map']['nodes'][0]['card_ids'] = [advice['project_result']['project_cards'][0]['card_id']]
    other = map_pack(); m = other['project_result']['project_map']
    m.update(title='离线数据校对', goal='将导入数据交给人工校对后导出。')
    m['nodes'][0].update(label='离线导入', owner='导入模块')
    m['nodes'][1].update(label='人工校对与导出', owner='校对工具')
    unknown = copy.deepcopy(other); unknown['project_result']['project_map']['journeys'] = []
    result = dict(real=real, advice=advice, other=other, unknown=unknown)
    for pack in result.values():
        pack['review_pack_hash'] = v.review_pack_hash(pack)
        v.validate_review_pack(pack)
    return result


def layered_browser_pack():
    pack = layered_pack(); p = pack['project_result']; card = p['project_cards'][0]
    card['card_id'] = 'candidate\"quote'
    card['project_claim_hash'] = v.project_claim_hash(card)
    p['project_map']['nodes'][0]['card_ids'] = [card['card_id']]
    p['observations'][0]['disposition']['card_ids'] = [card['card_id']]
    pack['review_cards'][0]['project_claim_hash'] = card['project_claim_hash']
    p['project_map']['edges'][0]['kind'] = 'handoff'
    child = copy.deepcopy(card); child.update(card_id='child-advice', parent_card_id=card['card_id'])
    child['human_context']['decision_title'] = '执行消费者如何分阶段迁移？'
    child['anti_examples'].append('只读消费者没有执行状态时无需搬迁。')
    child['project_claim_hash'] = v.project_claim_hash(child)
    p['project_cards'].append(child)
    observation = copy.deepcopy(p['observations'][0]); observation['observation_id'] = 'child'
    observation['disposition']['card_ids'] = [child['card_id']]; p['observations'].append(observation)
    review = copy.deepcopy(pack['review_cards'][0]); review['project_claim_hash'] = child['project_claim_hash']; pack['review_cards'].append(review)
    p['project_map']['nodes'][1]['card_ids'] = [child['card_id']]
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    return pack


def nested_journey_pack():
    """Sanitized real failure shape: handoffs exist only below collapsed groups."""
    pack = layered_browser_pack(); m = pack['project_result']['project_map']
    template = m['nodes'][0]
    m['nodes'] += [dict(copy.deepcopy(template), id=id_, label=label, summary=summary, card_ids=[])
                   for id_, label, summary in [('authoring', '准备内容', '整理输入并交给下游。'),
                       ('delivery', '消费结果', '使用准确的输入并读回结果。'),
                       ('draft', '草稿', '在同一职责内校对草稿。')]]
    edge = m['edges'][0]
    m['edges'] += [dict(copy.deepcopy(edge), id=id_, source=source, target=target, kind=kind, card_ids=[])
                  for id_, source, target, kind in [('owns-entry', 'authoring', 'entry', 'contains'),
                      ('owns-draft', 'authoring', 'draft', 'contains'),
                      ('owns-consumer', 'delivery', 'consumer', 'contains'),
                      ('internal', 'draft', 'entry', 'handoff')]]
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    v.validate_review_pack(pack)
    return pack


def shared_parent_pack(reverse=False):
    pack = nested_journey_pack(); m = pack['project_result']['project_map']
    m['edges'].append(dict(copy.deepcopy(m['edges'][1]), id='shared-entry', source='delivery', target='entry'))
    if reverse:
        m['edges'].reverse()
    pack['review_pack_hash'] = v.review_pack_hash(pack)
    v.validate_review_pack(pack)
    return pack


class ScoutProjectMapTests(unittest.TestCase):
    def test_review_brief_explains_the_system_before_recommendations(self):
        from render_review import render_conversation_brief
        pack = layered_pack()
        brief = render_conversation_brief(pack)
        self.assertLess(brief.index(pack['project_result']['project_map']['goal']), brief.index('项建议'))
        self.assertIn('用户入口 → 实际消费者', brief)
        self.assertIn('消费者取得结果。', brief)

    def test_continuation_resolves_frozen_objects_and_visible_journey(self):
        from project_map import map_context, resolve_selection
        context = map_context(layered_browser_pack())
        result = resolve_selection(context, 'project:' + context['project_key'], journey_id='ordinary')
        self.assertEqual('project', result['object_kind'])
        self.assertEqual('ordinary', result['journey']['id'])
        self.assertEqual(['entry', 'consumer'], [n['id'] for n in result['nodes']])
        self.assertTrue(result['evidence_sources'])
        for selection in ('node:entry', 'edge:handoff', 'advice:child-advice', 'journey:ordinary'):
            self.assertTrue(resolve_selection(context, selection)['evidence_sources'])
        for selection in ('node:overview', 'node:missing', 'project:another', 'edge:missing'):
            with self.subTest(selection=selection), self.assertRaises(v.ContractError):
                resolve_selection(context, selection)
        with self.assertRaises(v.ContractError):
            resolve_selection(context, 'node:entry', journey_id='missing')
        for n in context['project_map']['nodes']:
            n['card_ids'] = []
        context['project_map']['journeys'][0]['card_ids'] = ['child-advice']
        result = resolve_selection(context, 'advice:child-advice')
        self.assertEqual(['entry', 'consumer'], [n['id'] for n in result['nodes']])
        self.assertEqual('ordinary', result['journeys'][0]['id'])
        nested = map_context(nested_journey_pack())
        legacy = map_context(map_pack())
        self.assertEqual('entry', resolve_selection(legacy, 'node:entry', journey_id=legacy['project_map']['journeys'][0]['id'])['object_id'])
        self.assertEqual('authoring', resolve_selection(nested, 'node:authoring', journey_id='ordinary')['object_id'])
        for selection in ('node:draft', 'edge:internal'):
            with self.subTest(selection=selection), self.assertRaises(v.ContractError):
                resolve_selection(nested, selection, journey_id='ordinary')

    def test_system_recommendation_does_not_invent_a_rule_or_accepted_change(self):
        import prepare_review
        import prepare_delivery as d
        pack = layered_pack()
        with mock.patch.object(prepare_review, 'resolve', side_effect=AssertionError('unrelated Owner')):
            self.assertEqual(pack, prepare_review.prepare_review(pack, codex_home=Path('unused')))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifact = d.prepare_delivery(pack, artifact_dir=root, protected_roots=[SCRIPTS])
            receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome='not_requested')
            recovered = d.verify_final_receipt(receipt, artifact_root=root)
            self.assertEqual([0], manifest['visible_action_counts'])
            self.assertIn('首项建议', receipt)
            body = artifact.read_text(encoding='utf-8')
            self.assertIn('收益假设', body)
            self.assertNotIn('接受后的准确规则', body)
            self.assertIsNone(recovered['recovery_bundle'])
            self.assertEqual('engineering', recovered['project_map_bundle']['context']['advice'][0]['kind'])

    def test_hierarchy_and_typed_relations_preserve_unknowns_without_invented_depth(self):
        p = layered_pack()['project_result']
        v.validate_project(p)
        p['project_map']['journeys'] = []
        v.validate_project(p)
        p['project_map']['edges'][0]['target'] = 'entry'
        with self.assertRaises(v.ContractError): v.validate_project(p)

    def test_engineering_subtree_and_full_counterevidence_survive_projection(self):
        from project_map import map_context
        from render_review import render_conversation_brief
        pack = layered_browser_pack(); v.validate_review_pack(pack)
        brief = render_conversation_brief(pack)
        self.assertIn('按 1 项主建议展开', brief)
        self.assertNotIn('执行消费者如何分阶段迁移？', brief)
        projected = map_context(pack)['advice'][1]
        self.assertEqual(pack['project_result']['project_cards'][0]['card_id'], projected['parent_card_id'])
        self.assertIn('只读消费者没有执行状态时无需搬迁。', projected['anti_examples'])
        self.assertEqual(pack['project_result']['project_cards'][1]['direct_evidence'], projected['direct_evidence'])
        broken = copy.deepcopy(pack); broken['project_result']['project_cards'][0]['parent_card_id'] = 'child-advice'
        with self.assertRaises(v.ContractError): v.validate_review_pack(broken)

    def test_engineering_advice_cannot_create_global_authority(self):
        for field, value in [('owner_recommendation', 'global_agents'), ('rule_payload', v.build_card()['rule_payload'])]:
            pack = layered_pack(); card = pack['project_result']['project_cards'][0]; card[field] = value
            card['project_claim_hash'] = v.project_claim_hash(card)
            with self.subTest(field=field), self.assertRaises(v.ContractError): v.validate_project(pack['project_result'])
        pack = layered_pack(); pack['review_cards'][0]['allowed_actions'] = ['confirm']
        with self.assertRaises(v.ContractError): v.validate_review_pack(pack)

    def test_mixed_pack_plans_only_rule_candidates(self):
        pack = v.valid_review_pack(); engineering = layered_pack()
        p = pack['project_result']
        p.update(contract_version='global_owner_scout_project_v7', purpose='review',
                 project_map=copy.deepcopy(engineering['project_result']['project_map']))
        card = engineering['project_result']['project_cards'][0]
        card['card_id'] = 'engineering-only'; card['project_claim_hash'] = v.project_claim_hash(card)
        p['project_map']['nodes'][0]['card_ids'] = [card['card_id']]
        p['project_cards'].append(card)
        observation = engineering['project_result']['observations'][0]
        observation['disposition']['card_ids'] = [card['card_id']]; p['observations'].append(observation)
        review = engineering['review_cards'][0]; review['project_claim_hash'] = card['project_claim_hash']
        pack['review_cards'].append(review); pack['contract_version'] = 'global_owner_scout_review_pack_v8'
        pack['review_pack_hash'] = v.review_pack_hash(pack)
        v.validate_review_pack(pack)
        self.assertEqual([c['card_id'] for c in p['project_cards'][:-1]], [c['card_id'] for c in v.review_bundle(pack)['items']])
        from render_review import render_review_pack
        from verify_visible_output import verify_visible_output
        self.assertEqual([5, 5, 0], verify_visible_output(render_review_pack(pack, surface='interactive'), surface='interactive')['visible_action_counts'])

    def test_actual_delivery_reply_recovers_without_manual_receipt_extraction(self):
        import prepare_delivery as d
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifact = d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS])
            original = artifact.read_bytes()
            linked_receipt = ('修复已完成。完整依据与回执见 [回执](receipt.md)。\n\n'
                              'visualize{"path":"' + str(root / manifest['visual_name']) + '"}\n')
            with self.assertRaises(v.ContractError):
                d.verify_final_receipt(linked_receipt, artifact_root=root)
            for outcome in d.SURFACE_COPY:
                receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root, outcome=outcome)
                # Actual delivery shape: source/release closeout, exact receipt, inline map, host footer.
                final = ('发布与部署已完成。\n\n- 后续采用仍未证。\n\n'
                         'visualize{"path":"unrelated-chart.html"}\n\n'
                         '交付回执：工程代码已交付。\n\n' + receipt + '\n本轮没有用户测试操作。\n')
                with self.subTest(outcome=outcome):
                    recovered = d.verify_final_receipt(final, artifact_root=root)
                    self.assertEqual(d.verify_final_receipt(receipt, artifact_root=root), recovered)
                    self.assertFalse(recovered['confirmation_eligible'])
                    self.assertEqual(original, artifact.read_bytes())
                for invalid in [final.replace('让用户完成目标。', '已证明用户采用。'),
                                final + receipt,
                                final.replace(manifest['visual_name'], 'another.html').replace('\nvisualize{"path": ', '\n  \n  visualize{"path": '),
                                final.replace(manifest['visual_name'], 'another.html')]:
                    with self.subTest(invalid=invalid[-100:]), self.assertRaises(v.ContractError):
                        d.verify_final_receipt(invalid, artifact_root=root)

    def test_native_presentation_can_vary_without_changing_evidence_or_recovery(self):
        import prepare_delivery as d
        from project_map import resolve_selection
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment = '<section id="state-comparison"><h2>运行状态对照</h2><p>当前仅有设计依据。</p></section>'
            visual = root / 'state-comparison.html'
            visual.write_text(fragment, encoding='utf-8')
            manifest, artifact = d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS], visual_input=visual)
            self.assertEqual(fragment, (root / manifest['visual_name']).read_text(encoding='utf-8'))
            for text_only in (False, True):
                receipt = d.render_delivery_receipt(manifest, artifact_path=artifact, artifact_root=root,
                                                    outcome='not_requested', text_only=text_only)
                self.assertEqual(not text_only, 'visualize' in receipt)
                recovered = d.verify_final_receipt(receipt, artifact_root=root)
                self.assertEqual('verified', recovered['visual_status'])
                context = recovered['project_map_bundle']['context']
                self.assertEqual('entry', resolve_selection(context, 'node:entry')['object']['id'])
                self.assertFalse(recovered['confirmation_eligible'])
            visual.write_text('<p>Changed presentation</p>', encoding='utf-8')
            with self.assertRaises(v.ContractError):
                d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS], visual_input=visual)
            with self.assertRaises(v.ContractError):
                d.prepare_delivery(map_pack(), artifact_dir=root, protected_roots=[SCRIPTS], visual_input=Path(__file__).resolve())

    def test_cross_project_and_partial_topologies_are_valid(self):
        packs = browser_packs()
        self.assertEqual([2, 1, 1, 0], [len(p['project_result']['project_map']['journeys']) for p in packs.values()])

    def test_visual_advice_preserves_context_and_current_disposition(self):
        from project_map import map_context
        pack = v.valid_review_pack()
        card = pack['project_result']['project_cards'][0]
        pack['project_result'].update(purpose='review', project_map=map_project()['project_map'])
        advice = map_context(pack)['advice'][0]
        self.assertEqual(card['human_context'], advice['human_context'])
        self.assertEqual(card['owner_rationale'], advice['owner_rationale'])
        self.assertEqual(card['owner_recommendation'], advice['owner_recommendation'])
        self.assertEqual(pack['review_cards'][0]['recommended_action'], advice['recommended_action'])
        self.assertEqual(pack['review_cards'][0]['recommended_action_reason'], advice['recommended_action_reason'])
        self.assertNotIn('selection_token', advice)
        self.assertNotIn('rule_payload', advice)

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
            for pack in [v.valid_review_pack(), map_pack(), map_pack('review'), layered_pack()]:
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
            artifact.write_text(artifact.read_text(encoding='utf-8').replace('让用户完成目标。', '改写用户目标。'), encoding='utf-8')
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


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--browser-fixtures':
        from project_map import map_context, render_visual
        output = Path(sys.argv[2]); output.mkdir(parents=True, exist_ok=True)
        for name, pack in dict(browser_packs(), layered=layered_browser_pack()).items():
            (output / (name + '-map.html')).write_text(render_visual(map_context(pack), pack['review_pack_hash']), encoding='utf-8')
    else:
        unittest.main()
