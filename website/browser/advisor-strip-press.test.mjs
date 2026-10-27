import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, findRow, sleep } from "./walkdriver.mjs";

/* THE OWNER'S OWN PRESS IS NOT "OFF" (the 2026-10-25 navigation sweep, N5): Send, Reply and Redraft grey the row's draft verbs while they
   run, and the Advisor's strip read that as the advised move being unavailable - "Drafting… is off - it cannot be pressed right now." for
   half a second over the Reply just pressed. Since 2026-10-26 there is no strip at all (the owner: "remove the advisor"): every frame
   across each press is sampled, and nothing is said over the row - no line, no "is off" - anywhere on the page. */
test("nothing is said over the row while the owner's own press runs - no strip, no 'is off'", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t);
  const seen = [];
  for (const [row, act] of [[/Invoice 88213/, "card:^Send$"], [/Month-end close/, "reply"], [/resend the Q3/, "card:^Redraft$"]]) {
    await clickRow(page, await findRow(page, row)); await sleep(3000);
    await page.evaluate(() => { const t0 = performance.now(); window.__strip = [];
      const tick = () => { for (const e of document.querySelectorAll(".tq-dock .tq-next-txt, [data-tq-strip], [data-tq-advice] .tq-next-txt")) window.__strip.push(e.textContent || "(strip)");
        if (/ is off - /.test(document.body.innerText)) window.__strip.push("is off");
        if (performance.now() - t0 < 3000) requestAnimationFrame(tick); }; tick(); });
    if (act.startsWith("card:")) assert.ok(await clickText(page, new RegExp(act.slice(5)), ".tq-canvas-live"), act); else assert.ok(await doVerb(page, act), act);
    await sleep(3200);
    seen.push(...(await page.evaluate(() => window.__strip)).map((s) => `${row.source}: ${s}`));
  }
  assert.deepEqual([...new Set(seen)], [], "something was said over the row");
  assert.deepEqual(errors, []);
});
