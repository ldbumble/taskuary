import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* SEND ON CLOSE OUT CLOSES THE TASK ONCE IT WENT (the owner, 2026-10-29: "wait until the send actually succeeds, then close the task").
   A send that failed leaves the task open, on Close out, with the error showing - the page never swapped under the owner's hand
   (2026-10-27: "I hit send on close out and ... it reopened the task page???"). A send that went closes it: Mark done's own road. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Send on Close out: a failed send stays on Close out with its error, one that went closes the task", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the demo sends nothing, so the channel's answer is played here: the first press refused, the second one gone with its receipt -
  // what follows a send (the close) is the app's own, against the fixture
  let refuse = true, recorded = 0;
  page.off("request", page.fixtureRequestGuard);   // one handler answers every request: the fixture's guard for all but this one
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      // ...one that went is recorded as sent on the server, as a real Send leaves it: the close after it asks whether anything on the
      // task still waits for a Send (concierge.close_after_send), and a reply left pending would keep it open
      if (!refuse) recorded = (await fetch(`${harness.fixtureApi}/api/fixture/review/${rid}/sent`, { method: "POST", body: "{}",
        headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } })).status;
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(refuse
        ? { ok: false, status: "pending", sent: null, send_error: "the mailbox refused it" }
        : { ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const taskOf = async (id) => (await (await fetch(`${harness.fixtureApi}/api/tasks/${id}`, { headers: { "X-Taskuary-Token": harness.token } })).json()).task;
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting for Send");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"] [data-tq-closeout]`, { timeout: 20000 });
  await sleep(2500);
  const mainOf = () => page.$eval("[data-tq-task-body]", (e) => e.getAttribute("data-tq-main")).catch(() => null);
  assert.equal(await mainOf(), "close", "a drafted reply opens on Close out");
  const press = () => page.evaluate(() => {
    const b = [...document.querySelectorAll("[data-tq-closeout] button")].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    if (!b) return false; b.click(); return true;
  });

  assert.ok(await press(), "Close out offers Send");
  await page.waitForFunction(() => /The reply was not sent/.test(document.querySelector("[data-tq-closeout]")?.textContent || ""), { timeout: 15000 });
  const seen = new Set();
  for (let i = 0; i < 6; i++) { await sleep(500); seen.add(await mainOf()); }
  assert.deepEqual([...seen], ["close"], `a failed send stays on Close out: ${[...seen]}`);
  assert.notEqual(String((await taskOf(inv.TaskId)).Status), "done", "a failed send closes nothing");

  refuse = false;
  assert.ok(await press(), "Send again, once the error is read");
  let status = "";
  for (let i = 0; i < 40 && status !== "done"; i++) { await sleep(500); status = String((await taskOf(inv.TaskId)).Status); }
  const said = async () => (((await (await fetch(`${harness.fixtureApi}/api/tasks/${inv.TaskId}`, { headers: { "X-Taskuary-Token": harness.token } })).json()).comments) || [])
    .slice(-3).map((c) => c.Body).join(" / ");
  assert.equal(recorded, 200, "the reply that went recorded as sent");
  assert.equal(status, "done", `the send that went closed the task - it says: ${status === "done" ? "" : await said()}`);
  await page.waitForFunction((id) => !document.querySelector(`[data-tq-task-page="${id}"] [data-tq-closeout]`), { timeout: 15000 }, inv.TaskId);
  assert.deepEqual(errors, []);
});
