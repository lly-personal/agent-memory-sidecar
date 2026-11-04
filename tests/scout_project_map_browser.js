async (win) => {
 const d=win.document,root=d.querySelector('article'),source=JSON.parse(root.querySelector('[type="application/json"]').textContent);
 const checks=[],ok=(name,value)=>{if(!value)throw Error(name);checks.push(name);};
 const click=s=>{const el=root.querySelector(s);if(!el)throw Error('missing '+s);el.click();};
 const frame=()=>new Promise(r=>win.requestAnimationFrame(r));
 const saves=[],messages=[];win.openai={setWidgetState:v=>{saves.push(v);},sendFollowUpMessage:async v=>messages.push(v)};
 const teaser=root.querySelector('.at-advice-teaser [data-advice]');
 if(teaser){ok('teaser retains exact advice identity',source.advice.some(a=>a.card_id===teaser.dataset.advice));teaser.click();ok('teaser opens exact advice',saves.at(-1).privateContent.state.advice===teaser.dataset.advice);click('[data-action="back"]');}
 ok('overview names target goal',root.querySelector('h1').textContent===source.project_map.title&&root.textContent.includes(source.project_map.goal));
 const relations=source.project_map.edges.filter(e=>e.kind!=='contains');
 ok('collapsed overview preserves descendant relations',relations.every(e=>[...root.querySelectorAll('.at-crosslinks [data-edge]')].some(b=>b.dataset.edge===e.id)));
 click('[data-action="discuss"]');await frame();
 ok('overview resolves project rather than synthetic node',messages.at(-1).prompt.includes('project:'+source.project_key));
 if(source.project_map.journeys.length){
  const visible=root.querySelector('[data-visible-journey]').dataset.visibleJourney;
  ok('default displayed journey enters continuation',messages.at(-1).prompt.includes('路径 '+visible));
  click('[data-view="path"]');
  ok('default displayed journey enters model state',saves.at(-1).modelContent.journey_id===root.querySelector('#atlas-journey').value);
  const journey=source.project_map.journeys.find(j=>j.id===root.querySelector('#atlas-journey').value);
  ok('entry behavior is visible before the first handoff',source.project_map.nodes.find(n=>n.id===journey.entry).claims.every(c=>[...root.querySelectorAll('[data-step-claim]')].some(p=>p.textContent.includes(c.statement))));
  ok('normal path explains source-backed consequences',journey.edge_ids.every(id=>source.project_map.edges.find(e=>e.id===id).claims.every(c=>[...root.querySelectorAll('[data-step-claim]')].some(p=>p.textContent.includes(c.statement)))));
  click('[data-action="back"]');
 }
 click('[data-view="graph"]');await frame();
 const type=root.querySelector('#atlas-relation')?.value;
 const shared=source.project_map.nodes.filter(n=>source.project_map.edges.filter(e=>e.kind==='contains'&&e.target===n.id).length>1&&relations.some(e=>(e.kind||'handoff')===type&&(e.source===n.id||e.target===n.id)));
 ok('shared ownership does not choose an arbitrary parent',shared.every(n=>[...root.querySelectorAll('[data-graph-node]')].some(el=>el.dataset.graphNode===n.id)));
 ok('graph retains exact selected-type relations',relations.filter(e=>(e.kind||'handoff')===type).every(e=>[...root.querySelectorAll('.at-network-summary [data-edge]')].some(b=>b.dataset.edge===e.id)));
 if(root.querySelector('[data-expand]')){const count=root.querySelectorAll('[data-graph-node]').length;click('[data-expand]');ok('expansion retains overview scope',saves.at(-1).privateContent.state.node===saves.at(-2).privateContent.state.node);click('[data-action="back"]');ok('return restores graph frontier',root.querySelectorAll('[data-graph-node]').length===count);}
 click('[data-action="back"]');
 messages.length=0;
 click('[data-view="evidence"]');
 const relationEntry=root.querySelector('.at-table [data-edge]');
 if(relationEntry){const expected=relationEntry.dataset.edge;relationEntry.click();ok('evidence preserves relationship identity',saves.at(-1).modelContent.object_kind==='edge'&&saves.at(-1).modelContent.object_id===expected);click('[data-action="back"]');}
 click('[data-action="back"]');
 const initialJourney=source.project_map.journeys[0];
 if(initialJourney){
  const outside=source.project_map.edges.find(e=>e.kind!=='contains'&&!initialJourney.edge_ids.includes(e.id));
  if(outside){click('[data-view="evidence"]');click('.at-table [data-edge="'+outside.id+'"]');ok('unrelated relation clears previous journey',saves.at(-1).modelContent.journey_id===null);click('[data-action="back"]');click('[data-action="back"]');}
 }
 const sharedNode=source.project_map.nodes.find(n=>source.project_map.edges.filter(e=>e.kind==='contains'&&e.target===n.id).length>1);
 if(sharedNode){
  const parents=source.project_map.edges.filter(e=>e.kind==='contains'&&e.target===sharedNode.id).map(e=>e.source);
  const entered=parents.at(-1),parent=source.project_map.nodes.find(n=>n.id===entered);
  click('.at-branches [data-node="'+entered+'"]');click('.at-node-list [data-node="'+sharedNode.id+'"]');
  ok('shared breadcrumb preserves entered parent',root.querySelector('.at-breadcrumb').textContent.includes(parent.label));
  click('[data-action="back"]');click('[data-action="back"]');
 }
 click('.at-branches [data-node]');
 const selected=saves.at(-1);ok('navigation binds same report',selected.modelContent.report_hash===source.report_hash);
 click('[data-view="evidence"]');
 const snapshot=saves.at(-1),focused=d.activeElement;let mutations=0;
 const observer=new win.MutationObserver(ms=>mutations+=ms.length);observer.observe(root,{subtree:true,childList:true});
 win.dispatchEvent(new win.CustomEvent('openai:set_globals',{detail:{globals:{widgetState:snapshot}}}));await frame();observer.disconnect();
 ok('same snapshot causes zero redraws',mutations===0);ok('same snapshot preserves focused element',d.activeElement===focused&&focused.isConnected);
 const priorCount=saves.length;click('[data-view="evidence"]');ok('same selection does not save or rerender',saves.length===priorCount&&d.activeElement===focused);
 const changed=structuredClone(snapshot);changed.modelContent.report_hash='other';changed.privateContent.state.view='path';
 win.dispatchEvent(new win.CustomEvent('openai:set_globals',{detail:{globals:{widgetState:changed}}}));
 ok('other report state ignored',root.querySelector('[aria-pressed="true"]').dataset.view==='evidence');
 click('[data-view="relations"]');
 if(root.querySelector('[data-edge]')){click('[data-edge]');ok('relation identity retained',saves.at(-1).modelContent.object_kind==='edge');}
 click('[data-action="discuss"]');await frame();
 ok('discussion binds report object and no authority',messages.length===1&&messages[0].prompt.includes(source.report_hash)&&messages[0].prompt.includes('不要重跑普查')&&messages[0].prompt.includes('不要将本次讨论视为写入授权'));
 ok('no unsupported scroll option assumed',!Object.hasOwn(messages[0],'scrollToBottom'));
 win.openai.sendFollowUpMessage=async()=>{throw Error('unavailable');};click('[data-action="discuss"]');await frame();
 ok('failed discussion preserves exact identity',root.querySelector('.at-status').textContent.includes(source.report_hash));
 win.dispatchEvent(new win.CustomEvent('openai:set_globals',{detail:{globals:{widgetState:snapshot}}}));
 ok('changed valid snapshot restores view',root.querySelector('[aria-pressed="true"]').dataset.view==='evidence');
 const savedNode=snapshot.modelContent.object_id;
 if(source.advice.length){
  click('[data-view="advice"]');const entry=root.querySelector('[data-advice]:not([data-advice=""])');
  if(entry){entry.click();ok('advice retains cost and counterexample',root.textContent.includes('代价：')&&root.textContent.includes('保留或删除的条件：'));
   const child=root.querySelector('.at-reading [data-advice]');if(child){child.click();ok('layered advice retains parent',root.querySelectorAll('.at-advice-path [data-advice]').length>=3);}
   click('[data-action="back"]');ok('return retains originating object',saves.at(-1).privateContent.state.node===savedNode);}
 }
 // This tests our code inside a local browser fixture, not the Desktop chat's scroll controller.
 const bound=win.document.documentElement;ok('content fits viewport',bound.scrollWidth<=win.innerWidth+1);
 return {checks,source:source.project_key,report:source.report_hash,echoMutations:mutations,hostChatScroll:'not_observed'};
}
