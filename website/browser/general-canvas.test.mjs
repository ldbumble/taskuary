import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

// THE GENERAL AGENT'S CANVAS READS AS WHAT IT DID (the owner, 2026-10-21: "make the output on the general agent canvas more readable,
// not some greps and gets"). A research task one email brought, whose agent finished a turn on Claude Code: the recorded stream from
// tests/fixtures/agent_steps, invented people and paths, on a demo server that started no CLI.
test("a finished research turn shows plain steps, its words and its answer - no scripts, no repeats, no schedule offer", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1280, height: 1000 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => (await fetch("/api/fixture/general/canvas", { method: "POST", body: "{}",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(made.taskId, `fixture not made: ${JSON.stringify(made)}`);
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => document.querySelector(".tq-aui-agent")?.innerText.includes("Gail Moreno"), { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 600));
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "general-canvas.png"), fullPage: true });

  const shown = await page.$eval(".tq-aui-thread", (el) => el.innerText);
  for (const step of ["Searched your mail for 'budget review' (3 results)", "Opened TQ-1142", "Read 2 files in Budget/",
    "Searched files for 'approvedTotal'", "Searched the web for 'northwind budget review policy'", "Read a page on docs.northwind.example",
    "I'll find the budget review thread first"]) assert.ok(shown.includes(step), `missing "${step}" in:\n${shown}`);
  // closed rows keep the raw call out of sight; nothing of it is on the page as text
  for (const raw of ["X-Taskuary-Token", "TASKUARY_TOKEN", "python -X", "json.load", "curl", "C:\\Users", "Agent progress", "session started"])
    assert.ok(!shown.includes(raw), `"${raw}" is shown:\n${shown}`);
  assert.equal(shown.split("Opened TQ-1142").length - 1, 1, "a step is drawn once");
  assert.equal(shown.split("I'll find the budget review thread first").length - 1, 1, "its words are said once");
  // a one-off research request about one email is not something to put on a schedule
  assert.ok(!shown.includes("Worth running again?"), "the recurring-report offer stands under a one-off answer");

  // ...and the raw call is one disclosure away, for debugging
  const opened = await page.evaluate(() => {
    const row = [...document.querySelectorAll(".tq-aui-step")].find((d) => d.innerText.includes("Opened TQ-1142"));
    row.open = true;
    return row.innerText;
  });
  assert.match(opened, /api\/tasks\/1142/);
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, "general-canvas-details.png"), fullPage: true });
  assert.deepEqual(errors, []);
});
