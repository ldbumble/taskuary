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
const learned = `# LEARNED.md — how Dana works

Preferences learned from corrections, with evidence attached.
Edit or delete any line. SOUL.md always takes precedence.

## Voice & style
- Lead with the number, then explain the change.
  [s:5 | ev: rv12,rv15,rv31 | seen: 2026-09-03]
- Keep replies brief; leave out the long greeting.
  [s:4 | ev: rv18,rv22,rv34 | seen: 2026-09-03]

## Role & responsibilities
- Dana reviews vendor spend before the operations meeting.
  [s:4 | ev: mem8,mem11,mem19 | seen: 2026-09-03]

## Hypotheses — still being tested
<!-- hypotheses:start -->
- Include a category breakdown when comparing monthly spend.
  [s:2 | ev: rv35 | seen: 2026-09-03]
<!-- hypotheses:end -->

## Proposed rules — your call
<!-- proposed:start -->
- File routine vendor maintenance notices as FYI.
  [s:4 | ev: rv9,rv17,rv28 | seen: 2026-09-03]
<!-- proposed:end -->
`.replace(/\n  \[/g, ' [');
// Authored sample memory; only the capture fixture receives these illustrative lessons.
fixture['/api/doc'].learned.content = learned;
fixture['/api/doc'].learned.rendered = learned;
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
// THE OPENING CARD'S TOP (since.py): what changed since last night, counted - the same fictional morning as the rest
fixture['/api/since'] = {
  overnight: { line: '', mail: 23, reports: 3, closed: 4, sessions: 2 },
  learned: { line: 'Learned this week: 3 new things about how you work.', n: 3, latest: 'Lead with the number, then explain the change.' },
  cards: [
    { kind: 'agent', label: 'Agent finished · TQ-0006', text: 'Reconciled the August GL export - two entries need a look', key: 'task:6' },
    { kind: 'agent', label: 'Agent finished · TQ-0011', text: 'Updated the vendor list for the September close', key: 'task:11' },
    { kind: 'report', label: 'Report ran · 06:00', text: 'Process Error Check: 1 real failure overnight', key: 'report:939' },
  ],
  digest: { source_id: 3, at: '2026-09-03T08:00:00', text: digestText },      // ISO on purpose: the demo clock moves "YYYY-MM-DD HH:MM:SS" stamps
};
fixture['/api/cli/connections'] = { data: [
  ...fixture['/api/cli/detect'].data.filter(c => c.name === 'claude').map(c => ({ ...c, configured: true, setup: c.name, config: { cmd: c.cmd, args: c.args, timeout: c.timeout } })),
  ...[
    ['qwen', 'Qwen Code', ['--yolo', '--output-format', 'stream-json'], ''],
    ['opencode', 'OpenCode (DeepSeek, GLM, MiniMax)', ['run', '--format', 'json', '--auto'], 'Use /connect to add a provider, then /models to choose it. Task execution only; choose another provider for triage and reports.'],
    ['kimi', 'Kimi Code (Moonshot AI)', ['--output-format', 'stream-json'], 'Use /login to connect Kimi or Moonshot. Windows requires Git Bash. Task execution only; choose another provider for triage and reports.'],
  ].map(([name,label,args,description]) => ({ name, label, description, installed: false, configured: false, installable: true, install: name, config: { cmd: name, args, timeout: 1500 } })),
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
const clickRow = async text => {
  // the smallest box on the rail that holds the words - the row itself, not the lane around it
  const find = t => { const hits = [...document.querySelectorAll('[data-tq-rail] *')].filter(e => e.textContent.includes(t) && e.getBoundingClientRect().height > 24);
    return hits.sort((a, b) => a.getBoundingClientRect().height - b.getBoundingClientRect().height)[0]; };
  await page.waitForFunction(`(${find})(${JSON.stringify(text)})`);
  const r = await page.evaluate(`(() => { const e = (${find})(${JSON.stringify(text)}).getBoundingClientRect(); return { x: e.x + e.width / 2, y: e.y + e.height / 2 }; })()`);
  await page.mouse.click(r.x, r.y); await delay(1500);
};
const shot = async name => {
  await page.mouse.move(1430, 990);
  await delay(400);
  const content = await page.evaluate(() => document.body.innerText);
  if (name !== 'failure') assert.doesNotMatch(content, /unsupported canonical All|Something in this view failed to draw/);
  await page.screenshot({ path: path.join(scratch, name + '.png') });
  await writeFile(path.join(scratch, name + '.txt'), content);
  console.log('Captured ' + name);
};
const captureTimeline = async () => {
  await click('timeline', 'div');
  await page.evaluate(rows => {
    document.querySelector('[data-tq-timeline-stage]').parentElement.style.gridTemplateColumns = '720px minmax(0,1fr)';
      const names = {email:'Email',teams:'Teams',github:'GitHub',whatsapp:'WhatsApp',assistant:'Assistant'};
      const labelClock = (clock, label, color) => {
        const time = clock.textContent;
        clock.dataset.readmeOriginal = clock.innerHTML;
        const source = document.createElement('span');
        source.textContent = label;
        Object.assign(source.style, {display:'block',fontFamily:'Segoe UI,sans-serif',fontSize:'11px',fontWeight:'700',color,letterSpacing:'-.2px'});
        const timestamp = document.createElement('span');
        timestamp.textContent = time;
        Object.assign(timestamp.style, {display:'block',fontSize:'10px',fontWeight:'400',color:'#827e73'});
        clock.replaceChildren(source, timestamp);
        Object.assign(clock.style, {paddingTop:'2px',paddingLeft:'0',paddingRight:'8px',lineHeight:'12px'});
      };
    for (const row of rows) {
      const node = document.querySelector(`[data-processing-item="readme-${row.MessageId}"]`);
      if (!node) continue;
      const label = row.Channel === 'report' ? (row.MessageId === 939 ? 'Daily digest' : 'SQL report') : names[row.Channel] || row.Channel;
      const clock = node.firstElementChild;
        labelClock(clock, label, row.Channel === 'report' ? '#89642d' : '#426579');
    }
    // Calendar rows precede the message rows and have no processing item id.
    for (const icon of document.querySelectorAll('[data-testid="EventIcon"]')) {
      const row = icon.closest('[data-tq-timeline-stage]') ? null : icon.parentElement.parentElement.parentElement;
      if (row?.firstElementChild && /^\d/.test(row.firstElementChild.textContent)) {
          labelClock(row.firstElementChild, 'Calendar', '#89642d');
      }
    }
  },timelineRows);
  await shot('timeline');
  await page.evaluate(() => {
    document.querySelectorAll('[data-readme-original]').forEach(e=>{e.innerHTML=e.dataset.readmeOriginal;e.removeAttribute('style');delete e.dataset.readmeOriginal;});
    document.querySelector('[data-tq-timeline-stage]').parentElement.style.gridTemplateColumns='';
  });
};
const captureLearned = async () => {
  await nav('Docs'); await click('LEARNED.md','p,span,div');
  await page.waitForFunction(()=>[...document.querySelectorAll('textarea')].some(e=>e.value.includes('# LEARNED.md')));
  await page.setViewport({width:1200,height:1160,deviceScaleFactor:2});
  await page.evaluate(()=>{
    const editor=[...document.querySelectorAll('textarea')].find(e=>e.value.includes('# LEARNED.md'));
    editor.style.fontSize='14px'; editor.style.lineHeight='1.55';
  });
  await shot('learned');
  await page.setViewport({width:1200,height:1000,deviceScaleFactor:2});
};
const captureCli = async () => {
  await nav('Connections');
  const search = await page.waitForSelector('input[placeholder^="Search connectors"]');
  await search.type('AI CLI agents'); await click('AI CLI agents', 'p');
  await page.waitForSelector('[data-connection="qwen"]');
  await shot('cli');
};
try {
  await page.goto(origin + '/?workflow=numbers', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => [...document.querySelectorAll('button')].find(e => e.textContent.trim() === 'Put it away')?.click());
  await delay(1000);
  if (process.argv.includes('--cli-only')) {
    await captureCli();
  } else if (process.argv.includes('--home-only')) {
    // section 1 alone: the opening card - what changed since last night, the day, and what waits (2026-10-08). The full demo, not
    // the guided one-request journey, whose banner and single row are not the day
    await page.goto(origin + '/?demo=explore', { waitUntil: 'networkidle0', timeout: 120000 });
    await click('Chat', 'button'); await delay(1500);
    // ...and a fresh chat: the full demo opens on a scripted conversation, and the opening card is what an empty one shows
    await page.waitForSelector('button[aria-label^="New chat"]'); await page.click('button[aria-label^="New chat"]'); await delay(2000);
    await page.waitForSelector('.tq-day-box'); await delay(800);
    await shot('home');
  } else if (process.argv.includes('--timeline-only')) {
    await captureTimeline();
  } else if (process.argv.includes('--memory-update')) {
    await captureTimeline(); await captureLearned();
  } else {
  // The walkthrough (01-06): Ruth's request through the Chat and Task views. The rail on the left is the Timeline;
  // the chat on the right is the assistant, and a task opens INSIDE it as a card.
  await click('Chat', 'button'); await delay(1500);
  await page.waitForSelector('[data-tick]');
  await shot('home');
  // Replay the meeting strip's entrance and clock pulse at fixed times for the morning GIF.
  await page.evaluate(() => {
    window.readmeAnimations = document.querySelector('[data-tick]').getAnimations({ subtree: true });
    window.readmeAnimations.forEach(a => a.pause());
  });
  for (let i = 0; i < 25; i++) {
    await page.evaluate(t => window.readmeAnimations.forEach(a => { a.currentTime = t; }), i * 80);
    await page.screenshot({ path: path.join(scratch, `morning-${String(i).padStart(2,'0')}.png`) });
  }
  await page.evaluate(() => window.readmeAnimations.forEach(a => a.play()));
  await click('Task', 'button'); await clickRow('Latest vendor spend');
  await page.waitForFunction(() => document.body.innerText.includes('talk it through with the assistant'));
  await shot('task');
  // a pinned task keeps the pane; the demo starts over on a reload, so the walk begins from the morning
  await page.goto(origin + '/?workflow=numbers', { waitUntil: 'networkidle0', timeout: 120000 });
  await click('Chat', 'button'); await delay(1500);
  await click('Walk me through my tasks');
  await page.waitForFunction(() => document.body.innerText.includes('Where this came from') && document.body.innerText.includes('TQ-0018'));
  // a shorter window keeps the card and the action row under it in one frame
  await page.setViewport({ width: 1200, height: 760, deviceScaleFactor: 2 }); await delay(800); await shot('assistant');
  await page.setViewport({ width: 1200, height: 1000, deviceScaleFactor: 2 });
  await click('Start an agent'); await delay(1000); await click('Send to agent');
  await page.waitForFunction(() => document.body.innerText.includes('August vendor spend is ready for review'), { timeout: 30000 });
  await delay(1500); await shot('agent');
  await click('Task', 'button'); await clickRow('Latest vendor spend');
  await page.waitForFunction(() => [...document.querySelectorAll('textarea')].some(e => e.value.includes('August vendor spend was')));
  await page.setViewport({ width: 1200, height: 1300, deviceScaleFactor: 2 }); await delay(800);
  await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Approve & send')?.scrollIntoView({ block: 'center' }));
  await shot('review');
  await page.setViewport({ width: 1200, height: 1000, deviceScaleFactor: 2 });
  if (process.argv.includes('--extras')) {
    await captureCli();
    await nav('Hub'); await delay(800); await click('2 comments'); await shot('hub');
    await nav('Board'); await click('Live handoffs', 'div'); await shot('handoffs');
    await captureLearned();
  }
  }
  assert.deepEqual(errors, []);
} catch (error) {
  await shot('failure');
  throw error;
} finally { await browser.close(); await server.close(); }
