import test from "node:test";
import assert from "node:assert/strict";
import { startHarness, clickNav } from "./harness.mjs";

test("the built-in voice card selects Windows and tests it without an AI provider", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [], hit = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (q) => {
    const url = new URL(q.url());
    const ok = (data) => q.respond({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    if (url.pathname === "/api/voice/status") return ok({ ready: true, label: "Existing voice card", vocabulary: [],
      builtin: { engine: "windows_voice_typing", label: "Windows speech", live: true } });
    if (url.pathname === "/api/voice/transcribe") { hit.push("cloud"); return ok({ text: "wrong route" }); }
    if (url.pathname === "/api/voice/listen") { hit.push("windows"); return ok({ id: "abc123" }); }
    if (url.pathname.endsWith("/abc123/stop")) return ok({ said: [], done: true });
    if (url.pathname.endsWith("/abc123")) return ok({ said: url.searchParams.get("since") === "0" ? ["Test built-in dictation"] : [], done: false });
    return page.fixtureRequestGuard(q);
  });
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-nav="connections"]', { timeout: 30000 });
  await clickNav(page, "Connections");
  await page.waitForSelector('[data-tq-browse-chip="AI — voice"]', { timeout: 20000 });
  await page.click('[data-tq-browse-chip="AI — voice"]');
  await page.waitForSelector('[data-tq-browse-card="builtin-voice"]', { timeout: 20000 });
  await page.click('[data-tq-browse-card="builtin-voice"]');
  await page.waitForSelector('[data-tq-builtin-voice] [role="combobox"]');
  await page.waitForFunction(() => document.querySelector('[data-tq-builtin-voice] [role="combobox"]')?.getAttribute("aria-disabled") !== "true");
  await page.click('[data-tq-builtin-voice] [role="combobox"]');
  await page.click('[role="option"][data-value="windows"]');
  await page.waitForSelector('.MuiMenu-root', { hidden: true });
  const mic = '[data-tq-builtin-voice] button[data-tq-mic]';
  await page.waitForSelector(`${mic}:not([disabled])`);
  await page.click(mic);
  try {
    await page.waitForFunction(() => [...document.querySelectorAll('[data-tq-builtin-voice] textarea')].some((e) => e.value.includes("Test built-in dictation")), { timeout: 10000 });
  } catch (error) {
    throw new Error(`Microphone test did not receive text: ${JSON.stringify({ hit, errors, card: await page.$eval('[data-tq-builtin-voice]', (e) => e.innerText) })}`, { cause: error });
  }
  await page.click('[data-tq-builtin-voice] button[aria-label="stop recording"]');
  assert.deepEqual(hit, ["windows"]);
  assert.equal(await page.evaluate(() => localStorage.getItem("taskuary-microphone-provider")), "windows");
  assert.deepEqual(errors, []);
});
