import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";

import { startHarness } from "./harness.mjs";

/* CAME FROM IS ONE FLOW (the owner, 2026-10-28, a chat task with 15 messages and a 22-item to-do: "I want to be able to see what came in
   actual chat without going to the bottom ... show all 15 does nothing" - then "it has to be ONE flow without duplicates and easy to
   follow"). At 1440x900: the two boxes, then the Conversation - its latest five, oldest to newest, the newest marked, in view without a
   scroll - then The ask, then To do with its done items folded into one line. Show all opens the fifteen in place, Show fewer folds
   them; every message is drawn once, and nothing conversation-like is left under To do. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Came from: the boxes, the conversation, the ask, the to-do - each message once", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await (await fetch(`${h.fixtureApi}/api/fixture/task/long-chat`, { method: "POST",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: "{}" })).json();
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${made.taskId}"])`, FROM = `${CUR} [data-tq-from]`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
  if (await page.$(`${CUR} [data-tq-section-tab=from]`)) { await page.click(`${CUR} [data-tq-section-tab=from]`); await sleep(800); }
  await page.waitForSelector(`${FROM} [data-tq-conversation-block]`, { visible: true, timeout: 10000 });

  const look = () => page.evaluate((FROM) => {
    const from = document.querySelector(FROM), q = (s) => from.querySelector(s), all = (s) => [...from.querySelectorAll(s)].filter((e) => e.offsetParent);
    const block = q("[data-tq-conversation-block]"), todo = q("[data-tq-todo]"), ask = q("[data-tq-ask]"), boxes = q("[data-tq-from-cards]");
    const after = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
    const rows = all("[data-tq-conversation-row]");
    const text = from.innerText, mids = rows.map((r) => r.dataset.tqMid);
    return { rows: rows.map((r) => r.innerText.replace(/\s+/g, " ")), mids, newest: rows.at(-1)?.hasAttribute("data-tq-newest"),
      lastBottom: rows.at(-1)?.getBoundingClientRect().bottom,
      order: [after(boxes, block), after(block, ask), after(ask, todo)],
      below: todo ? [...from.querySelectorAll("[data-tq-conversation-row], [data-tq-history-toggle], [data-tq-conversation], [data-tq-came-from]")].filter((e) => after(todo, e)).length : -1,
      notes: Array.from({ length: 15 }, (_, i) => text.split(`Move note ${i + 1}:`).length - 1),
      todoRows: all("[data-tq-todo] .MuiCheckbox-root").length, struck: all("[data-tq-todo] .MuiCheckbox-root.Mui-checked").length,
      fold: q("[data-tq-todo-done-fold]")?.innerText || "", todoMore: q("[data-tq-todo-more]")?.innerText || "",
      firstTodo: q("[data-tq-todo] .MuiCheckbox-root")?.closest("[data-tq-todo] > *, [data-tq-todo-item]")?.innerText || "", more: q("[data-tq-conversation-more]")?.innerText || "" };
  }, FROM);

  const at = await look();
  assert.deepEqual(at.order, [true, true, true], "the boxes, then the conversation, then the ask, then To do");
  assert.equal(at.below, 0, "nothing conversation-like under To do");
  assert.equal(at.rows.length, 5, `its latest five: ${JSON.stringify(at.rows)}`);
  assert.match(at.rows.at(-1), /Move note 15:/, "newest last");
  assert.match(at.rows[0], /Move note 11:/, "oldest of the five first");
  assert.ok(at.newest, "the newest is marked");
  assert.ok(at.lastBottom < 900, `the newest is in view without a scroll: ${at.lastBottom}`);
  assert.deepEqual(at.notes, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1], "each shown message once, the hidden ones not at all");
  assert.equal(at.todoRows, 6, "the newest six open to-dos are what is seen (2026-10-28)");
  assert.equal(at.struck, 0, "the done ones are folded away");
  assert.match(at.fold, /^6 done/);
  assert.match(at.todoMore, /^Show 10 more/, "the other open ones behind Show more");
  assert.match(at.more, /^Show all 15/);
  if (process.env.TASKUARY_SHOT_DIR) await (await page.$(CUR)).screenshot({ path: path.join(process.env.TASKUARY_SHOT_DIR, "came-from-flow.png") });

  await page.click(`${FROM} [data-tq-conversation-more]`); await sleep(400);
  const open = await look();
  assert.equal(open.rows.length, 15, "Show all opens the fifteen in place");
  assert.deepEqual(open.notes, Array(15).fill(1), "every message once");
  assert.equal(new Set(open.mids).size, 15, "no message id twice");
  assert.match(open.more, /^Show fewer/);
  assert.equal(open.below, 0);
  await page.click(`${FROM} [data-tq-conversation-more]`); await sleep(400);
  assert.equal((await look()).rows.length, 5, "Show fewer folds it back");

  await page.click(`${FROM} [data-tq-todo-more]`); await sleep(300);
  assert.equal((await look()).todoRows, 16, "Show more opens every open one");
  await page.click(`${FROM} [data-tq-todo-done-fold]`); await sleep(300);
  const done = await look();
  assert.equal(done.todoRows, 22); assert.equal(done.struck, 6, "the fold opens the six done");
  assert.deepEqual(errors, []);
});
