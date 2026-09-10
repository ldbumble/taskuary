import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';
import { waitForDemoReplays, settleDemoWatcher } from './processing-fixtures.mjs';

test('sync phases leave rows usable and completion is discovered without live events', { timeout: 90000 }, async t => {
  const h = await startHarness();
  t.after(() => h.close());
  await settleDemoWatcher(h, await waitForDemoReplays(h));
  const phase = async value => {
    const response = await fetch(`${h.fixtureApi}/api/fixture/processing/sync-phase`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Taskuary-Token': h.token },
      body: JSON.stringify({ phase: value }),
    });
    assert.equal(response.status, 200);
  };
  await phase('fetching');
  const page = await h.newPage();
  page.on('pageerror', error => console.error(error.message));
  await page.evaluateOnNewDocument(() => {
    let prototype = WebSocket.prototype, descriptor;
    while (prototype && !descriptor) {
      descriptor = Object.getOwnPropertyDescriptor(prototype, 'onmessage');
      prototype = Object.getPrototypeOf(prototype);
    }
    if (!descriptor?.set) throw new Error('guarded WebSocket must inherit the native message handler');
    window.__droppedSyncEvents = 0;
    Object.defineProperty(WebSocket.prototype, 'onmessage', { ...descriptor,
      set(callback) { descriptor.set.call(this, event => {
        try { if (JSON.parse(event.data).type === 'feed-changed') { window.__droppedSyncEvents++; return; } } catch {}
        callback?.call(this, event);
      }); },
    });
  });
  const polls = [];
  page.on('request', req => { if (new URL(req.url()).pathname === '/api/ingest/status') polls.push(req.url()); });
  const cdp = await page.createCDPSession();
  let heldId, resolveHeld;
  const held = new Promise(resolve => { resolveHeld = resolve; });
  cdp.on('Fetch.requestPaused', event => {
    if (!heldId) { heldId = event.requestId; resolveHeld(); }
    else cdp.send('Fetch.continueRequest', { requestId: event.requestId }).catch(() => {});
  });
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/api/funnel/pile*', requestStage: 'Response' }] });
  await page.goto(h.ui, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await Promise.race([held, new Promise((_, reject) => setTimeout(() => reject(new Error('initial pile response was not held')), 15000))]);
  await page.waitForFunction(() => document.querySelector('.tq-pile-empty b')?.textContent === 'Loading timeline');
  assert.equal(await page.evaluate(() => document.body.innerText.includes('All done')), false,
    'an unloaded inventory is not an empty inventory');
  assert.ok(await page.$('button[aria-label="Past chats"]'), 'history stays available while items load');
  await cdp.send('Fetch.continueRequest', { requestId: heldId });
  await cdp.send('Fetch.disable');
  await page.waitForSelector('.tq-pile-row .card', { visible: true, timeout: 15000 });
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(n => n.textContent.trim() === 'Reading sources'));
  assert.notEqual(await page.$eval('[data-tq-sync-icon]', n => getComputedStyle(n).animationName), 'none');
  await phase('triaging');
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(n => n.textContent.trim() === 'Organizing'), { timeout: 10000 });
  assert.equal(await page.$eval('[data-tq-sync-icon]', n => getComputedStyle(n).animationName), 'none');
  assert.ok(await page.evaluate(() => document.body.innerText.includes('Synthetic triage error remains visible')));
  const compose = await page.$('.tq-compose textarea');
  if (compose) {
    await compose.type('Owner can still type while messages are organized');
    assert.match(await compose.evaluate(n => n.value), /Owner can still type/);
  }
  assert.ok(await page.$eval('.tq-pile-row .card', n => {
    for (let parent = n; parent; parent = parent.parentElement) if (Number(getComputedStyle(parent).opacity) < 1) return false;
    return true;
  }), 'sync must not dim the readable rows');
  await phase('running_reports');
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(n => n.textContent.trim() === 'Running reports'), { timeout: 10000 });
  const before = polls.length;
  await phase('idle');
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(n => n.textContent.trim() === 'Sync now' && !n.disabled), { timeout: 10000 });
  await page.waitForFunction(() => document.body.innerText.includes('next in'), { timeout: 10000 });
  assert.ok(await page.evaluate(() => document.body.innerText.includes('in today')), 'item count labels remain visible');
  assert.ok(polls.length > before, 'a periodic status read must observe completion');
  assert.equal(await page.evaluate(() => Number.isInteger(window.__droppedSyncEvents)), true,
    'the live-event guard remained installed while polling discovered completion');
  assert.deepEqual(page.fixtureEscapes, []);
});
