// THE ONE RULEBOOK, ON THE PAGE (the Advisor design, phase A; the owner's rulings, 2026-10-23): every state the design's table names, as
// the server decides it (advisor.decide - tests/test_rulebook.py holds the server side), drawn on the desk canvas and at phone width:
// at most ONE lit button - a send waiting for his yes, Mark done where the agent said it is over, or Next (the owner, 2026-11-15) - found among the buttons the row actually draws - and a line on the strip only where the
// decision carries a fact, never a sentence explaining the obvious move. Invented Northwind people only.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceShown, stripWord } from "../src/advice.js";
import { phoneRow, rowOf } from "../src/actionRow.js";
import { ADVICE_RULE } from "../src/words.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const NEXT = v("next", "next", { label: "Next" });
// what a task's row registers (TaskPage's verbs, by their row ids - buttons.json `row`)
const TASK = [v("reply", "decide", { label: "Reply" }), v("done", "more", { label: "Mark done" }), v("remind", "more", { label: "Remind me" }),
  v("nat", "more", { label: "Not a task" }), v("hand", "more", { label: "Hand it to a person" }), NEXT];

// (state, the decision the server answers, the row drawn, the id lit on the bar or the card)
const MATRIX = [
  ["draft_ready", { verb: "approve", label: "Send", line: "" }, [...TASK, v("12:approve", "decide", { label: "Send", card: true, tone: "p" })], "card:12:approve"],
  ["working", { verb: "next", label: "Next", line: "" }, [v("save-end", "agent", { label: "Stop and save", fill: true }), NEXT], "next"],
  ["agent_done", { verb: "close", label: "Mark done", line: "" }, TASK, "done"],
  ["report_ok", { verb: "next", label: "Next", line: "" }, [v("w:mine", "decide", { label: "Put it on my list" }), NEXT], "next"],
  ["fyi_batch", { verb: "next", label: "All read, next", line: "" }, [v("v:All read, next", "next", { label: "All read, next" })], "v:All read, next"],
  ["invite_no_cal", { verb: "next", label: "Next", line: "" }, [...TASK, v("accept_invite", "decide", { label: "Accept" })], "next"],
  ["goal", { verb: "next", label: "Next", line: "" }, TASK, "next"],
];
const KEY = "processing:pi_1";
const litOf = (row) => [...[...row.decide, ...row.agent, ...row.more].filter((x) => x.tone === "p" && !x.own).map((x) => x.id),
  ...(row.lit ? [`card:${row.lit}`] : []), ...(row.next?.tone === "p" ? [row.next.id] : [])];

for (const [state, said, list, want] of MATRIX) {
  test(`${state}: one lit button - the decision's own - on the desk and at phone width, and a line only for a fact`, () => {
    const decision = { ...said, for: KEY, key: KEY, state };
    const shown = adviceShown(decision, { key: KEY, lane: state === "working" ? "working" : "asked" }, false);
    const { pick } = stripWord({ speaks: true, shown, advice: decision, key: KEY, lane: state === "working" ? "working" : "asked" });
    // THE DESK: the bar (or the card, for a draft's own move) lights exactly the decision's button, nothing else
    const row = rowOf({ list, ref: "TQ-0004" }, pick);
    assert.deepEqual(litOf(row), [want], state);
    // THE DESK AT PHONE WIDTH (ruling 6, 2026-10-22): Next and the one lit move, every other button behind one ▾ - and Mark done, never
    // folded (the owner, 2026-10-28)
    const ph = phoneRow(row), others = ph.shown.filter((x) => x.id !== "done");
    assert.ok(others.length <= 1, state);
    if (!want.startsWith("card:") && want !== row.next?.id) assert.ok(ph.shown.some((x) => x.id === want), `${state}: the lit move rides beside Next on a phone`);
    // THE STRIP: the decision's fact, or nothing - never a sentence explaining the obvious button
    assert.equal(!!pick?.line, !!said.line, state);
    assert.ok((said.line || "").length <= 64, `${state}: a line is read whole on a phone`);
  });
}

// ...the server may light something on an asking agent now (the model's call); where it lights nothing, the row lights nothing either
test("a decision with no verb lights nothing on the row: an asking agent's pane holds the answers", () => {
  const decision = { verb: null, state: "agent_asking", line: "", for: KEY, key: KEY };
  assert.equal(adviceShown(decision, { key: KEY, lane: "blocked" }, false), null);
  const { pick } = stripWord({ speaks: true, shown: null, advice: decision, key: KEY, lane: "blocked" });
  assert.equal(pick, null);
  assert.deepEqual(litOf(rowOf({ list: [v("save-end", "agent", { label: "Stop and save" }), NEXT], ref: "" }, pick)), []);
});

// ONE LINE, READ WHOLE, ON A PHONE TOO (2026-10-26, superseding the two-line wrap of 2026-10-22): the phone gives the line the room
// ...and since 2026-10-26 there is no Advisor line over a row on any width (the owner: "remove the advisor"); setup's line keeps the one line
test("no Advisor strip at any width; the one .tq-next line left (setup's) stays one line", async () => {
  const fs = await import("node:fs");
  const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  assert.doesNotMatch(css, /\.tq-next-txt \{[^}]*white-space: normal/, "never a second line");
  assert.doesNotMatch(css, /\.tq-strip/);
  assert.match(css, /\.tq-next-txt \{[^}]*white-space: nowrap; overflow: hidden; text-overflow: ellipsis; \}/);
});

// THE STATES ARE FACTS NOW (the owner, 2026-11-02: "never ever use hard coded rules, let the ai see everything"): each says what it means
// and the fact said for it - no state lights a button by itself; the model decides every light (advisor.decide)
test("every state's words: what it means and a fact or silence - never a lit list, never the filler the owner struck out", () => {
  assert.ok(Object.keys(ADVICE_RULE).length >= 25);
  for (const [st, w] of Object.entries(ADVICE_RULE)) {
    assert.deepEqual(Object.keys(w).sort(), ["is", "line"], st);
    assert.ok(w.is.length > 0, st);
    for (const gone of ["No suggestion", "Nothing to decide", "Thinking", "the choice is yours", "Suggested"]) assert.ok(!w.line.includes(gone), `${st}: ${w.line}`);
    assert.ok(w.line.length <= 64, st);
  }
});
