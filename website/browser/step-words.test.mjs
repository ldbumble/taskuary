import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A TURN'S STEPS SAY WHAT THE AGENT DID (the owner, 2026-11-18, of a coding task on an ACP CLI: "feedback text is still weird.. weird spaces
   between feedback text and box then ran git is not feedback?? need better than this"). The stand-in ACP adapter plays a turn in the shape
   Codex sends: reasoning headers two to a message, shell calls with no words of their own (`git -c .. -C ..`, a cmd.exe wrapper, a here-string
   fed to python, Get-Content with a line count, taskuary --board/--note), two helpers started by title, then a command he allows from now on;
   a second turn is at work on a read. Shot with the work fold open, and recorded. Invented people and repositories only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "step-words", process.env.STEP_WORDS_SHOT || "now");

let n = 0;
const thought = (mid, ...heads) => heads.flatMap((h) => [{ sessionUpdate: "agent_thought_chunk", messageId: mid, content: { type: "text", text: "\n\n" } },
  { sessionUpdate: "agent_thought_chunk", messageId: mid, content: { type: "text", text: `**${h}**` } }]);
const ran = (command, { done = true, kind = "execute", title = command, rawInput = { command, cwd: "C:\\work\\ledger" } } = {}) => {
  const id = `sh_${++n}`;
  return [{ sessionUpdate: "tool_call", toolCallId: id, title, kind, status: "in_progress", rawInput },
    ...(done ? [{ sessionUpdate: "tool_call_update", toolCallId: id, status: "completed", content: [{ type: "content", content: { type: "text", text: "ok" } }], _sleep: 0.05 }] : [])];
};
const SCRIPT = [
  { when: "carry on with the totals", wait: 120, updates: [
    ...thought("r6", "Reading the insert procedure"),
    ...ran("Get-Content ledger/sql/procedures/Insert_Totals.sql | Select-Object -Skip 94 -First 60", { done: false }),
  ] },
  { when: "totals history", ask: "git push origin feat/ledger-history", first: "The history branch is pushed; the roll-up runs next.", updates: [
    ...thought("r1", "Locating the ledger scripts"),
    ...ran('taskuary --board\ntaskuary --note "Looking into the history of the ledger totals." --kind working\ngit -c safe.directory=C:/work/ledger -C ledger status --short --branch'),
    ...ran("", { kind: "other", title: "Start subagent history_probe", rawInput: { agentThreadId: "a1", agentPath: "/root/history_probe", activityKind: "started" } }),
    ...ran("", { kind: "other", title: "Start subagent history_count", rawInput: { agentThreadId: "a2", agentPath: "/root/history_count", activityKind: "started" } }),
    ...thought("r2", "Reading the totals snapshots"),
    ...ran("git -c safe.directory=C:/work/ledger -C ledger fetch --no-tags origin master"),
    ...ran("Get-Content ledger/totals.py -TotalCount 290\nGet-Content ledger/sql/notes.sql -TotalCount 60\nrg -n 'tax' ledger/sql"),
    ...thought("r3", "Reviewing the vendor mapping snapshots", "Planning the history roll-up"),
    ...thought("r4", "Checking the effective dates"),
    ...ran("@'\nfrom pathlib import Path\nimport json\nprint(len(Path('ledger/totals.py').read_text()))\n'@ | python -"),
    ...thought("r5", "Preparing the versioned schema", "Writing the isolated plan"),
    ...ran("\"C:\\\\WINDOWS\\\\system32\\\\cmd.exe\" /c 'git -C ledger worktree add -b feat/ledger-history ../ledger-history origin/master'"),
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

// every row of the turn's open fold, its words as drawn; the turn heads and the working line, with their type
const look = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]"), css = (e) => e && getComputedStyle(e);
  const rows = [...pane.querySelectorAll(".tq-aui-steps > .tq-aui-step")].map((e) => (e.querySelector("summary, .tq-aui-step-line")?.innerText || "").trim());
  const heads = [...pane.querySelectorAll(".tq-aui-agent > .tq-aui-role")].map((e) => ({ text: e.innerText, font: css(e).fontFamily, case: css(e).textTransform }));
  const line = pane.querySelector("[data-tq-working-line]");
  // ...the gaps round the answered card: from the last row above it, and to the head under it
  const card = pane.querySelector("[data-tq-permission-answered]"), r = card?.getBoundingClientRect();
  const above = card && [...pane.querySelectorAll(".tq-aui-step")].filter((e) => e.getBoundingClientRect().bottom <= r.top).pop();
  const below = card && [...pane.querySelectorAll(".tq-aui-role")].find((e) => e.getBoundingClientRect().top >= r.bottom);
  const gaps = card ? { aboveCard: Math.round(r.top - above.getBoundingClientRect().bottom), belowCard: Math.round(below.getBoundingClientRect().top - r.bottom),
    chain: (() => { const out = []; for (let e = above; e && e !== pane; e = e.parentElement) { const c = css(e); if (parseFloat(c.marginBottom) || parseFloat(c.paddingBottom)) out.push(`${e.className || e.tagName}:${c.marginBottom}/${c.paddingBottom}`); } return out; })() } : null;
  return { rows, heads, gaps, line: line && { text: line.innerText, font: css(line).fontFamily } };
});

test("a turn's steps read as what the agent did, each thought its own line, in the app's own type", { timeout: 560000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1400, height: 1000 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const git = process.platform === "win32" ? execFileSync("where.exe", ["git"], { encoding: "utf8" }).trim().split(/\r?\n/)[0] : "git";
  const made = await w.api("/api/fixture/coding", { git, title: "Ledger totals history" });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const input = "[data-tq-task-page] [data-tq-agent-room] .tq-aui-input";
  await page.waitForSelector(input, { visible: true, timeout: 60000 });
  await page.waitForFunction((s) => !document.querySelector(s)?.disabled, { timeout: 60000 }, input);
  await mkdir(out, { recursive: true });
  const rec = await record(page, out);
  const say = async (words) => { await page.evaluate((s) => document.querySelector(s)?.focus(), input); await page.keyboard.type(words); await page.keyboard.press("Enter"); };
  await say("look into the totals history");
  const dump = async (e) => { await page.screenshot({ path: path.join(out, "stuck.png") }); throw new Error(`${e.message}
${(await page.evaluate(() => document.body.innerText)).slice(-2500)}`); };
  await page.waitForSelector("[data-tq-task-page] [data-tq-permission-answer^=allow]", { visible: true, timeout: 200000 }).catch(dump);
  await page.click(await page.$("[data-tq-task-page] [data-tq-permission-answer=allow_always]") ? "[data-tq-task-page] [data-tq-permission-answer=allow_always]" : "[data-tq-task-page] [data-tq-permission-answer=allow_once]");
  await page.waitForSelector("[data-tq-task-page] [data-tq-permission-answered]", { visible: true, timeout: 30000 }).catch(dump);
  await page.waitForFunction(() => /roll-up runs next/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 30000 }).catch(dump);
  await say("carry on with the totals");
  await page.waitForSelector("[data-tq-task-page] [data-tq-working-line]", { visible: true, timeout: 60000 }).catch(dump);
  await page.waitForFunction(() => /Insert_Totals|insert procedure/i.test(document.querySelector("[data-tq-working-line]")?.innerText || ""), { timeout: 30000 }).catch(() => {});
  // ...the first turn's work, opened
  await page.evaluate(() => { const f = document.querySelector("[data-tq-task-page] .tq-aui-agent .tq-aui-working-fold > summary"); f?.click(); });
  await new Promise((r) => setTimeout(r, 800));
  const seen = await look(page);
  const card = await page.$("[data-tq-task-page] [data-tq-permission-answered]");
  await card.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({ path: path.join(out, "turn.png") });
  const pane = await page.$("[data-tq-task-page] .tq-aui-viewport");
  await pane.screenshot({ path: path.join(out, "chat.png") });
  await rec.stop();
  await writeFile(path.join(out, "seen.json"), JSON.stringify(seen, null, 1));
  const bad = seen.rows.filter((r) => /^(Ran (git|taskuary|python|a command)$|Used |Read \d+\b|Looked something up in Taskuary)/.test(r));
  await note(out, { done: "A coding turn in Codex's shape: wordless shell calls, paired reasoning headers, two helpers, an allowed command; a second turn at work.",
    expect: "Each row says what the agent did, each thought on its own row; no wide gaps; the head and working line in the app's type.",
    saw: JSON.stringify(seen), verdict: bad.length ? "FAIL" : "PASS" });
  assert.deepEqual(bad, [], `rows that say a program, not what it did: ${JSON.stringify(seen.rows)}`);
  assert.ok(seen.rows.includes("Reviewing the vendor mapping snapshots") && seen.rows.includes("Planning the history roll-up"), `each thought its own row: ${JSON.stringify(seen.rows)}`);
  for (const h of seen.heads) assert.ok(!/mono|consolas/i.test(h.font) && h.case !== "uppercase", `the turn's head in the app's type: ${JSON.stringify(h)}`);
  assert.ok(seen.line && !/mono|consolas/i.test(seen.line.font), `the working line in the app's type: ${JSON.stringify(seen.line)}`);
  assert.deepEqual(errors, []);
});
