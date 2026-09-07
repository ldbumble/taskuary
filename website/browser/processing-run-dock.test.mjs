// Unread is ranked, so the heading over it names the RUN the rail is crossing -
// not a date. A date there was actively misleading: the same day appears in several places down a
// ranked pile, so "Saturday, Sep 5" sat over rows from three different days (the owner, 2026-09-07:
// "the date on top makes no sense on the unread tab since we don't sort by date").
import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';
import { waitForDemoReplays, settleDemoWatcher } from './processing-fixtures.mjs';
import { RUN_META, RUN_ORDER, runLabel, runOf } from '../src/funnelPile.js';

async function request(h, path, body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Taskuary-Token': h.token, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${path}: ${response.status} ${response.ok ? '' : await response.text()}`);
  return response.json();
}

const dockText = (page) => page.$eval('[data-tq-run-dock]', (node) => node.textContent.trim());

// The rail's own geometry, read the way the dock's spy reads it: the run of the last row whose
// resting top has crossed the dock's edge. Computed fresh at assert time - the demo fixture keeps
// replaying arrivals, and content growing under a scrolled rail changes what is crossing.
const crossingRun = (page) => page.evaluate(() => {
  const rail = [...document.querySelectorAll('*')]
    .find((el) => el.scrollHeight > el.clientHeight + 4 && el.querySelector('.tq-pile-stack'));
  const stack = rail?.querySelector('.tq-pile-stack');
  if (!stack) return null;
  const base = stack.getBoundingClientRect().top - rail.getBoundingClientRect().top + rail.scrollTop;
  const tops = [...stack.querySelectorAll('.tq-pile-row[data-tq-run]')]
    .map((el) => ({ run: el.dataset.tqRun, top: base + (parseFloat(el.style.top) || 0) }))
    .sort((a, b) => a.top - b.top);
  const edge = rail.scrollTop + 1;
  let crossing = "", lastTop = -1;
  for (const row of tops) {
    if (row.top > edge) break;
    if (row.top === lastTop) continue;
    crossing = row.run; lastTop = row.top;
  }
  return { crossing: crossing || tops[0]?.run || "", scrollTop: rail.scrollTop,
           runs: [...new Set(tops.map((r) => r.run))] };
});

test('the Unread heading names the run the rail is crossing, and jumps between them', { timeout: 180000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  await settleDemoWatcher(h, await waitForDemoReplays(h));
  await request(h, '/api/fixture/processing/unread-activate', {});
  const pile = await request(h, '/api/funnel/pile');
  const runs = RUN_ORDER.filter((run) => pile.items.some((item) => runOf(item) === run));
  assert.ok(runs.length > 1, `this fixture needs at least two runs to move between, got ${runs}`);

  const page = await h.newPage();      // h.close() takes the browser with it; no page hook, or it
                                       // runs after the browser is gone and reports a dead socket
  // a short window on purpose: the rail has to be shorter than its own pile for there to be any
  // scroll to spy on (at full height these rows scroll 92px and no run is ever crossed)
  await page.setViewport({ width: 1280, height: 420 });
  await page.goto(h.ui, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForSelector('.tq-pile-row[data-tq-run]', { timeout: 30000 });
  // a row still dropping in sits at a NEGATIVE inline top (assistantView.css .landing)
  await page.waitForFunction(() => !document.querySelector('.tq-pile-row.landing'), { timeout: 20000 });

  // it is a RUN, never a date - and it is the run of the row under the dock
  const opening = await dockText(page);
  assert.ok(!/\d{4}|Today|Yesterday|Mon|Tue|Wed|Thu|Fri|Sat|Sun/.test(opening),
    `the heading is a run, never a date: ${opening}`);
  assert.ok(Object.values(RUN_META).some((m) => m.word === opening), `${opening} is not one of the runs`);
  assert.equal(opening, runLabel((await crossingRun(page)).crossing));

  // scrolling relabels it. Wherever the rail ends up - arrivals keep landing under it - the
  // heading names the run that is actually crossing the dock.
  await page.$$eval('.tq-pile-row[data-tq-run]', (rows) => {
    let scroller = rows[0].parentElement;
    while (scroller && scroller.scrollHeight <= scroller.clientHeight + 4) scroller = scroller.parentElement;
    scroller.scrollTop += 240;
  });
  for (let tries = 0; tries < 40 && (await dockText(page)) === opening; tries += 1) {
    await new Promise((done) => setTimeout(done, 100));
  }
  const scrolled = await dockText(page);
  assert.notEqual(scrolled, opening, 'scrolling into the next run relabels the heading');
  assert.ok(Object.values(RUN_META).some((m) => m.word === scrolled), `${scrolled} is not one of the runs`);
  // ...and it moved DOWN the pile, never to a run above the one we started on
  const wordOrder = runs.map((run) => runLabel(run));
  assert.ok(wordOrder.indexOf(scrolled) > wordOrder.indexOf(opening), `${opening} -> ${scrolled} is not further down`);

  // and the heading is navigation: pick the last run the pile holds and the rail glides to it
  const last = runs[runs.length - 1];
  await page.click('[data-tq-run-dock]');
  await page.waitForSelector('[role="option"], li[role="menuitem"]', { timeout: 10000 });
  const offered = await page.$$eval('[role="option"], li[role="menuitem"]',
    (nodes) => nodes.map((node) => node.textContent.trim()));
  assert.deepEqual(offered, runs.map((run) => runLabel(run)), 'the menu is exactly the runs the pile holds');
  await page.$$eval('[role="option"], li[role="menuitem"]', (nodes, word) => {
    nodes.find((node) => node.textContent.trim() === word).click();
  }, runLabel(last));
  // the picker owns the heading through its glide (dateJump), so this is the choice landing, not
  // the spy catching up - the glide itself is not asserted: arrivals keep resetting the rail here
  await page.waitForFunction((word) => document.querySelector('[data-tq-run-dock]')?.textContent.trim() === word,
    { timeout: 10000 }, runLabel(last));
  assert.equal(await dockText(page), runLabel(last));
});
