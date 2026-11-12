import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A GENERAL AGENT STARTING IS ONE LINE. Started from the Assistant, the task card opened under "researcher is working" on a pane
   about 300px tall with nothing in it but a spinner at its foot, for as long as the CLI took to come up (the owner, 2026-10-21).
   Until its first answer the pane is as high as what it shows - "Starting Agent on Codex…" (the agent goes by Agent, never its profile - F32, 2026-11-08) - and the room comes with
   the answer. The fixture is the session the server started: /api/terminals lists it live, /assistant has it busy and silent. */
test("a general agent that has said nothing yet is one line in its chat, the box at its foot", { timeout: 180000 }, async (t) => {
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

  // mode "assistant" is what a general session is (general.GeneralSession.mode): "chat" was no real mode, and since every task became Came
  // from and its one chat (2026-11-06) any other live mode is a coding terminal and opens CodingChat (taskLayout.liveTerminal)
  const ses = { sid: "g1", taskId: made.taskId, alive: true, busy: true, mode: "assistant", cli: "taskuary", agent: "researcher",
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
    // ...and the chat itself is the server's one list (conversation.items): the turn at work, then the answer in that same item
    const turn = { id: "t:0:0", kind: "turn", at: "", steps: [], cards: [], started: Date.now() / 1000 - 3 };
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/conversation`) return void json(answered
      ? { rev: "b", items: [{ ...turn, state: "done", ended: Date.now() / 1000, text: "Gail wants the renewal terms settled before Thursday.\n\n".repeat(12) }], pending: [], working: false, started: null }
      : { rev: "a", items: [{ ...turn, state: "starting", text: "", ended: null }], pending: [], working: true, started: turn.started });
    if (req.method() === "GET" && p === "/api/terminals") return void json({ data: [answered ? { ...ses, busy: false } : ses] });
    page.fixtureRequestGuard(req);
  });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-starting-line]", { timeout: 20000 });
  const quiet = await page.evaluate(() => {
    const pane = document.querySelector("[data-tq-starting]").getBoundingClientRect(), box = document.querySelector("[data-tq-starting] [data-tq-one-box]");
    const head = document.querySelector("[data-tq-starting] [data-tq-run-clock], [data-tq-turn] [data-tq-run-clock]"), spin = document.querySelector("[data-tq-starting-line]");
    return { line: spin.innerText, words: /Starting|Working/.test([...document.querySelectorAll("[data-tq-starting], .tq-aui-thread")].map((e) => e.innerText).join(" ")),
             head: head ? head.innerText : "", under: !!head && head.getBoundingClientRect().bottom <= spin.getBoundingClientRect().top + 1,
             welcome: !!document.querySelector(".tq-aui-welcome"),
             foot: box ? pane.bottom - box.getBoundingClientRect().bottom : null, onScreen: !!box && box.getBoundingClientRect().bottom <= innerHeight };
  });
  // ...the turn's own head - who, when, how long - with the spin under it, never a bare "Working..." (the owner, 2026-11-10), and the spin says
  // what we are waiting for (the owner, 2026-11-12: "the ... should say whats it's doing and what are we waiting for")
  assert.equal(quiet.line.trim(), "Waiting for the agent to start", "the spin says what it waits for"); assert.equal(quiet.words, false, "no Starting / Working words anywhere");
  assert.match(quiet.head, /working \d/, "the head and its running clock, from the start"); assert.ok(quiet.under, "the spin under the head");
  assert.equal(quiet.welcome, false, "no welcome copy over an agent already started");
  // ...A GENERAL TASK IS A CHAT TASK, whose box stays at the pane's foot from the first second (the owner, 2026-11-05, aaef3db35: "where is
  // the prompt box"; TaskPage data-tq-agent-room="chat"): the starting pane is no longer one line high, the empty room is the chat's, the
  // one line is the only thing in it. This passed on a fixture mode ("chat") no session has, which made the task a terminal's, not a chat's
  assert.ok(quiet.onScreen, "the box is on screen under the starting line");
  assert.ok(quiet.foot != null && quiet.foot < 40, `the box sits at the chat's foot, ${quiet.foot}px above it`);

  // ...and the answer gets the room
  answered = true;
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-agent")].some((m) => m.innerText.includes("renewal terms")),
    { timeout: 20000 });
  const room = await page.$eval(".tq-aui-thread", (el) => el.getBoundingClientRect().height);
  assert.ok(room > 300, `the answer should take the task's room, got ${room}px`);
  assert.equal(await page.$("[data-tq-starting]"), null);
  assert.deepEqual(errors, []);
});
