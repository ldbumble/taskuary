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

test("automatic chooses a browser then Windows without a voice card", () => {
  assert.equal(micRoute({ builtin: {} }, true, "auto"), "browser");
  assert.equal(micRoute({ builtin: {} }, false, "auto"), "windows");
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
