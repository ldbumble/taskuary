// THE CARD DRAWN LIVE IS THE TABLE'S (the dead-end walk's RING, 2026-10-20): after a Next and a link to another task, a chat read merged
// the linked item's durable line back above the one Next had drawn - the rail ringed TQ-0005 over TQ-0001's live card.
import test from "node:test";
import assert from "node:assert/strict";

import { drawnKey, tableCardIndex } from "../src/funnelPile.js";
import { tableOf } from "../src/tableState.js";

const item = (id, key, extra = {}) => ({ id, role: "assistant", text: id, card: { kind: "todo", key, ...extra } });

test("the live card is the table's line when a newer line is another item", () => {
  const ms = [item(1, "p:5"), item(2, "p:1")];
  assert.equal(tableCardIndex(ms, "p:5"), 0, "TQ-0005 is on the table: its line is drawn, not TQ-0001's");
  assert.equal(tableCardIndex(ms, "p:1"), 1);
  assert.equal(tableCardIndex([item(1, "p:9", { aliases: ["task:5"] }), item(2, "p:1")], "task:5"), 0, "by an alias too");
});

test("otherwise the newest card leads, as before", () => {
  const ms = [item(1, "p:5"), item(2, "p:1")];
  assert.equal(tableCardIndex(ms, null), 1, "nothing on the table");
  assert.equal(tableCardIndex(ms, "p:7"), 1, "the table's item has no line here");
  assert.equal(tableCardIndex([item(1, "p:5", {}), { ...item(2, "p:1"), done: true }], "p:5"), -1, "a line put down puts the table down");
  assert.equal(tableCardIndex([{ ...item(1, "p:5"), done: true }, item(2, "p:1")], "p:5"), 1, "the table's line put down is not brought back");
  const prop = { id: 3, role: "assistant", text: "?", proposal: { kind: "x" }, card: { kind: "proposal", key: "op:1" } };
  assert.equal(tableCardIndex([item(1, "p:5"), prop], "p:5"), 1, "a proposal after the item still leads");
});

// WALK 11: after a restart the table's record was empty while the chat's newest task card drew live - the task stood inside the home, the
// home's "Ask…" box under its own and the home's icons in its head. The card drawn live is what the table holds, one record for both
test("with nothing put on the table, the task card the chat draws live is on it", () => {
  const task = (c) => !!c.tid, ms = [item(1, "p:5", { tid: 5 }), item(2, "p:1", { tid: 1 })];
  assert.equal(drawnKey(ms, task), "p:1", "the one tableCardIndex draws live");
  assert.equal(ms[tableCardIndex(ms, null)].card.key, drawnKey(ms, task));
  assert.deepEqual(tableOf({ drawn: drawnKey(ms, task) }), { key: "p:1", folded: false, place: false, speaks: true });
  assert.equal(tableOf({ drawn: "p:1", foldedKey: "p:1" }).folded, true, "folded by its X, it is no longer in view");
  assert.equal(drawnKey([item(1, "p:5", { tid: 5 }), { ...item(2, "p:1", { tid: 1 }), done: true }], task), null, "put down: nothing");
  assert.equal(drawnKey([item(1, "n:1")], task), null, "an item that is no task is not one");
  assert.equal(tableOf({ current: "p:9", drawn: "p:1" }).key, "p:9", "what was put on the table leads");
});
