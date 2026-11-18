import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE DOTS GO WHEN THE TURN DOES (the owner, 2026-11-17: "the agent keeps saying 'Thinking...' even after it is done"). A task's agent is given a
   line and its turn ends one way or another - an answer, a tool that failed, a last step that is a thought, a card it raised, a stop, a CLI
   that died, a session idled out, a press, a restart. From the moment the server's own list says nothing works, the chat's working line
   (GeneralWorkspace ConvTurn, chatStream.workingLine) is gone within a beat and never comes back. Every state is sampled, and recorded.
   Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "thinking-after-done");
const ONLY = process.env.TAD_ONLY ? new RegExp(process.env.TAD_ONLY) : null;

const SCRIPT = [
  { when: "tool that fails", anywhere: true, first: "The ledger script failed, so I stopped there.", steps: [{ tool: "Bash", input: { command: "python totals.py" }, error: "Traceback: totals.py not found" }] },
  { when: "end on a thought", anywhere: true, first: "", steps: [{ tool: "Read", input: { file_path: "notes.md" } }, { thought: "Erin only asked for the date, so nothing more is owed." }] },
  { when: "take your time", anywhere: true, first: "Done after a while.", wait: 30 },
  { when: "die now", anywhere: true, exit: 1 },
  { when: "wrap up slowly", anywhere: true, first: "Thursday is free all day.", steps: [{ tool: "Read", input: { file_path: "calendar.ics" } }], tail: 6 },
  { when: "draft a reply", anywhere: true, first: "Drafted the reply for your Send.",
    post: [{ path: "/api/agent/reply", body: { text: "Hi Erin, Thursday works. Alex", agent: "assistant" } }] },
];

async function world(t, env = {}) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const py = execFileSync("python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, "claude"), `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SCRIPT: path.join(bin, "script.json"),
    FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1.5", FAKE_ACP_THINK: "1.5", FAKE_CLAUDE_LOG: path.join(bin, "log.jsonl"), FAKE_CLAUDE_CHROME: "1", FAKE_ACP_ASK: "git push origin main", ...env });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const say = async (page, words) => {
  const sel = "[data-tq-task-page] [data-tq-agent-room] .tq-aui-input";
  await page.waitForSelector(sel, { visible: true, timeout: 60000 });
  await page.waitForFunction((s) => !document.querySelector(s)?.disabled, { timeout: 60000 }, sel);
  await page.evaluate((s) => document.querySelector(s)?.focus(), sel);
  await page.keyboard.type(words); await page.keyboard.press("Enter");
};

// THE WATCH: the page's working line and the server's word, side by side, every 150 ms. Started before the line goes in; `stop()` -> the samples
const watch = (page, tid) => page.evaluate((tid) => {
  const S = (window.__tad = { seen: [], on: true });
  const tok = localStorage.getItem("taskuary_token");
  let server = null;
  const ask = async () => { while (S.on) {
    try { const d = await (await fetch(`/api/tasks/${tid}/conversation`, { headers: { "X-Taskuary-Token": tok } })).json();
      const live = (d.items || []).filter((x) => x.kind === "turn" && ["starting", "working"].includes(x.state));
      server = { working: !!d.working, live: live.map((x) => x.id) }; } catch { /* a restart */ }
    await new Promise((r) => setTimeout(r, 250)); } };
  ask();
  const t0 = performance.now();
  const tick = () => { if (!S.on) return;
    try { look(); } catch (x) { S.seen.push({ at: Math.round(performance.now() - t0), line: `watch error: ${x.message}`, sv: "" }); }
    setTimeout(tick, 100); };
  const look = () => {
    const pane = document.querySelector("[data-tq-task-page]"), w = pane?.querySelectorAll("[data-tq-working]") || [];
    const line = [...w].map((e) => `${e.closest("[data-tq-item]")?.getAttribute("data-tq-item") || (e.closest("[data-tq-pending-turn]") ? "pending" : "?")}:${e.innerText.trim() || "dots"}`).join(" | ");
    const last = S.seen.at(-1), sv = server ? `${server.working ? "W" : "-"}${server.live.length}` : "?";
    if (!last || last.line !== line || last.sv !== sv) S.seen.push({ at: Math.round(performance.now() - t0), line, sv }); };
  tick();
}, tid);
const stopWatch = (page) => page.evaluate(() => { window.__tad.on = false; return window.__tad.seen; });
const now = (page) => page.evaluate(() => window.__tad.seen.at(-1));

// Waits until the server's list says nothing works, then 8 s more: the page's line must be gone within 2.5 s of that and stay gone
async function settle(page, { limit = 60000 } = {}) {
  const t0 = Date.now();
  // ...from the server's first word that it works (a line not yet taken reads at rest), up to 10 s; then until it says nothing works
  while (Date.now() - t0 < 10000 && !(await page.evaluate(() => window.__tad.seen.some((x) => x.sv.startsWith("W"))))) await new Promise((r) => setTimeout(r, 200));
  while (Date.now() - t0 < limit) { const s = await now(page); if (s?.sv === "-0") break; await new Promise((r) => setTimeout(r, 200)); }
  await new Promise((r) => setTimeout(r, 8000));
  return stopWatch(page);
}
const judge = (seen) => {
  const bad = [];
  if (seen.at(-1)?.sv !== "-0") bad.push(`the server still says at work at the end: ${seen.at(-1)?.sv}`);
  const quietAt = seen.findIndex((s, i) => s.sv === "-0" && seen.slice(i).every((x) => x.sv === "-0"));
  if (quietAt >= 0) {
    const from = seen[quietAt].at;
    for (const s of seen.slice(quietAt)) if (s.line && s.at - from > 2500) { bad.push(`${s.at - from} ms after the server went quiet the chat still says "${s.line}"`); break; }
  }
  return bad;
};

async function scenario(t, w, page, name, { kind = "general", line, before, during, after }) {
  if (ONLY && !ONLY.test(name)) return;
  const dir = path.join(out, name);
  await mkdir(dir, { recursive: true });
  const made = kind === "general" ? await w.api("/api/fixture/mail-task", { title: `Thursday for Erin (${name})` })
    : await w.api("/api/fixture/coding", { title: `Comment the totals (${name})`, ...(kind === "pty" ? { pty: true } : {}) });
  const tid = made.taskId;
  await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
  await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 60000 });
  if (before) await before({ tid, page });
  await new Promise((r) => setTimeout(r, 1500));
  const rec = await record(page, dir);
  await watch(page, tid);
  await say(page, line);
  if (during) await during({ tid, page });
  const seen = await settle(page);
  if (after) { await watch(page, tid); await after({ tid, page }); seen.push({ at: -1, line: "-- after --", sv: "" }, ...(await settle(page))); }
  await rec.stop();
  // ...its session ended, so the next scenario's agent is never one too many (a full house is a road of its own)
  await w.api("/api/fixture/session", { taskId: tid, state: "ended" }).catch(() => {});
  await writeFile(path.join(dir, "seen.json"), JSON.stringify(seen, null, 1));
  await writeFile(path.join(dir, "server.log"), w.log());
  const tail = seen.slice(seen.findIndex((x) => x.line === "-- after --") + 1);
  const bad = [...judge(after ? seen.slice(0, seen.findIndex((x) => x.line === "-- after --")) : seen), ...(after ? judge(tail) : [])];
  await note(dir, { done: `${kind}: the owner types "${line}" and the turn ends (${name}).`, expect: "The working line goes within a beat of the server's quiet, and stays gone.",
    saw: JSON.stringify(seen), verdict: bad.length ? "FAIL" : "PASS" });
  return bad.map((b) => `${name}: ${b}`);
}

test("the working line goes when the turn has ended, for every agent and every way a turn ends", { timeout: 1800000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1500, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const bad = [];
  const run = async (name, o) => { const b = await scenario(t, w, page, name, o); if (b?.length) { bad.push(...b); console.log("FINDING", b.join("\n")); } else if (b) console.log("ok", name); };
  await run("chat-answer", { line: "is Thursday free?" });
  await run("chat-words-then-wrap-up", { line: "check Thursday and wrap up slowly" });
  await run("chat-tool-error", { line: "run the tool that fails" });
  await run("chat-thought-last", { line: "read the notes and end on a thought" });
  await run("chat-card", { line: "draft a reply saying Thursday" });
  await run("chat-died", { line: "die now please" });
  await run("chat-stop", { line: "take your time with it", during: async ({ page }) => {
    await page.waitForSelector("[data-tq-stop-run]", { visible: true, timeout: 30000 }); await new Promise((r) => setTimeout(r, 2500)); await page.click("[data-tq-stop-run]"); } });
  await run("chat-idled", { line: "is Friday free?", after: async ({ tid }) => { await w.api("/api/fixture/session", { taskId: tid, state: "idled" }); } });
  await run("chat-woken", { line: "is Monday free?", after: async ({ tid }) => { await w.api("/api/fixture/session", { taskId: tid, state: "woken", why: "the rest of it" }); } });
  await run("chat-restart-mid", { line: "take your time again", during: async () => { await new Promise((r) => setTimeout(r, 5000)); await w.restart(); } });
  await run("acp-answer", { kind: "acp", line: "comment the totals" });
  await run("acp-stop", { kind: "acp", line: "take your time on the totals", during: async ({ page }) => {
    await page.waitForSelector("[data-tq-stop-run]", { visible: true, timeout: 60000 }); await new Promise((r) => setTimeout(r, 2500)); await page.click("[data-tq-stop-run]"); } });
  await run("acp-tool-error", { kind: "acp", line: "run the tool that fails" });
  await run("acp-thought-last", { kind: "acp", line: "read the notes and end on a thought" });
  await run("acp-card", { kind: "acp", line: "draft a reply saying Thursday" });
  // ...its turn stops at a step it asks to run, and his Allow once lets it on to the end
  await run("acp-allow", { kind: "acp", line: "look at the ledger", after: async ({ page, tid }) => {
    const b = await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] button")].find((x) => /^(Allow once|Approve|Push|Allow)/.test(x.innerText.trim()) && !x.disabled), { timeout: 30000 })
      .catch(async (e) => { const c = await w.api(`/api/tasks/${tid}/conversation`);
        throw new Error(`${e.message}: ${JSON.stringify({ working: c.working, items: c.items, permissions: c.permissions, asking: c.asking }).slice(0, 3000)}\n${w.log().split("\n").filter((l) => !/GET \/api|TASKUARY_PORT/.test(l)).slice(-30).join("\n")}`); });
    await b.asElement().click(); } });
  // ...a second line while the first turn works: kept, then its own turn
  await run("chat-second-line", { line: "take your time with the second", during: async ({ page }) => {
    await new Promise((r) => setTimeout(r, 3000)); await say(page, "and is Tuesday free?"); } });
  // ...the card it raised, pressed: the letter goes and the agent hears it
  await run("chat-press", { line: "draft a reply for Erin", after: async ({ page }) => {
    await w.api("/api/fixture/outbox", {});
    const b = await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] [data-tq-review] button")].find((x) => x.innerText.trim() === "Send" && !x.disabled), { timeout: 30000 });
    await b.asElement().click(); } });
  // ...the server restarted after the turn had ended, and the page read again
  await run("chat-restart-after", { line: "is Wednesday free?", after: async ({ page, tid }) => { await w.restart(); await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room]", { timeout: 60000 }); await watch(page, tid); } });
  await run("acp-restart-mid", { kind: "acp", line: "take your time on the ledger", during: async () => { await new Promise((r) => setTimeout(r, 4000)); await w.restart(); } });
  // ...the page read again while its turn works, and again once it has answered
  await run("chat-reload-mid", { line: "take your time and reload", during: async ({ page, tid }) => {
    await new Promise((r) => setTimeout(r, 3000)); await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room]", { timeout: 60000 }); await watch(page, tid); } });
  // ...and the terminal road last but one: the fixture switches the home's coding agents to it (agents.ACP_SETTING)
  await run("pty-answer", { kind: "pty", line: "comment the totals in the terminal" });
  // ...last: an adapter that died mid-turn sends the coding tasks after it to their CLI's terminal (acpcoding.FELL_BACK)
  await run("acp-died", { kind: "acp", line: "die now please" });
  assert.deepEqual(errors, []);
  assert.deepEqual(bad, []);
});
