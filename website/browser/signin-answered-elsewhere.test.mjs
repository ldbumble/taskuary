import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A SIGN-IN ANSWERED BY TASKUARY ITSELF LEAVES THE PAGE AT ONCE (the browser-agent walk, 2026-11-04). The saved sign-in was typed, the
   agent told and at work again - and the open task still showed the question and "your turn - type" over a page already signed in, the
   agent's next answer unseen until a reload: the pane read the conversation again only while it knew of a turn of its own. Here the ask
   is answered on the server, as the vault's fill, the fill page and the page watch answer it - not by any press on this page. Invented site
   and task only. */
test("a sign-in answered on the server clears from the open task without a reload", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (path, body = {}) => page.evaluate(async (path, body) => (await fetch(path, { method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), path, body);
  const made = await call("/api/fixture/signin/terminal-ask");
  assert.ok(made.taskId, JSON.stringify(made));
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const ask = '[data-tq-asking="signin:northwind.example"]';
  await page.waitForSelector(ask, { visible: true, timeout: 30000 })
    .catch(async () => assert.fail(`no sign-in line: ${JSON.stringify(errors)} ${(await page.evaluate(() => document.body.innerText)).slice(0, 1500)}`));
  // answered off this page - a fetch the page itself did not make through its own answer road
  const r = await harness.newPage().then(async (other) => {
    await other.goto(harness.ui, { waitUntil: "domcontentloaded" });
    const out = await other.evaluate(async (id) => (await fetch(`/api/tasks/${id}/worker/answer`, { method: "POST",
      body: JSON.stringify({ request_id: "signin:northwind.example", text: "Signed in" }),
      headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), made.taskId);
    await other.close(); return out;
  });
  assert.equal(r.delivered, true, JSON.stringify(r));
  await page.waitForFunction((ask) => !document.querySelector(ask), { timeout: 15000 }, ask)
    .catch(() => assert.fail("the answered sign-in still stands on the open task"));
  assert.deepEqual(errors, []);
});
