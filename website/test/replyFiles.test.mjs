// The card says what is GOING, not just who it is going to.
//
// TQ-0526's draft read "Attached are the PTO accrual files for the 8/31 payroll" and the card showed
// nothing at all, because nothing could be attached - so approving it would have sent the words and
// no files (the owner, 2026-09-14: "otherwise it looks like it sends without attachment").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { filesPromised, filesShort, sizeText } from "../src/replyFiles.js";
import { replyEnvelope } from "../src/sendState.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a file is named the way a person would say its size", () => {
  assert.equal(sizeText(900), "900 B");
  assert.equal(sizeText(1740 * 1024), "1.7 MB");
  assert.equal(sizeText(64 * 1024), "64 KB");
  assert.equal(sizeText(undefined), "0 B");
});

test("whether a draft promises a file is its writer's word on the review, never read off the text", () => {
  assert.equal(filesPromised({ FilesPromised: JSON.stringify({ named: ["PTO_Accruals.xlsx"] }) }), true);
  assert.equal(filesPromised({ FilesPromised: JSON.stringify({ named: [] }) }), true, "a file promised, unnamed");
  // the words say "attached" and the writer said no file rides with it: the card believes the writer
  assert.equal(filesPromised({ DraftText: "His logins were attached to an old leftover record.", FilesPromised: null }), false);
  assert.equal(filesPromised({}), false);
  assert.equal(filesPromised(null), false);
  assert.equal(filesPromised({ FilesPromised: "not json" }), false);
  // ...and nothing in the module reads the draft's words
  assert.doesNotMatch(read("replyFiles.js"), /attach\(|enclosed|\.test\(/);
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

test("the surface that approves a reply shows what rides with it", () => {
  const review = read("ReviewDecision.jsx");
  assert.match(review, /<ReplyFiles reviewId=\{r\.ReviewId\} files=\{deliveryFiles\(filedDelivery\)\}/);
});

test("a chat offers no picker that lies, and says a file cannot ride only where its draft promises one", () => {
  const pane = read("ReplyFiles.jsx");
  assert.match(pane, /\) : \(promised \|\| files\.length\) \? \(/);
  assert.match(read("ReviewDecision.jsx"), /promised=\{filesPromised\(r\)\}/);
  assert.match(read("ReviewDecision.jsx"), /deliveryFiles\(filedDelivery\)\.length > 0 \|\| filesPromised\(r\)\)/);
  assert.match(pane, /message cannot carry one — reply by email with the file instead/);
  // ...no line under every chat draft that promises nothing (the owner, 2026-10-22: no explanation lines)
  assert.doesNotMatch(pane, /answer by email to attach one/);
  assert.match(pane, /const mail = String\(channel \|\| "email"\)\.toLowerCase\(\) === "email"/);
  // the warning is a LINE, never a block: "attached in my last mail" is a real sentence
  assert.doesNotMatch(pane, /disabled=\{missing/);
});

// THREE NAMED, TWO RIDE (2026-11-04): the agent's draft said "here are the three" and Close out showed two chips and nothing more - the third,
// over the mailbox's cap, was refused in a comment under the agent's pane. The card says which file did not ride and why, where the files are.
test("a file the agent named that did not ride is said on the card, by name and why", () => {
  const two = [{ name: "_ Summary - Erin_ Gail.xlsx", size: 9 }, { name: "_ Summary - Ray_ Omar.xlsx", size: 9 }];
  const r = { FilesPromised: JSON.stringify({ named: ["% Summary - Erin, Gail.xlsx", "% Summary - Ray, Omar.xlsx", "% Summary - 15 east sites.xlsx"] }),
    Deliver: JSON.stringify({ kind: "reply", to: ["a@b.test"], attachments: two,
      not_attached: [{ name: "% Summary - 15 east sites.xlsx", why: "that file is over 25MB, which no mailbox will accept" }] }) };
  assert.deepEqual(filesShort(r, two), ["Not attached: % Summary - 15 east sites.xlsx — that file is over 25MB, which no mailbox will accept."]);
  // ...and with no reason kept (a writer that named three, two attached by hand), the count says it
  const counted = { FilesPromised: r.FilesPromised, Deliver: JSON.stringify({ attachments: two }) };
  assert.deepEqual(filesShort(counted, two), ["The draft names 3 files and 2 are attached."]);
  // ...all there, or none promised, or none attached at all (the card's own "nothing is attached" line covers that): nothing more
  assert.deepEqual(filesShort({ FilesPromised: JSON.stringify({ named: ["a.xlsx", "b.xlsx"] }) }, two), []);
  assert.deepEqual(filesShort({}, two), []);
  assert.deepEqual(filesShort({ FilesPromised: r.FilesPromised }, []), []);
  assert.match(read("ReviewDecision.jsx"), /short=\{filesShort\(filedDelivery, deliveryFiles\(filedDelivery\)\)\}/);
});
