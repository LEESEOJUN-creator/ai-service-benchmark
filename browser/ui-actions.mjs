/** Optional preparation helpers, not a browser driver or paid-send mechanism.
 * readUrl must use the connected tool's documented CURRENT-tab URL API.
 * No guessed coordinates, force clicks, retries, navigation or global settings.
 */
export const serviceOrigins = Object.freeze({
  monogpt: 'https://monogpt.kr', timely: 'https://timelyai.io', chatgpt: 'https://chatgpt.com',
});

export function assertServiceUrl(service, currentUrl) {
  const expected = serviceOrigins[service];
  let url;
  try { url = new URL(currentUrl); } catch { throw Error('UI_URL: current tab URL unavailable'); }
  if (!expected || url.origin !== expected || url.username || url.password)
    throw Error('UI_URL: wrong service origin; refresh tab inventory, do not click');
}

/** Conservative snapshot match: exact accessible name, not page prose/substrings. */
export function hasControl(snapshot, role, name, flag) {
  const prefix = `${role} ${JSON.stringify(name)}`;
  return snapshot.split('\n').some(line => {
    const entry = line.trim().replace(/^-\s*/, '');
    if (!entry.startsWith(prefix)) return false;
    const suffix = entry.slice(prefix.length);
    return (!suffix || /^[\s:]/.test(suffix)) &&
      (!flag || suffix.includes(`[${flag}]`));
  });
}

export function checkedUI(tab, service, readUrl) {
  if (typeof readUrl !== 'function')
    throw Error('UI_URL: supply a live readUrl callback from the supported browser tool');
  let busy = false, needsReconcile = false;
  const snapshot = async () => {
    assertServiceUrl(service, await readUrl());
    const text = await tab.playwright.domSnapshot();
    assertServiceUrl(service, await readUrl());
    return text;
  };
  return {
    snapshot,
    async click(role, name, verifyAfter) {
      if (busy || needsReconcile)
        throw Error('UI_RECONCILE: inspect current state before creating a new preparation flow');
      if (!['button', 'menuitem', 'menuitemradio'].includes(role) ||
          typeof name !== 'string' || !name || typeof verifyAfter !== 'function')
        throw Error('UI_CONTRACT: exact preparation control and postcondition required');
      busy = true;
      try {
        const before = await snapshot();
        if (!hasControl(before, role, name))
          throw Error('UI_TARGET: exact control absent from fresh snapshot');
        const target = tab.playwright.getByRole(role, {name, exact: true});
        if (await target.count() !== 1 || !await target.isVisible() || !await target.isEnabled())
          throw Error('UI_TARGET: missing, ambiguous, hidden or disabled control; do not guess');
        assertServiceUrl(service, await readUrl());
        await target.click(); // ONE action; even a timeout never triggers an automatic retry.
        const after = await snapshot();
        if (await verifyAfter(after, before) !== true)
          throw Error('UI_POSTCONDITION: expected state not observed; do not continue clicking');
        return after;
      } catch (error) {
        needsReconcile = true;
        throw error;
      } finally {
        busy = false;
      }
    },
  };
}
