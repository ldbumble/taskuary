import assert from "node:assert/strict";
import test from "node:test";
import { boot, bubbles, clickRow, doVerb, findRow, folded, ringed, rowVerbs, sleep, unwatch, watch } from "./walkdriver.mjs";

/* ONE PRESS, ONE ROAD (the 2026-10-25 navigation sweep, N2-N4): a row button the server proposes for came back twice - the page ran it, and the
   server wrote the press into the chat as an owner line nobody typed ("Not ours: FW: ...") with a card of its own, which folded the next
   item after it; a verb that was not "auto" (Chase them, Put it on my list) drew "Nothing happens until you say yes" over a button already
   pressed, and the row shrank to that card's button. The owner, 2026-10-19: "no confirm cards" - the row's button IS the confirmation. */
const CONFIRM = /Nothing happens until you say yes/;
async function press(t, row, verb) {
  const { page, errors } = await boot(t);
  await clickRow(page, await findRow(page, row)); await sleep(3000);
  await watch(page);
  assert.ok(await doVerb(page, verb), `no ${verb} to press`);
  await sleep(6000);
  return { page, errors, said: await unwatch(page) };
}

test("Not ours on an fyi: no owner line, its badge on the fold, and what came up after it stays up", { timeout: 180000 }, async (t) => {
  const { page, said } = await press(t, /Regional operations newsletter/, "w:not_ours");
  assert.deepEqual(said.filter((l) => l.you), [], "a press was written as an owner line");
  assert.deepEqual((await bubbles(page)).filter((b) => b.who === "you"), []);
  assert.ok((await folded(page)).some((f) => /Regional operations/.test(f.title) && f.badge === "Not ours"), `no Not ours badge: ${JSON.stringify(await folded(page))}`);
  // ...and the batch the walk brought next stays up, not folded by a second card the server wrote for the same press
  await sleep(4000);
  assert.ok(!(await folded(page)).some((f) => /fyi/i.test(f.title)), `the next batch folded with nothing pressed: ${JSON.stringify(await folded(page))}`);
  assert.equal(await page.$eval("[data-tq-row] [data-tq-next]", (b) => b.textContent.trim()).catch(() => ""), "All read, next");
});

test("Put it on my list runs at once: no confirm card, its badge, and it is a task on the table", { timeout: 180000 }, async (t) => {
  const { page, said } = await press(t, /Headcount by site/, "w:mine");
  assert.ok(!said.some((l) => CONFIRM.test(l.s)), "one press asked to be confirmed");
  assert.deepEqual(said.filter((l) => l.you), [], "a press was written as an owner line");
  assert.ok(said.some((l) => /Headcount by site.*✓ Put it on my list/.test(l.s)), `the press drew no badge: ${JSON.stringify(said)}`);
  assert.match(await ringed(page), /Headcount by site.*TQ-\d+/, "it did not become a task");
});

test("the Advisor's Chase them on a goal runs at once and the row keeps Next and its verbs", { timeout: 180000 }, async (t) => {
  const { page, said } = await press(t, /Migrate the census/, "advice:chase");
  assert.ok(!said.some((l) => CONFIRM.test(l.s)), "one press asked to be confirmed");
  assert.deepEqual(said.filter((l) => l.you), [], "a press was written as an owner line");
  assert.ok(await page.$("[data-tq-row] [data-tq-next]"), "the row lost Next");
  assert.ok((await rowVerbs(page)).length > 1, `the row shrank to one button: ${await rowVerbs(page)}`);
});
