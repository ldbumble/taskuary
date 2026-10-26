import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// A TASK OPENS SETTLED (the owner, 2026-10-26): "why is this cut off" - a long draft outgrew the work column, the lit Send was scrolled up
// to, and "Result" rested half under the column's edge; "should we not leave a drop of space under it" - a card of words stops a drop
// short of the dock; "the buttons load then go gray then reload" - an agent button drew as "nothing known" and flipped a beat later.
test("a task with a long draft opens at its top, Send in view, a gap under it, and its buttons draw once", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const fixture = (path, body = {}) => page.evaluate(async (p, b) => (await fetch(p, { method: "POST", body: JSON.stringify(b),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), path, body);
  const draft = Array.from({ length: 14 }, (_, i) => `Point ${i + 1}: Ray Colton signs the snag list on Thursday; the handover sheet says so.`).join("\n\n");
  const saved = await fixture("/api/fixture/task/chat-saved", { draft });
  assert.ok(saved.taskId, JSON.stringify(saved));

  for (const [width, height] of [[1440, 900], [1366, 768]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, saved.taskId);
    await page.waitForSelector(`[data-tq-task-page="${saved.taskId}"] [data-tq-work] textarea[data-tq-draft]`, { timeout: 20000 });
    await sleep(2200);   // past the lit move's 1.5s hold
    const m = await page.evaluate(() => {
      const work = document.querySelector("[data-tq-work]"), card = document.querySelector("[data-tq-canvas-item]");
      const body = card.closest(".tq-chat-body"), w = work.getBoundingClientRect();
      const send = [...work.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith("Send"));
      const first = work.firstElementChild.getBoundingClientRect();
      return { scroll: work.scrollTop, firstTop: first.top, workTop: w.top, workBottom: w.bottom, send: send?.getBoundingClientRect().bottom,
        gap: Math.round(body.getBoundingClientRect().bottom - card.getBoundingClientRect().bottom) };
    });
    assert.equal(m.scroll, 0, `${width}: the work column opens at its top ${JSON.stringify(m)}`);
    assert.ok(m.firstTop >= m.workTop, `${width}: its first row is whole ${JSON.stringify(m)}`);
    assert.ok(m.send && m.send <= m.workBottom, `${width}: Send is in view under the draft ${JSON.stringify(m)}`);
    assert.ok(m.gap >= 20, `${width}: a drop of space under the card ${JSON.stringify(m)}`);
  }

  // the agent's buttons draw once on a second task: never on, then off (or off, then on) as the agent list lands
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const other = tasks.find((x) => x.Source === "email" && x.Status === "open" && x.TaskId !== saved.taskId);
  assert.ok(other);
  await page.evaluate((id) => {
    window.__seen = {}; const t0 = performance.now();
    const tick = () => {
      for (const b of document.querySelectorAll("[data-tq-row] button")) {
        const k = b.textContent.trim();
        if (/agent/i.test(k)) (window.__seen[k] ||= []).at(-1) === b.disabled || window.__seen[k].push(b.disabled);
      }
      if (performance.now() - t0 < 4000) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    location.hash = `task=${id}`;
  }, other.TaskId);
  await sleep(4500);
  const seen = await page.evaluate(() => window.__seen);
  assert.ok(Object.keys(seen).length, "the row carries an agent button");
  for (const [label, states] of Object.entries(seen)) assert.equal(states.length, 1, `${label} drew once, not ${JSON.stringify(states)}`);
  assert.deepEqual(errors, []);
});
