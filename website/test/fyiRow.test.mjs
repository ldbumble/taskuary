// An fyi says its thing ONCE, and its two doors are named for what they do.
//
// The card drew the item's title and then its gist under it. Mail has a subject and a body, so two
// lines earn their place - but an assistant's idea has no subject: the funnel files the same
// sentence as title and as gist, so the card printed it twice, truncated at two different points,
// beside two buttons reading "Read" and "Dig in" (the owner, 2026-09-14: "Read/Dig in mean the same
// thing and are hard to read? they eyes don't focus on one thing").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { gistFor, norm } from "../src/fyiRow.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// the row from the owner's screenshot: title and gist are one sentence, cut at 140 and at 240
const IDEA = {
  key: "msg:7001", who: "Assistant",
  title: 'Both Summit Bank contacts auto-replied out at 16:01 on "Riverton Operator LLC" — Jackie on maternity leave. I\'d resend to k',
  preview: 'Both Summit Bank contacts auto-replied out at 16:01 on "Riverton Operator LLC" — Jackie on maternity leave. I\'d resend to klazon/mhayes, the SFTP names Neil\'s re',
};

test("a gist that only restates the line above it is not shown", () => {
  assert.equal(gistFor(IDEA), "");
});

test("a real second fact still gets its line", () => {
  const mail = { title: "PTO True up", preview: "Can you send me the PTO file for the 8/31 payroll?" };
  assert.equal(gistFor(mail), "Can you send me the PTO file for the 8/31 payroll?");
  // summary wins over preview when the server wrote one
  assert.equal(gistFor({ title: "PTO True up", summary: "She needs the 8/31 file.", preview: "Hi, ..." }),
    "She needs the 8/31 file.");
});

test("it compares the words, not the whitespace or the case", () => {
  assert.equal(gistFor({ title: "Both   Summit Bank contacts AUTO-REPLIED out", preview: "both summit bank contacts auto-replied out at 16:01" }), "");
  assert.equal(norm("  A   b \n c "), "a b c");
  assert.equal(gistFor({ title: "", preview: "anything" }), "anything");
  assert.equal(gistFor({ title: "x", preview: "" }), "");
  assert.equal(gistFor(null), "");
});

test("the line opens its message, and talking about it is one of the opened line's actions", () => {
  const card = read("assistantCards.jsx");
  assert.match(card, /title=\{open === i\.key \? "Fold it" : "Read it here"\}/);
  assert.match(card, /onSurface\?\.\(i\.key\)\} sx=\{faint\}>Talk about it</);
  assert.doesNotMatch(card, />Dig in</);
  assert.doesNotMatch(card, /\? "Fold" : "Read"/);
});

test("acting on it belongs to the one you opened", () => {
  const card = read("assistantCards.jsx");
  // four buttons on every row is twelve on a three-fyi card, in a card whose point is that
  // nothing here needs you
  assert.match(card, /\{open === i\.key && \(\s*<div className="tq-card-actions tq-fyi-acts"/);
  assert.match(card, /\{open !== i\.key && !folded && gistFor\(i\) &&/);
});

test("the line wraps instead of being cut", () => {
  const css = read("assistantView.css");
  assert.match(css, /\.tq-fyi-line \.t \{[^}]*-webkit-line-clamp: 3/);
  assert.doesNotMatch(css, /\.tq-fyi-row \.t \{[^}]*white-space: nowrap/);
});
