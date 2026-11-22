import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

// ONE MOVE AT A TIME (the owner, 2026-11-03): Next and Back grey from a press until its answer lands - ten fast clicks are one move, never a
// queue of held presses. The press still draws what the walk already knows at once (walk.below, walk.above); a rail row clicked over a move
// is drawn at once from its own row, and the move's answer never takes the table back from it.
import { mergeDurableTurns } from "../src/assistantTurns.js";
const read = (n) => readFileSync(fileURLToPath(new URL(`../src/${n}`, import.meta.url)), "utf8");
const view = read("AssistantView.jsx");


test("a chat read never merges lines over a move: the table stays where it was drawn", () => {
  assert.match(view, /mergeDurableTurns\(m, st\.messages \|\| \[\], \{ append: !mid && !turnFlight\.current && moves === tableMoves\.current \}\)/);
  const was = [{ id: "a1", role: "assistant", text: "Up next.", card: { key: "task:1" } }];
  const { messages } = mergeDurableTurns(was, [{ id: 7, role: "assistant", text: "Up next.", card: { key: "task:1", pressed: "Next" } },
    { id: 8, role: "assistant", text: "Then this.", card: { key: "task:2" } }], { append: false });
  assert.deepEqual(messages.map((m) => m.id), ["a1"], "no line pushed under the table over a move");
});


test("a close that comes in after another row was opened leaves the table, and the walk, where the owner is", async () => {
  const { closedElsewhere } = await import("../src/funnelPile.js");
  const rail = [{ key: "task:1" }, { key: "processing:b", aliases: ["processing:a"] }, { key: "task:3" }];
  assert.equal(closedElsewhere(rail, "leave", "task:1", { key: "task:3" }), true);
  assert.equal(closedElsewhere(rail, "leave", "task:1", { key: "task:1" }), false, "the row on the table closes as ever");
  assert.equal(closedElsewhere(rail, "leave", "processing:a", { key: "processing:b" }), false, "one row under two keys is the row on the table");
  assert.equal(closedElsewhere(rail, "leave", "task:1", null), false, "an empty table has nothing to keep");
  assert.equal(closedElsewhere(rail, "next", "task:1", { key: "task:3" }), false, "only a close: Next names its own row");
  assert.match(view, /const away = closedElsewhere\(pileRef\.current\?\.items, how, fromKey, currentRef\.current\);/);
  assert.match(view, /\.\.\.\(pageReads\.length \? \{ read: pageReads \} : \{\}\), \.\.\.\(away \? \{ away: true \} : \{\}\) \}\);/, "the server is told, so its walk stays too");
  assert.match(view, /off = \(\) => away \|\| rowsDrawn\.current !== drawn0;/, "its answer never draws over the table");
  assert.match(view, /\.\.\.\(body\.away \? \{ away: true \} : \{\}\) \}\)\)\.data;/);
});
