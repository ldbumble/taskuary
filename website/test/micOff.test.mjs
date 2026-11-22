import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { place } from "../src/words.js";

// No voice AI, no live mic (the owner, 2026-10-15: "if there is no voice provider the mic icon in the bar on bottom should be crossed
// out with popup to configure voice ai before it will activate") - unless a voice is found, and then no press to turn it on (the owner,
// 2026-11-01: "it should be built in without having to turn it on if it finds it").
const ui = readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");
const mic = ui.slice(ui.indexOf("export const MicButton"), ui.indexOf("export const ChoiceRow"));


test("the popup opens the voice section of Connections, and that link lands there", () => {
  assert.match(mic, /"Set up voice AI"\}<\/Button>/);
  assert.match(mic, /openAppLink\(place\("voice"\)\.href\)/);     // the place's link, from words.json
  const r = canvasRequestFromHash(place("voice").href);
  assert.deepEqual([r.area, r.state], ["connections", { section: "AI — voice", open: null }]);
});


// Silence is not sent to be made up (the owner, 2026-11-09): the recording measures itself and the server gates a silent clip
test("a recording sends its own loudness and length, and a meter that never ran sends no level", async () => {
  assert.match(mic, /const chunks = \[\], meter = levelMeter\(stream\)/);
  assert.match(mic, /headers: \{ "Content-Type": blob\.type \|\| "audio\/webm", \.\.\.measured \}/);
  const { levelMeter } = await import("data:text/javascript," + encodeURIComponent(ui.slice(ui.indexOf("export const levelMeter"), ui.indexOf("// One mic."))));
  const fake = (state, v) => class { constructor() { this.state = state; }
    createAnalyser() { return { fftSize: 0, getFloatTimeDomainData: (b) => b.fill(v) }; }
    createMediaStreamSource() { return { connect() {} }; } close() {} };
  const run = async (AC) => { const m = levelMeter({}, AC); await new Promise((r) => setTimeout(r, 80)); return m.stop(); };
  const loud = await run(fake("running", 0.25));
  assert.equal(loud["X-Voice-Level"], "0.2500"); assert.ok(+loud["X-Voice-Seconds"] > 0);
  assert.equal((await run(fake("suspended", 0.25)))["X-Voice-Level"], undefined, "a suspended context never calls speech silence");
  assert.equal((await run(undefined))["X-Voice-Level"], undefined, "no AudioContext, no level");
});
