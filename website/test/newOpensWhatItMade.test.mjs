import test from "node:test";
import assert from "node:assert/strict";


import { holdsNew, pressOnto } from "../src/funnelPile.js";


// a task open on the table, then New posted over it: the New card is the live page
const msgs = [{ id: "a1", role: "assistant", card: { key: "task:7", tid: 7 } }, { id: "b2", role: "browse", area: "new", state: { kind: "agent" } }];
const rail = [{ key: "task:7", tid: 7, title: "Held mail from a stranger" }];

test("New's press opening the task it just made keeps the card up: no rail row holds that task yet, so nothing draws at the press", () => {
  assert.equal(pressOnto({}, rail, { key: "task:12", card: { key: "task:7" } }).below, "task:12");     // the press names it...
  assert.equal(rail.find((i) => i.key === "task:12"), undefined);                                      // ...but no row draws it
  assert.equal(holdsNew(msgs, "b2", rail, "task:12"), true);
});

test("the card goes with the press as ever when the row draws at once, the page is not New, or nothing is browsed", () => {
  assert.equal(holdsNew(msgs, "b2", [...rail, { key: "task:12" }], "task:12"), false);                 // its row is drawn ahead
  assert.equal(holdsNew(msgs, "b2", [...rail, { key: "task:12", settling: true }], "task:12"), true);  // a settling row draws nothing
  assert.equal(holdsNew([...msgs.slice(0, 1), { id: "b3", role: "browse", area: "reports" }], "b3", rail, "task:12"), false);
  assert.equal(holdsNew(msgs, null, rail, "task:12"), false);
  assert.equal(holdsNew(msgs, "b2", rail, null), false);
});


// THE TASK NEW MADE IS ON THE TABLE AT THE PRESS (the owner, 2026-11-16: "on new task it says sent to agent and then the bottom of the screen
// shows ... it should show ... on the agent starting, not randomly on the bottom of the canvas"): New hands the canvas the task as its row, drawn
// as a rail row is, so the "…" of the move that brings its real row waits under the fold, never at the canvas foot under New's card
