// TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): a line typed while the agent's turn runs is shown at once and goes to the same
// session as its next turn - Enter while running only put a newline in the box, and the line never left it.
import assert from "node:assert/strict";
import test from "node:test";

import { heldLine, stillHeld, waitingShown } from "../src/heldLines.js";

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

test("the lines the server kept for the agent show on every screen, once (the owner, 2026-11-07)", () => {
  const waiting = [{ id: 7, text: "make it 2,500", at: "2026-11-07 20:33:04" }, { id: 8, text: "and copy Erin", at: "2026-11-07 20:33:09" }];
  const server = [said("compare three tools")];
  // a page opened mid-turn (or another screen) has none of its own: both, as the server kept them
  assert.deepEqual(waitingShown(waiting, [], server, server).map((w) => w.id), [7, 8]);
  // ...the screen that typed one draws its own held copy instead, never both
  assert.deepEqual(waitingShown(waiting, [{ id: "h", text: "make it  2,500" }], server, server).map((w) => w.id), [8]);
  // ...and a line its own thread streamed is its thread's; the server's conversation counts nothing extra
  assert.deepEqual(waitingShown(waiting, [], [...server, said("and copy Erin")], server).map((w) => w.id), [7]);
  assert.deepEqual(waitingShown(undefined, [], server, server), []);
});

// A PRESS IS THE OWNER'S LINE, NOT A HELD ONE (the owner, 2026-11-08: "You set a reminder for Monday" drawn on the right): a press landing
// while a line is held never takes that line away
test("a press drawn as the owner's line never counts as the held line arriving", () => {
  const held = [{ text: "copy Erin", after: 1 }];
  const press = { ...said("You set a reminder for Monday."), press: true };
  assert.deepEqual(stillHeld(held, [said("hi"), press]), held);
  assert.deepEqual(stillHeld(held, [said("hi"), { ...press, press: undefined, metadata: { custom: { press: true } } }]), held);
  assert.deepEqual(stillHeld(held, [said("hi"), said("copy Erin")]), []);
});

// A HELD LINE IS THE OWNER'S LINE (the product audit, 2026-11-08): it had no "You · time" head, and the turn's PDF stood under it
test("a held line wears the owner's own head and stands last, under the turn's files and cards", async () => {
  const { readFileSync } = await import("node:fs");
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const held = ws.indexOf('data-tq-held=""'), shut = ws.lastIndexOf("</ThreadPrimitive.If>", held);
  assert.ok(held > ws.indexOf("<PublishedPages pages={published} deliver />") && shut > 0, "after the turn's own cards");
  assert.match(ws.slice(held, held + 600), /<div className="tq-aui-user-head"><PersonOutlineIcon[^>]*\/>You\{l\.at \? ` · \$\{when\(l\.at\)\}` : ""\}<\/div>/);
});
