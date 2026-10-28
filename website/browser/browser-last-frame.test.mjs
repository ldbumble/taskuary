import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE BROWSER'S LAST FRAME, KEPT ONLY WHEN THE SESSION STOPPED ON A HELD OR FAILED ACT (owner-approved, 2026-10-25). The browser closes
   with its session, so a task that ended waiting on Approve showed nothing of the page it stood on. The fixture ends three sessions
   through the real close: one on a held act, one on an act that failed when approved, one normally. Invented site and task only. */
test("the last frame is shown in the chat with a plain caption on a held or failed act, and not on a normal end", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const end = (how) => page.evaluate(async (how) => (await fetch("/api/fixture/browser/last-frame", { method: "POST", body: JSON.stringify({ end: how }),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), how);
  const open = async (id, said) => {
    await page.evaluate((id) => { window.location.hash = `task=${id}`; }, id);
    // the session is over: where an act still waits it leads the page and the chat is one press away, under its Result heading
    const chat = `() => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes(${JSON.stringify(said)}))`;
    // ...in the three sections: the Agent's tab, then its one Full results and record press (2026-10-27)
    const folded = () => document.querySelector("[data-tq-section-tab=agent]") || document.querySelector('[data-tq-full-result][aria-expanded="false"]')
      || [...document.querySelectorAll('[aria-expanded="false"]')].find((h) => /^(Result|Agent work)/.test(h.innerText.trim()));
    await page.waitForFunction(`(${chat})() || ((${folded})()?.click(), false)`, { timeout: 30000, polling: 500 });
    await new Promise((r) => setTimeout(r, 800));
    // ...in the chat, under the answer (the Result's summary may list the same frame under What it made)
    return page.evaluate(() => ({ names: [...document.querySelectorAll(".tq-aui-agent .tq-published-name b")].map((b) => b.textContent.trim()) }));
  };

  for (const [how, caption, said] of [["held", "Where the browser was when it waited for you", "waiting on your Approve"],
    ["failed", "Where the browser was when it stopped", "did not go through"]]) {
    const made = await end(how);
    assert.ok(made.taskId, JSON.stringify(made));
    const seen = await open(made.taskId, said);
    assert.deepEqual(seen.names, [caption], `${how}: ${JSON.stringify(seen)}`);
    // ...drawn as a picture, under the answer, open
    await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-agent .tq-published-picture img")].some((i) => i.complete && i.naturalWidth > 0),
      { timeout: 10000 });
  }
  const normal = await end("normal");
  assert.deepEqual((await open(normal.taskId, "I read the invoice page.")).names, [], "a normal end keeps nothing");
  assert.deepEqual(errors, []);
});
