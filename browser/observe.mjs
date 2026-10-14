/** Agent-injected browser helper. No HTTP, credentials, browser launch or login.
 * Run only inside the environment's documented browser REPL after reading its
 * policy. Never run this file with standalone node expecting browser access.
 * Current DOM must confirm selectors before invocation. No retry of send.
 */
export const serviceControls = Object.freeze({
  monogpt: {send: '보내기', stop: '응답 생성 중단', copy: '답변 복사'},
  timely: {send: 'send button', completeText: '답변이 완료되었습니다.'},
  chatgpt: {send: '보내기', stop: '중지', copy: '복사'},
});

export async function sendOnce({tab, service, prompt, textboxName, persist, reservationId, uiVerified}) {
  const c = serviceControls[service];
  if (!c || uiVerified !== true || !reservationId || typeof persist !== 'function')
    throw new Error('Verified current UI and durable reservation are required');
  const box = tab.playwright.getByRole('textbox', {name: textboxName, exact: true});
  // Scope to the visible textbox. Never fill a hidden form or evaluate app state.
  if (await box.count() !== 1 || !await box.isVisible()) throw new Error('Ambiguous textbox');
  await box.fill(prompt);
  // Some composers acquire a model-specific accessible name after typing.
  // Re-observe and resolve the sole visible textbox, never reuse that stale name.
  await tab.playwright.domSnapshot();
  const filled = tab.playwright.getByRole('textbox').filter({visible:true});
  if (await filled.count() !== 1) throw new Error('Ambiguous filled textbox');
  const current = await filled.evaluate(el =>
    ['TEXTAREA','INPUT'].includes(el.tagName) ? el.value : el.innerText);
  if (current !== prompt) throw new Error('Input changed; do not send');
  const button = tab.playwright.getByRole('button', {name: c.send, exact: true});
  if (await button.count() !== 1 || !await button.isEnabled()) throw new Error('Send unavailable');
  const state = {reservationId, service, prompt, status: 'submission_started',
    startedAt: new Date().toISOString(), observations: [], sendActionReturned: false};
  await persist(state); // MUST finish before the paid side effect.
  state.startedMonotonic = performance.now();
  try {
    await button.click();
    state.sendActionReturned = true;
  } catch (error) {
    state.status = 'reconcile_before_retry';
    await persist(state);
    throw error; // Never assume a timeout means nothing was sent.
  }
  await persist(state);
  return state;
}

export async function observeWindow({tab, state, persist, windowMs = 20000}) {
  if (!state.sendActionReturned || !Number.isFinite(state.startedMonotonic))
    throw new Error('Live clock missing; reconcile UI, do not manufacture elapsed time');
  if (!(windowMs > 0 && windowMs <= 30000)) throw new Error('Observation window must be <=30s');
  const c = serviceControls[state.service], deadline = performance.now() + windowMs;
  do {
    const snapshot = await tab.playwright.domSnapshot();
    const elapsed = performance.now() - state.startedMonotonic;
    const promptSeen = snapshot.includes(state.prompt);
    const stopped = c.stop ? snapshot.includes(`button "${c.stop}"`) :
      (state.service === 'timely' && snapshot.includes('status: 답변을 생성하고 있습니다.'));
    const copied = c.copy ? await tab.playwright.getByRole('button', {name:c.copy, exact:true}).count() === 1 : false;
    // ChatGPT may leave a stale completion status in a blank new chat. Require
    // the submitted prompt and actual final answer controls, not status alone.
    const complete = promptSeen && !stopped && (copied ||
      (state.service === 'timely' && snapshot.includes('status: '+c.completeText)
       && snapshot.includes('message control button') && snapshot.includes('img "copy"')));
    state.observations.push({elapsedMs:elapsed, generating:stopped, complete});
    if (stopped) state.lastGeneratingObservedMs = elapsed;
    if (complete) {
      state.firstCompleteObservedMs = elapsed;
      state.status = 'completion_observed';
      await persist(state);
      return state;
    }
    await persist(state);
    // Each tool's snapshot performs its own observation wait. No blind sleep.
  } while (performance.now() < deadline);
  state.status = 'still_observing';
  await persist(state);
  return state; // Resume observation, never send again. Agent reports progress.
}
