import assert from "node:assert/strict";
import test from "node:test";
import { bootMixed, clean, held, look, oneTable, pressBack, pressNext, shot, sleep, startWalk, still } from "./stress-mixed-lib.mjs";

/* MIXED USE 2 - EVERY PAGE, OVER AND OVER, WHILE A PRESS IS OUT (the owner, 2026-11-02: "no crazy stuff"). Next and Back are pressed in turn with every
   /api/ answer held 1500 ms, and while it is out the chat pop-up opens and shuts, Search everything (Ctrl K) opens and Escapes, and Settings,
   Reports, Connections, New, Hub, Board and back to Chat are each visited - 20 times round. Each cycle: the page answers within a frame budget,
   no card is drawn twice, back on Chat the table is the ringed row (never the stale one the press left), no console error. Over the 20 the
   listeners on window/document, the intervals and the DOM stay bounded - nothing piles up per visit. */
const STOPS = ["pop", "search", "settings", "reports", "connections", "new", "hub", "board", "chat"];
const go = (page, stop) => page.evaluate((stop) => {
  const q = (s) => document.querySelector(s), chat = () => { const sw = q("[data-tq-view-switch]"); if (sw?.getAttribute("data-tq-view-switch") !== "chat") q('[data-tq-view="chat"]')?.click(); };
  if (stop === "board") { q('[data-tq-view="board"]')?.click(); return true; }
  if (stop === "chat") { chat(); return true; }
  if (stop === "pop") { const p = q("[data-tq-chat-pop]"); if (p && !p.hidden) q("[data-tq-chat-pop] [aria-label='Close the chat']")?.click(); else q(".tq-compose-box textarea")?.click(); return true; }
  chat();
  const n = q(`[data-tq-nav="${stop}"]`); n?.click(); return !!n;
}, stop);

test("twenty rounds of every page while a Next is out keep the page answering, the table fresh and the listeners bounded", { timeout: 600000 }, async (t) => {
  const { page, errors } = await bootMixed(t, { width: 1440, height: 900, delay: 1500 });
  await startWalk(page);
  const marks = [], slow = [];
  for (let i = 0; i < 20; i++) {
    // Next then Back, round about: the table swings between the same two rows, so what one round holds is comparable with another
    if (i % 2) await pressBack(page); else await pressNext(page);
    for (const stop of STOPS) {
      if (stop === "search") { await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
        await page.waitForSelector("[data-tq-search] input", { timeout: 8000 }).catch(() => {}); await sleep(120); await page.keyboard.press("Escape"); }
      else assert.ok(await go(page, stop), `round ${i}: ${stop} is there to press`);
      // responsive: a frame answers within 600 ms while the press is out (the round trip from the test included; a first Hub draw on a busy box is ~350)
      const t0 = Date.now(); await page.evaluate(() => new Promise((r) => requestAnimationFrame(r))); const ms = Date.now() - t0;
      if (ms > 600) slow.push(`${i}:${stop}:${ms}`);
      if (stop === "new") { await sleep(200); await page.keyboard.press("Escape"); }
      await sleep(150);
      const s = await look(page);
      assert.equal(new Set(s.cards).size, s.cards.length, `round ${i} ${stop}: a card drawn twice ${JSON.stringify(s.cards)}`);
    }
    const s = await still(page, 30000);
    if (s.ring[0] && s.items[0] && s.ring[0] !== s.items[0]) await shot(page, `pages-stale-${i}`);
    oneTable(s, `round ${i} back on Chat`);
    clean(errors, `round ${i}`);
    marks.push(await held(page));
  }

  console.log("held per round", JSON.stringify(marks), "slow", slow);
  // bounded: the last six rounds hold no more than six early ones (three of each row) plus a little - growth per round is a leak
  const avg = (xs, k) => xs.reduce((a, x) => a + x[k], 0) / xs.length, early = marks.slice(2, 8), late = marks.slice(-6);
  // ...the page outside the chat: each Next and Back leaves its put-down line in the conversation on purpose (concierge.history - the chat
  // is the day's record until New chat), so the chat is held apart
  for (const m of marks) { m.page = m.nodes - m.chat; m.per = m.chat / Math.max(1, m.msgs); }
  for (const k of ["listeners", "intervals", "page"]) assert.ok(avg(late, k) <= avg(early, k) * 1.15 + 5, `${k} grew over 20 rounds: ${marks.map((m) => m[k]).join(",")}`);
  // ...and the chat grows by its lines alone: what one line costs stays the same - the pages visited leave nothing in it
  assert.ok(avg(late, "per") <= avg(early, "per") * 1.25 + 2, `each chat line grew: ${marks.map((m) => `${m.chat}/${m.msgs}`).join(",")}`);
  if (marks[0].heap != null) assert.ok(avg(late, "heap") <= avg(early, "heap") * 1.6 + 20, `JS heap grew: ${marks.map((m) => m.heap).join(",")}`);
  assert.deepEqual(slow, [], "frames held past 600 ms");
});
