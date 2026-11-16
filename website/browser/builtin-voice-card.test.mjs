import test from "node:test";
import assert from "node:assert/strict";
import { startHarness, clickNav } from "./harness.mjs";

test("the built-in voice card selects Windows and its mic toggles Windows voice typing on the test box", { timeout: 300000 }, async (t) => {
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
      builtin: { engine: "windows_voice_typing", label: "Windows voice typing", keys: true } });
    if (url.pathname === "/api/voice/transcribe") { hit.push("cloud"); return ok({ text: "wrong route" }); }
    // Win+H (voice.toggle_voice_typing): what the box had focused when the chord went is where Windows' own bar types
    if (url.pathname === "/api/voice/keys") { page.evaluate(() => document.activeElement?.closest("[data-tq-builtin-voice]") && document.activeElement.tagName).then((t) => hit.push(`windows:${t}`)); return ok({ toggled: true }); }
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
  for (let i = 0; i < 50 && !hit.length; i++) await new Promise((r) => setTimeout(r, 100));
  assert.deepEqual(hit, ["windows:TEXTAREA"], "Win+H went with the card's test box focused, and nothing went to a voice AI");
  assert.equal(await page.evaluate(() => localStorage.getItem("taskuary-microphone-provider")), "windows");
  assert.deepEqual(errors, []);
});
