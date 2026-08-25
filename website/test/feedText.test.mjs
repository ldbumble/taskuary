// The timeline row's text. Every case here was a real rendering, not a hypothetical.
import test from "node:test";
import assert from "node:assert/strict";
import { subjectOf, sourceOf } from "../src/feedText.js";

const row = (o) => ({ Subject: "", FromName: "", FromEmail: "", SourceName: "", ...o });

test("a report stops repeating its own title", () => {
  assert.equal(subjectOf(row({ FromName: "Morning digest", SourceName: "Reports",
    Subject: "Morning digest — the last 3 days" })), "the last 3 days");
});

test("a Teams synthesized subject is dropped entirely", () => {
  assert.equal(subjectOf(row({ FromName: "Ayush", SourceName: "eng-chat", Subject: "Ayush in eng-chat" })), "");
});

// The prefix strip used to match on bare characters and ate real words.
for (const [who, subject] of [
  ["Bob", "Bobby's quarterly numbers"],
  ["Ayush", "Ayushman scan results are in"],
  ["CI", "CID lookup failing on prod"],
  ["Sam", "Sam needs the invoice"],
  ["Al", "Already fixed upstream"],
]) test(`"${who}" does not chew into "${subject}"`, () => {
  assert.equal(subjectOf(row({ FromName: who, SourceName: "x", Subject: subject })), subject);
});

test("separators other than an em dash also count", () => {
  for (const sep of ["—", "-", "–", ":", "·"])
    assert.equal(subjectOf(row({ FromName: "Nightly", Subject: `Nightly ${sep} build is green` })), "build is green");
});

test("a missing subject or sender is not a crash", () => {
  assert.equal(subjectOf(row({})), "");
  assert.equal(subjectOf(row({ Subject: "orphan" })), "orphan");
});

test("the source chip hides when it only echoes the sender", () => {
  assert.equal(sourceOf(row({ SourceName: "Ayush", FromName: "Ayush" })), "");
  assert.equal(sourceOf(row({ SourceName: "eng-chat", FromName: "Ayush" })), "eng-chat");
  assert.equal(sourceOf(row({ SourceName: "a@b.com", FromEmail: "a@b.com" })), "");
});
