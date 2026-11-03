import test from "node:test";
import { back, frames, look, matrix, next, presses, ringAt, settle, sleep, start, stopRecord, verdict } from "./stresswalk.mjs";

/* NEXT AND BACK, QUICKLY, ONE AFTER THE OTHER (the owner, 2026-11-02: "hitting Next then Back quickly"). On the big world, five rows down:
   N,B twenty times at 150 ms and N,N,B,B,N six times - a button greyed while a move is out takes no press (one move at a time, 2026-11-03),
   so where it comes to rest is exactly the Nexts taken less the Backs taken; then Back every 150 ms to the top, where it greys. Every frame recorded; settled, the ring, the card and the server's walk agree. LONG: run by name. */
const down = async (page, n) => { for (let i = 0; i < n; i++) { await next(page); await settle(page); } };

test("Next and Back alternated fast, then Back to the top", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, [
    { id: "NB-x20", run: async ({ page, why, record }) => {
      await start(page); await down(page, 5);
      const at0 = await ringAt(page);
      await record(); const n = await presses(page, "NB".repeat(20), 150); await settle(page);
      const at1 = await ringAt(page);
      if (at1 - at0 !== n.N - n.B) why.push(`N,B x20 took ${n.N} Nexts and ${n.B} Backs and came to rest ${at1 - at0} rows on`);
      return { metrics: { moved: at1 - at0, taken: n } };
    } },
    { id: "NNBBN-x6", run: async ({ page, why, record }) => {
      await start(page); await down(page, 3);
      const at0 = await ringAt(page);
      await record(); const n = await presses(page, "NNBBN".repeat(6), 150); await settle(page);
      const at1 = await ringAt(page);
      if (at1 - at0 !== n.N - n.B) why.push(`N,N,B,B,N x6 took ${n.N} Nexts and ${n.B} Backs and came to rest ${at1 - at0} rows on`);
      return { metrics: { moved: at1 - at0, taken: n } };
    } },
    { id: "back-to-top", run: async ({ page, why, record }) => {
      await start(page); await down(page, 8);
      await record();
      let n = 0;
      // ...pressed every 150 ms until the top: the walk goes up as fast as its moves answer, greyed between
      for (const t0 = Date.now(); Date.now() - t0 < 45000 && (await ringAt(page)) > 0; ) { if (await back(page)) n++; await sleep(150); }
      const s = await settle(page);
      if (s.ring[0] !== s.rail[0]?.[1]) why.push(`Back to the top rested on row ${await ringAt(page)}`);
      if (s.back) why.push("Back is still on at the top");
      return { metrics: { backs: n } };
    } },
  ]));
});
