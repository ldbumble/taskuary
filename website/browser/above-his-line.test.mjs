import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";
import { NAMES, check, sampler } from "./real-conv.mjs";

/* NOTHING ABOVE A NEW PROMPT, RECORDED (the owner, 0.4.0.26: "when i type in prompt the agent is typing on top of it then under it. weird"):
   a general chat on a stand-in claude that writes slowly, so each answer streams for seconds. He sends a line at rest, then one while that
   answer still streams, then one more at rest. Every painted frame is read (real-conv's sampler) and judged by its rules: nothing new drawn
   above what was there, no turn at work above his newest line, his line heard with its turn under it. The screen is recorded
   (TQ_REC_DIR, else a temp folder) to be watched. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
// ...a turn that writes for seconds, message by message as the real CLI does between its steps: the beat his line meets the agent's words
const said = (t) => ({ type: "assistant", message: { role: "assistant", content: [{ type: "text", text: t }] }, _sleep: 0.9 });
const LONG = (w) => [said(w), ...["Payworth bills per head each month.", "Trainly bills per seat each quarter.", "Spendly bills per site each year.",
  "Payworth is cheapest for a small office.", "Trainly is cheapest past fifty heads."].map((x) => said(`${w.split(" ")[1]}: ${x}`))];
// ...each rule reads the whole prompt (a task's turn names his words its own way), the newest office first
const SCRIPT = [{ when: "west office", anywhere: true, events: LONG("The west office has no vendor yet."), first: "That is the west office." },
  { when: "north office", anywhere: true, events: LONG("The north office runs Trainly today."), first: "That is the north office." },
  { when: "south office", anywhere: true, events: LONG("The south office runs two sites."), first: "That is the south office." }];

/* ...AND THE WORDS, NOT ONLY THE ROWS (the sampler reads which rows stand where; his "typing on top of it" is words growing): each painted
   frame, every row's id and its words. A row above his newest line that gains words in a frame after that line was painted is the agent
   typing over his line - what it writes from his line on belongs under it */
const wordsSampler = () => {
  window.__words = []; let last = "";
  const tick = () => { if (window.__wordsOff) return;
    const vp = document.querySelector(window.__tid ? `[data-tq-task-page="${window.__tid}"] .tq-aui-viewport` : "[data-tq-task-page] .tq-aui-viewport");
    if (vp) { const rows = [...vp.querySelectorAll("[data-tq-item]")].map((e) => [e.getAttribute("data-tq-item"), (e.querySelector(".tq-aui-agent-body, .tq-aui-user-bubble") || e).innerText.replace(/\s+/g, " ").trim()]);
      const sig = JSON.stringify(rows); if (sig !== last) { last = sig; window.__words.push({ t: Math.round(performance.now()), rows }); } }
    requestAnimationFrame(() => setTimeout(tick, 0)); };
  tick();
};
const isLine = (id) => /^l[0-9a-z]/.test(id) && !id.startsWith("t:");
export const wordsAbove = (frames) => { const bad = [];
  frames.forEach((f, n) => { const prev = frames[n - 1]; if (!prev) return;
    const his = f.rows.map(([id]) => isLine(id)).lastIndexOf(true), hisId = f.rows[his]?.[0];
    if (his < 0 || !prev.rows.some(([id]) => id === hisId)) return;
    f.rows.slice(0, his).forEach(([id, w]) => { const was = prev.rows.find(([i]) => i === id)?.[1];
      if (was != null && w.length > was.length && !isLine(id)) bad.push(`${f.t} ms: ${id} above his line ${hisId} grew: "${w.slice(was.length, was.length + 60)}"`); }); });
  return bad; };
// ...and none of it said twice around his line: a sentence of the row right above his newest line drawn again in the row under it
export const twiceAround = (frames) => { const bad = [], seen = new Set(), parts = (w) => w.split(/(?<=[.!?])\s+/).filter((x) => x.length > 15);
  for (const f of frames) { const his = f.rows.map(([id]) => isLine(id)).lastIndexOf(true), up = f.rows[his - 1]?.[1] || "", down = f.rows[his + 1]?.[1] || "";
    for (const x of his > 0 ? parts(down) : []) if (parts(up).includes(x) && !seen.has(x)) { seen.add(x); bad.push(`${f.t} ms: "${x}" stands above his line ${f.rows[his][0]} and again under it`); } }
  return bad; };

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32", fake = path.join(repo, "tests", "fake_claude.py");
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.8" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  const page = await h.newPage(), errors = [];
  await page.setViewport({ width: 1600, height: 900 });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  return { ...h, api, page, errors };
}
const say = async (page, w) => { await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus()); await page.keyboard.type(w); await page.keyboard.press("Enter"); };
const inChat = (page, re, timeout = 60000) => page.waitForFunction((s) => new RegExp(s).test(document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || ""), { timeout, polling: 30 }, re.source);
const atRest = (page) => page.waitForFunction(() => document.querySelector("[data-tq-task-page] .tq-aui-viewport") && !document.querySelector("[data-tq-task-page] [data-tq-working]"), { timeout: 60000, polling: 50 });
// ...the frames read from the first one, the screen recorded, and what was seen written beside the video
async function watched(w, name, done, walk) {
  const { page } = w, out = path.join(process.env.TQ_REC_DIR || await mkdtemp(path.join(os.tmpdir(), "tq-above-")), name), rec = await record(page, out);
  let bad = [], frames = [], words = [];
  try {
    await page.evaluate(sampler, NAMES); await page.evaluate(wordsSampler);
    await walk();
    frames = await page.evaluate(() => { cancelAnimationFrame(window.__raf); window.__wordsOff = true; return window.__frames; });
    words = await page.evaluate(() => window.__words);
    bad = [...check(frames), ...wordsAbove(words), ...twiceAround(words)];
  } finally {
    await rec.stop();
    await writeFile(path.join(out, "samples.json"), JSON.stringify(frames)); await writeFile(path.join(out, "words.json"), JSON.stringify(words));
    await note(out, { done, expect: "His line stays where it was drawn; its turn's dots and words appear under it, never above and then moved.",
      saw: bad.join("\n") || "no finding", verdict: bad.length ? "FAIL" : "PASS" });
  }
  assert.deepEqual(bad, [], `recorded in ${out}`);
  assert.deepEqual(w.errors, []);
}

test("his line stays put and everything new draws under it: sent at rest and while an answer streams", { timeout: 300000 }, async (t) => {
  const w = await world(t), { page } = w;
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare payroll vendors office by office", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; window.__tid = id; }, made.taskId);
  await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 60000 });
  await watched(w, "chat", "Three lines on a slow-writing stand-in: at rest, while the answer streams, at rest again.", async () => {
    await say(page, "start with the south office");
    await page.waitForFunction(() => /south office runs/.test(document.querySelector("[data-tq-task-page] [data-tq-turn=working]")?.innerText || ""), { timeout: 60000, polling: 30 });
    // ...the answer is streaming: he writes again now
    await say(page, "then the north office"); await inChat(page, /The north office runs Trainly/); await atRest(page);
    await new Promise((r) => setTimeout(r, 800));
    await say(page, "and the west office"); await inChat(page, /The west office has no vendor/); await atRest(page);
    await new Promise((r) => setTimeout(r, 1500));
  });
});

// ...AND HIS FIRST LINE, TYPED IN NEW'S BOX (the one start, /api/start): the task opens with its agent at work, his words its first line
test("a line typed in New opens its task with his words first and the agent's under them, from the first frame", { timeout: 300000 }, async (t) => {
  const w = await world(t), { page } = w;
  await page.evaluate(() => { location.hash = "new-task"; });
  const box = "[data-tq-new] [data-tq-prompt-box]";
  await page.waitForSelector(`${box} textarea`, { visible: true, timeout: 60000 });
  await watched(w, "new", "New's box: 'start with the south office', Send; the task opens with its agent at work; then one more line at rest.", async () => {
    await page.type(`${box} textarea`, "start with the south office"); await page.click(`${box} button[type=submit]`);
    await inChat(page, /south office runs/); await atRest(page);
    await new Promise((r) => setTimeout(r, 800));
    await say(page, "and the west office"); await inChat(page, /The west office has no vendor/); await atRest(page);
    await new Promise((r) => setTimeout(r, 1500));
  });
});

// A TASK IS NEVER ITS HEAD OVER NOTHING (the owner's rule; seen in one of two runs of the test above, 2026-11-18: New's task drew its head with
// no chat under it for ~337 ms): the chat's own code still on its way is that beat, held here until a second after Send - every frame from Send
// until the chat stands, read for a task head with no chat room under it
test("New's task never stands as its head over nothing while the chat's code is still coming", { timeout: 300000 }, async (t) => {
  const w = await world(t), { page } = w;
  let release; const held = new Promise((r) => { release = r; });
  const guard = page.fixtureRequestGuard; page.off("request", guard);
  page.on("request", (r) => (/GeneralWorkspace\.jsx/.test(r.url()) ? held.then(() => guard(r)) : guard(r)));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.evaluate(() => { location.hash = "new-task"; });
  const box = "[data-tq-new] [data-tq-prompt-box]";
  await page.waitForSelector(`${box} textarea`, { visible: true, timeout: 60000 });
  await page.evaluate(() => { window.__bare = []; const tick = () => { const p = document.querySelector("[data-tq-task-page]");
    if (p?.querySelector("[data-tq-agent-room]") && !p.querySelector(".tq-aui-viewport")) window.__bare.push(Math.round(performance.now()));
    if (!window.__stop) requestAnimationFrame(tick); }; tick(); });
  await page.type(`${box} textarea`, "start with the south office"); await page.click(`${box} button[type=submit]`);
  await new Promise((r) => setTimeout(r, 1000)); release();
  await inChat(page, /south office runs/);
  const bare = await page.evaluate(() => { window.__stop = true; return window.__bare; });
  assert.deepEqual(bare.length ? [bare[0], bare.at(-1)] : [], [], `the task stood as its head over nothing for ${bare.length ? bare.at(-1) - bare[0] : 0} ms`);
  assert.deepEqual(w.errors, []);
});
