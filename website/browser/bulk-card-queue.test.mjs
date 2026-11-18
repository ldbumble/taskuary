import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A BULK CARD IN THE LINE OF CARDS (taskuary/bulkcard.py, cardqueue.py; the owner, 2026-11-16). He asks for thirty letters; the stand-in agent
   raises them as ONE card and a note to Gail behind it. The line reads "1 of 2 · next: the email to Gail"; he presses Send 30 emails; the bar
   counts in the card; the note to Gail stands only once the turn that heard the run has answered - never before. Sampled every 100 ms and
   recorded. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "bulk-queue");
const N = 30, GAIL = "gail@northwind.example";
const mcp = (name, args) => ({ path: "/api/mcp?task={task}", body: { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } } });
const letters = Array.from({ length: N }, (_, i) => ({ to: `owner${i}@cedar.example`, subject: `About ${100 + i} Market St`, text: `Hello - about ${100 + i} Market St. Alex` }));
const SCRIPT = [
  { when: "pressed the bulk card", anywhere: true, first: "All thirty went out; the note to Gail is next.", wait: 3 },
  { when: "send the market street letters", anywhere: true, first: "Set up: the letters, then a note to Gail.",
    post: [mcp("propose_email", { items: letters }), mcp("propose_email", { to: GAIL, subject: "Letters out", text: "Gail - the Market St letters went out. Alex" })] },
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
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1", FAKE_CLAUDE_LOG: path.join(bin, "log.jsonl") });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const look = (page) => page.evaluate((gail) => {
  const ticks = document.querySelectorAll("[data-tq-task-page] [data-tq-bulk-card] [data-tq-bulk-row]").length ? [...document.querySelectorAll("[data-tq-task-page] [data-tq-bulk-card] [data-tq-bulk-row]")].filter((e) => e.innerText.includes("✓")).length : 0;
  const pane = document.querySelector("[data-tq-task-page]");
  const bulk = pane?.querySelector("[data-tq-bulk-card]"), bar = bulk?.querySelector("[data-tq-bulk-progress]");
  const press = bulk?.querySelector("[data-tq-bulk-press]"), stop = bulk?.querySelector("[data-tq-bulk-stop]");
  const vis = (e) => !!e && e.getBoundingClientRect().height > 0;
  // ...a lit Send outside the bulk card, on a card that names Gail (the letter's own block carries no review mark)
  const near = (b) => { for (let e = b, i = 0; e && i < 8; e = e.parentElement, i++) if (e.innerText.includes(gail)) return true; return false; };
  const gailCard = [...(pane?.querySelectorAll("button") || [])].some((b) => vis(b) && /^Send$/.test(b.innerText.trim()) && !b.disabled && !b.closest("[data-tq-bulk-card]") && near(b));
  return { bulk: vis(bulk), bar: bar?.innerText.replace(/\s+/g, " ").trim() || "", press: press ? `${press.innerText.trim()}${press.disabled ? "(off)" : ""}` : "",
    stop: vis(stop), ticks, queue: [...(pane?.querySelectorAll("[data-tq-card-queue]") || [])].filter(vis).map((e) => e.innerText.trim()).join(" | "), gail: gailCard,
    answered: (pane?.innerText || "").includes("All thirty went out") };
}, GAIL);

test("a bulk card in the line: the bar counts, and the card behind stands only after the turn that heard the run", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await w.api("/api/fixture/outbox", { delay: 0.1 });      // ...a run of a few seconds, as a real mailbox takes
  const made = await w.api("/api/fixture/mail-task", {});
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const box = await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  await box.type("send the market street letters to every owner"); await page.keyboard.press("Enter");
  await page.waitForSelector("[data-tq-task-page] [data-tq-bulk-press]", { visible: true, timeout: 90000 });
  await new Promise((r) => setTimeout(r, 2500));
  const dir = path.join(out, "video", "press"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  const t0 = await look(page);
  await page.click("[data-tq-task-page] [data-tq-bulk-press]");
  const seen = [t0];
  for (let i = 0; i < 600; i++) {
    const s = await look(page), last = seen.at(-1);
    if (JSON.stringify({ ...s }) !== JSON.stringify({ ...last })) seen.push({ ...s, at: i * 100 });
    if (s.gail && s.answered) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  await new Promise((r) => setTimeout(r, 1500)); seen.push({ ...(await look(page)), at: "end" });
  await rec.stop();
  await writeFile(path.join(dir, "states.json"), JSON.stringify(seen, null, 1));
  const early = seen.filter((s) => s.gail && !s.answered);
  const bars = seen.map((s) => +(/^(\d+) of/.exec(s.bar) || [])[1]).filter((n) => !Number.isNaN(n)), back = bars.findIndex((n, i) => i && n < bars[i - 1]);
  // ...the bar counts what the rows show: never "0 of 30" over rows already ticked (recorded before BulkCard read its run as the rows changed)
  // ...past the one read in flight as the rows change (a round trip): a lag a beat long was a second long, the bar's own poll
  const lags = (s) => typeof s.at === "number" && (+(/^(\d+) of/.exec(s.bar) || [])[1] || 0) < s.ticks, behind = [];
  for (let i = 0, from = null; i < seen.length; i++) {
    if (lags(seen[i])) { from ??= seen[i].at; continue; }
    if (from != null && typeof seen[i].at === "number" && seen[i].at - from > 250) behind.push({ from, to: seen[i].at, bar: seen[i - 1].bar, ticks: seen[i - 1].ticks });
    from = null;
  }
  const verdict = !behind.length && t0.queue.includes(`1 of 2 · next: the email to ${GAIL}`) && !early.length && back < 0 && seen.at(-1).gail && seen.at(-1).bar.startsWith(`${N} of ${N}`);
  await note(dir, { done: `A bulk card of ${N} emails with a note to Gail behind it; the owner presses Send ${N} emails.`,
    expect: `The line reads 1 of 2; the bar counts up to ${N} of ${N}; the note to Gail stands only after the agent's answer to the run.`, saw: JSON.stringify(seen), verdict: verdict ? "PASS" : "FAIL" });
  assert.match(t0.queue, new RegExp(`1 of 2 · next: the email to ${GAIL}`), JSON.stringify(t0));
  assert.equal(t0.press, `Send ${N} emails`);
  assert.deepEqual(early, [], `the note to Gail stood before the turn that heard the run: ${JSON.stringify(seen)}`);
  assert.deepEqual(behind, [], `the bar counted fewer than the rows already ticked: ${JSON.stringify(behind)}`);
  assert.equal(back, -1, `the bar went backwards: ${bars}`);
  assert.ok(seen.at(-1).gail && seen.at(-1).bar.startsWith(`${N} of ${N}`), JSON.stringify(seen.at(-1)));
  assert.deepEqual(errors, []);
});
