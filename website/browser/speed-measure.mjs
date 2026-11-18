// SPEED MEASURING HARNESS (workstream 7). Not a pass/fail test: it prints numbers a person compares before and after a change, and
// writes them to $SPEED_OUT (default: stdout only). Run it through the browser slot limiter:
//   cd website && TASKUARY_BROWSER_EXECUTABLE=... PYTHONPATH=<repo> node browser/speed-measure.mjs
// What it measures, on a stand-in CLI (tests/fake_claude.py) and a real server with SEED_TASKS invented tasks (default 300):
//   (a) Enter -> his line on screen -> the working line on screen
//   (b) the agent's first word / last word written (fake CLI log clock) -> that word on screen
//   (c) every HTTP request the open task makes: on opening it, 30 s idle, 30 s of a turn at work - count, bytes, duplicates, unchanged answers
//   (d) bytes the agent is sent on turn 1, 2 and 10 of one task (FAKE_CLAUDE_LOG_PROMPT keeps each prompt)
//   (e) server time per polled endpoint, with the seeded store and a long chat
// Invented people only. REPEATS (default 3) runs; medians are reported.
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

import { startHarness } from "./harness.mjs";

const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const REPEATS = +(process.env.REPEATS || 3), SEED = +(process.env.SEED_TASKS || 300), WINDOW = +(process.env.WINDOW_S || 30), TURNS = +(process.env.TURNS || 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const median = (xs) => { const s = xs.filter((x) => x != null).sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
const lines = [];
const say = (s = "") => { lines.push(s); console.log(s); };

const SLOW = "hold on a moment please";
const WORDS = "Gail's renewal terms are settled for Thursday; the sheet lists two open flaws, export and sso, each with an owner and a date. ".repeat(4);
const SCRIPT = [
  { when: SLOW, anywhere: true, first: "Done waiting.", wait: WINDOW + 2 },
  { when: "ping", anywhere: true, first: WORDS },
];

async function world() {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, "claude"), `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  const log = path.join(bin, "log.jsonl");
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SCRIPT: path.join(bin, "script.json"),
    FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.7", FAKE_CLAUDE_LOG: log, FAKE_CLAUDE_LOG_PROMPT: "1" });
  const h = await startHarness({ fresh: true, bin });
  const api = (p, body, method = body ? "POST" : "GET") => fetch(`${h.fixtureApi}${p}`, { method,
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api, log, close: async () => { await h.close(); await rm(bin, { recursive: true, force: true }).catch(() => {}); } };
}

// every request the page makes, with its answer's size and a hash of the body, so "asked again, got the same bytes" can be counted
function watch(page) {
  const seen = [];
  page.on("response", async (res) => {
    const u = new URL(res.url()); if (!u.pathname.startsWith("/api/")) return;
    let bytes = 0, hash = "";
    try { const b = await res.buffer(); if (process.env.DUMP_BODIES && /\/api\/tasks\/\d+(\/assistant)?$/.test(u.pathname)) (globalThis.__bodies ||= []).push([u.pathname, Date.now(), b.toString()]); bytes = b.length; hash = createHash("sha1").update(b).digest("hex").slice(0, 10); } catch { /* streams */ }
    if (watch.marker && !watch.hit && hash && res.request().method() === "GET" && (await res.text().catch(() => "")).includes(watch.marker)) watch.hit = { at: Date.now(), key: u.pathname };
    seen.push({ at: Date.now(), m: res.request().method(), key: u.pathname.replace(/\/\d+(?=\/|$)/g, "/N") + u.search, bytes, hash, ms: null });
  });
  return { seen, mark: () => seen.length, since: (i) => seen.slice(i) };
}
function tally(reqs) {
  const by = new Map();
  for (const r of reqs) { const k = `${r.m} ${r.key}`, e = by.get(k) || { n: 0, bytes: 0, same: 0, hashes: new Set(), last: null }; e.n++; e.bytes += r.bytes;
    if (e.last === r.hash) e.same++; e.last = r.hash; by.set(k, e); }
  const rows = [...by.entries()].sort((a, b) => b[1].bytes - a[1].bytes);
  return { n: reqs.length, bytes: reqs.reduce((s, r) => s + r.bytes, 0), unchanged: rows.reduce((s, [, e]) => s + e.same, 0), rows };
}
const show = (title, reqs, secs) => {
  const t = tally(reqs); say(`  ${title}: ${t.n} requests, ${t.bytes} bytes, ${t.unchanged} answered the same bytes as the last ask${secs ? ` (${(t.n / secs).toFixed(2)}/s)` : ""}`);
  for (const [k, e] of t.rows.slice(0, 12)) say(`      ${String(e.n).padStart(3)}x ${String(e.bytes).padStart(8)} B  same ${String(e.same).padStart(3)}  ${k}`);
  return t;
};

async function events(path_) { try { return (await readFile(path_, "utf8")).trim().split("\n").map((l) => JSON.parse(l)); } catch { return []; } }

async function once(i) {
  const w = await world();
  const out = { i };
  try {
    // (e) a store of SEED invented tasks, before the page opens
    for (let k = 0; k < SEED; k++) await w.api("/api/tasks", { Title: `Invented task ${k}: renew the Northwind vendor sheet`, Summary: `Erin Blake asked about item ${k}`, Kind: "human" });
    // ...a real store is mostly finished work: four in five of the invented tasks are closed, so the rail holds the open fifth
    const rows = (await w.api("/api/tasks")).data || [];
    for (const r of rows.filter((_, k) => k % 5)) await w.api(`/api/tasks/${r.TaskId}`, { Status: "done" }, "PATCH");
    const made = await w.api("/api/fixture/mail-task", {});
    const tid = made.taskId;
    const page = await w.newPage();
    await page.setViewport({ width: 1600, height: 900 });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(w.ui, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
    await sleep(2500);
    const net = watch(page);
    // (c1) opening the task
    const m0 = net.mark(), openAt = Date.now();
    await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
    await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
    await sleep(3000);
    out.open = net.since(m0); out.openMs = Date.now() - openAt;
    // the page's own clock: a MutationObserver stamps the first time a text, then a working line, are in the document
    await page.evaluate(() => {
      window.__first = {}; const stamp = (k) => { if (!(k in window.__first)) window.__first[k] = Date.now(); };
      window.__marks = { line: null, words: [] };
      const look = () => { const t = document.querySelector("[data-tq-task-page]")?.innerText || "";
        if (window.__marks.line && t.includes(window.__marks.line)) stamp("line");
        if (window.__marks.line && document.querySelector("[data-tq-task-page] [data-tq-run-clock], [data-tq-task-page] [data-tq-starting-line], [data-tq-task-page] [data-tq-pending-turn]")) stamp("working");
        for (const w of window.__marks.words) if (t.includes(w)) stamp("word:" + w); };
      new MutationObserver(look).observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    const say_ = async (text, marks) => {
      await page.evaluate((text, marks) => { window.__first = {}; window.__marks = { line: text, words: marks }; }, text, marks);
      await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
      await page.keyboard.type(text);
      const t0 = Date.now(); await page.keyboard.press("Enter"); return t0;
    };
    // (a)+(b) turn 1: Enter -> his line -> working line; the agent's first and last word on screen vs written
    const wordHead = WORDS.slice(0, 18), wordTail = WORDS.slice(-24);
    const evBefore = (await events(w.log)).length;
    watch.marker = wordTail; watch.hit = null;
    // ...the server's own side of the hop: the answer read from the API directly every 40 ms, no page between
    let apiAt = null, t0 = Date.now(); const apiLoop = (async () => { while (!apiAt && Date.now() < Date.now() + 60000) { try { const r = await fetch(`${w.fixtureApi}/api/tasks/${tid}/conversation`, { headers: { "X-Taskuary-Token": w.token } }); if ((await r.text()).includes(wordTail)) apiAt = Date.now(); } catch { /* next */ } await sleep(40); if (Date.now() - t0 > 60000) break; } })();
    t0 = await say_("ping the vendor sheet", [wordHead, wordTail]);
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) { const f = await page.evaluate(() => window.__first); if (f["word:" + wordTail]) break; await sleep(25); }
    const f = await page.evaluate(() => window.__first), ev = (await events(w.log)).slice(evBefore);
    // ...the AGENT's own process: the one handed the owner's line (the rest are side calls - a probe, a memory pick, a summary)
    const got = ev.find((e) => e.ev === "turn" && (e.prompt || "").includes("ping the vendor sheet") && (e.prompt || "").includes("TASK TQ-")), agentPid = got && got.pid;
    const tok = ev.find((e) => e.ev === "first_token" && e.pid === agentPid), res = ev.find((e) => e.ev === "result" && e.pid === agentPid);
    if (process.env.SERVER_LOG) await writeFile(process.env.SERVER_LOG, w.backend.output());
    await sleep(200); out.hops = { agentHandedPrompt: got && got.t * 1000 - t0, cliWrote: res && res.t * 1000 - t0, apiHas: apiAt && apiAt - t0, pageFetched: watch.hit && watch.hit.at - t0, pageFetchedBy: watch.hit && watch.hit.key, onScreen: f["word:" + wordTail] && f["word:" + wordTail] - t0 };
    out.a = { line: f.line && f.line - t0, working: f.working && f.working - t0 };
    out.b = { firstWord: f["word:" + wordHead] && tok && f["word:" + wordHead] - tok.t * 1000, lastWord: f["word:" + wordTail] && res && f["word:" + wordTail] - res.t * 1000 };
    await sleep(2500);
    // (c2) 30 s idle on the open task
    const idle0 = net.mark(); await sleep(WINDOW * 1000); out.idle = net.since(idle0);
    // (c3) 30 s of a turn at work
    const run0 = net.mark();
    await say_(SLOW, []);
    await sleep(WINDOW * 1000); out.turn = net.since(run0);
    const end = Date.now() + 15000; while (Date.now() < end && !(await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText.includes("Done waiting")))) await sleep(200);
    // (d) turns 3..TURNS, each a quick ping, then read what the agent was handed
    for (let k = 3; k <= TURNS; k++) {
      const before = (await events(w.log)).filter((e) => e.ev === "result").length;
      await say_(`ping number ${k}`, []);
      const stop = Date.now() + 45000; while (Date.now() < stop && (await events(w.log)).filter((e) => e.ev === "result").length <= before) await sleep(150);
      await sleep(300);
    }
    const turns = (await events(w.log)).filter((e) => e.ev === "turn");
    // ...the agent's own process(es): the ones that were handed the owner's first line (a probe or a side call is another process)
    const mine = new Set(turns.filter((e) => (e.prompt || "").includes("ping the vendor sheet")).map((e) => e.pid));
    out.prompts = turns.filter((e) => mine.has(e.pid)).map((e, k) => ({ ...e, n: k + 1 })).map((e) => ({ n: e.n, pid: e.pid, chars: e.chars, text: e.prompt }));
    // (e) the polled endpoints, timed on the server with the seeded store and a long chat (this task now has TURNS turns)
    out.server = {};
    const paths = [["funnel/pile", `/api/funnel/pile?current=processing:x&fyi=50&force=1`], ["funnel/pile (poll)", `/api/funnel/pile`], ["task", `/api/tasks/${tid}`], ["conversation", `/api/tasks/${tid}/conversation`],
      ["conversation rev", `/api/tasks/${tid}/conversation?rev=zzz`], ["assistant", `/api/tasks/${tid}/assistant`], ["terminals", "/api/terminals?details=false"], ["concierge", "/api/concierge"], ["runs/live", "/api/runs/live?lines=4"], ["capabilities", "/api/capabilities"]];
    for (const [name, p] of paths) {
      const ts = []; let bytes = 0, status = 0;
      for (let k = 0; k < 7; k++) { const s = process.hrtime.bigint(); const r = await fetch(`${w.fixtureApi}${p}`, { headers: { "X-Taskuary-Token": w.token } }); const b = await r.arrayBuffer(); ts.push(Number(process.hrtime.bigint() - s) / 1e6); bytes = b.byteLength; status = r.status; }
      out.server[name] = { p, status, bytes, ms: median(ts) };
    }
    // ...what the rail's read is made of: bytes per top-level key, and per row
    const pile = await (await fetch(`${w.fixtureApi}/api/funnel/pile?fyi=50&force=1`, { headers: { "X-Taskuary-Token": w.token } })).json();
    out.pileShape = Object.fromEntries(Object.entries(pile).map(([k, v]) => [k, JSON.stringify(v).length]).sort((a, b) => b[1] - a[1]).slice(0, 6));
    out.pileItems = (pile.items || []).length; out.pileItem = JSON.stringify((pile.items || [])[1] || {}, null, 1).slice(0, 3000);
    out.errors = errors; out.events = await events(w.log);
  } finally { await w.close(); }
  return out;
}

const runs = [];
for (let i = 0; i < REPEATS; i++) { say(`--- run ${i + 1}/${REPEATS} (load ${os.loadavg().map((x) => x.toFixed(1)).join(" ")}) ---`); runs.push(await once(i)); const r = runs.at(-1);
  say(`  (a) enter->line ${r.a.line} ms, enter->working ${r.a.working} ms; (b) first word ${r.b.firstWord} ms after written, last ${r.b.lastWord} ms; open ${r.openMs} ms`); }

say("\n=== MEDIANS over " + runs.length + " runs ===");
say(`(a) Enter -> his line on screen: ${median(runs.map((r) => r.a.line))} ms; -> the working line: ${median(runs.map((r) => r.a.working))} ms`);
say(`(b) agent's first word written -> on screen: ${median(runs.map((r) => r.b.firstWord))} ms; last word -> on screen: ${median(runs.map((r) => r.b.lastWord))} ms`);
say(`(b) hops from Enter, medians (ms): the agent handed its prompt ${median(runs.map((r) => r.hops.agentHandedPrompt))} -> its CLI finished writing ${median(runs.map((r) => r.hops.cliWrote))} -> server API has the answer ${median(runs.map((r) => r.hops.apiHas))} -> page fetched it ${median(runs.map((r) => r.hops.pageFetched))} (${runs.map((r) => r.hops.pageFetchedBy).join(", ")}) -> on screen ${median(runs.map((r) => r.hops.onScreen))}; min/max on screen ${Math.min(...runs.map((r) => r.hops.onScreen))}/${Math.max(...runs.map((r) => r.hops.onScreen))}`);
say(`(c) polling, the last run in full:`);
const last = runs.at(-1);
show("opening the task (3 s)", last.open); show(`idle ${WINDOW} s`, last.idle, WINDOW); show(`a turn at work ${WINDOW} s`, last.turn, WINDOW);
say(`    medians: open ${median(runs.map((r) => r.open.length))} req, idle ${median(runs.map((r) => r.idle.length))} req / ${median(runs.map((r) => tally(r.idle).bytes))} B, turn ${median(runs.map((r) => r.turn.length))} req / ${median(runs.map((r) => tally(r.turn).bytes))} B`);
say(`(d) prompt size per turn (chars; the live process is one session, so turn n is what turn n was handed):`);
for (const r of runs) say(`    run ${r.i + 1}: ` + r.prompts.filter((p) => [1, 2, 3, 5, 10].includes(p.n)).map((p) => `turn ${p.n}=${p.chars}`).join("  "));
const p1 = last.prompts.find((p) => p.n === 1), p10 = last.prompts.find((p) => p.n === TURNS);
if (p1?.text) say(`    turn 1 (first 1500 chars):\n${p1.text.slice(0, 1500)}`);
if (p10?.text) say(`    turn ${TURNS} (all):\n${p10.text.slice(0, 3000)}`);
say(`    the rail's read: ${last.pileItems} items; bytes by key ${JSON.stringify(last.pileShape)}`);
if (process.env.SHOW_ITEM) say(last.pileItem);
say(`(e) server time per polled endpoint (median of 7, ${SEED}+ tasks, a ${TURNS}-turn chat), median over runs:`);
for (const k of Object.keys(last.server)) say(`    ${k.padEnd(14)} ${last.server[k].p.padEnd(40)} ${String(median(runs.map((r) => r.server[k].ms))?.toFixed(1)).padStart(8)} ms  ${last.server[k].bytes} B  [${last.server[k].status}]`);
if (process.env.DUMP_BODIES) await writeFile(process.env.DUMP_BODIES, JSON.stringify(globalThis.__bodies || []));
if (process.env.SPEED_OUT) await writeFile(process.env.SPEED_OUT + ".events.json", JSON.stringify(runs.at(-1).events.map((e) => ({ ...e, prompt: e.prompt && e.prompt.slice(0, 4000) })), null, 1));
if (process.env.SPEED_OUT) await writeFile(process.env.SPEED_OUT, lines.join("\n") + "\n");
