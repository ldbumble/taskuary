import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* SEND KEEPS CLOSE OUT ON THE PAGE (the owner, 2026-10-27: "I hit send on close out and instead of keeping that page open it reopened the
   task page??? what are we doing here"). With the draft gone and only mail sent OUTSIDE Taskuary counted, a reply sent from here read as
   "a reply owed, nothing written" - that stage's main view is the task, and the page swapped under the owner's hand. The page stays where
   it is through Send, and the sent reply is what Close out shows. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Send on Close out keeps Close out on the page", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting for Send");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"] [data-tq-closeout]`, { timeout: 20000 });
  await sleep(2500);
  const mainOf = () => page.$eval("[data-tq-task-body]", (e) => e.getAttribute("data-tq-main"));
  const before = await mainOf();
  assert.equal(before, "work", "a drafted reply opens on Close out");
  // the card's own Send, under the draft
  const sent = await page.evaluate(() => {
    const b = [...document.querySelectorAll("[data-tq-closeout] button")].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    if (!b) return false; b.click(); return true;
  });
  assert.ok(sent, "Close out offers Send");
  const seen = new Set();
  for (let i = 0; i < 16; i++) { await sleep(500); seen.add(await mainOf()); }
  assert.deepEqual([...seen], ["work"], `the page stayed on Close out through Send, never the task: ${[...seen]}`);
  assert.ok(await page.$("[data-tq-task-body] [data-tq-closeout]"), "Close out is still the page");
  assert.deepEqual(errors, []);
});
