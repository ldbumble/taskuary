import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("a historical finished-task card is never restored as current funnel work", () => {
  const exclusions = source.match(/\["brief", "setup", "agentdone"\]/g) || [];
  assert.equal(exclusions.length, 2, "both initial history and live watcher updates exclude closed-task cards");
});
