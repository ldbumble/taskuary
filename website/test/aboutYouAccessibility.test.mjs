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

test("avatar style chips are buttons announcing their pressed state", () => {
  // On About you, each avatar style chip must take keyboard focus and tell
  // screen readers which style is active (#140).
  const body = fs.readFileSync(path.join(process.cwd(), "src", "AboutYou.jsx"), "utf8");
  assert.match(body, /const activeStyle = preview\?\.style \|\| f\.owner_avatar_style \|\| "monogram"/);
  const chips = body.match(/<Box key=\{s\} component="button" type="button" aria-pressed=\{activeStyle === s\}[\s\S]*?>\{s\}<\/Box>/);
  assert.ok(chips, "style chips are buttons with aria-pressed from the shared local");
  assert.match(chips[0], /fontFamily: "inherit"/);
});
