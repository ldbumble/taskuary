// QUIT AND A WAITING UPDATE (the owner, 2026-10-25), against the demo world's real UI with the two routes answered by the test, so the
// harness's own server keeps running: Quit sits on the top line with the hover saying what stops, its press leaves a plain "Taskuary
// has stopped" page and no dialog; the Assistant's Updates link lights the real Update button; and Update now with an agent running
// says what it waits for instead of swapping the program.
import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';

const json = (r, body) => r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });

test('Quit on the top line stops it with no box asking; Updates lights its button and an update waits for running work', { timeout: 180000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], quits = [], updates = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (r) => {
    const p = new URL(r.url()).pathname;
    if (p === '/api/quit') { quits.push(r.method()); return json(r, r.method() === 'GET' ? { agents: 1, workflows: 0, running: '1 running agent' } : { quitting: true, stopped: ['TQ-0012'] }); }
    if (p === '/api/update') {
      updates.push(r.method());
      return json(r, r.method() === 'GET' ? { current: '0.3.9.34', latest: '0.3.9.35', newer: true, how: 'exe', error: null, waits: 'Update waits for 1 running agent', queued: updates.includes('POST') }
        : { waiting: true, waits: 'Update waits for 1 running agent', restarting: false });
    }
    return page.fixtureRequestGuard(r);
  });

  // the Assistant's link: Settings → Updates, its Update button lit until it is pressed
  await page.goto(`${harness.ui}#settings=updates&key=update`, { waitUntil: 'domcontentloaded' });
  const btn = await page.waitForSelector('[data-tq-knob="update"]:not([disabled])', { timeout: 30000 });
  assert.equal(await btn.evaluate((e) => e.textContent), 'Update to v0.3.9.35');
  assert.equal(await btn.evaluate((e) => e.hasAttribute('data-tq-asked')), true, 'the real button is lit');
  await btn.click();
  await page.waitForFunction(() => document.body.innerText.includes('Update waits for 1 running agent - it starts by itself when that is done.'), { timeout: 15000 });
  assert.equal(await page.$eval('[data-tq-knob="update"]', (e) => e.hasAttribute('data-tq-asked')), false, 'pressed: no longer lit');
  assert.equal(await page.$eval('[data-tq-knob="update"]', (e) => e.textContent), 'Waiting…');

  // Quit: on the top line, the hover reads what stops, and the press leaves the stopped page
  const quit = await page.waitForSelector('#tqTopNav [data-tq-quit]', { timeout: 15000 });
  await quit.hover();
  await page.waitForFunction(() => [...document.querySelectorAll('[role="tooltip"]')].some((e) => e.innerText.includes('and the 1 running agent with it')), { timeout: 10000 });
  await quit.click();
  await page.waitForSelector('[data-tq-stopped]', { timeout: 10000 });
  const said = await page.$eval('[data-tq-stopped]', (e) => e.innerText);
  assert.match(said, /Taskuary has stopped/); assert.match(said, /The work on TQ-0012 stopped with it/);
  assert.equal(await page.$('#tqTopNav'), null, 'nothing of the app is left to call a server that is gone');
  assert.equal(await page.$('[role="dialog"]'), null, 'no dialog');
  assert.deepEqual(quits.filter((m) => m === 'POST'), ['POST']);
  assert.deepEqual(errors, []);
});
