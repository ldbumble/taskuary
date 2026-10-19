import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE HAND IT RAISED IS THE AGENT'S OWN WORDS. The question and its choices used to be repeated in a card with answer
   buttons under the answer (2026-09-15); the owner removed it (2026-10-19: "inline we have the agent to talk to, no need
   to intermediate"). Only the WhatsApp doorway relays a question with its choices. Here the answer reads as the agent
   wrote it, nothing is drawn over or under it, and the owner's reply goes in the composer.

   The fixture is the raised hand: /assistant answers with `asking`, exactly as the server does. */
test("the agent's question is its own answer - no card with answer buttons in the pane", { timeout: 180000 }, async (t) => {
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

  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    if (new URL(req.url()).pathname === `/api/tasks/${made.taskId}/assistant`) {
      return void req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({
        messages: [{ id: "m1", role: "assistant", content: [{ type: "text", text: "The login page is open. Have you signed in successfully?" }] }],
        asking: { request_id: "r1", kind: "input_needed", text: "Have you signed in successfully?", choices: ["Signed in", "Login failed"] },
        session: null, starting: false, providers: [{ id: 1, label: "Test CLI", model: "" }] }) });
    }
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes("Have you signed in")),
    { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 800));
  const shown = await page.evaluate(() => ({ card: !!document.querySelector(".tq-aui-asking"),
    choices: [...document.querySelectorAll("button")].filter((b) => ["Signed in", "Login failed"].includes(b.textContent.trim())).length }));
  assert.deepEqual(shown, { card: false, choices: 0 }, "the question is not repeated as a card with answer buttons");
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
  await page.waitForSelector(".tq-aui-agent", { timeout: 20000 });
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
