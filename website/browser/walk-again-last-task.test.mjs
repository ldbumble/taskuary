import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* NEXT ON THE LAST TASK OFFERS THE WALK AGAIN (the owner, 2026-10-25: "I hit next when a task is the last thing and the walk through
   again did not show up"). The end of a walk put "Walk me through my tasks" on the row only beside an Open of a task on the owner: a
   task left waiting on someone else is still under Tasks, but is not on them, so the row said "Nothing's waiting." over it and offered a
   bare Next. Here: the demo with one open task left - waiting on its other party - walked to the end, then walked again to that task.
   ...and since Nav (the owner, 2026-10-27: "on the first one no Back, like no Next on the last one"), that task - the last thing, and the
   first - wears neither: its row is its own moves, and the walk again stands at the end of a walk. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function request(h, path, method = "GET", body) {
  const r = await fetch(`${h.fixtureApi}${path}`, { method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  assert.ok(r.ok, `${method} ${path}: ${r.status}`);
  return r.json();
}
const WALK = "Walk me through my tasks";
const press = (page, re) => page.evaluate((src) => {
  const b = [...document.querySelectorAll(".tq-asst-col button")].find((n) => new RegExp(src).test(n.textContent.trim()) && !n.disabled && n.offsetParent);
  if (b) b.click(); return !!b;
}, re.source);
// ...a greyed button is no way to go (the owner, 2026-10-29: on a desk Back is always on the bar, greyed where there is nowhere to go back to)
const row = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-asst-col button")].filter((b) => b.offsetParent && !b.disabled).map((b) => b.textContent.trim()));
const said = (page) => page.$$eval(".tq-msg .body", (els) => els.map((e) => e.textContent.trim()));
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(250)) if (await f()) return true; return false; };

test("the end of a walk with one task left, waiting on someone else, offers Walk me through my tasks again - and that task, the last, has no Next", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const pile = await request(h, "/api/funnel/pile");
  const theirs = pile.items.find((i) => i.tid && i.lane === "theirs");
  assert.ok(theirs, "the demo has a task waiting on someone else");
  for (const i of pile.items) if (i.tid && i.tid !== theirs.tid) await request(h, `/api/tasks/${i.tid}`, "PATCH", { Status: "done" });
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await sleep(2000);
  // the first walk: the one task, then every report and fyi, to the end
  assert.ok(await until(() => press(page, /^Walk me through my tasks$/)), "the day opens with its Walk");
  for (let i = 0; i < 30 && await until(() => press(page, /^(Next|All read, next)$/), 6000); i += 1) await sleep(1500);
  await sleep(2000);
  assert.ok((await row(page)).includes(WALK), `the end of the walk offers the walk again: ${JSON.stringify(await row(page))}`);
  // ...nor "Nothing else needs you right now; 1 in progress." where an agent's work is what is left: the Walk button says it (the owner, 2026-10-25)
  assert.ok(!(await said(page)).some((s) => s === "Nothing's waiting." || s.startsWith("Nothing else needs you right now")), "no sentence over a task still on the rail");
  // ...and walking again brings the task up, and Next on it - the last thing - offers the walk again
  await press(page, /^Walk me through my tasks$/);
  assert.ok(await until(() => page.evaluate((ref) => [...document.querySelectorAll(".tq-asst-col")].some((c) => c.textContent.includes(ref)), theirs.ref)),
    "the walk again brings the task up");
  assert.ok(await until(async () => (await row(page)).length > 1), "the task's own row is up");
  await sleep(2500);
  const last = await row(page);
  assert.ok(!last.includes("Next") && !last.includes("Back"), `the only thing left: no Next below it, no Back above it: ${JSON.stringify(last)}`);
  assert.deepEqual(errors, []);
});
