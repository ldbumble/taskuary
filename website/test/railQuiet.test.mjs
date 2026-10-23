// BUTTONS DO THE TALKING (the owner, 2026-10-22: "I hate free text"): a click on the rail puts its item on the table and says nothing
// in the chat - no 'Show me "..."' bubble for a row, no receipt listing a section's titles for its heading.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("a rail row is pulled quietly, as a search hit is", () => {
  assert.doesNotMatch(src, /Show me “\$\{i\.title\}”/, "no bubble saying the click");
  assert.match(src, /!i\.settling && onPull\(i\.key\)\)\}/);
});

test("a section click walks its first row and posts no receipt listing the section", () => {
  const walk = src.slice(src.indexOf("const walkSection = (level) => {"), src.indexOf("const browse = (area"));
  assert.match(walk, /pull\(first\.key, null\);/);
  assert.doesNotMatch(walk, /setMsgs|role: "receipt"|to go through/, "the rail already lists the section");
});
