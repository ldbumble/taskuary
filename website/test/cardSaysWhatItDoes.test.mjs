import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A CARD SAYS WHAT IS HAPPENING NOW (the UI audit, 2026-10-21): setup's key check was an empty grey spinner over "What AI do you
// have?", and a good Save left the last Test's failure ("need tenant_id...") standing under it
const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");

test("a key or mailbox being checked says so beside its button", () => {
  assert.match(src, /\{busy === "save" && <Typography variant="body2" data-tq-checking=""/);
  assert.match(src, /"Checking your key works - it sorts one test email, a minute or two…"/);
});

test("a save clears the last Test's verdict and says to press Test, on the mail card and the generic card", () => {
  assert.equal((src.match(/data-tq-saved-test=""[^>]*>Saved - press Test to check it\./g) || []).length, 2);
  assert.match(src, /setSecret\(""\); setCfg\(withoutWriteOnly\(conn, cfg\)\); setTest\(null\); setFresh\(!d\?\.error\); reload\(\);/);
  assert.match(src, /setMsg\("saved ✓"\); setSecret\(""\); setTest\(null\); setFresh\(true\); reload\(\);/);
  assert.equal((src.match(/setBusy\("test"\); setFresh\(false\);/g) || []).length, 2, "a Test pressed is the news again");
});
