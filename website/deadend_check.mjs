// Does the walk ever leave the owner alone? Clicks through a fresh demo world, writes switched ON, and fails on a dead end.
//
// Tests read the source; a dead end only shows on the screen. The 2026-10-17 click-through found five that every test passed:
// "Open TQ-0001" opened TQ-0010 (three chips shared one row id), a task card landed with only its header in view, a failed
// send said "add one under Connections" with nothing to press, a closed task left no line saying so, and Next stood dark
// over an agent waiting on the owner. Each is one rule below, checked at every step of the walk:
//
//   DARK      the bar is dark only when the Advisor spoke, and then on one button - never a fallback of its own (the owner,
//             2026-10-17: "nothing dark until advisor ... keep it ai")
//   SEEN      the card on the table shows more than its header
//   FIX       an error on screen has a way out on the row - a verb that is not Next
//   RECEIPT   an item that leaves the rail leaves a line in the chat naming it
//   OPENS     a chip that says "Open TQ-x" puts TQ-x on the table
//
//   WORDS     no developer word on the card, the row or the Advisor's line (words.json's jargon - the plain-words audit, 2026-10-17)
//   NAMES     every button the row shows is a named button - a label (or a state's label) in buttons.json - so the bar never
//             grows a word that is not on the one list (the owner, 2026-10-17: "make a complete list of buttons")
//   CALLS     no /api request fails while the walk runs
//
//   node website/deadend_check.mjs [--port 7799] [--keep] [--no-build]    # exits 1 with every finding
//
// It builds the page from THIS checkout's source into a scratch folder (--no-build: the committed bundle), starts its own
// server on a throwaway home (never the owner's 7787), demo world, every write allowed, and drives it.
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
import { JARGON_RES } from "./src/words.js";
import { ALL_LABELS } from "./src/buttons.js";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const port = Number(arg("--port", 7799)), keep = process.argv.includes("--keep"), build = !process.argv.includes("--no-build");
const root = join(dirname(fileURLToPath(import.meta.url)), ".."), home = mkdtempSync(join(tmpdir(), "tq-deadend-"));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// words the owner should never have to read: the one list the server's sentences are held to as well (taskuary/words.json) - and
// what only a crash leaves on a screen, which is no word anyone chose
const JARGON = [...JARGON_RES, /\bnull\b/, /\bundefined\b/, /Traceback/, /\b[45]\d\d(?= \()/];
// a word on the row that is no named button: not a label on the list, not a state's label, not a working state ("Sending…"), not
// the More arrow, and not an item's own name (the end of the walk's "Open TQ-12 · ...")
const NAMED = new Set(ALL_LABELS.map((l) => l.trim()));
// ...nor a failed send's fix ('<rid>:fix'), which wears the fix's own words ("Connect a mailbox") - buttons.json says so of `fix`
const named = (w, id = "") => !w || NAMED.has(w) || /…$/.test(w) || w === "▾" || /^Open TQ-\d+/.test(w) || /:fix$/.test(id);
const web = build ? mkdtempSync(join(tmpdir(), "tq-deadend-web-")) : "";
if (build && spawnSync("npx", ["vite", "build", "--outDir", web, "--emptyOutDir"], { cwd: join(root, "website"), shell: true, stdio: "ignore" }).status) {
  console.error("the page did not build"); process.exit(2);
}

// the demo world with its doors open: a send FAILS for real (no mailbox), Done really closes - the paths a refusal would hide
// ...and the page built from this checkout served in place of the committed one: its mounts are made at import, so they are re-pointed
const LAUNCH = `
import sys, pathlib; from taskuary import demo, cli, server
from fastapi.staticfiles import StaticFiles
demo.REFUSALS = (); demo.ALLOWED_WRITES = (r'.*',); demo.ALLOWED_METHODS = {'POST', 'PATCH', 'PUT', 'DELETE'}; demo.refuse_op = lambda op: ''
web = ${JSON.stringify(web)}
if web:
    server._web_root = pathlib.Path(web)
    for r in server.app.routes:
        if getattr(r, 'name', '') in ('assets', 'walk'): r.app = StaticFiles(directory=str(server._web_root / r.name), check_dir=False)
sys.argv = ['taskuary', '--demo', '--no-browser', '--port', '${port}']; cli.main()`;
const srv = spawn("python", ["-c", LAUNCH], { cwd: root, env: { ...process.env, TASKUARY_HOME: home, TASKUARY_ALLOW_TEST_HOME: "1", TASKUARY_DEMO: "1" }, stdio: "ignore" });
const base = `http://127.0.0.1:${port}`;
const stop = () => { if (!keep) srv.kill(); };
let token = "";
for (let i = 0; i < 60 && !token; i++) {
  await wait(1000);
  try { token = (readFileSync(join(home, "config.toml"), "utf8").match(/^token = "([^"]+)"/m) || [])[1] || ""; } catch { /* not written yet */ }
  if (token && !(await fetch(`${base}/api/funnel/pile`, { headers: { "X-Taskuary-Token": token } }).then((r) => r.ok).catch(() => false))) token = "";
}
if (!token) { stop(); console.error("the demo server never came up"); process.exit(2); }
const { key } = await (await fetch(`${base}/api/launch-key`, { method: "POST", headers: { "X-Taskuary-Token": token } })).json();

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1366, height: 768 });            // a laptop: where "the card is off the screen" happens
const found = [], note = (rule, at, what) => found.push(`${rule.padEnd(7)} ${at}: ${what}`);
page.on("pageerror", (e) => note("CRASH", "page", e.message));
let step = "start";
page.on("response", (r) => {
  const u = new URL(r.url());
  if (u.pathname.startsWith("/api/") && r.status() >= 400) note("CALLS", step, `${r.request().method()} ${u.pathname} answered ${r.status()}`);
});
await page.goto(`${base}/?k=${key}`, { waitUntil: "load" });
await wait(6000);

// one read of everything the rules look at
const look = () => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const row = document.querySelector("[data-tq-row]"), chat = document.querySelector(".tq-chat-body");
  const verbs = row ? [...row.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), id: b.getAttribute("data-tq-verb") || "", dark: b.classList.contains("p"), next: b.hasAttribute("data-tq-next"), off: b.disabled })) : [];
  const cards = [...document.querySelectorAll("[data-tq-task-page]")].filter(vis), card = cards[cards.length - 1];
  window.__tqCards = cards.map((c) => { const r = c.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height), c.className.slice(0, 40)]; });
  const cr = card?.getBoundingClientRect(), hr = chat?.getBoundingClientRect(), rr = row?.getBoundingClientRect();
  const errs = [...document.querySelectorAll('[role="alert"], .MuiAlert-standardError, .tq-next-err')].filter(vis).map((e) => e.innerText.trim()).filter(Boolean);
  const rail = [...document.querySelectorAll("[data-tq-rail] [data-tq-key]")].map((e) => ({ key: e.getAttribute("data-tq-key"),
    text: e.innerText.replace(/\s+/g, " ").trim(), title: (e.querySelector(".card b")?.innerText || "").trim() }));
  const table = [...document.querySelectorAll("[data-tq-rail] *")].find((e) => e.children.length === 0 && e.innerText?.trim() === "ON THE TABLE");
  const ref = (table?.closest("[data-tq-key]")?.innerText.match(/TQ-\d+/) || [])[0] || ((card?.innerText || "").match(/TQ-\d+/) || [])[0] || "";
  const read = [card?.innerText || "", row?.innerText || "", document.querySelector("[data-tq-advice]")?.innerText || ""].join("\n");
  // the no-AI strip asks for an AI - it picks nothing, so nothing on the bar may be dark under it (CI's demo has no CLI to ask)
  return { verbs, advice: !!document.querySelector('[data-tq-advice]:not([data-tq-advice="no_ai"])'), adv: document.querySelector('[data-tq-advice]:not([data-tq-advice="no_ai"])')?.innerText || "",
    errs, rail, ref, read, chat: chat?.innerText || "",
    cards: window.__tqCards, card: card ? { top: cr.top, shown: Math.min(cr.bottom, rr ? rr.top : hr.bottom) - Math.max(cr.top, hr.top) } : null };
});
const press = async (word) => {
  const hs = await page.$$("[data-tq-row] button");
  for (const h of hs) if ((await h.evaluate((b) => b.innerText.trim())) === word) { await h.click(); return true; }
  return false;
};
const judge = (s, at) => {
  const dark = s.verbs.filter((v) => v.dark);
  if (s.card || s.ref) {
    if (!s.advice && dark.length) note("DARK", at, `"${dark.map((v) => v.word).join('", "')}" dark with no Advisor line over it`);
    if (s.advice && dark.length !== 1) note("DARK", at, `the Advisor spoke and ${dark.length} buttons are dark - ${JSON.stringify(s.verbs.map((v) => v.word))} / "${s.adv.slice(0, 80)}"`);
  }
  if (s.card && s.card.shown < 120) note("SEEN", at, `only ${Math.round(s.card.shown)}px of the card on the table is in view ${JSON.stringify(s.cards)}`);
  if (s.errs.length && !s.verbs.some((v) => !v.next && !v.off)) note("FIX", at, `"${s.errs[0].slice(0, 90)}" and nothing on the row but Next`);
  for (const w of JARGON) { const m = s.read.match(w); if (m) note("WORDS", at, `"${m[0]}" in "${s.read.slice(Math.max(0, m.index - 40), m.index + 40).replace(/\s+/g, " ")}"`); }
  const odd = [...new Set(s.verbs.filter((v) => !named(v.word, v.id)).map((v) => v.word))];
  if (odd.length) note("NAMES", at, `on the row but on no list of buttons: ${JSON.stringify(odd)}`);
};
const receipts = (before, after, at) => {
  const keys = new Set(after.rail.map((r) => r.key));
  for (const r of before.rail.filter((r) => !keys.has(r.key))) {
    // a line NAMING it: its ref, or its subject - a report or a message folds to its title line, a batch of fyi to its own line
    // ("✓ Read - 4 fyi let go") which names none of them, so a message that went in a batch counts the batch's line
    const ref = (r.text.match(/TQ-\d+/) || [])[0], name = ref || r.title.replace(/…$/, "").slice(0, 30);
    if (name && !after.chat.includes(name) && !(r.key.startsWith("processing:") && !ref && /fyi let go/.test(after.chat)))
      note("RECEIPT", at, `${name} left the rail with no line saying where it went`);
  }
};

// THE WALK: start it, and at each card do the thing its first line invites - send a draft, close an agent's task, read the fyi -
// so the failure paths run too; otherwise Next. Stops at the end line, then checks every Open chip it offers.
const start = await page.$$("button");
for (const b of start) if ((await b.evaluate((e) => e.innerText.trim())) === "Walk me through my tasks") { await b.click(); break; }
await wait(6000);
let s = await look(), sent = false, closed = false;
const seen = new Map();
for (let n = 0; n < 40; n++) {
  const at = step = `step ${n} ${s.ref || "(no item)"}`;
  judge(s, at);
  const words = s.verbs.map((v) => v.word);
  if (words.some((w) => w.startsWith("Open TQ"))) break;
  const before = s;
  if (!sent && words.includes("Send")) { sent = true; await press("Send"); }
  else if (!closed && words.includes("End")) {
    closed = true; await press("Done"); await wait(1200);
    for (const b of await page.$$('[role="dialog"] button')) if (/mark done/i.test(await b.evaluate((e) => e.innerText))) { await b.click(); break; }
  }
  else if (words.includes("All read, next")) await press("All read, next");
  else if (!(await press("Next →")) && !(await press("Next"))) {
    // BUTTONS IN A CHAT LINE are against the owner's rule ("no button in line ever ... it should on bottom by the prompt", 2026-10-06):
    // said, then pressed, so the walk can go on past it
    const inline = await page.$$(".tq-chat-body .tq-msg button, .tq-chat-body [data-tq-proposal] button");
    const words = await Promise.all(inline.map((h) => h.evaluate((b) => b.innerText.trim())));
    if (!inline.length) { note("FIX", at, `no Next on the row and nothing in the chat - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
    note("INLINE", at, `the way on is in the chat, not on the row: ${JSON.stringify(words.filter(Boolean))} - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`);
    await inline[0].click();
  }
  await wait(5000);
  s = await look();
  if (process.env.DEADEND_SHOTS) await page.screenshot({ path: join(process.env.DEADEND_SHOTS, `${String(n).padStart(2, "0")}.png`) });
  judge(s, `${at} after`);
  receipts(before, s, at);
  // the same screen three presses running: whatever was pressed changed nothing, and the owner would be pressing it still
  const sig = JSON.stringify([s.ref, s.verbs.map((v) => v.word), s.chat.length]);
  seen.set(sig, (seen.get(sig) || 0) + 1);
  if (seen.get(sig) >= 3) { note("STUCK", at, `three presses left the same screen - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
}
// OPENS: every chip on the end line, one at a time, must put its own TQ on the table
const opens = s.verbs.map((v) => v.word).filter((w) => w.startsWith("Open TQ"));
for (const w of opens) {
  const want = w.match(/TQ-\d+/)[0];
  if (!(await press(w))) continue;
  await wait(5000);
  const got = await look();
  if (got.ref !== want) note("OPENS", w, `put ${got.ref || "nothing"} on the table`);
  judge(got, w);
  break;                                       // the chips are gone once one opens; the first one is the test
}

await browser.close(); stop();
// --json: the counts per rule, for browser/deadends.test.mjs to hold against its baseline
if (process.argv.includes("--json")) {
  const counts = {};
  for (const f of found) { const r = f.split(" ")[0]; counts[r] = (counts[r] || 0) + 1; }
  console.log(JSON.stringify({ counts, found })); process.exit(0);
}
if (found.length) { console.log(`${found.length} dead end${found.length === 1 ? "" : "s"}:\n` + found.join("\n")); process.exit(1); }
console.log("no dead ends: every step had its way on");
