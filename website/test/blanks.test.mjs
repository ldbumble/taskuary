import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { blankAsk, blankRefusal, blankSpans, findBlanks } from "../src/blanks.js";

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

// THE PRESS ASKS ONCE (the owner, 2026-11-08): Send stays lit, and its press asks about the first blank before anything goes
test("the ask names the first blank, a long choice by its head, and nothing when the draft is filled", () => {
  assert.equal(blankAsk("The review is in [ROOM]. [Gail is joining / Gail is not]"), "This still has [ROOM]. Send anyway?");
  assert.equal(blankAsk("Let you know by ___."), "This still has ___. Send anyway?");
  const long = blankAsk("[Gail is joining / Gail is not joining / I am confirming with Gail]");
  assert.match(long, /^This still has \[Gail is joining \/ Gail is not joining…\]\. Send anyway\?$/);
  assert.equal(blankAsk("All set for Friday - Alex"), "");
});

test("every card that sends a draft asks with the one shared line before it posts", () => {
  for (const f of ["ReviewDecision.jsx", "assistantCards.jsx"]) {
    const src = readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
    assert.match(src, /<BlankAsk /, f); assert.match(src, /blanks_ok: blanksOk/, f);
  }
});
