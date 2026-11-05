import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE AGENT SECTION IS ONE CHAT (the owner, 2026-11-04: "i want this to be a chat? where is the prompt box and don't need the whole conversation
   thing ... it should be one chat as a agent thinking, then i can say no this is dumb, and the agent retriggers based off new messages and
   rethinks"). On a non-coding task whose agent has finished: triage's reading opens the chat, each turn ends in its summary, the box stands
   under it with no press first - no "The whole conversation", no record under it, no Continue - and what is typed goes to the same session
   in the owner's own words, under YOU. A new mail on the thread is a timestamped line in the stream, the agent's re-think follows it with a
   fresh summary, and the earlier summary folds. Ray Colton, Gail Moreno and Alex Doyle are invented (fixture closeout-in-chat). */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const at = (min) => new Date(Date.now() - min * 60000).toISOString();
const ask = { id: "u1", role: "user", createdAt: at(60), content: [{ type: "text", text: "Answer Ray and keep Gail posted." }] };
const first = { id: "a1", role: "assistant", createdAt: at(59), content: [{ type: "text", text: "Ray's reply is drafted." }],
  summary: { about: "Ray Colton wants the 24-month renewal confirmed before he sends the paper.", did: "Checked the contract dates and drafted Ray a reply.",
    on_you: [], nothing_left: false } };
const WROTE = "One more thing - can the term start April 1 instead of March 1?";
const woke = { id: "b1", role: "user", brief: true, createdAt: at(10), content: [{ type: "text", text: "THE THREAD CHANGED: Ray Colton wrote on this task…" }],
  mail: [{ who: "Ray Colton", channel: "email", at: at(11).replace("T", " ").slice(0, 19), words: WROTE }] };
const again = { id: "a2", role: "assistant", createdAt: at(9), content: [{ type: "text", text: "Redrafted for an April 1 start." }],
  summary: { about: "Ray Colton now asks for the renewal to start April 1.", did: "Read Ray's new mail, checked the notice period and redrafted the reply for April 1.",
    on_you: [], nothing_left: false } };

async function open(t, messages, { streamed = [] } = {}) {
  const h = await startHarness();
  t.after(() => h.close());
  const r = await fetch(`${h.fixtureApi}/api/fixture/task/closeout-in-chat`, { method: "POST", body: JSON.stringify({ kind: "general", drafts: 1, on_you: false }),
    headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
  const made = await r.json();
  assert.ok(made.taskId, JSON.stringify(made));
  const state = { messages: [...messages] };
  const payload = () => ({ messages: state.messages, session: null, starting: false, providers: [{ id: 1, label: "Codex", model: "" }] });
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const p = new URL(req.url()).pathname;
    if (req.method() === "GET" && p === `/api/tasks/${made.taskId}/assistant`)
      return void req.respond({ status: 200, contentType: "application/json", body: JSON.stringify(payload()) });
    // the box's line is the session's next turn: the stand-in agent answers it as the CLI would, and files it on the conversation
    if (req.method() === "POST" && p === `/api/tasks/${made.taskId}/assistant/stream`) {
      const body = JSON.parse(req.postData() || "{}"), reply = "Redone from scratch: the reply now asks Ray which start date he wants.";
      streamed.push(body);
      state.messages = [...state.messages, { id: `u${state.messages.length + 1}`, role: "user", createdAt: new Date().toISOString(), content: [{ type: "text", text: body.text }] },
        { id: `a${state.messages.length + 2}`, role: "assistant", createdAt: new Date().toISOString(), content: [{ type: "text", text: reply }] }];
      return void req.respond({ status: 200, contentType: "application/x-ndjson", body: `${JSON.stringify({ type: "done", reply, payload: payload() })}\n` });
    }
    page.fixtureRequestGuard(req);
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page="${made.taskId}"]`;
  await page.waitForSelector(`${sel} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await page.waitForSelector(`${sel} .tq-aui-thread [data-tq-summary=open]`, { timeout: 20000 });
  await sleep(800);
  return { page, errors, sel, made };
}

test("a finished chat task is one chat with the box under it, no press first", { timeout: 300000 }, async (t) => {
  const { page, errors, sel, made } = await open(t, [ask, first]);
  const m = await page.evaluate((sel) => {
    const q = (s) => [...document.querySelectorAll(`${sel} ${s}`)], input = document.querySelector(`${sel} .tq-aui-input`);
    const reading = document.querySelector(`${sel} .tq-aui-viewport [data-tq-reading=chat]`), msg = document.querySelector(`${sel} .tq-aui-viewport .tq-aui-message`);
    return { box: !!input && !!input.offsetParent && !input.disabled, placeholder: input?.placeholder || "",
      readingFirst: !!reading && !!msg && !!(reading.compareDocumentPosition(msg) & Node.DOCUMENT_POSITION_FOLLOWING),
      readingOutside: q("[data-tq-reading=chat]").filter((e) => !e.closest(".tq-aui-viewport")).length,
      whole: q("[data-tq-full-result]").length, summaryCard: q("[data-tq-result-summary]").length, brief: q("[data-tq-brief]").length,
      continueCard: q("[data-tq-continue-card]").length, cont: q('button[data-tq-verb$="continue"]').length + document.querySelectorAll('[data-tq-row] button[data-tq-verb$="continue"]').length,
      words: q("button").filter((b) => b.offsetParent).map((b) => b.textContent.trim()),
      card: q(`.tq-aui-thread [data-tq-summary=open] [data-tq-review]`).map((e) => Number(e.dataset.tqReview)) };
  }, sel);
  assert.ok(m.box, "the box is there before anything is pressed");
  assert.match(m.placeholder, /^Tell me what's wrong, or ask about anything here/);
  assert.ok(m.readingFirst, "triage's reading opens the chat, above its first turn");
  assert.equal(m.readingOutside, 0, "and is not a block of its own over the chat");
  assert.equal(m.whole, 0, "no The whole conversation / Back to the result");
  assert.equal(m.summaryCard, 0, "no Result summary block over the chat");
  assert.equal(m.brief, 0, "no Taskuary's instructions fold");
  assert.equal(m.cont, 0, `no Continue: the box is continue (${m.words.join(" | ")})`);
  assert.ok(!m.words.includes("Continue"), `no Continue button: ${m.words.join(" | ")}`);
  assert.deepEqual(m.card, made.reviews, "the draft card is in the newest summary's Next steps");
  assert.deepEqual(errors, []);
});

test("a line typed in the box shows under YOU and continues the same session", { timeout: 300000 }, async (t) => {
  const streamed = [], { page, errors, sel } = await open(t, [ask, first], { streamed });
  const words = "no this is dumb, redo it";
  await page.click(`${sel} .tq-aui-input`);
  await page.type(`${sel} .tq-aui-input`, words);
  await page.keyboard.press("Enter");
  await page.waitForFunction((sel, w) => [...document.querySelectorAll(`${sel} .tq-aui-user`)].some((u) => u.innerText.includes(w)), { timeout: 5000 }, sel, words);
  const you = await page.$$eval(`${sel} .tq-aui-user`, (us) => us.map((u) => ({ role: u.querySelector(".tq-aui-role")?.textContent || "", text: u.innerText })));
  assert.ok(you.some((u) => /you/i.test(u.role) && u.text.includes(words)), `under YOU: ${JSON.stringify(you)}`);
  for (let i = 0; i < 20 && !streamed.length; i++) await sleep(200);
  assert.equal(streamed.length, 1, "one turn sent");
  assert.equal(streamed[0].text, words, "the owner's exact words go to the agent");
  await page.waitForFunction((sel) => /Redone from scratch/.test(document.querySelector(`${sel} .tq-aui-thread`)?.innerText || ""), { timeout: 10000 }, sel);
  const order = await page.evaluate((sel, w) => { const t = document.querySelector(`${sel} .tq-aui-thread`).innerText; return [t.indexOf("Ray's reply is drafted"), t.indexOf(w), t.indexOf("Redone from scratch")]; }, sel, words);
  assert.ok(order[0] >= 0 && order[0] < order[1] && order[1] < order[2], `the same conversation, oldest to newest: ${order}`);
  assert.ok(await page.$(`${sel} .tq-aui-input`), "the box is still there for the next line");
  assert.deepEqual(errors, []);
});

test("a new mail is a line in the chat, the re-think follows it, and the earlier summary folds", { timeout: 300000 }, async (t) => {
  const { page, errors, sel } = await open(t, [ask, first, woke, again]);
  await page.waitForSelector(`${sel} [data-tq-chat-arrived]`, { timeout: 10000 });
  const m = await page.evaluate((sel) => {
    const one = (s) => document.querySelector(`${sel} ${s}`), all = (s) => [...document.querySelectorAll(`${sel} ${s}`)];
    const line = one("[data-tq-chat-arrived]"), open = all(".tq-aui-thread [data-tq-summary=open]"), folded = all(".tq-aui-thread [data-tq-summary=folded]");
    const after = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    return { line: line.innerText, arrived: all("[data-tq-chat-arrived]").length, open: open.length, folded: folded.length,
      freshAfter: open.length === 1 && after(line, open[0]), oldBefore: folded.length === 1 && after(folded[0], line),
      fresh: open[0]?.innerText || "", brief: all("[data-tq-brief]").length };
  }, sel);
  assert.equal(m.arrived, 1);
  assert.match(m.line, /^↓ .*\d{1,2}:\d{2}\s?[AP]M · Ray Colton wrote again:/, `the line says when and who: ${m.line}`);
  assert.ok(m.line.includes(WROTE), "in their own words");
  assert.equal(m.open, 1, "one summary open: the newest");
  assert.ok(m.freshAfter, "the re-think's summary follows the new mail");
  assert.match(m.fresh, /redrafted the reply for April 1/);
  assert.ok(m.oldBefore, "the earlier summary is folded, above the new mail");
  assert.equal(m.brief, 0, "the turn's instructions are not drawn");
  assert.deepEqual(errors, []);
});
