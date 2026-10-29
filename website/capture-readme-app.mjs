// The README's task-view pictures (02-05, 12-14), from the real app on the demo world: the browser harness's own backend and home, no
// live account. Ruth's request is written into that home by readme_seed.py; the rest is the demo world as it ships. Run from the repo
// root with Node 22+, then frame them with render-readme.mjs:
// npm exec --yes --package=node@22 -- node website/capture-readme-app.mjs
import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { startHarness } from './browser/harness.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, '..');
const scratch = path.join(root, '.codex-tmp/readme');
await mkdir(scratch, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const h = await startHarness();
const seed = (...args) => execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
  [path.join(here, 'readme_seed.py'), ...args], { cwd: root, env: { ...process.env, TASKUARY_HOME: h.home }, encoding: 'utf8' }).trim();
const page = await h.newPage(), errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

// THE PICTURE IS THE PANE: the Taskuary pane - the card on its warm ground and the row under it - without the rail beside it
const shot = async name => {
  await page.mouse.move(2, 2); await sleep(600);
  const c = await page.evaluate(() => { let e = document.querySelector('.tq-dock');
    while (e && !e.querySelector('.tq-chat-body')) e = e.parentElement;
    const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, width: b.width, height: b.height }; });
  await page.screenshot({ path: path.join(scratch, name + '.png'), clip: c });
  await writeFile(path.join(scratch, name + '.txt'), await page.evaluate(() => document.body.innerText));
  console.log('Captured ' + name);
};
const openTask = async tid => {
  await page.evaluate(id => { location.hash = ''; location.hash = `task=${id}`; }, tid);
  await page.waitForSelector(`[data-tq-task-page="${tid}"] [data-tq-task-body][data-tq-sections]`, { timeout: 20000 }); await sleep(2000);
};
const rowKey = re => page.evaluate(src => [...document.querySelectorAll('[data-tq-rail] .tq-pile-row')].find(r => new RegExp(src).test(r.innerText))?.dataset.tqKey, re.source);
const clickRow = async re => {
  const k = await rowKey(re); assert.ok(k, `a rail row ${re}`);
  await page.evaluate(k => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), k); await sleep(3000);
};
const reportsOpen = () => page.evaluate(() => { const f = document.querySelector('[data-tq-section-head="reports"] .fold');
  if (f && !document.querySelector('[data-tq-run="reports"] .tq-pile-row')) f.click(); });
try {
  await page.goto(h.ui, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-tq-rail] .tq-pile-row', { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready); await sleep(1500);

  // 02 A REQUEST BECOMES A TASK: Came from open - what came in, what triage made of it, the ask - Agent and Close out folded beside it
  const tid = seed('ask');
  await openTask(tid); await shot('task');

  // 05 THE ASSISTANT: the chat window over the bar, on the task on the table
  await page.click('.tq-compose-box textarea');
  await page.waitForSelector('[data-tq-chat-win]:not([hidden])', { timeout: 5000 });
  await page.keyboard.type("What's on me right now?"); await page.keyboard.press('Enter');
  await page.waitForFunction(() => /looked at your list/.test(document.querySelector('[data-tq-chat-win]')?.innerText || ''), { timeout: 30000 });
  await page.waitForFunction(() => !document.querySelector('[data-tq-chat-win] .tq-pending'), { timeout: 30000 }); await sleep(800);
  await shot('assistant');

  // 03 + 04: the analyst finished - Close out opens on the drafted reply and its Send; the Agent's Result is what it did and made
  seed('done', tid);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-tq-rail] .tq-pile-row', { timeout: 30000 });
  await page.evaluate(() => document.querySelector('[data-tq-chat-win] [aria-label="Close"], [data-tq-chat-win] button[aria-label*="lose"]')?.click());
  await openTask(tid);
  await page.waitForSelector('[data-tq-closeout] textarea[data-tq-draft]', { timeout: 20000 }); await sleep(800);
  await shot('review');
  await page.click('[data-tq-section-tab=agent]');
  await page.waitForSelector('[data-tq-result-summary] [data-tq-result-made]', { visible: true, timeout: 20000 }); await sleep(800);
  await shot('agent');

  // 13 A REPORT in a task's three sections; 14 the dashboard, landed beside the reports
  await reportsOpen(); await sleep(1200);
  await clickRow(/Headcount by site/);
  await page.waitForSelector('[data-tq-item-sections="report"]', { timeout: 20000 }); await sleep(1500);
  await shot('report');
  // ...the shelf shows two reports and folds the rest under "N more reports"
  await page.evaluate(() => document.querySelector('[data-tq-run="reports"] .tq-pile-more')?.click()); await sleep(1500);
  await clickRow(/Taskuary at a glance/);
  await page.waitForSelector('[data-tq-dashboard]', { timeout: 20000 }); await sleep(2000);
  await shot('dashboard');

  // 12 AN FYI BATCH: the last report, then Next - every message of the batch on Came from, each folded to its line
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await page.evaluate(() => document.querySelector('[data-tq-row] [data-tq-next]').click());
  await page.waitForSelector('[data-tq-item-sections="fyis"]', { timeout: 20000 }); await sleep(1500);
  // ...the second batch: the first names a vendor company that reads like a real one, and the picture is public
  await page.evaluate(() => document.querySelector('[data-tq-row] [data-tq-next]').click()); await sleep(3000);
  await page.waitForFunction(() => /Statement of account/.test(document.querySelector('[data-tq-item-sections="fyis"]')?.innerText || ''), { timeout: 20000 });
  await shot('fyi');
  assert.deepEqual(errors, []);
} catch (e) {
  await page.screenshot({ path: path.join(scratch, 'app-failure.png') }); throw e;
} finally { await h.close(); }
