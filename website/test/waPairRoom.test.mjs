import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

// ROOM HELD FOR A LATE PANEL (the 2026-10-19 UI walk, G8): the WhatsApp card drew nothing for its pairing box until the bridge's status
// answered, then the box pushed the card's tabs ~245px down under the owner's eyes (measured 2026-10-20, status held 800 ms). The box
// stands from the first frame at about the height it will have; the tabs under it then move a few pixels, not a screenful.
test("the pairing box holds its room while the bridge's status is read", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/ConnectorsView.jsx", import.meta.url)), "utf8");
  const wa = src.slice(src.indexOf("const WaPair = "), src.indexOf("const WaChats = "));
  assert.doesNotMatch(wa, /if \(!st\) return null;/, "nothing drawn until the answer is the jump");
  assert.match(wa, /if \(!st\) return \(\s*<Box data-tq-wa-pair="reading" sx=\{\{.*minHeight: 230/);
  assert.match(wa, /Pair with your phone<\/Typography>[\s\S]*Reading the pairing status…/);
});
