import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A TRACKER TASK CLOSES OUT ON ITS ITEM (trackers.py, 2026-10-25): a task from a Jira item whose agent finished proposes "comment and move
   to Done" as Close out's move, the comment drafted from the result - the GitHub close-out's card, with the tracker's own done state read
   from Jira when the card is drawn. The fixture's Jira lives in the server's process; nothing reaches it until the owner presses. */
const COMMENT = "The export read a renamed view; it reads the new one, and tonight's run will be full.";

test("a Jira task's Close out shows the comment and the move to Done, and nothing is written before the press", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const call = (path, body) => page.evaluate(async ([p, b]) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch(p, b ? { method: "POST", headers, body: JSON.stringify(b) } : { headers });
    return r.json();
  }, [path, body]);
  const made = await call("/api/fixture/task/tracker-closeout", { comment: COMMENT });
  assert.ok(made.taskId, `no tracker close-out: ${JSON.stringify(made)}`);

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-closeout] textarea", { timeout: 20000 });
  await page.waitForFunction(() => /NW-12 in Jira → Done/.test(document.querySelector("[data-tq-closeout]")?.innerText || ""), { timeout: 20000 });

  const seen = await page.evaluate(() => {
    const box = document.querySelector("[data-tq-closeout]");
    const approve = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Approve");
    return { text: box.innerText, draft: box.querySelector("textarea").value, approve: !!approve, live: approve && !approve.disabled };
  });
  assert.equal(seen.draft, COMMENT, "the comment is drafted from the agent's result");
  assert.match(seen.text, /Approve comments on NW-12 and moves it to Done/);
  assert.ok(seen.approve, "Approve is the close-out's button");
  await page.waitForFunction(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Approve");
    return b && !b.disabled;
  }, { timeout: 20000 });                         // the card read Jira (the fixture's) and found the move to Done there
  assert.deepEqual((await call("/api/fixture/tracker/writes")).writes, [], "drawing the card wrote nothing to Jira");
  assert.deepEqual(errors, []);
});
