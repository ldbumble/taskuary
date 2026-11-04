import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

// TQ-0420: "New task for the agent" with no repository created the task, navigated to it, and
// showed an empty box. The workspace gated its whole body - welcome, composer, and the effect that
// asks the typed question - on a live session, and a task that has never run has none.
test("a general task with no session opens as a usable chat and asks its question", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });

  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Research Instinct", Summary: "Research what people say about Instinct online.",
      Kind: "general", Tags: "ask:assistant" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(".tq-aui-composer textarea", { timeout: 20000 });

  // the pane is a chat, not an empty box: the composer takes input with nothing running
  assert.equal(await page.$eval(".tq-aui-composer textarea", (el) => el.disabled), false);
  // ...once the page has laid out the turn it started: the first frame is as high as what it holds, and "Working on this…" is one line
  // where the band was three (2026-11-04)
  const box = await page.waitForFunction(() => { const h = document.querySelector(".tq-aui-thread")?.getBoundingClientRect().height || 0; return h > 300 && h; },
    { timeout: 5000, polling: "raf" }).then((h) => h.jsonValue()).catch(() => page.$eval(".tq-aui-thread", (el) => el.getBoundingClientRect().height));
  assert.ok(box > 300, `the chat should take the task page's room, got ${box}px`);

  // ...and the question the owner typed is asked, by the thread, as the first message
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-user")]
    .some((m) => m.innerText.includes("Research what people say about Instinct online.")), { timeout: 20000 });

  // asked once and only once - the tag is stripped on the server as it goes (newTask.js)
  const after = await page.evaluate(async (id) => (await fetch(`/api/tasks/${id}`, {
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), made.taskId);
  assert.doesNotMatch(String(after.task?.Tags || ""), /ask:assistant/);
  assert.deepEqual(errors, []);
});

// A TASK'S CHAT, made by the fixture and answered by the page's own request hook: `state()` is what /assistant serves at each read
const chatTask = async (harness, t, title, state, extra = {}) => {
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async (Title, extra) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({ Title, Summary: Title, Kind: "general", ...extra }) })).json();
  }, title, extra);
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const p = new URL(req.url()).pathname, json = (body) => req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant`) return void json(state());
    if (req.method() === "GET" && p === "/api/terminals") return void json({ data: state().session ? [{ ...state().session, taskId: made.taskId }] : [] });
    page.fixtureRequestGuard(req);
  });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  return { page, errors, made };
};

/* "WORKING ON THIS…" (the closeout-in-chat spec, 2026-11-04): while the agent works there is one quiet line, its steps folded under it
   and opened on a press - no live lines scrolling by. When the turn ends it says what this is about, what it did and the next steps;
   an earlier turn's summary folds to "What I did". */
test("working folds the steps", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const trace = [{ type: "tool_call", name: "WebSearch", detail: { tool_call_id: "c1", args: { query: "Northwind renewal terms" } } },
                 { type: "tool_result", name: "WebSearch", detail: { tool_call_id: "c1" } },
                 { type: "tool_call", name: "WebFetch", detail: { tool_call_id: "c2", args: { url: "https://vendor.example/terms" } } }];
  const ses = { sid: "g1", alive: true, busy: true, mode: "chat", cli: "taskuary", provider: "Codex", trace, trace_revision: 1 };
  const said = (id, text) => ({ id, role: "assistant", createdAt: new Date().toISOString(), content: [{ type: "text", text }] });
  const first = { ...said("a1", "I read Gail's note."), summary: { about: "Gail Moreno asked for the renewal terms.", did: "Read her note.", on_you: [], nothing_left: false } };
  let done = false;
  const { page, errors, made } = await chatTask(harness, t, "Brief me on the Northwind renewal", () => done
    ? { messages: [first, { id: "u2", role: "user", content: [{ type: "text", text: "and the dates?" }] },
                   { ...said("a2", "The terms are on the vendor's page."), summary: { about: "Gail Moreno wants the renewal terms before Thursday.",
                     did: "Found the terms on vendor.example and wrote them up.", on_you: [], nothing_left: true } }],
        session: { ...ses, busy: false }, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] }
    : { messages: [first, { id: "u2", role: "user", content: [{ type: "text", text: "and the dates?" }] }],
        session: ses, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] }, { Assignee: "agent:researcher" });

  await page.waitForSelector(".tq-aui-thread [data-tq-working]", { timeout: 20000 });
  const working = await page.evaluate(() => ({
    lines: [...document.querySelectorAll(".tq-aui-thread [data-tq-working]")].map((el) => el.querySelector("summary")?.innerText || el.innerText),
    band: !!document.querySelector(".tq-aui-band, .tq-aui-thinking"),
    stepsShown: [...document.querySelectorAll(".tq-aui-thread [data-tq-working] .tq-aui-step")].filter((s) => s.checkVisibility()).length,
    steps: document.querySelectorAll(".tq-aui-thread [data-tq-working] .tq-aui-step").length }));
  assert.equal(working.lines.length, 1, `one working line, got ${JSON.stringify(working.lines)}`);
  assert.match(working.lines[0], /Working on this…/);
  assert.equal(working.band, false, "no second line saying it is working");
  assert.ok(working.steps >= 2, "the steps are there, under the line");
  assert.equal(working.stepsShown, 0, "...folded");
  await page.click(".tq-aui-thread [data-tq-working] summary");
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-thread [data-tq-working] .tq-aui-step")].some((s) => s.checkVisibility()),
    { timeout: 5000 });

  // ...the turn ends in three parts, and the earlier one folds to what it did
  done = true;
  await page.waitForFunction(() => document.querySelectorAll("[data-tq-summary]").length === 2 && !document.querySelector(".tq-aui-thread [data-tq-working]"), { timeout: 20000 });
  const parts = await page.evaluate(() => [...document.querySelectorAll("[data-tq-summary]")].map((el) => ({
    folded: el.getAttribute("data-tq-summary"), text: el.innerText })));
  assert.equal(parts[0].folded, "folded");
  assert.match(parts[0].text, /What I did/);
  assert.doesNotMatch(parts[0].text, /What this is about|Next steps/);
  assert.equal(parts[1].folded, "open");
  for (const h of [/What this is about/, /before Thursday/, /What I did/, /Found the terms on vendor\.example/, /Next steps/, /Nothing left to do here/])
    assert.match(parts[1].text, h);
  assert.ok(made.taskId);
  assert.deepEqual(errors, []);
});

/* WHEN THE AGENT NEEDS THE OWNER IT SAYS SO IN PLAIN WORDS (the spec, 2026-11-04): its question is a line of the conversation, not a card
   headed "Taskuary asked you something", and there are choice buttons only when it gave real choices */
test("an agent's question reads in plain words", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const q = "I found the login email from vendor.example and I'm not sure what to do next: should I send it to Ray, or wait for Gail?";
  const { page, errors } = await chatTask(harness, t, "Sort out the vendor login", () => ({
    messages: [{ id: "a1", role: "assistant", content: [{ type: "text", text: `I read the thread.\n\n${q}` }] }],
    asking: { request_id: "r9", kind: "input_needed", text: q, choices: [], sid: "p1" },
    session: null, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] }), { Tags: "ask:assistant" });
  await page.waitForSelector('[data-tq-asking="r9"]', { visible: true, timeout: 20000 });
  const ask = await page.$eval('[data-tq-asking="r9"]', (el) => ({ text: el.innerText.trim(), buttons: el.querySelectorAll("button").length }));
  assert.equal(ask.text, q, "the question, in the agent's own words, and nothing else");
  assert.equal(ask.buttons, 0, "no choices were given, so no buttons");
  assert.deepEqual(errors, []);
});
