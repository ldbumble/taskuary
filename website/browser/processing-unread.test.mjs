import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';
import { waitForDemoReplays, settleDemoWatcher } from './processing-fixtures.mjs';

async function request(h, path, body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Taskuary-Token': h.token, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${path}: ${response.status} ${response.ok ? '' : await response.text()}`);
  return response.json();
}

async function clickState(page, label) {
  const handles = await page.$$('[role="group"][aria-label="Feed views"] *');
  for (const handle of handles) {
    if (await handle.evaluate((node, wanted) => node.children.length === 0
      && node.textContent.trim().toLowerCase() === wanted && node.getBoundingClientRect().width > 0, label)) {
      await handle.click(); return;
    }
  }
  assert.fail(`visible ${label} feed view was not found`);
}

test('All and Unread share 507 fresh roots, including ignored and pending triage', { timeout: 180000 }, async t => {
  const h = await startHarness();
  t.after(() => h.close());
  await settleDemoWatcher(h, await waitForDemoReplays(h));
  await request(h, '/api/fixture/processing/unread-activate', {});
  await request(h, '/api/fixture/processing/unread-arrivals', {});
  const pile = await request(h, '/api/funnel/pile');
  const arrivals = pile.items.filter(i => i.title.startsWith('Shared arrival'));
  assert.equal(arrivals.length, 507);
  assert.equal(new Set(arrivals.map(i => i.processing_id)).size, 507);
  assert.equal(arrivals.find(i => i.title === 'Shared arrival 505').actionable, false);
  assert.equal(arrivals.find(i => i.title === 'Shared arrival 506').unread, true);
  let cursor = null;
  const all = [];
  do {
    const page = await request(h, `/api/processing/all?limit=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
    all.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  assert.deepEqual(new Set(all.filter(i => i.title.startsWith('Shared arrival') && i.row.Unread).map(i => i.item_id)),
    new Set(arrivals.map(i => i.processing_id)));
  const page = await h.newPage();
  await page.goto(h.ui, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForFunction(() => [...document.querySelectorAll('.tq-pile-row .card b')]
    .filter(n => n.textContent.startsWith('Shared arrival')).length === 507, { timeout: 30000 });
  const before = (await request(h, '/api/funnel/pile')).items.map(i => i.key);
  const scopedRequests = [];
  page.on('request', req => {
    const url = new URL(req.url());
    if (url.pathname === '/api/funnel/pile') scopedRequests.push(url.searchParams.get('only'));
  });
  await page.click('[aria-label="Timeline category"]');
  await page.waitForSelector('[role="option"]', { visible: true, timeout: 5000 });
  for (const candidate of await page.$$('[role="option"]')) {
    if (await candidate.evaluate(n => n.textContent.trim() === 'email')) { await candidate.click(); break; }
  }
  await page.waitForFunction(() => document.querySelector('[aria-label="Timeline category"]')?.textContent.includes('email'));
  await page.waitForNetworkIdle({ idleTime: 200, timeout: 20000 });
  const walk = (await page.$$('button')).filter(Boolean);
  for (const candidate of walk) {
    if (await candidate.evaluate(n => n.textContent.trim() === 'Walk me through my tasks')) { await candidate.click(); break; }
  }
  await page.waitForSelector('.tq-pile-row.current', { timeout: 20000 });
  assert.equal(JSON.parse(scopedRequests.at(-1).slice(5)).channel, 'email', 'Walk keeps the visible shared filter');
  await page.waitForFunction(() => {
    const button = document.querySelector('button[aria-label^="New chat"]');
    return button && !button.disabled && !document.querySelector('.tq-typing');
  }, { timeout: 20000 });
  await page.click('button[aria-label^="New chat"]');
  await page.waitForFunction(() => !document.querySelector('.tq-pile-row.current'), { timeout: 20000 });
  await page.waitForNetworkIdle({ idleTime: 200, timeout: 20000 });
  assert.equal(JSON.parse(scopedRequests.at(-1).slice(5)).channel, 'email', 'New chat keeps the visible shared filter');
  await clickState(page, 'all');
  await page.waitForSelector('[data-processing-item]', { timeout: 20000 });
  assert.equal(await page.$('.tq-compose'), null);
  await clickState(page, 'unread');
  await page.waitForSelector('.tq-pile-row', { timeout: 20000 });
  assert.deepEqual((await request(h, '/api/funnel/pile')).items.map(i => i.key), before,
    'switching views must not read any arrival');
  assert.deepEqual(page.fixtureEscapes, []);
});
