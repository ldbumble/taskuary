import assert from "node:assert/strict";
import test from "node:test";
import { boot, findRow, sleep } from "./walkdriver.mjs";

/* A BIG TASK OPENS AT ONCE (the owner, 2026-11-01: "this still happens"). A rail row clicked showed only a spinner with the task's title, in
   an empty frame, for seconds before the task page drew. The task was a long WhatsApp group - 1,500 lines, files, agent runs, saved
   sessions. Three things held it: the task's read judged where every line came from one line at a time (tests/test_big_task_opens_fast.py);
   the rail press put nothing on the table until the server's walk move answered, and that move rebuilt the rail, which counted the task's
   chain once per line of it (4.1-4.8 s here); and the page drew all 1,500 lines into Came from's spine to measure and hide all but a dozen.
   Clicked as a person clicks it - the pointer moves onto the row and presses - the task's own page is up within half a second of the
   press, the read asked at the pointer-down is the one it draws from, and no spinner stands over an empty frame longer than that.
   TQ_OPEN_TRACE=1 prints every request and long task from the press. */
const BUDGET = Number(process.env.TQ_OPEN_BUDGET || (process.env.CI ? 1500 : 500));

test("a big task clicked on the rail draws its page within half a second", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t);
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/fixture/task/big-chat", { method: "POST", headers, body: "{}" })).json();
  });
  assert.ok(made.taskId, `no task made: ${JSON.stringify(made)}`);
  let key = null;
  for (let i = 0; i < 40 && !key; i++) { await sleep(1000); key = await findRow(page, /walk-in cooler/); }
  assert.ok(key, "the big task has no row on the rail");
  // ...and the server done with what the fixture's own writes set off (the rail's first build over 1,500 new lines), as a home at rest is
  await page.evaluate(async () => { await fetch("/api/funnel/pile?fyi=50", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } }); });
  await sleep(3000);
  // every frame from the press: when the task's own page is up (its header line in the card on the table), and every stretch a spinner stood
  await page.evaluate((key) => {
    const log = window.__tqOpen = { t0: 0, head: 0, spin: [], reads: [], all: [] };
    const on = () => {
      if (!log.t0) return;
      const t = performance.now() - log.t0, spin = !!document.querySelector("[data-tq-canvas-item] [data-tq-task-loading]"), last = log.spin.at(-1);
      if (spin && !(last && last.to == null)) log.spin.push({ from: t, to: null });
      if (!spin && last && last.to == null) last.to = t;
      if (!log.head && document.querySelector(`[data-tq-canvas-item="${key}"] [data-tq-task-head]`)) log.head = t;
    };
    const tick = () => { on(); requestAnimationFrame(tick); }; tick();
    const note = (e, what) => log.all.push(`${Math.round(e.startTime - log.t0)}+${Math.round(e.duration)} ${what}`);
    new PerformanceObserver((l) => l.getEntries().forEach((e) => { if (/\/api\/tasks\/\d+$/.test(e.name)) log.reads.push(Math.round(e.duration));
      note(e, e.name.replace(location.origin, "").slice(0, 80)); })).observe({ type: "resource" });
    new PerformanceObserver((l) => l.getEntries().forEach((e) => note(e, "long task"))).observe({ type: "longtask" });
    document.addEventListener("pointerdown", () => { if (!log.t0) log.t0 = performance.now(); }, { capture: true });
  }, key);
  await (await page.$(`[data-tq-rail] .tq-pile-row[data-tq-key="${key}"] .card`)).click();
  await page.waitForFunction(() => window.__tqOpen.head > 0, { timeout: 30000 });
  await sleep(1500);
  const log = await page.evaluate(() => window.__tqOpen);
  const spun = log.spin.map((s) => (s.to ?? log.head + 1500) - s.from);
  if (process.env.TQ_OPEN_TRACE) console.log(log.all.join("\n"));
  console.log(`big task: page up ${Math.round(log.head)} ms after the press; spinner ${JSON.stringify(spun.map(Math.round))} ms; task reads ${JSON.stringify(log.reads)} ms`);
  assert.ok(log.head <= BUDGET, `the task page came up ${Math.round(log.head)} ms after the press (budget ${BUDGET})`);
  assert.ok(spun.every((ms) => ms <= BUDGET), `a spinner stood over an empty frame: ${JSON.stringify(spun)}`);
  // ...one read asked ahead and the view's own after it, never a third beside them on the way up
  assert.ok(log.reads.length <= 2, `the task was read ${log.reads.length} times on the way up: ${JSON.stringify(log.reads)}`);
  assert.deepEqual(errors, []);
});
