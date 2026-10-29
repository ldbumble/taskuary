import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE SMALL PILL LEAVES A LAPTOP ITS BUTTONS (the owner, 2026-10-27: "yes shrink the chat box"). At 220px the one-row bar's chat pill took
   the room Mark done and Send to agent need, and on a 1366-1600px laptop they folded behind a ▾ - two clicks each, and Mark done's next
   card ~500-800 ms instead of ~200. The chat is its own small pill in the corner now (the owner, 2026-10-29), the bar ending before it: Mark
   done stays on the bar, on one line, at every laptop width - and Send to agent, a stage move, is on Agent's spine, never the bar's. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("at rest the pill is small and Mark done stays on the row at 1366, 1440 and 1600px", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const reply = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(reply, "the demo's invoice reply");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, reply.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${reply.TaskId}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  for (const width of [1366, 1440, 1600]) {
    await page.setViewport({ width, height: 810, deviceScaleFactor: 1 });
    await sleep(1500);
    const s = await page.evaluate(() => {
      const line = document.querySelector(".tq-dock .tq-dock-line"), pill = document.querySelector(".tq-chat-unit .tq-compose-box");
      const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      return { pill: Math.round(pill.getBoundingClientRect().width), line: Math.round(line.getBoundingClientRect().height),
        // ...the task's own moves on its title bar now (the owner, 2026-10-29: the bar is Back and Next)
        verbs: [...document.querySelectorAll("[data-tq-row] button[data-tq-verb], [data-tq-head-moves] button[data-tq-verb]")].filter(vis).map((b) => b.getAttribute("data-tq-verb").split(":").pop()),
        spine: [...document.querySelectorAll("[data-tq-spine-moves=agent] button[data-tq-verb]")].filter(vis).map((b) => b.getAttribute("data-tq-verb")) };
    });
    const say = `${width}px ${JSON.stringify(s)}`;
    assert.ok(s.pill >= 300, `the wide ask bar, as wide as the open window (the owner, 2026-10-29) ${say}`);
    assert.ok(s.line <= 46, `one line ${say}`);
    console.log(`# ${say}`);
    // ...and Close folds last (the owner, 2026-10-27: "if there is no space"): Mark done is on the row at every laptop width
    assert.ok(s.verbs.includes("done"), `Mark done is on the title bar, not behind a ▾ ${say}`);
    assert.ok(!s.verbs.some((v) => /agent/.test(v)) && s.spine.some((v) => /agent/.test(v)), `Send to agent is on Agent's spine, not the bar ${say}`);
  }
  assert.deepEqual(errors, []);
});
