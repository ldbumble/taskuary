import test from "node:test";
import { back, clickRow, look, matrix, next, ringAt, settle, sleep, start, verdict, walkChip } from "./stresswalk.mjs";

/* EVERY WALK BUTTON CLICKED TEN TIMES, QUICKLY (the owner, 2026-11-02: "clicking the walk-through buttons 10 times"). Next, Back, an FYI
   batch's "All read, next" (the row's Next under a batch) and Walk me through, each ten clicks 40 ms apart on the big world. The button greys
   while its move is out (one move at a time, 2026-11-03): a click on it then is no press, so the walk moves exactly once per click it took -
   once in all when the server is slow - and the table, the ring and the server agree.
   LONG: run by name. */
const ten = async (page, press) => { let n = 0; for (let i = 0; i < 10; i++) { if (await press(page)) n++; await sleep(40); } return n; };
// ...and once the server is slow, the first click's move is still out for the other nine: they are refused
const once = (why, delay, n, what) => { if (delay && n !== 1) why.push(`${what}: ${n} of ten clicks taken over a ${delay} ms move`); };

test("each walk button hammered ten times", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, [
    { id: "next-x10", run: async ({ page, why, record, delay }) => {
      await start(page); await next(page); await settle(page);
      const at0 = await ringAt(page);
      await record(); const n = await ten(page, next); await settle(page);
      const at1 = await ringAt(page);
      if (!n || at1 - at0 !== n) why.push(`ten Nexts took ${n} and moved ${at1 - at0} rows`);
      once(why, delay, n, "Next");
      return { metrics: { moved: at1 - at0, taken: n } };
    } },
    { id: "back-x10", run: async ({ page, why, record, delay }) => {
      await start(page); for (let i = 0; i < 6; i++) { await next(page); await settle(page); }
      const at0 = await ringAt(page);
      await record(); const n = await ten(page, back); await settle(page);
      const at1 = await ringAt(page);
      if (!n || at0 - at1 !== n) why.push(`ten Backs took ${n} and moved ${at0 - at1} rows up`);
      once(why, delay, n, "Back");
      return { metrics: { moved: at0 - at1, taken: n } };
    } },
    { id: "allread-x10", run: async ({ page, why, record, delay }) => {
      // the FYI heading walks its section from its first row, and Next from it brings a batch of four - its Next "All read, next"
      await page.evaluate(() => document.querySelector(`[data-tq-section-head="fyi"]`)?.click()); await settle(page);
      await next(page); await settle(page);
      const n0 = (await look(page)).heads.fyi;
      await record(); const n = await ten(page, next); await settle(page);
      const n1 = (await look(page)).heads.fyi || 0;
      // a batch is four: each press taken reads one batch
      if (n0 - n1 < 4 || n0 - n1 > 4 * n) why.push(`ten All read, next took ${n} and read ${n0 - n1} FYI (${n0} -> ${n1})`);
      once(why, delay, n, "All read, next");
      return { metrics: { read: n0 - n1, taken: n } };
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
