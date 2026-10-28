import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, pressNext, sleep } from "./walkdriver.mjs";

/* A REPORT AND AN FYI COME IN A TASK'S THREE SECTIONS (the owner, 2026-10-28: "even reports should come in with the 3 sections of came in-close
   out but they should be small on the side like active agent. Want this to be consistent across. even fyi ... opening on what came in all
   together"). On the demo world: a report opens on the Report, Came from and Close out the slim 44px tabs a live agent leaves; an FYI and a
   batch of them open on Came from - every message of the batch at once, each with who, when and its own words - Agent and Close out slim.
   The card is a task's height, a tab opens its section without moving it, and the row under the chat is the same row: nothing new to press. */
const look = (page) => page.evaluate(() => {
  const it = document.querySelector("[data-tq-item-sections]"), cv = document.querySelector(".tq-chat-body");
  if (!it) return null;
  const box = (e) => e && (({ top, width, height }) => ({ top: Math.round(top), w: Math.round(width), h: Math.round(height) }))(e.getBoundingClientRect());
  const vis = (e) => !!e && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility === "visible";
  return { kind: it.dataset.tqItemSections, main: it.querySelector("[data-tq-sections]").dataset.tqMain, card: box(it), canvas: box(cv),
    head: it.querySelector("[data-tq-item-head]")?.innerText.replace(/\s+/g, " ").trim(),
    slots: [...it.querySelectorAll("[data-tq-slot]")].map((s) => ({ key: s.dataset.tqSlot, open: s.hasAttribute("data-tq-open"), w: box(s).w,
      mini: !!s.querySelector(":scope > [data-tq-section-tab][data-tq-mini]"), tab: !!s.querySelector(":scope > [data-tq-section-tab]") })),
    open: [...it.querySelectorAll("[data-tq-slot] > [role=region]")].filter(vis).map((e) => e.getAttribute("aria-label")),
    msgs: [...it.querySelectorAll("[data-tq-fyi-msg]")].filter((e) => vis(e.closest("[role=region]"))).map((e) => ({
      who: e.querySelector(".tq-item-msg-h b")?.textContent || "", at: e.querySelector(".tq-item-msg-h .at")?.textContent || "",
      words: (e.querySelector(".tq-card-full, .tq-thr-words")?.innerText || "").trim() })),
    row: [...document.querySelectorAll("[data-tq-row] button")].filter((b) => b.getBoundingClientRect().width > 0).map((b) => b.textContent.trim()).filter(Boolean) };
});
const tab = (page, key) => page.evaluate((k) => document.querySelector(`[data-tq-item-sections] [data-tq-section-tab="${k}"]`)?.click(), key);
const settled = async (page, kind) => { await page.waitForSelector(`[data-tq-item-sections="${kind}"]`, { timeout: 20000 }); await sleep(1500); return look(page); };
// the walk to the first FYI batch, the way fyi-count-between-batches gets there: the last report, then Next
const toBatch = async (page) => {
  await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold').click()); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await pressNext(page);
  return settled(page, "fyis");
};

test("a report opens on itself between slim Came from and Close out tabs, a task's height, on the same row", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  assert.ok(await clickRow(page, await findRow(page, /Headcount by site/)));
  const m = await settled(page, "report");
  assert.equal(m.main, "report", JSON.stringify(m));
  assert.deepEqual(m.slots.map((s) => s.key), ["from", "report", "close"], "the flow's order");
  assert.deepEqual(m.slots.map((s) => [s.open, s.mini, s.w]), [[false, true, 44], [true, false, m.slots[1].w], [false, true, 44]], JSON.stringify(m.slots));
  assert.ok(m.slots[1].w > 800, `the report keeps nearly all the width: ${m.slots[1].w}`);
  assert.match(m.head, /^Report Headcount by site, nightly · Today - 5 rows/, m.head);
  assert.ok(Math.abs(m.card.top - m.canvas.top) <= 2, `pinned to the canvas's top ${JSON.stringify(m)}`);
  assert.ok(m.card.h >= m.canvas.h - 30, `a task's height: ${m.card.h} of ${m.canvas.h}`);
  // ...its table and its chart, as on its card
  assert.equal(await page.$$eval("[data-tq-report-body] [data-tq-report-table] tbody tr", (r) => r.length), 5);
  assert.ok(await page.$("[data-tq-report-body] [data-tq-report-chart]"), "its chart is there");
  // ...and the row is the report's own: Next, its moves, Share
  for (const w of ["Next", "Put it on my list", "Pause this report", "Share"]) assert.ok(m.row.includes(w), `${w} on the row: ${m.row}`);

  // Came from opens on press - what produced it - and the report folds to its full tab; the card never moves
  await tab(page, "from"); await sleep(600);
  const f = await look(page);
  assert.equal(f.main, "from");
  assert.deepEqual(f.open, ["Came from"]);
  assert.deepEqual(f.slots.map((s) => [s.key, s.mini, s.w]).filter(([, mini]) => !mini).map(([k, , w]) => [k, w]).find(([k]) => k === "report"), ["report", 156]);
  assert.deepEqual([f.card.top, f.card.h], [m.card.top, m.card.h], "one height through a switch");
  const from = await page.$eval("[data-tq-report-from]", (e) => e.innerText);
  assert.match(from, /Report\s+Headcount by site, nightly[\s\S]*Ran\s+\S[\s\S]*Runs\s+\S[\s\S]*Edit this report/, from);
  // ...Close out says what happens next, in the row's own words - nothing to press in it that the row does not have
  await tab(page, "close"); await sleep(600);
  assert.equal((await look(page)).main, "close");
  const close = await page.$eval("[data-tq-report-close] [data-tq-row-moves]", (e) => e.innerText);
  assert.match(close, /Put it on my list[\s\S]*Pause this report[\s\S]*Next/, close);
  assert.equal(await page.$$eval("[data-tq-report-close] button", (b) => b.length), 0, "no buttons of its own");
  await tab(page, "report"); await sleep(600);
  assert.equal((await look(page)).main, "report");
  // Next still walks on
  assert.ok(await pressNext(page)); await sleep(3500);
  assert.notEqual((await look(page))?.head, m.head, "Next put the report down");
  assert.deepEqual(errors, []);
});

test("an FYI opens on what came in: one message, or a batch's all together, Agent and Close out slim", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  assert.ok(await clickRow(page, await findRow(page, /Regional operations newsletter/)));
  const one = await settled(page, "fyi");
  assert.equal(one.main, "from");
  assert.deepEqual(one.slots.map((s) => [s.key, s.open, s.mini]), [["from", true, false], ["agent", false, true], ["close", false, true]]);
  assert.deepEqual(one.slots.filter((s) => s.mini).map((s) => s.w), [44, 44]);
  assert.equal(one.msgs.length, 1);
  assert.equal(one.msgs[0].who, "Priya Shah");
  assert.ok(one.msgs[0].at && /Sharing for visibility/.test(one.msgs[0].words), JSON.stringify(one.msgs));
  assert.ok(one.row.includes("Next"), one.row);
  // the Agent tab opens on press and says nobody is on it
  await tab(page, "agent"); await sleep(600);
  assert.equal((await look(page)).main, "agent");
  assert.match(await page.$eval("[data-tq-fyi-agent]", (e) => e.innerText), /No agent yet[\s\S]*Nobody is working on this/);

  const b = await toBatch(page);
  const n = Number((b.head.match(/(\d+) messages/) || [])[1]);
  assert.ok(n >= 2, b.head);
  assert.equal(b.main, "from");
  assert.equal(b.msgs.length, n, "every message of the batch, together");
  for (const x of b.msgs) assert.ok(x.who && x.at && x.words, `who, when and its own words: ${JSON.stringify(x)}`);
  assert.ok(b.row.includes("All read, next"), `the batch's way on is still the row's: ${b.row}`);
  assert.ok(b.card.h >= b.canvas.h - 30, `a task's height: ${b.card.h} of ${b.canvas.h}`);
  // a message's line opens its own moves under it, as on the batch's card
  await page.evaluate(() => document.querySelector("[data-tq-item-sections] [data-tq-fyi-msg] .tq-item-msg-h.press").click()); await sleep(400);
  assert.ok(await page.$("[data-tq-item-sections] [data-tq-fyi-msg][data-tq-open] .tq-fyi-acts button"), "its moves opened under it");
  // ...and All read, next still settles the handful and walks on
  const was = b.msgs.map((x) => x.words).join("|");
  assert.ok(await pressNext(page)); await sleep(4000);
  const after = await look(page);
  assert.notEqual(after?.msgs.map((x) => x.words).join("|"), was, "All read, next moved on");
  assert.deepEqual(errors, []);
});

test("on a phone the same three sections: the open one has the room, the slim tabs at its sides", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 390, height: 844 });
  assert.ok(await clickRow(page, await findRow(page, /Headcount by site/)));
  const r = await settled(page, "report");
  assert.deepEqual(r.slots.map((s) => [s.key, s.open, s.w === 44]), [["from", false, true], ["report", true, false], ["close", false, true]]);
  assert.ok(r.slots[1].w >= 240, `the report has the room: ${r.slots[1].w}`);
  const b = await toBatch(page);
  assert.equal(b.main, "from");
  assert.deepEqual(b.slots.filter((s) => !s.open).map((s) => s.w), [44, 44]);
  assert.ok(b.msgs.length >= 2 && b.msgs.every((x) => x.who && x.words), JSON.stringify(b.msgs));
  assert.deepEqual(errors, []);
});
