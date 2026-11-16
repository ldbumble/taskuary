import test from "node:test";
import assert from "node:assert/strict";
import { micRoute, voiceChoice, chooseVoice } from "../src/voiceChoice.js";

test("an explicit built-in choice never routes audio to an AI card", () => {
  const voice = { ready: true, builtin: { live: true } };
  assert.equal(micRoute(voice, true, "windows"), "windows");
  assert.equal(micRoute(voice, true, "browser"), "browser");
  assert.equal(micRoute(voice, true, "auto"), "connector");
  assert.equal(micRoute({ ready: true }, true, "windows"), "off");
  assert.equal(micRoute(voice, false, "browser"), "off");
});

// Automatic (the owner, 2026-11-16: "Use the Windows voice rec"): a voice card, else Windows voice typing on this computer, else the tab's own
test("automatic chooses a voice card, then Windows voice typing, then the browser's own", () => {
  assert.equal(micRoute({ ready: true, builtin: {} }, true, "auto"), "connector");
  assert.equal(micRoute({ builtin: {} }, true, "auto"), "windows", "Windows voice typing before the tab's recogniser");
  assert.equal(micRoute({}, true, "auto"), "browser", "a Mac or Linux tab");
  assert.equal(micRoute({}, false, "auto"), "off");
});

test("choice persists and notifies already mounted microphone buttons", () => {
  const values = new Map(); let changed;
  globalThis.localStorage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
  globalThis.window = { dispatchEvent: (event) => { changed = event.type; } };
  try {
    assert.equal(voiceChoice(), "auto");
    chooseVoice("windows");
    assert.equal(voiceChoice(), "windows");
    assert.equal(changed, "taskuary-voice-choice");
    chooseVoice("unknown");
    assert.equal(voiceChoice(), "auto");
  } finally { delete globalThis.localStorage; delete globalThis.window; }
});
