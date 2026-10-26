import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE QUESTION IS ON THE AGENT'S CANVAS, WITH ITS ANSWER BOX (owner-approved, the UI audit's W6, 2026-10-21). The card said
   "Agent asked you something" over a pane that never showed what - the question lived only in the rail row's hover. Now the
   question and the answers it named are drawn in the Agent work pane with a box under them; an answer that cannot be delivered
   says why and keeps the words, and one that is delivered takes the card away.

   The fixture is the raised hand of an agent asking from a terminal on the task: /assistant answers with `asking` and no
   conversation session, exactly as the server does, so the answer goes by the worker's answer road. */
test("the agent's question is drawn in its canvas with an answer box, and answering it clears it", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Clock in to the portal", Summary: "Sign in and read the message", Kind: "general", Tags: "ask:assistant needs:browser" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  const answers = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const at = new URL(req.url()).pathname;
    if (at === `/api/tasks/${made.taskId}/assistant`) {
      return void req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({
        messages: [{ id: "m1", role: "assistant", content: [{ type: "text", text: "The login page is open. Have you signed in successfully?" }] }],
        asking: { request_id: "r1", kind: "input_needed", text: "Have you signed in successfully?", choices: ["Signed in", "Login failed"], sid: "p1" },
        session: null, starting: false, providers: [{ id: 1, label: "Test CLI", model: "" }] }) });
    }
    if (at === `/api/tasks/${made.taskId}/worker/answer` && req.method() === "POST") {
      answers.push(JSON.parse(req.postData() || "{}"));
      // the first answer finds nobody listening - the card says so and keeps the words; the second is delivered
      return void req.respond(answers.length === 1
        ? { status: 422, contentType: "application/json", body: JSON.stringify({ detail: "disconnected: no live worker on this task" }) }
        : { status: 200, contentType: "application/json", body: JSON.stringify({ delivered: true, state: "delivered", sid: "p1" }) });
    }
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector('[data-tq-asking="r1"]', { visible: true, timeout: 20000 });  const card = await page.$eval('[data-tq-asking="r1"]', (el) => ({ text: el.innerText,
    choices: [...el.querySelectorAll("button")].map((b) => b.textContent.trim()), box: !!el.querySelector("input") }));
  assert.match(card.text, /Have you signed in successfully\?/, "the question itself is on the canvas");
  assert.deepEqual(card.choices.filter((c) => ["Signed in", "Login failed"].includes(c)), ["Signed in", "Login failed"]);
  assert.ok(card.box, "an answer box under the question");

  // the failure: typed, sent, refused - the reason is said and the words stay
  await page.type('[data-tq-asking="r1"] input', "Signed in on the second try");
  await page.click('[data-tq-asking="r1"] button[type="submit"]');
  await page.waitForFunction(() => document.querySelector('[data-tq-asking="r1"] [role="alert"]')?.innerText.includes("no live worker"), { timeout: 10000 });
  assert.equal(await page.$eval('[data-tq-asking="r1"] input', (i) => i.value), "Signed in on the second try");

  // ...and a press on one of its answers is delivered, and the card goes
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-asking="r1"] button')].find((b) => b.textContent.trim() === "Signed in").click());
  await page.waitForFunction(() => !document.querySelector('[data-tq-asking="r1"]'), { timeout: 10000 });
  assert.deepEqual(answers, [{ request_id: "r1", text: "Signed in on the second try" }, { request_id: "r1", text: "Signed in" }]);
  assert.deepEqual(errors, []);
});

/* A LONG ANSWER THAT ENDS IN A QUESTION, OPENED IN A SHORT WINDOW. Pinned to the bottom, the question card and the input
   took the room and the owner read the answer's last paragraph only (2026-10-18: "I can't see any of the agent
   output without scrolling"). Opened, the answer reads from its first line. */
test("a long answer opens at its first line", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 700 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Build the ledger export", Summary: "Pull a year of the ledger for the listed sites", Kind: "general", Tags: "ask:assistant" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  const para = (i) => `Paragraph ${i}: the export runs a site at a time, so each one is checked against the month's totals before it is added.`;
  const answer = ["FIRST LINE of the answer.", ...Array.from({ length: 14 }, (_, i) => para(i + 1)), "Which format should the file be?"].join("\n\n");
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    if (new URL(req.url()).pathname === `/api/tasks/${made.taskId}/assistant`) {
      return void req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({
        messages: [{ id: "u1", role: "user", content: [{ type: "text", text: "Pull the ledger." }] },
          { id: "m1", role: "assistant", content: [{ type: "text", text: answer }] }],
        asking: { request_id: "r1", kind: "input_needed", text: "Which format?", choices: ["One workbook", "Single CSV"] },
        session: null, starting: false, providers: [{ id: 1, label: "Test CLI", model: "" }] }) });
    }
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-agent", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 1200));

  // ...in whatever scrolls it: a finished agent's chat is no scroller of its own since the work column became the one scroller
  // (TaskPage data-tq-agent-room "rest", 2026-10-26) - so the pane is the nearest box that scrolls, and the answer must open at
  // its first line there, never at its last
  const seen = await page.evaluate(() => {
    const m = [...document.querySelectorAll(".tq-aui-agent")].pop();
    let v = m.parentElement;
    while (v && !(/auto|scroll/.test(getComputedStyle(v).overflowY) && v.scrollHeight > v.clientHeight + 1)) v = v.parentElement;
    if (!v) return { overflow: false, tall: Math.round(m.getBoundingClientRect().height) };
    const vr = v.getBoundingClientRect(), mr = m.getBoundingClientRect();
    return { scroller: v.className || [...v.attributes].map((a) => a.name).join(" "), scrolled: v.scrollTop, overflow: true,
      longer: mr.height > vr.height, top: Math.round(mr.top - vr.top), room: Math.round(vr.height) };
  });
  assert.ok(seen.overflow && seen.longer, `the answer must be longer than the pane for this to test anything: ${JSON.stringify(seen)}`);
  assert.ok(seen.top >= 0 && seen.top < seen.room - 40, `the answer's first line must open in view at the top of the pane: ${JSON.stringify(seen)}`);
  assert.deepEqual(errors, []);
});
