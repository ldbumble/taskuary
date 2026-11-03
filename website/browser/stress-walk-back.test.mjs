import test from "node:test";
import { back, frames, look, matrix, next, presses, ringAt, settle, sleep, start, stopRecord, verdict } from "./stresswalk.mjs";

/* NEXT AND BACK, QUICKLY, ONE AFTER THE OTHER (the owner, 2026-11-02: "hitting Next then Back quickly"). On the big world, five rows down:
   N,B twenty times at 150 ms - where it comes to rest is where it started, or one row either side while a press was held; N,N,B,B,N six
   times; then Back to the top until it greys. Every frame recorded; settled, the ring, the card and the server's walk agree. LONG: run by name. */
const down = async (page, n) => { for (let i = 0; i < n; i++) { await next(page); await settle(page); } };

test("Next and Back alternated fast, then Back to the top", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, [
    { id: "NB-x20", run: async ({ page, why, record }) => {
      await start(page); await down(page, 5);
      const at0 = await ringAt(page);
      await record(); await presses(page, "NB".repeat(20), 150); await settle(page);
      const at1 = await ringAt(page);
      if (Math.abs(at1 - at0) > 1) why.push(`N,B x20 came to rest ${at1 - at0} rows from where it started`);
      return { metrics: { moved: at1 - at0 } };
    } },
    { id: "NNBBN-x6", run: async ({ page, why, record }) => {
      await start(page); await down(page, 3);
      const at0 = await ringAt(page);
      await record(); await presses(page, "NNBBN".repeat(6), 150); await settle(page);
      const at1 = await ringAt(page);
      // each round is one row down when every press runs; a press held over another can fold two into one - never up, never past six
      if (at1 < at0 || at1 - at0 > 6) why.push(`N,N,B,B,N x6 came to rest ${at1 - at0} rows down`);
      return { metrics: { moved: at1 - at0 } };
    } },
    { id: "back-to-top", run: async ({ page, why, record }) => {
      await start(page); await down(page, 8);
      await record();
      let n = 0;
      for (let i = 0; i < 40; i++) { if (await back(page)) n++; await sleep(150); }
      const s = await settle(page);
      if (s.ring[0] !== s.rail[0]?.[1]) why.push(`Back to the top rested on row ${await ringAt(page)}`);
      if (s.back) why.push("Back is still on at the top");
      return { metrics: { backs: n } };
    } },
  ]));
});
