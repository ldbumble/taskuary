import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { doVerb } from "./walkdriver.mjs";

/* THE USUAL RECIPIENT, CHOSEN NOT SENT (the owner, 2026-10-25: "Hand it to a person" pre-fills the usual recipient). On the demo world,
   where Priya's asks this week went on to Ruth: her new-starter ask's Hand it to a person opens with Ruth in To and says whose usual it
   is - and nothing is sent until Send it is pressed. Clicked through the failure first: the server failing the ask leaves the form as it
   always was, empty and quiet. Invented Northwind people. */

const TO = 'input[placeholder="who should own this — name or email"]';

test("Hand it to a person opens with the usual recipient chosen, not sent; a failed ask leaves it empty", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];
  const ask = tasks.find((x) => /^New starter on Monday/.test(x.Title || "") && x.Status === "open");
  assert.ok(ask, "the demo world has Priya's new-starter ask");

  const page = await harness.newPage(), errors = [], sends = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let fail = true;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const path = new URL(r.url()).pathname;
    if (r.method() === "POST" && /\/handoff$/.test(path)) sends.push(path);
    if (fail && /\/handoff\/usual$/.test(path)) return r.respond({ status: 500, contentType: "application/json", body: "{}" });
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  const hand = async () => {
    await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, ask.TaskId);
    await page.waitForFunction((tid) => !!document.querySelector(`[data-tq-task-page="${tid}"] [data-tq-task-head]`), { timeout: 30000 }, String(ask.TaskId));
    // on the row or behind its fold, wherever it fits (the action row is one line)
    let how = null;
    for (let i = 0; i < 40 && !(how = await doVerb(page, "hand")); i++) await new Promise((r) => setTimeout(r, 250));
    assert.ok(how, "Hand it to a person is on the task's row");
    await page.waitForSelector(TO, { visible: true, timeout: 20000 });
  };
  const close = async () => {
    await page.click('[aria-label="Close handoff"]');
    await page.waitForFunction((sel) => !document.querySelector(sel), { timeout: 20000 }, TO);
  };

  // the failure path: the usual cannot be read, and the form is the one it always was
  await hand();
  await new Promise((r) => setTimeout(r, 1500));
  assert.equal(await page.$eval(TO, (e) => e.value), "", "nothing chosen when the ask failed");
  assert.equal(await page.$("[data-tq-handoff-usual]"), null);
  await close();

  // the usual recipient: Ruth, chosen and said whose usual she is - and not sent
  fail = false;
  await hand();
  await page.waitForFunction((sel) => document.querySelector(sel)?.value === "rbennett@northwind.example", { timeout: 20000 }, TO);
  assert.match(await page.$eval("[data-tq-handoff-usual]", (e) => e.textContent), /your usual for pshah@northwind\.example/);
  await new Promise((r) => setTimeout(r, 1000));
  assert.deepEqual(sends, [], "chosen, not sent: nothing goes until Send it is pressed");
  const now = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];
  assert.equal(now.find((x) => x.TaskId === ask.TaskId)?.Status, "open", "the task is still the owner's");
  assert.deepEqual(errors, []);
});
