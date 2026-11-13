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
RELATIONS = {'contains': '结构归属', 'depends_on': '依赖', 'constrains': '约束', 'implements': '实现', 'handoff': '执行交接', 'evolves': '演进'}
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
    layered = project.get('contract_version') in {'global_owner_scout_project_v7', 'global_owner_scout_project_v8'}
    edges = entities('edges', {'id', 'source', 'target', 'label', 'evidence_refs', 'claims', 'card_ids'} | ({'kind'} if layered else set()))
    for node in nodes.values():
        for key in ('kind', 'summary', 'owner'): require_string(node[key], key)
    for edge in edges.values():
        require(edge['source'] in nodes and edge['target'] in nodes, 'map edge has unknown endpoint')
    if layered:
        children = {n: [] for n in nodes}
        for edge in edges.values():
            require(edge['kind'] in RELATIONS, 'invalid relation kind')
            if edge['kind'] == 'contains': children[edge['source']].append(edge['target'])
        # Only containment is acyclic; dependencies and execution may contain feedback loops.
        pending = {n: sum(n in values for values in children.values()) for n in nodes}
        ready = [n for n, count in pending.items() if count == 0]; visited = 0
        while ready:
            node = ready.pop(); visited += 1
            for child in set(children[node]):
                pending[child] -= 1
                if pending[child] == 0: ready.append(child)
        require(visited == len(nodes), 'containment cycle')
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
    context = {'purpose': p['purpose'], 'project_key': p['project_key'], 'project_map': p['project_map'],
            'project_identity': p['project_identity'], 'context_snapshot_hash': p['read_only_proof']['after_context_snapshot_hash'],
            'evidence_sources': p['evidence_sources'],
            'advice': [{'card_id': c['card_id'], 'title': c['human_context']['decision_title'],
                        'recommendation': c['human_context']['recommended_outcome'],
                        'human_context': c['human_context'], 'owner_recommendation': c['owner_recommendation'],
                        'owner_rationale': c['owner_rationale'], 'unproven': c['unproven'],
                        'recommended_action': reviews[c['project_claim_hash']]['recommended_action'],
                        'recommended_action_reason': reviews[c['project_claim_hash']]['recommended_action_reason']}
                       for c in p['project_cards']]}
    if p.get('contract_version') in {'global_owner_scout_project_v7', 'global_owner_scout_project_v8'}:
        context['project_contract'] = p['contract_version']
        for advice, card in zip(context['advice'], p['project_cards']):
            if card.get('kind') == 'engineering':
                advice.update({k: card[k] for k in ('kind', 'parent_card_id', 'alternatives', 'benefit_hypothesis',
                    'implementation_cost', 'validation_conditions', 'anti_examples', 'direct_evidence')})
    return context


def render_visual(context, pack_hash):
    payload = dict(context, report_hash=pack_hash, layer_labels=LAYERS, coverage_labels=COVERAGE, relation_labels=RELATIONS)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (Path(__file__).resolve().parent.parent / 'assets/project-map.html').read_text(encoding='utf-8')
    return template.replace('__SCOUT_ROOT__', 'scout-map-' + pack_hash[:16]).replace('__SCOUT_DATA__', encoded)


def resolve_selection(context, selection, *, journey_id=None):
    """Resolve discussion context only after the caller has verified the frozen artifact."""
    m = context['project_map']
    kind, _, id_ = selection.partition(':')
    collections = {'node': m['nodes'], 'edge': m['edges'], 'journey': m['journeys'], 'advice': context['advice']}
    if kind == 'project':
        require(id_ == context['project_key'], 'unknown selected project')
        obj = {'id': id_, 'label': m['title'], 'goal': m['goal'], 'boundary': m['boundary']}
    else:
        require(kind in collections, 'unknown selected object kind')
        obj = next((x for x in collections[kind] if x.get('id', x.get('card_id')) == id_), None)
        require(obj is not None, 'unknown selected object')
    if kind == 'journey':
        require(journey_id in (None, id_), 'conflicting selected journey')
        journey_id = id_
    journey = next((j for j in m['journeys'] if j['id'] == journey_id), None)
    require(journey_id is None or journey is not None, 'unknown selected journey')
    def prerequisites(node_ids, edge_ids):
        # Follow recorded authority/prerequisites inward, never unrelated dependent branches.
        while True:
            required = [e for e in m['edges'] if
                        (e.get('kind') in {'contains', 'constrains'} and e['target'] in node_ids) or
                        (e.get('kind') == 'depends_on' and e['source'] in node_ids)]
            expanded = node_ids | {i for e in required for i in (e['source'], e['target'])}
            edge_ids.update(e['id'] for e in required)
            if expanded == node_ids:
                break
            node_ids.update(expanded)

    journeys = []; node_ids = set(); edge_ids = set()
    for candidate in m['journeys']:
        path_edges = {e['id'] for e in m['edges'] if e['id'] in candidate['edge_ids']}
        path_nodes = {candidate['entry'], *(e['target'] for e in m['edges'] if e['id'] in path_edges)}
        prerequisites(path_nodes, path_edges)
        related = (kind in {'project', 'journey'} or
                   (kind == 'node' and id_ in path_nodes) or (kind == 'edge' and id_ in path_edges) or
                   (kind == 'advice' and (id_ in candidate['card_ids'] or any(id_ in x['card_ids'] for x in
                       [*(n for n in m['nodes'] if n['id'] in path_nodes),
                        *(e for e in m['edges'] if e['id'] in path_edges)]))))
        if journey is not None and candidate == journey:
            require(related, 'selected journey does not contain selected object')
        if related and (journey is None or candidate == journey):
            journeys.append(candidate); node_ids.update(path_nodes); edge_ids.update(path_edges)
    if kind == 'project' or not journeys or (kind == 'advice' and journey is None):
        edges = [e for e in m['edges'] if kind == 'project' or
                 (kind == 'edge' and e['id'] == id_) or
                 (kind == 'node' and id_ in (e['source'], e['target'])) or
                 (kind == 'advice' and id_ in e['card_ids'])]
        edge_ids.update(e['id'] for e in edges)
        node_ids.update(i for e in edges for i in (e['source'], e['target']))
        node_ids.update(n['id'] for n in m['nodes'] if kind == 'project' or
                        (kind == 'node' and n['id'] == id_) or (kind == 'advice' and id_ in n['card_ids']))
        prerequisites(node_ids, edge_ids)
    edges = [e for e in m['edges'] if e['id'] in edge_ids]
    nodes = [n for n in m['nodes'] if n['id'] in node_ids]
    evidence_refs = set()
    for item in [obj, *nodes, *edges, *journeys, *m['coverage']]:
        evidence_refs.update(item.get('evidence_refs', []))
        evidence_refs.update(r for c in item.get('claims', []) for r in c['evidence_refs'])
    if kind == 'advice':
        evidence_refs.update(obj['human_context']['evidence_refs'])
    sources = [dict(s, refs=[r for r in s['refs'] if r['ref'] in evidence_refs])
               for s in context['evidence_sources'] if any(r['ref'] in evidence_refs for r in s['refs'])]
    return dict({k: context[k] for k in ('purpose', 'project_key', 'project_identity', 'context_snapshot_hash', 'project_contract') if k in context},
                **{k: m[k] for k in ('goal', 'boundary', 'observed_at', 'source_revision', 'coverage')},
                object_kind=kind, object_id=id_, object=obj, journey=journey, journeys=journeys,
                nodes=nodes, edges=edges, evidence_sources=sources)


def map_bundle(pack, *, visual=None):
    context = map_context(pack)
    visual = (render_visual(context, pack['review_pack_hash']) if visual is None else visual).encode('utf-8')
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
        require_exact_keys(c, {'purpose', 'project_key', 'project_identity', 'context_snapshot_hash', 'project_map', 'evidence_sources', 'advice'} | ({'project_contract'} if 'project_contract' in c else set()), 'map context')
        require(c['purpose'] in {'inspect', 'review'}, 'invalid map purpose')
        require(c.get('project_contract') in {None, 'global_owner_scout_project_v7', 'global_owner_scout_project_v8'}, 'invalid map generation')
        validate_map(dict(contract_version=c.get('project_contract'), project_map=c['project_map'], evidence_sources=c['evidence_sources'], project_cards=c['advice'],
                          read_only_proof={'after_head': c['project_map']['source_revision']}))
        require_exact_keys(value['visual'], {'visual_name', 'visual_sha256', 'visual_bytes'}, 'visual descriptor')
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('invalid map recovery: ' + str(exc)) from exc
    return value


def markdown_map(pack, *, visual=None):
    m = pack['project_result']['project_map']
    def text(value): return html.escape(value, quote=False).replace('|', '&#124;').replace('\n', '<br>')
    lines = ['## 工程全貌', '', text(m['goal']), '', '范围：' + text(m['boundary']), '',
             f"来源版本：`{m['source_revision']}`；观察时间：{text(m['observed_at'])}。", '',
             '| 能力或参与者 | 职责 | 维护归属 | 依据 |', '| --- | --- | --- | --- |']
    for n in m['nodes']:
        lines.append('| ' + ' | '.join(text(x) for x in (n['label'], n['summary'], n['owner'], '、'.join(n['evidence_refs']))) + ' |')
    nodes = {n['id']: n for n in m['nodes']}; edges = {e['id']: e for e in m['edges']}
    if pack['project_result'].get('contract_version') in {'global_owner_scout_project_v7', 'global_owner_scout_project_v8'}:
        lines += ['', '### 结构、依赖与演进', '', '| 起点 | 关系 | 终点 | 说明 | 依据 |', '| --- | --- | --- | --- | --- |']
        for edge in m['edges']:
            lines.append('| ' + ' | '.join(text(x) for x in (nodes[edge['source']]['label'], RELATIONS[edge['kind']], nodes[edge['target']]['label'], edge['label'], '、'.join(edge['evidence_refs']))) + ' |')
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
    lines += ['', MAP_START + canonical_json(map_bundle(pack, visual=visual)).decode('utf-8') + MAP_END, '']
    return lines
