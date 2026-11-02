import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE AGENT'S DRAFT IS APPROVED WHERE THE AGENT IS (the owner, 2026-11-02: "when we ask the agent to ask the sender, we should have the
   approve right there instead of having to go to the Close out tab ... for a CLI agent it should be a POP-UP. A general agent should show it
   where we ask questions, in the bottom space"). A CLI agent saves a message for the sender with `taskuary --reply`: a pop-up over its
   terminal's corner, the terminal's size untouched; Later hides it, opening the task again brings it back; its Send is Close out's Send and
   clears Close out too. A general agent's draft is a card at the foot of its chat. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WORDS = "Hi - before I file it, could you confirm the purchase order number for invoice 88213?";

test("a CLI agent's draft pops up over its terminal without resizing it; Later hides it; Send sends it and clears Close out", { timeout: 300000 }, async (t) => {
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
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title)), other = tasks.find((x) => x.TaskId !== inv?.TaskId && x.Status === "open");
  assert.ok(inv && other, "the demo's invoice task, and another to look at");
  assert.equal((await api("/api/fixture/task/live-agent", { task_id: inv.TaskId })).status, 200, "a CLI agent live on it");
  const made = await (await api("/api/fixture/task/agent-draft", { task_id: inv.TaskId, text: WORDS, agent: "Claude Code" })).json();
  assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const pageSel = `[data-tq-task-page="${inv.TaskId}"]`, pop = `${pageSel} [data-tq-agent-popup]`;
  await page.waitForSelector(`${pageSel} [data-tq-term-box] .xterm`, { timeout: 20000 });
  await page.waitForSelector(pop, { timeout: 20000 });
  await sleep(600);
  const rects = () => page.evaluate((sel) => {
    const box = document.querySelector(`${sel} [data-tq-term-box]`), term = box.querySelector(".xterm"), p = box.querySelector("[data-tq-agent-popup]");
    const r = (el) => { const b = el?.getBoundingClientRect(); return b ? { x: b.x, y: b.y, w: b.width, h: b.height } : null; };
    return { box: r(box), term: r(term), pop: r(p), cols: term.querySelector(".xterm-rows")?.children.length || 0 };
  }, pageSel);
  const withPop = await rects();
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-popup.png") });
  // ...a small card over the terminal's corner, inside its box - not a modal over the page
  assert.ok(withPop.pop.w <= 410 && withPop.pop.x + withPop.pop.w <= withPop.box.x + withPop.box.w + 1 && withPop.pop.y >= withPop.box.y - 1,
    `the pop-up lies over the terminal's corner: ${JSON.stringify(withPop)}`);
  assert.ok(withPop.pop.w < withPop.box.w * 0.75, `it leaves the terminal most of its width: ${JSON.stringify(withPop)}`);
  const said = await page.$eval(pop, (el) => ({ text: el.innerText, draft: el.querySelector("textarea[data-tq-draft], textarea")?.value || "" }));
  assert.match(said.text, /Claude Code drafted a message/);
  assert.match(said.text, /\bTo\b/, `who it goes to: ${said.text}`);
  assert.ok(said.draft.includes(WORDS), `the draft, editable: ${said.draft}`);
  assert.match(said.text, /stays open while the agent is working/, `Close out's own line under its Send: ${said.text}`);
  // ...the Assistant is told of it by name: its Send an outward send, its box told apart from Close out's
  const view = await page.evaluate(async () => (await import("/src/pageView.js")).context());
  assert.ok(view.buttons.some((b) => b.label === "Send in the pop-up" && b.send), `the pop-up's Send, named: ${JSON.stringify(view.buttons.map((b) => b.label))}`);
  assert.ok(view.fields.some((f) => f.label === "Reply draft in the pop-up" && f.value.includes(WORDS)), `its box: ${JSON.stringify(view.fields.map((f) => f.label))}`);

  // Later: the pop-up goes, the terminal is the size it was - the pop-up never took any of it
  await page.$eval(`${pop} [data-tq-agent-later]`, (b) => b.click());
  await page.waitForFunction((sel) => !document.querySelector(sel), { timeout: 5000 }, pop);
  await sleep(400);
  const without = await rects();
  assert.deepEqual({ box: without.box, term: without.term }, { box: withPop.box, term: withPop.term }, "the terminal kept its size under the pop-up");
  // ...and the draft is still in Close out
  const close = await (await api(`/api/tasks/${inv.TaskId}`)).json();
  assert.equal(close.reviews.find((r) => r.ReviewId === made.reviewId)?.Status, "pending", "Later sends nothing");

  // opening the task again brings it back
  await page.evaluate((id) => { location.hash = `task=${id}`; }, other.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${other.TaskId}"]`, { timeout: 20000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(pop, { timeout: 20000 });

  // an edit in the pop-up is what goes; its Send runs Close out's decide for that review
  await page.click(`${pop} textarea`);
  await page.keyboard.press("End");
  await page.keyboard.type(" Thanks, Alex");
  await page.evaluate((sel) => {
    const b = [...document.querySelectorAll(`${sel} [data-tq-moves] button`)].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled);
    b.click();
  }, pop);
  for (let i = 0; i < 20 && !decided.length; i++) await sleep(250);
  assert.equal(decided.length, 1, "one send");
  assert.equal(decided[0].rid, made.reviewId);
  assert.equal(decided[0].body.verb, "approve");
  assert.ok(String(decided[0].body.final_text).includes("Thanks, Alex"), `the edited words went: ${decided[0].body.final_text}`);
  assert.equal(decided[0].recorded, 200);
  // ...and it clears both places: the pop-up, and Close out's pending draft
  await page.waitForFunction((sel) => !document.querySelector(sel), { timeout: 10000 }, pop);
  if (await page.$(`${pageSel} [data-tq-section-tab=close]`)) await page.$eval(`${pageSel} [data-tq-section-tab=close]`, (b) => b.click());
  await page.waitForFunction((sel) => {
    const co = document.querySelector(`${sel} [data-tq-closeout]`);
    return !!co && ![...co.querySelectorAll("button")].some((b) => /^Send\b/.test(b.textContent.trim()) && b.offsetParent);
  }, { timeout: 10000 }, pageSel).catch(async () => assert.fail(`Close out still offers Send: ${await page.$eval(`${pageSel} [data-tq-closeout]`, (e) => e.innerText)}`));
  assert.deepEqual(errors, []);
});

test("a general agent's draft is a card at the foot of its conversation, with Close out's Send", { timeout: 300000 }, async (t) => {
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
  const made = await (await api("/api/fixture/task/agent-draft", { task_id: taskId, text: "Hi Gail - which quarter should the review cover?", agent: "assistant" })).json();
  assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, taskId);
  const card = `[data-tq-task-page="${taskId}"] .tq-aui-viewport [data-tq-agent-card]`;
  await page.waitForSelector(card, { visible: true, timeout: 20000 });
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "agent-draft-card.png") });
  const got = await page.$eval(card, (el) => ({ text: el.innerText, draft: el.querySelector("textarea")?.value || "",
    last: el.parentElement.lastElementChild === el, send: [...el.querySelectorAll("[data-tq-moves] button")].some((b) => /^Send\b/.test(b.textContent.trim())) }));
  assert.match(got.text, /drafted a message/);
  assert.ok(got.draft.includes("which quarter"), got.draft);
  assert.ok(got.send, `its Send: ${got.text}`);
  assert.ok(got.last, "at the foot of the conversation, where its questions are asked");
  assert.equal(await page.$(`[data-tq-task-page="${taskId}"] [data-tq-agent-popup]`), null, "no pop-up over a chat");
  assert.deepEqual(errors, []);
});
