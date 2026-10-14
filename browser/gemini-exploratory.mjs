/** Explicit user-authorized asymmetric Gemini recipe, NEVER strict parity. */
export async function prepareGeminiExploratory(service,tab){
  const pw=tab.playwright;
  let snap=await pw.domSnapshot();
  if(service==='monogpt'){
    if(snap.includes('button "사이드바 열기"')){
      await pw.getByRole('button',{name:'사이드바 열기',exact:true}).click();snap=await pw.domSnapshot();
    }
    await pw.getByRole('button',{name:'새 채팅 ⌘⇧O',exact:true}).click();
    snap=await pw.domSnapshot();
    if(!snap.includes('heading "어떻게 도와드릴까요?"') || await pw.getByRole('button',{name:'답변 복사',exact:true}).count()!==0)
      throw Error('New conversation not verified; do not send');
    if(!snap.includes('button "Gemini 3.5 Flash-Lite"')){
      // This account resets new chats to Opus 4.8. Never submit that model.
      if(!snap.includes('button "Opus 4.8"'))throw Error('Select Gemini 3.5 Flash-Lite first');
      await pw.getByRole('button',{name:'Opus 4.8',exact:true}).click();snap=await pw.domSnapshot();
      if(!snap.includes('button "Gemini 30"'))throw Error('Model category changed');
      await pw.getByRole('button',{name:'Gemini 30',exact:true}).click();snap=await pw.domSnapshot();
      if(!snap.includes('button "🟢 Gemini 3.5 Flash-Lite ☆"'))throw Error('Model entry changed');
      await pw.getByRole('button',{name:'🟢 Gemini 3.5 Flash-Lite ☆',exact:true}).click();snap=await pw.domSnapshot();
      if(!snap.includes('button "Gemini 3.5 Flash-Lite"'))throw Error('Model selection not confirmed');
    }
    if(snap.includes('button "옵션 열기"')){
      await pw.getByRole('button',{name:'옵션 열기',exact:true}).click();snap=await pw.domSnapshot();
    }
    if(!snap.includes('status "심층 사고 미지원"'))throw Error('Reasoning UI changed; re-check authorization');
    return snap;
  }
  if(service==='timely'){
    if(snap.includes('button "캔버스 닫기"'))await pw.getByRole('button',{name:'캔버스 닫기',exact:true}).click();
    await pw.getByRole('button',{name:'new chat button',exact:true}).click();
    await pw.waitForURL('https://timelyai.io/timely/chat',{timeoutMs:10000});
    await pw.domSnapshot();
    await pw.getByRole('button',{name:'model menu button',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('button "Gemini 3.5 Flash Lite"'))throw Error('Model unavailable');
    await pw.getByRole('button',{name:'Gemini 3.5 Flash Lite',exact:true}).click();
    await pw.domSnapshot();
    await pw.getByRole('button',{name:'추론 설정',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('button "보통"'))throw Error('Medium unavailable');
    await pw.getByRole('button',{name:'보통',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('generic: 보통'))throw Error('Medium not confirmed');
    return snap;
  }
  throw Error('Gemini not offered on this service');
}
