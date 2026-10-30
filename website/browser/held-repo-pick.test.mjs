import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* A START HELD FOR A REPOSITORY CARRIES ITS PICK ON THE LINE THAT SAYS SO (the owner, 2026-10-30): "Repository: none - not started"
   named the problem and offered nothing to press. The line has Choose where the code is, and it opens the task's own repository picker. */

test("a coding task held for a repository has Choose where the code is on its line, and it opens the picker", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const H = { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" };
  const made = await (await fetch(`${harness.fixtureApi}/api/tasks`, { method: "POST", headers: H,
    body: JSON.stringify({ Title: "Fix the nightly export", Summary: "The export drops its last row", Kind: "coding", Tags: "held:repo" }) })).json();
  assert.ok(made.taskId, "a task to open");
  assert.equal((await fetch(`${harness.fixtureApi}/api/setup/dismiss`, { method: "POST", headers: H, body: JSON.stringify({ dismissed: true }) })).status, 200);

  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, made.taskId);
  await page.waitForSelector("[data-tq-fact-alert='repo'] [data-tq-fact-pick='repo']", { timeout: 30000 })
    .catch(async (e) => { throw new Error(`${e.message}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`); });
  const line = await page.$eval("[data-tq-fact-alert='repo']", (el) => el.innerText);
  assert.match(line, /Repository: none - not started/);
  assert.match(line, /Choose where the code is/);
  assert.equal(await page.$("[data-tq-repo-picker]"), null, "the picker is closed until pressed");

  await page.click("[data-tq-fact-alert='repo'] [data-tq-fact-pick='repo']");
  await page.waitForSelector("[data-tq-repo-picker]", { visible: true, timeout: 10000 });
  assert.match(await page.$eval("[data-tq-repo-picker]", (el) => el.innerText), /Which code is this about\?/);
  assert.deepEqual(errors, []);
});
