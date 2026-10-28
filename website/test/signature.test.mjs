// The reply box shows the signature that goes under the email (signatures.py; the owner, 2026-10-28: "It should use the default
// signature always"): an empty box opens on it, a draft gets it once, a signed draft is left alone, chat has none.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { withSignature, withoutSignature } from "../src/signature.js";

const SIG = "Alex Doyle\nOperations | Northwind";

test("an empty box opens on the signature, two lines down for the words", () => {
  assert.equal(withSignature("", SIG), `\n\n${SIG}`);
  assert.equal(withoutSignature(`\n\n${SIG}`, SIG).trim(), "", "only the signature is still an empty box");
});

test("a draft gets it once, and a signed one is not signed again", () => {
  assert.equal(withSignature("Hi Erin,\n\nDone.", SIG), `Hi Erin,\n\nDone.\n\n${SIG}`);
  assert.equal(withSignature(`Hi Erin,\n\nDone.\n\n${SIG}`, SIG), `Hi Erin,\n\nDone.\n\n${SIG}`);
  assert.equal(withoutSignature(`Hi Erin,\n\nDone.\n\n${SIG}`, SIG), "Hi Erin,\n\nDone.");
});

test("no signature (chat, an invite, the switch off) leaves the box as filed", () => {
  assert.equal(withSignature("on it", ""), "on it");
  assert.equal(withSignature("", ""), "");
});

test("the reply box is drawn with it and counts only the words above it", () => {
  const src = readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");
  assert.match(src, /text \?\? withSignature\(reviewText\(r\), r\.Signature\)/);
  assert.doesNotMatch(src, /value\.trim\(\)/, "Send is offered on what the owner wrote, not on the signature alone");
});
