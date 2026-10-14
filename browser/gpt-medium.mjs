/** Observed Korean-UI recipe; invoke only after current UI selector validation. */
export async function prepareGPTMedium(service, tab, wrapper) {
  const pw=tab.playwright;
  if(service==='monogpt') {
    await pw.getByRole('button',{name:'새 채팅 ⌘⇧O',exact:true}).click();
    let snap=await pw.domSnapshot();
    if(!snap.includes('button "GPT-6 Sol"')) throw new Error('Re-select GPT-6 Sol in current model menu');
    await pw.getByRole('button',{name:'옵션 열기',exact:true}).click();
    snap=await pw.domSnapshot();
    if(snap.includes('button "심층분석 꺼짐"')) await pw.getByRole('button',{name:'심층분석 꺼짐',exact:true}).click();
    if(snap.includes('button "검색 켜짐"')) await pw.getByRole('button',{name:'검색 켜짐',exact:true}).click();
    snap=await pw.domSnapshot();
    if(!snap.includes('button "보통"')) throw new Error('Reasoning menu changed');
    await pw.getByRole('button',{name:'보통',exact:true}).click();
    return pw.domSnapshot();
  }
  if(service==='timely') {
    await pw.getByRole('button',{name:'new chat button',exact:true}).click();
    await pw.waitForURL('https://timelyai.io/timely/chat',{timeoutMs:10000});
    await pw.domSnapshot();
    await pw.getByRole('button',{name:'model menu button',exact:true}).click();
    let snap=await pw.domSnapshot();
    if(!snap.includes('button "GPT-6 Sol"')) throw new Error('Model no longer offered');
    await pw.getByRole('button',{name:'GPT-6 Sol',exact:true}).click();
    snap=await pw.domSnapshot();
    if(!snap.includes('generic: 보통')) throw new Error('Set medium explicitly before send');
    return snap;
  }
  if(service==='chatgpt') {
    await pw.getByRole('button',{name:'새 채팅',exact:true}).click();
    await pw.waitForURL('https://chatgpt.com/',{timeoutMs:10000});
    let snap=await pw.domSnapshot();
    if(!snap.includes('button "Work" [pressed]')) throw new Error('Work mode must be selected');
    await pw.getByRole('button',{name:'ChatGPT 모델 선택',exact:true}).click();
    await pw.domSnapshot();
    await pw.getByRole('menuitem',{name:'모델 선택',exact:true}).click();
    await pw.domSnapshot();
    await pw.getByRole('menuitemradio').filter({hasText:/^GPT-6 Sol$/}).click();
    snap=await pw.domSnapshot();
    if(!snap.includes('status: Medium,')) throw new Error('Set Medium explicitly before send');
    await wrapper.pressKey(null,'Escape');
    return pw.domSnapshot();
  }
  throw new Error('Unknown service');
}

export async function copyAnswer(service,tab) {
  const snap=await tab.playwright.domSnapshot();
  let source='chat';
  if(service==='timely') {
    if(snap.includes('button "캔버스 닫기"')) {
      await tab.playwright.getByRole('button',{name:'복사',exact:true}).click();source='canvas';
    } else {
      await tab.playwright.getByRole('button',{name:'message control button',exact:true})
        .filter({has:tab.playwright.getByRole('img',{name:'copy',exact:true})}).click();
    }
  } else await tab.playwright.getByRole('button',{name:service==='monogpt'?'답변 복사':'복사',exact:true}).click();
  const answer=await tab.clipboard.readText();
  if(!answer.trim()) throw new Error('Empty clipboard is not a completed answer');
  return {answer,answer_source:source};
}
