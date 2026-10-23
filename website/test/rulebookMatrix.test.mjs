// THE ONE RULEBOOK, ON THE PAGE (the Advisor design, phase A; the owner's rulings, 2026-10-23): every state the design's table names, as
// the server decides it (advisor.decide - tests/test_rulebook.py holds the server side), drawn on the desk canvas and at phone width:
// exactly ONE lit button, the decision's own, found among the buttons the row actually draws - and a line on the strip only where the
// decision carries a fact, never a sentence explaining the obvious move. Invented Northwind people only.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceShown, stripWord } from "../src/advice.js";
import { phoneRow, rowOf } from "../src/actionRow.js";
import { ADVICE_RULE, adviceNone } from "../src/words.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const NEXT = v("next", "next", { label: "Next" });
// what a task's row registers (TaskPage's verbs, by their row ids - buttons.json `row`)
const TASK = [v("reply", "decide", { label: "Reply" }), v("done", "more", { label: "Mark done" }), v("remind", "more", { label: "Remind me" }),
  v("nat", "more", { label: "Remove - not a task" }), v("hand", "more", { label: "Hand it to a person" }), NEXT];

// (state, the decision the server answers, the row drawn, the id lit on the bar or the card)
const MATRIX = [
  ["asked", { verb: "reply", label: "Reply", line: "Erin Blake asked 3 days ago." }, TASK, "reply"],
  ["draft_ready", { verb: "approve", label: "Send", line: "" }, [...TASK, v("12:approve", "decide", { label: "Send", card: true, tone: "p" })], "card:12:approve"],
  ["draft_promise", { verb: "redraft", label: "Redraft", line: "Draft promises Friday - nothing here shows it." },
    [...TASK, v("12:approve", "decide", { label: "Send", card: true, tone: "p" }), v("12:redraft", "decide", { label: "Redraft", card: true })], "card:12:redraft"],
  ["unsendable", { verb: "copy", label: "Copy", line: "" }, [...TASK, v("12:copy", "decide", { label: "Copy", card: true })], "card:12:copy"],
  ["duplicate", { verb: "remove", label: "Remove - not a task", line: "Same ask as TQ-0006." }, TASK, "nat"],
  ["working", { verb: "next", label: "Next", line: "" }, [v("save-end", "agent", { label: "Stop and save", fill: true }), NEXT], "next"],
  ["unpushed", { verb: "review_changes", label: "Review changes", line: "Changes ready - not pushed." }, [...TASK, v("diff", "agent", { label: "Review changes" })], "diff"],
  ["stopped", { verb: "continue", label: "Continue", line: "Stopped 40 min ago." }, [...TASK, v("continue", "agent", { label: "Continue" })], "continue"],
  ["failed", { verb: "fix", label: "Connect an AI", line: "Failed: no AI connected for coding." }, [...TASK, v("fix", "decide", { label: "Connect an AI" })], "fix"],
  ["agent_done", { verb: "close", label: "Mark done", line: "" }, TASK, "done"],
  ["report_ok", { verb: "next", label: "Next", line: "" }, [v("w:mine", "decide", { label: "Put it on my list" }), NEXT], "next"],
  ["fyi_batch", { verb: "next", label: "All read, next", line: "" }, [v("v:All read, next", "next", { label: "All read, next" })], "v:All read, next"],
  ["invite_free", { verb: "accept_invite", label: "Accept", line: "Free then." }, [...TASK, v("accept_invite", "decide", { label: "Accept" })], "accept_invite"],
  ["invite_clash", { verb: "propose_time", label: "Propose a new time", line: "Clashes with 1:1 with Omar 10:00-10:30 AM." },
    [...TASK, v("accept_invite", "decide", { label: "Accept" }), v("propose_time", "decide", { label: "Propose a new time" })], "propose_time"],
  ["invite_no_cal", { verb: "next", label: "Next", line: "" }, [...TASK, v("accept_invite", "decide", { label: "Accept" })], "next"],
  ["waiting", { verb: "defer", label: "Remind me", line: "" }, TASK, "remind"],
  ["waiting_late", { verb: "chase", label: "Chase them", line: "Ray Colton: 4 days, no answer." }, [...TASK, v("advice:chase", "more", { label: "Chase them", tone: "p" })], "advice:chase"],
  ["goal_late", { verb: "chase", label: "Chase them", line: "Ray Colton's schema sign-off: 2 days late." }, [...TASK, v("advice:chase", "more", { label: "Chase them", tone: "p" })], "advice:chase"],
  ["goal", { verb: "next", label: "Next", line: "" }, TASK, "next"],
  ["idea", { verb: "mine", label: "Put it on my list", line: "" }, [v("w:mine", "decide", { label: "Put it on my list" }), NEXT], "w:mine"],
  ["unsorted", { verb: "retriage", label: "Sort it again", line: "" }, [v("retriage", "more", { label: "Sort it again" }), NEXT], "retriage"],
];
const KEY = "processing:pi_1";
const litOf = (row) => [...[...row.decide, ...row.agent, ...row.more].filter((x) => x.tone === "p" && !x.own).map((x) => x.id),
  ...(row.lit ? [`card:${row.lit}`] : []), ...(row.next?.tone === "p" ? [row.next.id] : [])];

for (const [state, said, list, want] of MATRIX) {
  test(`${state}: one lit button - the decision's own - on the desk and at phone width, and a line only for a fact`, () => {
    const decision = { ...said, for: KEY, key: KEY, state };
    const shown = adviceShown(decision, { key: KEY, lane: state === "working" ? "working" : "asked" }, false);
    const { noAi, pick } = stripWord({ speaks: true, shown, advice: decision, key: KEY, lane: state === "working" ? "working" : "asked" });
    assert.equal(noAi, false);
    // THE DESK: the bar (or the card, for a draft's own move) lights exactly the decision's button, nothing else
    const row = rowOf({ list, ref: "TQ-0004" }, pick);
    assert.deepEqual(litOf(row), [want], state);
    // THE DESK AT PHONE WIDTH (ruling 6, 2026-10-22): Next and the one lit move, every other button behind one ▾
    const ph = phoneRow(row);
    assert.ok(ph.shown.length <= 1, state);
    if (!want.startsWith("card:") && want !== row.next?.id) assert.equal(ph.shown[0]?.id, want, `${state}: the lit move rides beside Next on a phone`);
    // THE STRIP: the decision's fact, or nothing - never a sentence explaining the obvious button
    assert.equal(!!pick?.line, !!said.line, state);
    assert.ok((said.line || "").length <= 64, `${state}: a line is read whole on a phone`);
  });
}

test("no AI where the move needs one: the strip says so once, and the row lights its own Connect an AI or nothing", () => {
  const decision = { none: "no_ai", for: KEY, key: KEY };
  const { noAi, pick } = stripWord({ speaks: true, aiOff: true, advice: decision, key: KEY, lane: "asked" });
  assert.equal(noAi, true); assert.equal(pick.none, "no_ai");
  assert.equal(adviceNone("no_ai").line, "Connect an AI.");
  assert.equal(adviceNone("no_ai").move, "ai");
});

test("an agent asking lights nothing on the row: its pane holds the answers", () => {
  const decision = { verb: null, state: "agent_asking", line: "", for: KEY, key: KEY };
  assert.equal(adviceShown(decision, { key: KEY, lane: "blocked" }, false), null);
  const { pick } = stripWord({ speaks: true, shown: null, advice: decision, key: KEY, lane: "blocked" });
  assert.equal(pick, null);
  assert.deepEqual(litOf(rowOf({ list: [v("save-end", "agent", { label: "Stop and save" }), NEXT], ref: "" }, pick)), []);
});

test("at phone width the Advisor's line wraps to two lines, never cut; the desk keeps its one line", async () => {
  const fs = await import("node:fs");
  const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 600px\) \{\s*\.tq-strip \.tq-next-txt \{ white-space: normal; overflow: visible; text-overflow: clip;/);
  assert.match(css, /\.tq-next-txt \{[^}]*white-space: nowrap; overflow: hidden; text-overflow: ellipsis; \}/);
});

test("every state's words: a fact or silence, and never the filler the owner struck out", () => {
  assert.ok(Object.keys(ADVICE_RULE).length >= 25);
  for (const [st, w] of Object.entries(ADVICE_RULE)) {
    assert.ok(Array.isArray(w.lit), st);
    for (const gone of ["No suggestion", "Nothing to decide", "Thinking", "the choice is yours", "Suggested"]) assert.ok(!w.line.includes(gone), `${st}: ${w.line}`);
    assert.ok(w.line.length <= 64, st);
  }
  for (const st of ["working", "report_ok", "dashboard", "fyi_batch", "goal", "invite_no_cal"]) assert.deepEqual(ADVICE_RULE[st], { line: "", lit: ["next"] }, st);
});
