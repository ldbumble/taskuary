import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* WHAT YOU ARE TYPING SURVIVES WHAT THE AGENT IS DOING. The busy poll bumped a key on the thread
   every time an answer or a tool step landed, which REMOUNTS it - and the draft lives in the
   composer inside that runtime, so the box emptied under the owner's fingers every 2.5s while an
   agent worked (the owner, 2026-09-14: "when i start typing it automatically goes off").

   The agent is the fixture: /assistant answers busy, with one more message on every poll, which is
   exactly the signal the pane rebuilt itself on. */
test("a draft survives the agent's own progress, and keeps its cursor", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Clock in to ADP", Summary: "Clock me in", Kind: "general", Tags: "ask:assistant" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  // the working agent: every poll of this task's assistant state has one more thing in it
  let polls = 0;
  page.off("request", page.fixtureRequestGuard);           // this one answers first, the guard still guards
  page.on("request", (req) => {
    if (new URL(req.url()).pathname !== `/api/tasks/${made.taskId}/assistant`) return void page.fixtureRequestGuard(req);
    polls += 1;
    const messages = Array.from({ length: polls }, (_, i) => ({
      id: `m${i}`, role: "assistant", content: [{ type: "text", text: `step ${i + 1}: reading the sign-in page` }],
    }));
    req.respond({ status: 200, contentType: "application/json",
      body: JSON.stringify({ messages, session: null, starting: true, providers: [{ id: 1, label: "Test CLI", model: "" }] }) });
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-composer textarea", { timeout: 20000 });
  await page.waitForFunction(() => document.body.innerText.includes("step 1"), { timeout: 20000 });

  const draft = "my ADP user id is the one on the badge";
  await page.click(".tq-aui-composer textarea");
  await page.keyboard.type(draft);
  const pollsAtStart = polls;

  // three ticks of the 2.5s poll, each one landing a new message under the typing
  await page.waitForFunction(() => document.body.innerText.includes("step 4"), { timeout: 30000, polling: 200 });
  assert.ok(polls > pollsAtStart + 1, `the fixture agent never worked: ${pollsAtStart} -> ${polls} polls`);

  const state = await page.evaluate(() => {
    const box = document.querySelector(".tq-aui-composer textarea");
    return { text: box.value, focused: document.activeElement === box, caret: box.selectionStart };
  });
  assert.equal(state.text, draft, "the agent's progress emptied the composer");
  assert.equal(state.focused, true, "the composer lost the keyboard while the agent worked");
  assert.equal(state.caret, draft.length, "the cursor moved");

  // and it is still a live box afterwards: the rest of the sentence goes in where the cursor is
  await page.keyboard.type(" - 4821");
  assert.equal(await page.$eval(".tq-aui-composer textarea", (el) => el.value), `${draft} - 4821`);
  assert.deepEqual(errors, []);
});
