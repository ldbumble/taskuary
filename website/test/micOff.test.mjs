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
  assert.match(mic, /const off = !!\(voice && route !== "connector" && !viaBrowser && !viaBuiltin\)/);
  assert.match(mic, /off \? <MicOffIcon/);
  assert.match(mic, /const press = \(e\) => \{ setErr\(""\); if \(!off && !\(viaBuiltin && speechAsk\)\) return start\(\); setAsk\(e\.currentTarget\)/);
});

test("a browser recogniser or the computer's own is used at once, with no opt-in to press", () => {
  // the order lives in micRoute (voiceChoice.js, its own tests): Automatic = a voice card, else the browser's, else the computer's own
  assert.match(mic, /route = micRoute\(voice, SR, voice\?\.choice\)/);
  assert.match(mic, /viaBrowser = !!\(voice && route === "browser" && !\(srDown && builtin && voice\.choice === "auto"\)\)/, "the browser's recogniser whenever there is one");
  assert.match(mic, /viaBuiltin = !!\(builtin && !viaBrowser && \(route === "windows" \|\| \(route === "browser" && voice\?\.choice === "auto"\)\)\)/, "else the computer's own, as the server reports it");
  assert.doesNotMatch(ui, /tq-voice-browser|useBrowser|this browser's own \(free\)/, "the opt-in step is gone");
  assert.doesNotMatch(mic, /toWav/, "no WAV clip for the 2006 offline dictation: it is gone (TQ-1283)");
});

test("a tab whose speech service will not answer hands over to the computer's own", () => {
  assert.match(mic, /builtin && voice\.choice === "auto" && \[dictationError\("network"\), dictationError\("service-not-allowed"\)\]\.includes\(line\)/);
  assert.match(mic, /setSrDown\(true\)/);
});

test("the popup opens the voice section of Connections, and that link lands there", () => {
  assert.match(mic, /"Set up voice AI"\}<\/Button>/);
  assert.match(mic, /openAppLink\(place\("voice"\)\.href\)/);     // the place's link, from words.json
  const r = canvasRequestFromHash(place("voice").href);
  assert.deepEqual([r.area, r.state], ["connections", { section: "AI — voice", open: null }]);
});

// Windows voice typing first (the owner, 2026-11-02: "do the changes to use desktop if the machine has it"): it hears the microphone
// itself, so the mic holds a session on the server instead of recording a clip; a Mac's crossed-out mic points at its Dictation key.
test("Windows voice typing is a session the server holds, from one press to the next", () => {
  assert.match(mic, /const viaLive = !!\(viaBuiltin && builtin\.live && !speechAsk\)/);
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

// NOTHING THAT DOES NOT WORK (TQ-1283, the owner, 2026-11-03: "trigger the question if you want to turn that on"): voice typing with its
// speech setting off ASKS - a yes turns it on and starts listening; nothing falls back to worse dictation.
test("voice typing with its setting off asks to turn it on, and a yes turns it on and listens", () => {
  assert.match(mic, /const speechAsk = !!builtin\?\.ask/);
  assert.match(mic, /api\.post\("\/api\/voice\/speech-on"\); setAsk\(null\); voice\.recheck\(\); listen\(\);/);
  assert.match(mic, /Turn on speech recognition\?/);
  assert.match(mic, /data-tq-speech-on="" onClick=\{turnOn\}/);
  assert.match(mic, /if \(viaBuiltin\) return;/, "nothing records a clip for the computer's own any more");
});

// A MIC THAT HEARD NOTHING SAYS WHY (the owner, 2026-11-09: "you start it and end it and no words show up???"): every road that ends with
// no words - an empty transcript from the voice AI, a Windows voice typing session that heard nothing or whose stop failed - flashes a reason.
test("a failed or empty transcription shows a reason, never silence", () => {
  assert.match(ui, /export const heardNothing = \(who\) => `\$\{who\} heard no words - /);
  assert.match(mic, /if \(data\.text\) live\.current\.onText\?\.\(data\.text\); else flash\(heardNothing\(/, "an empty transcript names who heard nothing");
  assert.doesNotMatch(mic, /flash\("nothing audible"\)/);
  assert.match(mic, /catch \(e\) \{ flash\(e\?\.response\?\.data\?\.detail \|\| "transcription failed"\); \}/, "a failed one says the server's reason");
  assert.match(mic, /heard \|\|= said\.length > 0/);
  assert.match(mic, /if \(error \|\| !heard\) flash\(error \|\| heardNothing\("Windows voice typing"\)\)/, "a voice typing session that heard nothing says so");
  assert.doesNotMatch(mic, /catch \{ end\(""\); \}/, "a failed stop is not a silent end");
});

test("a refused microphone in the Taskuary window points at Windows' setting, not an address bar it does not have", () => {
  assert.match(mic, /catch \(e\) \{ flash\(micRefused\(e\?\.name\)\); \}/);
  const fn = ui.slice(ui.indexOf("export const micRefused"), ui.indexOf("// One mic. Press to record"));
  assert.match(fn, /inWindow \? "Windows kept the microphone from this window - turn on \\"Let desktop apps access your microphone\\"/);
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

test("a mic failure stays said beside the mic with its fix as a button, never only a fading tooltip", () => {
  assert.doesNotMatch(mic, /setTimeout\(\(\) => setErr\(""\)/, "no 8 s fade");
  assert.match(mic, /<Popper open=\{!!err && !ask/);
  assert.match(mic, /data-tq-mic-err="" role="alert"/);
  assert.match(mic, /fix\.settings \? openSettings\(fix\.settings\)/);
  assert.match(mic, /api\.post\("\/api\/voice\/open-settings", null, \{ params: \{ which \} \}\)/);
  assert.match(mic, /window\.addEventListener\("focus", back\)/, "back from Windows' settings, the mic checks again");
  assert.match(mic, /data-tq-speech-settings=""/, "the speech ask also opens Windows' own page");
});
