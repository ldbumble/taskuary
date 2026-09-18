import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };

// The knob table lived only in this JSX, so the assistant knew the pile and not one of the 52 knobs
// (2026-09-18). One file, read by both sides - the rule lanes.json already keeps for the lanes.
test("the Settings page draws its knobs from the shared schema file", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/SettingsView.jsx", import.meta.url)), "utf8");
  assert.match(view, /import schema from "\.\.\/\.\.\/taskuary\/settings_schema\.json"/);
  assert.match(view, /const KNOB_META = schema\.knobs;/);
  assert.match(view, /const GROUPS = schema\.groups;/);
  assert.doesNotMatch(view, /const KNOB_META = \{/);
});

test("every knob carries what the page needs to draw it", () => {
  assert.ok(Object.keys(schema.knobs).length > 40);
  for (const [key, meta] of Object.entries(schema.knobs)) {
    for (const f of ["group", "label", "type", "desc"]) assert.ok(meta[f], `${key} lacks ${f}`);
    assert.ok(schema.groups.includes(meta.group), `${key}: unknown group ${meta.group}`);
    if (meta.type === "select") assert.ok(Array.isArray(meta.options) && meta.options.length, `${key}: a select with no options`);
  }
});
