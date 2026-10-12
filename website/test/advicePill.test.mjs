// The Advisor's line in the prompt box (spec 2026-10-12, build step 3): ghost text while the box is empty, and a pill
// where the send arrow sits that presses the card's own button through the same chip path. These tests read the
// source, the way the composer's other tests do (assistantEmoji, canvasItem), so a regression in the JSX is caught
// without a browser.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");

test("the Advisor's line is the ghost text while the box is empty, and the pill sits where the arrow does", () => {
  assert.match(src, /const \[advice, setAdvice\] = useState\(null\)/);
  assert.match(src, /api\.get\("\/api\/advice", \{ params: \{ key/);
  assert.match(src, /onLive\("advice"/);
  assert.match(src, /advice\?\.line && !text\.trim\(\)/);                       // ghost text only while empty
  assert.match(src, /Tell me what to do with it, or press…/);
  assert.match(src, /className="tq-pill"/);
  assert.match(src, /runChip\(\{ verb: advice\.verb, label: advice\.label \}\)/);   // the card's own button, same path
  assert.match(css, /\.tq-pill \{/);
});

test("the pill never shows beside a typed line or a picture", () => {
  assert.match(src, /advice\?\.verb && !text\.trim\(\) && !pics\.imgs\.length\s*\?\s*\(\s*<button type="button" className="tq-pill"/);
});
