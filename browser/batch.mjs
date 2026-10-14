/** One immutable case per invocation. Host supplies approved tabs and persistence. */
export async function runCase({caseDoc,results,tabs,helper,persistRun,windowMs=18000,preflight}) {
  if(results.records.some(r=>r.case_id===caseDoc.id)) throw new Error('Do not duplicate existing case');
  if(!preflight || preflight.uiVerified!==true || preflight.conditionsMatch!==true ||
     typeof preflight.authorizationScope!=='string' || !preflight.authorizationScope.trim() ||
     !Number.isInteger(preflight.maxTotalRequests) || preflight.maxTotalRequests<1)
    throw new Error('Explicit verified preflight and approved request scope required');
  if(!Array.isArray(tabs)||tabs.length<2||new Set(tabs.map(t=>t.service)).size!==tabs.length)
    throw new Error('Need distinct participating services');
  if(results.records.length+tabs.length>preflight.maxTotalRequests)
    throw new Error('Approved request scope exceeded');
  const states={};
  let queue=Promise.resolve();
  const persist=async(service,state)=>{
    const id=caseDoc.id+'-'+service;
    let record=results.records.find(r=>r.id===id);
    if(!record){record={id,case_id:caseDoc.id,prompt_version:caseDoc.prompt_version,
      model:results.model,reasoning:results.reasoning,
      authorization_scope:preflight.authorizationScope};results.records.push(record);}
    Object.assign(record,state);
    const payload=JSON.stringify(results,null,2);
    queue=queue.then(()=>persistRun(payload));
    await queue;
  };
  for(const {service,tab,textboxName} of tabs) states[service]=await helper.sendOnce({
    tab,service,prompt:caseDoc.turns[0],textboxName,
    persist:state=>persist(service,state),reservationId:caseDoc.id+'-'+service,uiVerified:true});
  await Promise.all(tabs.map(async({service,tab})=>{
    states[service]=await helper.observeWindow({tab,state:states[service],
      persist:state=>persist(service,state),windowMs});
  }));
  return {states,persist};
}
