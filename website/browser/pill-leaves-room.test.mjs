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
  // ...and with the walk's Back beside it (2026-10-27) neither is shortened: drawn as wide as each one's unseen copy, arrow and all
  // (an ellipsis over a ::after arrow is no overflow to scrollWidth - the 2026-10-27 sweep saw "All read, next…" and "←…" pass the line above)
  assert.deepEqual(await whole(page), [], "Back and All read, next drawn whole");
  assert.deepEqual(errors, []);
});

// every row button drawn narrower than its natural width (the row's own unseen copy measures it): a squeezed label
const whole = (page) => page.evaluate(() => {
  const w = (e) => Math.ceil(e.getBoundingClientRect().width), row = document.querySelector(".tq-dock [data-tq-row]"), g = (s) => row.querySelector(`.tq-arow-ghost ${s}`);
  const want = (b) => (b.hasAttribute("data-tq-walk-back") ? g("[data-tq-wbk]") : b.hasAttribute("data-tq-next") ? g("[data-tq-wn]") : g(`[data-tq-w="${b.dataset.tqVerb}"]`));
  return [...row.querySelectorAll(".tq-arow-verbs button")].filter((b) => !b.classList.contains("tq-cl-more") && want(b) && w(b) < w(want(b)) - 1)
    .map((b) => `${b.textContent.trim() || b.getAttribute("aria-label")}: ${w(b)} of ${w(want(b))}`);
});

/* ...AND A MOVE WITH NO ROOM FOR ITS WORDS GOES INTO THE ▾ (the 2026-10-27 sweep): a report on a phone drew Back, Next, "Pu" and the ▾ */
test("on a phone a report's row draws no squeezed move: Back, Next and the ▾ hold the rest", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 390, height: 844 });
  const reps = await page.$$eval('[data-tq-run="reports"] .tq-pile-row[data-tq-key]', (e) => e.map((x) => x.dataset.tqKey));
  await page.evaluate(() => document.querySelector('[aria-label="Your work"], [data-testid=ViewSidebarIcon]')?.closest("button")?.click());
  await page.evaluate((k) => document.querySelector(`.tq-pile-row[data-tq-key="${k}"] .card`).click(), reps[1]); await sleep(3500);
  assert.ok(await page.$(".tq-dock [data-tq-row] [data-tq-walk-back]"), "Back is on the row (a report below the first row)");
  assert.deepEqual(await whole(page), [], "every button on the row drawn whole");
  const verbs = await page.$$eval(".tq-dock [data-tq-row] .tq-arow-verbs button[data-tq-verb]", (bs) => bs.map((b) => b.dataset.tqVerb));
  const more = await page.$(".tq-dock [data-tq-row] [data-tq-more]");
  assert.ok(more, `the report's own moves are behind the ▾: ${JSON.stringify(verbs)}`);
  assert.deepEqual(errors, []);
});

test("on the desk the pill's hint is one line", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await toFyi(page);
  const p = await pill(page);
  assert.equal(p.next?.text, "All read, next");
  assert.equal(p.hint, "nowrap");
  assert.ok(p.box >= 276 && p.box <= 284, `the desk's pill is the chat's own 280px at rest (the owner, 2026-10-28): ${p.box}`);
  assert.deepEqual(errors, []);
});
