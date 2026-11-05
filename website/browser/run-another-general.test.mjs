import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* RUN ANOTHER AGENT ON A GENERAL TASK IS A SECOND AGENT (the owner, 2026-10-27: "I hit Run another agent and it just opened the same
   window instead of a new one??? does it mean Continue?"). The box's start dispatched with nothing to say it was another agent, the
   server resumed the stopped one's conversation and, nothing typed, sent nothing: the same chat. The press now asks for a fresh
   conversation (`fresh`, general.new_run - pinned in tests/test_run_another_general.py), and the pane draws the new agent's thread with
   the earlier agent's folded above it. The demo refuses starts, so the dispatch and the new run's reads are answered here. */
const OLD = "The rerun produced", NEW = "Starting over on the parcel list with the county file.";
/* ...AND ON A CHAT TASK THERE IS NO RUN ANOTHER AT ALL (the owner, 2026-11-05: "we can remove those 2 buttons like continue agent or start new
   agent. Just type and it continues"): a stopped general agent's chat shows its turns and keeps its box, and neither Run another agent, its
   stronger twin nor Continue is on the row, the strip or behind a menu. Typing on is continue-shows-turn's. */
test("a stopped general agent's chat offers no Run another or Continue - its box is the way on", { timeout: 180000 }, async (t) => {
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
  // a general task's Agent section is ONE chat (the owner, 2026-11-04): the finished agent's turns are on screen, no Result to press first
  await page.waitForFunction((old) => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes(old)), { timeout: 30000 }, OLD);

  await page.waitForSelector('[data-tq-row] [data-tq-more], [data-tq-row] [data-tq-next], [data-tq-pane-moves] button', { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 1000));
  const gone = '[data-tq-verb$="run-another"], [data-tq-verb$="strong-again"], [data-tq-verb$="continue"]';
  const seen = [];
  const look = async () => seen.push(...await page.evaluate((sel) => [...document.querySelectorAll(sel)].map((b) => b.getAttribute("data-tq-verb") + "=" + b.innerText), gone));
  await look();
  for (const more of await page.$$("[data-tq-row] [data-tq-more]")) {
    await more.click(); await new Promise((r) => setTimeout(r, 600)); await look();
    await page.keyboard.press("Escape"); await new Promise((r) => setTimeout(r, 300));
  }
  assert.deepEqual(seen, [], "no Run another, stronger twin or Continue on a chat task");
  assert.ok(await page.$(".tq-aui-chat .tq-aui-input"), "the chat's box is there to type on");
  assert.equal(dispatched, null, "nothing was started");
  assert.deepEqual(errors, []);
});
