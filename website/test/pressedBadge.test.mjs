// A PRESS IS A BADGE ON ITS CARD, NEVER A LINE (the owner, 2026-10-22: "why do we have done-mark done text. we don't need that text
// ever. I hate free text" ... "put a little animation on the corner of the past task - like button marked done not free text").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { mergeDurableTurns, nextBadge, pressChip, pressLine, pressedNoteOf, pressedOf } from "../src/assistantTurns.js";
import { label as btn } from "../src/buttons.js";
import { chipsOf, lastActIndex, sentChips } from "../src/funnelPile.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const item = (id, key, tid) => ({ id, role: "assistant", text: "", card: { kind: "task", key, tid, title: "Send Erin the signed form" } });

test("the press marks the item's newest card with the button's label, and adds no line", () => {
  const ms = [item("a1", "task:7", 7), { id: "a2", role: "assistant", text: "Next up." }, item("a3", "task:7", 7), item("a4", "task:8", 8)];
  const out = pressLine(ms, { key: "task:7", tid: 7 }, btn("close"));
  assert.equal(out.length, ms.length);
  assert.equal(out[2].pressed, "Mark done");
  assert.equal(pressedOf(out[2]), "Mark done");
  assert.equal(out[0].pressed, undefined); assert.equal(out[3].pressed, undefined);
  assert.ok(!out.some((m) => m.role === "receipt"));
  // by its task alone too - the task view's Remind me knows only the task
  assert.equal(pressLine(ms, { tid: 8 }, btn("defer"))[3].pressed, "Remind me");
  // nothing to mark: nothing changes, and still no line
  assert.deepEqual(pressLine(ms, { key: "task:99" }, "Mark done"), ms);
});

test("a proposal line and a words line are not the item's card", () => {
  const ms = [item("a1", "task:7", 7), { id: "a2", role: "assistant", text: "Mark done?", card: { kind: "proposal", key: "task:7", tid: 7 }, proposal: { id: "p" } }];
  const out = pressLine(ms, { key: "task:7", tid: 7 }, "Mark done");
  assert.equal(out[0].pressed, "Mark done"); assert.equal(out[1].pressed, undefined);
});

test("a word pressed under a line marks that line and leaves it", () => {
  const close = { verb: "close", label: "Mark done", tid: 7, ref: "TQ-0007" };
  const ms = [{ id: "r1", role: "receipt", text: "Not ours - filed.", chips: [close, { verb: "next", label: "Next" }] }];
  const out = pressChip(ms, close);
  assert.equal(out.length, 1);
  assert.equal(out[0].pressed, "Mark done");
  assert.deepEqual(out[0].chips.map((c) => c.verb), ["next"]);
});

// A SEND IS A BADGE TOO (the owner, 2026-10-22: "yes"): no "Sent to Erin Blake." line - the folded reply card wears "✓ Send" and
// carries Mark done and Next for the row by the prompt (AssistantView sent)
test("a send folds its card badged Send, with Mark done and Next on the row, and adds no line", () => {
  const sent = (m, pressed, tid, ref) => m.map((x, i) => (i === m.length - 1 ? { ...x, done: true, sent: true, pressed, ...sentChips(tid, ref) } : x));
  const ms = sent([item("a1", "review:3", 7)], btn("approve"), 7, "TQ-0007");
  assert.equal(ms.length, 1, "no line under the card");
  assert.ok(!ms.some((m) => m.role === "receipt" || /Sent to/.test(m.text)));
  assert.equal(pressedOf(ms[0]), "Send");
  // the folded card is the line that carries the words, so the row draws them
  assert.equal(lastActIndex(ms), 0);
  assert.deepEqual(chipsOf(ms[0]).map((c) => [c.verb, c.label]), [["close", "Mark done"], ["next", "Next"]]);
  // Mark done pressed from the row: its badge on the same card, Next left
  const closed = pressChip(ms, chipsOf(ms[0])[0]);
  assert.equal(pressedOf(closed[0]), "Mark done");
  assert.deepEqual(chipsOf(closed[0]).map((c) => c.verb), ["next"]);
  // ...and a read of the server's copy keeps the fold's words on it
  const local = [{ ...ms[0], id: "a9" }];
  const read = mergeDurableTurns(local, [{ id: 61, role: "assistant", text: "", card: local[0].card }]).messages;
  assert.equal(read[0].sent, true); assert.equal(read[0].done, true); assert.equal(read[0].pressed, "Send");
  assert.deepEqual(chipsOf(read[0]).map((c) => c.verb), ["close", "next"]);
});

test("the server's stamp reaches a line already drawn, and the press's own badge survives a read", () => {
  const local = [{ ...item("a1", "task:7", 7), commentId: 41 }];
  const { messages } = mergeDurableTurns(local, [{ id: 41, role: "assistant", text: "", card: { ...local[0].card, pressed: "Mark done" } }]);
  assert.equal(pressedOf(messages[0]), "Mark done");
  const bubble = [{ ...item("a2", "task:8", 8), pressed: "Send to coding agent" }];
  const read = mergeDurableTurns(bubble, [{ id: 52, role: "assistant", text: "", card: bubble[0].card }]).messages;
  assert.equal(read[0].pressed, "Send to coding agent");
});

// A TYPED CLOSE WITH A NOTE (the owner, 2026-10-23: "it should collapse the task and write on it marked done with note"): the folded card
// wears "✓ Close with a note" and the owner's reason after it - at the press, and from the server's stamp after a read
test("a Close with a note wears its note beside the badge, at the press and after a read", () => {
  const ms = [item("a1", "task:7", 7)];
  const out = pressLine(ms, { key: "task:7", tid: 7 }, btn("close_note"), "Paula sent it herself");
  assert.equal(pressedOf(out[0]), "Close with a note"); assert.equal(pressedNoteOf(out[0]), "Paula sent it herself");
  assert.equal(pressedNoteOf(pressLine(ms, { tid: 7 }, btn("close"))[0]), "", "a bare Mark done has no note");
  const local = [{ ...item("a2", "task:8", 8), commentId: 44 }];
  const { messages } = mergeDurableTurns(local, [{ id: 44, role: "assistant", text: "",
    card: { ...local[0].card, pressed: "Close with a note", pressed_note: "done on the phone" } }]);
  assert.equal(pressedOf(messages[0]), "Close with a note"); assert.equal(pressedNoteOf(messages[0]), "done on the phone");
});

test("no button press writes a 'Done - <button>' line or a free-text receipt on the desk", () => {
  const view = src("AssistantView.jsx"), cards = src("assistantCards.jsx");
  for (const gone of ["marked done.`", "- done.`", "Closed with your note:", "fyi let go", "Started on ${", "is with ${who} now", "answers again - that row is gone",
    "The rule is made", "again once the checks pass"])
    assert.ok(!view.includes(gone) && !cards.includes(gone), `still says: ${gone}`);
  // a press that went through and carries no way on adds no receipt line - it marks its card
  assert.match(view, /const worn = out\.status === "done" \? pressLine\(/);
  assert.match(view, /return quiet && worn !== ms \? worn/);
  // ...and the badge is drawn on the folded card, as the button's own label
  assert.match(view, /<Pressed label=\{pressedOf\(m\)\} \/>/);
  assert.match(src("assistantView.css"), /\.tq-pressed \{[^}]*animation: tq-pressed-in/);
  assert.match(src("assistantView.css"), /prefers-reduced-motion: reduce\) \{ \.tq-pressed \{ animation: none; \}/);
});

test("Next leaves its own badge on the card it passed, and a failed Next takes it off", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  // the owner, 2026-10-23: "we should have next pill on this one to show what was clicked on each task"
  assert.match(view, /const word = i < 0 \? "" : nextBadge\(m\[i\]\.card\);/);
  assert.match(view, /on \? \{ \.\.\.x, pressed: word \}/);
  assert.match(view, /if \(putDown\) wear\(true\);/);
  // ...unless the server says that Next was made already (already_completed): then nothing is taken back (the email walk, 2026-10-29)
  assert.match(view, /if \(!done && putDown\) \{ setFoldedKey\(\(k\) => \(k === putDown \? null : k\)\); wear\(false\); \}/);
});

// NEXT READS A REPORT, IT PASSES A TASK (the owner, 2026-10-23: "should show read on reports if you go pass them when you hit next"):
// the badge says which - "Read" where Next settled the row read, "Next" where the row stays yours
test("Next's badge is Read on a report, a dashboard or an fyi it read, and Next on a task it only passed", () => {
  assert.equal(btn("next", "read"), "Read");
  for (const c of [{ kind: "report", lane: "report" }, { kind: "report", lane: "report", dashboard: true }, { kind: "report", lane: "broken", bad: true },
    { kind: "agentdone", lane: "report", tid: 8 }, { kind: "fyi", lane: "fyi" }]) assert.equal(nextBadge(c), "Read", JSON.stringify(c));
  for (const c of [{ kind: "task", lane: "yours", tid: 7 }, { kind: "review", lane: "approve", tid: 3 }, { kind: "agent", lane: "blocked", tid: 5 },
    { kind: "meeting", lane: "time" }, { kind: "connection", lane: "broken" }, null]) assert.equal(nextBadge(c), "Next", JSON.stringify(c));
  assert.equal(nextBadge({ kind: "fyis", lane: "fyi" }), btn("next", "batch"));
  // ...worn the way wear() puts it, and taken off by a failed Next only when it is Next's own word
  const ms = [{ id: "a1", role: "assistant", text: "", card: { kind: "report", key: "report:4", lane: "report", title: "Weekly spend" } }, item("a2", "task:7", 7)];
  const wear = (m, key, on) => m.map((x) => (x.card?.key !== key ? x : on ? (pressedOf(x) ? x : { ...x, pressed: nextBadge(x.card) })
    : x.pressed === nextBadge(x.card) ? (({ pressed, ...r }) => r)(x) : x));
  const passed = wear(wear(ms, "report:4", true), "task:7", true);
  assert.equal(pressedOf(passed[0]), "Read"); assert.equal(pressedOf(passed[1]), "Next");
  assert.equal(pressedOf(wear(passed, "report:4", false)[0]), "", "a failed Next takes Read off");
  const closed = pressLine(ms, { key: "task:7", tid: 7 }, btn("close"));
  assert.equal(pressedOf(wear(wear(closed, "task:7", true), "task:7", false)[1]), "Mark done", "another press's badge is never Next's to take");
});

// THE END OF THE WALK SAYS NOTHING (the owner, 2026-10-23: "yes remove the sentence, just the button"): the server sends no words on the
// desk, and a line with no words and no item draws no bubble - only its buttons, on the row by the prompt
test("a line with no words and no item is only its buttons", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /&& !m\.proposal && !String\(m\.text \|\| ""\)\.trim\(\) && !pressedOf\(m\)\)\n\s+return last \? <BarVerbs owner=\{`line:\$\{m\.id\}`\} chips=\{barHolds \? \[\] : chipsOf\(m\)\}/);
  const end = { id: "a9", role: "assistant", text: "", chips: [{ verb: "walk", label: btn("walk") }, { verb: "open", key: "task:4", label: "Open TQ-0004 · Quarter plan" }] };
  assert.deepEqual(chipsOf(end).map((c) => c.verb), ["walk", "open"]);
});
