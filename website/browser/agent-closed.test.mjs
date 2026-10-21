import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* AN AGENT'S OWN CLOSE OPENS ON ITS WORK (the owner, 2026-10-21: "when an agent closes a task and no close out is needed, I have no
   idea what the agent did and why it closed. The agent thing should open, not the close part"). On the table the page has no list
   row: it read the agent's close as "stopped and saved" and opened Close out, which said only "Work it, or write what you found".
   The fixture closes a demo task through the real ending (selfclose.declare); the page opens it on the table, as the rail does. */
const ANSWER = "The nightly run in org/app failed on a missing DEPLOY_KEY secret. I re-added it and the re-run passed.";
const SAID = "the run failed on a missing secret; re-added it and the re-run passed";

test("a task its agent closed opens on Agent work, saying who closed it and why", { timeout: 180000 }, async (t) => {
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
  await page.waitForFunction((said) => document.querySelector("[data-tq-closed-why]")?.textContent === `Closed by the agent: ${said}`,
    { timeout: 20000 }, SAID);

  const seen = await page.evaluate(() => {
    const heading = (title) => [...document.querySelectorAll("[aria-expanded], [role=button], div")]
      .find((el) => el.querySelector(":scope > div > p")?.textContent === title);
    const folded = (title) => heading(title)?.getAttribute("aria-expanded") === "false";
    return { agentFolded: folded("Agent work"), closeFolded: folded("Close out"), text: document.body.innerText };
  });
  assert.equal(seen.agentFolded, false, "Agent work is the open step");
  assert.equal(seen.closeFolded, true, "Close out is folded");
  assert.ok(seen.text.includes(ANSWER.slice(0, 60)), "the agent's write-up is on screen");
  assert.doesNotMatch(seen.text, /Work it, or write what you found/, "no advice for an open task on a closed one");
  assert.deepEqual(errors, []);
});
