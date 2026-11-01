import assert from "node:assert/strict";
import test from "node:test";
import { mkdirSync } from "node:fs";
import path from "node:path";

import { startHarness } from "./harness.mjs";

/* CLOSE OUT HAPPENS MORE THAN ONCE (the owner, 2026-11-01, on a task new mail had reopened: "Why is this showing not the last response i
   sent ... why is status coming up as well? ... let's update the close out to match the agent runs"). Close out showed the reply of the
   round before - "What was sent", "Sent · ... The task stays open until you mark it done" - over the message that reopened it. Now the
   current round answers that message, with nothing of the old one on it, and the old round is a line under it that opens in place, as an
   agent's earlier run does; a reply sent now is the current round's. Invented people (fixture closeout-rounds).
   TASKUARY_SHOT_DIR: where the 1366x768 frames of a three-round task go. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const QUESTION = "which of the 4100 accounts moved", OLD = "They were folded into 4100", NEW = "4101 and 4102 moved";

const open = async (harness, body) => {
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 768, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await page.evaluate(async (b) => (await fetch("/api/fixture/task/closeout-rounds", { method: "POST", body: JSON.stringify(b),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), body);
  assert.equal(made.status, "open", `the question did not reopen it: ${JSON.stringify(made)}`);
  return { page, errors, tid: made.taskId };
};
// ...on the task, with Close out the open section
const onCloseOut = async (page, tid) => {
  // ...asked again until it is there: a send that closed it moves the walk on, and a hash set while that settles can be overtaken
  await page.waitForFunction((id) => !!document.querySelector(`[data-tq-task-page="${id}"]`)
    || (location.hash === `#task=${id}` ? (location.hash = "") : (location.hash = `task=${id}`), false), { timeout: 30000, polling: 1500 }, tid);
  await sleep(2000);
  if (await page.$(`[data-tq-task-page="${tid}"] [data-tq-section-tab=close]`)) await page.click(`[data-tq-task-page="${tid}"] [data-tq-section-tab=close] [data-tq-tab-name]`);
  await page.waitForSelector(`[data-tq-task-page="${tid}"] [data-tq-closeout] [data-tq-section-head], [data-tq-task-page="${tid}"] [data-tq-closeout]`, { visible: true, timeout: 20000 });
  await sleep(800);
};
// what Close out says, the current round apart from the rounds folded under it
const closeOut = (page) => page.evaluate(() => {
  const co = document.querySelector("[data-tq-closeout]"), list = co.querySelector("[data-tq-rounds-before]");
  const all = co.innerText, before = list ? list.innerText : "";
  return { current: before ? all.slice(0, all.lastIndexOf(before)) : all, before, answering: co.querySelector("[data-tq-answering]")?.innerText || "",
    draft: [...co.querySelectorAll("textarea")].map((x) => x.value).join(" "),
    rows: [...co.querySelectorAll("[data-tq-round-before]")].map((r) => [r.getAttribute("data-tq-round-before"), r.innerText,
      r.querySelector("[role=button]").getAttribute("aria-expanded")]) };
});

test("reopened by a new message: Close out answers it with no stale Sent, the old round folds under it, and a new reply is the current round's", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const { page, errors, tid } = await open(harness, { rounds: 2, draft: true });
  // the demo sends nothing: Send's answer is played here, and the reply recorded as sent on the server, as a real Send leaves it
  let recorded = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      recorded = (await fetch(`${harness.fixtureApi}/api/fixture/review/${rid}/sent`, { method: "POST", body: "{}",
        headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } })).status;
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  await onCloseOut(page, tid);
  let co = await closeOut(page);
  assert.match(co.answering, new RegExp(`Answering Erin Blake: .*${QUESTION}`), `the current round answers the message that reopened it: ${co.answering}`);
  assert.ok(co.draft.includes("4102 moved"), `its draft waits for Send: ${co.draft}`);
  assert.doesNotMatch(co.current, /What was sent|Sent · |stays open until you mark it done|The task closed with it/, `nothing of the old round on the current one: ${co.current}`);
  assert.ok(!co.current.includes(OLD), "the old reply is not the current round's");
  assert.match(co.before, /^Earlier rounds · 1/i);
  assert.equal(co.rows.length, 1);
  assert.match(co.rows[0][1], /Round 1 · Replied to Erin Blake · [A-Z][a-z]{2} \d+, \d+:\d\d [AP]M/, `when and what was done: ${co.rows[0][1]}`);
  assert.ok(co.rows[0][1].includes(OLD) && co.rows[0][2] === "false", "folded to its line, what went on it");

  // ...it opens in place: what it answered, what went, how it closed
  await page.click("[data-tq-round-before='1'] [role=button]");
  await page.waitForFunction(() => /What was sent/.test(document.querySelector("[data-tq-round-before='1']")?.innerText || ""), { timeout: 10000 });
  const opened = await page.$eval("[data-tq-round-before='1']", (e) => e.innerText);
  assert.match(opened, /Answering Erin Blake: Some accounts are missing/);
  assert.match(opened, /✓ Marked done · /);

  // ...and the reply sent now is the current round's sent reply, the round before still under it
  const sent = await page.evaluate(() => {
    const b = [...document.querySelectorAll("[data-tq-closeout] button")].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    if (!b) return false; b.click(); return true;
  });
  assert.ok(sent, "the current round offers Send");
  let status = "", d = null;
  for (let i = 0; i < 40 && status !== "done"; i++) {
    await sleep(500);
    d = await (await fetch(`${harness.fixtureApi}/api/tasks/${tid}`, { headers: { "X-Taskuary-Token": harness.token } })).json();
    status = String(d.task.Status);
  }
  assert.equal(recorded, 200);
  assert.equal(status, "done", `the send closed the task - it says: ${(d.comments || []).slice(-3).map((c) => c.Body).join(" / ")}`);
  await onCloseOut(page, tid);
  await page.waitForFunction((w) => (document.querySelector("[data-tq-closeout]")?.innerText || "").includes(w), { timeout: 15000 }, NEW);
  co = await closeOut(page);
  assert.match(co.current, /What was sent · /);
  assert.ok(co.current.includes(NEW) && !co.current.includes(OLD), `the current round's own reply: ${co.current}`);
  assert.equal(co.rows.length, 1, "round 1 still folded under it");
  assert.ok(co.rows[0][1].includes(OLD));
  if (process.env.TASKUARY_SHOT_DIR) { mkdirSync(process.env.TASKUARY_SHOT_DIR, { recursive: true }); await page.screenshot({ path: path.join(process.env.TASKUARY_SHOT_DIR, "closeout-rounds-sent.png") }); }
  assert.deepEqual(errors, []);
});

test("three rounds: the current one open on top, the two before it a line each, newest first, one opened", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const { page, errors, tid } = await open(harness, { rounds: 3 });
  await onCloseOut(page, tid);
  const co = await closeOut(page);
  assert.match(co.answering, new RegExp(QUESTION));
  assert.doesNotMatch(co.current, /What was sent|Sent · |Walked Erin through/);
  assert.deepEqual(co.rows.map((r) => r[0]), ["2", "1"], "newest first");
  assert.match(co.rows[0][1], /Round 2 · Closed with a note · [^\n]+\s+Walked Erin through the mapping/);
  assert.match(co.rows[1][1], /Round 1 · Replied to Erin Blake/);
  const dir = process.env.TASKUARY_SHOT_DIR;
  if (dir) mkdirSync(dir, { recursive: true });
  const shot = (name) => dir ? page.screenshot({ path: path.join(dir, name) }) : null;
  const scroll = () => page.evaluate(() => document.querySelector("[data-tq-rounds-before]")?.scrollIntoView({ block: "center" }));
  await scroll(); await shot("closeout-rounds-folded.png");
  await page.click("[data-tq-round-before='1'] [role=button]");
  await page.waitForFunction(() => /What was sent/.test(document.querySelector("[data-tq-round-before='1']")?.innerText || ""), { timeout: 10000 });
  await scroll(); await shot("closeout-rounds-one-open.png");
  // ...a phone's width stacks it the same way
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 }); await sleep(1500);
  await onCloseOut(page, tid);
  assert.ok(await page.$("[data-tq-closeout] [data-tq-rounds-before] [data-tq-round-before='2']"), "the rounds stack on a phone too");
  await scroll(); await shot("closeout-rounds-phone.png");
  assert.deepEqual(errors, []);
});
