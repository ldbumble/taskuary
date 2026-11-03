import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* MARK DONE ALWAYS SHOWS ON CLOSE OUT (the owner, 2026-11-02: "Mark done always shows on Close out, which will save the result and move on").
   An agent parked at its prompt, waiting on the owner, offered only Stop and save; Mark done came back only once it had stopped, and Close
   out said "Close-out controls return when the agent stops." Now Close out carries Mark done beside the live agent, first; a press stops
   and saves the session and closes the task. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a live agent waiting on you: Close out offers Mark done first, and the press saves the session and closes the task", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  const tasks = (await (await api("/api/tasks")).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice task");
  assert.equal((await api("/api/fixture/task/live-agent", { task_id: inv.TaskId })).status, 200, "an agent live on it, waiting on you");
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const pageSel = `[data-tq-task-page="${inv.TaskId}"]`;
  await page.waitForSelector(`${pageSel} :is(.xterm, [data-tq-agent-room=live])`, { timeout: 20000 });
  // Close out, opened by its tab while the agent holds the page
  await page.waitForSelector(`${pageSel} [data-tq-section-tab=close]`, { timeout: 20000 });
  await page.$eval(`${pageSel} [data-tq-section-tab=close]`, (b) => b.click());
  const moves = `${pageSel} [data-tq-pane-moves=close]`;
  await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} button`)].some((b) => b.dataset.tqVerb === "done" && b.offsetParent && !b.disabled),
    { timeout: 20000 }, moves)
    .catch(async () => assert.fail(`no Mark done on Close out: ${await page.evaluate(() => [...document.querySelectorAll("button")].filter((b) => b.offsetParent).map((b) => b.textContent.trim()).join(" | "))}`));
  const first = await page.$eval(moves, (g) => [...g.querySelectorAll("button")].find((b) => b.offsetParent)?.dataset.tqVerb);
  assert.equal(first, "done", "Mark done is Close out's first button");
  // ...and Close out no longer says nothing waits, nor that its controls come back later
  const told = await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-closeout]`)?.innerText || "", pageSel);
  assert.doesNotMatch(told, /Nothing is waiting on you|controls return when the agent stops/, told.slice(0, 400));
  await page.$eval(moves, (g) => [...g.querySelectorAll("button")].find((b) => b.dataset.tqVerb === "done").click());
  // the session is written up and the task closes - the server's own job, behind the press
  let task = null;
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    task = (await (await api(`/api/tasks/${inv.TaskId}`)).json());
    if (String(task.task?.Status) === "done") break;
  }
  assert.equal(String(task.task?.Status), "done", `the task closed: said ${(task.comments || []).slice(-3).map((c) => c.Body).join(" / ")}`);
  assert.ok(!task.session?.alive, "the agent was stopped");
  assert.ok((task.comments || []).some((c) => /^(?:AGENT|CODER) REPORT|Closed the general-work session/.test(String(c.Body || ""))), "what it did was saved first");
  assert.deepEqual(errors, []);
});
