// LOAD AND PERFORMANCE: does the app groan under the weight? (the owner, 2026-11-24). Not a test - it measures and writes numbers.
// A scratch app (fresh home, no outside connection) on the stand-in CLI (tests/fake_claude.py) as `claude`: triage answers after a
// scripted delay per mail, agents' turns are answered here (fake_director.py) after a delay of their own. Then a burst through the real
// roads - mail stored as a poll stores it and judged by the one drain worker (fixture_load.py), lines typed into tasks, presses - while a
// probe times the page's main reads every second, the server samples itself every second, and one Chrome clicks Next/Back and opens rows.
//   cd website && node browser/load-burst.mjs           env: MAILS=100 LINES=30 PRESSES=20 BIG=0 (a task of BIG lines, opened and timed)
//   LOAD_OUT=<folder> (default: os.tmpdir()/claude/load)  DRAIN_MAX_S=900  FAST=1 (triage delays 1-3 s, for the 300-mail run)
// Writes <LOAD_OUT>/<tag>.json (every sample and timing) and <tag>.md (the tables). Invented people only (CLAUDE.md).
import { writeFileSync, mkdirSync, readdirSync, readFileSync, existsSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const E = (k, d) => (process.env[k] === undefined ? d : +process.env[k]);
const MAILS = E("MAILS", 100), LINES = E("LINES", 30), PRESSES = E("PRESSES", 20), BIG = E("BIG", 0), DRAIN_MAX = E("DRAIN_MAX_S", 900), FAST = E("FAST", 0);
const OUT = process.env.LOAD_OUT || path.join(os.tmpdir(), "claude", "load"), TAG = process.env.LOAD_TAG || `m${MAILS}${BIG ? `-big${BIG}` : ""}`;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const pick = (a) => a[Math.floor(rnd() * a.length)];
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

// ── the stand-in brain ──
const bin = path.join(OUT, `bin-${TAG}`), dir = path.join(OUT, `director-${TAG}`);
mkdirSync(bin, { recursive: true }); mkdirSync(dir, { recursive: true });
for (const f of readdirSync(dir)) try { (await import("node:fs")).rmSync(path.join(dir, f)); } catch {}
writeFileSync(path.join(bin, "claude.cmd"), "@echo off\r\nrem stand-in: fixture_load.py runs tests/fake_claude.py for this name\r\n");
const script = path.join(OUT, `script-${TAG}.json`);
Object.assign(process.env, { TASKUARY_FIXTURE_LOAD: "1", FAKE_CLAUDE_SCRIPT: script, FAKE_CLAUDE_SPAWN: "1.5", FAKE_CLAUDE_THINK: "0.3", FAKE_DIRECTOR_WAIT: "120" });

// ── the mail: who writes, what triage makes of it, how long the model takes ──
const people = [["Erin Blake", "erin"], ["Gail Moreno", "gail"], ["Paula Vance", "paula"], ["Ray Colton", "ray"], ["Marcus Reed", "marcus"], ["Omar Keller", "omar"]];
const delay = () => FAST ? 1 + Math.round(rnd() * 2) : (r => r < 0.08 ? 20 : r < 0.25 ? 5 + Math.round(rnd() * 5) : 1 + Math.round(rnd() * 4))(rnd());
const MIX = [["general", 20], ["reply", 15], ["task", 10], ["fyi", 25], ["list", 10], ["thread", 10], ["stranger", 5], ["watch", 5]];
function mails(n) {
  const kinds = MIX.flatMap(([k, c]) => Array(Math.round(c * n / 100)).fill(k)).slice(0, n);
  while (kinds.length < n) kinds.push("fyi");
  const out = [], heads = [];
  kinds.sort(() => rnd() - 0.5).forEach((k, i) => {
    const id = `LT${String(i).padStart(4, "0")}`, [name, user] = pick(people), d = delay();
    const now = new Date(Date.now() - (n - i) * 1000).toISOString().replace("T", " ").slice(0, 19);
    const base = { external_id: `load:${TAG}:${id}`, channel: "email", to: ["alex@northwind.example"], source_name: "alex@northwind.example", sent_at: now };
    let m, v;
    const words = { general: ["Can you pull the Payworth export for October and check the totals?", "general"], reply: ["Which cost centre should the new laptops go on?", null],
      task: ["Please renew the Trainly seats before Friday.", "task"] }[k];
    if (k === "general" || k === "reply" || k === "task") {
      m = { ...base, from_name: name, from_email: `${user}@northwind.example`, subject: `${words[0].slice(0, 40)} (${id})`, body: `Hi Alex,\n${words[0]}\n[${id}]\nThanks, ${name.split(" ")[0]}`, conversation_id: `conv-${id}` };
      v = k === "reply" ? { intent: "reply_only", title: `Answer ${name.split(" ")[0]} about cost centre (${id})`, sender_class: "person", asks_owner: true, why: "a question for you" }
        : { intent: "task", kind: words[1], title: `${words[0].slice(0, 50)} (${id})`, sender_class: "person", asks_owner: k === "task", why: "a concrete ask" };
      if (k !== "task") heads.push(m);
    } else if (k === "fyi") {
      m = { ...base, from_name: "Payworth Updates", from_email: "noreply@vendor.example", subject: `Payroll calendar notice ${id}`, body: `For your information - nothing is asked. [${id}]`, conversation_id: `conv-${id}` };
      v = { intent: "fyi", title: `Payroll calendar notice (${id})`, sender_class: "automated", asks_owner: false, why: "automated/informational" };
    } else if (k === "list") {
      m = { ...base, from_name: "Trainly Digest", from_email: "digest@vendor.example", subject: `Trainly weekly digest ${id}`, body: `This week's courses. Unsubscribe any time. [${id}]`, conversation_id: `conv-${id}`,
        mail_meta: { list: true } };
      v = { intent: "fyi", title: `Trainly digest (${id})`, sender_class: "bulk", asks_owner: false, why: "a newsletter" };
    } else if (k === "thread") {
      const h = heads.length ? pick(heads) : null;
      m = { ...base, from_name: h?.from_name || name, from_email: h?.from_email || `${user}@northwind.example`, subject: `RE: ${h?.subject || "the export"}`,
        body: `One more thing - the numbers for site two too, please. [${id}]`, conversation_id: h?.conversation_id || `conv-${id}` };
      v = { intent: "reply_only", title: `More on the export (${id})`, sender_class: "person", asks_owner: true, why: "a follow-up on the thread" };
    } else if (k === "stranger") {
      m = { ...base, from_name: "Dana Fox", from_email: `dana${i}@vendor.example`, subject: `Partnership question (${id})`, body: `Hello, could you send me your price list? [${id}]`, conversation_id: `conv-${id}` };
      v = { intent: "task", kind: "general", title: `Send Dana the price list (${id})`, sender_class: "person", asks_owner: false, why: "a stranger asks" };
    } else {
      m = { ...base, from_name: name, from_email: `${user}@northwind.example`, subject: `I'll sort the badge reader (${id})`, body: `FYI I will handle the badge reader this week. [${id}]`, conversation_id: `conv-${id}` };
      v = { intent: "watch", title: `${name.split(" ")[0]} sorts the badge reader (${id})`, sender_class: "person", asks_owner: false, why: "someone else's to do" };
    }
    out.push({ id, kind: k, delay: d, msg: m, verdict: v });
  });
  return out;
}
const M = mails(MAILS);
// newest first: a reply's prompt carries its thread's earlier markers too, and the first rule that matches answers
const PROOF = { when: "Q3 vendor invoice - can you approve by Friday", anywhere: true, first: JSON.stringify({ intent: "task", kind: "task", title: "Approve the Q3 invoice", sender_class: "person", asks_owner: true, why: "a test" }) };
writeFileSync(script, JSON.stringify([PROOF, ...[...M].reverse().map((x) => ({ when: `"body": "[^"]*\\[${x.id}\\]`, anywhere: true, first: JSON.stringify(x.verdict), wait: x.delay }))]));

// ── the app ──
const h = await startHarness({ fresh: true, bin });
writeFileSync(path.join(h.home, ".fake-director"), dir);
const hdr = { "Content-Type": "application/json", "X-Taskuary-Token": h.token };
// one request, timed: ttfb (headers) and full (body read), node:http with no clock of its own
function call(p, body, method) {
  const u = new URL(`${h.fixtureApi}${p}`), data = body === undefined ? undefined : JSON.stringify(body), t0 = performance.now();
  return new Promise((ok) => {
    const r = http.request(u, { method: method || (data ? "POST" : "GET"), headers: hdr }, (res) => {
      const ttfb = performance.now() - t0; let t = ""; res.setEncoding("utf8"); res.on("data", (c) => (t += c));
      res.on("end", () => { let j = null; try { j = JSON.parse(t); } catch {} ok({ status: res.statusCode, ttfb, ms: performance.now() - t0, bytes: t.length, j }); });
    });
    r.on("error", (e) => ok({ status: 0, ttfb: null, ms: performance.now() - t0, err: e.message })); r.setTimeout(0); r.end(data);
  });
}
const api = async (p, b, m) => (await call(p, b, m)).j;
const timings = {}; const time = (k, r) => { (timings[k] ||= []).push({ at: Date.now(), ttfb: r.ttfb, ms: r.ms, status: r.status, bytes: r.bytes }); return r; };

let stopped = false;
try {
  log("setup", JSON.stringify(await api("/api/setup/first-run/ai", { name: "claude" })).slice(0, 200));
  await api("/api/setup/dismiss", { dismissed: true });
  await api("/api/fixture/outbox", {});
  await api("/api/fixture/load/start", {});
  // drafts waiting for Send, as the arrival road leaves them (fixture_server mail-task), each its own thread
  const drafts = [];
  for (let i = 0; i < Math.ceil(PRESSES * 0.4); i++) drafts.push(await api("/api/fixture/mail-task", { title: `Vendor review ${i} for Erin`, conversation: `conv-draft-${i}`, sent: "2026-11-24 07:00:00" }));
  const seeded = [...drafts];
  const big = BIG ? await api("/api/fixture/load/big", { lines: BIG }) : null;

  // ── the director: every agent turn answered after its own delay; a triage prompt that lands here answered from its marker ──
  const turns = [], answering = new Set(), byId = Object.fromEntries(M.map((x) => [x.id, x]));
  const director = (async () => {
    while (!stopped) {
      for (const f of readdirSync(dir)) {
        const m = f.match(/^(\d+)\.in$/); if (!m || answering.has(m[1])) continue;
        answering.add(m[1]);
        const prompt = readFileSync(path.join(dir, f), "utf8"), mk = [...prompt.matchAll(/\[(LT\d{4})\]/g)].map((x) => x[1]).at(-1);
        const triage = /"sender_class"|JSON object the instructions describe/.test(prompt) && mk;
        const d = triage ? byId[mk].delay : rnd() < 0.1 ? 20 : 2 + Math.round(rnd() * 5), lines = [...prompt.matchAll(/LTLINE-(\d+)/g)].map((x) => +x[1]);
        turns.push({ k: +m[1], at: Date.now(), chars: prompt.length, triage: !!triage, lines: [...new Set(lines)], delay: d });
        setTimeout(() => writeFileSync(path.join(dir, `${m[1]}.out`), triage ? JSON.stringify(byId[mk].verdict) : `Checked it and done - the totals match. (turn ${m[1]})`), d * 1000);
      }
      await sleep(150);
    }
  })();

  // ── the page, recorded, and its own clock: frames that stall, blank beats, every /api answer's time ──
  const page = await h.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const net = [];
  page.on("requestfinished", (r) => { const u = new URL(r.url()); if (!u.pathname.startsWith("/api/")) return; const t = r.response()?.timing();
    net.push({ at: Date.now(), key: `${r.method()} ${u.pathname.replace(/\/\d+(?=\/|$)/g, "/N")}`, ms: t ? t.receiveHeadersEnd : null }); });
  const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.evaluateOnNewDocument(() => {
    window.__ld = { gaps: [], blanks: 0, lastMut: performance.now(), inflight: 0 };
    let last = performance.now();
    const raf = () => { const n = performance.now(); if (n - last > 250) window.__ld.gaps.push([Date.now(), Math.round(n - last)]); last = n; requestAnimationFrame(raf); }; requestAnimationFrame(raf);
    window.__ld.muts = [];
    new MutationObserver(() => { window.__ld.lastMut = performance.now(); const m = window.__ld.muts; m.push(Date.now()); if (m.length > 2000) m.splice(0, 1000); }).observe(document, { subtree: true, childList: true, characterData: true, attributes: true });
    const f = window.fetch; window.fetch = (...a) => { window.__ld.inflight++; return f(...a).finally(() => window.__ld.inflight--); };
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail]", { timeout: 60000 }).catch(() => log("no rail at start"));
  await sleep(3000);
  // ...the screen recorded for REC_S seconds of the burst only: every paint is a JPEG, ~1 GB per 5 minutes - a whole drain filled the disk
  const rec = await record(page, path.join(OUT, `video-${TAG}`)), REC_S = E("REC_S", 90);
  let frames = null; const recDone = sleep(REC_S * 1000).then(async () => { frames = await rec.stop({ sheet: 12 }); });

  // ── the server's probe, once a second: the page's main reads, timed from outside ──
  let probeTid = seeded[0]?.taskId;
  const probe = (async () => {
    while (!stopped) {
      const t = Date.now();
      await Promise.all([
        call("/api/funnel/pile").then((r) => time("GET rail (/api/funnel/pile)", r)),
        probeTid && call(`/api/tasks/${probeTid}/conversation`).then((r) => time("GET task conversation", r)),
        probeTid && call(`/api/tasks/${probeTid}`).then((r) => time("GET task (header)", r)),
        call("/api/ingest/status").then((r) => time("GET header status (/api/ingest/status)", r)),
        big && call(`/api/tasks/${big.taskId}/conversation`).then((r) => time(`GET conversation of the ${BIG}-line task`, r)),
      ]);
      await sleep(Math.max(0, 1000 - (Date.now() - t)));
    }
  })();

  // ── the UI's hand: Next, Back, a row, each timed from the click to the screen settling (no DOM change 300 ms, no fetch open) ──
  const ui = [];
  async function settle(t0) {
    const end = Date.now() + 15000; let moved = false;
    while (Date.now() < end) {
      const s = await page.evaluate((t0) => ({ first: window.__ld.muts.find((x) => x >= t0) || null, idle: performance.now() - window.__ld.lastMut, inflight: window.__ld.inflight, mutAt: Date.now() - (performance.now() - window.__ld.lastMut),
        blank: (document.querySelector("main, [data-tq-task-page], [data-tq-rail]")?.innerText || "").trim().length < 15 }), t0);
      if (s.blank) ui.blank = (ui.blank || 0) + 1;
      if (s.mutAt > t0) moved = true;
      if (s.idle > 300 && !s.inflight && (moved || Date.now() - t0 > 2000)) return { ms: moved ? Math.round(s.mutAt - t0) : null, first: s.first ? s.first - t0 : null, moved };
      await sleep(50);
    }
    return { ms: 15000, moved, timeout: true };
  }
  const clickBy = (sel, words) => page.evaluate((sel, words) => {
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const b = [...document.querySelectorAll(sel)].filter(vis).filter((e) => !words || new RegExp(words, "i").test((e.innerText || e.getAttribute("aria-label") || "").trim()))
      .filter((e) => !e.disabled && !e.closest("[aria-disabled=true]"))[0];
    if (!b) return null; const q = b.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2, w: (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 40) };
  }, sel, words);
  const uiLoop = (async () => {
    const acts = [["open a rail row", "[data-tq-rail] .tq-pile-row[data-tq-key]", null], ["Next", "button", "^next\\b"], ["Next", "button", "^next\\b"], ["Back", "button", "^back\\b"]];
    let i = 0;
    while (!stopped) {
      const [what, sel, words] = acts[i++ % acts.length];
      const at = await clickBy(sel, words).catch(() => null);
      if (at) { const t0 = Date.now(); await page.mouse.click(at.x, at.y); const s = await settle(t0); ui.push({ at: t0, what, label: at.w, ...s }); }
      else ui.push({ at: Date.now(), what, missing: true });
      await sleep(2500);
    }
  })();

  // ── the burst ──
  const T0 = Date.now(); log(`burst: ${MAILS} mails over ~60 s, ${LINES} lines, ${PRESSES} presses`);
  const arrive = (async () => {
    const per = Math.max(1, Math.ceil(MAILS / 15));
    for (let i = 0; i < M.length; i += per) {
      time("POST mail batch stored (fixture poll)", await call("/api/fixture/load/arrive", { messages: M.slice(i, i + per).map((x) => x.msg) }));
      await sleep(4000);
    }
  })();
  const outcomes = async () => (await api("/api/fixture/load/outcomes", { externals: M.map((x) => x.msg.external_id) })) || { out: {} };
  // lines typed into the tasks the burst gave agents, while they work
  const sent = [];
  // ...each sent as the page sends it, never waiting on the answer before the next line (the page draws the line at once and reads on)
  const lines = (async () => {
    await sleep(20000);
    const flying = [];
    for (let n = 0; n < LINES; n++) {
      const o = (await outcomes()).out, tids = [...new Set(M.filter((x) => x.kind === "general" && o[x.msg.external_id]?.task).map((x) => o[x.msg.external_id].task))];
      const tid = tids.length ? tids[n % tids.length] : seeded[n % seeded.length].taskId;
      flying.push(call(`/api/tasks/${tid}/assistant/messages`, { text: `LTLINE-${n} also check the site two totals please`, line_id: `lt-${n}` })
        .then((r) => { time("POST typed line (assistant/messages)", r); sent.push({ n, tid, status: r.status, ms: Math.round(r.ms), said: JSON.stringify(r.j || {}).slice(0, 160) }); }));
      await sleep(Math.round(45000 / Math.max(1, LINES)));
    }
    await Promise.all(flying);
  })();
  const pressed = [];
  const presses = (async () => {
    await sleep(15000);
    const nSend = drafts.length, nDone = Math.round((PRESSES - nSend) / 2), nNot = PRESSES - nSend - nDone;
    for (let i = 0; i < PRESSES; i++) {
      let k, r, target;
      if (i % 2 === 0 && drafts.length) { const d = drafts.shift(); target = d.reviewId; k = "press Send (reviews/decide approve)"; r = await call(`/api/reviews/${d.reviewId}/decide`, { verb: "approve" }); }
      else {
        const o = (await outcomes()).out, ids = M.filter((x) => o[x.msg.external_id]?.task && !pressed.some((p) => p.target === o[x.msg.external_id].task) && ["task", "general", "reply"].includes(x.kind));
        const x = ids[i % Math.max(1, ids.length)]; if (!x) { await sleep(3000); continue; }
        target = o[x.msg.external_id].task;
        if (pressed.filter((p) => /Mark done/.test(p.k)).length < nDone) { k = "press Mark done (funnel/settle done)"; r = await call("/api/funnel/settle", { key: `task:${target}`, verb: "done" }); }
        else { k = "press Not a task (not-a-task)"; r = await call(`/api/tasks/${target}/not-a-task`, { learn: false }); }
      }
      time(k, r); pressed.push({ k, target, status: r.status, ms: Math.round(r.ms), said: JSON.stringify(r.j || {}).slice(0, 160) });
      await sleep(2500);
    }
  })();
  await Promise.all([arrive, lines, presses]);
  log(`burst sent in ${Math.round((Date.now() - T0) / 1000)} s; draining`);

  // ── the drain: until no mail waits for triage, no agent start waits in the queue and no turn is still owed, quiet for 20 s ──
  let quietSince = 0, last = null;
  const D0 = Date.now();
  while (Date.now() - D0 < DRAIN_MAX * 1000) {
    const s = (await api(`/api/fixture/load/stats?since=${1e9}`)) || {};
    last = await api(`/api/fixture/load/stats?since=${Math.max(0, (s.now || 0) - 3)}`);
    const smp = last?.samples?.at(-1) || {}, owed = turns.filter((t) => !existsSync(path.join(dir, `${t.k}.out`))).length;
    const busy = smp.triage_backlog || smp.queued_agents || smp.working_agents || owed;
    if (!busy) { quietSince ||= Date.now(); if (Date.now() - quietSince > 20000) break; } else quietSince = 0;
    if ((Date.now() - D0) % 30000 < 2100) log(`drain: backlog ${smp.triage_backlog} queued ${smp.queued_agents} working ${smp.working_agents} owed turns ${owed} cpu ${smp.cpu}% rss ${smp.rss_mb}MB`);
    await sleep(2000);
  }
  const drainS = Math.round((Date.now() - T0) / 1000);
  log(`drained (or gave up) at ${drainS} s`);
  // the big task opened in the page, timed - after the burst, on its own
  const bigOpen = [];
  if (big) for (let i = 0; i < 3; i++) {
    const t0 = Date.now(); await page.evaluate((id) => { location.hash = `task=${id}`; }, big.taskId);
    const ok = await page.waitForSelector("[data-tq-task-page] .tq-aui-viewport", { timeout: 30000 }).then(() => true, () => false);
    const s = await settle(t0); bigOpen.push({ ok, ...s }); await page.evaluate(() => { location.hash = ""; }); await sleep(3000);
  }
  stopped = true;
  await Promise.all([probe, uiLoop, director]).catch(() => {});
  await recDone;
  const page_ = await page.evaluate(() => ({ gaps: window.__ld.gaps }));
  const stats = await api("/api/fixture/load/stats?since=0"), fin = await outcomes();
  const outbox = existsSync(path.join(h.home, "outbox.jsonl")) ? readFileSync(path.join(h.home, "outbox.jsonl"), "utf8").trim().split("\n").filter(Boolean).length : 0;
  const comments = {};
  for (const p of pressed) if (p.target && /Mark done|Not a task/.test(p.k)) comments[p.target] = (await api(`/api/tasks/${p.target}`))?.Status || (await call(`/api/tasks/${p.target}`)).status;
  writeFileSync(path.join(OUT, `${TAG}.json`), JSON.stringify({ TAG, MAILS, LINES, PRESSES, BIG, FAST, drainS, timings, ui, uiBlank: ui.blank || 0, net, page: page_, errs, stats, mails: M.map(({ id, kind, delay, msg }) => ({ id, kind, delay, ext: msg.external_id })),
    outcomes: fin, turns, sent, pressed, outbox, after: comments, frames: frames?.length, bigOpen, log: h.log().slice(-200000) }));
  log(`wrote ${path.join(OUT, `${TAG}.json`)}`);
} finally {
  stopped = true;
  await h.close();
}
