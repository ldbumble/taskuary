import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A GENERAL AGENT STARTING IS ONE LINE. Started from the Assistant, the task card opened under "researcher is working" on a pane
   about 300px tall with nothing in it but a spinner at its foot, for as long as the CLI took to come up (the owner, 2026-10-21).
   Until its first answer the pane is as high as what it shows - "Starting Taskuary on Codex…" (the agent goes by Taskuary, never its profile - 2026-10-28) - and the room comes with
   the answer. The fixture is the session the server started: /api/terminals lists it live, /assistant has it busy and silent. */
test("a general agent that has said nothing yet is one line, not a tall empty pane", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Brief me before the vendor meeting", Summary: "Read Gail Moreno's mail about the renewal and brief me",
      Kind: "general", Assignee: "agent:researcher" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  const ses = { sid: "g1", taskId: made.taskId, alive: true, busy: true, mode: "chat", cli: "taskuary", agent: "researcher",
                provider: "Codex", trace: [], trace_revision: 0 };
  let answered = false;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const p = new URL(req.url()).pathname, json = (body) => req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant`) return void json(answered
      ? { messages: [{ id: "a1", role: "assistant", createdAt: new Date().toISOString(),
                       content: [{ type: "text", text: "Gail wants the renewal terms settled before Thursday.\n\n".repeat(12) }] }],
          session: { ...ses, busy: false }, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] }
      : { messages: [], session: ses, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] });
    if (req.method() === "GET" && p === "/api/terminals") return void json({ data: [answered ? { ...ses, busy: false } : ses] });
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-starting-line]", { timeout: 20000 });
  const quiet = await page.evaluate(() => ({ line: document.querySelector("[data-tq-starting-line]").innerText,
    pane: document.querySelector("[data-tq-starting]").getBoundingClientRect().height,
    welcome: !!document.querySelector(".tq-aui-welcome") }));
  assert.match(quiet.line, /Starting Taskuary on Codex…/);
  assert.equal(quiet.welcome, false, "no welcome copy over an agent already started");
  // the line, the composer and the pane's own padding - nothing reserved for an answer that has not come
  assert.ok(quiet.pane < 200, `the starting pane should be as high as its line, got ${quiet.pane}px`);

  // ...and the answer gets the room
  answered = true;
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes("renewal terms")),
    { timeout: 20000 });
  const room = await page.$eval(".tq-aui-thread", (el) => el.getBoundingClientRect().height);
  assert.ok(room > 300, `the answer should take the task's room, got ${room}px`);
  assert.equal(await page.$("[data-tq-starting]"), null);
  assert.deepEqual(errors, []);
});
