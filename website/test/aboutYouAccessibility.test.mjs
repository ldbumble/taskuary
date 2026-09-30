import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("every About you text field has an accessible name", () => {
  const body = fs.readFileSync(path.join(process.cwd(), "src", "AboutYou.jsx"), "utf8");
  const fields = body.match(/<TextField\b[\s\S]*?\/>/g) || [];

  assert.equal(fields.length, 5, "the test should cover every About you text field");
  for (const field of fields) {
    assert.match(field, /inputProps=\{\{[\s\S]*?"aria-label":\s*"[^"]+"/, field);
  }
});
