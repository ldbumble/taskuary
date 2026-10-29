// THE BUILDER'S QUESTIONS, PRESSED (the owner, 2026-10-29): New > Report's "Build it" asked which repository as a free-text box, and
// "Answer & build" sat greyed and still once pressed. Against the demo world's server, with the composer and the repository list
// answered by the test: a repo question is the repository dropdown, a choice is a select, Answer & build presses with a box left
// blank, spins with a status line while it builds, a second press sends nothing, and a miss keeps the questions with Try again.
import assert from 'node:assert/strict';
import test from 'node:test';
import { startHarness } from './harness.mjs';

const delay = (ms) => new Promise((r) => setTimeout(r, ms));
const REPO_Q = 'Which repository holds the review skill?', SITE_Q = 'Which sites?', NOTE_Q = 'Anything it should skip?';

test('a repository question is the repository list, and Answer & build shows it is working', { timeout: 180000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], sent = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.off('request', page.fixtureRequestGuard);
  page.on('request', async (r) => {
    const p = new URL(r.url()).pathname;
    const json = (body, status = 200) => r.respond({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (p === '/api/repos') return json({ data: [{ repo: 'northwind/ledger', has_path: true }, { repo: 'northwind/portal', has_path: false }] });
    if (p !== '/api/reports/compose') return page.fixtureRequestGuard(r);
    const body = JSON.parse(r.postData() || '{}'); sent.push(body);
    if (!body.answers) return json({ questions: [REPO_Q, SITE_Q, NOTE_Q], asks: [{ q: REPO_Q, kind: 'repo', options: [] },
      { q: SITE_Q, kind: 'choice', options: ['North', 'South'] }, { q: NOTE_Q, kind: 'text', options: [] }] });
    await delay(2500);
    return json({ detail: 'the model timed out' }, 502);
  });

  await page.setViewport({ width: 1366, height: 900 });
  await page.goto(`${harness.ui}/#new-task`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-tq-new] [role=tab]', { timeout: 30000 });
  await page.$$eval('[data-tq-new] [role=tab]', (tabs) => tabs.find((x) => x.textContent.includes('Report'))?.click());
  const box = await page.waitForSelector('[data-tq-new] textarea[placeholder*="exports"]', { visible: true, timeout: 15000 });
  await box.type('run the review skill every week');
  await page.$$eval('[data-tq-new] button', (bs) => bs.find((b) => b.textContent.trim() === 'Build it')?.click());

  // the repository question is the repository list, the choice its options, the rest a text box
  const repo = await page.waitForSelector(`select[aria-label="${REPO_Q}"]:not([disabled])`, { timeout: 15000 });
  assert.deepEqual(await repo.$$eval('option', (os) => os.map((o) => o.textContent)), ['choose…', 'northwind/ledger', 'northwind/portal', 'Another repository…']);
  assert.deepEqual(await page.$eval(`select[aria-label="${SITE_Q}"]`, (s) => [...s.options].map((o) => o.textContent)), ['choose…', 'North', 'South', 'Something else…']);
  assert.ok(await page.$('[data-tq-ask="text"]'), 'a text question stays a text box');

  // nothing answered: the button waits, and says why on hover
  const btn = '[data-tq-answer-build]';
  assert.equal(await page.$eval(btn, (b) => b.disabled), true);
  await page.hover(`span:has(> ${btn})`);
  await page.waitForFunction(() => document.querySelector('[role=tooltip]')?.textContent.includes('Answer at least one'), { timeout: 5000 });

  // one answered of three: it presses, and a second press while it builds sends nothing
  await repo.select('northwind/ledger');
  await page.waitForFunction((s) => !document.querySelector(s).disabled, { timeout: 5000 }, btn);
  assert.match(await page.evaluate(() => document.querySelector('[data-tq-new]').innerText), /2 left blank/);
  await page.click(btn); await page.click(btn).catch(() => {});
  await page.waitForFunction((s) => document.querySelector(s).textContent.includes('Building…') && document.querySelector(s).querySelector('[role=progressbar]'),
    { timeout: 3000 }, btn);
  assert.ok(await page.$$eval('[role=status]', (xs) => xs.some((x) => x.textContent.includes('Building it from your answers'))), 'a status line says it is building');
  await delay(400); await page.evaluate((s) => document.querySelector(s).click(), btn);
  assert.equal(sent.filter((b) => b.answers).length, 1, 'one press while it builds');
  assert.deepEqual(sent[1].answers, { [REPO_Q]: 'northwind/ledger', [SITE_Q]: '', [NOTE_Q]: '' }, 'blank answers go back as blanks');

  // the miss is a sentence with Try again, and the questions and the answer stay
  await page.waitForSelector('[data-tq-composer-retry]', { timeout: 10000 });
  assert.match(await page.evaluate(() => document.querySelector('[data-tq-new]').innerText), /the model timed out/);
  assert.equal(await page.$eval(`select[aria-label="${REPO_Q}"]`, (s) => s.value), 'northwind/ledger');
  await page.click('[data-tq-composer-retry]');
  for (let i = 0; i < 50 && sent.length < 3; i++) await delay(100);
  assert.deepEqual(sent[2]?.answers, sent[1].answers, 'Try again sends the same answers');
  assert.deepEqual(errors, []);
});
