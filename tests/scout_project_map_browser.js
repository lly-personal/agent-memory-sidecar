async (page, {baseURL, outputDir}) => {
 const checks=[],layouts=[],errors=[];
 const ok=(name,value)=>{if(!value)throw Error(name);checks.push(name);};
 page.on('pageerror',e=>errors.push(e.message));
 async function load(name){
  await page.goto(baseURL+'/'+name+'-preview.html');
  await page.locator('iframe').evaluate(e=>e.style.height='5000px');
  const f=page.frames().find(x=>x.parentFrame());await f.waitForSelector('[data-overview]');
  await f.evaluate(()=>{window.__saves=[];window.__messages=[];window.openai.setWidgetState=async v=>window.__saves.push(v);window.openai.sendFollowUpMessage=async v=>window.__messages.push(v);});
  return f;
 }
 await page.setViewportSize({width:768,height:1800});
 let f=await load('real');
 ok('overview starts without permanent detail',await f.locator('[data-overview]').isVisible()&&!await f.locator('[data-focus]').isVisible());
 ok('zero recommendations has no task button',await f.locator('[data-review]').isHidden());
 await f.locator('[data-support] [data-id="revoke"]').click();
 await f.locator('[data-timeline] [data-id="owner"]').click();
 await f.locator('[data-detail] [data-id="adopt"]').click();
 ok('shared edge retains revoke context',(await f.evaluate(()=>window.__saves.at(-1))).privateContent.journey==='revoke');
 await f.locator('[data-view]').click();
 const matrixState=await f.evaluate(()=>window.__saves.at(-1));
 ok('matrix retains selected object',matrixState.modelContent.selection.id==='adopt');
 await f.locator('[data-view]').click();
 await f.locator('[data-discuss]').click();
 const msg=(await f.evaluate(()=>window.__messages))[0];
 ok('discussion binds report and object without approval',msg.prompt.includes('edge:adopt')&&msg.prompt.includes('不要重跑普查')&&msg.prompt.includes('不要将本次讨论视为写入授权'));
 await f.evaluate(()=>window.openai.sendFollowUpMessage=async()=>{throw Error('test unavailable')});await f.locator('[data-discuss]').click();
 ok('bridge failure keeps same-chat exact fallback',(await f.locator('[data-status]').textContent()).includes('edge:adopt'));
 await f.locator('[data-home]').click();
 await f.evaluate(v=>window.dispatchEvent(new CustomEvent('openai:set_globals',{detail:{globals:{widgetState:v}}})),matrixState);
 ok('host restores exact selection and matrix',await f.locator('[data-matrix]').isVisible()&&(await f.locator('[data-location]').textContent()).includes('撤销'));
 const changed=structuredClone(matrixState);changed.modelContent.report_hash='unrelated';changed.modelContent.selection.id='owner';
 await f.evaluate(v=>window.dispatchEvent(new CustomEvent('openai:set_globals',{detail:{globals:{widgetState:v}}})),changed);
 ok('unrelated report state ignored',await f.locator('[data-matrix]').isVisible()&&(await f.locator('[data-detail] h4').textContent()).includes('采用'));
 for(const width of [736,320])for(const theme of ['light','dark']){
  await page.setViewportSize({width:width+32,height:1800});await f.evaluate(t=>document.documentElement.style.colorScheme=t,theme);
  if(await f.locator('[data-focus]').isVisible())await f.locator('[data-home]').click();
  const states=['overview','path','matrix'];
  for(const view of states){
   if(view==='path')await f.locator('[data-primary] button').first().click();
   if(view==='matrix')await f.locator('[data-view]').click();
   const m=await f.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
   ok('fits '+width+' '+theme+' '+view,m.width===width&&m.scroll<=width+1);layouts.push({theme,view,...m});
   if(outputDir)await f.locator('article').screenshot({path:outputDir+'/'+view+'-'+width+'-'+theme+'.png'});
  }
 }
 f=await load('advice');
 await f.locator('[data-primary] button').first().focus();await page.keyboard.press('Enter');
 ok('keyboard opens selected path',await f.locator('[data-focus]').isVisible());
 await f.locator('[data-detail] [data-kind="advice"]').click();
 ok('advice retains cost changes exception and current action',(await f.locator('[data-advice]').textContent()).includes('用户成本')&&(await f.locator('[data-advice]').textContent()).includes('例外与风险'));
 const adviceState=await f.evaluate(()=>window.__saves.at(-1));
 ok('advice retains origin',adviceState.privateContent.returnTo.selection.id==='entry');
 await f.locator('[data-home]').click();await f.evaluate(v=>window.dispatchEvent(new CustomEvent('openai:set_globals',{detail:{globals:{widgetState:v}}})),adviceState);
 await f.locator('[data-view]').click();ok('advice returns to exact origin',(await f.evaluate(()=>window.__saves.at(-1))).modelContent.selection.id==='entry');
 f=await load('other');
 ok('different project topology and vocabulary',(await f.locator('[data-title]').textContent())==='离线数据校对'&&await f.locator('[data-primary] button').count()===2);
 ok('single path has no artificial supporting paths',await f.locator('[data-support]').isHidden());
 await f.locator('[data-primary] button').last().click();ok('different owner follows source',(await f.locator('[data-detail]').textContent()).includes('校对工具'));
 f=await load('unknown');
 ok('unknown path is not invented',await f.locator('[data-primary] button').count()===0&&(await f.locator('[data-primary]').textContent()).includes('尚未建立'));
 await f.getByText('工程范围、参与者与覆盖边界',{exact:true}).click();await f.locator('[data-boundary] button').first().click();
 ok('standalone evidence still readable',await f.locator('[data-focus]').isVisible());
 ok('no runtime errors',errors.length===0);
 return {checks,layouts,errors,scope:'Production renderer in native preview wrapper. Bridge stub verifies parameters, never sends Desktop messages or grants approval. Browser acceptance does not prove human comprehension or later adoption.'};
}
