import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* WHERE A TYPED COMMAND'S TIME GOES, IN THE BROWSER (the assistant speed pass, 2026-10-27). Not a test - a probe, run by hand:
     npm exec --yes --package=node@22 -- node browser/assistant-speed.probe.mjs
   A fresh home with the stand-in claude on PATH (tests/fake_claude.py, its realistic timings unless FAKE_CLAUDE_* say otherwise), two
   invented tasks, and three commands typed into the chat box. Each is clocked on one wall clock: Enter -> the request leaves -> the
   stand-in has the prompt -> its first token -> its answer -> the page reads `done` -> the page shows the result (the task brought up,
   the button lit, the task put down). Prints a row per command. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-speed-claude-"));
const win = process.platform === "win32";
const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n`
  : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`, { mode: 0o755 });
const script = path.join(bin, "script.json"), log = path.join(bin, "fake.log");
Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: script, FAKE_CLAUDE_LOG: log });
await writeFile(script, "[]");
const h = await startHarness({ fresh: true, bin });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
  headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
const rows = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const a = await api("/api/tasks", { Title: "Lease renewal for the north office", Summary: "Renew the north office lease before it lapses", Kind: "general" });
  const b = await api("/api/tasks", { Title: "Quarterly access review", Summary: "Review who can reach the census database", Kind: "general" });
  const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;
  const call = (kind, params = {}) => `CALL: ${JSON.stringify({ kind, params })}`;
  const COMMANDS = [
    { text: `open ${ref(b.taskId)}`, first: `Here: [${ref(b.taskId)}](#task=${b.taskId}).`,
      shown: (id) => location.hash.includes(`task=${id}`) && !!document.querySelector(`[data-tq-task-page="${id}"]`), arg: b.taskId },
    { text: "remind me Monday", first: `Putting it away until Monday.\n${call("task.defer", { until: "monday 9am" })}`,
      shown: () => !!document.querySelector('button.tq-ab.p[data-tq-verb$="remind"]') },
    { text: "mark this done", first: `Done.\n${call("close")}`,
      shown: () => document.body.innerText.includes("✓ Mark done") },                  // its card folds with the button's badge
  ];
  await writeFile(script, JSON.stringify(COMMANDS.map((c) => ({ when: `^${c.text}$`, first: c.first }))));

  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  // every ndjson event of the turn's stream, timestamped as the page reads it
  await page.evaluateOnNewDocument(() => {
    window.__tq = [];
    const f = window.fetch;
    window.fetch = async (...args) => {
      const r = await f(...args);
      if (/assistant\/stream|concierge\/stream/.test(String(args[0]?.url || args[0]))) {
        const at = { url: String(args[0]), sent: Date.now(), events: [] }; window.__tq.push(at);
        const reader = r.clone().body.getReader(), dec = new TextDecoder(); let buf = "";
        (async () => { for (;;) { const { value, done } = await reader.read(); if (done) break; buf += dec.decode(value, { stream: true });
          const lines = buf.split("\n"); buf = lines.pop();
          for (const l of lines) if (l.trim()) { try { at.events.push([JSON.parse(l).type, Date.now()]); } catch { /* partial */ } } } })();
      }
      return r;
    };
  });
  const sent = [];
  page.on("request", (r) => { if (r.method() === "POST" && /stream$/.test(new URL(r.url()).pathname)) sent.push([new URL(r.url()).pathname, Date.now()]); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, a.taskId);
  await page.waitForSelector(`[data-tq-task-page="${a.taskId}"]`, { timeout: 30000 });
  await sleep(6000);                                   // the page opened: the CLI warms while the owner reads (concierge.warm)

  for (const c of COMMANDS) {
    const box = await page.waitForSelector(".tq-compose-box textarea", { timeout: 15000 });
    await box.click(); await page.keyboard.type(c.text);
    const n = await page.evaluate(() => window.__tq.length); sent.length = 0;
    const t0 = Date.now(); await page.keyboard.press("Enter");
    await page.waitForFunction(c.shown, { timeout: 30000, polling: "raf" }, c.arg).catch(async (e) => {
      console.log(`"${c.text}" never showed:`, JSON.stringify(await page.evaluate((n) => window.__tq.slice(n), n)),
                  (await page.evaluate(() => location.hash + "\n" + document.body.innerText)).slice(0, 2500),
                  (await readFile(log, "utf8").catch(() => "")).slice(-1500));
      throw e;
    });
    const ui = Date.now();
    await sleep(1500);
    const st = await page.evaluate((n) => window.__tq.slice(n), n);
    const lines = (await readFile(log, "utf8")).trim().split("\n").map((l) => JSON.parse(l)).filter((e) => e.t * 1000 >= t0);
    const at = (ev) => { const e = lines.find((x) => x.ev === ev); return e ? Math.round(e.t * 1000 - t0) : null; };
    const done = st.flatMap((s) => s.events).find(([k]) => k === "done");
    rows.push({ command: c.text, request: sent[0] ? sent[0][1] - t0 : null, prompt_in: at("turn"), first_token: at("first_token"),
      answer: at("result"), done: done ? done[1] - t0 : null, shown: ui - t0, prompt_chars: lines.find((x) => x.ev === "turn")?.chars ?? null,
      spawned: lines.some((x) => x.ev === "ready") });
    await sleep(1000);
  }
  // every CLI start, by the instructions it was launched with: a start after the page's own warm-up means those changed under it
  const starts = (await readFile(log, "utf8")).trim().split("\n").map((l) => JSON.parse(l)).filter((e) => e.ev === "ready");
  console.log("CLI starts:", starts.map((e) => `${new Date(e.t * 1000).toISOString().slice(11, 23)} ${path.basename(e.args[e.args.indexOf("--system-prompt-file") + 1] || "-")}`).join(" | "));
} finally { await h.close(); await rm(bin, { recursive: true, force: true }).catch(() => {}); }
console.log("ms after Enter:");
console.table(rows);
