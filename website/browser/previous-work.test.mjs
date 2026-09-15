import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { clickNav, startHarness } from './harness.mjs';

test('Previous work shows saved recaps and only resumes after a click', { timeout: 120000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), resumed = [], pulled = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let fail = true;
  const items = [
    { taskId: 1, title: 'Finish the item report', recap: 'August figures collected. Next: compare them with July.', lastWorkedAt: '2026-09-13 17:30:00', action: 'resume' },
    { taskId: 2, title: 'Review the prepared summary', recap: 'Summary ready. Waiting for your approval.', lastWorkedAt: '2026-09-13 16:00:00', action: 'review', reviewId: 21 },
  ];
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname; let data, status = 200;
    if (path === '/api/assistant/previous-work') data = { data: items };
    if (path === '/api/tasks/1/resume') {
      resumed.push(JSON.parse(request.postData() || '{}'));
      if (fail) { status = 422; data = { detail: 'Connect an AI provider to resume.' }; }
      else data = { action: 'review', taskId: 1, reviewId: 22 }; // It became ready since the card loaded.
    }
    if (path === '/api/concierge/stream') {
      pulled.push(JSON.parse(request.postData()).key);
      return request.respond({ status: 200, contentType: 'application/x-ndjson', body: JSON.stringify({ type: 'done', say: 'The saved draft is ready for review.' }) + '\n' });
    }
    if (data) return request.respond({ status, contentType: 'application/json', body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  await page.goto(harness.ui, { waitUntil: 'domcontentloaded' });
  await clickNav(page, 'Assistant');
  const shelf = '[aria-label="Continue previous work"]';
  await page.waitForSelector(shelf);
  if (await page.$eval(`${shelf} button[aria-expanded]`, (b) => b.getAttribute('aria-expanded')) === 'false')
    await page.click(`${shelf} button[aria-expanded]`);
  assert.match(await page.$eval(shelf, (el) => el.innerText), /August figures collected/);
  assert.deepEqual(resumed, [], 'Loading the welcome card never starts an agent');
  const click = (text) => page.evaluate(({ shelf, text }) => [...document.querySelectorAll(`${shelf} button`)].find((b) => b.textContent === text).click(), { shelf, text });
  await click('Continue');
  await page.waitForFunction(() => document.body.innerText.includes('Connect an AI provider to resume'));
  assert.equal(resumed.length, 1);
  await mkdir('../.codex-tmp', { recursive: true });
  await page.screenshot({ path: '../.codex-tmp/previous-work.png', fullPage: true });
  await click('Review draft');
  await page.waitForFunction(() => document.body.innerText.includes('The saved draft is ready for review'));
  assert.deepEqual(pulled, ['review:21']);
  assert.equal(resumed.length, 1, 'Review does not start a session');
  fail = false;
  await click('Continue');
  await page.waitForFunction(() => ![...document.querySelectorAll('[aria-label="Continue previous work"] button')].some((b) => b.disabled));
  await page.waitForFunction(() => document.body.innerText.split('The saved draft is ready for review.').length >= 3);
  assert.equal(resumed.length, 2);
  assert.deepEqual(pulled, ['review:21', 'review:22']);
  assert.deepEqual(errors, []);
});
