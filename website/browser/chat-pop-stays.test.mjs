import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE CHAT POP-UP IS ONE NARROW COLUMN WITH THE BOX, AND STAYS (the owner, 2026-10-27): the open box and the answer over it had different
   widths ("doesn't match the size"), the row kept a blank white pill in the box's slot that read as a second input, and an answer that only
   lit a button shut the pop-up by itself after 1.8 s - "it disappeared when done? not sure what happened" - its Show the last answer
   bringing back the owner's own line alone ("useless"). At 1600x810, on the demo's invoice: one ~280px column (the pill's, 2026-10-28), the slot kept but unseen, and
   "remind me Monday" (the demo's brain lights Remind me, no words) leaves a receipt that is still up 5 s later and comes back with it. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width }; });

test("the box and the pop-up are one column, the row's slot is unseen, and an act-only answer stays up with its receipt", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2500);

  // OPEN: the box keeps the pill's room in the bar (the owner, 2026-10-28: "the chat should come out of the bottom bar"), drawing nothing
  // of its own there - its field, rising out of it, is the one input
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await sleep(300);
  const slot = await page.$eval(".tq-compose-box", (e) => {
    const s = getComputedStyle(e);
    return { w: e.getBoundingClientRect().width, border: parseFloat(s.borderTopWidth) === 0, bg: s.backgroundColor, shadow: s.boxShadow, fields: e.querySelectorAll(".tq-compose-field").length };
  });
  // ...on a desk the window opens out of the pill in the corner, its own unit (the owner, 2026-10-29): the box is the window's width, 340px
  assert.ok(slot.w >= 300, `the box is the window's width ${JSON.stringify(slot)}`);
  assert.ok(slot.border && slot.bg === "rgba(0, 0, 0, 0)" && slot.shadow === "none" && slot.fields === 1, `...and is not drawn: no blank second input ${JSON.stringify(slot)}`);

  // SENT: an answer that only lit a button
  await page.keyboard.type("remind me Monday");
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
  await sleep(400);
  const pop = await rect(page, "[data-tq-chat-pop]"), box = await rect(page, ".tq-compose-box .tq-compose-field");
  const say = JSON.stringify({ pop, box });
  assert.ok(Math.abs(pop.l - box.l) <= 1 && Math.abs(pop.r - box.r) <= 1, `one column: the same left and right edges ${say}`);
  assert.ok(pop.w >= 300, `...the window's width, like a chat helper on an app ${say}`);
  assert.ok(pop.b <= box.t + 1 && box.t - pop.b <= 8, `...the answer flush above the box ${say}`);

  // ...still up 5 s later, ending on words that say what was done
  await sleep(5000);
  const after = await page.$eval("[data-tq-chat-pop]", (p) => ({ hidden: p.hidden, receipt: p.querySelector(".tq-chat-pop-body .tq-msg.receipt")?.textContent.trim() || "",
    you: p.querySelector(".tq-chat-pop-body .tq-msg.you")?.textContent || "" }));
  assert.equal(after.hidden, false, "the pop-up never shuts by itself");
  assert.match(after.you, /remind me Monday/);
  assert.match(after.receipt, /Remind me/, `a receipt line naming what it did ${JSON.stringify(after)}`);

  // ...and the pill, pressed again, brings the whole exchange back, the receipt with it (the chat window, 2026-10-28)
  await page.click("[data-tq-chat-pop] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-pop][hidden]", { timeout: 5000 });
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-chat-pop] .tq-chat-pop-body", (b) => b.textContent), /remind me Monday[\s\S]*Remind me/);
  assert.deepEqual(errors, []);
});
