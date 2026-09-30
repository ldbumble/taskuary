import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");

test("message detail toggles are keyboard-operable and expose their state", () => {
  for (const state of ["full", "showRaw", "showQuoted"]) {
    const toggle = source.match(new RegExp(`<Typography[^>]+onClick=\\{\\(\\) => set${state[0].toUpperCase()}${state.slice(1)}\\(!${state}\\)\\}[^>]*>`))?.[0];
    assert.ok(toggle, `missing ${state} toggle`);
    assert.match(toggle, /component="button"/);
    assert.match(toggle, /type="button"/);
    assert.match(toggle, new RegExp(`aria-expanded=\\{${state}\\}`));
  }
});
