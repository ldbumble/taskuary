/* A MIC CLIP AS WAV, for the computer's own recogniser (voice.py, builtin): Windows' System.Speech reads 16-bit PCM WAV only, and the
   browser records Opus in WebM. The clip is decoded and mixed down to 16 kHz mono here, so the server needs no audio library. */
export const WAV_RATE = 16000;

// samples in [-1, 1] -> a 44-byte RIFF header and 16-bit little-endian PCM, mono
export function encodeWav(samples, rate = WAV_RATE) {
  const n = samples.length, b = new ArrayBuffer(44 + n * 2), v = new DataView(b);
  const put = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  put(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); put(8, "WAVE"); put(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); put(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) { const x = Math.max(-1, Math.min(1, samples[i])); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true); }
  return b;
}

// a recorded Blob -> a WAV Blob at 16 kHz mono (an OfflineAudioContext of one channel mixes down and resamples in one render)
export async function toWav(blob, w = window) {
  const Ctx = w.AudioContext || w.webkitAudioContext, ctx = new Ctx();
  try {
    const src = await ctx.decodeAudioData(await blob.arrayBuffer());
    const off = new w.OfflineAudioContext(1, Math.max(1, Math.ceil(src.duration * WAV_RATE)), WAV_RATE);
    const node = off.createBufferSource(); node.buffer = src; node.connect(off.destination); node.start();
    return new Blob([encodeWav((await off.startRendering()).getChannelData(0))], { type: "audio/wav" });
  } finally { ctx.close?.(); }
}
