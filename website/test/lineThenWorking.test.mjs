// THE OWNER'S LINE, THEN THE AGENT AT WORK UNDER IT, AT ONCE (the owner, 2026-11-10: "i put in new prompt it then showed working on top of it to
// the left for split second then disappered and 10 second later the agent thing came up ... NOthing should ever show above a new promt and the
// agnt thing should show right away working"). A line typed to a coding agent took the coding road, which never kept the press: the agent's
// turn was drawn where a working agent's turn stands - over the line held at the chat's foot - and only once the server said it was at work.
// Every road now keeps the press (pendingTurn.sentNow) and the turn it asked for stands under the lines held at the foot. Invented people.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { pendingTurn, sentNow, settled } from "../src/pendingTurn.js";

const src = readFileSync(fileURLToPath(new URL("../src/GeneralWorkspace.jsx", import.meta.url)), "utf8");

test("every typed line keeps its press, so the turn is drawn from the press on every road", () => {
  const hold = src.slice(src.indexOf("const holdText = (w, c) =>"), src.indexOf("const sendArrow ="));
  assert.match(hold, /setSent\(sentNow\(runtime\.thread\.getState\(\)\.messages, Date\.now\(\), busyNow\.current\)\)/);
  assert.ok(hold.indexOf("setSent(") < hold.indexOf("api.post("), "kept before any request goes");
});

test("the turn a line asked for stands under the lines at the foot, never over them", () => {
  assert.match(src, /const atFoot = footLines\.length > 0;/);
  const thread = [{ role: "user", id: "u1" }, { role: "assistant", id: "a1" }];
  const sent = sentNow(thread, 1);
  assert.equal(pendingTurn(thread, { sent }), true, "drawn from the press, before the server says a word");
  assert.equal(pendingTurn(thread, { busy: true, sent }), true, "and while it starts");
  assert.equal(settled([...thread, { role: "user" }, { role: "assistant", id: "live-a2" }], sent), true, "let go once the turn is the thread's own");
});

test("a line typed while a turn runs waits for that turn to end, then the turn it asked for", () => {
  const thread = [{ role: "user", id: "u1" }, { role: "assistant", id: "live-a1" }];
  const sent = sentNow(thread, 1, true);
  assert.equal(sent.busy, true);
  assert.equal(pendingTurn(thread, { busy: true, sent }), false, "the live turn is what is at work - nothing new over it");
  assert.equal(pendingTurn([thread[0], { role: "assistant", id: "a1" }], { busy: false, sent }), true, "its end is not the line's answer");
});
