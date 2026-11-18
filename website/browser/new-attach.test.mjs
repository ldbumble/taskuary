import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* EVERY KIND OF FILE ATTACHED IN NEW IS THE TASK'S OWN, ON HIS LINE, AND IN ITS AGENT'S OWN INPUT (the stress round of New's attachments).
   New is one box: its words and files go to the Assistant, which starts an agent's job, or writes a card back (a goal) to finish there. A
   picture, a PDF, a workbook, a CSV and a Word document are attached with the paperclip; each must be copied into the task's folder, drawn as
   a pill on the line that opens its chat, and named - in that folder - in the prompt the agent's CLI itself was handed (its own log, not the
   app's). Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "new-attach");
const PNG = "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201a5e2b8f60000000049454e44ae426082";
const FILES = { "shot.png": Buffer.from(PNG, "hex"), "q3 census.pdf": Buffer.from("%PDF-1.4\n%fake\n"), "ledger.xlsx": Buffer.from("PK\x03\x04fake"),
  "rows.csv": Buffer.from("site,beds\nNorth,40\n"), "memo.docx": Buffer.from("PK\x03\x04fake") };

async function world(t, script) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(script));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.3", FAKE_CLAUDE_THINK: "0.3",
    FAKE_CLAUDE_LOG: path.join(bin, "log.jsonl"), FAKE_CLAUDE_LOG_PROMPT: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const files = path.join(bin, "files"); await mkdir(files);
  for (const [n, b] of Object.entries(FILES)) await writeFile(path.join(files, n), b);
  const log = path.join(bin, "log.jsonl");
  const prompts = async () => (existsSync(log) ? (await readFile(log, "utf8")).split("\n").filter(Boolean)
    .map((l) => JSON.parse(l)).filter((e) => e.ev === "turn" && e.prompt).map((e) => e.prompt) : []);
  return { ...h, api, files, prompts };
}

// New's one box, its files picked with the paperclip, its words typed, Send
async function ask(w, page, words, names) {
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => { location.hash = "new-task"; });
  const box = "[data-tq-new] [data-tq-prompt-box]";
  await page.waitForSelector(`${box} textarea`, { visible: true, timeout: 60000 });
  const input = await page.$(`${box} input[type=file]`);
  await input.uploadFile(...names.map((n) => path.join(w.files, n)));
  await page.waitForFunction((b, n) => document.querySelectorAll(`${b} [data-tq-file-chip], ${b} [data-tq-attach-more]`).length >= Math.min(n, 4),
    { timeout: 30000 }, box, names.length);
  await page.type(`${box} textarea`, words);
  await page.click(`${box} button[type=submit]`);
}

const taskFolder = (w, tid) => path.join(w.home, "scratch", "outputs", `TQ-${String(tid).padStart(4, "0")}`);

test("every kind of file attached in New is the started agent's: in its folder, a pill on his line, in its own prompt", { timeout: 300000 }, async (t) => {
  const job = { kind: "task.create_from_text", params: { kind: "general", text: "Summarise the attached files for Erin Blake" } };
  const w = await world(t, [{ when: "summarise these", first: `CALL: ${JSON.stringify(job)}` }]);
  const page = await w.newPage(); await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const names = Object.keys(FILES), dir = path.join(out, "agent"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  await ask(w, page, "summarise these for Erin", names);
  await page.waitForFunction(() => /task=\d+/.test(location.hash), { timeout: 60000 });
  const tid = Number((await page.evaluate(() => location.hash)).match(/task=(\d+)/)[1]);
  await page.waitForFunction((n) => document.querySelectorAll("[data-tq-line-file]").length >= n, { timeout: 60000 }, names.length).catch(() => {});
  const pills = await page.$$eval("[data-tq-line-file]", (xs) => xs.map((x) => x.innerText.trim()));
  const folder = taskFolder(w, tid), t0 = Date.now();
  let seen = "";
  while (Date.now() - t0 < 60000) {
    seen = (await w.prompts()).find((p) => p.includes(folder)) || "";
    if (names.every((n) => seen.includes(path.join(folder, n)))) break;
    await new Promise((r) => setTimeout(r, 500));
  }
  const bubble = await page.$eval("[data-tq-line-came]", (x) => x.parentElement.innerText).catch(() => "");
  await rec.stop();
  await note(dir, { done: "New's box: five files attached, 'summarise these for Erin', Send; the Assistant starts an agent's job.",
    expect: "the task opens; his line has a pill per file; each file in the task folder; the agent's prompt names each there",
    saw: JSON.stringify({ pills, tid, bubble, inFolder: names.map((n) => existsSync(path.join(folder, n))) }), verdict: "see asserts" });
  for (const n of names) assert.ok(existsSync(path.join(folder, n)), `${n} is in the task's folder`);
  assert.deepEqual([...pills].sort(), [...names].sort(), "a pill per file on his line");
  assert.doesNotMatch(bubble, /ATTACHED|scratch/, "no path in his words");
  for (const n of names) assert.ok(seen.includes(path.join(folder, n)), `the agent's own prompt names ${n} in the task's folder`);
  assert.deepEqual(errors, []);
});

test("a goal the Assistant writes back from New keeps the files that were in the box", { timeout: 300000 }, async (t) => {
  const goal = { kind: "task.create_from_text", params: { kind: "goal", text: "The Q3 census is filed for all three sites" } };
  const w = await world(t, [{ when: "track this", first: `CALL: ${JSON.stringify(goal)}` }]);
  const page = await w.newPage(); await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const dir = path.join(out, "goal"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  await ask(w, page, "track this until it is done", ["q3 census.pdf"]);
  // ...the goal's card comes up in New's place, the file still on it
  await page.waitForSelector("[data-tq-new] [data-tq-field=by]", { visible: true, timeout: 60000 });
  const chips = await page.$$eval("[data-tq-new] [data-tq-file-chip]", (xs) => xs.map((x) => x.getAttribute("data-tq-file-chip")));
  const buttons = await page.$$eval("[data-tq-new] button", (xs) => xs.map((x) => x.innerText.trim()).filter(Boolean));
  await rec.stop();
  await note(dir, { done: "New's box: a PDF, 'track this until it is done'; the Assistant writes a goal card back.",
    expect: "the goal card carries the PDF chip", saw: JSON.stringify({ chips, buttons }), verdict: chips.length ? "PASS" : "FAIL" });
  assert.deepEqual(chips, ["q3 census.pdf"], `the file is on the goal's card (buttons: ${buttons.join(" | ")})`);
  assert.deepEqual(errors, []);
});
