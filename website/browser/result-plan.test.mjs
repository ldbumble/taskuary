import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

// WHERE IS THE PLAN (the owner, 2026-10-27, a general agent finished on a WhatsApp task, its reply drafted): the Result was the white focus
// over a draft waiting for Send, folded to "finished its work - its record is below" and the agent's last words, and the plan it wrote was
// nowhere on the page. The Result rests on what it did and what it made - the plan by name with its Open - and the Result heading unfolds
// the rest. Since the closeout-in-chat spec (2026-11-04) a general task's chat is home: no Close out section, the draft's card under the
// Result in the Agent, as its Next steps.
test("a finished agent with a draft waiting: the Agent holds its Result, the plan it made with Open, and the draft's card under them", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const fixture = (path, body = {}) => page.evaluate(async (p, b) => (await fetch(p, { method: "POST", body: JSON.stringify(b),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), path, body);
  const made = await fixture("/api/fixture/task/chat-saved", { draft: "Ray Colton signs it on Thursday - keys are at reception from 7.", made: "Snag-list-plan.md" });
  assert.ok(made.taskId, JSON.stringify(made));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`[data-tq-task-page="${made.taskId}"] [data-tq-result-summary] [data-tq-result-made]`, { timeout: 20000 });
  await page.waitForSelector("[data-tq-closeout] textarea[data-tq-draft]", { timeout: 20000 });
  // ...the task opens on its chat: the Result, then the draft waiting, one column - Close out is no section of its own
  assert.equal(await page.$eval("[data-tq-task-body]", (e) => e.getAttribute("data-tq-main")), "agent", "a chat task opens on the Agent");
  assert.equal(await page.$("[data-tq-slot=close]"), null, "no Close out section");
  const order = await page.evaluate(() => { const r = document.querySelector("[data-tq-result-summary]"), c = document.querySelector("[data-tq-closeout] textarea[data-tq-draft]");
    return { below: !!(r.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING), seen: !!r.offsetParent && !!c.offsetParent }; });
  assert.ok(order.below && order.seen, `the draft's card is under the Result, both in view: ${JSON.stringify(order)}`);

  const at = await page.evaluate(() => ({
    summary: document.querySelector("[data-tq-result-summary]").innerText,
    made: [...document.querySelectorAll("[data-tq-result-made] .tq-published-page")].map((e) => e.innerText),
    open: !!document.querySelector("[data-tq-result-made] [data-tq-open]"),
    record: !!document.querySelector("[data-tq-result]"), chat: !!document.querySelector("[data-tq-agent-room]"),
    page: document.querySelector("[data-tq-work]").innerText }));
  assert.match(at.summary, /Ray Colton signs it; the group should be told\./, "what it did, from its write-up");
  assert.match(at.summary, /^Ray Colton signs it[\s\S]*What it found\s+Ray Colton signs the snag list on Thursday\./i, "what it did first, then what it based it on");
  assert.equal(at.made.length, 1, `the plan once - the shown copy and the outputs file are one file: ${JSON.stringify(at.made)}`);
  assert.match(at.made[0], /Snag-list-plan\.md/);
  assert.ok(at.open, "the plan has its Open");
  assert.doesNotMatch(at.page, /finished its work|record is below|is still open/, "no state sentence over the summary");
  assert.ok(!at.record && !at.chat, "the record and the chat are behind the Result heading");

  // Open shows the plan in place
  await page.click("[data-tq-result-made] [data-tq-open]");
  await page.waitForFunction(() => /Keys are at reception from 7/.test(document.querySelector("[data-tq-result-made]")?.innerText || ""), { timeout: 10000 });

  // ...and the Result heading unfolds the rest, and folds it back
  const heading = () => page.$eval('[data-tq-work]', (w) => (w.querySelector('[data-tq-full-result]') || w.querySelector('[data-tq-step="2"]').parentElement).click());
  await heading();
  await page.waitForFunction(() => !document.querySelector("[data-tq-result-summary]") && !!document.querySelector("[data-tq-result] [data-tq-replay]"), { timeout: 10000 });
  await heading();
  await page.waitForSelector("[data-tq-result-summary]", { timeout: 10000 });
  assert.deepEqual(errors, []);
});
