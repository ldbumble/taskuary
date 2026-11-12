// THE BASIC FLOW ON THE PAGE (the owner, 2026-11-12: "have you ever seen a chat that you type something new and the past agent turn changes.
// of course not ... nothing ever goes backwards"): the server's list keeps it (conversation.flow_breaks, run over every list the python
// corpora build); the page must not undo it with its own caches or its own lines. Invented people only.
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { flowBreaks, newerList, withMine } from "../src/chatStream.js";

const mail = { id: "m:1", kind: "arrival", words: "Can you make Thursday?" };
const answer = { id: "t:m:1:0", kind: "turn", state: "done", text: "Drafted a yes.", steps: [], cards: [{ id: "r:1", review: 1, status: "pending" }] };

test("back on a task, the list asked last is drawn - never an older one over it", () => {
  const left = { items: [mail, answer], working: false, _at: 1000 };
  const ahead = { items: [mail, { ...answer, cards: [{ id: "r:1", review: 1, status: "passed" }] }, { id: "l-2", kind: "line", text: "try now" }], working: true, _at: 2000 };
  assert.equal(newerList(left, ahead), ahead);
  assert.equal(newerList(ahead, left), ahead);
  assert.equal(newerList(null, left), left);
  assert.deepEqual(flowBreaks(newerList(left, ahead), left), []);
});

test("his line sent at rest stands over the turn it began, even when the read already has that turn starting", () => {
  const read = { items: [mail, answer, { id: "t:0:1:1", kind: "turn", state: "starting", text: "", steps: [], cards: [] }], pending: [], working: true };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items.map((x) => x.id), ["m:1", "t:m:1:0", "l-2", "t:0:1:1"]);
  assert.deepEqual(flowBreaks(got), []);
  // ...and the old merge, line under the dots, is what the rule names
  assert.match(flowBreaks({ items: [mail, answer, read.items[2], { id: "l-2", kind: "line", text: "try now" }] })[0], /^a: the turn at work/);
});

test("his line greys the reply card above it in the same frame, before the server's read is back", () => {
  const card = { id: "r:1", review: 1, what: "draft_reply", status: "pending", was: { text: "Hi Gail, yes." } };
  const read = { items: [mail, { ...answer, cards: [card] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items[1].cards.map((c) => c.status), ["passed"]);
  assert.deepEqual(withMine(read, []).items[1].cards.map((c) => c.status), ["pending"]);     // ...and only then
});

test("nothing drawn goes or moves, and nothing new is drawn above it", () => {
  const was = { items: [mail, answer] };
  assert.deepEqual(flowBreaks({ items: [mail, answer, { id: "l-2", kind: "line", text: "x" }] }, was), []);
  assert.match(flowBreaks({ items: [mail, { id: "p:9", kind: "press", text: "You sent it." }, answer] }, was)[0], /^f: p:9 is drawn above/);
  assert.match(flowBreaks({ items: [mail] }, was)[0], /^c: t:m:1:0 was on the canvas and is gone/);
});

test("a card is drawn where the list has it and nowhere else - never loose under a turn at work, never live again at the foot", async () => {
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /const loose = working \? \[\] : nodes\.filter\(\(n\) => !used\.has\(n\.key\) && !listed\.has\(n\.rid\)\)/);
  assert.match(src, /const nextLoose = next && !used\.has\("next"\) && !working && !listed\.has\(nextRid\)/);
  // ...a draft no longer to press is greyed in its place with its words: rewritten, set aside as he wrote again, taken back by its agent
  assert.match(src, /const PAST = \{ superseded: .*passed: .*withdrawn: /);
  assert.doesNotMatch(src, /stands below, under a later answer/);
});

test("the box says what the header says: never \"pick the session back up\" while a turn is at work", async () => {
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /cli \|\| convWorks \|\| !conv\.list\?\.ran \? MESSAGE : "Write to pick the session back up…"/);
});
