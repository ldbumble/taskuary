import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* WHAT HE SEES (design round 4, H6 - three walks, 2026-11-19). One task, one stand-in Claude turn in the shapes the walks met: a command that
   failed with a PATH dump, a look-up of Taskuary's own tool list, a code search by regex, an answer that names another task by a link, then two
   emails in a row. He presses Send on the first and keeps the mouse still: the second card draws where his press landed, and he presses again a
   beat later - that press must not send a letter he never read. The counter over the card, the Chat detail menu typed through, a routine card
   kept in words, and the task at a narrow window (~760 px) are looked at and shot. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "what-he-sees", process.env.H6_SHOT || "now");
const GAIL = "gail@northwind.example", PAULA = "paula@vendor.example";
const mcp = (name, args) => ({ path: "/api/mcp?task={task}", body: { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } } });
const tool = (id, name, input, ms = 0) => ({ _sleep: ms / 1000, type: "assistant", message: { role: "assistant", content: [{ type: "tool_use", id, name, input }] } });
const result = (id, text, error, ms = 0) => ({ _sleep: ms / 1000, type: "user", message: { role: "user", content: [{ type: "tool_result", tool_use_id: id, content: text, is_error: error }] } });
const PATH_DUMP = `Exit code 127\nwhich: no python3 in (/c/Users/alex/bin:/mingw64/bin:/usr/local/bin:/usr/bin:/bin:/c/Windows/system32:/c/Windows:${"/c/Program Files/Tool/bin:".repeat(12)})`;
const SCRIPT = [
  { when: "on what you set up, and it went through", anywhere: true, first: "The first letter is out; the second waits for you.", wait: 0.3 },
  { when: "open the vendor portal", anywhere: true, first: "The portal wants a sign-in. [[TASKUARY-YOURTURN: sign in to the vendor portal]]" },
  { when: "keep it as a routine", anywhere: true, first: "The Monday summary is set up as a routine for your yes.",
    post: [mcp("propose", { action: "save_routine", title: "Monday vendor spend summary", cron: "0 8 * * 1", why: "sums the week's vendor spend export and lists the top five",
      script: "import json, sys\nrows = [json.loads(l) for l in sys.stdin]\ntotal = sum(float(r['amount']) for r in rows)\njson.dump([{'total': total}], sys.stdout)\n" })] },
  { when: "set up the two letters", anywhere: true, first: "Both letters are set up. I used the dates from [the vendor review](#task=1).",
    events: [tool("t1", "Bash", { command: "which python3" }, 300), result("t1", PATH_DUMP, true, 300),
      tool("t2", "mcp__taskuary__find_tools", { query: "propose_reply" }, 200), result("t2", "propose_reply: The reply to a person on this task", false, 200),
      tool("t3", "Grep", { pattern: "import.*spawn|def run\\(|capture_output" }, 200), result("t3", "spawn.py:12", false, 200)],
    post: [mcp("propose_email", { to: GAIL, subject: "Venue shortlist", text: "Hi Gail - the two venues we liked are below. Alex" }),
      mcp("propose_email", { to: PAULA, subject: "October spend", text: "Hi Paula - the October total is attached. Alex" })] },
];

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.5" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const PANE = "[data-tq-task-page]";
// the open fold's rows, the counter and its type, the answer's link words, the cards' lit Sends
const look = (page) => page.evaluate((pane) => {
  const p = document.querySelector(pane), css = (e) => e && getComputedStyle(e);
  const rows = [...p.querySelectorAll(".tq-aui-steps .tq-aui-step, .tq-aui-steps .tq-aui-note")].map((e) => (e.querySelector("summary, .tq-aui-step-line")?.innerText || e.innerText || "").trim());
  const q = p.querySelector("[data-tq-card-queue]");
  const links = [...p.querySelectorAll("[data-tq-task-link]")].map((a) => a.innerText.trim());
  const sends = [...p.querySelectorAll("button")].filter((b) => /^Send$/.test(b.innerText.trim()) && !b.disabled && b.getClientRects().length).length;
  return { rows, queue: q && { text: q.innerText.trim(), font: css(q).fontFamily, size: css(q).fontSize }, links, sends };
}, PANE);
const shot = (page, name) => page.screenshot({ path: path.join(out, `${name}.png`) });

test("what he sees: steps in words, a link by its words, the counter in the app's type, no press on a card drawn under it, a narrow window", { timeout: 600000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1400, height: 950 });
  await mkdir(out, { recursive: true });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const sent = await w.api("/api/fixture/outbox", {});
  const made = await w.api("/api/fixture/mail-task", {});
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const box = await page.waitForSelector(`${PANE} .tq-aui-input`, { visible: true, timeout: 60000 });
  const rec = await record(page, path.join(out, "video"));
  const findings = {};
  try {
    await box.type("set up the two letters"); await page.keyboard.press("Enter");
    await page.waitForSelector(`${PANE} [data-tq-card-queue]`, { visible: true, timeout: 90000 });
    await new Promise((r) => setTimeout(r, 1500));
    // ...the turn's work, opened
    await page.evaluate((pane) => document.querySelectorAll(`${pane} .tq-aui-working-fold > summary`).forEach((s) => s.click()), PANE);
    await new Promise((r) => setTimeout(r, 600));
    findings.before = await look(page); await shot(page, "1-steps-and-counter");
    findings.items = (await w.api(`/api/tasks/${made.taskId}/conversation`)).items?.filter((x) => x.kind === "turn").map((x) => x.steps);

    // THE PRESS, AND THE CARD DRAWN UNDER IT: Send on the first letter with a real mouse, the pointer kept still
    // ...the Send of the card the counter stands over: the first lit Send after it in the page's order
    const first = await page.evaluateHandle((pane) => { const q = document.querySelector(`${pane} [data-tq-card-queue]`);
      return [...document.querySelectorAll(`${pane} button`)].find((b) => /^Send$/.test(b.innerText.trim()) && !b.disabled && q && (q.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)); }, PANE);
    await first.evaluate((b) => b.scrollIntoView({ block: "center" })); await new Promise((r) => setTimeout(r, 400));
    const r = await first.evaluate((b) => { const x = b.getBoundingClientRect(); return { x: x.left + x.width / 2, y: x.top + x.height / 2 }; });
    await page.mouse.move(r.x, r.y); await page.mouse.click(r.x, r.y);
    // ...the next Send under that same point, the moment it is there - his second press of a double press
    const t0 = Date.now(); let under = false, pressedAfter = null;
    while (Date.now() - t0 < 60000) {
      under = await page.evaluate(({ x, y }) => { const b = document.elementFromPoint(x, y)?.closest("button");
        return !!b && /^Send$/.test(b.innerText.trim()) && !b.disabled && !b.closest("[data-tq-past]") && b.isConnected && b.dataset.h6seen !== "1"; }, r);
      if (under) { await new Promise((res) => setTimeout(res, 150)); pressedAfter = Date.now(); await page.mouse.click(r.x, r.y); break; }
      await page.evaluate(({ x, y }) => { const b = document.elementFromPoint(x, y)?.closest("button"); if (b) b.dataset.h6seen = "1"; }, r);
      await new Promise((res) => setTimeout(res, 50));
    }
    await new Promise((res) => setTimeout(res, 2500));
    const went = (await readFile(sent.outbox, "utf8").catch(() => "")).split("\n").filter(Boolean).map((l) => JSON.stringify(l));
    findings.press = { drawnUnder: under, waited: pressedAfter && pressedAfter - t0, toGail: went.filter((l) => l.includes("Gail") || l.includes(GAIL)).length,
      toPaula: went.filter((l) => l.includes(PAULA)).length };
    await shot(page, "2-after-the-second-press");

    // THE CHAT DETAIL MENU, TYPED THROUGH: words typed while it is open go on into the box
    await page.click(`${PANE} [data-tq-head-pop=chat-detail]`).catch(() => {});
    await page.waitForSelector("[data-tq-head-pop-body=chat-detail]", { visible: true, timeout: 5000 }).catch(() => {});
    await page.keyboard.type("hello there");
    await new Promise((res) => setTimeout(res, 800));
    findings.menu = await page.evaluate((pane) => ({ box: document.querySelector(`${pane} .tq-aui-input`)?.value || "", open: !!document.querySelector("[data-tq-head-pop-body=chat-detail]") }), PANE);
    if (findings.menu.open) await page.keyboard.press("Escape");          // ...the old page kept it open over the box
    await new Promise((res) => setTimeout(res, 400));
    await page.evaluate((pane) => { const b = document.querySelector(`${pane} .tq-aui-input`); if (b) { b.focus(); b.select(); } }, PANE);
    await page.keyboard.press("Backspace");

    // A ROUTINE KEPT: what runs, when and where, in words - the script folded
    await page.focus(`${PANE} .tq-aui-input`); await page.keyboard.type("keep it as a routine"); await page.keyboard.press("Enter");
    await page.waitForFunction((pane) => /Monday vendor spend summary/.test(document.querySelector(pane)?.innerText || ""), { timeout: 90000 }, PANE).catch(() => {});
    await new Promise((res) => setTimeout(res, 2500));
    findings.routine = await page.evaluate((pane) => { const p = document.querySelector(pane), code = [...p.querySelectorAll("textarea, pre")].find((e) => /json\.dump/.test(e.value || e.innerText || ""));
      return { scriptShown: !!code && code.getClientRects().length > 0 && getComputedStyle(code).display !== "none", lead: [...p.querySelectorAll("[data-tq-held-lead]")].pop()?.innerText || "" }; }, PANE);
    await page.evaluate((pane) => [...document.querySelectorAll(`${pane} [data-tq-held-lead]`)].pop()?.scrollIntoView({ block: "center" }), PANE);
    await shot(page, "3-routine-card");

    // A NARROW WINDOW: the rail, the box's placeholder and the tabs at ~760 px - the agent's page handed to him beside the chat
    await w.api("/api/fixture/browser-page", { taskId: made.taskId });
    await page.setViewport({ width: 760, height: 900 }); await new Promise((res) => setTimeout(res, 800));
    await page.focus(`${PANE} .tq-aui-input`); await page.keyboard.type("open the vendor portal"); await page.keyboard.press("Enter");
    await page.waitForFunction((pane) => /sign in to the vendor portal|wants a sign-in/i.test(document.querySelector(pane)?.innerText || ""), { timeout: 60000 }, PANE).catch(() => {});
    await new Promise((res) => setTimeout(res, 4000));
    findings.narrow = await page.evaluate((pane) => {
      const p = document.querySelector(pane), input = p?.querySelector(".tq-aui-input"), cs = input && getComputedStyle(input);
      const lh = cs && parseFloat(cs.lineHeight) || 20;
      return { scrollX: document.documentElement.scrollWidth - innerWidth, paneW: Math.round(p?.getBoundingClientRect().width || 0),
        inputW: Math.round(input?.getBoundingClientRect().width || 0), inputLines: input ? Math.round(input.scrollHeight / lh) : 0 };
    }, PANE);
    await shot(page, "4-narrow-760");
  } finally {
    await rec.stop({ sheet: 12 });
    await writeFile(path.join(out, "findings.json"), JSON.stringify(findings, null, 1));
  }
  const bad = (findings.before?.rows || []).filter((s) => /```|Exit code|\(taskuary\)|find tools|\\\(|\|/.test(s));
  const ok = !bad.length && findings.before?.links.every((l) => !/TQ-\d+/.test(l)) && !/mono|consolas/i.test(findings.before?.queue?.font || "")
    && findings.press.toPaula + findings.press.toGail === 1 && /hello there/.test(findings.menu?.box || "") && !findings.routine?.scriptShown && findings.narrow?.inputW >= 120 && findings.narrow?.inputLines <= 2;
  await note(out, { done: "A turn with a failed command, a tool list look-up, a regex search and a task link; two letters in a row, Send pressed with the pointer kept still and pressed again when the next card drew under it; the Chat detail menu typed through; a routine card; the window cut to 760 px.",
    expect: "Steps in words, a failure one line; the link reads its words; the counter in the app's type; only the first letter goes; the words land in the box; the routine card in words with the script folded; the task usable at 760 px.",
    saw: JSON.stringify(findings), verdict: ok ? "PASS" : "FAIL" });
  assert.deepEqual(bad, [], `steps that read as a program's text: ${JSON.stringify(findings.before?.rows)}`);
  assert.ok(findings.before.links.length && findings.before.links.every((l) => !/TQ-\d+/.test(l)), `a task link reads its words: ${JSON.stringify(findings.before.links)}`);
  assert.ok(!/mono|consolas/i.test(findings.before.queue.font), `the counter in the app's type: ${JSON.stringify(findings.before.queue)}`);
  assert.equal(findings.press.toGail + findings.press.toPaula, 1, `one letter went: ${JSON.stringify(findings.press)}`);
  assert.match(findings.menu.box, /hello there/, JSON.stringify(findings.menu));
  assert.ok(!findings.routine.scriptShown && findings.routine.lead, JSON.stringify(findings.routine));
  assert.ok(findings.narrow.inputW >= 120 && findings.narrow.inputLines <= 2 && findings.narrow.scrollX <= 0, JSON.stringify(findings.narrow));
  // ...the failed command is its own row, its output behind it (a chat never says "failed" of a step - the owner, 2026-11-05)
  assert.equal(findings.before.rows[0], "Ran which python3");
  assert.deepEqual(errors, []);
});
