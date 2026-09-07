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
  const traffic = [];
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/api/')) {
      traffic.push({ path: new URL(response.url()).pathname, status: response.status() });
      if (traffic.length > 30) traffic.shift();
    }
  });
  try {
  await page.goto(h.ui, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForFunction(() => [...document.querySelectorAll('.tq-pile-row .card b')]
    .filter(n => n.textContent.startsWith('Shared arrival')).length === 507, { timeout: 30000 });
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
  const previousCard = (await request(h, '/api/concierge')).messages
    .toReversed().find(message => message.card?.key && !message.card.background_event)?.card;
  assert.ok(previousCard?.key, 'Walk must have persisted its exact Current card');
  const previousMembers = previousCard.kind === 'fyis' ? previousCard.items.map(item => item.key) : [previousCard.key];
  assert.ok(previousMembers.length && previousMembers.every(key => key.startsWith('processing:')));
  const nextRequests = [];
  const observeTurn = req => {
    const path = new URL(req.url()).pathname;
    if (req.method() === 'POST' && path.startsWith('/api/concierge/')) {
      nextRequests.push({ path, body: JSON.parse(req.postData() || '{}') });
    }
  };
  page.on('request', observeTurn);
  const isTurn = (response, mode) => {
    const req = response.request();
    const path = new URL(response.url()).pathname;
    return req.method() === 'POST' && (path === `/api/concierge/${mode}`
      || (path === '/api/concierge/stream' && JSON.parse(req.postData() || '{}').mode === mode));
  };
  const [said, advanced] = await Promise.all([
    page.waitForResponse(response => isTurn(response, 'say'), { timeout: 20000 }),
    page.waitForResponse(response => isTurn(response, 'next'), { timeout: 20000 }),
    (async () => {
      await page.click('.tq-compose textarea');
      await page.type('.tq-compose textarea', 'Next');
      await page.keyboard.press('Enter');
    })(),
  ]);
  const completedTurn = async response => {
    const text = await response.text();
    assert.equal(response.status(), 200, text);
    return new URL(response.url()).pathname === '/api/concierge/stream'
      ? text.trim().split('\n').map(line => JSON.parse(line)).findLast(event => event.type === 'done')
      : JSON.parse(text);
  };
  assert.equal((await completedTurn(said)).decision?.verb, 'next', 'the fixture must exercise the model decision path');
  const nextResult = await completedTurn(advanced);
  assert.ok(nextResult?.item?.key, 'typed Next must land an item');
  assert.notEqual(nextResult.item.key, previousCard.key, 'typed Next advances past the Current it just put down');
  const nextBody = JSON.parse(advanced.request().postData());
  assert.equal(nextBody.exclude, previousCard.key, 'Current survives until the guarded Next captures its exclusion');
  assert.equal(nextBody.expected_next_key, nextResult.item.key);
  assert.equal(JSON.parse(nextBody.only.slice(5)).channel, 'email', 'typed Next keeps the shared category filter');
  const nextMembers = nextResult.item.kind === 'fyis' ? nextResult.item.items : [nextResult.item];
  assert.ok(nextMembers.every(item => !previousMembers.includes(item.key)), 'the previous FYI members are excluded too');
  await page.waitForFunction(title => document.querySelector('.tq-pile-row.current .card b')?.textContent.trim() === title,
    { timeout: 20000 }, nextMembers[0].title);
  await page.waitForFunction(() => !document.querySelector('.tq-typing'), { timeout: 20000 });
  page.off('request', observeTurn);
  assert.equal(nextRequests.filter(turn => turn.path === '/api/concierge/say' || turn.body.mode === 'say').length, 1);
  assert.equal(nextRequests.filter(turn => turn.path === '/api/concierge/next' || turn.body.mode === 'next').length, 1,
    'one typed Next performs exactly one guarded advance');
  const afterNext = await request(h, '/api/funnel/pile');
  // What the walk SHOWS is read, with NO exception - the owner removed the approve/blocked one on
  // 2026-09-07 ("hitting next or done should mark it read and then move on"): walking past a draft
  // ends the reply obligation rather than holding the row for another pass. Which row leads the pile
  // is nondeterministic since the levels became triage's verdict, so this stays lane-agnostic: it
  // holds whether the row left Unread outright or merely stopped being unread.
  for (const key of previousMembers) assert.notEqual(afterNext.items.find(item => item.key === key)?.unread, true,
    'walking past an item reads it: it does not come back as unread');
  await page.click('button[aria-label^="New chat"]');
  await page.waitForFunction(() => !document.querySelector('.tq-pile-row.current'), { timeout: 20000 });
  await page.waitForNetworkIdle({ idleTime: 200, timeout: 20000 });
  assert.equal(JSON.parse(scopedRequests.at(-1).slice(5)).channel, 'email', 'New chat keeps the visible shared filter');
  // the pile AS IT STANDS, not as it stood before the walk: the walk read what it showed, which is
  // the point of the rule above. What must not read anything is the view SWITCH itself.
  const beforeSwitch = (await request(h, '/api/funnel/pile')).items.map(i => i.key);
  await clickState(page, 'timeline');
  await page.waitForSelector('[data-processing-item]', { timeout: 20000 });
  assert.equal(await page.$('.tq-compose'), null);
  await clickState(page, 'work');
  await page.waitForSelector('.tq-pile-row', { timeout: 20000 });
  assert.deepEqual((await request(h, '/api/funnel/pile')).items.map(i => i.key), beforeSwitch,
    'switching views must not read any arrival');
  assert.deepEqual(page.fixtureEscapes, []);
  } catch (error) {
    console.error('Unread failure diagnostics', JSON.stringify({ traffic, ui: await page.evaluate(() => ({
      text: document.body.innerText.slice(-7000), current: document.querySelector('.tq-pile-row.current')?.innerText,
    })).catch(() => null) }));
    throw error;
  }
});
