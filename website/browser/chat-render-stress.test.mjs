import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A CHAT ONLY GROWS AT ITS FOOT, AND SAYS IT WORKS THE MOMENT HE WRITES (chat-render). A general chat on the stand-in CLI is written to as a
   person does: a line that is answered, one whose turn runs a tool that fails, one whose CLI compacts mid-turn, one whose CLI dies part-way, two
   lines back to back, then a reload. Every DOM change is read: the rows above his newest line never change once he wrote it, a working line
   stands under his line from the first frame it is drawn, and no row is drawn empty. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "chat-render");
const tool = (id, name, input, ms = 0) => ({ _sleep: ms / 1000, type: "assistant", message: { role: "assistant", content: [{ type: "tool_use", id, name, input }] } });
const result = (id, text, error, ms = 0) => ({ _sleep: ms / 1000, type: "user", message: { role: "user", content: [{ type: "tool_result", tool_use_id: id, content: text, is_error: error }] } });

test("a general chat grows only at its foot, and says it works under his line at once", { timeout: 600000 }, async (t) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  const cli = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(cli, win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(cli, 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([
    { when: "what is on my plate", anywhere: true, first: "Two things: the vendor review for Erin and the ledger totals." },
    { when: "check the vendor folder", anywhere: true, first: "The folder is not there, so I looked in the shared drive instead.",
      events: [tool("tu1", "Bash", { command: "ls ~/vendor" }, 800), result("tu1", "ls: cannot access '/home/alex/vendor': No such file or directory", true, 800)] },
    { when: "summarise the long thread", anywhere: true, first: "Summary: Erin wants the review by Friday.",
      events: [tool("tu2", "Read", { file_path: "thread.txt" }, 600), result("tu2", "(a long thread)", false, 600),
               { _sleep: 0.6, type: "system", subtype: "compact_boundary", compact_metadata: { trigger: "auto", pre_tokens: 160000 } }] },
    { when: "draft the reply to gail", anywhere: true, exit: 1,
      events: [tool("tu3", "Read", { file_path: "gail.txt" }, 600), result("tu3", "Hi Alex, ...", false, 600)] },
    { when: "first of two", anywhere: true, first: "Got the first.", wait: 3 },
    { when: "second of two", anywhere: true, first: "Got the second." },
    { when: "audit every vendor file", anywhere: true, first: "All forty vendor files are read.",
      events: Array.from({ length: 40 }, (_, i) => [tool(`v${i}`, "Read", { file_path: `vendor-${i}.txt` }, 120), result(`v${i}`, "x".repeat(3000), false, 60)]).flat() },
    { when: "slow look at the ledger", anywhere: true, first: "The ledger is fine.", wait: 12,
      events: [tool("lg1", "Read", { file_path: "ledger.csv" }, 500)] },
    { when: "one I will stop", anywhere: true, first: "Never said.", wait: 30, events: [tool("st1", "Read", { file_path: "notes.md" }, 500)] },
    { when: "after the stop", anywhere: true, first: "Back after the stop." },
  ]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "1", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const task = await api("/api/fixture/mail-task", { kind: "general" });
  const p = await h.newPage();
  await p.setViewport({ width: 1280, height: 900 });
  const errors = []; p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(h.ui, { waitUntil: "domcontentloaded" });
  await p.evaluate((id) => { location.hash = `task=${id}`; }, task.taskId);
  await p.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 3000));
  await mkdir(out, { recursive: true });
  // every committed state of the chat, from before the first line to the end: its rows top to bottom
  const watch = () => {
    window.__seen = window.__seen || [];
    const t0 = performance.now();
    const read = () => {
      const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
      if (!vp) return;
      const rows = [...vp.querySelectorAll(".tq-aui-message")].map((e) => ({ k: e.className.match(/tq-aui-(user|agent|system)/)?.[1] || "?",
        h: Math.round(e.getBoundingClientRect().height), y: Math.round(e.getBoundingClientRect().top), t: (e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 90) }));
      const working = !!vp.querySelector("[data-tq-run-clock], [data-tq-starting-line]");
      const key = JSON.stringify([rows.map((r) => [r.k, r.t, r.h ? 1 : 0]), working]);
      if (window.__last !== key) { window.__last = key; window.__seen.push({ at: Math.round(performance.now() - t0), rows, working }); }
    };
    new MutationObserver(read).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    read();
  };
  await p.evaluateOnNewDocument(`window.__watch = ${watch.toString()}`);
  await p.evaluate(watch);
  const seenAll = [];
  const rec = await record(p, path.join(out, "video"));
  const typeIn = async (words) => {
    await p.waitForFunction(() => { const b = document.querySelector("[data-tq-task-page] .tq-aui-input"); return b && !b.disabled; }, { timeout: 60000 });
    await p.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input").focus());
    await p.keyboard.type(words); await p.keyboard.press("Enter"); };
  const until = (re, timeout = 60000) => p.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || ""),
    { timeout, polling: 100 }, re.source);
  const quiet = () => p.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-stop-run]"), { timeout: 90000, polling: 100 });
  const settle = (ms = 2500) => new Promise((r) => setTimeout(r, ms));
  try {
    await typeIn("what is on my plate"); await until(/Two things/); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "1-answered.png") });
    await typeIn("check the vendor folder"); await until(/shared drive instead/); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "2-tool-error.png") });
    await typeIn("summarise the long thread"); await until(/Erin wants the review/); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "3-compacted.png") });
    await typeIn("draft the reply to gail"); await settle(9000); await quiet().catch(() => {}); await settle();
    await p.screenshot({ path: path.join(out, "4-died.png") });
    await typeIn("first of two"); await settle(1200); await typeIn("second of two"); await until(/Got the second/, 90000); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "5-two.png") });
    await typeIn("audit every vendor file"); await until(/All forty vendor files/, 120000); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "7-long.png") });
    await typeIn("slow look at the ledger"); await settle(4000);
    seenAll.push(...(await p.evaluate(() => window.__seen)).map((x) => ({ ...x, at: `a${x.at}` })), { at: "RELOAD", rows: [], working: true });
    await p.reload({ waitUntil: "domcontentloaded" }); await p.waitForSelector("[data-tq-task-page] .tq-aui-viewport", { timeout: 60000 });
    await p.evaluate(() => window.__watch()); await until(/The ledger is fine/, 60000); await quiet(); await settle();
    await typeIn("one I will stop"); await settle(4000);
    await p.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-stop-run]")?.click()); await quiet(); await settle();
    await typeIn("after the stop"); await until(/Back after the stop/); await quiet(); await settle();
    await p.screenshot({ path: path.join(out, "8-stop.png") });
  } finally {
    await rec.stop({ sheet: 24 });
    await writeFile(path.join(out, "server.log"), h.backend.output());
  }
  const seen = [...seenAll, ...(await p.evaluate(() => window.__seen))];
  await p.reload({ waitUntil: "domcontentloaded" }); await until(/Back after the stop/); await settle(3000);
  const reloaded = await p.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] .tq-aui-message")].map((e) => (e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 90)));
  await p.screenshot({ path: path.join(out, "6-reloaded.png"), fullPage: true });
  await writeFile(path.join(out, "seen.json"), JSON.stringify(seen, null, 1));
  await writeFile(path.join(out, "server.log"), h.backend.output());
  await writeFile(path.join(out, "payload.json"), JSON.stringify(await api(`/api/tasks/${task.taskId}/conversation`), null, 1));
  // what broke: a row above his newest line that changed or appeared after he wrote it; his line with nothing working under it; an empty row
  const breaks = [];
  let mine = null;
  let steps = null;
  for (const s of seen) {
    if (s.at === "RELOAD") { mine = null; steps = null; continue; }
    const w = s.rows.find((r) => /working \d/.test(r.t)), n = w && +(w.t.match(/(\d+) steps?/)?.[1] || 0);
    if (w && steps && steps.line === s.rows.findLast((r) => r.k === "user")?.t && n < steps.n) breaks.push(`${s.at}ms: the turn at work went from ${steps.n} steps to ${n}`);
    steps = w ? { n, line: s.rows.findLast((r) => r.k === "user")?.t } : null;
    const his = s.rows.findLastIndex((r) => r.k === "user");
    if (his < 0) continue;
    const above = s.rows.slice(0, his).map((r) => r.t).join(" | "), line = s.rows[his].t;
    if (mine && mine.line === line && mine.above !== above) breaks.push(`${s.at}ms: above "${line}" changed:\n   was ${mine.above}\n   now ${above}`);
    if (!mine || mine.line !== line) mine = { line, above };
    const after = s.rows.slice(his + 1);
    for (const r of s.rows) if (r.h > 0 && !r.t) breaks.push(`${s.at}ms: an empty ${r.k} row`);
    if (!s.working && !after.some((r) => r.t))
      breaks.push(`${s.at}ms: "${line}" stands with nothing under it and nothing working`);
  }
  await note(out, { done: "A general chat: an answer, a tool error, a compaction, a CLI that died mid-turn, two lines back to back, a reload.",
    expect: "Rows above his newest line never change; a working line under his line at once; no empty row; the reload draws the same rows.",
    saw: breaks.join("\n") + "\nRELOADED: " + JSON.stringify(reloaded), verdict: breaks.length ? "FAIL" : "PASS" });
  assert.deepEqual(errors, []);
  assert.deepEqual(breaks, []);
});
