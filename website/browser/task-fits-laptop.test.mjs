import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

// A FAILED RUN FITS A LAPTOP (the owner, 2026-10-26, 1600x810: "you can't see anything. there are too many lines on top of the tasks. button
// height is too high? you can't see what you have to do.. this has to be fixed"): a playbook whose agent could not start, cut off by a
// restart after. Its title was said twice, three scrollbars stood in one column, the reason it failed was at the foot of a scroller inside
// a scroller, and the dock took 138px. Now: the title once, one scroller per column, the reason first, the dock about 115px.
test("a failed playbook run shows its title once, its reason first, one scroller per column and a short dock", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await page.evaluate(async () => (await fetch("/api/fixture/task/playbook-failed", { method: "POST", body: "{}",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(made.taskId, JSON.stringify(made));
  for (const [width, height] of [[1600, 810], [1366, 768]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, made.taskId);
    await page.waitForSelector(`[data-tq-task-page="${made.taskId}"] [data-tq-run-why]`, { timeout: 20000 });
    await page.waitForSelector(".tq-dock [data-tq-row]", { timeout: 20000 });
    await new Promise((resolve) => setTimeout(resolve, 2200));   // past the lit move's hold and the chat's first draw
    const m = await page.evaluate(() => {
      const card = document.querySelector("[data-tq-canvas-item]");
      const cols = [...card.querySelectorAll("[data-tq-from], [data-tq-work]")];
      const scrolls = (e) => /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 1;
      const inner = cols.flatMap((c) => [...c.querySelectorAll("*")].filter(scrolls)
        .map((e) => `${[...e.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.name).join(",") || e.className} ${e.clientHeight}/${e.scrollHeight}`));
      const why = card.querySelector("[data-tq-run-why]"), w = why.getBoundingClientRect();
      // seen: inside the window and inside every box above it that clips
      let seen = w.top >= 0 && w.bottom <= innerHeight;
      for (let p = why.parentElement; p && seen; p = p.parentElement) {
        if (getComputedStyle(p).overflowY === "visible") continue;
        const b = p.getBoundingClientRect(); seen = w.top >= b.top - 1 && w.bottom <= b.bottom + 1;
      }
      const title = card.querySelector("[data-tq-task-head]").textContent.match(/Create playbook: [^.]{20}/)?.[0] || "";
      return { inner, seen, why: why.textContent, ask: !!card.querySelector("[data-tq-ask]"), title,
        twice: title ? card.innerText.split(title).length - 1 : -1, dock: document.querySelector(".tq-dock").getBoundingClientRect().height };
    });
    const say = `${width}x${height}: ${JSON.stringify(m)}`;
    assert.deepEqual(m.inner, [], `nothing scrolls inside a column ${say}`);
    assert.ok(m.title && !m.ask && m.twice === 1, `the title is said once ${say}`);
    assert.match(m.why, /could not start: this tool has no built-in reviewer/, say);
    assert.ok(m.seen, `the reason is in view ${say}`);
    assert.ok(m.dock <= 120, `the dock is short ${say}`);
  }
  assert.deepEqual(errors, []);
});
