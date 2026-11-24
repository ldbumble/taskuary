// WHERE A TEXT CHANGED, IN THE TEXT (the owner, 2026-11-24: "show also where it changed in the full text")
import test from "node:test";
import assert from "node:assert/strict";
import { changeMarks, hasChange, wordDiff } from "../src/textDiff.js";

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
