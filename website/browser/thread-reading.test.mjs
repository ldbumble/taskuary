import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* TRIAGE'S READING OF THE THREAD IS SEEN (closeout in the agent's chat, task 1.4). On the demo world: the general task whose thread triage
   read shows it atop its agent section (Came from no longer repeats it, 2026-11-05); a coding task, whose agent is a terminal and which has no
   reading, shows none there. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const open = async (page, id) => {
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-canvas-item] [data-tq-task-page="${id}"] [data-tq-task-body]`, { timeout: 20000 });
  await sleep(1800);
};
const section = async (page, id, key) => {
  const tab = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"]) [data-tq-section-tab=${key}] [data-tq-tab-arrow]`;
  if (await page.$(tab)) { await page.click(tab); await sleep(900); }
};

test("the reading sits atop the agent's chat and opens Came from; a coding task has none", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${h.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": h.token } })).json()).data;
  const id = (re) => tasks.find((x) => re.test(x.Title))?.TaskId;
  const CUR = (n) => `[data-tq-canvas-item]:has([data-tq-task-page="${n}"])`;

  const g = id(/^Reconcile the August GL/), c = id(/importers#214/);
  assert.ok(g && c, "the demo tasks are there");
  await open(page, g);
  await section(page, g, "agent");
  const chat = await page.$(`${CUR(g)} [data-tq-reading=chat]`);
  assert.ok(chat, "the general task's agent section opens with the reading");
  const text = await chat.evaluate((e) => e.innerText);
  assert.match(text, /reconciled against the bank feed/, "it says what is asked");
  await section(page, g, "from");
  // ...and Came from carries no "What's going on" (the owner, 2026-11-05): What came in, the Conversation and the To do say it
  assert.equal(await page.$(`${CUR(g)} [data-tq-from] [data-tq-reading]`), null, "Came from has no reading");

  await open(page, c);
  await section(page, c, "agent");
  assert.equal(await page.$(`${CUR(c)} [data-tq-reading=chat]`), null, "a coding task's terminal has no reading");
  assert.equal(await page.$(`${CUR(c)} [data-tq-reading]`), null, "nor does its Came from");
  assert.deepEqual(errors, []);
});
