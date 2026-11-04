async (win) => {
 const d=win.document,root=d.querySelector('article'),source=JSON.parse(root.querySelector('[type="application/json"]').textContent);
 const checks=[],ok=(name,value)=>{if(!value)throw Error(name);checks.push(name);};
 const click=s=>{const el=root.querySelector(s);if(!el)throw Error('missing '+s);el.click();};
 const frame=()=>new Promise(r=>win.requestAnimationFrame(r));
 const saves=[],messages=[];win.openai={setWidgetState:v=>{saves.push(v);},sendFollowUpMessage:async v=>messages.push(v)};
 const teaser=root.querySelector('.at-advice-teaser [data-advice]');
 if(teaser){ok('teaser retains exact advice identity',source.advice.some(a=>a.card_id===teaser.dataset.advice));teaser.click();ok('teaser opens exact advice',saves.at(-1).privateContent.state.advice===teaser.dataset.advice);click('[data-action="back"]');}
 ok('overview names target goal',root.querySelector('h1').textContent===source.project_map.title&&root.textContent.includes(source.project_map.goal));
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
   click('[data-action="back"]');ok('return retains object',saves.at(-1).modelContent.object_id===savedNode);}
 }
 // This tests our code inside a local browser fixture, not the Desktop chat's scroll controller.
 const bound=win.document.documentElement;ok('content fits viewport',bound.scrollWidth<=win.innerWidth+1);
 return {checks,source:source.project_key,report:source.report_hash,echoMutations:mutations,hostChatScroll:'not_observed'};
}
