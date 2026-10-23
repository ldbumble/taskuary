import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// "change" beside To opened an empty picker while the footer still named the old address (the UI audit, 2026-10-21): it opens on it
test("To's change opens on the address it has, kept until another is picked", () => {
  const ui = readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");
  // ...its addresses: the line wears the sender's name, and saved back whole that name became the address (replyDelivery.bareAddresses)
  assert.match(ui, /\{\.\.\.pressable\(\(\) => \{ setText\(bareAddresses\(to\)\.join\(", "\)\); setOpen\(true\); \}\)\} data-tq-to-change/);
});
