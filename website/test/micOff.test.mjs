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

test("with no voice AI and no voice found the mic is crossed out, and its press asks instead of recording", () => {
  assert.match(mic, /const off = !!\(voice && !voice\.ready && !viaBrowser && !viaBuiltin\)/);
  assert.match(mic, /off \? <MicOffIcon/);
  assert.match(mic, /const press = \(e\) => \{ if \(!off\) return start\(\); setAsk\(e\.currentTarget\)/);
});

test("a browser recogniser or the computer's own is used at once, with no opt-in to press", () => {
  assert.match(mic, /viaBrowser = !!\(voice && !voice\.ready && SR && !\(srDown && builtin\)\)/, "the browser's recogniser whenever there is one");
  assert.match(mic, /viaBuiltin = !!\(builtin && !viaBrowser\)/, "else the computer's own, as the server reports it");
  assert.doesNotMatch(ui, /tq-voice-browser|useBrowser|this browser's own \(free\)/, "the opt-in step is gone");
  assert.match(mic, /viaBuiltin \? await toWav\(clip\) : clip/, "the computer's own hears WAV");
});

test("a tab whose speech service will not answer hands over to the computer's own", () => {
  assert.match(mic, /builtin && \[dictationError\("network"\), dictationError\("service-not-allowed"\)\]\.includes\(line\)/);
  assert.match(mic, /setSrDown\(true\)/);
});

test("the popup opens the voice section of Connections, and that link lands there", () => {
  assert.match(mic, /Set up voice AI<\/Button>/);
  assert.match(mic, /openAppLink\(place\("voice"\)\.href\)/);     // the place's link, from words.json
  const r = canvasRequestFromHash(place("voice").href);
  assert.deepEqual([r.area, r.state], ["connections", { section: "AI — voice", open: null }]);
});

// Windows voice typing first (the owner, 2026-11-02: "do the changes to use desktop if the machine has it"): it hears the microphone
// itself, so the mic holds a session on the server instead of recording a clip; a Mac's crossed-out mic points at its Dictation key.
test("Windows voice typing is a session the server holds, from one press to the next", () => {
  assert.match(mic, /const viaLive = !!\(viaBuiltin && builtin\.live\)/);
  assert.match(mic, /if \(viaLive\) return listen\(\);/);
  assert.match(mic, /api\.post\("\/api\/voice\/listen"\)/);
  assert.match(mic, /api\.get\(`\/api\/voice\/listen\/\$\{id\}`, \{ params: \{ since: seen \} \}\)/, "each settled phrase, once");
  assert.match(mic, /api\.post\(`\/api\/voice\/listen\/\$\{id\}\/stop`/, "the stop lets a phrase still being said land");
  assert.match(mic, /if \(!viaBrowser && !viaLive\) setRec\(null\)/);
});

test("a Mac with no voice is pointed at its own Dictation key", () => {
  assert.match(mic, /\/Mac\/\.test\(navigator\.platform/);
  assert.match(mic, /Dictation key/);
});
