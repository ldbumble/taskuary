import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep, type } from "./walkdriver.mjs";

/* THE PILL'S HINT FITS THE PILL (the overnight setup walk, 2026-10-26): an answer with a row under it (Next) and no task on the table left
   the chat box as the dock's 220px pill holding the long hint, "Ask Taskuary anything — a name or a subject pulls it in…", which ran on
   under the pill's own send button cut mid-word. At rest the pill says the short one; opened, it says the whole hint again. */
const hint = (page) => page.evaluate(() => {
  const t = document.querySelector(".tq-compose-box textarea"), cs = getComputedStyle(t);
  const ctx = document.createElement("canvas").getContext("2d"); ctx.font = `${cs.fontSize} ${cs.fontFamily}`;
  const room = t.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  return { text: t.placeholder, fits: ctx.measureText(t.placeholder).width <= room + 1, pill: !!t.closest(".tq-dock-line")?.querySelector(":scope > .tq-arow"),
    open: t.closest(".tq-compose-box").hasAttribute("data-tq-open") };
});

test("the dock's pill at rest says a hint that fits it, and the whole hint once opened", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await type(page, "what is on my list?");
  await page.waitForFunction(() => document.querySelector(".tq-dock-line > .tq-arow"), { timeout: 30000 });
  await page.evaluate(() => document.activeElement?.blur()); await sleep(800);
  const rest = await hint(page);
  assert.ok(rest.pill && !rest.open, `the box is the pill beside the row: ${JSON.stringify(rest)}`);
  assert.ok(rest.fits, `the pill's hint fits it: ${JSON.stringify(rest)}`);
  // ...and it is the SAME words whatever is on the table (the owner, 2026-10-27: "it should always be the same size and words")
  assert.equal(rest.text, "Ask…");
  await page.focus(".tq-compose-box textarea"); await sleep(500);
  const open = await hint(page);
  assert.ok(open.open && open.fits, `opened, its hint fits: ${JSON.stringify(open)}`);
  assert.deepEqual(errors, []);
});
