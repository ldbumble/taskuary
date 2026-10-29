import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { browserRecogniser, dictate, dictationError } from "../src/dictation.js";

/* The browser's own voice keeps listening until the owner stops it (the owner, 2026-10-28: "hit the mic and it just turns right off"). */
const made = [];
class FakeSR {
  constructor() { made.push(this); this.started = 0; }
  start() { this.started++; }
  stop() { this.onend?.(); }
  abort() { this.aborted = true; this.onend?.(); }
  set phrases(v) { this._p = v; }
  get phrases() { return this._p; }
}
const res = (...xs) => ({ results: xs.map(([t, fin]) => Object.assign([{ transcript: t }], { isFinal: fin })) });
const run = (o = {}) => {
  made.length = 0;
  const got = { finals: [], interim: [], ends: [] };
  let t = 0;
  const d = dictate({ SR: FakeSR, onFinal: (x) => got.finals.push(x), onInterim: (x) => got.interim.push(x), onEnd: (l) => got.ends.push(l),
                      now: () => (t += o.step ?? 5000), ...o });
  return { d, got, sr: () => made[made.length - 1] };
};

test("dictation listens continuously with interim results", () => {
  const { sr } = run();
  assert.equal(sr().continuous, true);
  assert.equal(sr().interimResults, true);
  assert.equal(sr().started, 1);
});

test("a settled phrase lands once, what is still heard shows, and the next result does not repeat it", () => {
  const { sr, got } = run();
  sr().onresult(res(["reply saying", false]));
  assert.deepEqual(got.interim.at(-1), "reply saying");
  sr().onresult(res(["reply saying Thursday", true], ["works", false]));
  sr().onresult(res(["reply saying Thursday", true], ["works for me", true]));
  assert.deepEqual(got.finals, ["reply saying Thursday", "works for me"]);
  assert.equal(got.interim.at(-1), "");
});

test("Chrome's own end while the mic is on starts listening again", () => {
  const { sr, got, d } = run();
  const first = sr();
  first.onerror({ error: "no-speech" }); first.onend();
  assert.notEqual(sr(), first, "a new session");
  assert.equal(sr().started, 1);
  assert.deepEqual(got.ends, [], "not over");
  assert.equal(d.on, true);
  sr().onresult(res(["still here", true]));
  assert.deepEqual(got.finals, ["still here"]);
});

test("a refused vocabulary is dropped and the mic goes on without it", () => {
  const { sr, got } = run({ phrases: () => ["Northwind"] });
  assert.deepEqual(sr().phrases, ["Northwind"]);
  const first = sr();
  first.onerror({ error: "phrases-not-supported" }); first.onend();
  assert.notEqual(sr(), first);
  assert.equal(sr().phrases, undefined, "no phrases the second time");
  assert.deepEqual(got.ends, []);
});

test("a blocked microphone ends dictation with one plain line", () => {
  const { sr, got, d } = run();
  sr().onerror({ error: "not-allowed" }); sr().onend();
  assert.deepEqual(got.ends, [dictationError("not-allowed")]);
  assert.match(got.ends[0], /blocked the microphone.*address bar/);
  assert.equal(d.on, false);
  assert.equal(made.length, 1, "not started again");
});

test("no network says browser voice needs one", () => {
  const { sr, got } = run();
  sr().onerror({ error: "network" }); sr().onend();
  assert.match(got.ends[0], /needs an internet connection/);
});

test("a browser that ends every session at once gives up with a line instead of spinning", () => {
  const { sr, got } = run({ step: 10 });
  for (let i = 0; i < 5 && !got.ends.length; i++) sr().onend();
  assert.deepEqual(got.ends, [dictationError("no-speech")]);
  assert.ok(made.length <= 3);
});

test("the owner's stop ends it with no line, and the last words still land", () => {
  const { sr, got, d } = run();
  const s = sr();
  s.stop = function () { this.onresult(res(["last words", true])); this.onend(); };
  d.stop();
  assert.deepEqual(got.finals, ["last words"]);
  assert.deepEqual(got.ends, [null]);
  assert.equal(made.length, 1, "a stop is not restarted");
});

test("a send cancels: nothing more lands", () => {
  const { sr, got, d } = run();
  const s = sr();
  d.cancel();
  assert.ok(s.aborted);
  s.onresult?.(res(["late", true]));
  assert.deepEqual(got.finals, []);
  assert.deepEqual(got.ends, [null]);
});

test("every error a browser names has a plain line", () => {
  for (const c of ["not-allowed", "service-not-allowed", "network", "audio-capture", "language-not-supported", "no-speech", "aborted"])
    assert.ok(dictationError(c) && !/\(/.test(dictationError(c)), c);
  assert.match(dictationError("weird"), /weird/);
});

test("the mic shows its error beside it and the chat box shows what is being heard and cancels on a send", () => {
  const ui = readFileSync(fileURLToPath(new URL("../src/ui.jsx", import.meta.url)), "utf8");
  const av = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(ui, /data-tq-mic-err/);
  assert.match(ui, /open=\{!ask && \(!!err/);
  assert.match(av, /onInterim=\{setHeard\}/);
  assert.match(av, /micRef\.current\?\.cancel\(\)/);
});

test("the Taskuary window has no browser voice: WebView2's recogniser has no service behind it", () => {
  assert.equal(browserRecogniser({ webkitSpeechRecognition: FakeSR, pywebview: {} }), null);
  assert.equal(browserRecogniser({ webkitSpeechRecognition: FakeSR }), FakeSR);
  assert.equal(browserRecogniser({}), null);
});
