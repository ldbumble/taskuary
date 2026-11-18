import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* AN ACT'S CARD NEVER LIGHTS AGAIN BEFORE IT SAYS WHAT WAS PRESSED (the owner, 2026-11-17: "when you click buttons on card it flickers then
   presses"). A comment on a tracker item waits on the task (ActionCard); he presses Dismiss, or its press. Every DOM change from the press is
   read: once pressed, its buttons may grey, and then the card is the pressed card - never its buttons lit again in between. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "act-card");

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), "[]");
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// every committed state of the card from the press: its buttons lit, greyed, or none; and what it says
const watch = (page, sel, which, ms = 6000) => page.evaluate((sel, which, ms) => new Promise((done) => {
  const seen = [], t0 = performance.now();
  const read = () => {
    const c = document.querySelector(sel), bs = c ? [...c.querySelectorAll("button")] : [];
    const s = !c ? "gone" : !bs.length ? "pressed" : bs.some((b) => !b.disabled) ? "lit" : "busy";
    const text = (c?.innerText || "").replace(/\s+/g, " ").slice(-90), last = seen.at(-1);
    if (last?.s !== s || last?.text !== text) seen.push({ at: Math.round(performance.now() - t0), s, text, state: c?.getAttribute("data-tq-act-state") });
  };
  const obs = new MutationObserver(read); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  read();
  const b = document.querySelector(`${sel} ${which}`);
  if (!b) return done([{ s: "no-button", text: document.querySelector(sel)?.innerText }]);
  b.click();
  setTimeout(() => { obs.disconnect(); read(); done(seen); }, ms);
}), sel, which, ms);

const relitAfter = (states) => { const after = states.slice(1); return after.findIndex((x, i) => x.s === "lit" && after.slice(0, i).some((y) => y.s !== "lit")); };

for (const [name, which, body] of [["dismiss", "[data-tq-act-dismiss]", {}], ["post-fails", "[data-tq-act-press]", { connected: true }]]) {
  test(`an act's card pressed (${name}) never lights again before it says what was pressed`, { timeout: 300000 }, async (t) => {
    const w = await world(t), page = await w.newPage();
    await page.setViewport({ width: 1600, height: 900 });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    const made = await w.api("/api/fixture/act-card", body);
    assert.ok(made.taskId, JSON.stringify(made));
    await page.goto(w.ui, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
    const sel = `[data-tq-task-page] [data-tq-act="${made.reviewId}"]`;
    await page.waitForSelector(sel, { visible: true, timeout: 60000 });
    await new Promise((r) => setTimeout(r, 2500));
    const dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
    const rec = await record(page, dir);
    const states = await watch(page, sel, which);
    // ...and once the chat is read again it is still that card, pressed, with its words - never swapped for another (2026-11-18)
    const kept = await page.evaluate((sel) => document.querySelector(sel)?.innerText.replace(/\s+/g, " ") || "", sel);
    await rec.stop();
    await writeFile(path.join(dir, "states.json"), JSON.stringify(states, null, 1));
    const relit = relitAfter(states);
    await note(dir, { done: `An act's card waits; the owner presses ${name}.`, expect: "Its buttons grey, then the card says what was pressed - never lit again between.",
      saw: JSON.stringify(states), verdict: relit < 0 ? "PASS" : "FAIL" });
    assert.notEqual(states[0]?.s, "no-button", `no button on the card: ${states[0]?.text}`);
    assert.equal(relit, -1, `the card lit its buttons again after the press: ${JSON.stringify(states)}`);
    assert.match(kept, /deployed this morning/, `the pressed card went from where it stood: ${JSON.stringify(states)}`);
    assert.ok(!states.some((x) => x.s === "gone"), `the card went, or was swapped for another, after the press: ${JSON.stringify(states)}`);
    assert.deepEqual(errors, []);
  });
}
