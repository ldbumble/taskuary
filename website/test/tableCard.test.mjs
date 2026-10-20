// THE CARD DRAWN LIVE IS THE TABLE'S (the dead-end walk's RING, 2026-10-20): after a Next and a link to another task, a chat read merged
// the linked item's durable line back above the one Next had drawn - the rail ringed TQ-0005 over TQ-0001's live card.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { tableCardIndex } from "../src/funnelPile.js";

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

test("the chat draws, and asks about, the table's card", () => {
  const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(src, /const lastCardIdx = useMemo\(\(\) => tableCardIndex\(shown, old \? null : current \|\| cardKey\), \[shown, old, current, cardKey\]\);/);
  assert.match(src, /const table = msgs\[tableCardIndex\(msgs, current \|\| cardRef\.current\)\]\?\.card;/);
});
