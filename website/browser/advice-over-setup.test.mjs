import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* A TASK OPENED OVER SETUP IS THE ITEM IN FRONT OF THE OWNER (the 2026-10-26 memory A/B's UI pass): opened by its link or by Search while
   setup was still open, it drew its row with nothing lit and no line, while the same task reached in the walk had its line and its lit
   button - the table counted setup as being in view (tableOf's `setup`) though the task was drawn over it. The decision is stood in for
   here (the fresh fixture has no AI), so what is checked is the page: the line is said, its button lit, and Back to Setup puts setup back
   with the strip quiet. Invented Northwind people. */

const LINE = "You usually answer Erin within the hour; this is 3h.";

test("a task opened over setup has its Advisor line and lit button; back on setup the strip is quiet", { timeout: 240000 }, async (t) => {
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
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ key, state: "asked_late", verb: "close", label: "Mark done",
        line: LINE, by: "rule", revision: "r1", pill: "Mark done", evidence: [], ask: true, needs_ai: false }) });
    }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  const said = () => page.evaluate((l) => [...document.querySelectorAll(".tq-next-txt")].some((e) => e.textContent.includes(l)), LINE);
  await page.waitForFunction(() => /Back to Setup|Your AI/.test(document.body.innerText), { timeout: 60000, polling: 200 });
  assert.equal(await said(), false, "setup in view: no Advisor line");

  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, made.taskId);
  await page.waitForFunction((l) => [...document.querySelectorAll(".tq-next-txt")].some((e) => e.textContent.includes(l)), { timeout: 30000, polling: 200 }, LINE)
    .catch(async (e) => { throw new Error(`${e.message}\n${(await page.evaluate(() => document.body.innerText)).slice(-1200)}`); });
  assert.ok(await page.$('.tq-arow .tq-ab.p[data-tq-verb]'), "its button is lit");

  // ...and Back to Setup: setup is in view again, and the task's line is not said over it
  const back = await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "Back to Setup"); b?.click(); return !!b; });
  assert.ok(back, "Back to Setup is offered over the task");
  await page.waitForFunction((l) => ![...document.querySelectorAll(".tq-next-txt")].some((e) => e.textContent.includes(l)), { timeout: 20000, polling: 200 }, LINE);
  assert.deepEqual(errors, []);
});
