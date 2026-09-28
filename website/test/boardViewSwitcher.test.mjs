import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/BoardView.jsx", import.meta.url)), "utf8");

test("the Board view switcher exposes keyboard-operable tabs", () => {
  assert.match(source, /role="tablist"/);
  assert.match(source, /role="tab"/);
  assert.match(source, /tabIndex=\{0\}/);
  assert.match(source, /aria-selected=\{view === o\.k\}/);
  assert.match(source, /e\.key === "Enter" \|\| e\.key === " "/);
});
