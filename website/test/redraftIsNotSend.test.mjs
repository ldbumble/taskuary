// A REDRAFT IS NOT A SEND (the email walk, 2026-10-29): Redraft set the card's `busy`, and every Send label reads busy as
// "Sending…" - so the owner watched a reply apparently leave while the model was only rewriting it. Redraft has its own state:
// Send is held off but keeps its word, and Redraft says "Redrafting…".
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(fileURLToPath(new URL("../src/ReviewDecision.jsx", import.meta.url)), "utf8");
const redraft = src.slice(src.indexOf("const redraft = async"), src.indexOf("// THE DECISION'S VERBS"));

test("Redraft never sets the send's busy", () => {
  assert.doesNotMatch(redraft, /setBusy\(/);
  assert.match(redraft, /setRedrafting\(true\)/);
  assert.match(redraft, /finally \{[^}]*setRedrafting\(false\)/);
});

test("a redraft holds Send off without renaming it, and names itself", () => {
  assert.match(src, /const drafting = job\?\.state === "drafting" \|\| redrafting;/);
  assert.match(src, /const off = busy \|\| drafting;/);
  assert.match(src, /redrafting && r\.DraftText \? "Redrafting…"/);
  assert.doesNotMatch(src, /disabled(: |=\{)busy\b/, "every button is held by `off`, which a redraft sets");
});
