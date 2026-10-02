// BREAK IT IN TWO OPENS AT ONCE (the owner, 2026-10-01: buttons never wait on the AI). The drawer held a spinner where the form
// goes until the model had suggested a split; now the form is there at the press and the suggestion fills in what is still empty.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const part = (src, from, to) => src.slice(src.indexOf(from), src.indexOf(to, src.indexOf(from)));

test("Break it in two opens at once and the AI's split fills in only what the owner has not typed", () => {
  const split = part(read("Reshape.jsx"), "const SplitInTwo", "// The router's own signals");
  assert.doesNotMatch(split, /!sug \? <CircularProgress/, "the form is never held behind the suggestion");
  assert.match(split, /setFirst\(\(v\) => typed\.current\.first \? v : /, "a suggestion never types over the owner");
  assert.match(split, /setSecond\(\(v\) => typed\.current\.second \? v : /);
  assert.match(split, /Reading it for two jobs…/);
});
