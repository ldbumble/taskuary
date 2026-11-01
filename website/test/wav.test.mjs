import test from "node:test";
import assert from "node:assert/strict";
import { encodeWav, WAV_RATE } from "../src/wav.js";

// the computer's own recogniser (Windows' System.Speech) reads 16-bit PCM WAV only: the header must say exactly what the bytes are
test("a clip encodes as 16 kHz mono 16-bit PCM WAV, clipped to range", () => {
  const b = encodeWav(new Float32Array([0, 1, -1, 2, -0.5]));
  const v = new DataView(b), s = (o, n) => String.fromCharCode(...new Uint8Array(b, o, n));
  assert.equal(b.byteLength, 44 + 10);
  assert.deepEqual([s(0, 4), s(8, 4), s(12, 4), s(36, 4)], ["RIFF", "WAVE", "fmt ", "data"]);
  assert.equal(v.getUint32(4, true), 36 + 10);
  assert.deepEqual([v.getUint16(20, true), v.getUint16(22, true), v.getUint32(24, true), v.getUint32(28, true), v.getUint16(32, true), v.getUint16(34, true)],
                   [1, 1, WAV_RATE, WAV_RATE * 2, 2, 16]);
  assert.equal(v.getUint32(40, true), 10);
  assert.deepEqual([0, 1, 2, 3, 4].map((i) => v.getInt16(44 + i * 2, true)), [0, 32767, -32768, 32767, -16384]);
});
