import test from "node:test";
import assert from "node:assert/strict";
import { mergeDurableTurns } from "../src/assistantTurns.js";

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
