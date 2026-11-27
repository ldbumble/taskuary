// A PRESS IS A BADGE ON ITS CARD, NEVER A LINE (the owner, 2026-10-22: "why do we have done-mark done text. we don't need that text
// ever. I hate free text" ... "put a little animation on the corner of the past task - like button marked done not free text").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { mergeDurableTurns, nextBadge, pressChip, pressLine, pressedNoteOf, pressedOf } from "../src/assistantTurns.js";
import { label as btn } from "../src/buttons.js";
import { chipsOf, lastActIndex } from "../src/funnelPile.js";

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


// NEXT READS A REPORT, IT PASSES A TASK (the owner, 2026-10-23: "should show read on reports if you go pass them when you hit next"):
// the badge says which - "Read" where Next settled the row read, "Next" where the row stays yours
test("Next's badge is Read on a report, a dashboard or an fyi it read, and Next on a task it only passed", () => {
  assert.equal(btn("next", "read"), "Read");
  for (const c of [{ kind: "report", lane: "report" }, { kind: "report", lane: "report", dashboard: true }, { kind: "report", lane: "broken", bad: true },
    { kind: "agentdone", lane: "yours", tid: 8 }, { kind: "fyi", lane: "fyi" }]) assert.equal(nextBadge(c), "Read", JSON.stringify(c));
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
