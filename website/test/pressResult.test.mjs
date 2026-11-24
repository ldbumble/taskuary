// WHAT A PRESS DID, ON WHAT WAS PRESSED, BEFORE THE WALK MOVES (the owner, 2026-11-23, walk 11 F6: "Not for me" and "Send and close" left the
// screen at once with nothing saying what the press did) - and ONE TOOLBAR for every task state (F7: held for a stranger the row read "Close with
// a note / Find a time / Share / ▾", at work "Change ▾" and none of those). Drawn through the real row components, server-rendered.
import test, { mock } from "node:test";
import assert from "node:assert/strict";

const page = async () => {
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
  const { mkdtempSync, writeFileSync } = await import("node:fs"), { tmpdir } = await import("node:os"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
  const f = join(mkdtempSync(join(tmpdir(), "tq-press-")), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
  return import(pathToFileURL(f).href);
};
// ...built on first use inside a test, never at import: a build started before the runner's first test left its promise pending on Node 22
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };
const words = { label: (k, s) => `${k}${s ? `:${s}` : ""}`, hint: () => "", doneHint: "", natTitle: "", repo: "Pick", repoHint: "" };
const noop = () => {};
const run = { reopen: noop, done: noop, note: noop, nat: noop, remind: noop, watch: noop, hand: noop, reshape: noop, kind: noop, priority: noop, repo: noop };

test("each press that moves the walk on shows what it did on its own button first, then moves - Back and Next greyed through the beat", async () => {
  const m = await P;
  mock.timers.enable(["setTimeout"]);
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
