import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const feed = readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");

// The 2026-10-11 walk: at 1440px a Timeline row read "Erin Bl... [task · open] [reply]" - the subject had flex 1
// (basis 0) so it got only what the sender and the chips left, which in the 217px card was nothing. The pixels
// are proved by a puppeteer probe; this pins the rule so the row cannot quietly go back to it.
test("a Timeline row's subject keeps 72px, the sender gives way first, the chips wrap as one block", () => {
  const who = feed.slice(feed.indexOf("const WhoWhat"), feed.indexOf("const WhoWhat") + 700);
  assert.match(who, /gridTemplateColumns: `fit-content\(\$\{whoMax\}px\) minmax\(72px, 1fr\)`/, "the subject track never drops below 72px");
  assert.match(who, /minWidth: 28/, "the sender keeps a few letters");
  assert.match(feed, /const ROW_LINE = \{[^}]*flexWrap: "wrap"/, "the chips drop to a second line instead of clipping");
  assert.match(feed, /const ROW_CHIPS = \{[^}]*flexShrink: 0/, "the chips never shrink");
});

test("both row kinds - a message and a folded conversation - use the one first line", () => {
  assert.equal((feed.match(/<WhoWhat /g) || []).length, 2);
  assert.equal((feed.match(/<Box sx=\{ROW_CHIPS\}>/g) || []).length, 2);
  assert.doesNotMatch(feed, /letterSpacing: "-.1px", flex: 1, minWidth: 0 \}\}>\s*\{(subjectOf|cleanText)/, "no subject on basis 0");
});
