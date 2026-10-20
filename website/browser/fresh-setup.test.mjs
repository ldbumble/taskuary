// SETUP NEVER ASSUMES AN AI, on the rendered page (the owner, 2026-10-20: "every time someone is installing a fresh install of the
// .exe, the advisor says claude is installed, set it up?? first of all it was not, and stop assuming that ... It should let them
// choose the AIs"). A first start - not the demo - on a PATH with no AI tool, then with one fake CLI on it.
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile, chmod } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const VENDORS = /claude|codex|gemini|chatgpt|openai|anthropic|copilot|qwen|cursor|devin|kimi|opencode|muse/i;

async function firstRun(harness) {
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-firstrun="ai"] [data-tq-card^="cli-"]', { timeout: 45000 });
  await page.waitForFunction(() => /What AI do you have\?/.test(document.querySelector(".tq-next-txt")?.innerText || ""), { timeout: 20000 });
  const seen = await page.evaluate(() => ({
    line: document.querySelector(".tq-next-txt").innerText,
    lit: [...document.querySelectorAll("[data-tq-firstrun] [data-tq-setup-lit]")].map((e) => e.innerText),
    cards: Object.fromEntries([...document.querySelectorAll("[data-tq-card]")].map((e) => [e.getAttribute("data-tq-card"), e.innerText])),
  }));
  return { page, errors, ...seen };
}

test("a fresh install with no AI tool lights no AI, names none and calls none installed or connected", { timeout: 180000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { line, lit, cards, errors } = await firstRun(harness);
  assert.doesNotMatch(line, VENDORS, `the Advisor line picks no vendor: ${line}`);
  assert.doesNotMatch(line, /installed|connected|set it up/i, line);
  assert.deepEqual(lit, [], "no card is lit - the person chooses");
  for (const [k, text] of Object.entries(cards)) assert.doesNotMatch(text, /Connected|On this computer|Installed/, `${k}: ${text}`);
  assert.ok(cards["cli-claude"] && cards["cli-codex"], "the coding tools are still offered, as choices");
  assert.deepEqual(errors, []);
});

test("one CLI genuinely on PATH is said to be found - as one choice, never lit, never connected", { timeout: 180000 }, async (t) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-cli-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const fake = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(fake, win ? "@echo ok\r\n" : "#!/bin/sh\necho ok\n"); if (!win) await chmod(fake, 0o755);
  const harness = await startHarness({ fresh: true, bin }); t.after(() => harness.close());
  const { line, lit, cards, errors } = await firstRun(harness);
  assert.match(line, /Claude is on this computer - pick it if that is the one you use, or pick any other/, line);
  assert.doesNotMatch(line, /connected|set it up/i, line);
  assert.deepEqual(lit, [], "found is offered, not picked");
  assert.match(cards["cli-claude"], /On this computer - pick it to check it works/);
  assert.doesNotMatch(cards["cli-codex"], /On this computer|Connected/, "only the one that is here");
  assert.deepEqual(errors, []);
});
