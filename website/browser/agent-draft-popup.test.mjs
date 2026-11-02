import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE AGENT'S DRAFT IS SAID WHERE THE AGENT IS AND SENT FROM CLOSE OUT (the owner, 2026-11-02: "in agent we should just say 'agent drafted a
   message' and take you to the Close out screen"). A CLI agent saves a message for the sender with `taskuary --reply`: a small notice in its
   terminal's corner, the terminal's size untouched, and no draft or Send in the agent's pane - its one press opens Close out at the draft,
   whose Send sends it and takes the notice away. A general agent's notice stands at the foot of its chat; and a draft the owner already
   answered says so in Close out, its Send a second reply. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WORDS = "Hi - before I file it, could you confirm the purchase order number for invoice 88213?";

test("a CLI agent's draft is a notice over its terminal, never a second draft; its press opens Close out, whose Send clears it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  // the demo sends nothing: the decide is answered as gone and recorded as sent (send-live-agent-stays' road)
  const decided = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      decided.push({ rid: Number(rid), body: JSON.parse(req.postData() || "{}"), recorded: (await api(`/api/fixture/review/${rid}/sent`, {})).status });
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  const tasks = (await (await api("/api/tasks")).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice task");
  assert.equal((await api("/api/fixture/task/live-agent", { task_id: inv.TaskId })).status, 200, "a CLI agent live on it");
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const pageSel = `[data-tq-task-page="${inv.TaskId}"]`, note = `${pageSel} [data-tq-agent-notice=popup]`;
  await page.waitForSelector(`${pageSel} [data-tq-term-box] .xterm`, { timeout: 20000 });
  await sleep(800);
  const rects = () => page.evaluate((sel) => {
    const box = document.querySelector(`${sel} [data-tq-term-box]`), n = box.querySelector("[data-tq-agent-notice]");
    const r = (el) => { const b = el?.getBoundingClientRect(); return b ? { x: b.x, y: b.y, w: b.width, h: b.height } : null; };
    return { box: r(box), term: r(box.querySelector(".xterm")), note: r(n) };
  }, pageSel);
  const before = await rects();
  // ...the agent saves its message mid-session: the notice comes up on its own
  const made = await (await api("/api/fixture/task/agent-draft", { task_id: inv.TaskId, text: WORDS, agent: "Claude Code" })).json();
  assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
  await page.waitForSelector(note, { timeout: 20000 });
  await sleep(500);
  const after = await rects();
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-notice.png") });
  assert.deepEqual({ box: after.box, term: after.term }, { box: before.box, term: before.term }, "the terminal kept its size under the notice");
  assert.ok(after.note.w <= 470 && after.note.h < 70 && after.note.x + after.note.w <= after.box.x + after.box.w + 1 && after.note.y >= after.box.y,
    `a small notice in the terminal's corner: ${JSON.stringify(after)}`);
  // NEVER BOTH: the agent's pane says it, and holds no draft and no Send - the draft is Close out's alone
  const said = await page.$eval(note, (el) => ({ text: el.innerText, boxes: el.querySelectorAll("textarea").length,
    buttons: [...el.querySelectorAll("button")].map((b) => b.textContent.trim()) }));
  assert.match(said.text, /Claude Code drafted a message to Tom Alvarez/);
  assert.equal(said.boxes, 0, "no draft box in the agent's pane");
  assert.deepEqual(said.buttons, ["Open in Close out"]);
  const outside = await page.evaluate((sel, w) => [...document.querySelectorAll(`${sel} textarea`)].filter((x) => x.value.includes(w) && !x.closest("[data-tq-closeout]")).length, pageSel, WORDS);
  assert.equal(outside, 0, "the draft is drawn nowhere but Close out");
  // ...and the Assistant reads its press as a door, never an outward send
  const view = await page.evaluate(async () => (await import("/src/pageView.js")).context());
  const door = view.buttons.find((b) => b.label === "Open in Close out");
  assert.ok(door && !door.send, `the notice's press, not a send: ${JSON.stringify(view.buttons.map((b) => [b.label, !!b.send]))}`);

  // its press opens Close out on the draft, and that Send sends it
  await page.$eval(`${note} button`, (b) => b.click());
  await page.waitForFunction((sel, w) => [...document.querySelectorAll(`${sel} [data-tq-closeout] textarea`)].some((x) => x.offsetParent && x.value.includes(w)),
    { timeout: 10000 }, pageSel, WORDS).catch(async () => assert.fail(`Close out did not open on the draft: ${await page.evaluate(() => document.body.innerText.slice(0, 1500))}`));
  await page.evaluate((sel) => {
    const b = [...document.querySelectorAll(`${sel} [data-tq-closeout] button`)].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    b.click();
  }, pageSel);
  for (let i = 0; i < 20 && !decided.length; i++) await sleep(250);
  assert.equal(decided.length, 1, "one send");
  assert.equal(decided[0].rid, made.reviewId);
  assert.ok(String(decided[0].body.final_text).includes(WORDS));
  // ...and the notice is gone with it
  await page.waitForFunction((sel) => !document.querySelector(sel), { timeout: 10000 }, `${pageSel} [data-tq-agent-notice]`);
  assert.deepEqual(errors, []);
});

test("a general agent's draft is a notice at the foot of its chat; one the owner already answered says so in Close out", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1400, height: 1000, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  const { taskId } = await (await api("/api/fixture/general/canvas", {})).json();
  assert.ok(taskId);
  const made = await (await api("/api/fixture/task/agent-draft", { task_id: taskId, text: "Hi Gail - which quarter should the review cover?", agent: "assistant",
    answered: "Hi Gail, it covers the third quarter - the sign-off is all that is left." })).json();
  assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, taskId);
  const pageSel = `[data-tq-task-page="${taskId}"]`, note = `${pageSel} .tq-aui-viewport [data-tq-agent-notice=chat]`;
  await page.waitForSelector(note, { visible: true, timeout: 20000 });
  const got = await page.$eval(note, (el) => ({ text: el.innerText, boxes: el.querySelectorAll("textarea").length, last: el.parentElement.lastElementChild === el }));
  assert.match(got.text, /assistant drafted a message to Gail Moreno/);
  assert.equal(got.boxes, 0, "no draft in the chat");
  assert.ok(got.last, "at the foot of the conversation, where its questions are asked");
  assert.equal(await page.$(`${pageSel} [data-tq-agent-notice=popup]`), null, "no corner notice over a chat");
  await page.$eval(`${note} button`, (b) => b.click());
  const co = `${pageSel} [data-tq-closeout]`;
  await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} [data-tq-already-answered]`)].some((e) => e.offsetParent), { timeout: 10000 }, co).catch(async () => {
    assert.fail(`no already-answered line in Close out: ${await page.$eval(co, (e) => e.innerText).catch(() => "no Close out")}`);
  });
  if (process.env.TASKUARY_SHOTS) { await sleep(800); await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-answered.png") }); }
  const card = await page.$eval(co, (el) => el.innerText);
  assert.match(card, /You already answered Gail Moreno at [^:]+:\d\d[^:]*: "Hi Gail, it covers the third quarter/);
  assert.match(card, /as a second reply/, `Send's line says it: ${card}`);
  assert.deepEqual(errors, []);
});
