import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE HAND IT RAISED, WHERE THE OWNER IS STANDING. An agent that cannot go on says so with a marker
   and Taskuary records the question and the answers it offered (selfclose.ASK_LINE, PW-225). Both
   were recorded and neither was ever shown: the workspace got the prose ("tell me when you're
   signed in"), the chip said "needs you", and the two choices the agent named were not clickable
   anywhere in the app (2026-09-15, driving a real sign-in through the browser pane).

   The fixture is the raised hand: /assistant answers with `asking`, exactly as the server now does. */
test("the agent's question and its answers are in the pane, and a choice is the next thing said", { timeout: 180000 }, async (t) => {
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

  const sent = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const path = new URL(req.url()).pathname;
    if (path === `/api/tasks/${made.taskId}/assistant`) {
      return void req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({
        messages: [{ id: "m1", role: "assistant", content: [{ type: "text", text: "The login page is open with the username field focused." }] }],
        asking: { request_id: "r1", kind: "input_needed", text: "Have you signed in successfully?", choices: ["Signed in", "Login failed"] },
        session: null, starting: false, providers: [{ id: 1, label: "Test CLI", model: "" }] }) });
    }
    if (path.endsWith("/assistant/stream")) {
      sent.push(JSON.parse(req.postData() || "{}"));
      return void req.respond({ status: 200, contentType: "application/x-ndjson",
        body: `${JSON.stringify({ type: "done", reply: "Reading the secure area now." })}\n` });
    }
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-asking", { timeout: 20000 });

  const card = await page.$eval(".tq-aui-asking", (el) => el.innerText);
  assert.match(card, /asked you/, "the card must say who is waiting");
  assert.match(card, /Have you signed in successfully\?/, "the question itself is missing");

  const labels = await page.$$eval(".tq-aui-asking-choices button", (bs) => bs.map((b) => b.textContent.trim()));
  assert.deepEqual(labels, ["Signed in", "Login failed"], "the answers it offered must be clickable");

  await page.evaluate(() => [...document.querySelectorAll(".tq-aui-asking-choices button")]
    .find((b) => b.textContent.trim() === "Signed in").click());
  await page.waitForFunction(() => !document.querySelector(".tq-aui-asking"), { timeout: 10000 });

  assert.equal(sent.length, 1, `the choice was not sent: ${JSON.stringify(sent)}`);
  assert.equal(sent[0].text, "Signed in", "the choice goes in as the owner's own next message");
  assert.deepEqual(errors, []);
});

/* A LONG ANSWER THAT ENDS IN A QUESTION, OPENED IN A SHORT WINDOW. Pinned to the bottom, the question card, the report offer
   and the input took the room and the owner read the answer's last paragraph only (2026-10-18: "I can't see any of the agent
   output without scrolling"). Opened, the answer reads from its first line; the offer to schedule waits until nothing is asked. */
test("a long answer opens at its first line, and nothing offers to schedule a run that is waiting on you", { timeout: 180000 }, async (t) => {
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
  await page.waitForSelector(".tq-aui-asking", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 1200));

  const seen = await page.evaluate(() => {
    const v = document.querySelector(".tq-aui-viewport"), m = [...v.querySelectorAll(".tq-aui-agent")].pop();
    const vr = v.getBoundingClientRect(), mr = m.getBoundingClientRect();
    return { scrolled: v.scrollTop, overflow: v.scrollHeight > v.clientHeight, top: mr.top - vr.top, offer: !!document.querySelector(".tq-aui-report-action") };
  });
  assert.ok(seen.overflow, `the answer must be longer than the pane for this to test anything: ${JSON.stringify(seen)}`);
  assert.ok(seen.top >= 0 && seen.top < 40, `the answer's first line must open at the top of the pane: ${JSON.stringify(seen)}`);
  assert.equal(seen.offer, false, "no 'Worth running again?' while the agent waits on your call");
  assert.deepEqual(errors, []);
});
