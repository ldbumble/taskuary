
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("every RepoPicker text field has an accessible name", () => {
  const body = fs.readFileSync(
    path.join(process.cwd(), "src", "RepoPicker.jsx"),
    "utf8"
  );

  const fields = body.match(/<TextField\b[\s\S]*?\/>/g) || [];

  assert.ok(fields.length > 0, "the test should find RepoPicker text fields");

  for (const field of fields) {
    assert.match(
      field,
      /inputProps=\{\{[\s\S]*?"aria-label":\s*"[^"]+"/,
      "every TextField should have an aria-label in inputProps"
    );
  }
});
