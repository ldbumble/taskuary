// A RESTART ONTO A NEW BUILD RELOADS THE PAGE (2026-10-21: a restart from one version into the next left an open window on
// the old rail until a manual reload). Against the demo world's real server, with /api/build answered by the test: a page at
// rest reloads itself once when the reported build changes, a second look at the same build does not reload it again, and
// a page with text in its composer keeps the text and gets the quiet line instead.
import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

test('a changed server build reloads a page at rest once, and only says so to someone typing', { timeout: 180000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let build = 'index-before.js', asked = 0, loads = 0;
  page.on('load', () => { loads += 1; });
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (r) => {
    if (new URL(r.url()).pathname !== '/api/build') return page.fixtureRequestGuard(r);
    asked += 1;
    r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ asset: build, version: '0.3.9.20', disk_version: '0.3.9.20' }) });
  });
  const look = async () => { const n = asked; await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    for (let i = 0; i < 100 && asked === n; i++) await delay(100); assert.ok(asked > n, 'focus asks the server which build it runs'); };

  await page.goto(harness.ui, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#tqTopNav', { timeout: 30000 });
  for (let i = 0; i < 100 && !asked; i++) await delay(100);
  await delay(1500);
  assert.equal(loads, 1, 'the same build reloads nothing');
  await look(); await delay(1500);
  assert.equal(loads, 1, 'a second look at the same build reloads nothing');

  // the server restarted onto a new build: the page at rest reloads by itself, once
  build = 'index-after.js';
  await look();
  for (let i = 0; i < 150 && loads < 2; i++) await delay(100);
  assert.equal(loads, 2, 'a page at rest reloads for a new build');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('tq-build-reloaded')), 'index-after.js', 'the reload is remembered for this build');
  await page.waitForSelector('#tqTopNav', { timeout: 30000 });
  await delay(1500); await look(); await delay(1500);
  assert.equal(loads, 2, 'never twice for the same build');

  // ...and with words in the composer the next build is only said, on the existing quiet line
  const box = await page.waitForSelector('textarea:not(.xterm-helper-textarea)', { visible: true, timeout: 30000 });
  await box.type('half a sentence');
  build = 'index-later.js';
  await look();
  await page.waitForFunction(() => document.body.innerText.includes('A new version is running – Reload'), { timeout: 15000 });
  await delay(1500);
  assert.equal(loads, 2, 'typing is never reloaded under');
  assert.equal(await box.evaluate((el) => el.value), 'half a sentence');
  // ...the words are in the chat window, which the box opens (2026-10-28); no other dialog asks
  assert.equal(await page.$('[role="dialog"]:not([data-tq-chat-win])'), null, 'no dialog');
  assert.deepEqual(errors, []);
});
