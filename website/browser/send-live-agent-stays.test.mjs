import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A SEND NEVER CLOSES A TASK WITH WORK STILL LIVE ON IT (the owner, 2026-11-01: "if agent screen is still open and you hit send message it
   should not close the tasks. it did that and now it's open with it not being on the table. If anything still working never close the task
   automatically"). The task's agent sits at its prompt, waiting on the owner; Send on Close out sends the reply, and the task stays open -
   on the rail, on the table, its agent still there. The page put the row down at the press and never picked it back up: off the rail,
   its canvas drawn over nothing. The press is Send and close, Close out's closing send (the owner, 2026-11-03). Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Send with a live agent waiting on you: the reply goes, the task stays on the rail and the table with its agent", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  // the demo sends nothing: the decide is answered as gone and recorded as sent (send-stays-on-closeout's road)
  let recorded = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      recorded = (await api(`/api/fixture/review/${rid}/sent`, {})).status;
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  const tasks = (await (await api("/api/tasks")).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting for Send");
  assert.equal((await api("/api/fixture/task/live-agent", { task_id: inv.TaskId })).status, 200, "an agent live on it, waiting on you");
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  // the task's own row, by the key the rail gives it
  const pile = await (await api("/api/funnel/pile")).json();
  const key = (pile.items || []).find((i) => i.tid === inv.TaskId)?.key;
  assert.ok(key, `the invoice task is on the rail: ${(pile.items || []).map((i) => `${i.key}=${i.tid}`).join(", ")}`);
  const pageSel = `[data-tq-task-page="${inv.TaskId}"]`, rowSel = `[data-tq-rail] .tq-pile-row[data-tq-key="${key}"]`;
  await page.waitForSelector(`${pageSel} :is(.xterm, [data-tq-agent-room=live])`, { timeout: 20000 });
  await page.waitForSelector(rowSel, { timeout: 20000 });
  // Close out, where its Send is: opened by its tab while the agent holds the page - unless its buttons are already in view. Folded, its
  // draft is drawn there out of sight (lendsReply, so Redraft stays on the spine): a button there is not Close out open
  await page.waitForSelector(`${pageSel} [data-tq-section-tab=close]`, { timeout: 20000 });
  if (!(await page.$$eval(`${pageSel} [data-tq-closeout] button`, (bs) => bs.some((b) => b.offsetParent)))) await page.$eval(`${pageSel} [data-tq-section-tab=close]`, (b) => b.click());
  await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} [data-tq-closeout] button, [data-tq-row] button`)]
    .some((b) => /^Send and close\b/.test(b.textContent.trim()) && !b.disabled && b.offsetParent), { timeout: 20000 }, pageSel)
    .catch(async () => assert.fail(`no Send: ${await page.evaluate(() => [...document.querySelectorAll("button")].filter((b) => b.offsetParent).map((b) => b.textContent.trim()).join(" | "))}`));
  // ...and what it says under it tells the truth: the task stays open while the agent works
  const told = await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-closeout]`)?.innerText || "", pageSel);
  assert.ok(!/then the task closes/.test(told), `Send says it closes the task under a live agent: ${told.slice(0, 400)}`);
  await page.evaluate((sel) => {
    const b = [...document.querySelectorAll(`${sel} [data-tq-closeout] button, [data-tq-row] button`)].find((x) => /^Send and close\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    b.click();
  }, pageSel);
  for (let i = 0; i < 20 && recorded !== 200; i++) await sleep(250);
  assert.equal(recorded, 200, "the reply went");
  // the row is never put down: it stays on the rail throughout, and the task on the table with its agent
  for (let i = 0; i < 12; i++) {
    await sleep(500);
    const seen = await page.evaluate((rowSel, key) => ({ row: !!document.querySelector(rowSel),
      table: !!document.querySelector(`[data-tq-canvas-item="${key}"]`) }), rowSel, key);
    if (!seen.table || !seen.row) {
      const now = (await (await api(`/api/tasks/${inv.TaskId}`)).json());
      const on = await page.evaluate(() => [...document.querySelectorAll("[data-tq-canvas-item]")].map((e) => e.getAttribute("data-tq-canvas-item")).join(","));
      assert.fail(`after the Send (${i * 0.5 + 0.5}s): ${JSON.stringify(seen)} - status ${now.task?.Status}, table holds ${on || "nothing"}, `
        + `said: ${(now.comments || []).slice(-2).map((c) => c.Body).join(" / ")}`);
    }
  }
  // ...and its agent is still there, one press away on its own section, the terminal live
  await page.waitForSelector(pageSel, { timeout: 5000 });
  if (!(await page.$(`${pageSel} .xterm`))) await page.$eval(`${pageSel} [data-tq-section-tab=agent]`, (b) => b.click());
  await page.waitForSelector(`${pageSel} :is(.xterm, [data-tq-agent-room=live])`, { timeout: 10000 });
  const task = (await (await api(`/api/tasks/${inv.TaskId}`)).json()).task;
  assert.notEqual(String(task.Status), "done", "the task stays open while its agent is live");
  assert.deepEqual(errors, []);
});
