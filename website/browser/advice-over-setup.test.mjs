import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* A TASK OPENED OVER SETUP IS THE ITEM IN FRONT OF THE OWNER (the 2026-10-26 memory A/B's UI pass): opened by its link or by Search while
   setup was still open, it drew its row with nothing lit, while the same task reached in the walk had its lit button - the table counted
   setup as being in view (tableOf's `setup`) though the task was drawn over it. The decision is stood in for here (the fresh fixture has no
   AI): its button is lit, and its line - no strip over the row since 2026-10-26 (the owner: "remove the advisor") - stands in the task's
   Advisor section; Back to Setup puts setup back, with nothing said over it. Invented Northwind people. */

const LINE = "Ray Colton already answered this on the thread.";

test("a task opened over setup has its lit button and its line in the task's Advisor section; back on setup nothing is said", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const H = { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" };
  const made = await (await fetch(`${harness.fixtureApi}/api/tasks`, { method: "POST", headers: H, body: JSON.stringify({ Title: "Q4 headcount forecast" }) })).json();
  assert.ok(made.taskId, "a task to open");

  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname === "/api/advice") {
      const key = u.searchParams.get("key");
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ key, state: "asked", verb: "close", label: "Mark done",
        line: LINE, by: "model", revision: "r1", pill: "Mark done", evidence: [], ask: true, needs_ai: false }) });
    }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  const said = () => page.evaluate((l) => document.body.innerText.includes(l), LINE);
  await page.waitForFunction(() => /Back to Setup|Your AI/.test(document.body.innerText), { timeout: 60000, polling: 200 });
  assert.equal(await said(), false, "setup in view: nothing of the Advisor's");

  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, made.taskId);
  await page.waitForFunction((l) => document.querySelector("[data-tq-canvas-item] [data-tq-advisor] [data-tq-advisor-note]")?.textContent.includes(l), { timeout: 30000, polling: 200 }, LINE)
    .catch(async (e) => { throw new Error(`${e.message}\n${(await page.evaluate(() => document.body.innerText)).slice(-1200)}`); });
  // ...and its button lit on the row, which is drawn a beat after the section on a slow machine
  await page.waitForSelector(".tq-arow .tq-ab.p[data-tq-verb]", { timeout: 15000 }).catch(async () => assert.fail(`its button is not lit: ${
    await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")].map((b) => `${b.getAttribute("data-tq-verb")}.${b.className}`).join(", "))}`));
  assert.equal(await page.$(".tq-dock .tq-next, [data-tq-strip]"), null, "and nothing over the row");
  // ...in the task's own Advisor section (the owner, 2026-10-26), its line keeping its Why? - in the MAIN view, never a drawer, so no tab
  // says it holds a note (the Advisor audit's judge, 2026-10-26)
  assert.ok(await page.$("[data-tq-advisor] .tq-next-why"), "the line's Why?");
  assert.equal(await page.$("[data-tq-work-side] [data-tq-advisor], [data-tq-from-side] [data-tq-advisor]"), null, "not in a drawer");
  const tab = await page.evaluate(() => document.querySelector("[data-tq-work-tab]")?.textContent || "");
  assert.doesNotMatch(tab, /note/);

  // ...and Back to Setup: setup is in view again, and the task's warning goes with the task
  const back = await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "Back to Setup"); b?.click(); return !!b; });
  assert.ok(back, "Back to Setup is offered over the task");
  await page.waitForFunction((l) => !document.body.innerText.includes(l), { timeout: 20000, polling: 200 }, LINE);
  assert.deepEqual(errors, []);
});
