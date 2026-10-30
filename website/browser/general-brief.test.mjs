import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* TASKUARY'S INSTRUCTIONS ARE NOT THE OWNER'S WORDS (the owner, 2026-10-30): an agent that started by itself showed the brief it was
   handed - "THIS TASK IS A REPLY OWED..." - under YOU, as though the owner had typed it. The server marks that turn (general.BRIEF_ACTOR,
   `brief` on the message - pinned in tests/test_session_record.py); the pane draws it as one grey line, "Taskuary's instructions", whose
   text opens on a click. What the owner typed after it is still under YOU. */
const BRIEF = "THIS TASK IS A REPLY OWED to Erin Blake, and it needs work before it can be answered.";
const MINE = "Check whether Saturday works too.";

test("an auto-start brief is one folded line, and the owner's own words stay under YOU", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Partner day on Friday", Summary: "Erin Blake asks whether we go to the partner day", Kind: "general", Assignee: "agent:researcher" }) })).json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  const at = new Date().toISOString(), text = (s) => [{ type: "text", text: s }];
  const ses = { sid: "g1", taskId: made.taskId, alive: true, busy: false, mode: "chat", cli: "taskuary", agent: "researcher",
                provider: "Codex", trace: [], trace_revision: 0 };
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const p = new URL(req.url()).pathname, json = (body) => req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant`) return void json({ session: ses, starting: false,
      providers: [{ id: 1, label: "Codex", model: "" }], messages: [
        { id: "comment-1", role: "user", brief: true, createdAt: at, content: text(BRIEF) },
        { id: "comment-2", role: "assistant", createdAt: at, content: text("Friday works for Erin's session.") },
        { id: "comment-3", role: "user", createdAt: at, content: text(MINE) },
        { id: "comment-4", role: "assistant", createdAt: at, content: text("Saturday is free as well.") }] });
    if (req.method() === "GET" && p === "/api/terminals") return void json({ data: [ses] });
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-brief [data-tq-brief] summary", { timeout: 30000 });
  const seen = await page.evaluate(() => ({
    briefs: document.querySelectorAll(".tq-aui-brief").length,
    label: document.querySelector(".tq-aui-brief summary").innerText.trim(),
    open: document.querySelector(".tq-aui-brief details").open,
    shown: document.querySelector(".tq-aui-brief details > div").checkVisibility(),
    yours: [...document.querySelectorAll(".tq-aui-user")].map((m) => m.innerText) }));
  assert.equal(seen.briefs, 1);
  assert.equal(seen.label, "Taskuary's instructions");
  assert.equal(seen.open, false, "folded until clicked");
  assert.equal(seen.shown, false, "its text is not on screen folded");
  assert.equal(seen.yours.length, 1, "only the owner's own line is under YOU");
  assert.match(seen.yours[0], /you/i); assert.ok(seen.yours[0].includes(MINE)); assert.ok(!seen.yours[0].includes("REPLY OWED"));

  await page.click(".tq-aui-brief summary");
  await page.waitForFunction((b) => document.querySelector(".tq-aui-brief details").open
    && document.querySelector(".tq-aui-brief details > div").innerText.includes(b), { timeout: 5000 }, BRIEF);
  assert.deepEqual(errors, []);
});
