import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE BOX STAYS OPEN WHILE THE OWNER DICTATES (the owner, 2026-10-27: "I click on the voice thing, it expands, but while I'm talking it gets
   small. come on.."). The mic opened the box; the browser's microphone prompt then took the focus, the box read that as a look away and shut
   - its mic with it, mid-sentence. A stand-in recogniser (the browser's own, Web Speech) listens; the focus leaves the box; it stays open
   until the words land in it. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the chat box stays open while its mic listens, and the words land in it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.evaluateOnNewDocument(() => {
    try { localStorage.setItem("tq-voice-browser", "1"); } catch { /* the mic falls back to asking */ }
    // a recogniser that hears one sentence when stopped - the owner talking for as long as the test holds it
    window.SpeechRecognition = class {
      start() { window.__listening = this; }
      stop() { window.__listening = null; this.onresult?.({ results: [Object.assign([{ transcript: "reply saying Thursday works" }], { isFinal: true })] }); this.onend?.(); }
      abort() { this.stop(); }
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
  await sleep(2000);

  await page.click(".tq-compose-box textarea");
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await page.click('.tq-compose-box button[aria-label="dictate"]');
  await page.waitForFunction(() => !!window.__listening, { timeout: 5000 });
  // ...the browser's mic prompt takes the focus away from the page's box
  await page.evaluate(() => document.activeElement?.blur());
  for (let i = 0; i < 6; i++) {
    await sleep(500);
    assert.ok(await page.$(".tq-compose-box[data-tq-open]"), `the box stays open while the owner talks (${(i + 1) * 0.5}s)`);
    assert.ok(await page.$('.tq-compose-box button[aria-label="stop recording"]'), "its mic is still there to stop");
  }
  await page.click('.tq-compose-box button[aria-label="stop recording"]');
  await page.waitForFunction(() => document.querySelector(".tq-compose-box textarea")?.value === "reply saying Thursday works", { timeout: 5000 });
  assert.ok(await page.$(".tq-compose-box[data-tq-open]"), "the words are in the open box");
  assert.deepEqual(errors, []);
});
