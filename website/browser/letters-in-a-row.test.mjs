import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A FEW LETTERS IN A ROW, AND A TURN THAT OWNS WHAT IT SHOWS (design round 5, I3 + I4). The stand-in agent writes three caterer emails in ONE
   call (`items`) and ends saying what is left to him. Seen: each email stands alone with "1 of 3", never one bulk card; his Send brings the
   next one at once - no turn of "Thinking..." over a letter already written; the turn's head keeps one time from at work to done; "For you
   to do" stays on the turn that wrote it when he types again. Sampled every 100 ms and recorded. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", process.env.LETTERS_OUT || "letters-in-a-row");
const mcp = (name, args) => ({ path: "/api/mcp?task={task}", body: { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } } });
const CATERERS = ["harbor", "mill", "quay"].map((n) => ({ to: `events@${n}-catering.example`, subject: "Catering for 40 in March",
  text: `Hello - could you quote lunch for 40 on March 12? Alex` }));
const SUM = (on) => `[[TASKUARY-SUMMARY]]${JSON.stringify({ did: "Three emails set up.", about: "Catering for the offsite.", on_you: on })}[[/TASKUARY-SUMMARY]]`;
const SCRIPT = [
  { when: "also the menu", anywhere: true, first: `The menus are in each email already. ${SUM([])}`, wait: 1 },
  { when: "The owner pressed .* on what you set up", anywhere: true, first: `All three went out. ${SUM([])}`, wait: 1 },
  { when: "three caterers", anywhere: true, first: `Three caterer emails are set up. ${SUM(["Pick the date to hold with the caterer you like"])}`, wait: 2,
    post: [mcp("propose_email", { items: CATERERS })] },
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
  return { ...h, api, bin };
}

const look = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]"), vis = (e) => !!e && e.getBoundingClientRect().height > 0;
  const sends = [...(pane?.querySelectorAll("button") || [])].filter((b) => vis(b) && /^Send$/.test(b.innerText.trim()) && !b.disabled && /catering\.example/.test(b.closest("[data-tq-turn-cards], [data-tq-next-steps], .tq-aui-agent-body")?.innerText || ""));
  const to = (b) => { for (let e = b, i = 0; e && i < 10; e = e.parentElement, i++) { const m = /events@(\w+)-catering/.exec(e.innerText || ""); if (m) return m[1]; } return ""; };
  return { queue: [...(pane?.querySelectorAll("[data-tq-card-queue]") || [])].filter(vis).map((e) => e.innerText.trim()).join(" | "),
    bulk: !!pane?.querySelector("[data-tq-bulk-card]"), sends: sends.map(to),
    working: [...(pane?.querySelectorAll("[data-tq-turn='working'], [data-tq-turn='starting']") || [])].length,
    heads: [...(pane?.querySelectorAll("[data-tq-item^='t:'] [data-tq-ran]") || [])].map((e) => [e.closest("[data-tq-item]").dataset.tqItem, (/·\s*([^·]+?)\s*(·|$)/.exec(e.innerText) || [])[1] || ""]),
    onYou: [...(pane?.querySelectorAll("[data-tq-on-you]") || [])].map((e) => [e.closest("[data-tq-item]")?.dataset.tqItem, e.innerText.trim()]) };
});

test("a few letters stand one at a time, the next at once; a turn keeps its time and its For you to do", { timeout: 400000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 950 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await w.api("/api/fixture/outbox", {});
  const made = await w.api("/api/fixture/mail-task", { title: "Catering for the offsite" });
  await w.api(`/api/reviews/${made.reviewId}/decide`, { verb: "reject" });          // ...the fixture's own reply to Erin, said no to: only the three letters wait
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const box = await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const dir = path.join(out, "video"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir), seen = [];
  const sample = async (label, until, ms = 30000) => {
    const end = Date.now() + ms;
    for (;;) { const s = await look(page); const last = seen.at(-1);
      if (!last || JSON.stringify({ ...s }) !== JSON.stringify({ ...last.s })) seen.push({ at: rec.mark(), label, s });
      if (until(s) || Date.now() > end) return s; await new Promise((r) => setTimeout(r, 100)); }
  };
  await box.type("ask three caterers for a quote for 40"); await page.keyboard.press("Enter");
  const working = await sample("asked", (s) => s.working > 0 && s.heads.length);
  const first = await sample("set up", (s) => !s.working && s.sends.length > 0, 90000);
  // ...each Send: the next letter stands, sampled from the press
  const gaps = [];
  for (const n of [1, 2, 3]) {
    const t0 = rec.mark(); await page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((x) => /^Send$/.test(x.innerText.trim()) && !x.disabled && x.getBoundingClientRect().height > 0); b?.scrollIntoView({ block: "center" }); b?.click(); });
    const next = ["mill", "quay"][n - 1];
    const s = await sample(`sent ${n}`, (x) => n < 3 ? x.sends.length === 1 && x.sends[0] === next : !x.working && seen.some((y) => y.label === `sent ${n}` && y.s.working), n < 3 ? 15000 : 60000);
    gaps.push({ n, ms: rec.mark() - t0, thought: seen.filter((y) => y.label === `sent ${n}` && y.s.working).length > 0, queue: s.queue });
  }
  const before = await look(page);
  await box.type("also the menu please"); await page.keyboard.press("Enter");
  const after = await sample("typed", (s) => !s.working && s.heads.length > before.heads.length, 60000);
  await new Promise((r) => setTimeout(r, 1500)); seen.push({ at: rec.mark(), label: "end", s: await look(page) });
  await rec.stop();
  await writeFile(path.join(dir, "states.json"), JSON.stringify(seen, null, 1));
  const sent = (await readFile(path.join(w.home, "outbox.jsonl"), "utf8").catch(() => "")).trim().split("\n").filter(Boolean).length;
  const headOf = (s, id) => (s.heads.find(([k]) => k === id) || [])[1];
  const t1 = working.heads.at(-1)?.[0], moved = seen.filter((x) => headOf(x.s, t1) && headOf(x.s, t1) !== headOf(working, t1));
  const keptOnYou = before.onYou.length && before.onYou.every(([k, w]) => after.onYou.some(([k2, w2]) => k2 === k && w2 === w));
  const verdict = !first.bulk && first.queue.startsWith("1 of 3") && gaps.slice(0, 2).every((g) => !g.thought && g.ms < 3000) && sent === 3 && !moved.length && keptOnYou;
  await note(dir, { done: "Three caterer emails raised in one call; the owner sends each; then types again.",
    expect: "1 of 3 on the first, no bulk card; each next email stands at once after a Send with no Thinking turn between; the first turn's head time never changes; For you to do stays on the turn that wrote it.",
    saw: JSON.stringify({ first, gaps, sent, moved: moved.slice(0, 3), before: before.onYou, after: after.onYou }), verdict: verdict ? "PASS" : "FAIL" });
  assert.ok(!first.bulk, "a few letters are never one bulk card"); assert.match(first.queue, /^1 of 3/);
  for (const g of gaps.slice(0, 2)) { assert.ok(!g.thought, `a Thinking turn stood between letters: ${JSON.stringify(gaps)}`); assert.ok(g.ms < 3000, JSON.stringify(gaps)); }
  assert.equal(sent, 3);
  assert.deepEqual(moved.map((x) => headOf(x.s, t1)), [], `the turn's head time changed: ${headOf(working, t1)}`);
  assert.ok(keptOnYou, `For you to do moved: ${JSON.stringify({ before: before.onYou, after: after.onYou })}`);
  assert.deepEqual(errors, []);
});
