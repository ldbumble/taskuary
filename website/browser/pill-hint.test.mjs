import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, sleep, type } from "./walkdriver.mjs";

/* THE PILL'S HINT FITS THE PILL (the overnight setup walk, 2026-10-26): an answer with a row under it (Next) and no task on the table left
   the chat box as the dock's 220px pill holding the long hint, "Ask Taskuary anything — a name or a subject pulls it in…", which ran on
   under the pill's own send button cut mid-word. At rest the pill says the short one; opened over the canvas - a column as narrow as a
   phone's line since 2026-10-27 - the phone's short hint, whole. */
const hint = (page) => page.evaluate(() => {
  const t = document.querySelector(".tq-compose-box textarea"), cs = getComputedStyle(t);
  const ctx = document.createElement("canvas").getContext("2d"); ctx.font = `${cs.fontSize} ${cs.fontFamily}`;
  const room = t.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  return { text: t.placeholder, fits: ctx.measureText(t.placeholder).width <= room + 1, pill: !!t.closest(".tq-chat-unit") || !!t.closest(".tq-dock-line")?.querySelector(":scope > .tq-arow"),   // a desk's own unit (2026-10-29), or beside the row
    open: t.closest(".tq-compose-box").hasAttribute("data-tq-open") };
});

/* ...AND ITS "Ask…" IN THE MIDDLE OF ITS HEIGHT on a task opened from the day's opener (the 2026-10-27 sweep): the box's grow-as-you-type
   height was measured while it was the opener's whole line, 34px, and stayed on the pill - its 30px line sat 2px high */
test("a task opened from the opener: the pill's line is centred in the pill", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  const first = await page.$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (e) => e.getAttribute("data-tq-key"));
  await clickRow(page, first);
  await page.waitForSelector(".tq-dock-line > .tq-arow [data-tq-next]", { timeout: 30000 }); await sleep(1500);
  const at = await page.evaluate(() => {
    const box = document.querySelector(".tq-dock-line > .tq-compose-box, .tq-chat-unit > .tq-compose-box"), ta = box.querySelector("textarea"), send = box.querySelector(".tq-send");
    const mid = (e) => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; };
    return { box: mid(box), ta: mid(ta), send: mid(send), h: ta.getBoundingClientRect().height, open: box.hasAttribute("data-tq-open") };
  });
  assert.ok(!at.open, "the pill at rest");
  // ...on a desk the ask bar is a composer card (the owner, 2026-10-29): its words one 32px line, the send round at that line's end
  const desk = await page.$(".tq-chat-unit > .tq-compose-box");
  assert.equal(at.h, desk ? 32 : 30, `one line: ${JSON.stringify(at)}`);
  assert.ok((desk || Math.abs(at.ta - at.box) <= 1) && Math.abs(at.ta - at.send) <= 2, `the line is centred with its send: ${JSON.stringify(at)}`);
  assert.deepEqual(errors, []);
});

test("the dock's pill at rest says a hint that fits it, and the whole hint once opened", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await type(page, "what is on my list?");
  await page.waitForFunction(() => document.querySelector(".tq-dock-line > .tq-arow"), { timeout: 30000 });
  // ...shut by its × (the box stays open until the owner shuts it, 2026-10-27), not by a look away
  await page.click("[data-tq-box-close]"); await sleep(800);
  const rest = await hint(page);
  assert.ok(rest.pill && !rest.open, `the box is the pill, its own unit beside the bar: ${JSON.stringify(rest)}`);
  assert.ok(rest.fits, `the pill's hint fits it: ${JSON.stringify(rest)}`);
  // ...and it is the SAME words whatever is on the table (the owner, 2026-10-27: "it should always be the same size and words") - the
  // short one in a narrow pill, the box's own words in the desk's wide ask bar (2026-10-29)
  assert.ok(rest.text === "Ask…" || (await page.$(".tq-chat-unit > .tq-compose-box") && rest.text.length > 3), JSON.stringify(rest));
  await page.focus(".tq-compose-box textarea"); await sleep(500);
  const open = await hint(page);
  assert.ok(open.open && open.fits, `opened, its hint fits: ${JSON.stringify(open)}`);
  assert.deepEqual(errors, []);
});
