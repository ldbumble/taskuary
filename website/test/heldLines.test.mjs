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

// A LINE IS KNOWN BY THE NAME ITS PAGE GAVE IT (the spine audit, 2026-11-09): by its words and by counting, a line from another window or
// the phone retired a held line the server did not have yet, and "ok" sent twice stood once
test("a line sent under its name is the conversation's when the conversation has the name, and by nothing else", () => {
  const named = (text, line) => ({ ...said(text), line }), held = [{ id: "h1", text: "ok", after: 1, drawn: 1, named: true }, { id: "h2", text: "ok", after: 1, drawn: 1, named: true }];
  assert.deepEqual(stillHeld(held, [said("hello")]).map((l) => l.id), ["h1", "h2"]);
  // ...the phone's "ok", another window's "ok" under its own name, a third line: none of them is this page's line arriving
  assert.deepEqual(stillHeld(held, [said("hello"), said("ok"), named("ok", "other-1"), said("and one more")]).map((l) => l.id), ["h1", "h2"]);
  assert.deepEqual(stillHeld(held, [said("hello"), named("ok", "h2")]).map((l) => l.id), ["h1"], "the second arrived first: the first is still held");
  assert.deepEqual(stillHeld(held, [said("hello"), named("ok", "h2"), named("ok", "h1")]), []);
  // ...the thread on screen carries the name on the message's metadata, all the runtime keeps (GeneralWorkspace `initial`)
  assert.deepEqual(stillHeld(held, [said("hello"), { ...said("ok"), metadata: { custom: { line: "h1" } } }], "drawn").map((l) => l.id), ["h2"]);
  // ...and a named line of the conversation's is never an unnamed held line arriving, by its words or by the count (the coding CLI's road)
  const loose = [{ id: "c1", text: "ok", after: 1 }];
  assert.deepEqual(stillHeld(loose, [said("hello"), named("ok", "other-1")]), loose);
  assert.deepEqual(stillHeld([...held, ...loose], [said("hello"), said("ok")]).map((l) => l.id), ["h1", "h2"], "an unnamed one still goes by its words");
});

test("a kept line is this page's own by its name; unnamed, each of the page's copies stands for one kept line", () => {
  const server = [said("compare three tools")], waiting = [{ id: 7, text: "ok", line: "h1" }, { id: 8, text: "ok", line: "other-1" }, { id: 9, text: "ok" }, { id: 10, text: "ok" }];
  // this page holds h1: the other window's "ok" and the phone's two are drawn, and its own is not drawn twice
  assert.deepEqual(waitingShown(waiting, [{ id: "h1", text: "ok", named: true }], server, server).map((w) => w.id), [8, 9, 10]);
  // ...its thread streamed one "ok" of its own, with no name: one kept line is that one, not both
  assert.deepEqual(waitingShown(waiting, [], [...server, said("ok")], server).map((w) => w.id), [7, 8, 10]);
  assert.deepEqual(waitingShown(waiting, [{ id: "c1", text: "ok" }], server, server).map((w) => w.id), [7, 8, 10], "nor an unnamed held line for more than one");
  // ...A CODING CHAT'S HELD LINE (named: false - its conversation never echoes the name) is still sent under its id, and the kept copy carries it:
  // that copy is this held line, drawn once (the browser walk, 2026-11-10: a line typed after a coding session ended stood twice, both "held")
  const coding = [{ id: 11, text: "check the tax line", line: "c2" }, { id: 12, text: "check the tax line" }];
  assert.deepEqual(waitingShown(coding, [{ id: "c2", text: "check the tax line" }], server, server).map((w) => w.id), [12], "its own kept copy, by its id; the phone's, by nothing");
});

test("the chat sends a held line under its name, and the thread keeps the name the server gives back", async () => {
  const { readFileSync } = await import("node:fs");
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(ws, /setHeld\(\(h\) => \[\.\.\.h, \{ id, text: w \|\| withImages\("", files\.map\(\(a\) => a\.path\)\), after, drawn: mineDrawn\.length, named: !road \}\]\);/);
  assert.match(ws, /api\.post\(`\/api\/tasks\/\$\{task\.TaskId\}\/assistant\/messages`, \{ text: w, attachments: files\.map\(\(a\) => a\.path\), line_id: id \}/);
  assert.match(ws, /\.\.\.\(m\.line \? \{ line: m\.line \} : \{\}\),/);
  // ...the public demo's own server answers the same way: a line typed there is not left standing at the foot
  assert.match(readFileSync(new URL("../src/demoApi.js", import.meta.url), "utf8"), /role: "user", content: \[\{ type: "text", text: asked \}\], \.\.\.\(body\?\.line_id \? \{ line: body\.line_id \} : \{\}\) \}\);/);
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
  const held = ws.indexOf("<FootLines "), shut = ws.lastIndexOf("</ThreadPrimitive.If>", held);
  assert.ok(held > ws.indexOf("<PublishedPages pages={published} deliver />") && shut > 0, "after the turn's own cards");
  assert.match(ws.slice(ws.indexOf('data-tq-held=""'), ws.indexOf('data-tq-held=""') + 600), /<div className="tq-aui-user-head"><PersonOutlineIcon[^>]*\/>You\{l\.at \? ` · \$\{when\(l\.at\)\}` : ""\}<\/div>/);
});

// THE LINE IS LET GO ONLY ONCE THE THREAD ON SCREEN DRAWS IT (the recorded walk, 2026-11-10: in a coding chat his line vanished for a frame the
// moment the agent took it - the held copy was let go when the server's payload had the line, a render before the thread drew it)
test("a held line is let go by the thread on screen, never by the payload alone", async () => {
  const { readFileSync } = await import("node:fs");
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(ws, /useEffect\(\(\) => \{ setHeld\(\(h\) => \(h\.length \? stillHeld\(h, mineDrawn, "drawn"\) : h\)\); \}, \[mineDrawn\]\);/);
  assert.doesNotMatch(ws, /stillHeld\(h, messages\)/);
});
