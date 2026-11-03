"""Evidence-bound project views; no discovery, authority or persistent UI state."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

from validate_output import (ContractError, canonical_json, require, require_exact_keys,
    require_list, require_object, require_string, validate_iso)

LAYERS = {'design': '设计规定', 'implementation': '实现事实', 'observed': '运行观察',
          'inference': '推断', 'unknown': '未知'}
COVERAGE = {'covered': '已覆盖', 'partial': '部分覆盖', 'unknown': '未知', 'not_applicable': '不适用'}
MAP_START = '<!-- scout:map:start -->\n<details>\n<summary>图谱恢复数据</summary>\n\n```text\n'
MAP_END = '\n```\n\n</details>\n<!-- scout:map:end -->'
IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')


def validate_map(project):
    m = require_object(project['project_map'], 'project_map')
    require_exact_keys(m, {'title', 'goal', 'boundary', 'observed_at', 'source_revision', 'nodes', 'edges', 'journeys', 'coverage'}, 'project_map')
    for key in ('title', 'goal', 'boundary'): require_string(m[key], key)
    validate_iso(m['observed_at'], 'observed_at')
    require(m['source_revision'] == project['read_only_proof']['after_head'], 'map source_revision does not bind project HEAD')
    refs = {r['ref'] for s in project['evidence_sources'] if s['status'] in {'available', 'degraded'} for r in s['refs']}
    cards = {c['card_id'] for c in project['project_cards']}

    def evidence(obj, *, nonempty=True):
        values = require_list(obj['evidence_refs'], 'evidence_refs', nonempty=nonempty)
        require(all(isinstance(x, str) for x in values) and len(values) == len(set(values)), 'duplicate or invalid map evidence')
        require(set(values) <= refs, 'map evidence is undeclared or unavailable')

    def links(obj):
        ids = require_list(obj['card_ids'], 'card_ids')
        require(all(isinstance(x, str) for x in ids) and len(ids) == len(set(ids)) and set(ids) <= cards, 'map advice is not an actual Project Card')
        evidence(obj)

    def entities(kind, fields):
        result = {}
        for obj in require_list(m[kind], kind, nonempty=kind == 'nodes'):
            require_object(obj, kind)
            require_exact_keys(obj, fields, kind)
            id_ = require_string(obj['id'], 'id')
            require(IDENTIFIER.fullmatch(id_) is not None and id_ not in result, 'map IDs must be safe and unique')
            require_string(obj['label'], 'label'); links(obj)
            result[id_] = obj
        return result

    nodes = entities('nodes', {'id', 'label', 'kind', 'summary', 'owner', 'evidence_refs', 'claims', 'card_ids'})
    edges = entities('edges', {'id', 'source', 'target', 'label', 'evidence_refs', 'claims', 'card_ids'})
    for node in nodes.values():
        for key in ('kind', 'summary', 'owner'): require_string(node[key], key)
    for edge in edges.values():
        require(edge['source'] in nodes and edge['target'] in nodes, 'map edge has unknown endpoint')
    for obj in [*nodes.values(), *edges.values()]:
        for claim in require_list(obj['claims'], 'claims', nonempty=True):
            require_exact_keys(require_object(claim, 'claim'), {'layer', 'environment', 'statement', 'evidence_refs'}, 'claim')
            require(claim['layer'] in LAYERS, 'invalid evidence layer')
            for key in ('environment', 'statement'): require_string(claim[key], key)
            evidence(claim, nonempty=claim['layer'] != 'unknown')
    journeys = entities('journeys', {'id', 'label', 'entry', 'edge_ids', 'outcome', 'recovery', 'evidence_refs', 'card_ids'})
    for journey in journeys.values():
        cursor = journey['entry']; require(cursor in nodes, 'unknown journey entry')
        for id_ in require_list(journey['edge_ids'], 'edge_ids', nonempty=True):
            require(id_ in edges and edges[id_]['source'] == cursor, 'journey must follow connected directed edges')
            cursor = edges[id_]['target']
        for key in ('outcome', 'recovery'): require_string(journey[key], key)
    dimensions = set()
    for item in require_list(m['coverage'], 'coverage', nonempty=True):
        require_exact_keys(require_object(item, 'coverage'), {'dimension', 'status', 'explanation', 'evidence_refs'}, 'coverage')
        require_string(item['dimension'], 'dimension'); require_string(item['explanation'], 'explanation')
        require(item['dimension'] not in dimensions and item['status'] in COVERAGE, 'invalid coverage dimension')
        dimensions.add(item['dimension']); evidence(item, nonempty=item['status'] in {'covered', 'partial'})
    return m


def map_context(pack):
    p = pack['project_result']
    reviews = {r['project_claim_hash']: r for r in pack['review_cards']}
    return {'purpose': p['purpose'], 'project_key': p['project_key'], 'project_map': p['project_map'],
            'project_identity': p['project_identity'], 'context_snapshot_hash': p['read_only_proof']['after_context_snapshot_hash'],
            'evidence_sources': p['evidence_sources'],
            'advice': [{'card_id': c['card_id'], 'title': c['human_context']['decision_title'],
                        'recommendation': c['human_context']['recommended_outcome'],
                        'human_context': c['human_context'], 'owner_recommendation': c['owner_recommendation'],
                        'owner_rationale': c['owner_rationale'], 'unproven': c['unproven'],
                        'recommended_action': reviews[c['project_claim_hash']]['recommended_action'],
                        'recommended_action_reason': reviews[c['project_claim_hash']]['recommended_action_reason']}
                       for c in p['project_cards']]}


def render_visual(context, pack_hash):
    payload = dict(context, report_hash=pack_hash, layer_labels=LAYERS, coverage_labels=COVERAGE)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (Path(__file__).resolve().parent.parent / 'assets/project-map.html').read_text(encoding='utf-8')
    return template.replace('__SCOUT_ROOT__', 'scout-map-' + pack_hash[:16]).replace('__SCOUT_DATA__', encoded)


def map_bundle(pack):
    context = map_context(pack)
    visual = render_visual(context, pack['review_pack_hash']).encode('utf-8')
    return {'context': context, 'visual': {'visual_name': 'scout-project-map-' + pack['review_pack_hash'][:16] + '.html',
            'visual_sha256': hashlib.sha256(visual).hexdigest(), 'visual_bytes': len(visual)}}


def recover_map(body):
    if MAP_START not in body and MAP_END not in body: return None
    require(body.count(MAP_START) == body.count(MAP_END) == 1, 'map recovery block is duplicated or incomplete')
    data, end, _ = body.partition(MAP_START)[2].partition(MAP_END)
    require(bool(end), 'map recovery block is incomplete')
    try:
        value = json.loads(data)
        require(canonical_json(value).decode('utf-8') == data, 'map recovery is not canonical')
        require_exact_keys(value, {'context', 'visual'}, 'map recovery')
        c = value['context']
        require_exact_keys(c, {'purpose', 'project_key', 'project_identity', 'context_snapshot_hash', 'project_map', 'evidence_sources', 'advice'}, 'map context')
        require(c['purpose'] in {'inspect', 'review'}, 'invalid map purpose')
        validate_map(dict(project_map=c['project_map'], evidence_sources=c['evidence_sources'], project_cards=c['advice'],
                          read_only_proof={'after_head': c['project_map']['source_revision']}))
        require_exact_keys(value['visual'], {'visual_name', 'visual_sha256', 'visual_bytes'}, 'visual descriptor')
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('invalid map recovery: ' + str(exc)) from exc
    return value


def markdown_map(pack):
    m = pack['project_result']['project_map']
    def text(value): return html.escape(value, quote=False).replace('|', '&#124;').replace('\n', '<br>')
    lines = ['## 工程全貌', '', text(m['goal']), '', '范围：' + text(m['boundary']), '',
             f"来源版本：`{m['source_revision']}`；观察时间：{text(m['observed_at'])}。", '',
             '| 能力或参与者 | 职责 | 维护归属 | 依据 |', '| --- | --- | --- | --- |']
    for n in m['nodes']:
        lines.append('| ' + ' | '.join(text(x) for x in (n['label'], n['summary'], n['owner'], '、'.join(n['evidence_refs']))) + ' |')
    nodes = {n['id']: n for n in m['nodes']}; edges = {e['id']: e for e in m['edges']}
    lines += ['', '### 关键路径', '']
    for j in m['journeys']:
        lines += ['**' + text(j['label']) + '**', '', text(nodes[j['entry']]['label'])]
        for eid in j['edge_ids']:
            e = edges[eid]; lines.append('→ ' + text(e['label']) + ' → ' + text(nodes[e['target']]['label']))
        lines += ['', '结果：' + text(j['outcome']), '', '恢复与例外：' + text(j['recovery']), '']
    lines += ['### 能力与环境矩阵', '', '| 对象 | 证据层次 | 环境 | 事实或未证范围 | 依据 |', '| --- | --- | --- | --- | --- |']
    for obj in [*m['nodes'], *m['edges']]:
        for c in obj['claims']:
            lines.append('| ' + ' | '.join(text(x) for x in (obj['label'], LAYERS[c['layer']], c['environment'], c['statement'], '、'.join(c['evidence_refs']))) + ' |')
    lines += ['', '### 覆盖边界', '']
    for c in m['coverage']: lines.append('- ' + text(c['dimension']) + '：' + COVERAGE[c['status']] + '。' + text(c['explanation']))
    lines += ['', MAP_START + canonical_json(map_bundle(pack)).decode('utf-8') + MAP_END, '']
    return lines
