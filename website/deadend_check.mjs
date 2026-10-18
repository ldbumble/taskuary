// Does the walk ever leave the owner alone? Clicks through a fresh world, presses EVERY button the one list names, makes things
// fail on purpose, and fails on a dead end.
//
// Tests read the source; a dead end only shows on the screen. The 2026-10-17 click-through found five that every test passed, and
// then this walk itself went hollow: it pressed "Send", "End" and "Done" by their words - two of them no longer existed - with the
// demo's refusals switched off, so no send, close, fix or cancel was ever walked (the re-audit, 2026-10-18). Now every press is
// chosen by its VERB from buttons.js, a button nobody pressed fails the walk (COVER), and failures are forced at the boundary - the
// mailbox, the coding tool, the AI (taskuary/faults.py) - never by turning a refusal off. Four passes:
//
//   walk      the demo, refusals ON: Next through the day, doing what each card's first button invites
//   sweep     the demo, refusals ON: every button every row shows, in its row and its More menus, pressed once
//   faults    a seeded world with a mocked mailbox: each failure failures.classify knows, forced, then its way out pressed
//   cards     a proposal card cancelled, then pressed; a task folded by its X, then opened again from its line and the rail
//
// The rules, checked at every step:
//   DARK      the bar is dark only when the Advisor spoke, and then on one button (the owner, 2026-10-17: "keep it ai")
//   SEEN      the card on the table shows more than its header
//   FIX       an error on screen has a way out on the row - a verb that is not Next
//   RECEIPT   an item that leaves the rail leaves a line in the chat naming it
//   OPENS     a chip that says "Open TQ-x" puts TQ-x on the table
//   WORDS     no developer word and no raw error on the card, the row, the Advisor's line or an error (words.json's jargon)
//   NAMES     every button on the row and in its menus is a named button - a label in buttons.json
//   CALLS     no /api request fails while the walk runs - a refusal the demo says AS the demo is not a failure
//   NOTHING   a press that changes nothing on the screen
//   COVER     a button on the list that the walk never pressed and WALK_SKIP does not explain
//   WAYOUT    a forced failure whose screen has no button from the list that gets past it, or whose way out does nothing
//   LIVE      a cancelled or failed proposal card that still offers its buttons
//   FOLD      a task folded by its X that its folded line or its rail row cannot open again
//   UNDO      a receipt that says it can be undone ("Undo: ...") with no Take it back to press under it
//
//   node website/deadend_check.mjs [--port 7799] [--keep] [--no-build] [--json] [--only walk,sweep,faults,cards]
//
// It builds the page from THIS checkout's source into a scratch folder (--no-build: the committed bundle) and starts its own servers
// on throwaway homes (never the owner's 7787).
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
import { JARGON_RES } from "./src/words.js";
import { VERBS, ALL_LABELS, label, verbOfRow, choice } from "./src/buttons.js";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
// no --port: every server takes a port the system says is free - two walks on one box (or a walk beside the browser suite) collided
// on the fixed 7799..7802 and one of them "never came up" (2026-10-18). --port N pins N, N+1, N+2, N+3 as before.
const fixed = process.argv.includes("--port"), port = Number(arg("--port", 7799)), keep = process.argv.includes("--keep"), build = !process.argv.includes("--no-build");
const only = new Set(String(arg("--only", "walk,sweep,faults,cards")).split(","));
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// THE BUTTONS THE WALK CANNOT PRESS, and why - every other verb (and each of its states) is pressed at least once, or COVER says so.
// A new button with neither fails the walk: that is what keeps it from going hollow again.
const WALK_SKIP = {
  "approve:action": "an agent's proposal: the demo's agents are recordings and never propose an act",
  "redraft": "redrafting asks the AI - the demo's canned brain writes no drafts, and the faults world has no AI",
  "redraft:none": "as Redraft: writing a draft is the AI's",
  "not_ours_sender": "an answer inside Not ours' own question (buttons.json choices), pressed through that card, not a row of its own",
  "block_sender": "as Ignore this sender: an answer inside Not ours' question",
  "not_ours_kind": "an answer inside an idea's Not ours question",
  "coding_agent": "an answer inside Send to agent's question; the faults pass starts one through it",
  "stop_agent": "Stop and save ends a live session - the demo's agents are recordings with no session to save",
  "continue": "Keep going resumes a stopped agent's session - none in the demo world has one",
  "rerun": "runs a report - the demo refuses it (\"running reports are switched off\"), the faults world has no report source",
  "chase": "shows only on a person who has gone quiet past their usual time - the seeded world is hours old",
  "let_go": "as Chase them: a slipped follow-up's answer",
  "elsewhere": "as Chase them: a slipped follow-up's answer",
  "test_connection": "on a connection's own card, not an item's row - the connection cards are walked by the browser setup tests",
  "next:batch": "shows only on a run of notices read together - the demo's fyi fold away under 'more fyi' instead",
  "split": "opens the split-or-merge drawer; its own press is walked, the reshape itself is the task tests'",
  "review_changes": "opens the agent's diff drawer - walked when an agent row carries it",
  "run_another": "starts a second agent - the demo refuses starts and the faults pass starts one through Send to agent",
  "retriage": "asks the AI to sort it again - no AI in either world",
  "share": "opens Send out results - mailing someone is refused in the demo",
  "try_again": "repeats a failed press - pressed in the faults pass only where the failure says a retry could work",
  "take_back": "a receipt's undo - pressed in the faults pass on a Remind me receipt",
  "new_task": "the idle chips' New task opens the New sheet - walked by the browser New tests",
  "new_task:fix": "offered by the Advisor on a failure nothing fixes - the walk has no AI to offer it",
  "report_bug": "opens the bug report draft - the faults pass checks it is offered, never sends one",
  "approve:unknown": "Send anyway on a send nobody can confirm - the faults pass checks it is offered",
  "pick_repo:set": "shows once a task has a repository - neither world has one chosen",
  "split:split": "the plain split's own name for the same drawer Split or merge opens - the drawer's press is walked as split",
  "attach:more": "shows once a file is attached - the walk attaches none: the file picker is the system's own window",
};

// words the owner should never have to read: the one list the server's sentences are held to (taskuary/words.json) - and what only a
// crash or a raw provider error leaves on a screen, which is no word anyone chose
const JARGON = [...JARGON_RES, /\bnull\b/, /\bundefined\b/, /Traceback/, /\b[45]\d\d(?= \()/, /\[Errno \d+\]/, /\bb'[^']{3,}'/, /\(\d{3}, b['"]/,
  /\w+Error: /];
const NAMED = new Set(ALL_LABELS.map((l) => l.trim()));
// a failed send's fix ('<rid>:fix') and a failure's own fix wear the fix's own words ("Connect a mailbox") - buttons.json says so of `fix`
const named = (w, id = "") => !w || NAMED.has(w) || /…$/.test(w) || w === "▾" || /^Open TQ-\d+/.test(w) || /:fix$/.test(id);
// the cover key of a button: its verb, and the state its words are ("approve:unknown" for Send anyway)
const coverOf = (verb, word) => {
  const v = VERBS[verb]; if (!v) return null;
  if (!word || word === v.label) return verb;
  const st = Object.entries(v.states || {}).find(([, w]) => w === word);
  return st ? `${verb}:${st[0]}` : verb;
};
// a row id -> its verb: the task page's own ids (buttons.json `row`), a chip's verb (`w:mine`), a draft's (`2:approve`)
const verbOfId = (id) => { const last = String(id || "").split(":").pop(); return verbOfRow(id) || (VERBS[last] ? last : null); };
const byLabel = Object.fromEntries(Object.entries(VERBS).flatMap(([k, v]) => [[v.label, k], ...Object.values(v.states || {}).map((w) => [w, k])]));

const web = build && only.size ? mkdtempSync(join(tmpdir(), "tq-deadend-web-")) : "";
if (web && spawnSync("npx", ["vite", "build", "--outDir", web, "--emptyOutDir"], { cwd: join(root, "website"), shell: true, stdio: "ignore" }).status) {
  console.error("the page did not build"); process.exit(2);
}

const found = [], pressed = new Map(), walked = [];          // walked: the paths that ran, so a quiet pass is not an empty one
const note = (rule, at, what) => found.push(`${rule.padEnd(7)} ${at}: ${what}`);
const mark = (key, at) => { if (key && !pressed.has(key)) pressed.set(key, at); };

// ── a server: the demo (refusals ON), or a seeded world whose mailbox, coding tool and AI are the faults module's ────────────
const freePort = () => new Promise((res, rej) => { const s = createServer(); s.unref(); s.on("error", rej);
  s.listen(0, "127.0.0.1", () => { const { port: p } = s.address(); s.close(() => res(p)); }); });
async function serve(n, opts = {}) {
  // a free port can be taken between asking and binding: once more on a fresh one before saying it failed
  for (let tries = 0; ; tries++) {
    const p = fixed ? port + n : await freePort();
    try { return await serveOn(p, opts); }
    catch (e) { if (fixed || tries >= 1) throw e; }
  }
}
async function serveOn(p, { faults = false } = {}) {
  const home = mkdtempSync(join(tmpdir(), "tq-deadend-"));
  const launchPy = `
import sys, pathlib
from taskuary import server, cli
from fastapi.staticfiles import StaticFiles
web = ${JSON.stringify(web)}
if web:
    server._web_root = pathlib.Path(web)
    for r in server.app.routes:
        if getattr(r, 'name', '') in ('assets', 'walk'): r.app = StaticFiles(directory=str(server._web_root / r.name), check_dir=False)
if ${faults ? "True" : "False"}:
    from taskuary import faults, demo, firstrun
    assert faults.install(server.app), 'the faults module refused to install'
    demo.seed(server.store); server.store.set_setting(firstrun.DISMISSED, '1', 'walk')
sys.argv = ['taskuary'${faults ? "" : ", '--demo'"}, '--no-browser', '--port', '${p}']; cli.main()`;
  const env = { ...process.env, TASKUARY_HOME: home, TASKUARY_ALLOW_TEST_HOME: "1", ...(faults ? { TASKUARY_FAULTS: "1" } : { TASKUARY_DEMO: "1" }) };
  delete env[faults ? "TASKUARY_DEMO" : "TASKUARY_FAULTS"];
  const srv = spawn("python", ["-c", launchPy], { cwd: root, env, stdio: ["ignore", "ignore", "pipe"] });
  let errTail = ""; srv.stderr.on("data", (d) => { errTail = (errTail + d).slice(-1500); });
  const base = `http://127.0.0.1:${p}`;
  let token = "";
  for (let i = 0; i < 90 && !token; i++) {
    await wait(1000);
    if (srv.exitCode !== null) break;                               // it died: say why now, not after 90 seconds
    try { token = (readFileSync(join(home, "config.toml"), "utf8").match(/^token = "([^"]+)"/m) || [])[1] || ""; } catch { /* not written yet */ }
    if (token && !(await fetch(`${base}/api/funnel/pile`, { headers: { "X-Taskuary-Token": token } }).then((r) => r.ok).catch(() => false))) token = "";
  }
  if (!token) {
    srv.kill();
    const why = srv.exitCode !== null ? `it exited (${srv.exitCode})` : "no answer in 90 s";
    const last = errTail.trim().split(/\r?\n/).slice(-4).join(" | ");
    throw new Error(`the ${faults ? "faults" : "demo"} server never came up on port ${p}: ${why}${last ? ` - its last words: ${last}` : ""}`);
  }
  const H = { "X-Taskuary-Token": token, "Content-Type": "application/json" };
  const api = async (method, path, body) => { const r = await fetch(`${base}${path}`, { method, headers: H, body: body ? JSON.stringify(body) : undefined }); return r.json().catch(() => ({})); };
  if (faults) await api("POST", "/api/setup/dismiss", { dismissed: true });
  return { base, token, api, stop: () => { if (!keep) srv.kill(); } };
}

// ── a page on it: the owner's token put where a launch key would (the demo refuses minting one), the rules' listeners attached ──
let browser;
async function pageOn(srv, phase) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });            // a laptop: where "the card is off the screen" happens
  await page.evaluateOnNewDocument((t) => { try { localStorage.setItem("taskuary_token", t); } catch { /* none */ } }, srv.token);
  page.step = phase;
  page.on("pageerror", (e) => note("CRASH", page.step, e.message));
  page.expect = new Set();                                           // an /api path whose failure the step forced on purpose
  page.on("response", async (r) => {
    const u = new URL(r.url());
    if (!u.pathname.startsWith("/api/") || r.status() < 400 || u.pathname === "/api/test/fault") return;
    const body = await r.json().catch(() => ({}));
    if (r.status() === 403 && body?.demo) return;                    // the demo saying no, as the demo: an ordinary line
    if ([...page.expect].some((x) => u.pathname.includes(x))) return;
    note("CALLS", page.step, `${r.request().method()} ${u.pathname} answered ${r.status()}${body?.detail ? ` - "${String(body.detail).slice(0, 80)}"` : ""}`);
  });
  await page.goto(`${srv.base}/`, { waitUntil: "load" });
  await wait(6000);
  await clickText(page, "Walk me through my tasks");
  await wait(5000);
  return page;
}
const clickText = async (page, t, scope = "") => {
  for (const b of await page.$$(`${scope} button`)) if (await b.evaluate((e, t) => e.innerText.trim() === t && e.getBoundingClientRect().width > 0, t)) { await b.click(); return true; }
  return false;
};

// one read of everything the rules look at
const look = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const row = document.querySelector("[data-tq-row]"), chat = document.querySelector(".tq-chat-body");
  const verbs = row ? [...row.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), id: b.getAttribute("data-tq-verb") || "", dark: b.classList.contains("p"), next: b.hasAttribute("data-tq-next"), off: b.disabled })) : [];
  const cards = [...document.querySelectorAll("[data-tq-task-page]")].filter(vis), card = cards[cards.length - 1];
  const cardBtns = card ? [...card.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), off: b.disabled })).filter((b) => b.word) : [];
  const cr = card?.getBoundingClientRect(), hr = chat?.getBoundingClientRect(), rr = row?.getBoundingClientRect();
  const errs = [...document.querySelectorAll('[role="alert"], .MuiAlert-standardError, .tq-next-err')].filter(vis).map((e) => e.innerText.trim()).filter(Boolean);
  const rail = [...document.querySelectorAll("[data-tq-rail] [data-tq-key]")].map((e) => ({ key: e.getAttribute("data-tq-key"),
    text: e.innerText.replace(/\s+/g, " ").trim(), title: (e.querySelector(".card b")?.innerText || "").trim(), current: e.classList.contains("current") }));
  const table = [...document.querySelectorAll("[data-tq-rail] *")].find((e) => e.children.length === 0 && e.innerText?.trim() === "ON THE TABLE");
  const ref = (table?.closest("[data-tq-key]")?.innerText.match(/TQ-\d+/) || [])[0] || ((card?.innerText || "").match(/TQ-\d+/) || [])[0] || "";
  const adviceEl = document.querySelector('[data-tq-advice]:not([data-tq-advice="no_ai"])');
  const read = [card?.innerText || "", row?.innerText || "", adviceEl?.innerText || "", ...errs].join("\n");
  const pops = [...document.querySelectorAll('.MuiPopover-paper, [role="dialog"], .MuiDrawer-paper')].filter(vis).map((p) => p.innerText.replace(/\s+/g, " ").slice(0, 80));
  const msgs = chat ? [...chat.querySelectorAll(".tq-msg")] : [];
  const tail = msgs.slice(-8);                       // a receipt stays a few lines up once the walk has brought the next item
  return { verbs, cardBtns, advice: !!adviceEl, adv: adviceEl?.innerText || "", errs, rail, ref, read, chat: chat?.innerText || "", pops,
    undoSaid: tail.some((m) => /Undo: /.test(m.innerText || "")),
    chatBtns: tail.flatMap((m) => [...m.querySelectorAll("button")].filter(vis).map((b) => b.innerText.trim())),
    nmsg: msgs.length, last: (msgs[msgs.length - 1]?.innerText || "").slice(0, 200), url: location.href, focus: document.activeElement?.tagName || "",
    folded: [...document.querySelectorAll("[data-tq-folded]")].filter(vis).map((e) => e.getAttribute("data-tq-folded")),
    card: card ? { top: cr.top, shown: Math.min(cr.bottom, rr ? rr.top : hr.bottom) - Math.max(cr.top, hr.top), text: card.innerText.length } : null };
});
// what a press may change: if none of it did, the owner pressed and nothing happened
const sig = (s) => JSON.stringify([s.verbs.map((v) => v.id + v.word + v.off), s.cardBtns.map((b) => b.word + b.off), s.rail.map((r) => r.key), s.nmsg, s.last,
  s.errs, s.pops, s.url, s.focus, s.ref, s.card?.text || 0, s.folded]);

const judge = (s, at) => {
  const dark = s.verbs.filter((v) => v.dark);
  if (s.card || s.ref) {
    if (!s.advice && dark.length) note("DARK", at, `"${dark.map((v) => v.word).join('", "')}" dark with no Advisor line over it`);
    if (s.advice && dark.length > 1) note("DARK", at, `the Advisor spoke and ${dark.length} buttons are dark - ${JSON.stringify(s.verbs.map((v) => v.word))} / "${s.adv.slice(0, 80)}"`);
  }
  if (s.card && s.card.shown < 120) note("SEEN", at, `only ${Math.round(s.card.shown)}px of the card on the table is in view`);
  if (s.errs.length && !s.verbs.some((v) => !v.next && !v.off) && !s.cardBtns.some((b) => !b.off && NAMED.has(b.word)))
    note("FIX", at, `"${s.errs[0].slice(0, 90)}" and nothing on the row but Next`);
  for (const w of JARGON) { const m = s.read.match(w); if (m) note("WORDS", at, `"${m[0]}" in "${s.read.slice(Math.max(0, m.index - 40), m.index + 60).replace(/\s+/g, " ")}"`); }
  if (s.undoSaid && !s.chatBtns.includes(label("take_back"))) note("UNDO", at, `a receipt offers an undo and no "${label("take_back")}" is drawn under it`);
  const odd = [...new Set(s.verbs.filter((v) => !named(v.word, v.id)).map((v) => v.word))];
  if (odd.length) note("NAMES", at, `on the row but on no list of buttons: ${JSON.stringify(odd)}`);
};
const receipts = (before, after, at) => {
  const keys = new Set(after.rail.map((r) => r.key));
  for (const r of before.rail.filter((r) => !keys.has(r.key))) {
    const ref = (r.text.match(/TQ-\d+/) || [])[0], name = ref || r.title.replace(/…$/, "").slice(0, 30);
    if (name && !after.chat.includes(name) && !(r.key.startsWith("processing:") && !ref && /fyi let go/.test(after.chat)))
      note("RECEIPT", at, `${name} left the rail with no line saying where it went`);
  }
};
const rowHandle = (page, verb) => page.evaluateHandle((verb, ids) => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return [...document.querySelectorAll("[data-tq-row] button[data-tq-verb]")].filter(vis).find((b) => ids.includes(b.getAttribute("data-tq-verb").split(":").pop())) || null;
}, verb, [verb, ...(VERBS[verb]?.row || [])]);
const pressVerb = async (page, verb) => { const h = (await rowHandle(page, verb)).asElement(); if (!h) return false; await h.click(); mark(verb, page.step); return true; };
const pressNext = async (page) => { const h = await page.$("[data-tq-row] [data-tq-next]"); if (!h) return false; await h.click(); mark("next", page.step); return true; };
const openItem = async (page, pick) => {                        // a rail row by its key, or the first whose words match
  const s = await look(page);
  const r = s.rail.find((x) => (typeof pick === "string" ? x.key === pick || x.text.includes(pick) : pick(x)));
  if (!r) return null;
  const h = await page.$(`[data-tq-rail] [data-tq-key="${r.key}"]`); if (!h) return null;
  await h.click(); await wait(3500); return r;
};
const closePops = async (page) => { for (let i = 0; i < 2; i++) { await page.keyboard.press("Escape"); await wait(300); } };

// ── WALK: Next through the day, doing what each card's first button invites, so the paths behind it run too ─────────────────
async function walk() {
  const srv = await serve(0), page = await pageOn(srv, "walk");
  let s = await look(page);
  const did = new Set(), seen = new Map();
  for (let n = 0; n < 40; n++) {
    const at = page.step = `walk ${n} ${s.ref || "(no item)"}`;
    judge(s, at);
    if (s.verbs.some((v) => v.word.startsWith("Open TQ"))) break;
    const before = s, has = (verb) => s.verbs.some((v) => verbOfId(v.id) === verb);
    if (!did.has("approve") && has("approve")) { did.add("approve"); await pressVerb(page, "approve"); }
    else if (!did.has("close") && has("close")) {
      did.add("close"); await pressVerb(page, "close"); await wait(1200);
      await clickText(page, label("close"), '[role="dialog"]');
    }
    else if (s.verbs.some((v) => v.word === label("next", "batch"))) await clickText(page, label("next", "batch"), "[data-tq-row]");
    else if (!(await pressNext(page))) {
      const inline = await page.$$(".tq-chat-body .tq-msg button, .tq-chat-body .tq-proposal button");
      const words = await Promise.all(inline.map((h) => h.evaluate((b) => b.innerText.trim())));
      if (!inline.length) { note("FIX", at, `no Next on the row and nothing in the chat - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
      note("INLINE", at, `the way on is in the chat, not on the row: ${JSON.stringify(words.filter(Boolean))}`);
      await inline[0].click();
    }
    await wait(5000);
    s = await look(page);
    judge(s, `${at} after`);
    receipts(before, s, at);
    const k = JSON.stringify([s.ref, s.verbs.map((v) => v.word), s.chat.length]);
    seen.set(k, (seen.get(k) || 0) + 1);
    if (seen.get(k) >= 3) { note("STUCK", at, `three presses left the same screen - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
  }
  // OPENS: the end line's first chip must put its own TQ on the table
  const w = s.verbs.map((v) => v.word).find((x) => x.startsWith("Open TQ"));
  if (w && await clickText(page, w, "[data-tq-row]")) {
    await wait(5000);
    const got = await look(page), want = w.match(/TQ-\d+/)[0];
    if (got.ref !== want) note("OPENS", w, `put ${got.ref || "nothing"} on the table`);
    judge(got, w);
  }
  await page.close(); srv.stop();
}

// ── SWEEP: every button every row shows, in the row and its More menus, pressed once each ──────────────────────────────────
async function sweep() {
  const srv = await serve(1), page = await pageOn(srv, "sweep");
  const done = new Set(), unnamed = new Set();
  for (let round = 0; round < 3; round++) {
    for (const r of (await look(page)).rail) {
      if (done.has(r.key)) continue;
      if (!(await openItem(page, r.key))) continue;
      // what the row offers: its buttons, and each More menu's items
      const offers = [];
      const s0 = await look(page);
      for (const v of s0.verbs) if (!v.next && v.word !== "▾") offers.push({ id: v.id, word: v.word, menu: -1 });
      const mores = await page.$$("[data-tq-row] button");
      let mi = 0;
      for (const m of mores) {
        if ((await m.evaluate((b) => b.innerText.trim())) !== "▾") continue;
        await m.click(); await wait(600);
        const items = await page.evaluate(() => [...document.querySelectorAll('[role="menuitem"]')].filter((e) => e.getBoundingClientRect().width > 0)
          .map((e) => ({ id: e.getAttribute("data-tq-verb") || "", word: e.innerText.trim() })));
        for (const it of items) {
          offers.push({ ...it, menu: mi });
          if (!named(it.word, it.id) && !unnamed.has(it.word)) { unnamed.add(it.word); note("NAMES", `sweep ${r.text.slice(0, 30)} menu`, `"${it.word}" in the row's More menu is on no list of buttons`); }
        }
        await closePops(page); mi++;
      }
      let left = false;
      for (const o of offers) {
        const verb = verbOfId(o.id) || byLabel[o.word], key = verb && coverOf(verb, o.word);
        if (!key || pressed.has(key)) continue;
        if (!(await openItem(page, r.key))) { left = true; break; }
        const at = page.step = `sweep ${key} on ${r.text.slice(0, 40)}`;
        const before = await look(page);
        if (o.menu >= 0) {
          const ms = []; for (const m of await page.$$("[data-tq-row] button")) if ((await m.evaluate((b) => b.innerText.trim())) === "▾") ms.push(m);
          if (!ms[o.menu]) continue;
          await ms[o.menu].click(); await wait(600);
          const it = await page.evaluateHandle((id, word) => [...document.querySelectorAll('[role="menuitem"]')].find((e) => (id && e.getAttribute("data-tq-verb") === id) || e.innerText.trim() === word) || null, o.id, o.word);
          if (!it.asElement()) { await closePops(page); continue; }
          await it.asElement().click();
        } else {
          const h = await page.$(`[data-tq-row] [data-tq-verb="${o.id}"]`);
          if (!h) continue;
          await h.click();
        }
        mark(key, at);
        await wait(4500);
        const after = await look(page);
        if (sig(after) === sig(before)) note("NOTHING", at, `pressed "${o.word}" and nothing on the screen changed`);
        judge(after, at);
        receipts(before, after, at);
        await closePops(page);
        if (!after.rail.some((x) => x.key === r.key)) { left = true; break; }
      }
      if (!left) done.add(r.key);
    }
  }
  await page.close(); srv.stop();
}

// ── FAULTS: each failure the app knows, forced at the boundary, and its way out pressed ─────────────────────────────────────
async function faults() {
  const srv = await serve(2, { faults: true }), page = await pageOn(srv, "faults");
  const fault = (f) => srv.api("POST", "/api/test/fault", { fault: f });
  // each scenario from the chat as it opens: a fix that opened a place leaves the canvas on it
  const fresh = async () => { await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(4000); };
  const outs = (s) => [...s.verbs.filter((v) => !v.next && !v.off).map((v) => ({ word: v.word, id: v.id, row: true })), ...s.cardBtns.filter((b) => !b.off).map((b) => ({ word: b.word }))];
  // press the draft's Send: on the row when the Advisor put it there, else the card's own
  const send = async () => (await pressVerb(page, "approve")) || (await clickText(page, label("approve"), "[data-tq-task-page]") && (mark("approve", page.step), true));
  // after a forced failure: the screen must carry a way out from the list, and pressing it must do something
  const wayOut = async (at, want, { press = true } = {}) => {
    const s = await look(page);
    judge(s, at);
    const ways = outs(s), hit = want.map((w) => ways.find((x) => (typeof w === "string" ? x.word === w : w(x)))).find(Boolean);
    if (!hit) { note("WAYOUT", at, `expected ${want.map((w) => (typeof w === "string" ? `"${w}"` : w.name || "a fix")).join(" or ")} - the screen offers ${JSON.stringify(ways.map((w) => w.word))}${s.errs[0] ? ` under "${s.errs[0].slice(0, 80)}"` : ""}`); return null; }
    walked.push(`${at}: offered "${hit.word}"`);
    if (!press) return hit;
    const before = s;
    if (hit.id) { const h = await page.$(`[data-tq-row] [data-tq-verb="${hit.id}"]`); if (h) await h.click(); }
    else await clickText(page, hit.word);
    const v = hit.id ? verbOfId(hit.id) : byLabel[hit.word]; mark(v && coverOf(v, hit.word), at);
    await wait(4500);
    const after = await look(page);
    if (sig(after) === sig(before)) note("WAYOUT", at, `"${hit.word}" was offered as the way out and pressing it changed nothing`);
    judge(after, `${at} after "${hit.word}"`);
    await closePops(page);
    return hit;
  };
  const aFix = (x) => /:fix$/.test(x.id || "");
  // a refused recipient is fixed by changing the draft, not by sending it again - Redraft is its way, or the bug report
  const plan = [["auth", [aFix, "Sign in again"]], ["reject", [aFix, label("redraft"), label("report_bug")]],
                ["nomailbox", [aFix, "Connect a mailbox"]], ["unknown", [label("approve", "unknown")]]];
  for (const [f, want] of plan) {
    await fault(f); page.step = `faults ${f}`; await fresh();
    // a draft that can send (a chat's draft is answered where it came from, and shows no Send) and has not failed yet
    let sent = false;
    for (const r of (await look(page)).rail.filter((x) => /🏁/.test(x.text))) {
      if (!(await openItem(page, r.key))) continue;
      if (await send()) { sent = true; break; }
    }
    if (!sent) { note("WAYOUT", page.step, "no draft in the seeded world shows a Send to press"); await fault(""); continue; }
    await wait(6000);
    await wayOut(page.step, want, { press: !["unknown", "reject"].includes(f) });
    if (f === "unknown") {
      const s = await look(page);
      if (!outs(s).some((x) => x.word === label("close"))) note("WAYOUT", page.step, `a send nobody can confirm offers no ${label("close")}`);
      if (outs(s).some((x) => x.word === label("try_again"))) note("WAYOUT", page.step, `${label("try_again")} on a send that may have gone - it would only say "nothing was sent again"`);
    }
    await fault("");
  }
  // the coding tool not installed, and a folder that is not there: Send to agent on a task, the coding agent chosen
  for (const f of ["nocli", "badrepo"]) {
    await fault(f); page.step = `faults ${f}`; await fresh();
    page.expect.add("/dispatch");                                      // its status is the subject here, judged by WAYOUT and WORDS
    const r = await openItem(page, (x) => /📋/.test(x.text));
    if (!r || !(await pressVerb(page, "regular_agent"))) { note("WAYOUT", page.step, "no task with Send to agent to start"); continue; }
    await wait(3000);
    await clickText(page, choice("agent", "coding_agent"));            // the card's question, when it asks which agent
    await wait(5000);
    await wayOut(page.step, [aFix, f === "nocli" ? "Connect a coding tool" : label("pick_repo"), (x) => /coding tool/i.test(x.word)]);
    page.expect.delete("/dispatch"); await fault("");
  }
  // no AI at all: the strip asks for one, with the button that connects it
  page.step = "faults noai"; await fresh();
  const s = await look(page);
  if (!(await page.$('[data-tq-advice="no_ai"] button'))) note("WAYOUT", page.step, "with no AI the Advisor's strip offers no way to connect one");
  else { const before = s; await (await page.$('[data-tq-advice="no_ai"] button')).click(); await wait(3000);
    if (sig(await look(page)) === sig(before)) note("WAYOUT", page.step, "the strip's Connect an AI changed nothing"); await closePops(page); }
  // an act on a task closed behind its open card: the act is refused - with the way to reopen it, never only "reopen it first"
  page.step = "faults closed"; await fresh();
  const t = await openItem(page, (x) => /📋/.test(x.text)), ref = t && ((await look(page)).ref.match(/TQ-(\d+)/) || [])[1];
  if (!ref) note("WAYOUT", page.step, "no task on the rail to close behind its card");
  else {
    const op = await srv.api("POST", "/api/operations", { kind: "task.complete", target: Number(ref), params: {} });
    if (op?.id) await srv.api("POST", `/api/operations/${op.id}/execute`, { version: op.version });
    page.expect.add("/remind"); page.expect.add("/execute");
    if (await pressVerb(page, "defer")) {
      await wait(1500);
      const day = (await page.$$(".MuiPopover-paper button"))[0];
      if (day) { await day.click(); await wait(4500); await wayOut(page.step, [aFix, (x) => /reopen/i.test(x.word)]); }
      else note("WAYOUT", page.step, "Remind me opened no day to pick");
    } else note("WAYOUT", page.step, `the closed task's card shows no ${label("defer")}`);
    page.expect.delete("/remind"); page.expect.delete("/execute");
  }
  // an act that can be undone: Remind me on an open task - its receipt must carry Take it back, and pressing it must put it back
  page.step = "faults undo"; await fresh();
  if (await openItem(page, (x) => /📋/.test(x.text)) && (await pressVerb(page, "defer"))) {
    await wait(1500);
    const day = (await page.$$(".MuiPopover-paper button"))[0];
    if (day) {
      await day.click(); await wait(4500);
      const s = await look(page); judge(s, page.step);
      const tb = label("take_back");
      if (!s.verbs.some((v) => v.word === tb) && !s.chatBtns.includes(tb)) note("UNDO", page.step, `${label("defer")}'s receipt offers no "${tb}" on the bar or under it`);
      else {
        const before = sig(s);
        if ((await pressVerb(page, "take_back")) || (await clickText(page, tb, ".tq-chat-body") && (mark("take_back", page.step), true))) {
          await wait(4000);
          if (sig(await look(page)) === before) note("WAYOUT", page.step, `"${tb}" changed nothing`);
        }
      }
    }
  }
  await page.close(); srv.stop();
}

// ── CARDS: a proposal cancelled then pressed; a task folded by its X then opened again ────────────────────────────────────────
async function cards() {
  const srv = await serve(3), page = await pageOn(srv, "cards");
  // a proposal card: Not ours on an idea asks its own question, Put it on my list proposes; whichever draws a card first
  page.step = "cards cancel";
  let card = null;
  for (const r of (await look(page)).rail) {
    for (const verb of ["not_ours", "mine"]) {
      if (!(await openItem(page, r.key)) || !(await pressVerb(page, verb))) continue;
      await wait(4000);
      card = await page.$(".tq-proposal");
      if (card) break;
    }
    if (card) break;
  }
  if (!card) note("LIVE", page.step, "no press drew a proposal card to cancel - the cancel path was not walked");
  else {
    const btns = await card.$$("button");
    const words = await Promise.all(btns.map((b) => b.evaluate((e) => e.innerText.trim())));
    const ci = words.findIndex((w) => /^(cancel|not now|no|never mind)/i.test(w));
    if (ci < 0) note("LIVE", page.step, `the proposal card has no way to cancel it: ${JSON.stringify(words)}`);
    else {
      page.expect.add("/execute");
      await btns[ci].click(); await wait(3000); walked.push(`cancel: "${words[ci]}" on a proposal card`);
      const live = await card.evaluate((c) => [...c.querySelectorAll("button")].filter((b) => !b.disabled && b.getBoundingClientRect().width > 0).map((b) => b.innerText.trim()));
      if (live.length) {
        note("LIVE", page.step, `cancelled, the card still offers ${JSON.stringify(live)}`);
        const before = await look(page); await (await card.$("button"))?.click(); await wait(3000);
        judge(await look(page), `${page.step} pressed after cancel`); void before;
      }
      page.expect.delete("/execute");
    }
  }
  // fold the task on the table by its X, then open it again from its folded line, then from its rail row
  page.step = "cards fold";
  await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(5000);
  const t = await openItem(page, (x) => /📋/.test(x.text));
  const x = t && await page.$('[data-tq-task-page] [aria-label="Close task"]');
  if (!x) note("FOLD", page.step, `no task on the table with an X to fold it - X buttons on screen: ${JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("[aria-label]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.getAttribute("aria-label")).filter((a) => /close|fold|put/i.test(a))))}, card: ${!!(await look(page)).card}`);
  else {
    await x.click(); await wait(2500);
    let s = await look(page);
    const line = await page.$("[data-tq-folded][role='button']");
    if (!line) note("FOLD", page.step, `folded, the task left no line to open it again (${JSON.stringify(s.folded)})`);
    else {
      await line.click(); await wait(3000); s = await look(page); walked.push("fold: reopened from its folded line");
      if (!s.card) note("FOLD", page.step, "its folded line did not open the task again");
    }
    const x2 = await page.$('[data-tq-task-page] [aria-label="Close task"]');
    if (x2) {
      await x2.click(); await wait(2500);
      const cur = await page.$("[data-tq-rail] [data-tq-key].current");
      if (cur) { await cur.click(); await wait(3000); walked.push("fold: reopened from its rail row"); if (!(await look(page)).card) note("FOLD", page.step, "its rail row, ringed as on the table, did not open it again"); }
    }
  }
  await page.close(); srv.stop();
}

browser = await launch();
const phases = { walk, sweep, faults, cards };
for (const [name, run] of Object.entries(phases)) {
  if (!only.has(name)) continue;
  try { await run(); } catch (e) { note("CRASH", name, `the ${name} pass did not finish: ${e.message.split("\n")[0]}`); }
}
await browser.close();

// COVER: every button on the list, and each of its states, pressed - or skipped for a reason written above
if (only.size === 4) for (const [v, d] of Object.entries(VERBS)) for (const k of [v, ...Object.keys(d.states || {}).map((s) => `${v}:${s}`)])
  if (!pressed.has(k) && !WALK_SKIP[k]) note("COVER", k, `"${label(...k.split(":"))}" was never pressed, and WALK_SKIP gives no reason`);

if (process.argv.includes("--json")) {
  const counts = {};
  for (const f of found) { const r = f.split(" ")[0]; counts[r] = (counts[r] || 0) + 1; }
  console.log(JSON.stringify({ counts, found, pressed: [...pressed.keys()], walked })); process.exit(0);
}
console.log(`pressed ${pressed.size}: ${[...pressed.keys()].join(", ")}`);
console.log(`walked: ${walked.join("; ")}`);
if (found.length) { console.log(`${found.length} dead end${found.length === 1 ? "" : "s"}:\n` + found.join("\n")); process.exit(1); }
console.log("no dead ends: every step had its way on");
