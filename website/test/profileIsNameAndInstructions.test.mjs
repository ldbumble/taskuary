// A PROFILE IS A NAME AND INSTRUCTIONS (the owner, 2026-10-22): Manage profiles asked for a model provider and a model, and Save waited on
// a CLI connection - so a box with no AI could not make a profile at all. The brain is the AI defaults' answer, asked when work starts.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const panel = readFileSync(new URL("../src/AgentsPanel.jsx", import.meta.url), "utf8");
const pageOf = panel.slice(panel.indexOf("export const AgentsPage"));

test("the profile editor has no provider or model field, and sends neither", () => {
  assert.doesNotMatch(pageOf, /Model provider|Model name|Autocomplete|providerLabel|modelOptions|draft\.provider|draft\.model/);
  assert.match(panel, /const BLANK_PROFILE = \{ name: "", purpose: "", kind: "general", rulesDoc: "", triageEnabled: true \};/);
  assert.match(pageOf, /triage_enabled: draft\.triageEnabled \};/);
});

test("Save needs only a new name and a purpose", () => {
  assert.match(pageOf, /disabled=\{saving \|\| !agents \|\| !draft\.name\.trim\(\) \|\| \(!draft\.existing && !!agents\?\.\[draft\.name\.trim\(\)\]\) \|\| !draft\.purpose\.trim\(\)\}/);
});
