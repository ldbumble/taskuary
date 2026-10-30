import assert from "node:assert/strict";
import test from "node:test";
import { boot, rail } from "./walkdriver.mjs";

/* THE DEMO OPENS ON ITS TOUR (the owner, 2026-10-30: "when you open it it first opens on a task list todo to get sense of what it can
   do"): the first view is the tour task on the canvas, its to-do read top down, its row the rail's first. */
test("the demo's first view is the tour task, its to-do in reading order", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900, tour: true });
  const opened = await page.waitForFunction(() => !!document.querySelector("[data-tq-todo]") && /TQ-\d+\s*Start here - what Taskuary can do/.test(document.body.innerText),
    { timeout: 20000 }).catch(() => null);
  assert.ok(opened, "the canvas did not open on the tour");
  const todo = await page.$eval("[data-tq-todo]", (e) => e.innerText);
  const at = (s) => todo.indexOf(s);
  assert.ok(at("Month-end close") >= 0 && at("Month-end close") < at("Next and Back") && at("Next and Back") < at("What's on me right now?"),
    `the steps are not top down: ${todo}`);
  assert.match(todo, /0 of 6/, "every step shown, none behind Show more");
  const rows = await rail(page);
  assert.match(rows[0].text, /Start here/, "the tour leads the rail");
  // ...an own to-do: nobody to reply to, and nothing for an agent to start
  const body = await page.evaluate(() => document.body.innerText);
  assert.match(body, /Nothing owed/); assert.doesNotMatch(body, /Reply to Taskuary/);
  assert.deepEqual(errors, []);
});
