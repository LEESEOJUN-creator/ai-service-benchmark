import test from 'node:test';
import assert from 'node:assert/strict';
import {sendOnce,observeWindow,timingResult} from '../browser/observe.mjs';
import {runCase,resolveComparison} from '../browser/batch.mjs';

function tabMock({snapshot='',copy=0,changed=false,failClick=false}={}){
  const log=[];let text='';
  const box={count:async()=>1,isVisible:async()=>true,fill:async v=>{text=v;log.push('fill');},
    filter(){return this;},evaluate:async()=>changed?'changed':text};
  const tab={playwright:{domSnapshot:async()=>snapshot,getByRole(role,{name}={}){
    if(role==='textbox')return box;
    if(['복사','답변 복사'].includes(name))return{count:async()=>copy};
    return{count:async()=>1,isEnabled:async()=>true,click:async()=>{log.push('click');if(failClick)throw Error('timeout');}};
  }}};return{tab,log};
}
test('persist before paid click and one send',async()=>{
  const {tab,log}=tabMock();
  await sendOnce({tab,service:'chatgpt',prompt:'hello',textboxName:'old name',reservationId:'one',uiVerified:true,persist:async()=>log.push('persist')});
  assert.deepEqual(log,['fill','persist','persist','click','persist']);
});
test('changed input does not send',async()=>{
  const {tab,log}=tabMock({changed:true});
  await assert.rejects(sendOnce({tab,service:'chatgpt',prompt:'hello',reservationId:'one',uiVerified:true,persist:async()=>{}}));
  assert.equal(log.includes('click'),false);
});
test('ambiguous failed click is persisted and never retried',async()=>{
  const {tab,log}=tabMock({failClick:true}),saved=[];
  await assert.rejects(sendOnce({tab,service:'chatgpt',prompt:'hello',reservationId:'one',uiVerified:true,persist:async s=>saved.push(s.status)}));
  assert.equal(log.filter(x=>x==='click').length,1);assert.equal(saved.at(-1),'reconcile_before_retry');
});
test('stale completion cannot complete new prompt',async()=>{
  const {tab}=tabMock({snapshot:'status: 답변이 완료되었습니다.',copy:1});
  const state={service:'chatgpt',prompt:'new prompt',sendActionReturned:true,startedMonotonic:performance.now(),observations:[]};
  await observeWindow({tab,state,persist:async()=>{},windowMs:1});assert.equal(state.status,'still_observing');
});
test('current prompt and copy mark completion',async()=>{
  const {tab}=tabMock({snapshot:'new prompt',copy:1});
  const state={service:'chatgpt',prompt:'new prompt',sendActionReturned:true,startedMonotonic:performance.now(),observations:[]};
  await observeWindow({tab,state,persist:async()=>{},windowMs:1});assert.equal(state.status,'completion_observed');
});
test('batch duplicate guard runs before any helper',async()=>{
  await assert.rejects(runCase({caseDoc:{id:'same'},results:{records:[{case_id:'same'}]}}),/duplicate/);
});
test('batch without verified scope fails closed',async()=>{
  await assert.rejects(runCase({caseDoc:{id:'new'},results:{records:[]}}),/preflight/);
});
test('batch refuses request scope overflow',async()=>{
  await assert.rejects(runCase({caseDoc:{id:'new'},results:{records:[]},tabs:[{service:'monogpt'},{service:'timely'}],
    preflight:{uiVerified:true,conditionsMatch:true,authorizationScope:'synthetic one-request cap',maxTotalRequests:1}}),/scope exceeded/);
});
test('Timely generating status provides timing lower bound',async()=>{
  const {tab}=tabMock({snapshot:'prompt\nstatus: 답변을 생성하고 있습니다.'});
  const state={service:'timely',prompt:'prompt',sendActionReturned:true,startedMonotonic:performance.now(),observations:[]};
  await observeWindow({tab,state,persist:async()=>{},windowMs:1});
  assert.ok(state.lastGeneratingObservedMs>=0);assert.equal(state.status,'still_observing');
});
test('unapproved mismatch fails closed',async()=>{
  await assert.rejects(runCase({caseDoc:{id:'x'},results:{records:[]},preflight:{uiVerified:true,conditionsMatch:false,comparisonMode:'exploratory',authorizationScope:'test',maxTotalRequests:2}}),/preflight/);
});
test('authorized exploratory batch remains labeled and retains per-service reasoning',async()=>{
  const results={records:[],model:'Gemini',reasoning_by_service:{monogpt:'unknown',timely:'medium'}};
  const helper={sendOnce:async({service,persist})=>{const s={service};await persist(s);return s;},observeWindow:async({state})=>state};
  await runCase({caseDoc:{id:'x',turns:['prompt']},results,tabs:[{service:'monogpt'},{service:'timely'}],helper,persistRun:async()=>{},
    preflight:{uiVerified:true,conditionsMatch:false,comparisonMode:'exploratory',userAuthorizedMismatch:true,mismatchNote:'explicit asymmetry',authorizationScope:'test only',maxTotalRequests:2}});
  assert.equal(results.records[0].comparison_mode,'exploratory');assert.equal(results.records[0].reasoning,'unknown');assert.equal(results.records[1].reasoning,'medium');
});

test('measured completion is mapped to report fields without losing upper-only time',async()=>{
  const {tab}=tabMock({snapshot:'hello',copy:1}),saved=[];
  const persist=async s=>saved.push(JSON.parse(JSON.stringify(s)));
  const state=await sendOnce({tab,service:'chatgpt',prompt:'hello',reservationId:'x',uiVerified:true,persist});
  assert.ok(saved[1].startedEpochMs>0);
  await observeWindow({tab,state,persist,windowMs:1});
  const result=timingResult(state);
  assert.ok(result.first_complete_observed_ms>=0);
  assert.equal(result.last_generating_observed_ms,null);
  assert.equal(result.timing_status,'observed');
  assert.equal(saved.at(-1).first_complete_observed_ms,result.first_complete_observed_ms);
});

test('resume uses persisted wall clock not a foreign monotonic origin',async()=>{
  const {tab}=tabMock({snapshot:'hello',copy:1});
  const state={service:'chatgpt',prompt:'hello',sendActionReturned:true,observations:[],
    startedEpochMs:Date.now()-2000,startedMonotonic:1,clockOrigin:-1};
  await observeWindow({tab,state,persist:async()=>{},windowMs:1});
  assert.ok(state.first_complete_observed_ms>=2000);
  assert.equal(state.timing_method,'wall_clock_ui_observation_after_resume');
});

test('missing completion stays unavailable rather than zero',()=>{
  assert.equal(timingResult({}).first_complete_observed_ms,null);
  assert.match(timingResult({}).timing_unavailable_reason,/do not resend/);
  assert.throws(()=>timingResult({firstCompleteObservedMs:2,lastGeneratingObservedMs:3}),/interval/);
});

test('reasoning-only default policy proceeds and ask policy requests confirmation',()=>{
  const p={conditionsMatch:false,reasoningMismatchPolicy:'auto_exploratory',sameModelVerified:true,
    sameInputVerified:true,otherSettingsMatch:true,authorizationScope:'approved two requests',mismatchNote:'unknown vs medium'};
  assert.equal(resolveComparison(p).comparisonMode,'exploratory');
  for(const bad of [{reasoningMismatchPolicy:'ask'},{sameModelVerified:false},{sameInputVerified:false},{otherSettingsMatch:false},{authorizationScope:''}])
    assert.throws(()=>resolveComparison({...p,...bad}),/confirm/);
});

test('batch observes each service immediately and does not send next while generating',async()=>{
  const log=[];
  const helper={sendOnce:async({service})=>{log.push('send '+service);return {service};},
    observeWindow:async({state})=>{log.push('observe '+state.service);return {...state,status:'still_observing'};}};
  await runCase({caseDoc:{id:'x',turns:['prompt']},results:{records:[]},tabs:[{service:'monogpt'},{service:'timely'}],helper,persistRun:async()=>{},
    preflight:{uiVerified:true,conditionsMatch:true,authorizationScope:'test',maxTotalRequests:2}});
  assert.deepEqual(log,['send monogpt','observe monogpt']);
});

test('explicit batch resume observes existing request then sends only the unsent service',async()=>{
  const results={records:[],model:'test',reasoning:'low'},log=[];
  let complete=false;
  const helper={sendOnce:async({service,prompt,persist})=>{
      log.push('send '+service);const state={service,prompt,sendActionReturned:true};await persist(state);return state;
    },observeWindow:async({state,persist})=>{
      log.push('observe '+state.service);state.status=complete?'completion_observed':'still_observing';await persist(state);return state;
    }};
  const args={caseDoc:{id:'x',turns:['prompt']},results,tabs:[{service:'monogpt'},{service:'timely'}],helper,persistRun:async()=>{},
    preflight:{uiVerified:true,conditionsMatch:true,authorizationScope:'test',maxTotalRequests:2}};
  await runCase(args);
  complete=true;
  await runCase({...args,resume:true});
  assert.deepEqual(log,['send monogpt','observe monogpt','observe monogpt','send timely','observe timely']);
  await runCase({...args,resume:true});
  assert.equal(log.length,5);
  await assert.rejects(runCase({...args,caseDoc:{id:'x',turns:['changed']},resume:true}),/conditions changed/);
});
