import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A SEARCHED TASK OPENS AS ITS RAIL ROW DOES (the owner, 2026-11-18: "when you click on searched tasks its so buggy especially when you are on
   another task. it does nothing then moves to new one slowly ... and then the walk highlight disappears"). Task A on the table, its row lit;
   Ctrl+K, a word of task B, B's hit clicked. Watched every frame from the click: B's head is drawn and the box gone at once, never A standing
   under a shut box for a round trip; the rail's light moves to B's row, and a closed task (on no row) puts it out cleanly. Invented people. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "search-open");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FRAME = 120;   // one frame budget past a rail row's own click: a draw at the press, never a round trip

// every frame from the click: the box, the task drawn last on the canvas, the rail's lit row
const watch = (page) => page.evaluate(() => {
  const read = () => {
    const pages = [...document.querySelectorAll("[data-tq-canvas-item] [data-tq-task-page]")].filter((e) => e.getBoundingClientRect().height > 0);
    return { box: [...document.querySelectorAll("[data-tq-search] [role=dialog]")].some((e) => getComputedStyle(e).visibility !== "hidden" && e.getBoundingClientRect().height > 0),
      task: pages.at(-1)?.getAttribute("data-tq-task-page") || "",
      lit: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => e.getAttribute("data-tq-key")).join(",") };
  };
  const w = { t0: performance.now(), seen: [] }; let last = "";
  const tick = () => { const v = read(), s = JSON.stringify(v); if (s !== last) { w.seen.push({ at: Math.round(performance.now() - w.t0), ...v }); last = s; } w.raf = requestAnimationFrame(tick); };
  tick(); window.__tqSearch = w;
});
const seen = (page) => page.evaluate(() => { const w = window.__tqSearch; cancelAnimationFrame(w.raf); return w.seen; });

async function searchClick(page, word, tid) {
  await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
  await page.waitForSelector("[data-tq-search] input", { visible: true, timeout: 10000 });
  await page.keyboard.type(word);
  const hit = `[data-tq-search-hit="task:${tid}"]`;
  await page.waitForSelector(hit, { visible: true, timeout: 15000 });
  await sleep(600);   // the hit highlighted and read ahead, as a person's pointer reaches it
  const at = await page.evaluate((s) => { const q = document.querySelector(s).getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, hit);
  await watch(page);
  await page.mouse.click(at.x, at.y);
  await sleep(4000);
  return seen(page);
}

test("a searched task opens at the click, over the task on the table, and the walk's light follows it", { timeout: 300000 }, async (t) => {
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  const a = await api("/api/fixture/mail-task", { title: "Quarterly figures for Gail", sent: "2026-11-10 08:00:00" });
  const b = await api("/api/fixture/mail-task", { title: "Pelican budget from Ray", sent: "2026-11-10 08:05:00" });
  const c = await api("/api/fixture/mail-task", { title: "Heron contract for Omar", sent: "2026-11-10 08:10:00" });
  await api(`/api/tasks/${c.taskId}`, { Status: "done" }, "PATCH");
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const row = async (tid) => page.evaluate((n) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")]
    .find((e) => e.querySelector(`[data-tq-tid="${n}"]`) || new RegExp(`:${n}$`).test(e.getAttribute("data-tq-key")))?.getAttribute("data-tq-key") || null, tid);
  await page.waitForSelector("[data-tq-rail] .tq-pile-row[data-tq-key]", { timeout: 60000 });
  await sleep(1500);
  const keyB = (await api("/api/funnel/pile")).items?.find((i) => Number(i.tid) === b.taskId)?.key;
  const keyA = (await api("/api/funnel/pile")).items?.find((i) => Number(i.tid) === a.taskId)?.key;
  assert.ok(keyA && keyB, "A and B are on the rail");
  const dir = path.join(out, process.env.SEARCH_OPEN_NAME || "after"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir), runs = {}, bad = [];
  try {
    // A on the table by its own row, lit - the row click's own time to draw is the yardstick
    await watch(page);
    await page.click(`[data-tq-rail] .tq-pile-row[data-tq-key="${keyA}"]`);
    await page.waitForFunction((k) => document.querySelector(`[data-tq-rail] .tq-pile-row.current[data-tq-key="${k}"]`), { timeout: 15000 }, keyA);
    await sleep(1500);
    runs.row = await seen(page);
    const rowAt = runs.row.find((s) => s.task === String(a.taskId))?.at ?? 0, budget = rowAt + FRAME;
    // ...B, an open task on the rail, found by a word of its title
    runs.open = await searchClick(page, "pelican", b.taskId);
    const drawn = runs.open.find((s) => s.task === String(b.taskId));
    const shut = runs.open.find((s) => !s.box);
    if (!drawn || drawn.at > budget) bad.push(`open B: its head drew ${drawn ? `${drawn.at} ms` : "never"} after the click, a row click ${rowAt} ms`);
    if (!shut || !drawn || shut.at > drawn.at) bad.push(`open B: the box shut ${shut ? `${shut.at} ms` : "never"} after the click, B drawn at ${drawn?.at} ms`);
    const end = runs.open.at(-1);
    if (end.lit !== keyB) bad.push(`open B: the walk's light ended on "${end.lit}", not B's row ${keyB}`);
    if (runs.open.some((s) => s.at > 0 && !s.lit)) bad.push(`open B: the walk's light went out on the way (${JSON.stringify(runs.open)})`);
    // ...C, a closed task, on no row: it opens as it is and no row stays lit for A
    runs.closed = await searchClick(page, "heron", c.taskId);
    const drawnC = runs.closed.find((s) => s.task === String(c.taskId));
    if (!drawnC || drawnC.at > 1500) bad.push(`closed C: its head drew ${drawnC ? `${drawnC.at} ms` : "never"} after the click`);
    if (runs.closed.at(-1).lit && runs.closed.at(-1).lit !== (await row(c.taskId))) bad.push(`closed C: the light stayed on "${runs.closed.at(-1).lit}"`);
  } finally {
    await rec.stop();
    await writeFile(path.join(dir, "seen.json"), JSON.stringify(runs, null, 1));
    await note(dir, { done: "Three mail tasks; A opened by its rail row; Ctrl+K, 'pelican', B's hit clicked; then 'heron', closed C's hit clicked.",
      expect: "B's head and the shut box in the first frames after the click, B's row lit; C drawn, no row left lit for another task.",
      saw: bad.length ? bad.join("\n") : "as expected", verdict: bad.length ? "FAIL" : "PASS" });
  }
  console.log(`# ${JSON.stringify(runs)}`);
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});
