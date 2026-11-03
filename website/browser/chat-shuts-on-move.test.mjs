import assert from "node:assert/strict";
import test from "node:test";
import { bootMixed, clean, pressBack, pressNext, settled, shot, sleep, still } from "./stress-mixed-lib.mjs";

/* THE CHAT SHUTS WHEN THE OWNER MOVES ON, AND KEEPS ITS CONVERSATION (the owner, 2026-11-03): open, the pop-up stood over the next task's
   Close out - Close with a note, Hand it to a person, Share, Draft reply. Now Next, Back or another row shuts it as its × would; opened again
   it is the same conversation - the Assistant's question still there, the words typed and not sent still in the box. Its × keeps the question
   too. A press on the row already on the table is no move, and leaves it open. The question is a recorded answer (demo_answers.json). */
const QUESTION = /Do you want a reply drafted for them, or a reminder/;
const isOpen = (page) => page.evaluate(() => !!document.querySelector(".tq-compose-box[data-tq-open]") && !document.querySelector("[data-tq-chat-pop]")?.hidden);
const popText = (page) => page.$eval("[data-tq-chat-pop] .tq-chat-pop-body", (e) => e.innerText);
const boxWords = (page) => page.$eval(".tq-compose-box textarea", (e) => e.value);
const onTable = (page) => page.evaluate(() => document.querySelector("[data-tq-canvas-item] [data-tq-task-page]")?.getAttribute("data-tq-task-page") || null);
const openChat = async (page) => { await page.click(".tq-compose-box textarea"); await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 }); await sleep(300); };
const rowClick = (page, title) => page.evaluate((title) => { const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].find((x) => x.innerText.includes(title));
  r?.querySelector(".card")?.click(); return !!r; }, title);
// every move on Close out's spine drawn on top where it stands: nothing laid over it
const closeOutFree = (page) => page.evaluate(() => [...document.querySelectorAll('[data-tq-spine-moves="close"] button, [data-tq-pane-moves="close"] button')].filter((b) => b.offsetParent)
  .filter((b) => { const r = b.getBoundingClientRect(), top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !(top && b.contains(top)); }).map((b) => b.textContent.trim()));

test("the chat shuts on Next, Back and another row, and keeps its lines, its question and what is typed", { timeout: 300000 }, async (t) => {
  const { page, errors } = await bootMixed(t, { width: 1440, height: 900 });
  assert.ok(await rowClick(page, "New starter on Monday"), "the new starter's row"); await still(page);
  const first = await onTable(page);
  assert.ok(first, "a task on the table");

  await openChat(page);
  await page.keyboard.type("help me with this one"); await page.keyboard.press("Enter");
  await page.waitForFunction((re) => new RegExp(re).test(document.querySelector("[data-tq-chat-pop] .tq-chat-pop-body")?.innerText || ""), { timeout: 30000 }, QUESTION.source);
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
  await page.click(".tq-compose-box textarea"); await page.keyboard.type("reply saying Thursday");
  assert.ok(await isOpen(page), "the chat is open with its question");

  // ...a press on the row already on the table is no move: still open
  await rowClick(page, "New starter on Monday"); await sleep(800);
  assert.ok(await isOpen(page), "a press on the row on the table shut the chat");

  // ...Next: shut, the next task on the table, and nothing over its Close out
  assert.ok(await pressNext(page), "Next pressed"); await still(page); await settled(page); await sleep(600);
  try {
    assert.equal(await isOpen(page), false, "Next left the chat open");
    assert.notEqual(await onTable(page), first, "Next moved the table");
    assert.deepEqual(await closeOutFree(page), [], "Close out's moves are covered");
  } catch (e) { await shot(page, "chat-shuts-next"); throw e; }

  // ...opened again: the same conversation, the question in it, the typed words in the box
  await openChat(page);
  assert.match(await popText(page), QUESTION, "the question is gone after Next");
  assert.equal(await boxWords(page), "reply saying Thursday", "the typed words are gone after Next");

  // ...Back shuts it too
  assert.ok(await pressBack(page), "Back pressed"); await still(page); await sleep(600);
  assert.equal(await isOpen(page), false, "Back left the chat open");

  // ...and another row on the rail
  await openChat(page);
  await rowClick(page, "Invoice 88213"); await still(page); await sleep(600);
  assert.equal(await isOpen(page), false, "another row left the chat open");

  // ...its ×: shut, and the question still there when it opens again
  await openChat(page);
  await page.click("[data-tq-box-close]"); await sleep(400);
  assert.equal(await isOpen(page), false, "the × shuts it");
  await openChat(page);
  assert.match(await popText(page), QUESTION, "the question is gone after the ×");
  assert.equal(await boxWords(page), "reply saying Thursday", "the typed words are gone after the ×");
  clean(errors, "chat shuts on move");
});
