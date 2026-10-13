import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(
  fileURLToPath(new URL("../src/WallView.jsx", import.meta.url)),
  "utf8"
);

test("wall column switcher uses accessible native buttons", () => {
  assert.match(
    src,
    /COLS\.map\(\s*\(n\)\s*=>\s*\(\s*<Box\b[\s\S]*?component="button"/,
    "column options should use native buttons"
  );

  assert.match(
    src,
    /component="button"[^>]*type="button"/,
    "column buttons should declare type=button"
  );

  assert.match(
    src,
    /aria-pressed=\{cols\s*===\s*n\}/,
    "the active column option should expose its pressed state"
  );
});

test("wall column switcher resets native button styling", () => {
  const switcher = src.match(
    /COLS\.map\(\s*\(n\)\s*=>\s*\([\s\S]*?\{n\}×[\s\S]*?\)\s*\)\s*\}/
  );

  assert.ok(switcher, "could not find the column switcher");
  assert.match(switcher[0], /border:\s*0/);
  assert.match(switcher[0], /font:\s*"inherit"/);
});