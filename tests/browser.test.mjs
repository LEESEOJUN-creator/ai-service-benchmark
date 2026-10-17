import test from 'node:test';
import assert from 'node:assert/strict';
import {sendOnce,observeWindow,timingResult} from '../browser/observe.mjs';
import {runCase,resolveComparison} from '../browser/batch.mjs';
import {readFileSync} from 'node:fs';
import {assertServiceUrl,serviceOrigins,hasControl,checkedUI} from '../browser/ui-actions.mjs';
import {prepareGPTMedium} from '../browser/gpt-medium.mjs';

function uiMock({screens=['button "open"','button "ready"'],count=1,visible=true,enabled=true,failClick=false,urls=['https://chatgpt.com/']}={}) {
  const log=[];let stage=0,urlIndex=0;
  const tab={playwright:{
    domSnapshot:async()=>{log.push('snapshot');return screens[Math.min(stage,screens.length-1)];},
    getByRole:(role,options)=>{
      assert.equal(options.exact,true);
      return {count:async()=>count,isVisible:async()=>visible,isEnabled:async()=>enabled,
        click:async()=>{log.push(`click:${role}:${options.name}`);stage++;if(failClick)throw Error('timeout');}};
    },
  }};
  return {tab,log,readUrl:async()=>urls[Math.min(urlIndex++,urls.length-1)],
    wrapper:{pressKey:async(_,key)=>{assert.equal(key,'Escape');log.push('escape');stage++;}}};
}
const ready=s=>hasControl(s,'button','ready');
const clicks=mock=>mock.log.filter(x=>x.startsWith('click:'));

test('service origins match site configuration and allow current conversation paths',()=>{
  for(const [service,origin] of Object.entries(serviceOrigins)) {
    const config=JSON.parse(readFileSync(new URL(`../sites/${service}.json`,import.meta.url)));
    assert.equal(origin,new URL(config.url).origin);
    assert.doesNotThrow(()=>assertServiceUrl(service,origin+'/conversation/test?x=1'));
  }
});
test('wrong, lookalike, credentialed and unavailable URLs are rejected',()=>{
  for(const url of ['https://monogpt.com/','https://monogpt.kr.example.com/','http://monogpt.kr/',
    'https://u:p@monogpt.kr/','https://monogpt.kr:444/',undefined,''])
    assert.throws(()=>assertServiceUrl('monogpt',url),/UI_URL/);
  assert.throws(()=>assertServiceUrl('unknown','https://chatgpt.com/'),/UI_URL/);
});
test('snapshot match is exact control rather than model prose or similar model',()=>{
  assert.equal(hasControl('- menuitemradio "GPT-6 Sol" [checked]','menuitemradio','GPT-6 Sol','checked'),true);
  for(const text of ['generic: GPT-6 Sol','button "GPT-6.1 Sol"','menuitemradio "GPT-6 Sol extra"'])
    assert.equal(hasControl(text,'menuitemradio','GPT-6 Sol'),false);
  assert.equal(hasControl('menuitemradio "GPT-6 Sol"','menuitemradio','GPT-6 Sol','checked'),false);
});
test('every click observes before and after without bundling actions',async()=>{
  const m=uiMock({screens:['button "open"','button "ready"','button "done"']});
  const ui=checkedUI(m.tab,'chatgpt',m.readUrl);
  await ui.click('button','open',ready);
  await ui.click('button','ready',async s=>hasControl(s,'button','done'));
  assert.deepEqual(m.log,['snapshot','click:button:open','snapshot','snapshot','click:button:ready','snapshot']);
});
for(const [label,options] of Object.entries({missing:{count:0},duplicate:{count:2},hidden:{visible:false},disabled:{enabled:false},stale:{screens:['button "other"']}})) {
  test(`${label} control causes no click`,async()=>{
    const m=uiMock(options),ui=checkedUI(m.tab,'chatgpt',m.readUrl);
    await assert.rejects(ui.click('button','open',ready),/UI_TARGET/);
    assert.equal(clicks(m).length,0);
  });
}
test('missing postcondition or live URL callback cannot click',async()=>{
  const m=uiMock();
  assert.throws(()=>checkedUI(m.tab,'chatgpt'),/UI_URL/);
  await assert.rejects(checkedUI(m.tab,'chatgpt',m.readUrl).click('button','open'),/UI_CONTRACT/);
  assert.equal(clicks(m).length,0);
});
for(const [label,urls,expectedClicks] of [
  ['before observation',['https://wrong.example/'],0],
  ['after observation',['https://chatgpt.com/','https://wrong.example/'],0],
  ['before click',['https://chatgpt.com/','https://chatgpt.com/','https://wrong.example/'],0],
  ['after click',['https://chatgpt.com/','https://chatgpt.com/','https://chatgpt.com/','https://wrong.example/'],1],
]) {
  test(`origin change ${label} halts flow`,async()=>{
    const m=uiMock({urls}),ui=checkedUI(m.tab,'chatgpt',m.readUrl);
    await assert.rejects(ui.click('button','open',ready),/UI_URL/);
    await assert.rejects(ui.click('button','open',ready),/UI_RECONCILE/);
    assert.equal(clicks(m).length,expectedClicks);
  });
}
test('timeout does not cause a retry or next click',async()=>{
  const m=uiMock({failClick:true}),ui=checkedUI(m.tab,'chatgpt',m.readUrl);
  await assert.rejects(ui.click('button','open',ready),/timeout/);
  await assert.rejects(ui.click('button','ready',ready),/UI_RECONCILE/);
  assert.equal(clicks(m).length,1);
});
test('unchanged menu blocks cascading clicks but permits read-only reconciliation',async()=>{
  const m=uiMock({screens:['button "open"']}),ui=checkedUI(m.tab,'chatgpt',m.readUrl);
  await assert.rejects(ui.click('button','open',ready),/UI_POSTCONDITION/);
  assert.equal(await ui.snapshot(),'button "open"');
  await assert.rejects(ui.click('button','open',ready),/UI_RECONCILE/);
  assert.equal(clicks(m).length,1);
});
test('truthy non-boolean postcondition is not verification',async()=>{
  const m=uiMock();
  await assert.rejects(checkedUI(m.tab,'chatgpt',m.readUrl).click('button','open',()=> 'yes'),/UI_POSTCONDITION/);
});
test('concurrent preparation actions are rejected',async()=>{
  const m=uiMock(),ui=checkedUI(m.tab,'chatgpt',m.readUrl);
  const first=ui.click('button','open',ready);
  await assert.rejects(ui.click('button','open',ready),/UI_RECONCILE/);
  await first;assert.equal(clicks(m).length,1);
});
const gptReady=s=>hasControl(s,'button','Selected GPT-6 Sol')&&s.includes('status: Medium,'); // synthetic UI only
const gptSteps=['button "새 채팅"','button "Work" [pressed]\nbutton "ChatGPT 모델 선택"',
  'menuitem "모델 선택"','menuitemradio "GPT-6 Sol"'];
for(const autoClose of [true,false]) {
  test(`GPT current model selection verified; menu auto-close=${autoClose}`,async()=>{
    const readyState='button "Selected GPT-6 Sol"\nstatus: Medium,';
    const m=uiMock({screens:[...gptSteps,...(autoClose?[readyState]:['menuitemradio "GPT-6 Sol" [checked]\n'+readyState,readyState])]});
    await prepareGPTMedium('chatgpt',m.tab,m.wrapper,{readUrl:m.readUrl,verifyReady:gptReady});
    assert.equal(clicks(m).length,4);
    assert.equal(m.log.includes('escape'),!autoClose);
  });
}
test('missing GPT submenu never clicks writing-style or another neighbor',async()=>{
  const m=uiMock({screens:[...gptSteps.slice(0,2),'button "문체학습 해보기"']});
  await assert.rejects(prepareGPTMedium('chatgpt',m.tab,m.wrapper,{readUrl:m.readUrl,verifyReady:gptReady}),/UI_POSTCONDITION/);
  assert.deepEqual(clicks(m),['click:button:새 채팅','click:button:ChatGPT 모델 선택']);
});
test('similar but wrong model is not selected',async()=>{
  const m=uiMock({screens:[...gptSteps.slice(0,3),'menuitemradio "GPT-6.1 Sol"']});
  await assert.rejects(prepareGPTMedium('chatgpt',m.tab,m.wrapper,{readUrl:m.readUrl,verifyReady:gptReady}),/UI_POSTCONDITION/);
  assert.equal(clicks(m).length,3);
});
test('GPT recipe requires current readiness and URL checks before any action',async()=>{
  const m=uiMock();
  await assert.rejects(prepareGPTMedium('chatgpt',m.tab,m.wrapper),/UI_CONTRACT/);
  await assert.rejects(prepareGPTMedium('chatgpt',m.tab,m.wrapper,{verifyReady:gptReady}),/UI_URL/);
  assert.equal(clicks(m).length,0);
});
test('MonoGPT rereads after each toggle and verifies final selection',async()=>{
  const m=uiMock({urls:['https://monogpt.kr/'],screens:[
    'button "새 채팅 ⌘⇧O"','button "GPT-6 Sol"\nbutton "옵션 열기"',
    'button "심층분석 꺼짐"\nbutton "검색 켜짐"',
    'button "보통"\nbutton "검색 켜짐"','button "보통"\nbutton "검색 꺼짐"',
    'button "Selected GPT-6 Sol"\nstatus: Medium,',
  ]});
  await prepareGPTMedium('monogpt',m.tab,m.wrapper,{readUrl:m.readUrl,verifyReady:gptReady});
  assert.deepEqual(clicks(m),['click:button:새 채팅 ⌘⇧O','click:button:옵션 열기',
    'click:button:심층분석 꺼짐','click:button:검색 켜짐','click:button:보통']);
});
test('MonoGPT does not toggle a search state already off',async()=>{
  const m=uiMock({urls:['https://monogpt.kr/'],screens:[
    'button "새 채팅 ⌘⇧O"','button "GPT-6 Sol"\nbutton "옵션 열기"',
    'button "보통"\nbutton "검색 꺼짐"','button "Selected GPT-6 Sol"\nstatus: Medium,',
  ]});
  await prepareGPTMedium('monogpt',m.tab,m.wrapper,{readUrl:m.readUrl,verifyReady:gptReady});
  assert.equal(clicks(m).length,3);assert.equal(clicks(m).some(x=>x.includes('검색')),false);
});
test('Timely confirms selected model instead of just its presence in open menu',async()=>{
  const screens=['button "new chat button"','button "model menu button"','button "GPT-6 Sol"'];
  const good=uiMock({urls:['https://timelyai.io/timely/chat'],screens:[...screens,
    'button "Selected GPT-6 Sol"\nstatus: Medium,\ngeneric: 보통']});
  await prepareGPTMedium('timely',good.tab,good.wrapper,{readUrl:good.readUrl,verifyReady:gptReady});
  assert.equal(clicks(good).length,3);
  const bad=uiMock({urls:['https://timelyai.io/timely/chat'],screens});
  await assert.rejects(prepareGPTMedium('timely',bad.tab,bad.wrapper,{readUrl:bad.readUrl,verifyReady:gptReady}),/UI_POSTCONDITION/);
  assert.equal(clicks(bad).length,3);
});

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
