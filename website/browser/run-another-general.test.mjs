import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* RUN ANOTHER AGENT ON A GENERAL TASK IS A SECOND AGENT (the owner, 2026-10-27: "I hit Run another agent and it just opened the same
   window instead of a new one??? does it mean Continue?"). The box's start dispatched with nothing to say it was another agent, the
   server resumed the stopped one's conversation and, nothing typed, sent nothing: the same chat. The press now asks for a fresh
   conversation (`fresh`, general.new_run - pinned in tests/test_run_another_general.py), and the pane draws the new agent's thread with
   the earlier agent's folded above it. The demo refuses starts, so the dispatch and the new run's reads are answered here. */
const OLD = "The rerun produced", NEW = "Starting over on the parcel list with the county file.";

test("Run another agent on a stopped general agent starts a new conversation and shows it", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/fixture/general/rest", { method: "POST", headers, body: "{}" })).json();
  });
  assert.ok(made.taskId, `no stopped general task: ${JSON.stringify(made)}`);

  // an AI is connected (the demo has none, and greys every start), and once dispatched the new agent is live and has answered
  const ses = { sid: "g2", taskId: made.taskId, alive: true, busy: false, mode: "assistant", cli: "taskuary", agent: "general",
                provider: "Claude Code", trace: [], trace_revision: 0 };
  let dispatched = null, earlier = null;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const p = new URL(req.url()).pathname, json = (body) => req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "GET" && p === "/api/capabilities") return void json({ coding: false, ai: true, mail: true, send: {} });
    if (req.method() === "GET" && p === "/api/agents") return void json({ data: [{ Name: "general", Kind: "general" }], config: {}, models: {},
      general_brains: [{ pick: "cli:claude", label: "Claude Code" }], brain_list: [], coding_ready: false });
    if (req.method() === "POST" && p === `/api/tasks/${made.taskId}/dispatch`) {
      dispatched = JSON.parse(req.postData() || "{}");
      return void json({ dispatch: "assistant", agent: "Claude Code", started: true, existing: false, taskId: made.taskId, session: ses });
    }
    if (dispatched && req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant`) return void json({
      messages: [{ id: "comment-900", role: "assistant", createdAt: new Date().toISOString(), content: [{ type: "text", text: NEW }] }],
      earlier, session: ses, starting: false, providers: [{ id: "cli:claude", label: "Claude Code", model: "" }] });
    if (dispatched && req.method() === "GET" && p === "/api/terminals") return void json({ data: [ses] });
    page.fixtureRequestGuard(req);
  });
  // the earlier agent's turns, as the server reads them after the new run's row (general.earlier)
  earlier = await page.evaluate(async (id) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token") };
    return (await (await fetch(`/api/tasks/${id}/assistant`, { headers })).json()).messages;
  }, made.taskId);
  assert.ok(earlier.some((m) => m.content[0].text.startsWith(OLD)), "the fixture's stopped agent has answered");

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  // the finished agent's chat is the rest of its Result, behind the Result heading (the owner, 2026-10-27: "click Result to see more")
  await page.waitForSelector("[data-tq-result-summary]", { timeout: 30000 });
  await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.click());
  await page.waitForFunction((old) => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes(old)), { timeout: 30000 }, OLD);

  // Run another agent rides in the row's More - the row is up once it has its ▾ (Mark done folds into it beside Back, the nav pill)
  await page.waitForSelector('[data-tq-row] [data-tq-more]', { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 1000));
  let press = await page.$('[data-tq-row] button[data-tq-verb$="run-another"]');
  for (const more of await page.$$("[data-tq-row] [data-tq-more]")) {
    if (press) break;
    await more.click();
    press = await page.waitForSelector('[role=menuitem][data-tq-verb$="run-another"]', { timeout: 1500 }).catch(() => null);
    if (!press) { await page.keyboard.press("Escape"); await new Promise((r) => setTimeout(r, 400)); }
  }
  assert.ok(press, `no Run another agent on a stopped general agent: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button, [role=menuitem]")].map((b) => `${b.getAttribute("data-tq-verb")}=${b.innerText}`).join(", "))}`);
  assert.equal(await press.evaluate((el) => el.getAttribute("aria-disabled")), null, "Run another agent is greyed with an AI connected");
  await new Promise((r) => setTimeout(r, 400));     // the menu is still opening
  await press.click();
  await page.waitForSelector("[data-tq-run-form] [data-tq-agent-start=general]:not([disabled])", { timeout: 20000 })
    .catch(async () => assert.fail(`no box to start the new agent from: ${await page.evaluate(() => document.querySelector("[data-tq-run-form]")?.outerHTML.slice(0, 3000))}`));
  // ...the box scrolls itself into view smoothly, so the press is the button's own click, not a point that may have moved
  await page.$eval("[data-tq-run-form] [data-tq-agent-start=general]", (b) => b.click());

  await page.waitForFunction(() => document.querySelector("[data-tq-earlier-run]"), { timeout: 30000 })
    .catch(async () => assert.fail(`the new run was not drawn: dispatched ${JSON.stringify(dispatched)}`));
  assert.equal(dispatched?.fresh, true, `Run another agent did not ask for a new agent: ${JSON.stringify(dispatched)}`);
  await page.waitForFunction((now) => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes(now)), { timeout: 30000 }, NEW);
  const seen = await page.evaluate(() => ({
    thread: [...document.querySelectorAll(".tq-aui-thread .tq-aui-agent, .tq-aui-thread .tq-aui-user")].map((m) => m.innerText).join("\n"),
    fold: document.querySelector("[data-tq-earlier-run] summary")?.innerText || "",
    folded: document.querySelector("[data-tq-earlier-run]")?.textContent || "" }));
  assert.ok(!seen.thread.includes(OLD), `the earlier agent's chat is still the thread: ${seen.thread}`);
  assert.match(seen.fold, /The earlier agent's conversation · 2 messages/);
  assert.ok(seen.folded.includes(OLD), "the earlier agent's conversation is kept on the task");
  assert.deepEqual(errors, []);
});
