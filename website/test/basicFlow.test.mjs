// THE BASIC FLOW ON THE PAGE (the owner, 2026-11-12: "have you ever seen a chat that you type something new and the past agent turn changes.
// of course not ... nothing ever goes backwards"): the server's list keeps it (conversation.flow_breaks, run over every list the python
// corpora build); the page must not undo it with its own caches or its own lines. Invented people only.
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { flowBreaks, newerList, waitingChips, withMine } from "../src/chatStream.js";

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

test("his line sent at rest has the turn it begins under it even in the beat the server says working and has no turn yet", () => {
  const got = withMine({ items: [mail, answer], pending: [], working: true }, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items.map((x) => [x.id, x.state || ""]), [["m:1", ""], ["t:m:1:0", "done"], ["l-2", ""], ["t:l-2:0", "starting"]]);
});

test("his line greys the reply card above it in the same frame, before the server's read is back", () => {
  const card = { id: "r:1", review: 1, what: "draft_reply", status: "pending", was: { text: "Hi Gail, yes." } };
  const read = { items: [mail, { ...answer, cards: [card] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items[1].cards.map((c) => c.status), ["passed"]);
  assert.deepEqual(withMine(read, []).items[1].cards.map((c) => c.status), ["pending"]);     // ...and only then
});

test("a line whose send failed stays where it stands in his own words; the failure is one line under it with Try again", async () => {
  const read = { items: [mail, answer], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true, err: "The agent did not start" }]);
  assert.deepEqual(got.items.map((x) => x.id), ["m:1", "t:m:1:0", "l-2"]);          // in place, no turn under it, never by the box
  assert.deepEqual(got.pending, []);
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /\$\{x\.text\} - \$\{x\.err\}/, "an error is never glued into his words");
  assert.match(src, /data-tq-line-failed="">\{x\.err\}\{retry && <> · <button type="button" className="tq-aui-arrived-more-btn"\n\s+data-tq-try-again=""/);
});

test("what came in waits as a count on its sender's chip, his outside replies as their own, each naming the items it stands for", () => {
  const p = [{ id: "m:5", kind: "arrival", who: "Cat Priem", channel: "email" }, { id: "m:6", kind: "arrival", who: "Cat Priem", channel: "email" },
    { id: "m:7", kind: "arrival", who: "Gail Moreno", channel: "email" }, { id: "m:8", kind: "arrival", own: true, who: "You", channel: "whatsapp" },
    { id: "l-9", kind: "line", text: "and the dates" }];
  assert.deepEqual(waitingChips(p, "From Cat Priem"), [
    { key: "From Cat Priem", came: true, ids: ["m:5", "m:6"], label: "From Cat Priem · 2 new" },
    { key: "From Gail Moreno", came: false, ids: ["m:7"], label: "From Gail Moreno · 1 new" },
    { key: "You on WhatsApp", came: false, ids: ["m:8"], label: "You on WhatsApp · 1" }]);
});

test("his waiting lines are slim rows over the box - the newest two, +N more, Send now only where the turn takes words, a trash", async () => {
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /const rows = items\.filter\(\(x\) => x\.kind !== "arrival"\), shown = waitingShown\(rows, 2\), more = rows\.length - shown\.length;/);
  assert.match(src, /\{x\.kind === "line" && now && onNow && <button type="button" className="tq-conv-pending-act" data-tq-send-now=""/);
  assert.match(src, /data-tq-drop-line="" onClick=\{\(\) => onDrop\(x\)\}/);
  assert.doesNotMatch(src, /Waiting for the agent\{items\.length/, "no heading, no box");
  const css = await readFile(new URL("../src/generalWorkspace.css", import.meta.url), "utf8");
  assert.match(css, /\.tq-conv-pending \{ display: flex; flex-direction: column; align-items: flex-end;/);
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

test("a turn at work says what is happening, or what we wait for, beside its dots - one line, on every level", async () => {
  const { workingLine } = await import("../src/chatStream.js");
  const label = (s) => (s.status === "running" ? s.doing : s.summary);
  const parts = [{ type: "work", steps: [{ summary: "Read invoices.csv", status: "done" }] }, { type: "said", text: "x" },
    { type: "work", steps: [{ summary: "Ran a command", doing: "Running a command", status: "running" }] }];
  assert.equal(workingLine(parts, label), "Running a command");
  // ...and what we wait for, where no step runs: the model writing, a session opening, his press (waitingOn)
  assert.equal(workingLine([{ type: "work", steps: [{ summary: "Read a.csv", status: "done" }] }], label), "Thinking…");
  assert.equal(workingLine([], label, { starting: true }), "Waiting for the agent to start");
  assert.equal(workingLine(parts, label, { ask: "Waiting for your Allow once" }), "Waiting for your Allow once");
  const { waitingOn } = await import("../src/chatStream.js");
  assert.equal(waitingOn({ permissions: [{}] }), "Waiting for your Allow once");
  assert.equal(waitingOn({ asking: { request_id: "signin:bank.example" } }), "Waiting for you to sign in");
  assert.equal(waitingOn({ asking: { request_id: "q1" } }), "Waiting for your answer");
  assert.equal(waitingOn({}), "");
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /: doing \? <span className="tq-aui-working-line" data-tq-working-line="" title=\{doing\}>\{doing\}<\/span> : null/);
});
