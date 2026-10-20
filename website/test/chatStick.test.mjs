// The 2026-10-19 UI walk: after a reload the chat stopped short of its end - 285px on the demo, the answer the owner had just asked
// for under the fold. The thread is drawn, then the task view grows it by more than the observer's "within 240px of the end", so
// nothing followed it down. A thread put at its end stays STUCK there as it grows, until the owner scrolls it themselves.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("toEnd marks the thread stuck at its end, and growth keeps it there however much it grows", () => {
  const at = src.indexOf("const toEnd = (el) =>");
  assert.match(src.slice(at, at + 500), /stuck\.current = !top;/, "at the end = stuck; a task view held by its top is not");
  assert.match(src, /if \(!holdBottom\.current && \(stuck\.current \|\| el\.scrollHeight - el\.scrollTop - el\.clientHeight < 240\)/);
});

test("the owner's scroll lets go of the end, and scrolling back down takes it again", () => {
  assert.match(src, /const own = \(\) => \{ pin\.current = false; stuck\.current = false;/);
  assert.match(src, /const atEnd = \(\) => \{ if \(el\.scrollHeight - el\.scrollTop - el\.clientHeight < 4\) stuck\.current = true; \};/);
  assert.match(src, /el\.addEventListener\("scroll", atEnd/);
});

// ...and the pin on the card lets go for the KEYBOARD too: a card filled in by Tab and Enter snapped back to its top on Save (588px
// up on the Slack card), because only a wheel or a finger released it. Focus the app moves itself must not count.
test("a key pressed in the thread, focus Tabbed into it, or a press on its scrollbar lets go of the pin", () => {
  assert.match(src, /const key = \(\) => \{ keyAt = Date\.now\(\); \}, typed = \(\) => \{ pin\.current = false; \};/);
  assert.match(src, /const tabbed = \(\) => \{ if \(Date\.now\(\) - keyAt < 800\) pin\.current = false; \};/, "only focus a key just moved");
  assert.match(src, /const bar = \(e\) => \{ if \(e\.target === el\) own\(\); \};/);
  assert.match(src, /document\.addEventListener\("keydown", key, true\); el\.addEventListener\("keydown", typed\); el\.addEventListener\("focusin", tabbed\);/);
  assert.match(src, /document\.removeEventListener\("keydown", key, true\);/, "and the listeners go with the effect");
});
