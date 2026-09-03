import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("the Assistant composer offers an accessible emoji response picker", () => {
  assert.match(source, /aria-label="Choose an emoji response"/);
  assert.match(source, /Send a quick response/);
  assert.match(source, /EMOJI_REPLIES\.map\(\(\[emoji, label\]\)/);
  assert.match(source, /aria-label=\{`Send \$\{label\}`\}/);
});

test("an emoji sends immediately unless it is being added to a draft", () => {
  assert.match(source, /if \(text\.trim\(\)\) setText/);
  assert.match(source, /else send\(emoji\)/);
  assert.match(source, /Added to your draft; press send when ready\./);
});
