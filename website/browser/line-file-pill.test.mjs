import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A FILE HE SENDS WHILE THE AGENT WORKS IS A PILL ON HIS LINE FROM THE PRESS ON (the attach stress round, 2026-11-18): a line sent while a turn
   works waits by the box until a turn takes it, and that strip drew its words alone - a picture sent with words lost its pill until heard, and a
   picture sent alone was an empty row with a trash can. Every frame from the press to the heard line is read: the pill is there in each.
   Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "line-file-pill");

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: "Compare", first: "Payworth, Spendly and Trainly - Spendly is cheapest.", wait: 6 }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.5" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api, bin };
}

for (const words of ["and this one", ""]) test(`a picture sent ${words ? "with words" : "alone"} while the agent works is a pill on his line from the press on`, { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/tasks", { Title: "Compare expense tools", Summary: "Compare expense tools for Northwind", Kind: "general" });
  assert.ok(made.taskId, JSON.stringify(made));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const box = "[data-tq-task-page] textarea.tq-aui-input";
  await page.waitForSelector(box, { visible: true, timeout: 60000 });
  await page.type(box, "Compare three tools."); await page.keyboard.press("Enter");
  // ...at work: what he sends now is drawn by the box until the agent hears it
  await page.waitForFunction((id) => fetch(`/api/tasks/${id}/conversation`, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })
    .then((r) => r.json()).then((j) => j.working), { timeout: 30000, polling: 300 }, made.taskId);
  const pic = path.join(w.bin, "venue plan.png");
  await writeFile(pic, Buffer.from("89504e470d0a1a0a0000000d4948445200000001000000010806000000", "hex"));
  const input = await page.$("[data-tq-task-page] input[type=file]");
  await input.uploadFile(pic);
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] .tq-attach-chip")].some((c) => /venue plan/.test(c.innerText)), { timeout: 20000 });
  if (words) await page.type(box, words);
  const dir = path.join(out, words ? "with-words" : "alone"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  const seen = await page.evaluate((words) => new Promise((done) => {
    const frames = [], t0 = performance.now();
    const read = () => {
      const rows = [...document.querySelectorAll("[data-tq-pending-item], [data-tq-chat-line]")].filter((r) => r.innerText.includes(words || "venue plan") || /venue plan/.test(r.innerText));
      const s = rows.map((r) => `${r.matches("[data-tq-pending-item]") ? "waits" : "line"}:${/venue plan/.test(r.innerText) ? "pill" : "no pill"}:${(r.innerText || "").replace(/\s+/g, " ").slice(0, 60)}`).join(" | ");
      const chip = document.querySelector("[data-tq-pending-item] .tq-attach-chip");
      if (frames.at(-1)?.s !== s) frames.push({ at: Math.round(performance.now() - t0), s, chip: chip?.clientWidth, need: chip?.scrollWidth });
    };
    const obs = new MutationObserver(read); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    document.querySelector("[data-tq-task-page] [data-tq-send]").click();
    setTimeout(() => { obs.disconnect(); read(); done(frames); }, 14000);
  }), words);
  await rec.stop();
  await writeFile(path.join(dir, "frames.json"), JSON.stringify(seen, null, 1));
  const bad = seen.filter((f) => f.s && /no pill/.test(f.s));
  await note(dir, { done: `A line sent ${words ? "with words and" : "as"} a picture while the agent works.`, expect: "A pill on his line from the press, waiting and heard alike.",
    saw: JSON.stringify(seen), verdict: bad.length ? "FAIL" : "PASS" });
  assert.ok(seen.some((f) => /waits:pill/.test(f.s)), `never waited by the box: ${JSON.stringify(seen)}`);
  assert.ok(seen.some((f) => /line:pill/.test(f.s)), `never heard with its pill: ${JSON.stringify(seen)}`);
  // ...and the pill reads his file's name whole, never squeezed to "venu…"
  assert.ok(seen.every((f) => !/waits/.test(f.s) || f.chip >= f.need), `the pill was squeezed by the box: ${JSON.stringify(seen)}`);
  assert.deepEqual(bad, [], `a frame drew his line without its pill: ${JSON.stringify(seen)}`);
  assert.deepEqual(errors, []);
});
