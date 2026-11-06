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

test("no press is held: nothing queues a Next or a Back over a move in flight", () => {
  for (const s of ["holdMove", "nextHeld", "backHeld", "cancelHeld", "heldRef", "walkPress", "heldStep", "chatMoved"]) assert.ok(!view.includes(s), `${s} is back`);
  assert.ok(!read("funnelPile.js").includes("heldStep"), "the walk's word one step further is back");
  assert.match(view, /next: \(\) => runChip\(\{ verb: "next" \}\),/);
  assert.match(view, /if \(busy \|\| resetting \|\| !c \|\| \(c\.verb === "next" && deferredChat\.current\.size\)\) return;/, "a Next over a move, a typed one's too, does nothing");
  assert.match(view, /if \(c\.verb === "next"\) \{ surface\(null, null, key, !item\); return; \}/);
});

test("Next and Back grey while a move is out - a typed one's put-off move too - and only then", () => {
  assert.match(read("CanvasItem.jsx"), /useVerbs\("next", \[\{ id: "next", group: "next", label: btnLabel\("next"\), disabled: !!busy, run/);
  assert.match(view, /chip: runChip, busy: busy \|\| deferring \|\| resetting,/);
  assert.match(view, /deferredChat\.current\.add\(timer\); setDeferring\(true\);/);
  assert.match(view, /disabled: !backTo \|\| moving,/);
  assert.ok(!read("actionRow.js").includes("steady"), "a Next drawn as live while it is greyed is back");
});

test("a rail row clicked over a move draws at once, and that move's answer fills its own line, never the table", () => {
  assert.match(view, /rowsDrawn\.current \+= 1;/);
  assert.match(view, /else landed\(data, off\(\)\);/);
  assert.match(view, /landed\(data, rowsDrawn\.current !== drawn0\);/, "a typed turn's answer as well");
  assert.match(view, /if \(off\) \{\n\s+if \(below\) setMsgs/);
  assert.match(view, /if \(a && !pre\) \{ setMsgs\(\(m\) => m\.filter\(\(x\) => x\.id !== a\.id\)\); if \(!off\(\)\) putOnTable\(was\); \}/, "a failed move leaves the owner's row up");
  assert.match(view, /const pre = key \? \[\.\.\.msgsRef\.current\]\.reverse\(\)\.find\(\(x\) => x\.ahead && x\.card\?\.key === key\) : null;/, "its own move fills the line it drew");
});

test("a chat read never merges lines over a move: the table stays where it was drawn", () => {
  assert.match(view, /mergeDurableTurns\(m, st\.messages \|\| \[\], \{ append: !mid && !turnFlight\.current && moves === tableMoves\.current \}\)/);
  const was = [{ id: "a1", role: "assistant", text: "Up next.", card: { key: "task:1" } }];
  const { messages } = mergeDurableTurns(was, [{ id: 7, role: "assistant", text: "Up next.", card: { key: "task:1", pressed: "Next" } },
    { id: 8, role: "assistant", text: "Then this.", card: { key: "task:2" } }], { append: false });
  assert.deepEqual(messages.map((m) => m.id), ["a1"], "no line pushed under the table over a move");
});

test("Back draws the row above at its press, and Next or Back an FYI batch from its rows", () => {
  const pile = read("funnelPile.js");
  assert.match(pile, /: how === "back" && fromKey && walk\?\.on === fromKey && walk\.above \? walk\.above/);
  assert.match(pile, /const below = onIt && walk\.below \? walk\.below/);
  assert.match(view, /const \{ onIt, below \} = pressOnto\(walkNow, railNow, \{ putDown, how, fromKey, key, card: currentRef\.current \}\);/);
  assert.match(view, /fyis\.every\(Boolean\) \? \{ key: below, kind: "fyis",/, "a batch drawn at the press as railwalk.as_item draws it");
  assert.match(view, /if \(how === "back" && !data\.item && data\.top\) \{ undraw\(\);/, "the top after all: the row drawn comes down");
});
