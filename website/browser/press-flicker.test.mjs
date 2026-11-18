import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A PRESSED CARD NEVER LIGHTS AGAIN BEFORE IT SAYS WHAT WAS PRESSED (the owner, 2026-11-17: "when you click buttons on card it flickers then
   presses"). A reply drafted on arrival waits on the task; he presses Send. Every DOM change from the press is read: once the press began, the
   card's Send may spin or grey, and then the card is the sent card - never its live Send lit again in between. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "flicker");

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

test("a pressed Send never lights again before the card says it went", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await w.api("/api/fixture/outbox", {});
  const made = await w.api("/api/fixture/mail-task", {});
  assert.ok(made.taskId, JSON.stringify(made));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page] [data-tq-review="${made.reviewId}"]`;
  await page.waitForSelector(sel, { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 2500));
  const dir = path.join(out, "video", process.env.FLICKER_NAME || "send"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  // every committed state from the press: the card's Send - lit, spinning/greyed, or gone - and whether the card says it went
  const states = await page.evaluate((sel) => new Promise((done) => {
    const seen = [], t0 = performance.now();
    const read = () => {
      const c = document.querySelector(sel), b = c && [...c.querySelectorAll("button")].find((x) => /^(Send|Sending…?)$/.test(x.innerText.trim()));
      const s = !c ? "gone" : b && !b.disabled ? "lit" : b ? "busy" : "pressed";
      // ...where the letter stands while it is still the waiting card: its To line, and the card's height
      const to = c?.querySelector("[data-tq-to-line]"), y = to ? Math.round(to.getBoundingClientRect().top) : null, h = c ? Math.round(c.getBoundingClientRect().height) : null;
      const last = seen.at(-1);
      if (last?.s !== s || last?.y !== y || last?.h !== h) seen.push({ at: Math.round(performance.now() - t0), s, y, h, text: (c?.innerText || "").slice(0, 120) });
    };
    const obs = new MutationObserver(read); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    read();
    const b = [...document.querySelector(sel).querySelectorAll("button")].find((x) => x.innerText.trim() === "Send");
    if (!b) return done([{ s: "no-send", text: [...document.querySelector(sel).querySelectorAll("button")].map((x) => x.innerText + (x.disabled ? "(off)" : "")).join("|") + " :: " + document.querySelector(sel).innerText.slice(0, 400) }]);
    b.click();
    setTimeout(() => { obs.disconnect(); read(); done(seen); }, 8000);
  }), sel);
  await rec.stop();
  assert.notEqual(states[0]?.s, "no-send", `no Send on the card: ${states[0]?.text}`);
  const after = states.slice(1), relit = after.findIndex((x, i) => x.s === "lit" && after.slice(0, i).some((y) => y.s !== "lit"));
  // ...and while it sends, the card holds still: its To line where it stood, its height what it was
  const end = states.findIndex((x) => x.y == null), waiting = end < 0 ? states : states.slice(0, end), moved = waiting.filter((x) => x.y != null && (Math.abs(x.y - waiting[0].y) > 2 || Math.abs(x.h - waiting[0].h) > 2));
  await writeFile(path.join(dir, "states.json"), JSON.stringify(states, null, 1));
  await note(dir, { done: "A reply drafted on arrival waits; the owner presses Send.", expect: "Send spins, then the card says it went - never lit again between.",
    saw: JSON.stringify(states), verdict: relit < 0 && !moved.length ? "PASS" : "FAIL" });
  assert.deepEqual(moved, [], `the card moved or changed size while sending: ${JSON.stringify(states)}`);
  assert.equal(relit, -1, `the card lit its Send again after the press: ${JSON.stringify(states)}`);
  assert.deepEqual(errors, []);
});
