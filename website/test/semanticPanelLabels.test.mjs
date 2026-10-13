// The known-numbers panel's controls read like the rest of the app ("Run due now", "Test - show me
// the data") instead of sitting in all-lowercase next to sentence-case labels. The strings a
// button is matched by while work runs are keys, not labels, so those stay exactly as they are (#153).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const panel = readFileSync(fileURLToPath(new URL("../src/SemanticPanel.jsx", import.meta.url)), "utf8");

test("the known-numbers panel labels start with a capital letter", () => {
  assert.match(panel, />Add known number<\/Button>/);
  assert.match(panel, /busy === "run it" \? "Running…" : "Run it once"/);
  assert.match(panel, /busy === "check it" \? "Checking…" : "Check every known number"/);
});

test("no lowercase label is left behind, in a label or an attribute", () => {
  for (const label of ["add known number", "run it once", "running…", "check every known number", "checking…"]) {
    assert.ok(!panel.includes(`>${label}<`), `>${label}< is still in the panel`);
    assert.ok(!panel.includes(`"${label}"`), `"${label}" is still in the panel`);
  }
});
