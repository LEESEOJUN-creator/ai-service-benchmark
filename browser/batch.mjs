/** One immutable case per invocation. Host supplies approved tabs and persistence. */
export function resolveComparison(preflight) {
  if(preflight?.conditionsMatch === true) return preflight;
  if(preflight?.comparisonMode === 'exploratory' && preflight?.userAuthorizedMismatch === true)
    return preflight;
  if(preflight?.reasoningMismatchPolicy === 'auto_exploratory' &&
     preflight.sameModelVerified === true && preflight.sameInputVerified === true &&
     preflight.otherSettingsMatch === true && preflight.authorizationScope?.trim() && preflight.mismatchNote?.trim())
    return {...preflight, comparisonMode:'exploratory', userAuthorizedMismatch:true, conditionsMatch:false};
  throw new Error('preflight: confirm reasoning-only exploratory comparison once; do not silently omit this model');
}

export async function runCase({caseDoc,results,tabs,helper,persistRun,windowMs=18000,preflight,resume=false}) {
  const existing=results.records.filter(r=>r.case_id===caseDoc.id);
  if(existing.length && !resume) throw new Error('Do not duplicate existing case; resume observation explicitly');
  preflight=resolveComparison(preflight);
  const exploratory = preflight?.comparisonMode === 'exploratory' &&
    preflight?.conditionsMatch === false && preflight?.userAuthorizedMismatch === true &&
    typeof preflight?.mismatchNote === 'string' && preflight.mismatchNote.trim();
  if(!preflight || preflight.uiVerified!==true || (preflight.conditionsMatch!==true && !exploratory) ||
     typeof preflight.authorizationScope!=='string' || !preflight.authorizationScope.trim() ||
     !Number.isInteger(preflight.maxTotalRequests) || preflight.maxTotalRequests<1 || preflight.maxTotalRequests>40)
    throw new Error('Explicit verified preflight and approved request scope required');
  if(!Array.isArray(tabs)||tabs.length<2||new Set(tabs.map(t=>t.service)).size!==tabs.length)
    throw new Error('Need distinct participating services');
  const unsent=tabs.filter(t=>!existing.some(r=>r.id===caseDoc.id+'-'+t.service));
  if(results.records.length+unsent.length>preflight.maxTotalRequests)
    throw new Error('Approved request scope exceeded');
  for(const record of existing) {
    if(record.prompt!==caseDoc.turns[0] || record.authorization_scope!==preflight.authorizationScope ||
       record.comparison_mode!==(exploratory?'exploratory':'ui_matched') ||
       record.model!==results.model || record.reasoning!==(results.reasoning_by_service?.[record.service] ?? results.reasoning))
      throw new Error('Resume conditions changed; reconcile without sending');
    if(!record.sendActionReturned) throw new Error('Uncertain submission; reconcile without resending');
  }
  const states={};
  let queue=Promise.resolve();
  const persist=async(service,state)=>{
    const id=caseDoc.id+'-'+service;
    let record=results.records.find(r=>r.id===id);
    if(!record){record={id,case_id:caseDoc.id,prompt_version:caseDoc.prompt_version,
      model:results.model,reasoning:results.reasoning_by_service?.[service] ?? results.reasoning,
      comparison_mode:exploratory?'exploratory':'ui_matched',
      mismatch_note:exploratory?preflight.mismatchNote:null,
      authorization_scope:preflight.authorizationScope};results.records.push(record);}
    Object.assign(record,state);
    const payload=JSON.stringify(results,null,2);
    queue=queue.then(()=>persistRun(payload));
    await queue;
  };
  // Observe immediately after each send; never spend its response window setting up another site.
  for(const {service,tab,textboxName} of tabs) {
    const record=existing.find(r=>r.id===caseDoc.id+'-'+service);
    states[service]=record ? {...record} : await helper.sendOnce({tab,service,prompt:caseDoc.turns[0],textboxName,
      persist:state=>persist(service,state),reservationId:caseDoc.id+'-'+service,uiVerified:true});
    if(states[service].status==='completion_observed') continue;
    states[service]=await helper.observeWindow({tab,state:states[service],
      persist:state=>persist(service,state),windowMs});
    if(states[service].status==='still_observing') break; // Resume observation, NOT runCase/send again.
  }
  return {states,persist};
}
