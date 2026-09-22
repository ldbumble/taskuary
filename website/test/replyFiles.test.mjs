// The card says what is GOING, not just who it is going to.
//
// TQ-0526's draft read "Attached are the PTO accrual files for the 8/31 payroll" and the card showed
// nothing at all, because nothing could be attached - so approving it would have sent the words and
// no files (the owner, 2026-09-14: "otherwise it looks like it sends without attachment").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { promisesFiles, sizeText } from "../src/replyFiles.js";
import { replyEnvelope } from "../src/sendState.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a file is named the way a person would say its size", () => {
  assert.equal(sizeText(900), "900 B");
  assert.equal(sizeText(1740 * 1024), "1.7 MB");
  assert.equal(sizeText(64 * 1024), "64 KB");
  assert.equal(sizeText(undefined), "0 B");
});

test("the card can tell when the words promise a file", () => {
  assert.equal(promisesFiles("Attached are the PTO accrual files for the 8/31 payroll."), true);
  assert.equal(promisesFiles("I'm attaching the workbook."), true);
  assert.equal(promisesFiles("Please find enclosed the summary."), true);
  assert.equal(promisesFiles("Thanks - the numbers are in the body below."), false);
  assert.equal(promisesFiles(""), false);
});

test("the delivery envelope carries the files up to the card", () => {
  const env = replyEnvelope({ Deliver: JSON.stringify({ kind: "reply", to: ["a@b.test"], cc: [],
    attachments: [{ name: "PTO_Raw.zip", path: "C:/x/PTO_Raw.zip", size: 1740 * 1024 }] }) });
  assert.equal(env.attachments.length, 1);
  assert.equal(env.attachments[0].name, "PTO_Raw.zip");
  // an old envelope, written before any of this existed, still reads
  assert.deepEqual(replyEnvelope({ Deliver: JSON.stringify({ kind: "reply", to: ["a@b.test"] }) }).attachments, []);
  // ...and junk in the list never reaches the render
  assert.deepEqual(replyEnvelope({ Deliver: JSON.stringify({ kind: "reply", attachments: [null, {}, 3] }) }).attachments, []);
});

test("both surfaces that can approve a reply show what rides with it", () => {
  const feed = read("FeedView.jsx"), review = read("ReviewDecision.jsx");
  assert.match(feed, /<ReplyFiles reviewId=\{reviewId\} files=\{envelope\?\.attachments \|\| \[\]\}/);
  assert.match(review, /<ReplyFiles reviewId=\{r\.ReviewId\} files=\{deliveryFiles\(r\)\}/);
  // ...and the button counts them, so the send is never a surprise
  assert.match(feed, /files\.length \? `\$\{files\.length\} file\$\{files\.length === 1 \? "" : "s"\}` : ""/);
});

test("a chat says it cannot carry a file instead of offering a picker that lies", () => {
  const pane = read("ReplyFiles.jsx");
  assert.match(pane, /cannot carry a file/);
  assert.match(pane, /const mail = String\(channel \|\| "email"\)\.toLowerCase\(\) === "email"/);
  // the warning is a LINE, never a block: "attached in my last mail" is a real sentence
  assert.doesNotMatch(pane, /disabled=\{missing/);
});
