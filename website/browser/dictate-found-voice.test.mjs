import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NOTHING THAT DOES NOT WORK, AND A QUESTION INSTEAD (TQ-1283, the owner, 2026-11-03: "You can't use something that doesn't work ... ask
   them, trigger the question if you want to turn that on"). With no card and no browser recogniser (the desktop window: WebView2 has the
   class but no service, so browserRecogniser is null there - here it is simply taken away), Windows voice typing with its speech setting
   off makes the mic ASK: "Turn it on" switches the setting on (POST /api/voice/speech-on) and the mic starts listening at once. No clip
   ever goes to the 2006 offline dictation - it is gone. With nothing found the mic is crossed out and asks for a voice AI. The server's
   answers are stood in for, so the test reads the same on a box without Windows speech. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LIVE = { engine: "windows_voice_typing", label: "Windows voice typing (on this computer)", live: true };
const ASK = "Windows' speech recognition is off on this computer. Turn it on so the mic can hear you?";

test("voice typing with its setting off asks, and a yes turns it on and listens", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  let builtin = { ...LIVE, ask: ASK };
  const hit = [];
  page.off("request", page.fixtureRequestGuard);     // the voice routes are answered here; everything else still goes through the guard
  const ok = (q, body) => q.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  page.on("request", async (q) => {
    const u = q.url(), m = q.method();
    if (u.includes("/api/voice/status")) return ok(q, { ready: false, provider: null, label: null, vocabulary: [], builtin });
    if (u.includes("/api/voice/speech-on")) { hit.push("speech-on"); builtin = LIVE; return ok(q, { ready: false, builtin }); }
    if (u.includes("/api/voice/transcribe")) { hit.push("transcribe"); return ok(q, { text: "should never be asked" }); }
    if (/\/api\/voice\/listen\/[^/]+\/stop/.test(u)) { hit.push("stop"); return ok(q, { said: [], done: true, error: "" }); }
    if (/\/api\/voice\/listen\/[^/?]+/.test(u)) return ok(q, { said: hit.includes("said") ? [] : (hit.push("said"), ["reply saying Thursday works"]), done: false });
    if (u.includes("/api/voice/listen") && m === "POST") { hit.push("listen"); return ok(q, { id: "abc123" }); }
    return page.fixtureRequestGuard(q);
  });
  await page.evaluateOnNewDocument(() => {
    delete window.SpeechRecognition; delete window.webkitSpeechRecognition;
    window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;
    // a microphone that hums: a real MediaRecorder records it, so the WAV the page makes comes from a real Opus clip
    navigator.mediaDevices.getUserMedia = async () => {
      const ac = new AudioContext(); await ac.resume();
      const o = ac.createOscillator(), d = ac.createMediaStreamDestination(); o.connect(d); o.start();
      return d.stream;
    };
  });
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(1500);

  await page.click(".tq-compose-box textarea");
  const mic = '.tq-compose-box button[data-tq-mic]';
  await page.waitForSelector(`${mic}:not([disabled])`, { timeout: 10000 });
  assert.equal(await page.$eval(mic, (e) => e.dataset.tqMic), "on", "the mic is not crossed out - it can be made to work");
  await page.click('.tq-compose-box button[aria-label="dictate"]');
  await page.waitForSelector("[data-tq-speech-ask]", { visible: true, timeout: 5000 });
  assert.match(await page.$eval("[data-tq-speech-ask]", (e) => e.textContent), /Turn it on so the mic can hear you/);
  assert.deepEqual(hit, [], "nothing listens or records before the yes");
  await page.click("[data-tq-speech-on]");
  await page.waitForFunction(() => document.querySelector(".tq-compose-box textarea")?.value.includes("reply saying Thursday works"), { timeout: 15000 });
  await page.click('.tq-compose-box button[aria-label="stop recording"]');
  await sleep(500);
  assert.deepEqual(hit.filter((x) => x !== "said"), ["speech-on", "listen", "stop"], "the yes turns it on, then voice typing listens");
  assert.ok(!hit.includes("transcribe"), "no clip goes to anything worse");

  // nothing found: crossed out, and the ask has one road - set up a voice AI
  builtin = null;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(1500);
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector(`${mic}[data-tq-mic="off"]:not([disabled])`, { timeout: 10000 });
  await page.click(mic);
  await page.waitForSelector("[data-tq-voice-ask]", { visible: true, timeout: 5000 });
  const asked = await page.$eval("[data-tq-voice-ask]", (e) => [...e.querySelectorAll("button")].map((b) => b.textContent));
  assert.deepEqual(asked, ["Set up voice AI"]);
  assert.deepEqual(errors, []);
});
