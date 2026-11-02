import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE AGENT'S DRAFT IS SAID WHERE THE AGENT IS AND SENT FROM CLOSE OUT (the owner, 2026-11-02: "in agent we should just say 'agent drafted a
   message' and take you to the Close out screen"), and "if the agent makes a reply, bring out the reply (Close out) tab side by side". An
   agent no longer working gets Agent | Close out on its own, on the draft, once per draft - closed, it stays closed; a working one only a
   small notice in its terminal's corner, the terminal's size untouched, whose press pairs them. The draft is drawn in Close out alone. A
   general agent's notice stands at the foot of its chat; and a draft the owner already answered says so in Close out, its Send a second
   reply. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WORDS = "Hi - before I file it, could you confirm the purchase order number for invoice 88213?";
const PAIRED = (sel) => document.querySelector(`${sel} [data-tq-task-body]`)?.dataset.tqPair === "agent+close";

// the invoice task with a CLI agent live on it - waiting on you, or `working` mid-turn - open on the table; the decide answered as gone
async function cliTask(t, working) {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
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
  assert.equal((await api("/api/fixture/task/live-agent", { task_id: inv.TaskId, working })).status, 200, "a CLI agent live on it");
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const pageSel = `[data-tq-task-page="${inv.TaskId}"]`;
  await page.waitForSelector(`${pageSel} [data-tq-term-box] .xterm`, { timeout: 20000 });
  await sleep(800);
  const draft = async () => {
    const made = await (await api("/api/fixture/task/agent-draft", { task_id: inv.TaskId, text: WORDS, agent: "Claude Code" })).json();
    assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
    return made.reviewId;
  };
  const pair = () => page.evaluate((sel) => document.querySelector(`${sel} [data-tq-task-body]`)?.dataset.tqPair || "", pageSel);
  const draftShown = () => page.evaluate((sel, w) => [...document.querySelectorAll(`${sel} [data-tq-closeout] textarea`)].some((x) => x.offsetParent && x.value.includes(w)), pageSel, WORDS);
  return { page, errors, decided, pageSel, draft, pair, draftShown, note: `${pageSel} [data-tq-agent-notice=popup]` };
}

test("an agent waiting on you drafts a reply: Close out opens beside it on the draft; closed, it stays closed; its Send keeps the pair", { timeout: 300000 }, async (t) => {
  const { page, errors, decided, pageSel, draft, pair, draftShown, note } = await cliTask(t, false);
  const rid = await draft();
  await page.waitForFunction(PAIRED, { timeout: 20000 }, pageSel).catch(async () => assert.fail(`not side by side: "${await pair()}"`));
  await page.waitForFunction((sel, w) => [...document.querySelectorAll(`${sel} [data-tq-closeout] textarea`)].some((x) => x.offsetParent && x.value.includes(w)),
    { timeout: 10000 }, pageSel, WORDS);
  if (process.env.TASKUARY_SHOTS) { await sleep(600); await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-paired.png") }); }
  assert.ok(await page.$(`${pageSel} [data-tq-term-box] .xterm`), "the agent's terminal beside it");
  assert.equal(await page.$(note), null, "no notice: the draft is in plain sight beside it");
  // the owner closes the pair: it stays closed for this draft, and the notice is back
  await page.click(`${pageSel} [data-tq-pane-strip=agent] [data-tq-strip-pair]`);
  await page.waitForSelector(note, { timeout: 10000 });
  for (let i = 0; i < 8; i++) { await sleep(500); assert.equal(await pair(), "", `the closed pair came back (${i * 0.5 + 0.5}s)`); }
  // ...its press pairs them again, and Close out's Send sends it - the pair stays as it is
  await page.$eval(`${note} button`, (b) => b.click());
  await page.waitForFunction(PAIRED, { timeout: 10000 }, pageSel);
  await sleep(400);
  assert.ok(await draftShown());
  await page.evaluate((sel) => {
    const b = [...document.querySelectorAll(`${sel} [data-tq-closeout] button`)].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    b.click();
  }, pageSel);
  for (let i = 0; i < 20 && !decided.length; i++) await sleep(250);
  assert.equal(decided.length, 1, "one send");
  assert.equal(decided[0].rid, rid);
  assert.ok(String(decided[0].body.final_text).includes(WORDS));
  await page.waitForFunction((sel) => !document.querySelector(`${sel} [data-tq-closeout] [data-tq-draft-box]`), { timeout: 10000 }, pageSel);
  for (let i = 0; i < 4; i++) { await sleep(500); assert.equal(await pair(), "agent+close", "the pair stays as the owner left it after the send"); }
  assert.equal(await page.$(`${pageSel} [data-tq-agent-notice]`), null);
  assert.deepEqual(errors, []);
});

test("an agent still working drafts a reply: only a notice over its terminal, never a second draft; its press opens Close out beside it", { timeout: 300000 }, async (t) => {
  const { page, errors, pageSel, draft, pair, draftShown, note } = await cliTask(t, true);
  const rects = () => page.evaluate((sel) => {
    const box = document.querySelector(`${sel} [data-tq-term-box]`), n = box.querySelector("[data-tq-agent-notice]");
    const r = (el) => { const b = el?.getBoundingClientRect(); return b ? { x: b.x, y: b.y, w: b.width, h: b.height } : null; };
    return { box: r(box), term: r(box.querySelector(".xterm")), note: r(n) };
  }, pageSel);
  const before = await rects();
  await draft();
  await page.waitForSelector(note, { timeout: 20000 });
  await sleep(1500);
  const after = await rects();
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-notice.png") });
  assert.equal(await pair(), "", "a working terminal is never squeezed on its own");
  assert.deepEqual({ box: after.box, term: after.term }, { box: before.box, term: before.term }, "the terminal kept its size under the notice");
  assert.ok(after.note.w <= 470 && after.note.h < 70 && after.note.x + after.note.w <= after.box.x + after.box.w + 1 && after.note.y >= after.box.y,
    `a small notice in the terminal's corner: ${JSON.stringify(after)}`);
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
  await page.$eval(`${note} button`, (b) => b.click());
  await page.waitForFunction(PAIRED, { timeout: 10000 }, pageSel).catch(async () => assert.fail(`the press did not pair them: "${await pair()}"`));
  await sleep(500);
  assert.ok(await draftShown(), "Close out beside the agent, on the draft");
  assert.ok(await page.$(`${pageSel} [data-tq-term-box] .xterm`), "the terminal still there beside it");
  assert.deepEqual(errors, []);
});

test("a general agent's draft opens Close out beside its chat, saying the owner already answered; closed, its notice is at the chat's foot", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
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
  const pageSel = `[data-tq-task-page="${taskId}"]`, note = `${pageSel} .tq-aui-viewport [data-tq-agent-notice=chat]`, co = `${pageSel} [data-tq-closeout]`;
  await page.waitForFunction(PAIRED, { timeout: 20000 }, pageSel).catch(async () =>
    assert.fail(`not side by side: "${await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-task-body]`)?.dataset.tqPair || "", pageSel)}"`));
  await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} [data-tq-already-answered]`)].some((e) => e.offsetParent), { timeout: 10000 }, co).catch(async () => {
    assert.fail(`no already-answered line in Close out: ${await page.$eval(co, (e) => e.innerText).catch(() => "no Close out")}`);
  });
  if (process.env.TASKUARY_SHOTS) { await sleep(800); await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-answered.png") }); }
  const card = await page.$eval(co, (el) => el.innerText);
  assert.match(card, /You already answered Gail Moreno at [^:]+:\d\d[^:]*: "Hi Gail, it covers the third quarter/);
  assert.match(card, /as a second reply/, `Send's line says it: ${card}`);
  // the owner closes the pair: the notice stands at the foot of the conversation, where its questions are asked
  await page.click(`${pageSel} [data-tq-pane-strip=agent] [data-tq-strip-pair]`);
  await page.waitForSelector(note, { visible: true, timeout: 10000 });
  const got = await page.$eval(note, (el) => ({ text: el.innerText, boxes: el.querySelectorAll("textarea").length, last: el.parentElement.lastElementChild === el }));
  assert.match(got.text, /assistant drafted a message to Gail Moreno/);
  assert.equal(got.boxes, 0, "no draft in the chat");
  assert.ok(got.last, "at the foot of the conversation");
  assert.equal(await page.$(`${pageSel} [data-tq-agent-notice=popup]`), null, "no corner notice over a chat");
  assert.deepEqual(errors, []);
});
