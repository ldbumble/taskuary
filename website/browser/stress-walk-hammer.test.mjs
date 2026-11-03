import test from "node:test";
import { back, clickRow, look, matrix, next, ringAt, settle, sleep, start, verdict, walkChip } from "./stresswalk.mjs";

/* EVERY WALK BUTTON CLICKED TEN TIMES, QUICKLY (the owner, 2026-11-02: "clicking the walk-through buttons 10 times"). Next, Back, an FYI
   batch's "All read, next" (the row's Next under a batch) and Walk me through, each ten clicks 40 ms apart on the big world. A press held over
   a move in flight is one press more, never ten: the walk comes to rest at most two steps on, and the table, the ring and the server agree.
   LONG: run by name. */
const ten = async (page, press) => { for (let i = 0; i < 10; i++) { await press(page); await sleep(40); } };

test("each walk button hammered ten times", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, [
    { id: "next-x10", run: async ({ page, why, record }) => {
      await start(page); await next(page); await settle(page);
      const at0 = await ringAt(page);
      await record(); await ten(page, next); await settle(page);
      const at1 = await ringAt(page);
      if (at1 - at0 < 1 || at1 - at0 > 2) why.push(`ten Nexts moved ${at1 - at0} rows`);
      return { metrics: { moved: at1 - at0 } };
    } },
    { id: "back-x10", run: async ({ page, why, record }) => {
      await start(page); for (let i = 0; i < 6; i++) { await next(page); await settle(page); }
      const at0 = await ringAt(page);
      await record(); await ten(page, back); await settle(page);
      const at1 = await ringAt(page);
      if (at0 - at1 < 1 || at0 - at1 > 2) why.push(`ten Backs moved ${at0 - at1} rows up`);
      return { metrics: { moved: at0 - at1 } };
    } },
    { id: "allread-x10", run: async ({ page, why, record }) => {
      // the FYI heading walks its section: a batch of four on the table, its Next "All read, next"
      await page.evaluate(() => document.querySelector(`[data-tq-section-head="fyi"]`)?.click()); await settle(page);
      const n0 = (await look(page)).heads.fyi;
      await record(); await ten(page, next); await settle(page);
      const n1 = (await look(page)).heads.fyi || 0;
      // a batch is four: one press reads one batch, one held over it at most one more
      if (n0 - n1 < 4 || n0 - n1 > 8) why.push(`ten All read, next read ${n0 - n1} FYI (${n0} -> ${n1})`);
      return { metrics: { read: n0 - n1 } };
    } },
    { id: "walk-x10", run: async ({ page, why, record }) => {
      await record();
      for (let i = 0; i < 10; i++) { await walkChip(page); await sleep(40); }
      const s = await settle(page);
      if (s.ring[0] !== s.rail[0]?.[1]) why.push(`ten Walk me through rested on row ${await ringAt(page)}, not the top`);
      const opens = s.lines.filter((l) => /^Good (morning|afternoon|evening)/.test(l)).length;
      if (opens > 1) why.push(`${opens} greetings`);
      return { refolds: 0 };
    } },
  ]));
});
