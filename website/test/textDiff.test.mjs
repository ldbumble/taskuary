// WHERE A TEXT CHANGED, IN THE TEXT (the owner, 2026-11-24: "show also where it changed in the full text")
import test from "node:test";
import assert from "node:assert/strict";
import { changeMarks, hasChange, lengthSaid, wordDiff } from "../src/textDiff.js";

// The owner, 2026-11-26: a routine's instructions grew to ~3,000 characters behind a card that never said how long they were or had been
test("how long the words are, and were where that changed", () => {
  assert.equal(lengthSaid("x".repeat(1204), "y".repeat(2950)), "2,950 characters · was 1,204");
  assert.equal(lengthSaid("Keep it short.", "Keep it brief."), "14 characters", "the same length is said once");
  assert.equal(lengthSaid("", "A new page."), "11 characters · new");
  assert.equal(lengthSaid(undefined, "a"), "1 character · new");
});

test("a line rewritten in a page is struck on its own line: the line break after it is drawn once, the new text's", () => {
  const p = wordDiff("# Posts\n\nOne idea a post.\n\n1. Open with the lesson.\n", "# Posts\n\nOne idea a post, said plainly and first.\n\n1. Open with the lesson.\n");
  assert.deepEqual(p.filter((x) => x.t === "del").map((x) => x.s), ["post. "]);
  assert.equal(p.filter((x) => x.t !== "del").map((x) => x.s).join(""), "# Posts\n\nOne idea a post, said plainly and first.\n\n1. Open with the lesson.\n");
});

// The real walk, 2026-11-26: an agent restructured a skill's page, and read word by word across its lines the struck halves of three old steps
// stood stitched into the new ones. A line that went is struck whole, one that came is lit whole, one rewritten is marked in itself
test("a page is read line by line: a line gone or new is whole, a line rewritten is marked word by word", () => {
  const was = "# Posts\n\nVoice: plain and direct. One idea a post.\n\n1. Open with the lesson.\n2. X: under 260 characters.\n3. No hashtags, no emoji.\n";
  const now = "# Posts\n\nVoice: plain, direct and punchy. One idea a post.\n\nPunch rules:\n- Open with a blunt claim in under 12 words, never a warm-up line.\n\n1. X: under 220 characters, one sentence of proof after the lesson.\n2. No hashtags, no emoji.\n";
  const p = wordDiff(was, now);
  assert.equal(p.filter((x) => x.t !== "del").map((x) => x.s).join(""), now, "same + added is the new page exactly");
  assert.ok(p.some((x) => x.t === "del" && x.s.includes("1. Open with the lesson.\n")), "a line that went is struck whole, with its line break");
  assert.ok(p.some((x) => x.t === "add" && x.s.includes("Punch rules:\n- Open with a blunt claim in under 12 words, never a warm-up line.\n")), "lines that came are lit whole");
  assert.ok(p.some((x) => x.t === "same" && x.s.includes("Voice: ")) && p.some((x) => x.t === "same" && x.s.includes("One idea a post.\n")), "a line rewritten keeps what it kept");
  assert.ok(p.some((x) => x.t === "same" && x.s.includes("No hashtags, no emoji.")), "a line renumbered keeps its words");
  assert.ok(!p.some((x) => x.t === "del" && /lesson\.\n2\. X/.test(x.s) && /Voice/.test(x.s)), "no run stitched across the page");
  assert.deepEqual(wordDiff(was, was), [{ t: "same", s: was }]);
});

test("a new page against nothing is all added, and is the page exactly", () => {
  const page = "---\nname: social-posts\n---\n# Social posts\n\nOne idea a post.\n";
  assert.deepEqual(wordDiff("", page), [{ t: "add", s: page }]);
});

test("the new text whole, what went struck where it stood, what came lit", () => {
  const p = wordDiff("Write three posts a week, long and detailed.", "Write three short posts a week.");
  assert.equal(p.filter((x) => x.t !== "del").map((x) => x.s).join(""), "Write three short posts a week.", "same + added is the new text exactly");
  assert.deepEqual(p.filter((x) => x.t === "del").map((x) => x.s), ["posts a week, long and detailed."], "a word or two kept between changes is one rewrite");
  assert.deepEqual(p.filter((x) => x.t === "add").map((x) => x.s), ["short posts a week."]);
  assert.equal(hasChange(wordDiff("a b", "a b")), false);
});

test("a rewritten sentence reads as what went, then what came - never every other word", () => {
  const p = wordDiff("Each post should be long and detailed, around 300 words, with a story, three lessons and a question at the end.",
    "Keep each post short, under 80 words: one lesson and a question at the end.");
  assert.deepEqual(p.map((x) => x.t), ["del", "add", "same"]);
  assert.equal(p[2].s, "and a question at the end.");
});

test("its marks are spans of the new text the box lights as he types", () => {
  const now = "Keep it short.", m = changeMarks(wordDiff("Keep it long.", now));
  assert.deepEqual(m, [[8, 8, "del"], [8, 14, "add"]]);
  assert.equal(now.slice(8, 14), "short.");
});

test("a long rewrite is one removed run and one added run between their shared ends", () => {
  const a = Array.from({ length: 2500 }, (_, i) => `w${i}`).join(" "), b = Array.from({ length: 2500 }, (_, i) => `v${i}`).join(" ");
  assert.deepEqual(wordDiff(`Start ${a} end`, `Start ${b} end`).map((x) => x.t), ["same", "del", "add", "same"]);
});
