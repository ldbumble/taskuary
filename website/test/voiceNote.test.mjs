import test from "node:test";
import assert from "node:assert/strict";
import { isVoicePlaceholder, voiceNoteBody } from "../src/voiceNote.js";

const placeholder = "🎤 Voice note (82s) from WhatsApp - not transcribed: no connector";

test("a voice note is recognized from the timeline Preview used by the review panel", () => {
  const row = { MessageId: 12, Preview: placeholder };
  assert.equal(isVoicePlaceholder(voiceNoteBody(row)), true);
});

test("the loaded full message takes precedence over a stale timeline preview", () => {
  const row = { Preview: placeholder };
  const message = { BodyText: "Send her the revised agreement\n\n(voice note from whatsapp, transcribed by Groq)" };
  assert.equal(voiceNoteBody(row, message), message.BodyText);
  assert.equal(isVoicePlaceholder(voiceNoteBody(row, message)), false);
});
