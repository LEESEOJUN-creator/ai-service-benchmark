/** Verified Korean UI recipe; only use after checking the current UI. */
export async function prepareClaudeLow(service,tab){
  const pw=tab.playwright;
  let snap=await pw.domSnapshot();
  if(service==='monogpt'){
    if(snap.includes('button "사이드바 열기"')){
      await pw.getByRole('button',{name:'사이드바 열기',exact:true}).click();
      snap=await pw.domSnapshot();
    }
    await pw.getByRole('button',{name:'새 채팅 ⌘⇧O',exact:true}).click();
    snap=await pw.domSnapshot();
    if(!snap.includes('button "Sonnet 5.5"'))throw Error('Select Sonnet 5.5 explicitly first');
    if(snap.includes('button "옵션 열기"')){
      await pw.getByRole('button',{name:'옵션 열기',exact:true}).click();snap=await pw.domSnapshot();
    }
    if(snap.includes('button "적응형 사고 꺼짐"')){
      await pw.getByRole('button',{name:'적응형 사고 꺼짐',exact:true}).click();snap=await pw.domSnapshot();
    }
    if(!snap.includes('button "낮음"'))throw Error('Reasoning controls changed');
    await pw.getByRole('button',{name:'낮음',exact:true}).click();snap=await pw.domSnapshot();
    if(snap.includes('button "검색 켜짐"')){
      await pw.getByRole('button',{name:'검색 켜짐',exact:true}).click();snap=await pw.domSnapshot();
    }
    if(snap.includes('button "사이드바 닫기"')){
      await pw.getByRole('button',{name:'사이드바 닫기',exact:true}).click();snap=await pw.domSnapshot();
    }
    return snap;
  }
  if(service==='timely'){
    await pw.getByRole('button',{name:'new chat button',exact:true}).click();
    await pw.waitForURL('https://timelyai.io/timely/chat',{timeoutMs:10000});
    await pw.domSnapshot();
    await pw.getByRole('button',{name:'model menu button',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('button "Claude Sonnet 5.5"'))throw Error('Model not offered');
    await pw.getByRole('button',{name:'Claude Sonnet 5.5',exact:true}).click();snap=await pw.domSnapshot();
    await pw.getByRole('button',{name:'추론 설정',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('button "낮음"'))throw Error('Reasoning controls changed');
    await pw.getByRole('button',{name:'낮음',exact:true}).click();snap=await pw.domSnapshot();
    if(!snap.includes('generic: 낮음'))throw Error('Low setting not confirmed');
    return snap;
  }
  throw Error('Claude is not offered on this service');
}
