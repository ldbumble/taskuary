import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, findRow, pressNext, sleep, type } from "./walkdriver.mjs";

/* WHAT A PRESS LEFT NEVER COMES BACK (the owner, 2026-10-25: "one code that's it and it should work seamless"): an item pressed past or closed
   returns to the table only when its row is clicked. A done task bounced back over the agent row Next had brought, Mark done on the last task
   walked up to the goal above it, Put it on my list put the report back up as its task. Every press kind, every frame: the canvas's live item
   is recorded from the press on, and once the item the press left is gone it must not be drawn live again. And it stays instant (the owner,
   same day: "make sure next, mark done still feel instant"): press to the next card on the canvas, measured for each. */
// what is on the table, as drawn: the task view on the canvas, else the row the rail rings (a report, an fyi)
const NOW = () => [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0)
  .map((x) => x.getAttribute("data-tq-canvas-item")).pop() || document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "";
const live = (page) => page.evaluate(`(${NOW})()`);
const watchCanvas = (page) => page.evaluate((now) => {
  window.__k = []; window.__pressAt = null; let last = null; const t0 = window.__t0 = performance.now(), read = new Function(`return (${now})()`);
  const tick = () => {
    const v = read();
    if (v !== last) { last = v; window.__k.push([Math.round(performance.now() - t0), v]); }
    if (performance.now() - t0 < 9000) requestAnimationFrame(tick);
  }; tick();
}, NOW.toString());
const PRESSES = {
  "Next": { row: /Year-end audit/, press: (page) => pressNext(page) },
  "Mark done": { row: /Year-end audit/, press: (page) => doVerb(page, "done") },
  "Remind me": { row: /Year-end audit/, press: async (page) => (await doVerb(page, "remind")) && (await sleep(600), await clickText(page, /^Tomorrow/)) },
  "Close with a note": { row: /New starter/, press: async (page) => { await doVerb(page, "close-note"); await sleep(800); await page.keyboard.type("Sorted on the phone");
    return clickText(page, /^Close with a note$/, "[data-tq-close-note-card]"); } },
  "Put it on my list": { row: /Headcount by site/, press: (page) => doVerb(page, "w:mine") },
  "Next on the last task": { row: /schema sign-off/, press: (page) => pressNext(page) },
  "Mark done on the last task": { row: /schema sign-off/, press: (page) => doVerb(page, "done") },
  // ...and a closed task opened again by its ref, then Next: the done task that bounced back
  "Next from a closed task": { row: /Year-end audit/, before: async (page) => { await doVerb(page, "done"); await sleep(5000); await type(page, "open TQ-0011"); await sleep(7000); },
    press: (page) => pressNext(page) },
};
const timings = {}, INSTANT = new Set(["Next", "Mark done", "Next on the last task", "Next from a closed task"]);
for (const [name, p] of Object.entries(PRESSES)) {
  test(`${name}: what it left is never drawn again`, { timeout: 180000 }, async (t) => {
    const { page, errors } = await boot(t);
    await clickRow(page, await findRow(page, p.row)); await sleep(3500);
    if (p.before) await p.before(page);
    const left = await live(page);
    assert.ok(left, "nothing was on the table to press on");
    await watchCanvas(page);
    assert.ok(await p.press(page), `${name} could not be pressed`);
    await sleep(9200);
    const frames = await page.evaluate(() => window.__k);
    const gone = frames.findIndex(([, k]) => k !== left), back = gone < 0 ? [] : frames.slice(gone).filter(([, k]) => k === left);
    // ...timed from the click that pressed (doVerb's __pressAt): the one-row chat bar leaves a 1440 px row room to fold Mark done behind
    // a ▾, and the driver opening the ▾s to find it (400 ms a menu, ~1.1 s here) is not the press
    const at = await page.evaluate(() => (window.__pressAt == null ? 0 : Math.round(window.__pressAt - window.__t0)));
    const next = frames.map(([ms, k]) => [ms - at, k]).find(([, k]) => k && k !== left);
    timings[name] = next ? next[0] : null;
    console.log(`${name}: press to the next card ${next ? `${next[0]} ms` : "(none)"}`);
    assert.deepEqual(back, [], `${name} drew the item it left again: ${JSON.stringify(frames)}`);
    // ...and the presses that draw the next item at once still do (INSTANT NEXT, owner-approved 2026-10-20): ~100-250 ms here before and after
    if (INSTANT.has(name)) assert.ok(next && next[0] <= 600, `${name} took ${next?.[0]} ms to draw the next card`);
    assert.deepEqual(errors, []);
  });
}
test.after(() => console.log(`press to next card (ms): ${JSON.stringify(timings)}`));
