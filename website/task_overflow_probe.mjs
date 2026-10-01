// THE TASK VIEW NEVER DRAWS PAST ITS OWN BOX (the owner, 2026-10-01: "check the issue with task view if it can draw on top of it next
// message. That should never happen"). Opens every task of a `taskuary --demo` server on the canvas, at a tall and a short window,
// and measures: does any descendant of the task view paint below the view's own box, and does the next line of the chat start
// inside it. Prints one line per task and size; exits 1 on any overlap.
//   node website/task_overflow_probe.mjs http://127.0.0.1:7996 <token>
import { launch } from "./browser.mjs";

const [base, token] = process.argv.slice(2);
if (!base || !token) { console.error("usage: task_overflow_probe.mjs <base-url> <token>"); process.exit(2); }
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const tasks = await (await fetch(`${base}/api/tasks`, { headers: { "X-Taskuary-Token": token } })).json();
const ids = (tasks.data || tasks || []).map((t) => t.TaskId).filter(Boolean).slice(0, 40);
const browser = await launch();
let bad = 0;
for (const [w, h] of (process.env.SIZES ? JSON.parse(process.env.SIZES) : [[1440, 900], [1440, 560], [1280, 480], [390, 844]])) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  await page.goto(`${base}/?token=${token}`, { waitUntil: "networkidle2" });
  await wait(1500);
  for (const id of ids) {
    await page.evaluate((tid) => { location.hash = `#task=${tid}`; }, id);
    await wait(1800);
    const m = await page.evaluate(() => {
      const view = [...document.querySelectorAll("[data-tq-canvas-item]")].pop();
      if (!view) return null;
      const box = view.getBoundingClientRect();
      // the deepest point anything inside the view paints at, ignoring what is clipped by a scroller inside it
      let deepest = box.bottom;
      for (const el of view.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        let clipped = false;
        for (let p = el.parentElement; p && p !== view.parentElement; p = p.parentElement) {
          const o = getComputedStyle(p);
          if (/(auto|scroll|hidden|clip)/.test(o.overflowY) && p.getBoundingClientRect().bottom < r.bottom) { clipped = true; break; }
        }
        if (!clipped) deepest = Math.max(deepest, r.bottom);
      }
      // the next thing drawn in the chat after the view's own line
      const line = view.closest(".tq-canvas-live, .tq-msg") || view;
      let next = line.nextElementSibling;
      while (next && !next.getBoundingClientRect().height) next = next.nextElementSibling;
      const nextTop = next ? next.getBoundingClientRect().top : null;
      return { boxBottom: Math.round(box.bottom), deepest: Math.round(deepest), nextTop: nextTop == null ? null : Math.round(nextTop) };
    });
    if (!m) { console.log(`${w}x${h} task ${id}: no view`); continue; }
    const spill = m.deepest - m.boxBottom, under = m.nextTop == null ? 0 : m.boxBottom - m.nextTop;
    const ok = spill <= 1 && under <= 1;
    if (!ok) bad += 1;
    console.log(`${w}x${h} task ${id}: box ends ${m.boxBottom}, content ends ${m.deepest} (spill ${spill}), next line at ${m.nextTop} ${ok ? "ok" : "OVERLAP"}`);
  }
  await page.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
