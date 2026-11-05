// The README's pictures of the work itself (02-05, 12-16), from the real app on the demo world: the browser harness's own backend and
// home, no live account. The general agent's finished day is part of that world (taskuary/demo.py seed_agent_day) - a LinkedIn post with
// its chart, a reply with a workbook, a dashboard, a browser hand-over, the owner's own answer. Run from the repo root with Node 22+, then
// frame them with render-readme.mjs:
// npm exec --yes --package=node@22 -- node website/capture-readme-app.mjs
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
const page = await h.newPage(), errors = [];
page.on('pageerror', e => errors.push(e.message));
const size = (height = 900) => page.setViewport({ width: 1440, height, deviceScaleFactor: 2 });
await size();

// THE PICTURE IS THE PANE: the Taskuary pane - the task on its warm ground and the row under it - without the rail beside it; `whole`: the window
const shot = async (name, whole = false) => {
  await page.mouse.move(2, 2); await sleep(600);
  const c = whole ? null : await page.evaluate(() => { let e = document.querySelector('.tq-dock');
    while (e && !e.querySelector('.tq-chat-body')) e = e.parentElement;
    const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, width: b.width, height: b.height }; });
  await page.screenshot({ path: path.join(scratch, name + '.png'), ...(c ? { clip: c } : {}) });
  await writeFile(path.join(scratch, name + '.txt'), await page.evaluate(() => document.body.innerText));
  console.log('Captured ' + name);
};
const tasks = () => page.evaluate(async tok => (await (await fetch('/api/tasks', { headers: { 'X-Taskuary-Token': tok } })).json()).data, h.token);
const openTask = async title => {
  const t = (await tasks()).find(x => x.Title.startsWith(title)); assert.ok(t, `a task "${title}"`);
  await page.evaluate(id => { location.hash = ''; location.hash = `task=${id}`; }, t.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${t.TaskId}"] [data-tq-task-body][data-tq-sections]`, { timeout: 20000 }); await sleep(3000);
  return t.TaskId;
};
const rowKey = re => page.evaluate(src => [...document.querySelectorAll('[data-tq-rail] .tq-pile-row')].find(r => new RegExp(src).test(r.innerText))?.dataset.tqKey, re.source);
const clickRow = async re => {
  const k = await rowKey(re); assert.ok(k, `a rail row ${re}`);
  await page.evaluate(k => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), k); await sleep(3000);
};
const reportsOpen = () => page.evaluate(() => { const f = document.querySelector('[data-tq-section-head="reports"] .fold');
  if (f && !document.querySelector('[data-tq-run="reports"] .tq-pile-row')) f.click(); });
const moreReports = () => page.evaluate(() => document.querySelector('[data-tq-run="reports"] .tq-pile-more')?.click());
try {
  await page.goto(h.ui, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-tq-rail] .tq-pile-row', { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready); await sleep(2500);

  // 02 A TASK IS ONE CHAT: what came in on the right with its channel and time, the agent's turn on the left - its time, how long it ran,
  // what this is about, what it did with its sources, and the question it leaves with the owner
  await openTask('Same-day pay'); await shot('task');

  // 05 THE ASSISTANT: the chat window over the bar, on the task on the table
  await page.click('.tq-compose-box textarea');
  await page.waitForSelector('[data-tq-chat-win]:not([hidden])', { timeout: 5000 });
  await page.keyboard.type("What's on me right now?"); await page.keyboard.press('Enter');
  await page.waitForFunction(() => /looked at your list/.test(document.querySelector('[data-tq-chat-win]')?.innerText || ''), { timeout: 30000 });
  await page.waitForFunction(() => !document.querySelector('[data-tq-chat-win] .tq-pending'), { timeout: 30000 }); await sleep(800);
  await shot('assistant');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-tq-rail] .tq-pile-row', { timeout: 30000 }); await sleep(1500);

  // 03 THE ACTION IS SET UP: the LinkedIn post it wrote, with the chart it made, waiting on one press
  await size(1350);
  await openTask('Fairhaven safety milestone');
  await page.waitForSelector('[data-tq-act] img', { visible: true, timeout: 20000 }); await sleep(1500);
  await shot('agent');

  // 04 NEXT STEPS HOLD THE REPLY: a second mail joined the thread, the first turn keeps its draft read-only, the newest one's card has the
  // workbook attached and its Send
  await size(1500);
  await openTask('September overtime by site'); await shot('next-steps');

  // 15 THE OWNER ANSWERED THEMSELVES: the agent sees it and recommends closing - it never closes the task itself
  await size(1000);
  await openTask('Trainly renewal'); await shot('owner-answered');

  // 16 A BROWSER HAND-OVER: it signed in through the owner, filled the payment and handed the Pay press over, then confirmed it went
  await size(1080);
  await openTask('PhishGuard renewal'); await shot('handover');

  // 13 A REPORT; 14 the dashboard the agent built, landed beside the reports
  await size(1100);
  await reportsOpen(); await sleep(1200);
  await clickRow(/Headcount by site/);
  await page.waitForSelector('[data-tq-item-sections="report"]', { timeout: 20000 }); await sleep(1500);
  await shot('report');
  await moreReports(); await sleep(1500);
  await clickRow(/Vendor spend, weekly/);
  await page.waitForSelector('[data-tq-dashboard]', { timeout: 20000 }); await sleep(2500);
  await shot('dashboard');

  await size();
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
