import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { blankRefusal, blankSpans, findBlanks } from "../src/blanks.js";

// ONE LIST OF EDGE CASES with the server (tests/test_blanks.py): the box marks exactly what Send refuses over
const { cases } = JSON.parse(readFileSync(new URL("../../tests/fixtures/blanks_cases.json", import.meta.url), "utf8"));

test("every shared case finds the same blanks as the server", () => {
  for (const [text, want] of cases) assert.deepEqual(findBlanks(text), want, JSON.stringify(text));
});

test("a span points at the slot in the text the box shows", () => {
  const t = "See you on [DATE].";
  const [[a, b, s]] = blankSpans(t);
  assert.equal(t.slice(a, b), "[DATE]"); assert.equal(s, "[DATE]");
});

test("the refusal reads as the server's, word for word", () => {
  assert.equal(blankRefusal("because [REASON]."), "Fill in [REASON] first");
  assert.equal(blankRefusal("[DATE] and [REASON]"), "Fill in [DATE] and [REASON] first");
  assert.equal(blankRefusal("[DATE], [TIME] and [REASON]"), "Fill in [DATE], [TIME] and [REASON] first");
  assert.equal(blankRefusal("Re: [External] all filled in."), "");
});
