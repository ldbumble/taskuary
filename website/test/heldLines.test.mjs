// TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): a line typed while the agent's turn runs is shown at once and goes to the same
// session as its next turn - Enter while running only put a newline in the box, and the line never left it.
import assert from "node:assert/strict";
import test from "node:test";

import { heldLine, stillHeld } from "../src/heldLines.js";

const said = (text) => ({ role: "user", content: [{ type: "text", text }] });

test("Enter while the turn runs holds the line; Shift+Enter, an empty box and an idle turn do not", () => {
  const key = (k, o = {}) => ({ key: k, shiftKey: false, nativeEvent: {}, ...o });
  assert.equal(heldLine(key("Enter"), "  copy Erin  ", true), "copy Erin");
  assert.equal(heldLine(key("Enter"), "copy Erin", false), null);
  assert.equal(heldLine(key("Enter", { shiftKey: true }), "copy Erin", true), null);
  assert.equal(heldLine(key("Enter"), "   ", true), null);
  assert.equal(heldLine(key("a"), "copy Erin", true), null);
  assert.equal(heldLine(key("Enter", { nativeEvent: { isComposing: true } }), "copy Erin", true), null);
});

test("a held line stays drawn until the conversation has it, once", () => {
  const held = [{ id: "a", text: "copy Erin", after: 1 }, { id: "b", text: "keep it short", after: 1 }];
  assert.deepEqual(stillHeld(held, [said("hello")]).map((l) => l.id), ["a", "b"]);
  assert.deepEqual(stillHeld(held, [said("hello"), said("copy Erin")]).map((l) => l.id), ["b"]);
  // ...words the owner said before the hold are not it, and one filed line takes away one held line only
  assert.deepEqual(stillHeld([{ id: "a", text: "yes", after: 1 }], [said("yes")]).map((l) => l.id), ["a"]);
  const twice = [{ id: "a", text: "yes", after: 0 }, { id: "b", text: "yes", after: 0 }];
  assert.deepEqual(stillHeld(twice, [said("yes")]).map((l) => l.id), ["b"]);
});

test("a held line the server spelled back with other spacing or quotes is not drawn twice (2026-11-05)", () => {
  const msg = (text) => ({ role: "user", content: [{ type: "text", text }] });
  const held = [{ id: "h1", text: "It's over $4. I saw it.", after: 1 }];
  assert.deepEqual(stillHeld(held, [msg("first"), msg("It\u2019s over $4.  I saw it.\n")]), []);
  // ...and one the server kept in other words still goes once the owner's line has arrived
  assert.deepEqual(stillHeld(held, [msg("first"), msg("It is over four dollars")]), []);
  assert.deepEqual(stillHeld(held, [msg("first")]), held, "not there yet: still held");
});
