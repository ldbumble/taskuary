// Real UI, sealed demo data. Run from the repo root with Node 22+.
// npm exec --yes --package=node@22 -- node website/capture-readme.mjs
import { createServer } from 'vite';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { launch } from './browser.mjs';
import { installNumbersWorkflow } from './src/demoNumbers.js';
import { createDemoAssistantState, installDemoAssistantTimeline } from './src/demoAssistantData.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.codex-tmp/readme');
await mkdir(scratch, { recursive: true });
const fixture = JSON.parse(await readFile(path.join(root, 'website/src/demoFixtures.json'), 'utf8'));
fixture['/api/tasks/detail'][17].comments = [];
fixture['/api/tasks/detail'][17].transcript = null;
fixture['/api/calendar/today'] = { date: '2026-09-03', now: '10:24', errors: [], events: [
  { subject: 'Operations review', start: '2026-09-03T11:30:00', end: '2026-09-03T12:15:00', who: ['Ruth Bennett', 'Marcus Reed'], about: 'August spend and open operational items' },
  { subject: 'Vendor planning', start: '2026-09-03T14:00:00', end: '2026-09-03T15:30:00', who: ['Ruth Bennett'], about: 'Plan next month’s purchasing' },
] };
const digestText = 'NOW: Thursday, September 3 · Your morning brief\n\n🙋 People want\n- Ruth needs the August vendor spend numbers before the 11:30 operations review. TQ-0018 http://127.0.0.1/#task=18\n\n🚀 In flight\n- Prepare the total, the change from July, and a category breakdown. The reply comes back to you for approval.\n\n📅 Today\n- 11:30 · Operations review with Ruth and Marcus — August spend and open operational items.\n- 14:00 · Vendor planning with Ruth — plan next month’s purchasing.';
const digest = { ...fixture['/api/feed'].data.find(r => r.Channel === 'report'), MessageId: 939, Subject: 'Morning digest', SourceName: 'Morning digest', FromName: 'Taskuary', SentAt: '2026-09-03 10:23:00', CreatedAt: '2026-09-03 10:23:00', ConversationId: 'report:readme-morning', Preview: digestText, BodyText: digestText, TaskId: null, Category: 'report' };
fixture['/api/feed'].data.unshift(digest);
fixture['/api/messages/one'][939] = digest;
fixture['/api/cli/connections'] = { data: [
  ...fixture['/api/cli/detect'].data.filter(c => ['claude', 'codex'].includes(c.name)).map(c => ({ ...c, configured: true, setup: c.name, config: { cmd: c.cmd, args: c.args, timeout: c.timeout } })),
  ...[['gemini', 'Gemini CLI'], ['copilot', 'GitHub Copilot']].map(([name,label]) => ({ name, label, installed: false, configured: false, installable: true, install: name, config: { cmd: name, args: [], timeout: 1500 } })),
] };
fixture['/api/board/notes'].data.forEach(n => { if (n.Agent === 'codex') n.ReadBy = 'coder'; if (n.Agent === 'coder') n.ReadBy = 'codex'; });
fixture['/api/hub'].data[0].comments = [
  { CommentId: 1, Author: 'coder', CreatedAt: '2026-09-03 10:12:00', Body: 'I can add a dry-run check that reports missing account mappings before anything is written.' },
  { CommentId: 2, Author: 'codex', CreatedAt: '2026-09-03 10:18:00', Body: 'Include the rollback steps in the handoff. The next agent should know how to reverse the change.' },
];
// The saved demo predates the canonical Timeline endpoint. Supply its current response
// shape from the same sample records, without changing the app or hiding an error banner.
const timelineFixture = structuredClone(fixture);
installDemoAssistantTimeline(timelineFixture);
installNumbersWorkflow(timelineFixture, createDemoAssistantState());
const seen = new Set();
const timelineRows = timelineFixture['/api/feed'].data.sort((a,b) => b.SentAt.localeCompare(a.SentAt)).filter(row => {
  const key = row.TaskId ? `task:${row.TaskId}` : row.ConversationId || `message:${row.MessageId}`;
  if (seen.has(key)) return false;
  seen.add(key); return true;
});
fixture['/api/processing/all'] = { schema_version: 'taskuary.processing.all.v1', snapshot_revision: 'readme-demo', next_cursor: null,
  items: timelineRows.map(row => {
    const item = { item_id: `readme-${row.MessageId}`, member_ids: [`message:${row.MessageId}`], open_target: { kind: 'message', id: row.MessageId }, context_revision: '1', view_revision: '1', row };
    fixture[`/api/processing/items/${item.item_id}/detail`] = { ...item, detail: { messages: [row], reviews: [], attachments: [] } };
    return item;
  }) };
const server = await createServer({ root: path.join(root, 'website'), mode: 'demo', server: { host: '127.0.0.1', port: 0 }, plugins: [{
  name: 'readme-fictional-morning', enforce: 'pre',
  load(id) { if (id.replaceAll('\\', '/').endsWith('/src/demoFixtures.json')) return JSON.stringify(fixture); },
}] });
await server.listen();
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
const browser = await launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
await page.setViewport({ width: 1200, height: 1000, deviceScaleFactor: 2 });
await page.evaluateOnNewDocument(() => {
  const NativeDate = Date;
  window.Date = class extends NativeDate {
    constructor(...args) { super(...(args.length ? args : ['2026-09-03T10:24:00'])); }
    static now() { return new NativeDate('2026-09-03T10:24:00').getTime(); }
  };
});
const click = async (text, selector = 'button', includes = false) => {
  const args = { text, selector, includes };
  await page.waitForFunction(({text,selector,includes}) => [...document.querySelectorAll(selector)].some(e => e.getBoundingClientRect().height && (includes ? e.textContent.includes(text) : e.textContent.trim() === text)), {}, args);
  await page.evaluate(({text,selector,includes}) => [...document.querySelectorAll(selector)].find(e => e.getBoundingClientRect().height && (includes ? e.textContent.includes(text) : e.textContent.trim() === text)).click(), args);
  await delay(500);
};
const nav = text => click(text, '#tqTopNav div');
const shot = async name => {
  await page.mouse.move(1430, 990);
  await delay(400);
  const content = await page.evaluate(() => document.body.innerText);
  if (name !== 'failure') assert.doesNotMatch(content, /unsupported canonical All|Something in this view failed to draw/);
  await page.screenshot({ path: path.join(scratch, name + '.png') });
  await writeFile(path.join(scratch, name + '.txt'), content);
  console.log('Captured ' + name);
};
try {
  await page.goto(origin + '/?workflow=numbers', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => [...document.querySelectorAll('button')].find(e => e.textContent.trim() === 'Put it away')?.click());
  await delay(1000);
  if (!process.argv.includes('--extras')) {
  await click('timeline', 'div');
  await page.evaluate(() => { document.querySelector('[data-tq-timeline-stage]').parentElement.style.gridTemplateColumns = '720px minmax(0,1fr)'; });
  await shot('timeline');
  await page.evaluate(() => { document.querySelector('[data-tq-timeline-stage]').parentElement.style.gridTemplateColumns = ''; });
  await click('work', 'div');
  await click('Walk me through my tasks');
  await page.waitForFunction(() => document.body.innerText.includes('Open TQ-0018'));
  await page.setViewport({ width: 1200, height: 720, deviceScaleFactor: 2 });
  await shot('assistant');
  await page.setViewport({ width: 1200, height: 1000, deviceScaleFactor: 2 });
  await nav('Tasks'); await click('TQ-0018', '[data-tq-task-row]', true);
  await shot('task');
  await click('Agent work', 'p,span,div'); await click('Send to agent');
  await page.waitForFunction(() => document.body.innerText.includes('August vendor spend is ready for review'), { timeout: 30000 });
  await shot('agent');
  await nav('Review');
  await page.waitForFunction(() => [...document.querySelectorAll('textarea')].some(e => e.value.includes('August vendor spend was')));
  await page.evaluate(() => { const t = [...document.querySelectorAll('textarea')].find(e => e.value.includes('August vendor spend was')); let box=t.parentElement; while(box && getComputedStyle(box).maxWidth !== '980px') box=box.parentElement; if(box) box.style.maxWidth='800px'; t.style.maxHeight = 'none'; t.style.height = t.scrollHeight + 'px'; });
  await shot('review');
  }
  await nav('Assistant'); await click('Task', '.tq-stage-mode button');
  await click('timeline', 'div');
  await click('Morning digest', '.tqRow [data-tq-keep]', true);
  await click('Message', '[data-tq-timeline-stage] [role="tab"]');
  await page.waitForSelector('[data-tick]');
  await shot('digest');
  // Replay the actual meeting-strip entrance and clock pulse at deterministic times.
  // Only browser animation clocks change; the UI and its calendar data stay intact.
  await page.evaluate(() => {
    window.readmeAnimations = document.querySelector('[data-tick]').getAnimations({ subtree: true });
    window.readmeAnimations.forEach(a => a.pause());
  });
  for (let i = 0; i < 25; i++) {
    await page.evaluate(t => window.readmeAnimations.forEach(a => { a.currentTime = t; }), i * 80);
    await page.screenshot({ path: path.join(scratch, `morning-${String(i).padStart(2,'0')}.png`) });
  }
  await nav('Connections');
  const search = await page.waitForSelector('input[placeholder^="Search connectors"]');
  await search.type('AI CLI agents'); await click('AI CLI agents', 'p');
  await page.waitForSelector('[data-connection="claude"]');
  await shot('cli');
  await nav('Hub'); await delay(800); await click('2 comments'); await shot('hub');
  await nav('Board'); await click('Live handoffs', 'div'); await shot('handoffs');
  assert.deepEqual(errors, []);
} catch (error) {
  await shot('failure');
  throw error;
} finally { await browser.close(); await server.close(); }
