// The HIPAA AI card asked only for the access code, and this build ships no gateway address - so Connect could never work, and
// said the key was wrong (the owner, 2026-10-20: "you forgot the field to put in the url"). The card asks for the address too.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { needsGateway } from "../src/aiShelf.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


test("Connect waits for an address only when the build ships none", () => {
  const card = { Type: "hipaa_ai", GatewayBuiltIn: false };
  assert.equal(needsGateway(card, {}), true);
  assert.equal(needsGateway(card, { base_url: "   " }), true);
  assert.equal(needsGateway(card, { base_url: "https://ai.northwind.example" }), false);
  assert.equal(needsGateway({ ...card, GatewayBuiltIn: true }, {}), false);
  assert.equal(needsGateway({ Type: "groq" }, {}), false);
});
