// SEND AND CLOSE IS ONE STYLE (the product audit, 2026-11-08): filled on one reply card, outlined on the next - it stepped back for any lit
// move on its card, a Redraft the card did not draw included. It steps back only for a lit move drawn beside it
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("Send and close steps back only for a lit Send, or a lit Redraft the card draws", () => {
  const src = readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");
  assert.match(src, /const redraftDrawn = canRedraft && !r\.Stale && !delivery\.frozen && !warnTop;/);
  assert.match(src, /const closeVariant = lit === no\("approve"\) \|\| \(lit === no\("redraft"\) && redraftDrawn\) \? "outlined" : "contained";/);
  assert.doesNotMatch(src, /lit\.startsWith\(`\$\{r\.ReviewId\}:`\) && lit !== no\("send_close"\)/);
});
