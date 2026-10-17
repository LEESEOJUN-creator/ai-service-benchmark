import {checkedUI, hasControl} from './ui-actions.mjs';

/** Observed Korean-UI recipe, guarded but not verified across all live accounts.
 * Fourth argument: live readUrl and verifyReady(snapshot) callbacks, derived
 * from the connected tool and CURRENT UI, not a constant URL/true fallback.
 */
export async function prepareGPTMedium(service, tab, wrapper, {readUrl,verifyReady} = {}) {
  if(typeof verifyReady!=='function') throw Error('UI_CONTRACT: current UI model/reasoning readiness check required');
  const ui=checkedUI(tab,service,readUrl);
  const button=name=>s=>hasControl(s,'button',name);
  if(service==='monogpt') {
    let snap=await ui.click('button','새 채팅 ⌘⇧O',button('옵션 열기'));
    if(!button('GPT-6 Sol')(snap)) throw new Error('Re-select GPT-6 Sol in current model menu');
    snap=await ui.click('button','옵션 열기',s=>button('심층분석 꺼짐')(s)||button('보통')(s));
    if(button('심층분석 꺼짐')(snap)) snap=await ui.click('button','심층분석 꺼짐',button('보통'));
    if(button('검색 켜짐')(snap)) snap=await ui.click('button','검색 켜짐',button('검색 꺼짐'));
    if(!button('보통')(snap)) throw new Error('Reasoning menu changed');
    return ui.click('button','보통',verifyReady);
  }
  if(service==='timely') {
    await ui.click('button','new chat button',button('model menu button'));
    await ui.click('button','model menu button',button('GPT-6 Sol'));
    const snap=await ui.click('button','GPT-6 Sol',verifyReady);
    if(!snap.includes('generic: 보통')) throw new Error('Set medium explicitly before send');
    return snap;
  }
  if(service==='chatgpt') {
    if(typeof wrapper?.pressKey !== 'function') throw Error('Supported Escape action required');
    await ui.click('button','새 채팅',s=>hasControl(s,'button','Work','pressed')&&button('ChatGPT 모델 선택')(s));
    await ui.click('button','ChatGPT 모델 선택',s=>hasControl(s,'menuitem','모델 선택'));
    await ui.click('menuitem','모델 선택',s=>hasControl(s,'menuitemradio','GPT-6 Sol'));
    const snap=await ui.click('menuitemradio','GPT-6 Sol',verifyReady);
    if(!snap.includes('status: Medium,')) throw new Error('Set Medium explicitly before send');
    // Some UI versions close the menu on selection. Do not blindly toggle it.
    if(hasControl(snap,'menuitemradio','GPT-6 Sol')) {
      await ui.snapshot(); // live URL check before keyboard action
      await wrapper.pressKey(null,'Escape');
    }
    const ready=await ui.snapshot();
    if(hasControl(ready,'menuitemradio','GPT-6 Sol') || !ready.includes('status: Medium,') || await verifyReady(ready)!==true)
      throw Error('Composer not ready; inspect current UI, do not guess another click');
    return ready;
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
