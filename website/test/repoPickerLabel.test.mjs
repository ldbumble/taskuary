import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

test("the repository picker has an accessible name", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/RepoPicker.jsx", import.meta.url)), "utf8");
  assert.match(source, /<select className="tq-start-repo" aria-label="repository"/);
});
