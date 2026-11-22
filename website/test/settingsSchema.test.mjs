import test from "node:test";
import assert from "node:assert/strict";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };


test("every knob carries what the page needs to draw it", () => {
  assert.ok(Object.keys(schema.knobs).length > 40);
  for (const [key, meta] of Object.entries(schema.knobs)) {
    for (const f of ["group", "label", "type", "desc"]) assert.ok(meta[f], `${key} lacks ${f}`);
    assert.ok(schema.groups.includes(meta.group), `${key}: unknown group ${meta.group}`);
    if (meta.type === "select") assert.ok(Array.isArray(meta.options) && meta.options.length, `${key}: a select with no options`);
  }
});
