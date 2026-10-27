// A REMOVE ACTS AT ONCE, AND UNDO TAKES IT BACK (the owner, 2026-10-21: no "are you sure"). Against the demo world's real server:
// a report removed from its editor lands back on the list under "Removed <it> - Undo", Undo brings it back, Recently deleted
// restores it; a routing rule's bin does the same; a refused Undo is said on the line, never swallowed; nothing opens a dialog.
import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';

const has = (page, text, timeout = 15000) => page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);
const gone = (page, text, timeout = 15000) => page.waitForFunction((t) => !document.body.innerText.includes(t), { timeout }, text);
async function press(page, text, selector = 'button') {
  await page.waitForFunction(({ text, selector }) => [...document.querySelectorAll(selector)].some((el) => el.textContent.trim() === text && el.getBoundingClientRect().height), { timeout: 15000 }, { text, selector });
  await page.evaluate(({ text, selector }) => [...document.querySelectorAll(selector)].find((el) => el.textContent.trim() === text && el.getBoundingClientRect().height).click(), { text, selector });
}
const noDialog = async (page) => assert.equal(await page.$('[role="dialog"]'), null, 'a Remove never asks first');

test('Remove acts at once on a report and a rule; Undo and Recently deleted bring them back; a refused Undo says why', { timeout: 180000 }, async (t) => {
  // a fresh install, not the demo: the demo world refuses every write that would reach something real, Remove included
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const api = (path, init = {}) => fetch(`${harness.fixtureApi}${path}`, { ...init, headers: { 'Content-Type': 'application/json', 'X-Taskuary-Token': harness.token, ...(init.headers || {}) } }).then((r) => r.json());
  const TITLE = 'Northwind cash check';
  const sources = async () => { const r = await api('/api/sources'); return r.data || r; };
  const made = await api('/api/sources', { method: 'POST', body: JSON.stringify({ Channel: 'report', Address: TITLE, Active: true,
    ConfigJson: JSON.stringify({ type: 'sql', title: TITLE, daily_at: '07:00' }) }) });
  const sourceId = made.sourceId ?? made.SourceId;
  assert.ok(sourceId, `the report was made: ${JSON.stringify(made)}`);
  const page = await harness.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('dialog', (d) => { errors.push(`a browser dialog: ${d.message()}`); d.dismiss(); });

  // the report: its editor's Remove, at once, and the list it lands on says so with Undo
  await page.goto(`${harness.ui}#report=${sourceId}`, { waitUntil: 'domcontentloaded' });
  await press(page, 'Remove report');
  if (process.env.SHOT) { await new Promise((r) => setTimeout(r, 4000)); await page.screenshot({ path: process.env.SHOT }); }
  await has(page, `Removed ${TITLE}`);
  await noDialog(page);
  assert.equal((await sources()).some((s) => s.SourceId === sourceId), false, 'gone on the press');
  await press(page, 'Undo');
  await gone(page, `Removed ${TITLE}`);
  assert.equal((await sources()).some((s) => s.SourceId === sourceId), true, 'Undo put it back');

  // ...and again, then Restore from Recently deleted, under the list
  await page.goto(`${harness.ui}#report=${sourceId}`, { waitUntil: 'domcontentloaded' });
  await press(page, 'Remove report');
  await has(page, 'Recently deleted');
  await press(page, 'Restore');
  await page.waitForFunction(() => !document.querySelector('[data-tq-recently-deleted]'), { timeout: 15000 });
  assert.equal((await sources()).some((s) => s.SourceId === sourceId), true, 'Restore put it back');

  // a rule's bin: at once, Undo on the list; and an Undo the server refuses is said on the line
  const rule = await api('/api/policies', { method: 'POST', body: JSON.stringify({ Name: 'Mute the vendor newsletter', Kind: 'sender',
    Pattern: 'news@vendor.example', Action: 'ignore', Reason: 'a newsletter nobody reads', Active: true }) });
  assert.ok((await api('/api/policies')).data.some((p) => p.Name === 'Mute the vendor newsletter'), `the rule was made: ${JSON.stringify(rule)}`);
  await page.goto(`${harness.ui}#settings=policies`, { waitUntil: 'domcontentloaded' });
  if (process.env.SHOT2) { await new Promise((r) => setTimeout(r, 5000)); await page.screenshot({ path: process.env.SHOT2 }); }
  await has(page, 'Mute the vendor newsletter');
  await page.click('[aria-label="Remove this rule"]');
  await has(page, 'Removed Mute the vendor newsletter');
  await noDialog(page);
  page.off('request', page.fixtureRequestGuard);
  page.on('request', (r) => {
    if (r.method() === 'POST' && /\/api\/deleted\/\d+\/restore$/.test(new URL(r.url()).pathname))
      return r.respond({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'it is no longer in Recently deleted' }) });
    page.fixtureRequestGuard(r);
  });
  await press(page, 'Undo');
  await has(page, 'it is no longer in Recently deleted');                   // the failure, said where it happened
  assert.deepEqual(errors, []);
});

test('Not ours files at once, just this once, and offers From now on under its receipt - no card with Cancel', { timeout: 180000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: 'domcontentloaded' });
  const notOurs = () => page.evaluate(() => [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Not ours' && b.getBoundingClientRect().height));
  // each rail row in turn, until one whose row carries Not ours is on the table
  await page.waitForSelector('[data-tq-rail] [data-tq-key]', { timeout: 30000 });
  const keys = await page.$$eval('[data-tq-rail] [data-tq-key]', (rows) => rows.map((r) => r.getAttribute('data-tq-key')));
  for (const k of keys) {
    const h = await page.$(`[data-tq-rail] [data-tq-key="${k}"]`);
    if (!h || !(await h.boundingBox())) continue;
    await h.click(); await new Promise((r) => setTimeout(r, 3000));
    if (await notOurs()) break;
  }
  assert.ok(await notOurs(), 'a row on the table carries Not ours');
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Not ours' && b.getBoundingClientRect().height).click());
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some((b) => /^From now on/.test(b.textContent.trim())), { timeout: 20000 });
  // ...and it STAYS in reach once the walk has moved on - it was a flash between the receipt and the next item, gone when the row drew once
  await new Promise((r) => setTimeout(r, 2000));
  assert.ok(await page.evaluate(() => [...document.querySelectorAll('button')].some((b) => /^From now on/.test(b.textContent.trim()) && b.getBoundingClientRect().height)),
    'From now on stays on the row after the walk moves on');
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT });
  assert.equal(await page.evaluate(() => [...document.querySelectorAll('.tq-proposal button')].some((b) => /^Cancel$/.test(b.textContent.trim())
    && b.getBoundingClientRect().height)), false, 'no card waits for a yes');
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /learn: false/);
  assert.deepEqual(errors, []);
});

test('Remove connection wipes at once with Undo on the card; leaving with an unsaved change keeps it, without a browser box', { timeout: 180000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const api = (path, init = {}) => fetch(`${harness.fixtureApi}${path}`, { ...init, headers: { 'Content-Type': 'application/json', 'X-Taskuary-Token': harness.token, ...(init.headers || {}) } }).then((r) => r.json());
  const imap = (await api('/api/connectors')).data.find((c) => c.Type === 'imap');
  assert.ok(imap, 'the catalogue has an IMAP card');
  await api('/api/connectors', { method: 'POST', body: JSON.stringify({ ConnectorId: imap.ConnectorId, Active: true, Secret: 'app-password',
    ConfigJson: JSON.stringify({ host: 'mail.northwind.example', username: 'alex@northwind.example' }) }) });
  await api('/api/sources', { method: 'POST', body: JSON.stringify({ Channel: 'email', Address: 'alex@northwind.example', ConnectorId: imap.ConnectorId, Active: true }) });
  const page = await harness.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('dialog', (d) => { errors.push(`a browser dialog: ${d.message()}`); d.dismiss(); });
  const card = async () => (await api('/api/connectors')).data.find((c) => c.ConnectorId === imap.ConnectorId);

  await page.goto(`${harness.ui}#connector=imap`, { waitUntil: 'domcontentloaded' });
  await press(page, 'Remove connection');
  await page.waitForSelector('[data-tq-undo="connection"]', { timeout: 15000 });
  await noDialog(page);
  assert.equal((await card()).HasSecret, 0, 'wiped on the press');
  await press(page, 'Undo');
  await page.waitForFunction(() => !document.querySelector('[data-tq-undo="connection"]'), { timeout: 15000 });
  const back = await card();
  assert.equal(back.HasSecret, 1, 'Undo put its sign-in back');
  assert.equal(JSON.parse(back.ConfigJson).host, 'mail.northwind.example');

  // an unsaved change, then the crumb: no "Leave without saving" box, and the change is still there when the card opens again
  await press(page, 'Mailbox', 'span');                                         // the step that lists its mailboxes, each with its switch
  await page.waitForSelector('[aria-label="Remove alex@northwind.example"]', { timeout: 15000 });
  await page.evaluate(() => document.querySelector('[aria-label="Remove alex@northwind.example"]').parentElement.querySelector('input[type="checkbox"]').click());
  await has(page, 'unsaved change');
  await press(page, 'Email');                                                   // the crumb
  await gone(page, 'unsaved change');
  await page.goto(`${harness.ui}#connector=imap`, { waitUntil: 'domcontentloaded' });
  await has(page, 'unsaved change');
  assert.deepEqual(errors, []);
});
