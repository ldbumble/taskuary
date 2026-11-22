// A video or a sound the agent made PLAYS where it is opened (Gabi, 2026-11-08: "tried to open the mp4 instead of downloading it. No go" -
// the dialog drew its raw bytes as a page), and a file with no preview says so instead of drawing its bytes.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { outputRow } from "../src/taskOutputs.js";

const src = readFileSync(new URL("../src/PublishedPages.jsx", import.meta.url), "utf8");

test("an mp4 named in the words is a video row, a .wav a sound, a zip no preview", () => {
  const v = outputRow(1360, "taskuary-opening-test.mp4"), a = outputRow(1360, "voice.wav"), z = outputRow(1360, "bundle.zip");
  assert.deepEqual([v.preview, v.content_type], ["video", "video/mp4"]);
  assert.deepEqual([a.preview, a.content_type], ["audio", "audio/wav"]);
  assert.equal(z.preview, null);
});
