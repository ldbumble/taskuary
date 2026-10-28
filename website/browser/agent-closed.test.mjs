import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* AN AGENT'S OWN CLOSE OPENS ON ITS WORK (the owner, 2026-10-21: "when an agent closes a task and no close out is needed, I have no
   idea what the agent did and why it closed. The agent thing should open, not the close part"). On the table the page has no list
   row: it read the agent's close as "stopped and saved" and opened Close out, which said only "Work it, or write what you found".
   The fixture closes a demo task through the real ending (selfclose.declare); the page opens it on the table, as the rail does. */
const ANSWER = "The nightly run in org/app failed on a missing DEPLOY_KEY secret. I re-added it and the re-run passed.";
const SAID = "the run failed on a missing secret; re-added it and the re-run passed";

// ...the agent's half of the work column is its Result since the redesign (owner-approved 2026-10-21), and says first that nothing waits
test("a task its agent closed opens on its Result, saying it is handled, who closed it and why", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async (body) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/fixture/task/agent-closed", { method: "POST", headers, body: JSON.stringify(body) });
    return r.json();
  }, { answer: ANSWER, said: SAID });
  assert.ok(made.taskId, `task not closed by its agent: ${JSON.stringify(made)}`);

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-closeout]", { timeout: 20000 });
  // ...a closed task opens on Close out (the three sections, 2026-10-27): who closed it and why are the Agent's - its tab opens it
  await page.waitForSelector("[data-tq-section-tab=agent]", { timeout: 20000 });
  await page.click("[data-tq-section-tab=agent]");
  await page.waitForFunction((said) => document.querySelector("[data-tq-closed-why]")?.textContent === `Closed by the agent: ${said}`,
    { timeout: 20000 }, SAID);
  // the reason line comes with the task's details; the agent's write-up is its own read and can land a beat later (CI, 2026-10-21)
  await page.waitForFunction((head) => document.body.innerText.includes(head), { timeout: 20000 }, ANSWER.slice(0, 60));

  const seen = await page.evaluate(() => {
    const agent = document.querySelector("[data-tq-agent-section]"), full = agent?.querySelector("[data-tq-full-result]");
    return { agentHead: agent?.querySelector("[data-tq-section-head]")?.innerText || "", agentFolded: full?.getAttribute("aria-expanded") === "false",
      closeFolded: !!document.querySelector("[data-tq-section-tab=close]"), handled: document.querySelector("[data-tq-handled]")?.textContent || "", text: document.body.innerText };
  });
  assert.match(seen.agentHead, /^2 · Agent/i, "the agent's section");
  // ...resting on its summary: one press unfolds the rest (the owner, 2026-10-27: "just the summary"; "why are there 2 buttons for full results?")
  assert.equal(seen.agentFolded, true, "the Result rests on its summary");
  assert.ok(await page.$("[data-tq-result-summary]"), "the Result's summary is on screen");
  assert.equal(seen.handled, "Nothing to do. It's handled.");
  assert.equal(seen.closeFolded, true, "Close out is its tab");
  assert.ok(seen.text.includes(ANSWER.slice(0, 60)), "the agent's write-up is on screen");
  assert.doesNotMatch(seen.text, /Work it, or write what you found/, "no advice for an open task on a closed one");
  assert.deepEqual(errors, []);
});
