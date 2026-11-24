// WHAT A PRESS DID, ON WHAT WAS PRESSED, BEFORE THE WALK MOVES (the owner, 2026-11-23, walk 11 F6: "Not for me" and "Send and close" left the
// screen at once with nothing saying what the press did) - and ONE TOOLBAR for every task state (F7: held for a stranger the row read "Close with
// a note / Find a time / Share / ▾", at work "Change ▾" and none of those). Drawn through the real row components, server-rendered.
import test, { mock } from "node:test";
import assert from "node:assert/strict";

const page = async () => {
  // ...the loop held open while esbuild works: its service is unref'd, and on Node 22 the runner saw an empty loop and gave up on the build
  const hold = setInterval(() => {}, 1000);
  try { return await page_(); } finally { clearInterval(hold); }
};
const page_ = async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
    import ActionRow from "./src/ActionRow.jsx"; import { TaskButtons } from "./src/TaskRow.jsx";
    export * from "./src/actionRow.js"; export * from "./src/pressResult.js"; export { taskMoves } from "./src/taskMoves.js";
    export const row = () => renderToStaticMarkup(<ActionRow inline />);
    export const strip = (verbs) => renderToStaticMarkup(<TaskButtons verbs={verbs} act={() => {}} />);` },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' },
    loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
  // ...written to a file of its own: a stack through a data: URL is the whole bundle, once per frame
  const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
  const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-press-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
  return import(pathToFileURL(f).href);
};
// ...built on first use inside a test, never at import: a build started before the runner's first test left its promise pending on Node 22
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };
const words = { label: (k, s) => `${k}${s ? `:${s}` : ""}`, hint: () => "", doneHint: "", natTitle: "", repo: "Pick", repoHint: "" };
const noop = () => {};
// ...only setTimeout is mocked: Node 22 reads enable({apis}) and took the old array form as "every timer" - setImmediate too, so the awaited
// beat never came; Node 20.10 knows only the array
const onlyTimeouts = () => { try { mock.timers.enable({ apis: ["setTimeout"] }); } catch { mock.timers.enable(["setTimeout"]); } };
const run = { reopen: noop, done: noop, note: noop, nat: noop, remind: noop, watch: noop, hand: noop, reshape: noop, kind: noop, priority: noop, repo: noop };

test("each press that moves the walk on shows what it did on its own button first, then moves - Back and Next greyed through the beat", async () => {
  const m = await P;
  onlyTimeouts();
  try {
    for (const [verb, label, word] of [["nat", "Not for me", "Not for you - filed"], ["done", "Mark done", "Done"], ["close-note", "Close with a note", "Done · note kept"],
      ["watch", "Watch it", "Watching"]]) {
      const moved = [];
      m.put(`task:${verb}`, [{ id: verb, group: "more", label, run: async () => { await m.pressBeat(verb); moved.push(verb); } }], "TQ-0001", `task:${verb}`);
      m.rowTable(`task:${verb}`);
      m.press(verb);
      assert.equal(m.pressNow().word, word, verb);
      assert.equal(moved.length, 0, `${verb}: no move before the result is shown`);
      assert.match(m.row(), new RegExp(`data-tq-verb="${verb}"[^>]*><span data-tq-press-result="" role="status">${word}</span>`), `${verb}: on the button pressed`);
      assert.equal(m.pressNow().beating, true, "Back and Next stand greyed (useBeat)");
      mock.timers.tick(m.PRESS_BEAT);
      await new Promise((r) => setImmediate(r));
      assert.deepEqual(moved, [verb], `${verb}: then the move`);
      assert.equal(m.pressNow().beating, false);
      m.put(`task:${verb}`, null);
    }
    // ...the same verb on the next item is not the one pressed: its button keeps its own word
    m.put("task:a", [{ id: "nat", group: "more", label: "Not for me", run: () => m.pressBeat("nat") }], "TQ-0002", "task:a"); m.rowTable("task:a"); m.press("nat");
    m.put("task:a", null); m.put("task:b", [{ id: "nat", group: "more", label: "Not for me", run: noop }], "TQ-0003", "task:b"); m.rowTable("task:b");
    assert.doesNotMatch(m.row(), /data-tq-press-result/, "the next task's Not for me is not the one pressed");
    mock.timers.tick(m.PRESS_BEAT); m.put("task:b", null);
    // ...a press that failed takes its word back (the error says why) - and Remind me says the day it put the task off to
    assert.equal(m.pressWord("remind", { day: "tomorrow" }), "Back tomorrow");
    assert.equal(m.pressWord("r12:send_close"), "Sent · closed");
    m.pressOver(); assert.equal(m.pressNow(), null);
  } finally { mock.timers.reset(); }
});

test("one toolbar: held, at work, after a restart and closed wear the same task buttons in the same order - what does not apply is greyed, never gone", async () => {
  const m = await P;
  const states = { held: {}, working: { live: true }, restarted: { waitingDraft: true }, closed: { closed: true } };
  const order = (s) => m.taskButtons(m.splitRow(m.rowOf({ list: [...m.taskMoves(s, run, words), { id: "share", group: "more", label: "Share" }], ref: "" }), { open: "agent" }).by)
    .map((x) => (x.change ? `change[${x.change.map((v) => v.id)}]` : x.v.id === "reopen" ? "done" : x.v.id));
  const want = order(states.held);
  assert.deepEqual(want, ["done", "close-note", "remind", "nat", "watch", "share", "change[reshape,kind,priority]"]);
  for (const [k, s] of Object.entries(states)) assert.deepEqual(order(s), want, k);
  const off = (s) => m.taskMoves(s, run, words).filter((v) => v.disabled).map((v) => `${v.id}: ${v.why}`);
  assert.deepEqual(off(states.held), [], "held for a stranger, every move of the task's own is live");
  assert.deepEqual(off(states.working), ["close-note: an agent is working - Mark done stops it and closes the task"]);
  assert.ok(off(states.closed).length >= 6 && off(states.closed).every((x) => x.endsWith("the task is closed - reopen it first")), "closed: Reopen alone lit");
});

test("Mark done's result stays on the closed row - a greyed ✓ Done beside Reopen while he is on the task, never gone with the button", async () => {
  // the owner, 2026-11-24: "Done" stood on Mark done for a beat, then the closed task's row drew without it and the result vanished
  const m = await P;
  for (const [verb, word] of [["done", "✓ Done"], ["close-note", "✓ Done · note kept"]]) {
    const r = m.rowOf({ list: m.taskMoves({ closed: true, closedWith: verb }, run, words), ref: "" });
    assert.deepEqual(r.decide.slice(0, 2).map((v) => v.id), ["closed-result", "reopen"], verb);
    assert.deepEqual([r.decide[0].label, r.decide[0].disabled], [word, true], verb);
    assert.match(m.strip(m.taskMoves({ closed: true, closedWith: verb }, run, words)), new RegExp(`disabled=""[^>]*data-tq-verb="closed-result"[^>]*>${word}</button><button[^>]*data-tq-verb="reopen"`));
  }
  // ...kept by task while the page is open, so the task opened again (unfolded, Back onto it) still says it - and forgotten once it is seen open
  m.closedBy(7, "done");
  assert.equal(m.closedResult(7, false), "", "before the close lands the task still reads open - nothing yet, nothing forgotten");
  assert.equal(m.closedResult(7, true), "done"); assert.equal(m.closedResult(7, true), "done", "opened again, still its result");
  assert.equal(m.closedResult(7, false), ""); assert.equal(m.closedResult(7, true), "", "reopened by anyone, a later close is not his press");
  // ...closed by anything else, or open again, there is no result to keep: Reopen alone leads
  for (const s of [{ closed: true }, { closedWith: "done" }]) assert.ok(!m.taskMoves(s, run, words).some((v) => v.id === "closed-result"), JSON.stringify(s));
});

test("held for a sender he has not trusted, Trust is the row's own move - first on the strip, wherever the chat that says why is folded", async () => {
  // walk 14, 2026-11-24: opened from the rail the held task's one Trust sat in its folded Agent pane ("Agent not started"), nothing on screen moved it
  const m = await P, trusted = [], go = { ...run, trust: () => trusted.push(1) };
  const held = m.taskMoves({ trust: { label: "Trust Omar Keller", hint: "starts it" } }, go, words);
  const r = m.rowOf({ list: held, ref: "" });
  assert.equal(r.decide[0].id, "trust"); assert.equal(r.decide[0].label, "Trust Omar Keller");
  assert.ok(!r.decide.some((v) => v.id === "done"), "Mark done does not lead over the move that unblocks the task");
  assert.match(m.strip(held), /data-tq-verb="trust"[^>]*>(<[^>]+>)*Trust Omar Keller/);
  held[0].run(); assert.equal(trusted.length, 1);
  const busy = m.taskMoves({ trust: { label: "Trust Omar Keller", busy: true } }, go, words)[0];
  assert.deepEqual([busy.label, busy.disabled], ["Starting…", true]);
  for (const s of [{}, { closed: true, trust: { label: "Trust Omar Keller" } }]) assert.ok(!m.taskMoves(s, go, words).some((v) => v.id === "trust"), JSON.stringify(s));
});

test("the folded group is named - never a bare ▾ - on the task's strip and on the row", async () => {
  const m = await P;
  // a tucked move (Hand it to a person with no AI) always rides in the fold, so the fold is drawn
  const strip = m.strip([...m.taskMoves({ manual: true }, run, words)]);
  assert.match(strip, /data-tq-more="task"[^>]*>More ▾<\/button>/);
  m.put("task:z", m.taskMoves({ manual: true }, run, words), "TQ-0009", "task:z"); m.rowTable("task:z");
  const row = m.row(); m.put("task:z", null);
  assert.match(row, /class="tq-ab s tq-cl-more"[^>]*>(More|Change) ▾<\/button>/);
  for (const html of [strip, row]) assert.doesNotMatch(html, />▾<\/(button|span)>/, "no bare ▾");
});
