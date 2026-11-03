import assert from "node:assert/strict";
import test from "node:test";
import { bootMixed, clean, look, noBlank, oneLine, oneTable, overlaps, pressNext, rowLook, settled, shot, sleep, startWalk, still } from "./stress-mixed-lib.mjs";

/* MIXED USE 3 - THE WINDOW RESIZED UNDER THE WALK AND UNDER AN OPEN TASK (the owner, 2026-11-02: "no crazy stuff"). The window goes
   1440x900, 1280x800, and back and forth between 1920x1080 and 900x700 - mid-walk (a Next out, held 300 ms) and with a task open in its three
   sections, side by side and full screen. At every size once it lands: the row on one line (folds into ▾, never Next or the lit move), no box
   drawn over another, the page never scrolls sideways, one ring and one table, no blank frame, no console error; and the FYI batch on the table
   is 6 on a big window and 4 on a small one (fyiBatch.js). Invented people (fixture chat-saved). */
const SIZES = [[1440, 900], [1280, 800], [1920, 1080], [900, 700], [1920, 1080], [900, 700], [1440, 900]];
const size = (page, [w, h]) => page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
const lit = (page) => page.$$eval("[data-tq-row] button.tq-ab.p", (bs) => bs.filter((b) => b.offsetParent).map((b) => b.textContent.trim()));

async function everySize(page, errors, where, { walk = true } = {}) {
  for (const sz of SIZES) {
    const before = await lit(page);
    await size(page, sz); await settled(page); await sleep(700);
    const at = `${where} @${sz.join("x")}`, rows = await rowLook(page);
    try {
      oneLine(rows, at);
      for (const r of rows) assert.ok(!before.length || before.every((b) => r.labels.includes(b)) || !r.labels.length, `${at}: the lit move folded ${JSON.stringify({ before, r })}`);
      if (walk) assert.ok(rows.some((r) => r.next) || !rows.length, `${at}: Next is not on the row ${JSON.stringify(rows)}`);
      assert.deepEqual(await overlaps(page), [], `${at}: a box drawn over another`);
      oneTable(await look(page), at);
      await noBlank(page, at); clean(errors, at);
    } catch (e) { await shot(page, `resize-${at.replace(/\W+/g, "_")}`); throw e; }
  }
}

test("the walk, resized mid-press and at rest, keeps one line, one table and nothing over anything", { timeout: 420000 }, async (t) => {
  const { page, errors } = await bootMixed(t, { width: 1440, height: 900, delay: 300 });
  await startWalk(page);
  await everySize(page, errors, "walk at rest");
  // ...mid-press: Next out, the window swung between big and small while it lands
  for (let i = 0; i < 4; i++) {
    await pressNext(page);
    await size(page, i % 2 ? [900, 700] : [1920, 1080]); await sleep(150); await size(page, i % 2 ? [1920, 1080] : [900, 700]);
    oneTable(await still(page), `Next ${i} resized mid-press`);
  }
  await everySize(page, errors, "walk after the presses");
});

test("the FYI batch on the table is 6 on a big window, and the next one 4 once it is made small", { timeout: 300000 }, async (t) => {
  const { page, errors } = await bootMixed(t, { width: 1920, height: 1080 });
  // Next down into FYI puts a batch up (railwalk._batch): the row above the band opened, then Next - a heading's press opens its first row alone
  const above = await page.evaluate(() => { const rows = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")];
    const i = rows.findIndex((r) => r.closest('[data-tq-run="fyi"]')); return i > 0 ? rows[i - 1].getAttribute("data-tq-key") : null; });
  assert.ok(above, "a row above the FYI band");
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`)?.click(), above); await still(page);
  // ...the Reports band may hold rows behind its "N more" (a fixed FYI band, 2026-11-02): Next on down until the ring stands under FYI
  const inFyi = () => page.evaluate(() => !!document.querySelector('[data-tq-run="fyi"] :is(.tq-pile-row.current, .tq-pile-row.inbatch)'));
  for (const [sz, n] of [[[1920, 1080], 6], [[900, 700], 4]]) {
    await size(page, sz); await sleep(500);
    await pressNext(page); await still(page);
    for (let i = 0; i < 8 && !(await inFyi()); i++) { await pressNext(page); await still(page); }
    const batch = await page.$$eval("[data-tq-rail] .tq-pile-row.inbatch, [data-tq-rail] .tq-pile-row.current", (e) => e.length);
    if (batch !== n) await shot(page, `fyi-batch-${sz.join("x")}`);
    assert.equal(batch, n, `${sz.join("x")}: the FYI batch is ${batch}, not ${n}`);
    // ...its Next whole on the bar: "All read" on the 900px bar the ask bar squeezes (the owner, 2026-11-03), "All read, next" with room
    const word = await page.$eval("[data-tq-row] [data-tq-next]", (b) => b.textContent.trim());
    assert.equal(word, sz[0] < 960 ? "All read" : "All read, next", `${sz.join("x")}: the batch's Next says ${word}`);
    try { oneLine(await rowLook(page), `fyi batch @${sz.join("x")}`); } catch (e) { await shot(page, `fyi-line-${sz.join("x")}`); throw e; }
    clean(errors, `fyi @${sz.join("x")}`);
  }
});

/* THE BAR IS BACK AND NEXT AT EVERY DESK WIDTH, THE STAGE MOVES ON THE SPINE (the owner, 2026-11-03: "stage moves belong on the task's spine,
   never on the bottom bar"). From 900 to ~1100 wide the rail and the canvas left a task under 760px and it stacked, its Mark done and Reply back
   on a bar of ~120-250px squeezed against the ask bar (found 2026-11-02, then a todo here). On a desk window the task keeps its three sections
   (TaskPage.useStackBelow), and so does a window from 601 up with no rail: Mark done on Close out's spine, the bar Back and Next alone and both whole, nothing over anything. */
const onTable = async (page, api, title) => {
  const t = (await api("/api/tasks")).data.find((x) => x.Title.startsWith(title));
  const key = await page.evaluate((title) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].find((r) => r.innerText.includes(title))?.getAttribute("data-tq-key"), title);
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`)?.click(), key);
  await still(page); return t;
};
const spineMoves = (page) => page.$$eval("[data-tq-spine-moves] button, [data-tq-pane-moves] button", (bs) => bs.filter((b) => b.offsetParent).map((b) => b.textContent.trim()));
test("the bar is Back and Next alone and the stage moves stay on the spine from 640 to 1440 wide", { timeout: 420000 }, async (t) => {
  const { page, errors, api } = await bootMixed(t, { width: 1440, height: 900 });
  await onTable(page, api, "New starter on Monday");
  // ...the 601-810 band with no rail too (the owner, 2026-11-03): only a phone (600 and under) keeps its stacked page and its own row
  for (const sz of [[900, 700], [640, 800], [760, 800], [810, 800], [1024, 768], [1100, 800], [1280, 800], [1440, 900], [900, 700]]) {
    await size(page, sz); await settled(page); await sleep(900);
    const rows = await rowLook(page), at = `New starter @${sz.join("x")}`, spine = await spineMoves(page);
    try {
      assert.ok(rows.some((r) => r.next), `${at}: Next is on the bar`);
      for (const r of rows) assert.deepEqual(r.labels.filter((l) => !["Back", "Next"].includes(l)), [], `${at}: a move on the bar ${JSON.stringify(r)}`);
      for (const r of rows) assert.deepEqual([...r.navCut, ...r.cut], [], `${at}: Back or Next cut off ${JSON.stringify(r)}`);
      assert.ok(spine.includes("Mark done"), `${at}: Mark done is not on the spine ${JSON.stringify(spine)}`);
      assert.deepEqual(await overlaps(page), [], `${at}: a box drawn over another`);
      clean(errors, at);
    } catch (e) { await shot(page, `spine-${sz.join("x")}`); throw e; }
  }
});

for (const mode of ["three", "pair", "full"]) {
  test(`an open task in ${mode} survives the window swinging between sizes`, { timeout: 360000 }, async (t) => {
    const { page, errors, api } = await bootMixed(t, { width: 1440, height: 900 });
    const id = (await api("/api/fixture/task/chat-saved", {})).taskId;
    const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
    await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 }); await sleep(1500);
    if (mode === "pair") {
      const tog = await page.$(`${CUR} [data-tq-strip-pair]`);
      assert.ok(tog, "a side-by-side toggle on the open strip");
      await tog.click(); await sleep(800);
    }
    if (mode === "full") { await page.click(`${CUR} [data-tq-expand]`); await sleep(800); }
    await everySize(page, errors, `task ${mode}`, { walk: false });
    // ...and each open slot keeps its region inside it
    const fits = await page.evaluate((CUR) => [...document.querySelectorAll(`${CUR} [data-tq-slot][data-tq-open]`)].every((s) => {
      const r = s.querySelector(":scope > [role=region]")?.getBoundingClientRect(), o = s.getBoundingClientRect(); return !r || r.right <= o.right + 2; }), CUR);
    assert.ok(fits, `${mode}: an open section runs past its slot`);
  });
}
