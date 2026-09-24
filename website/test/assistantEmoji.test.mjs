import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
const css = readFileSync(fileURLToPath(new URL("../src/assistantView.css", import.meta.url)), "utf8");

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

test("mic, emoji, prompt and send button share one composer line, and stay on its bottom edge as it grows", () => {
  assert.match(source, /width: 34, height: 34/);
  // one line: every control is 34px, so the bottom edge IS the centre line. Grown to many lines, the buttons
  // stay by the last line, the way every chat app keeps them (2026-09-24)
  assert.match(css, /\.tq-compose-box \{[^}]*align-items: flex-end/);
  assert.match(source, /ref=\{composeRef\}/);
  assert.match(css, /\.tq-compose-box textarea \{[^}]*min-height: 34px/);
  assert.match(css, /\.tq-compose-box > span \{[^}]*flex: 0 0 34px/);
});
