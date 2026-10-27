import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* WHERE IT CAME FROM SAYS EACH THING ONCE (the overnight walk, 2026-10-27): an invitation's one message, open under Came from, read its
   first line in its row and again in full under it, and its subject under the conversation's own subject - four lines for two. */
const times = (s, words) => s.split(words).length - 1;

test("a task's one message, open under Came from: its words and its subject are each read once", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await clickRow(page, await findRow(page, /Invite: AP cutover/));
  await page.waitForSelector("[data-tq-came-from] [data-tq-letter]", { timeout: 20000 }); await sleep(1000);
  const from = await page.$eval("[data-tq-came-from]", (e) => e.innerText.replace(/\s+/g, " "));
  assert.equal(times(from, "A dry run of the AP cutover"), 1, from);
  assert.equal(times(from, "Invitation: AP cutover dry run"), 1, from);
  // ...and the row still names who and when, and still shuts the letter
  const row = await page.$eval("[data-tq-came-from] [data-tq-conversation-row][aria-expanded=true]", (e) => e.innerText.replace(/\s+/g, " ").trim());
  assert.match(row, /^Ruth Bennett .*\d/);
  await page.click("[data-tq-came-from] [data-tq-conversation-row][aria-expanded=true]"); await sleep(500);
  assert.equal(await page.$("[data-tq-came-from] [data-tq-letter]"), null);
  assert.match(await page.$eval("[data-tq-came-from] [data-tq-conversation-row]", (e) => e.innerText), /A dry run of the AP cutover/, "a shut row reads its line");
  assert.deepEqual(errors, []);
});
