import test from 'node:test';
import assert from 'node:assert/strict';
import {sendOnce,observeWindow} from '../browser/observe.mjs';
import {runCase} from '../browser/batch.mjs';

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
  assert.deepEqual(log,['fill','persist','click','persist']);
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
