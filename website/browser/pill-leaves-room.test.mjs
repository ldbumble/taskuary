import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* THE PILL LEAVES THE ROW ITS WORDS (the overnight walk, 2026-10-26). On a phone the chat pill kept its desk width - 220px, held there by
   the textarea's own 20 columns whatever its basis - and the row beside it was left 88px: at the walk's end "Walk me through my tasks"
   read "W.". On the desk the box's long hint wrapped inside the one-line pill and half its second line showed under the first. */
const pill = (page) => page.evaluate(() => {
  const box = document.querySelector(".tq-dock .tq-dock-line > .tq-compose-box"), ta = box?.querySelector("textarea");
  const b = document.querySelector("[data-tq-row] [data-tq-next]");
  return { line: box?.parentElement.getBoundingClientRect().width || 0, box: box?.getBoundingClientRect().width || 0,
    hint: ta ? getComputedStyle(ta, "::placeholder").whiteSpace : "", next: b ? { text: b.textContent.trim(), cut: b.scrollWidth > b.clientWidth + 1 } : null };
});
async function toFyi(page) {
  await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold')?.click()); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]").click()); await sleep(3500);
}

test("on a phone the pill takes under half the line and the batch's All read, next is whole", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 390, height: 844 });
  await toFyi(page);
  const p = await pill(page);
  assert.equal(p.next?.text, "All read, next", `no batch on the table: ${JSON.stringify(p)}`);
  assert.ok(p.box <= p.line * 0.45, `the pill took ${p.box} of ${p.line}`);
  assert.equal(p.next.cut, false, `the row's button was cut: ${JSON.stringify(p)}`);
  assert.deepEqual(errors, []);
});

test("on the desk the pill's hint is one line", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await toFyi(page);
  const p = await pill(page);
  assert.equal(p.next?.text, "All read, next");
  assert.equal(p.hint, "nowrap");
  assert.ok(p.box >= 110 && p.box <= 130, `the desk's pill is the small one at rest (the owner, 2026-10-27): ${p.box}`);
  assert.deepEqual(errors, []);
});
