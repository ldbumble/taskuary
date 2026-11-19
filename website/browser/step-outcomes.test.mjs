import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A TURN'S STEPS ARE WHAT IT DID, AND A TOOL'S ERROR IS THE AGENT'S (design round 5, 2026-11-19, three walks): after a press the chat drew a
   tool's refusal whole - "⚠ ``` `item` was not given Next: call tick again ... The input schema is: {...} select:mcp__taskuary__tick" - and
   step rows read "Running function Inspect-VendorForm", "Ran foreach (2 times)", "Using Load skill: dataviz", "Looked for files matching
   (a sync glob)". The stand-in claude plays a mail task's turn in those shapes: a skill loaded, a glob, a PowerShell function and foreach over
   the browser, a tick its CLI refused for a missing argument and retried. Shot with the work fold open, and recorded. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "step-outcomes", process.env.STEP_OUTCOMES_SHOT || "now");

const SCHEMA = "```\n`item` was not given\nNext: call tick again with it - find_tools tick has its whole instructions\n```\nThis tool's input schema was not in "
  + "your prompt when you called it. The input schema is: {\"type\":\"object\",\"properties\":{\"item\":{\"type\":\"string\"}},\"required\":[\"item\"]} "
  + "If the corrected call fails the same way, call ToolSearch with query \"select:mcp__taskuary__tick\" to load the tool, then call it again.";
const SCRIPT = [
  { when: "sync", anywhere: true, first: "The ledger sync finished last night at 2:10am; nothing failed.", steps: [
    { tool: "Skill", input: { skill: "dataviz" } },
    { tool: "Glob", input: { pattern: "**/*sync*" } },
    { tool: "PowerShell", input: { command: "function Inspect-VendorForm {\n  $landing = agent-browser snapshot -i -c\n  $landing | Write-Output\n}\n"
      + "foreach ($vendorTab in @('t2','t3')) {\n  agent-browser tab $vendorTab\n  if ($LASTEXITCODE -eq 0) { Inspect-VendorForm }\n}" } },
    { tool: "PowerShell", input: { command: "$vendorRefs = 3..5; foreach ($vendorRef in $vendorRefs) { agent-browser get attr \"@e$vendorRef\" href }" } },
    { tool: "mcp__taskuary__tick", input: {}, error: SCHEMA },
    { tool: "mcp__taskuary__tick", input: { item: "1" } },
  ] },
];

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py"), cli = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(cli, win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(cli, 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.5" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = async (p, body, method = body ? "POST" : "GET") => {
    const r = await fetch(`${h.fixtureApi}${p}`, { method, headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) });
    assert.ok(r.ok, `Fixture request failed: ${p}, ${r.status}`);
    return r.json();
  };
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// every row of the turn's open fold, as drawn, and every word of the chat
const look = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]");
  const rows = [...pane.querySelectorAll(".tq-aui-step")].map((e) => (e.querySelector("summary, .tq-aui-step-line")?.innerText || e.innerText || "").trim().split("\n")[0]);
  return { rows, text: pane.innerText };
});

test("a turn's steps read as outcomes, and a tool's refusal reaches the agent only", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1400, height: 1000 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", { title: "Erin asks about the ledger sync" });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const input = "[data-tq-task-page] [data-tq-agent-room] .tq-aui-input";
  await page.waitForSelector(input, { visible: true, timeout: 60000 });
  await page.waitForFunction((s) => !document.querySelector(s)?.disabled, { timeout: 60000 }, input);
  await mkdir(out, { recursive: true });
  const rec = await record(page, out);
  await page.evaluate((s) => document.querySelector(s)?.focus(), input);
  await page.keyboard.type("did the ledger sync finish?"); await page.keyboard.press("Enter");
  const dump = async (e) => { await page.screenshot({ path: path.join(out, "stuck.png") }); throw new Error(`${e.message}\n${w.log().split("\n").filter((l) => !/GET \/api/.test(l)).slice(-50).join("\n")}`); };
  await page.waitForFunction(() => /finished last night/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 90000 }).catch(dump);
  await new Promise((r) => setTimeout(r, 2500));
  // ...every step, at the chat's fullest detail, its work fold open
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => /^Everything$/.test(b.innerText.trim()))?.click());
  await new Promise((r) => setTimeout(r, 500));
  await page.evaluate(() => document.querySelectorAll("[data-tq-task-page] .tq-aui-agent details:not([open]) > summary").forEach((s) => s.click()));
  await new Promise((r) => setTimeout(r, 800));
  const seen = await look(page);
  await page.screenshot({ path: path.join(out, "turn.png") });
  await rec.stop();
  await writeFile(path.join(out, "seen.json"), JSON.stringify(seen, null, 1));
  const bad = seen.rows.filter((r) => /function|foreach|skill|matching '|tick|Used /i.test(r));
  const leak = /input schema|select:mcp|was not given|```/.test(seen.text);
  await note(out, { done: "A mail task's turn: a skill loaded, a glob, a PowerShell function and foreach over the browser, a tick refused for a missing argument, then retried.",
    expect: "Each row says what was done; no schema dump, no tool or skill name, no glob syntax anywhere in the chat.",
    saw: JSON.stringify(seen.rows), verdict: bad.length || leak ? "FAIL" : "PASS" });
  assert.deepEqual(bad, [], `rows that name machinery, not what was done: ${JSON.stringify(seen.rows)}`);
  assert.ok(!leak, `a tool's refusal reached the chat: ${seen.text.slice(0, 1500)}`);
  assert.deepEqual(errors, []);
});
