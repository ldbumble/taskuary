import test from "node:test";
import { clickRow, look, matrix, next, ringAt, settle, sleep, start, verdict } from "./stresswalk.mjs";

/* A RAIL ROW CLICKED WHILE A NEXT IS OUT, AND NEXT WHILE A ROW CLICK IS OUT (the owner, 2026-11-02). The last thing pressed wins: a row clicked
   over a Next comes to rest on that row; Next pressed over a row click comes to rest on that row or the one below it - never back where the
   walk was, never anywhere else. Also a burst: five rows clicked 100 ms apart, the last one stays. LONG: run by name. */
const keyAt = async (page, i) => (await look(page)).rail[i]?.[1];

test("rail rows and Next pressed over each other", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, [
    { id: "row-over-next", run: async ({ page, why, record }) => {
      await start(page);
      const target = await keyAt(page, 20);
      await record(); await next(page); await sleep(100); await clickRow(page, target);
      const s = await settle(page);
      if (s.ring[0] !== target) why.push(`row 20 clicked over a Next, rested on row ${await ringAt(page)}`);
    } },
    { id: "next-over-row", run: async ({ page, why, record }) => {
      await start(page);
      const target = await keyAt(page, 30);
      await record(); await clickRow(page, target); await sleep(100); await next(page);
      await settle(page);
      const at = await ringAt(page);
      if (at !== 30 && at !== 31) why.push(`Next pressed over a click on row 30 rested on row ${at}`);
      return { metrics: { at } };
    } },
    { id: "five-rows", run: async ({ page, why, record }) => {
      await start(page);
      await record();
      for (const i of [10, 40, 5, 60, 25]) { await clickRow(page, await keyAt(page, i)); await sleep(100); }
      const want = await keyAt(page, 25), s = await settle(page);
      if (s.ring[0] !== want) why.push(`five rows clicked, rested on row ${await ringAt(page)} not row 25`);
    } },
    { id: "next-row-next", run: async ({ page, why, record }) => {
      await start(page);
      const target = await keyAt(page, 50);
      await record(); await next(page); await sleep(60); await clickRow(page, target); await sleep(60); await next(page);
      await settle(page);
      const at = await ringAt(page);
      if (at !== 50 && at !== 51) why.push(`Next, row 50, Next rested on row ${at}`);
      return { metrics: { at } };
    } },
  ]));
});
