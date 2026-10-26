import assert from "node:assert/strict";
import test from "node:test";
import { boot, bubbles, clickRow, findRow, folded, rowVerbs, sleep } from "./walkdriver.mjs";

/* NOT OURS ON AN FYI FOLDS WITH ITS BADGE AND NO LINE (the 2026-10-26 sweep): the page added "✓ Done - Not ours · <subject>." to carry
   its From now on way on, the walk moved to the next FYI within ~200 ms and took the way on with it, and the bare line stayed with
   nothing to act on. A press that went through is a badge on its card; a line stays only where it carries a way on (the owner,
   2026-10-22: "we don't need that text ever"). */
test("Not ours on an FYI folds wearing its badge, with no line left behind", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  await clickRow(page, await findRow(page, /Regional operations newsletter/)); await sleep(3000);
  const verb = (await rowVerbs(page)).find((v) => /not_ours$/.test(v));
  assert.ok(verb, `the FYI's row has Not ours: ${await rowVerbs(page)}`);
  await page.evaluate((v) => document.querySelector(`[data-tq-row] button[data-tq-verb="${v}"]`).click(), verb);
  await sleep(3000);
  const lines = (await bubbles(page)).filter((b) => b.who === "receipt" && /Not ours/.test(b.text));
  assert.deepEqual(lines, [], "a bare receipt line was left over the folded card");
  const card = (await folded(page)).find((f) => /Regional operations newsletter/.test(f.title));
  assert.equal(card?.badge, "Not ours", `the card did not fold with its badge: ${JSON.stringify(await folded(page))}`);
  assert.deepEqual(errors, []);
});
