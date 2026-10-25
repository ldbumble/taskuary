import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, findRow, sleep } from "./walkdriver.mjs";

/* THE OWNER'S OWN PRESS IS NOT "OFF" (the 2026-10-25 navigation sweep, N5): Send, Reply and Redraft grey the row's draft verbs while they
   run, and the Advisor's strip read that as the advised move being unavailable - "Drafting… is off - it cannot be pressed right now." for
   half a second over the Reply just pressed, "Redraft is off" for a frame after Send. Every frame of the strip is sampled across each press. */
test("the strip never says a move is off while the owner's own press runs", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t);
  const seen = [];
  for (const [row, act] of [[/Invoice 88213/, "card:^Send$"], [/Month-end close/, "reply"], [/resend the Q3/, "card:^Redraft$"]]) {
    await clickRow(page, await findRow(page, row)); await sleep(3000);
    await page.evaluate(() => { const t0 = performance.now(); window.__strip = [];
      const tick = () => { for (const e of document.querySelectorAll("[data-tq-advice] .tq-next-txt")) window.__strip.push(e.textContent);
        if (performance.now() - t0 < 3000) requestAnimationFrame(tick); }; tick(); });
    if (act.startsWith("card:")) assert.ok(await clickText(page, new RegExp(act.slice(5)), ".tq-canvas-live"), act); else assert.ok(await doVerb(page, act), act);
    await sleep(3200);
    seen.push(...(await page.evaluate(() => window.__strip)).filter((s) => / is off - /.test(s)).map((s) => `${row.source}: ${s}`));
  }
  assert.deepEqual([...new Set(seen)], [], "the strip said the move just pressed was off");
  assert.deepEqual(errors, []);
});
