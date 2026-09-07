import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

// TQ-0420: "New task for the agent" with no repository created the task, navigated to it, and
// showed an empty box. The workspace gated its whole body - welcome, composer, and the effect that
// asks the typed question - on a live session, and a task that has never run has none.
test("a general task with no session opens as a usable chat and asks its question", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Research Instinct", Summary: "Research what people say about Instinct online.",
      Kind: "general", Tags: "ask:assistant" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-composer textarea", { timeout: 20000 });

  // the pane is a chat, not an empty box: the composer takes input with nothing running
  assert.equal(await page.$eval(".tq-aui-composer textarea", (el) => el.disabled), false);
  const box = await page.$eval(".tq-aui-thread", (el) => el.getBoundingClientRect().height);
  assert.ok(box > 300, `the chat should take the task page's room, got ${box}px`);

  // ...and the question the owner typed is asked, by the thread, as the first message
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-user")]
    .some((m) => m.innerText.includes("Research what people say about Instinct online.")), { timeout: 20000 });

  // asked once and only once - the tag is stripped on the server as it goes (newTask.js)
  const after = await page.evaluate(async (id) => (await fetch(`/api/tasks/${id}`, {
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), made.taskId);
  assert.doesNotMatch(String(after.task?.Tags || ""), /ask:assistant/);
  assert.deepEqual(errors, []);
});
