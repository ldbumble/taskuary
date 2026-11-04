import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* CLOSE OUT FOLDS INTO THE AGENT'S CHAT (the closeout-in-chat spec, 2026-11-04, Task 4.2). On a non-coding task the agent's newest summary
   draws every draft as its own card - its Send, Send and close, Redraft - with the On you steps and the emails owed, and Close out is no
   section at all: Came from | Agent. One copy of each draft, wherever it is drawn. A reply no agent ran shows triage's reading, the drafter's
   why as "What I did" and the card, and its box starts the agent with the owner's words. Mark done lights on the Agent's strip once the
   Advisor, reading the agent's summary (advisor.summary_line), finds nothing left - never before, while an On you step is open. A coding
   task keeps its three sections. Ray Colton, Gail Moreno and Alex Doyle are invented (fixture closeout-in-chat). */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ON_YOU = "Sign the renewal in your e-signature tool once Ray sends it.";

const world = async (h, body) => {
  const r = await fetch(`${h.fixtureApi}/api/fixture/task/closeout-in-chat`, { method: "POST", body: JSON.stringify(body),
    headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
  const out = await r.json();
  assert.ok(out.taskId, JSON.stringify(out));
  return out;
};
// the agent's conversation, served at each read: one finished turn whose summary names the On you step
const summaryTurn = (onYou) => ({ id: "a1", role: "assistant", createdAt: new Date().toISOString(), content: [{ type: "text", text: "Both replies are drafted." }],
  summary: { about: "Ray Colton wants the 24-month renewal confirmed; Gail Moreno wants to be kept posted.",
    did: "Checked the contract dates and drafted a reply to each of them.", on_you: onYou ? [ON_YOU] : [], nothing_left: false } });

const open = async (h, made, { sends = [], dispatched = [], advice = () => ({}) } = {}) => {
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const post = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", body: JSON.stringify(body), headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const p = new URL(req.url()).pathname, json = (body) => req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant` && made.turn)
      return void json({ messages: [{ id: "u1", role: "user", content: [{ type: "text", text: "Answer Ray and keep Gail posted." }] }, made.turn],
        session: null, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] });
    // ...and the Advisor's word is the test's: the demo's canned one lights whatever it likes
    if (req.method() === "GET" && p === "/api/advice") return void json(advice());
    // the demo sends nothing: a Send is answered as gone and recorded as sent, as a real one leaves it
    const rid = (p.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) { await post(`/api/fixture/review/${rid}/sent`, {}); sends.push(Number(rid));
      return void json({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }); }
    if (req.method() === "POST" && p === `/api/tasks/${made.taskId}/dispatch`) { dispatched.push(JSON.parse(req.postData() || "{}"));
      return void json({ state: "started", session: null }); }
    page.fixtureRequestGuard(req);
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page="${made.taskId}"]`;
  await page.waitForSelector(`${sel} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
  return { page, errors, sel };
};
const look = (page, sel) => page.evaluate((sel) => {
  const q = (s) => [...document.querySelectorAll(`${sel} ${s}`)];
  return { slots: q("[data-tq-slot]").map((s) => s.dataset.tqSlot), inSummary: q("[data-tq-summary=open] [data-tq-review]").map((e) => Number(e.dataset.tqReview)),
    reviews: q("[data-tq-review]").map((e) => Number(e.dataset.tqReview)), boxes: q("[data-tq-draft-box] textarea").map((e) => e.value),
    onYou: q("[data-tq-summary=open] [data-tq-on-you]").map((e) => e.innerText), closeSlot: !!document.querySelector(`${sel} [data-tq-slot=close]`) };
}, sel);

test("each draft is sent from inside the chat", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const made = await world(h, { kind: "general", drafts: 2, on_you: true });
  made.turn = summaryTurn(true);
  const sends = [], { page, errors, sel } = await open(h, made, { sends });
  await page.waitForFunction((sel) => document.querySelectorAll(`${sel} [data-tq-summary=open] [data-tq-review]`).length === 2, { timeout: 20000 }, sel);
  const m = await look(page, sel);
  assert.deepEqual(m.slots, ["from", "agent"], "Came from | Agent: no Close out on a chat task");
  assert.equal(m.closeSlot, false);
  assert.deepEqual(m.inSummary.sort(), [...made.reviews].sort(), "both drafts are cards inside the summary");
  assert.ok(m.onYou.some((x) => x.includes(ON_YOU)), `the On you step under them: ${JSON.stringify(m.onYou)}`);
  // ...the reply's card is Close out's own - Send and close, and Send beside it; the other answers its own person under "Answering", with its Send
  const main = await page.$$eval(`${sel} [data-tq-summary=open] [data-tq-review]:has([data-tq-send=close])`, (es) => es.map((e) => Number(e.dataset.tqReview)));
  assert.equal(main.length, 1, `one card carries Send and close: ${main}`);
  const other = made.reviews.find((r) => r !== main[0]);
  assert.match(await page.$eval(`${sel} [data-tq-summary=open] [data-tq-review="${other}"]`, (e) => e.innerText), /^Answering /);
  await page.click(`${sel} [data-tq-summary=open] [data-tq-review="${main[0]}"] [data-tq-send=open]`);
  for (let i = 0; i < 20 && !sends.length; i++) await sleep(250);
  assert.deepEqual(sends, [main[0]], "Send sent that draft and no other");
  await page.waitForFunction((sel) => document.querySelectorAll(`${sel} [data-tq-summary=open] [data-tq-review]`).length === 1, { timeout: 20000 }, sel);
  const after = await look(page, sel);
  assert.deepEqual(after.inSummary, [other], "the other draft is still waiting, in the chat");
  assert.equal(after.closeSlot, false);
  assert.deepEqual(errors, []);
});

test("one copy of each draft", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const made = await world(h, { kind: "general", drafts: 2, on_you: false });
  made.turn = summaryTurn(false);
  const { page, errors, sel } = await open(h, made);
  await page.waitForFunction((sel) => document.querySelectorAll(`${sel} [data-tq-summary=open] [data-tq-review]`).length === 2, { timeout: 20000 }, sel);
  await sleep(1000);
  const m = await look(page, sel);
  for (const rid of made.reviews) assert.equal(m.reviews.filter((x) => x === rid).length, 1, `draft ${rid} drawn once: ${JSON.stringify(m.reviews)}`);
  assert.equal(m.boxes.filter((v) => /^Hi Ray/.test(v)).length, 1, `Ray's draft in one box: ${JSON.stringify(m.boxes)}`);
  assert.equal(m.boxes.filter((v) => /^Hi Gail/.test(v)).length, 1, `Gail's draft in one box: ${JSON.stringify(m.boxes)}`);
  // ...and no notice pointing at a Close out that is not there
  assert.equal(await page.$(`${sel} [data-tq-agent-notice]`), null);
  assert.deepEqual(errors, []);
});

test("Mark done lights when the On you step is ticked and the Advisor finds nothing left", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  // ...the reply already went (sent from its card): what is left is the owner's own step
  const made = await world(h, { kind: "general", drafts: 1, on_you: true });
  await fetch(`${h.fixtureApi}/api/fixture/review/${made.reviews[0]}/sent`, { method: "POST", body: "{}", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
  made.turn = summaryTurn(true);
  // the Advisor is told the summary (advisor.summary_line, pinned in tests/test_turn_summary.py): "on you - …" lights nothing, "nothing left" Mark done
  let ticked = false;
  const { page, errors, sel } = await open(h, made, { advice: () => (ticked ? { verb: "done", line: "Nothing is left on this one." } : {}) });
  const done = `${sel} [data-tq-pane-strip=agent] [data-tq-verb=done]`;
  await page.waitForSelector(done, { timeout: 20000 });
  await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} [data-tq-summary=open] [data-tq-on-you]`)].length === 1, { timeout: 20000 }, sel);
  assert.ok(!(await page.$eval(done, (b) => b.classList.contains("p"))), "an On you step still open: Mark done is not lit");
  ticked = true;
  const r = await fetch(`${h.fixtureApi}/api/fixture/task/on-you-tick`, { method: "POST", body: JSON.stringify({ task_id: made.taskId, item: made.onYou[0] }),
    headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
  assert.equal(r.status, 200);
  await page.waitForFunction((done) => document.querySelector(done)?.classList.contains("p"), { timeout: 20000 }, done);
  assert.equal((await page.$$(`${sel} [data-tq-summary=open] [data-tq-on-you]`)).length, 0, "the ticked step is no longer on you");
  assert.equal(String((await (await fetch(`${h.fixtureApi}/api/tasks/${made.taskId}`, { headers: { "X-Taskuary-Token": h.token } })).json()).task.Status), "open",
    "lit, never pressed");
  assert.deepEqual(errors, []);
});

test("a reply with no agent shows the reading, why and the draft", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const made = await world(h, { kind: "reply", drafts: 1, on_you: false });
  const dispatched = [], { page, errors, sel } = await open(h, made, { dispatched });
  const chat = `${sel} [data-tq-no-agent-chat]`;
  await page.waitForSelector(`${chat} [data-tq-review="${made.reviews[0]}"]`, { timeout: 20000 });
  const m = await page.evaluate((chat) => { const el = document.querySelector(chat);
    return { reading: !!el.querySelector("[data-tq-reading]"), text: el.innerText, why: el.querySelector("[data-tq-draft-why]")?.innerText || "" }; }, chat);
  assert.ok(m.reading, "triage's reading first");
  assert.match(m.text, /Ray Colton wants the renewal term confirmed/);
  assert.match(m.text, /What I did/);
  assert.match(m.why, /I read his question and the contract dates/, "the drafter's why is What I did");
  const s = await look(page, sel);
  assert.deepEqual(s.slots, ["from", "agent"]);
  assert.equal(s.reviews.filter((x) => x === made.reviews[0]).length, 1, "one card");
  // ...and its box starts the agent with the owner's own words, through Send to agent's road
  await page.type(`${chat} textarea[data-tq-no-agent-box]`, "Cc Gail on it too");
  await page.click(`${chat} [data-tq-no-agent-send]`);
  for (let i = 0; i < 20 && !dispatched.length; i++) await sleep(250);
  assert.deepEqual(dispatched.map((d) => [d.kind, d.instruction]), [["general", "Cc Gail on it too"]]);
  assert.deepEqual(errors, []);
});

test("a coding task is unchanged", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const made = await world(h, { kind: "coding", drafts: 1, on_you: false });
  const { page, errors, sel } = await open(h, made);
  await page.waitForSelector(`${sel} [data-tq-slot=close]`, { timeout: 20000 });
  const m = await look(page, sel);
  assert.deepEqual(m.slots, ["from", "agent", "close"], "a coding task keeps Close out");
  assert.deepEqual(m.inSummary, [], "no card in a summary");
  assert.equal(await page.$(`${sel} [data-tq-no-agent-chat]`), null);
  // ...its draft is Close out's, once
  assert.ok(await page.$(`${sel} [data-tq-slot=close] [data-tq-closeout]`) || await page.$(`${sel} [data-tq-closeout]`));
  assert.deepEqual(errors, []);
});
