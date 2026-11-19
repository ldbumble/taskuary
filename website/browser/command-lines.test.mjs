import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A COMMAND WITH NO WORDS OF ITS OWN IS SHOWN AS ITSELF (the owner, 2026-11-19, of rows reading "Ran a command", "Ran git", "Ran foreach, and 1
   more": "If not exact detail show what it's doing? other chats do this description thing much better"). The stand-in ACP adapter plays a turn
   in the shape Codex sends: a reasoning header, then shell calls with no description - wrapped in powershell.exe -Command as Codex wraps them -
   `git log --oneline -10`, a 12-line PowerShell block, a long foreach line, a `python -c` snippet, the same pytest twice. Each row should be the
   command in a code span, a script by its language and length; never "Ran a command" or a bare program. Shot with the work fold open, and
   recorded. Invented people and repositories only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "command-lines", process.env.COMMAND_LINES_SHOT || "now");

let n = 0;
const thought = (mid, h) => [{ sessionUpdate: "agent_thought_chunk", messageId: mid, content: { type: "text", text: `**${h}**` } }];
const ran = (command) => {
  const id = `sh_${++n}`, rawInput = { command: ["C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", command], cwd: "C:\\work\\ledger" };
  return [{ sessionUpdate: "tool_call", toolCallId: id, title: command, kind: "execute", status: "in_progress", rawInput },
    { sessionUpdate: "tool_call_update", toolCallId: id, status: "completed", content: [{ type: "content", content: { type: "text", text: "ok" } }], _sleep: 0.05 }];
};
const BLOCK = ["$rows = Import-Csv totals.csv", ...Array.from({ length: 10 }, (_, i) => `$rows[${i}].Total = [decimal]$rows[${i}].Total`), "$rows | Export-Csv out.csv"].join("\n");
const SCRIPT = [
  { when: "totals", first: "The totals add up; the test passes.", updates: [
    ...thought("r1", "Checking the recent history"),
    ...ran("git log --oneline -10"),
    ...thought("r2", "Normalising the totals sheet"),
    ...ran(BLOCK),
    ...ran("foreach ($f in Get-ChildItem *.csv) { $n = (Import-Csv $f).Count; \"$($f.Name) $n\" }"),
    ...ran("python -c \"import json; print(json.load(open('t.json'))['total'])\""),
    ...thought("r3", "Running the totals test"),
    ...ran("pytest tests/test_totals.py -q"),
    ...ran("pytest tests/test_totals.py -q"),
  ] },
];

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py"), cli = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(cli, win ? `@"${py}" "${fake}" %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(cli, 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_ACP_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SPAWN: "0.5" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = async (p, body, method = body ? "POST" : "GET") => {
    const r = await fetch(`${h.fixtureApi}${p}`, { method, headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) });
    assert.ok(r.ok, `Fixture request failed: ${p}, ${r.status}`);
    return r.json();
  };
  await api("/api/cli/connections/claude", { cmd: cli }, "PUT");
  await api("/api/ai/defaults", { slot: "default_brain", value: "cli:claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// every row of the turn's open fold, its words as drawn, and the code span inside it
const look = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]");
  return [...pane.querySelectorAll(".tq-aui-steps > .tq-aui-step")].map((e) => { const s = e.querySelector("summary, .tq-aui-step-line");
    return { text: (s?.innerText || "").trim(), code: s?.querySelector("code")?.innerText || "" }; });
});

test("a command with no words of its own reads as the command itself, a script by its language and length", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1400, height: 1000 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const git = process.platform === "win32" ? execFileSync("where.exe", ["git"], { encoding: "utf8" }).trim().split(/\r?\n/)[0] : "git";
  const made = await w.api("/api/fixture/coding", { git, title: "Ledger totals check" });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const input = "[data-tq-task-page] [data-tq-agent-room] .tq-aui-input";
  await page.waitForSelector(input, { visible: true, timeout: 60000 });
  await page.waitForFunction((s) => !document.querySelector(s)?.disabled, { timeout: 60000 }, input);
  await mkdir(out, { recursive: true });
  const rec = await record(page, out);
  await page.evaluate((s) => document.querySelector(s)?.focus(), input);
  await page.keyboard.type("check the totals"); await page.keyboard.press("Enter");
  const dump = async (e) => { await page.screenshot({ path: path.join(out, "stuck.png") }); throw new Error(`${e.message}
${(await page.evaluate(() => document.body.innerText)).slice(-2500)}`); };
  await page.waitForFunction(() => /the test passes/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 120000 }).catch(dump);
  await new Promise((r) => setTimeout(r, 1500));
  await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-agent .tq-aui-working-fold:not([open]) > summary")?.click());
  await new Promise((r) => setTimeout(r, 800));
  const rows = await look(page);
  const pane = await page.$("[data-tq-task-page] .tq-aui-viewport");
  await pane.screenshot({ path: path.join(out, "chat.png") });
  await rec.stop();
  await writeFile(path.join(out, "seen.json"), JSON.stringify(rows, null, 1));
  const texts = rows.map((r) => r.text);
  const bad = texts.filter((r) => /^Ran (a command|git|python|pytest|foreach)(, and \d+ more)?( \(\d+ times\))?$/.test(r));
  const want = ["git log --oneline -10", "pytest tests/test_totals.py -q"].filter((c) => !rows.some((r) => r.code === c));
  await note(out, { done: "A coding turn in Codex's shape: reasoning headers, then wordless shell calls wrapped in powershell -Command: git log, a 12-line block, a foreach line, python -c, the same pytest twice.",
    expect: "Each command row is the command in a code span (a long one cut), the block 'Ran a PowerShell script (12 lines)', pytest once '(2 times)'; never 'Ran a command' or a bare program.",
    saw: JSON.stringify(texts), verdict: bad.length || want.length ? "FAIL" : "PASS" });
  assert.deepEqual(bad, [], `rows that name a program, not the command: ${JSON.stringify(texts)}`);
  assert.deepEqual(want, [], `commands not shown as themselves: ${JSON.stringify(rows)}`);
  assert.ok(texts.includes("Ran a PowerShell script (12 lines)"), JSON.stringify(texts));
  assert.ok(texts.includes("Ran pytest tests/test_totals.py -q (2 times)"), JSON.stringify(texts));
  assert.ok(texts.includes("Checking the recent history"), `the thought stands above its commands: ${JSON.stringify(texts)}`);
  assert.deepEqual(errors, []);
});
