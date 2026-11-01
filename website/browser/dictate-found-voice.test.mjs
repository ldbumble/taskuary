import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A VOICE THAT IS FOUND IS ON, WITH NO PRESS TO TURN IT ON (the owner, 2026-11-01: "local voice using microsoft edge is not working. it
   should be built in without having to turn it on if it finds it"). With no card and no browser recogniser (the desktop window: WebView2
   has the class but no service, so browserRecogniser is null there - here it is simply taken away), the computer's own recogniser the
   server reports (voice.py builtin) makes the mic live: a press records at once, the clip goes up as 16 kHz WAV, and its words land in
   the box. With nothing found the mic is crossed out and asks, and the ask offers no "use this browser's own" step. The server's answers
   are stood in for, so the test reads the same on a box without Windows speech. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LABEL = "Windows speech recognition (on this computer)";

test("with no card the computer's own voice makes the mic live at once, and the clip goes up as WAV", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  let builtin = { engine: "windows_speech", label: LABEL };
  const posted = [];
  page.off("request", page.fixtureRequestGuard);     // the voice routes are answered here; everything else still goes through the guard
  page.on("request", async (q) => {
    const u = q.url();
    if (u.includes("/api/voice/status")) return q.respond({ status: 200, contentType: "application/json",
      body: JSON.stringify({ ready: false, provider: null, label: null, vocabulary: [], builtin }) });
    if (u.includes("/api/voice/transcribe")) {
      const raw = q.postData() ?? (await q.fetchPostData?.()) ?? "";
      const body = raw.startsWith("RIFF") ? raw : Buffer.from(raw, "base64").toString("latin1");   // a binary body comes base64
      posted.push({ type: q.headers()["content-type"], head: body.slice(0, 4), wave: body.slice(8, 12), len: body.length });
      return q.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ text: "reply saying Thursday works", provider: "windows_speech" }) });
    }
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
  assert.equal(await page.$eval(mic, (e) => e.dataset.tqMic), "on", "the mic is live, not crossed out");
  await page.click('.tq-compose-box button[aria-label="dictate"]');
  await page.waitForSelector('.tq-compose-box button[aria-label="stop recording"]', { timeout: 5000 });
  assert.equal(await page.$("[data-tq-voice-ask]"), null, "no offer to press first");
  await sleep(1200);
  await page.click('.tq-compose-box button[aria-label="stop recording"]');
  await page.waitForFunction(() => document.querySelector(".tq-compose-box textarea")?.value.includes("reply saying Thursday works"), { timeout: 15000 });
  assert.equal(posted.length, 1);
  assert.equal(posted[0].type, "audio/wav");
  assert.equal(posted[0].head, "RIFF"); assert.equal(posted[0].wave, "WAVE");
  assert.ok(posted[0].len > 16000, `about a second of 16 kHz audio (${posted[0].len} bytes)`);

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
