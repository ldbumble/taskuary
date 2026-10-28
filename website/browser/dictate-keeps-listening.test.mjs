import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE BROWSER'S VOICE KEEPS LISTENING (the owner, 2026-10-28: "clicked 'use your browser voice', then hit the mic and it just turns right
   off"). A stand-in recogniser the test drives: the mic starts on the press, what is still being heard shows in the box, Chrome's own end
   while the mic is on starts it again, the second press stops it, and a blocked microphone says so beside the mic. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("browser dictation survives Chrome's own end, shows interim words, stops on the second press, and says why it stopped", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.evaluateOnNewDocument(() => {
    try { localStorage.setItem("tq-voice-browser", "1"); } catch { /* the mic falls back to asking */ }
    window.__recs = [];
    window.SpeechRecognition = class {
      constructor() { window.__recs.push(this); this.live = false; }
      start() { this.live = true; }
      stop() { this.live = false; this.onend?.(); }
      abort() { this.live = false; this.onend?.(); }
    };
    const r = (...xs) => ({ results: xs.map(([tx, fin]) => Object.assign([{ transcript: tx }], { isFinal: fin })) });
    window.__last = () => window.__recs[window.__recs.length - 1];
    window.__say = (...xs) => window.__last().onresult?.(r(...xs));
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
  const box = () => page.evaluate(() => document.querySelector(".tq-compose-box textarea")?.value);

  await page.click(".tq-compose-box textarea");
  await page.click('.tq-compose-box button[aria-label="dictate"]');
  await page.waitForFunction(() => window.__recs.length === 1 && window.__recs[0].live, { timeout: 5000 });

  await page.evaluate(() => window.__say(["reply saying", false]));
  await page.waitForFunction(() => document.querySelector(".tq-compose-box textarea")?.value === "reply saying", { timeout: 5000 });

  // Chrome ends the session by itself (a pause): the mic goes on, in a new session
  await page.evaluate(() => { const s = window.__last(); s.live = false; s.onend?.(); });
  await page.waitForFunction(() => window.__recs.length === 2 && window.__recs[1].live, { timeout: 5000 });
  assert.ok(await page.$('.tq-compose-box button[aria-label="stop recording"]'), "still listening after Chrome's own end");
  assert.equal(await page.$("[data-tq-mic-err]"), null, "no error line for a natural end");

  await page.evaluate(() => window.__say(["reply saying Thursday works", true]));
  await page.waitForFunction(() => document.querySelector(".tq-compose-box textarea")?.value === "reply saying Thursday works", { timeout: 5000 });

  await page.click('.tq-compose-box button[aria-label="stop recording"]');
  await page.waitForSelector('.tq-compose-box button[aria-label="dictate"]', { timeout: 5000 });
  assert.equal(await box(), "reply saying Thursday works", "the words stay in the box");
  assert.equal(await page.evaluate(() => window.__recs.length), 2, "a stop is not restarted");

  // a blocked microphone: the mic goes off and says why, beside it
  await page.click('.tq-compose-box button[aria-label="dictate"]');
  await page.waitForFunction(() => window.__recs.length === 3, { timeout: 5000 });
  await page.evaluate(() => { const s = window.__last(); s.onerror?.({ error: "not-allowed" }); s.live = false; s.onend?.(); });
  await page.waitForSelector('.tq-compose-box button[aria-label="dictate"]', { timeout: 5000 });
  await page.waitForSelector("[data-tq-mic-err]", { visible: true, timeout: 5000 });
  const line = await page.$eval("[data-tq-mic-err]", (e) => e.textContent);
  assert.match(line, /blocked the microphone.*address bar/);
  assert.equal(await page.evaluate(() => window.__recs.length), 3, "a blocked mic is not started again");
  assert.deepEqual(errors, []);
});
