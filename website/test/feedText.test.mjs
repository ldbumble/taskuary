// The timeline row's text. Every case here was a real rendering, not a hypothetical.
import test from "node:test";
import assert from "node:assert/strict";
import { subjectOf, sourceOf, structured } from "../src/feedText.js";

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

// Chat is not mail: WhatsApp and Slack carry no subject at all, and Teams synthesizes one that
// only repeats the sender. Both used to leave the row blank, or the work pill reading "(no
// subject)", next to a message nobody could see without opening it (owner, 2026-09-07).
test("chat has no subject, so the row says what was actually said", () => {
  const said = "So what's their moves if it's free?";
  assert.equal(subjectOf(row({ FromName: "Tess", SourceName: "group chat", Preview: said })), said);
  assert.equal(subjectOf(row({ FromName: "Gail Moreno", Subject: "Teams chat with Gail Moreno",
    Preview: "can you add Nathan to the call" })), "can you add Nathan to the call");
  assert.equal(subjectOf(row({ FromName: "Tess", SourceName: "group chat", Subject: "Tess in group chat",
    Preview: "Budgeting" })), "Budgeting");
  // a chat WITH a real subject still has one
  assert.equal(subjectOf(row({ FromName: "Fireflies", Subject: "AI Agents", Preview: "Nathan invited" })), "AI Agents");
});

test("what it says has to fit the pill: one line, cut on a word", () => {
  const long = "Budgeting for the next quarter needs the new headcount plan from Nathan before anyone can sign it off";
  const out = subjectOf(row({ FromName: "Tess", Preview: long }));
  assert.ok(out.length <= 91, `too long for the pill: ${out.length}`);
  assert.ok(out.endsWith("…") && !out.endsWith(" …"), `cut mid-word: ${out}`);
  assert.equal(subjectOf(row({ FromName: "Tess", Preview: "first line\nsecond line" })), "first line");
  assert.equal(subjectOf(row({ FromName: "Tess", Preview: "   " })), "");
});

// A generated body (a report's error summary, the assistant's own note) is WRITTEN as structure -
// a lead sentence, then a list. The Summary pane put it through one flattening clamp, so it read
// as a wall of run-on text with the list mashed into the sentence (the owner, 2026-09-15: "let's
// clean up the message section making it look better not just continuous text").
test("a body with a list is split into its lead and its lines", () => {
  const body = "Error summary: 5 runs show duplicate-vendor discards in Vendors to Intacct.\n\n"
    + "By runTime / runId:\n"
    + "- 2026-09-15 14:39:04, runId 976445: Patricia Heflin already exists (V68593)\n"
    + "- 2026-09-15 13:39:05, runId 976407: Capital Caring Health already exists (V68661)";
  const { lead, bullets } = structured(body);
  assert.equal(lead, "Error summary: 5 runs show duplicate-vendor discards in Vendors to Intacct.\n\nBy runTime / runId:");
  assert.equal(bullets.length, 2);
  assert.equal(bullets[0], "2026-09-15 14:39:04, runId 976445: Patricia Heflin already exists (V68593)");
});

test("ordinary mail is left exactly as it was", () => {
  const body = "Hi Alex,\n\nCan you approve the refund for Heflin before Friday?\n\nThanks";
  const { lead, bullets } = structured(body);
  assert.equal(lead, body, "a body with no list must not be re-cut - a greeting is not a summary");
  assert.deepEqual(bullets, []);
});

test("a hyphen inside a sentence is not a list", () => {
  const body = "The refund - which Hafiza resubmitted - posts against the existing id.";
  assert.deepEqual(structured(body).bullets, []);
});

test("nothing at all is still safe to render", () => {
  assert.deepEqual(structured(""), { lead: "", bullets: [] });
  assert.deepEqual(structured(null), { lead: "", bullets: [] });
});
