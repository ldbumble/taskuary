import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

// No voice AI, no live mic (the owner, 2026-10-15: "if there is no voice provider the mic icon in the bar on bottom should be crossed
// out with popup to configure voice ai before it will activate").
const ui = readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");
const mic = ui.slice(ui.indexOf("export const MicButton"), ui.indexOf("export const ChoiceRow"));

test("with no voice AI the mic is crossed out, and its press asks instead of recording", () => {
  assert.match(mic, /const off = !!\(voice && !voice\.ready && !viaBrowser\)/);
  assert.match(mic, /off \? <MicOffIcon/);
  assert.match(mic, /const press = \(e\) => \{ if \(!off\) return start\(\); setAsk\(e\.currentTarget\)/);
  assert.match(mic, /viaBrowser = !!\(voice && !voice\.ready && SR && byBrowser\)/, "the browser's recogniser only once it was chosen");
});

test("the popup opens the voice section of Connections, and that link lands there", () => {
  assert.match(mic, /Set up voice AI<\/Button>/);
  assert.match(mic, /openAppLink\(`#connections=\$\{encodeURIComponent\("AI — voice"\)\}`\)/);
  const r = canvasRequestFromHash(`#connections=${encodeURIComponent("AI — voice")}`);
  assert.deepEqual([r.area, r.state], ["connections", { section: "AI — voice", open: null }]);
});
