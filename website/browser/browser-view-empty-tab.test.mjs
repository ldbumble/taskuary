import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* AN EMPTY TAB IS NOT A PAGE (the owner, 2026-11-03 and 2026-11-04: "browser should not show unless we need login"; "no browser should open
   if we don't have a URL"). A general task marked as needing a browser was answered without one, and half its canvas was the agent's
   Chrome on about:blank with "your turn - the agent is waiting on you; click the page and type" over it, while what the agent waited on
   was a question asked in words. An empty tab takes no room at all - no view, no chip - and only a wait ON a page is the owner's turn
   there. A real backend whose agent-browser session has no Chrome (fixture_changes.browser_view). Invented people and sites only. */
const post = (page, body) => page.evaluate(async (b) => (await fetch("/api/fixture/browser/view", { method: "POST", body: JSON.stringify(b),
  headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), body);
const FARES = `<html><body style="margin:0;font:16px system-ui;background:#fff;color:#1d2433"><div style="background:#0b5;color:#fff;padding:18px 32px;
  font-weight:600">Fares · Boston to Denver</div><div style="padding:24px 32px">3 nonstop flights · from $212</div></body></html>`;

async function open(harness, step, frame = "") {
  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const made = await post(page, { step, frame });
  assert.ok(made.taskId, JSON.stringify(made));
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  // the agent's room is drawn, with its answer and question in it
  await page.waitForFunction(() => document.body.innerText.includes("First month free, or a price now?")
    && document.querySelector("[data-tq-browser-layout]")
    || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  return { page, made, errors };
}
// ...polled a few times: the browser state is read every 3 s, so what the pane shows is read after the first reads are in
const settled = async (page) => {
  await new Promise((r) => setTimeout(r, 4000));
  return page.evaluate(() => ({ layout: document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout,
    text: document.body.innerText, view: !!document.querySelector("[data-tq-browser-view]") }));
};

test("a browser on an empty tab takes no room - no view, no chip - and a question in words is no turn on the page", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const { page, errors } = await open(harness, "blank");
  const at = await settled(page);
  assert.equal(at.layout, "none", `the empty tab is not shown at all: ${at.layout}`);
  assert.ok(!at.view && !/an empty tab|no page open/.test(at.text), "no view of the empty tab is drawn");
  assert.ok(!/browser ·/.test(at.text), "and no chip for it");
  assert.ok(!/your turn/i.test(at.text), "a question asked in words is not the owner's turn on the page");
  assert.deepEqual(errors, []);
});

test("a hand-over with no page to hand over is a question in words, never 'your turn - click the page'", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const { page, made, errors } = await open(harness, "blank");
  const r = await post(page, { step: "turn", taskId: made.taskId });
  assert.ok(r.requestId && !String(r.requestId).startsWith("yourturn:"), `no page, no hand-over: ${JSON.stringify(r)}`);
  await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });                 // a question in words is read on the next load
  await page.waitForFunction(() => document.body.innerText.includes("tick the") || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false),
    { timeout: 30000, polling: 500 });
  const at = await settled(page);
  assert.equal(at.layout, "none", `no view for it: ${at.layout}`);
  assert.ok(!/your turn/i.test(at.text) && !/click the page/.test(at.text), "the question is asked in the chat, not over an empty tab");
  assert.deepEqual(errors, []);
});

test("a page the agent opened, with its question asked in words, is not drawn in a chat task - nothing on the page is the owner's", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const painter = await harness.newPage();
  await painter.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  await painter.setContent(FARES);
  const frame = await painter.screenshot({ type: "jpeg", quality: 80, encoding: "base64" });
  await painter.close();
  const { page, errors } = await open(harness, "asked", frame);
  const at = await settled(page);
  // the owner, 2026-11-05: "for browser we don't really want to show it unless they need login" - a question in words is answered in the chat
  assert.equal(at.layout, "none", `the page is not drawn for a question in words: ${at.layout}`);
  assert.ok(!/your turn/i.test(at.text) && !/click the page and type/.test(at.text), "a question in words leaves the page the agent's");
  assert.deepEqual(errors, []);
});
