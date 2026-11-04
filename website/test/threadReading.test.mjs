import test from "node:test";
import assert from "node:assert/strict";
import { itemLines, readingOf, readingLines } from "../src/threadReading.js";

const mails = [{ MessageId: 11, FromName: "Ray Colton", SentAt: "2026-11-02 09:00" }];
const full = { asking: "Ray wants the export date", your_part: "Confirm Thursday", others: [{ who: "Gail Moreno", did: "sent the file" }],
  asks: [{ mid: 11, about: "date" }], aside: [{ mid: 12, why: "thanks" }, { mid: 13, why: "thanks" }], on_you: ["Reply to Ray"] };

test("a verdict without a reading is no reading", () => {
  assert.equal(readingOf('{"intent":"fyi"}'), null);
  assert.equal(readingOf(null), null);
  assert.equal(readingOf("not json"), null);
  assert.equal(readingOf({ asks: [] }), null);
});
test("a string or an object reads the same", () => { assert.deepEqual(readingOf(JSON.stringify(full)), readingOf(full)); assert.equal(readingOf(full).asking, "Ray wants the export date"); });
test("the lines: ask, part, others, aside, on you", () => {
  const ls = readingLines(readingOf(full), mails);
  assert.deepEqual(ls.map((l) => l.k), ["ask", "part", "others", "aside", "onyou"]);
  assert.equal(ls.find((l) => l.k === "aside").text, "2 emails are thanks, so the reply answers Ray Colton's 11/2 email");
  assert.equal(ls.find((l) => l.k === "others").text, "Gail Moreno sent the file");
});
test("one aside mail is singular; partial readings never throw", () => {
  const ls = readingLines(readingOf({ asking: "x", aside: [{ mid: 12, why: "a thank-you" }], asks: [{ mid: 11 }] }), mails);
  assert.equal(ls.find((l) => l.k === "aside").text, "1 email is a thank-you, so the reply answers Ray Colton's 11/2 email");
  assert.deepEqual(readingLines(readingOf({ your_part: "p", others: "bad", aside: 3 }), []).map((l) => l.k), ["part"]);
});
test("an item's reading says what it says and what matters to you, and only what it has", () => {
  assert.deepEqual(itemLines(readingOf(full)), [{ k: "says", text: "Ray wants the export date" }, { k: "matters", text: "Confirm Thursday" }]);
  assert.deepEqual(itemLines(readingOf({ asking: "A newsletter" })), [{ k: "says", text: "A newsletter" }]);
  assert.deepEqual(itemLines(null), []);
});
