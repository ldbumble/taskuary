import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { actReceipt, mergeDurableTurns } from "../src/assistantTurns.js";

test("durable chat turns reconcile with their optimistic bubbles instead of drawing twice", () => {
  const local = [
    { id: "u100", role: "user", text: "skip it" },
    { id: "a101", role: "assistant", text: "Tomorrow, then." },
  ];
  const durable = [
    { id: 1141, role: "user", text: "skip it" },
    { id: 1142, role: "assistant", text: "Tomorrow, then." },
  ];
  const result = mergeDurableTurns(local, durable);
  assert.equal(result.messages.length, 2);                     // one bubble each, not two
  assert.deepEqual(result.messages.map((m) => m.text), ["skip it", "Tomorrow, then."]);
  assert.deepEqual(result.messages.map((m) => m.commentId), [1141, 1142]);
  assert.deepEqual(result.added, []);
});

// AssistantView renders the chat as `shown.map((m) => <Line key={m.id} …>)`. A key that changes under
// a line unmounts it and mounts a new one, which tore down the card inside it and drew it again - the
// flicker every message did on the first freshness read after it was sent.
test("reconciling never changes the key a line is already drawn under", () => {
  const local = [
    { id: "u100", role: "user", text: "next" },
    { id: "a101", role: "assistant", text: "A report landed.", card: { key: "report:9", kind: "report" } },
  ];
  const durable = [
    { id: 1141, role: "user", text: "next" },
    { id: 1142, role: "assistant", text: "A report landed.", card: { key: "report:9", kind: "report" } },
  ];
  const once = mergeDurableTurns(local, durable);
  assert.deepEqual(once.messages.map((m) => m.id), ["u100", "a101"]);
  // ...and the second read is a no-op: nothing re-matched, nothing appended, no key moved
  const twice = mergeDurableTurns(once.messages, durable);
  assert.deepEqual(twice.messages.map((m) => m.id), ["u100", "a101"]);
  assert.deepEqual(twice.added, []);
});

test("repeated intentional turns with distinct durable ids are preserved", () => {
  const durable = [
    { id: 1, role: "user", text: "yes" },
    { id: 2, role: "assistant", text: "Okay." },
    { id: 3, role: "user", text: "yes" },
  ];
  assert.deepEqual(mergeDurableTurns(durable, durable).messages, durable);
});

test("new server-side events are appended and reported as fresh", () => {
  const old = [{ id: 1, role: "assistant", text: "Working." }];
  const incoming = [...old, { id: 2, role: "assistant", text: "New message arrived." }];
  const result = mergeDurableTurns(old, incoming);
  assert.deepEqual(result.messages, incoming);
  assert.deepEqual(result.added, [incoming[1]]);
});

test("an answer keeps its verbs when the server's text-only copy comes back - Next is never lost", () => {
  const chips = [{ verb: "reply", label: "Reply" }, { verb: "next", label: "Next" }];
  const { messages } = mergeDurableTurns([{ id: "a1", role: "assistant", text: "Erin sent it.", chips }],
    [{ id: 51, role: "assistant", text: "Erin sent it.", options: [], card: null }]);
  assert.deepEqual(messages[0].chips, chips);
});

test("the receipt drawn at the click and the server's recorded line are one turn", () => {
  const { messages, added } = mergeDurableTurns([{ id: "r1", role: "receipt", text: "Done - Put it on my list.", tid: 9, ref: "TQ-0009" }],
    [{ id: 52, role: "assistant", text: "Done - Put it on my list.", card: null }]);
  assert.equal(messages.length, 1); assert.deepEqual(added, []);
  assert.equal(messages[0].role, "receipt"); assert.equal(messages[0].ref, "TQ-0009");
  // ...but a line that carries a card (the undo offer) is its own turn
  assert.equal(mergeDurableTurns([{ id: "r2", role: "receipt", text: "Done." }], [{ id: 53, role: "assistant", text: "Done.", card: { kind: "proposal" } }]).messages.length, 2);
});

test("a card put down on the page stays down when the server's copy of its turn arrives", () => {
  // the owner, 2026-10-02: "if you click all read next on fyi mail too quickly it reopens the same 4 again before
  // disappearing" - the freshness read swapped the folded bubble for the durable turn and dropped its `done` mark
  const card = { key: "fyis:processing:p1,processing:p2", kind: "fyis" };
  const local = [{ id: "a201", role: "assistant", text: "2 things people told you.", card, done: true }];
  const durable = [{ id: 1301, role: "assistant", text: "2 things people told you.", card }];
  const merged = mergeDurableTurns(local, durable).messages;
  assert.equal(merged.length, 1);
  assert.equal(merged[0].done, true);
  assert.equal(merged[0].commentId, 1301);
});

test("the day's opener filled in its place is redrawn where it stands, not skipped by id", () => {
  const local = [{ id: 7, role: "assistant", text: "Good morning.", card: { kind: "brief", reading: true } },
    { id: "u1", commentId: 8, role: "user", text: "Walk me through my tasks" }];
  const { messages, added } = mergeDurableTurns(local, [
    { id: 7, role: "assistant", text: "Good morning. Three came in.", card: { kind: "brief", away: "Overnight: 3 came in." } },
    { id: 8, role: "user", text: "Walk me through my tasks" }]);
  assert.deepEqual(messages.map((m) => m.id), [7, "u1"]);
  assert.equal(messages[0].card.away, "Overnight: 3 came in.");
  assert.equal(added.length, 0);
});

test("a failed press's receipt is the server's recorded line even when that line carries its way on", () => {
  // concierge.receipt_turn records a failure WITH its chips as a words card: read as a turn of its own, it drew twice (re-audit, 2026-10-18)
  const text = "Not done - the agent did not start. TQ-0007 is where it was.";
  const local = [{ id: "r200", role: "receipt", status: "error", text, chips: [{ verb: "next", label: "Next" }] }];
  const durable = [{ id: 901, role: "assistant", text, card: { kind: "words", chips: [{ verb: "retry", label: "Try again" }] } }];
  const out = mergeDurableTurns(local, durable).messages;
  assert.equal(out.length, 1);
  assert.equal(out[0].role, "receipt");
  assert.equal(out[0].commentId, 901);
});

// ONE PICK LINE PER ITEM (verify, 2026-10-19): picking between two rail rows added another "Show me ..." line every time - the same title
// twice and more, gone on a reload since the server never records them. The last pick of an item stands; other lines are untouched
test("a rail pick of the same item twice leaves one pick line, and keeps everything else", async () => {
  const { pickLine } = await import("../src/assistantTurns.js");
  let m = [{ id: "u0", role: "user", text: "what is due?" }];
  for (const [i, k] of [["1", "msg:1"], ["2", "msg:2"], ["3", "msg:1"], ["4", "msg:2"]]) m = pickLine(m, { id: `u${i}`, role: "user", text: `Show me ${k}`, pick: k });
  assert.deepEqual(m.map((x) => x.id), ["u0", "u3", "u4"]);
  assert.deepEqual(pickLine(m, { id: "u5", role: "user", text: "and this?" }).map((x) => x.id), ["u0", "u3", "u4", "u5"], "a typed line is never dropped");
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /setMsgs\(\(m\) => pickLine\(m, \{ id: optimisticId, role: "user", text: asUser, pick: key \|\| undefined \}\)\)/);
});

// SWAP, NEVER CLEAR (G8, 2026-10-20): an item shown before was opened again - placeLine moved its line to the end and kept the old
// line's id as an alias - and the read that matched the new line to its durable turn dropped that alias. The next read found the old
// line unknown, pushed it at the end, and oneCopy kept it: the item before came back live on the table while the rail rang the new one
test("a line that replaced an item's older line keeps that line's id through every read, so the old line never comes back last", async () => {
  const { placeLine } = await import("../src/assistantTurns.js");
  const card = (key) => ({ key, kind: "todo" });
  const old = [{ id: 33, role: "assistant", text: "Erin asked for the August numbers.", card: card("processing:a") },
    { id: 38, role: "assistant", text: "Ray asked about the cutover.", card: card("processing:b") }];
  // the walk opens item a again, then item b again - each from the server's turn, with its own words
  let m = placeLine(old, { id: "a1", role: "assistant", text: "Erin asked for the August numbers (2h ago).", card: card("processing:a") });
  const durable1 = [...old, { id: 41, role: "assistant", text: "Erin asked for the August numbers (2h ago).", card: card("processing:a") }];
  m = mergeDurableTurns(m, durable1).messages;
  assert.deepEqual(m.find((x) => x.id === "a1").alias, [33], "the old line's id is still one of its names");
  m = placeLine(m, { id: "a2", role: "assistant", text: "Ray asked about the cutover (1h ago).", card: card("processing:b") });
  const durable2 = [...durable1, { id: 42, role: "assistant", text: "Ray asked about the cutover (1h ago).", card: card("processing:b") }];
  for (let read = 0; read < 3; read++) m = mergeDurableTurns(m, durable2).messages;
  assert.equal(m.at(-1).card.key, "processing:b", "the item the walk brought last is the last line - the one on the table");
  assert.equal(m.filter((x) => x.card?.key === "processing:a").length, 1);
});

// On the desk an item comes up under a few words naming only its kind: three reports in a row each say "Next up: a report.", and the
// second's durable turn matched the first's bubble - its card replaced the first's, and the report the walk left had no line (RECEIPT)
test("two lines with the same words but different items are two turns", () => {
  const card = (key, title) => ({ kind: "report", key, title });
  const local = [
    { id: "a1", role: "assistant", text: "Next up: a report.", card: card("report:1", "Tickets by day"), done: true },
    { id: "a2", role: "assistant", text: "Next up: a report.", card: card("report:2", "Ageing by vendor") },
  ];
  const durable = [
    { id: 501, role: "assistant", text: "Next up: a report.", card: card("report:2", "Ageing by vendor") },
    { id: 500, role: "assistant", text: "Next up: a report.", card: card("report:1", "Tickets by day") },
  ];
  const { messages, added } = mergeDurableTurns(local, durable);
  assert.deepEqual(messages.map((m) => [m.id, m.commentId, m.card.title]), [["a1", 500, "Tickets by day"], ["a2", 501, "Ageing by vendor"]]);
  assert.equal(messages[0].done, true);
  assert.deepEqual(added, []);
});

// AN ACT WITH NO WORDS STILL ENDS ON WORDS in the chat pop-up (the owner, 2026-10-27: it "disappeared when done"): what it did and where,
// one sentence for every act, the server's own line when it gave one
test("an act-only turn gets one receipt read off the act", () => {
  const light = { verb: "defer", label: "Remind me", key: "msg:4", tid: 4, ref: "TQ-0004", line: "" };
  assert.deepEqual(actReceipt({ say: "", light }, "msg:4"), { text: "Remind me is ready on the row for this task - yours to press.", status: "warn" });
  assert.match(actReceipt({ say: "", light }, "msg:9").text, /for TQ-0004/);
  // ...and a said day is in the words (F4)
  assert.equal(actReceipt({ light: { ...light, day: { until: "2026-11-02 09:00", day: "Mon 2 Nov" } } }, "msg:4").text,
    "Remind me (Mon 2 Nov) is ready on the row for this task - yours to press.");
  assert.deepEqual(actReceipt({ pressed: { label: "Mark done", key: "msg:4", ref: "TQ-0004", note: "paid Friday" } }, "msg:9"),
    { text: "Mark done - TQ-0004: paid Friday.", status: "done" });
  assert.equal(actReceipt({ light: { ...light, line: "Remind me is lit for Monday." } }).text, "Remind me is lit for Monday.");
  assert.match(actReceipt({ light: { ...light, label: "" } }, "msg:4").text, /^Brought up this task/);
  assert.equal(actReceipt({}).status, "warn");
  assert.ok(actReceipt({}).text, "even nothing back is said");
});
