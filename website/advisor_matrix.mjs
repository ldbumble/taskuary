// DOES THE ADVISOR'S LINE MATCH THE SCREEN? (the owner, 2026-10-19: "did you test every single advisor interaction matches what's on
// the screen?" - it was not.) Builds a world holding every item kind in every state the Advisor can see (taskuary/faults.world over
// the demo's seed: replies owed, drafted, sent, sent and answered, failed; coding and general agents working, asking, finished, failed,
// stopped and saved; reports, fyi, an idea, goals, meetings, a task put off, one with every todo ticked, one reopened by mail), with
// the demo's scripted Advisor answering (faults.scripted) and the mailbox the faults module's. Then it opens every item, presses every
// button its row and its draft carry - Send once refused by the mail server and once going - and clears a draft's text, and after
// arrival and every press records what the screen says: the Advisor's line, its lit button, the row, the card's state.
//
// DETERMINISTIC RULES (fail the run):
//   EMPTY   the strip under a settled item says nothing - no line, no reason, no Thinking
//   NOLIT   a line is up and no button anywhere is lit - the move it names is not on the screen
//   WORD    the lit button is not the one the line was judged for (/api/advice's label)
//   HIDDEN  the lit button is off the screen or covered (elementFromPoint), a scroll away from the line naming it
//   STALE   after a press the item moved on the server (its advice revision) and the screen still shows the line read before it
//
// THE SEMANTIC READ (a model, not a word list - the owner's rule): every record lands in --out as JSON with its screenshot. Hand the
// file to a model with this brief, one verdict per record: "Each record is one moment on the screen: the Advisor's line, the button it
// lit, the row's buttons, the card's state (statuses, Close out, the agent pane). Does the line say anything the screen contradicts -
// someone waiting on the owner after a reply went with nothing since, an agent working while it asks, a button named that is not
// there or not lit, a past-tense act that did not happen, a line left over from before the press? Is the lit button the move the line
// names, and in view? Is there a line or a reason at all? Answer {i, verdict: ok|mismatch, why}." Fix what it finds at the cause -
// usually evidence the Advisor's prompt lacked, a revision that missed a state change, or a lit verb not on the row.
//
//   node website/advisor_matrix.mjs [--port 7913] [--no-build] [--rounds 4] [--out matrix.json] [--shots dir] [--only sent-quiet,...]
//
// It builds THIS checkout's page into a scratch folder, starts its own servers on throwaway homes (never the owner's 7787), one per
// round: a press that takes the item off the rail is walked, and the item's next button is pressed on the next round's fresh world.
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
import { label } from "./src/buttons.js";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const fixed = process.argv.includes("--port"), port0 = Number(arg("--port", 7913)), build = !process.argv.includes("--no-build");
const rounds = Number(arg("--rounds", 4)), only = arg("--only", "") ? new Set(arg("--only").split(",")) : null;
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = arg("--out", join(tmpdir(), "advisor-matrix.json")), shots = arg("--shots", "");
if (shots) mkdirSync(shots, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const web = build ? mkdtempSync(join(tmpdir(), "tq-matrix-web-")) : "";
if (web && spawnSync("npx", ["vite", "build", "--outDir", web, "--emptyOutDir"], { cwd: join(root, "website"), shell: true, stdio: "ignore" }).status) {
  console.error("the page did not build"); process.exit(2);
}

const found = [], records = [];
const note = (rule, at, what) => found.push(`${rule.padEnd(6)} ${at}: ${what}`);

// ── a server: the demo's world and the matrix's, the faults module's mailbox, the demo's scripted Advisor ─────────────────────────
const freePort = () => new Promise((res, rej) => { const s = createServer(); s.unref(); s.on("error", rej);
  s.listen(0, "127.0.0.1", () => { const { port: p } = s.address(); s.close(() => res(p)); }); });
async function serve(n) {
  const p = fixed ? port0 + (n % 3) : await freePort();
  const home = mkdtempSync(join(tmpdir(), "tq-matrix-"));
  const launchPy = `
import sys, pathlib
from taskuary import server, cli, faults, demo, firstrun
from fastapi.staticfiles import StaticFiles
web = ${JSON.stringify(web)}
if web:
    server._web_root = pathlib.Path(web)
    for r in server.app.routes:
        if getattr(r, 'name', '') in ('assets', 'walk'): r.app = StaticFiles(directory=str(server._web_root / r.name), check_dir=False)
assert faults.install(server.app) and faults.scripted(), 'the faults module refused to install'
demo.seed(server.store); server.store.set_setting(firstrun.DISMISSED, '1', 'walk')
sys.argv = ['taskuary', '--no-browser', '--port', '${p}']; cli.main()`;
  const env = { ...process.env, TASKUARY_HOME: home, TASKUARY_ALLOW_TEST_HOME: "1", TASKUARY_FAULTS: "1" };
  delete env.TASKUARY_DEMO;
  const srv = spawn("python", ["-c", launchPy], { cwd: root, env, stdio: ["ignore", "ignore", "pipe"] });
  let errTail = ""; srv.stderr.on("data", (d) => { errTail = (errTail + d).slice(-1500); });
  const base = `http://127.0.0.1:${p}`;
  let token = "";
  for (let i = 0; i < 90 && !token; i++) {
    await wait(1000);
    if (srv.exitCode !== null) break;
    try { token = (readFileSync(join(home, "config.toml"), "utf8").match(/^token = "([^"]+)"/m) || [])[1] || ""; } catch { /* not yet */ }
    if (token && !(await fetch(`${base}/api/funnel/pile`, { headers: { "X-Taskuary-Token": token } }).then((r) => r.ok).catch(() => false))) token = "";
  }
  if (!token) { srv.kill(); throw new Error(`the matrix server never came up on ${p}: ${errTail.trim().split(/\r?\n/).slice(-3).join(" | ")}`); }
  const H = { "X-Taskuary-Token": token, "Content-Type": "application/json" };
  const api = async (method, path, body) => { const r = await fetch(`${base}${path}`, { method, headers: H, body: body ? JSON.stringify(body) : undefined }); return r.json().catch(() => ({})); };
  await api("POST", "/api/setup/dismiss", { dismissed: true });
  const states = await api("POST", "/api/test/world");
  // the state each task is in, by its ref - and the demo's own items named by what they are
  const name = Object.fromEntries(Object.entries(states).map(([k, t]) => [`TQ-${String(t).padStart(4, "0")}`, k]));
  return { base, token, api, name, stop: () => srv.kill() };
}

// ── what the screen says ────────────────────────────────────────────────────────────────────────────────────────────────────────
const look = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const row = document.querySelector("[data-tq-row]");
  const cards = [...document.querySelectorAll("[data-tq-task-page]")].filter(vis), card = cards[cards.length - 1];
  const strip = [...document.querySelectorAll("[data-tq-strip]")].find(vis);
  const lineEl = document.querySelector('[data-tq-advice=""]'), noneEl = document.querySelector('[data-tq-advice]:not([data-tq-advice=""])');
  const place = (e) => { if (!e) return null; const r = e.getBoundingClientRect(), hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { word: e.innerText.trim(), inView: r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth, covered: !(hit && (hit === e || e.contains(hit))) }; };
  const rowLit = row && [...row.querySelectorAll(".tq-ab.p")].find(vis);
  const cardLit = card && [...card.querySelectorAll(".MuiButton-contained")].find(vis);
  const lit = rowLit ? { ...place(rowLit), where: "row" } : cardLit ? { ...place(cardLit), where: "card" } : null;
  const rowBtns = row ? [...row.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), id: b.getAttribute("data-tq-verb") || (b.hasAttribute("data-tq-next") ? "next" : ""),
    dark: b.classList.contains("p"), off: b.disabled })).filter((b) => b.word) : [];
  const cardBtns = card ? [...card.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), off: b.disabled, lit: b.classList.contains("MuiButton-contained") })).filter((b) => b.word) : [];
  const chips = card ? [...card.querySelectorAll(".MuiChip-label, [data-tq-status]")].filter(vis).map((e) => e.innerText.trim()).filter(Boolean) : [];
  const errs = [...document.querySelectorAll('[role="alert"], .MuiAlert-standardError, .tq-next-err')].filter(vis).map((e) => e.innerText.trim()).filter(Boolean);
  const table = [...document.querySelectorAll("[data-tq-rail] *")].find((e) => e.children.length === 0 && e.innerText?.trim() === "ON THE TABLE");
  const rail = [...document.querySelectorAll("[data-tq-rail] [data-tq-key]")].map((e) => ({ key: e.getAttribute("data-tq-key"), text: e.innerText.replace(/\s+/g, " ").trim() }));
  const ref = (table?.closest("[data-tq-key]")?.innerText.match(/TQ-\d+/) || [])[0] || ((card?.innerText || "").match(/TQ-\d+/) || [])[0] || "";
  const box = card && [...card.querySelectorAll("textarea")].find((t) => vis(t) && !t.readOnly && t.getAttribute("aria-hidden") !== "true");
  return {
    ref, rail, table: table?.closest("[data-tq-key]")?.getAttribute("data-tq-key") || "",
    line: lineEl ? lineEl.querySelector(".tq-next-txt")?.innerText.trim() || "" : "", none: noneEl ? { why: noneEl.getAttribute("data-tq-advice"), line: noneEl.innerText.trim() } : null,
    strip: strip ? { busy: strip.getAttribute("data-tq-strip") === "busy", text: strip.innerText.replace(/\s+/g, " ").trim() } : null,
    lit, row: rowBtns, cardBtns, chips, errs, draft: box ? box.value : null,
    card: card ? card.innerText.replace(/\s+/g, " ").slice(0, 900) : "",
    agentPane: !!document.querySelector(".xterm, [data-tq-terminal], [data-tq-agent-pane]"),
    pops: [...document.querySelectorAll('.MuiPopover-paper, [role="dialog"], .MuiDrawer-paper, [role="menu"]')].filter(vis).map((p) => p.innerText.replace(/\s+/g, " ").slice(0, 120)),
  };
});

let browser;
async function pageOn(srv) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.evaluateOnNewDocument((t) => { try { localStorage.setItem("taskuary_token", t); } catch { /* none */ } }, srv.token);
  page.advice = {};                                                      // the newest /api/advice answer per key
  page.failedAt = 0;
  page.on("response", async (r) => {
    const u = new URL(r.url());
    if (u.pathname === "/api/advice") { const b = await r.json().catch(() => null); if (b) page.advice[u.searchParams.get("key")] = b; }
    if (u.pathname.startsWith("/api/") && r.status() >= 400 && r.request().method() !== "GET" && u.pathname !== "/api/test/fault") page.failedAt = Date.now();
  });
  page.on("pageerror", (e) => note("CRASH", "page", e.message));
  await page.goto(`${srv.base}/`, { waitUntil: "load" });
  await wait(6000);
  for (const b of await page.$$("button")) if (await b.evaluate((e) => e.innerText.trim() === "Walk me through my tasks")) { await b.click(); break; }
  await wait(4000);
  return page;
}
// settled: the strip not thinking, and the same for a second
async function settle(page, ms = 14000) {
  let last = "", same = 0, s = null;
  for (let t = 0; t < ms; t += 500) {
    await wait(500); s = await look(page);
    const k = JSON.stringify([s.line, s.none, s.lit, s.row, s.strip?.busy]);
    same = k === last && !s.strip?.busy ? same + 1 : 0; last = k;
    if (same >= 3) break;
  }
  return s;
}
const openKey = async (page, key) => {
  const h = await page.$(`[data-tq-rail] [data-tq-key="${key}"]`); if (!h) return false;
  await h.click(); return true;
};
const closePops = async (page) => { for (let i = 0; i < 2; i++) { await page.keyboard.press("Escape"); await wait(250); } };

let shotN = 0;
async function record(page, srv, item, step, s) {
  const adv = page.advice[s.table] || page.advice[item.key] || null;
  const rec = { i: records.length, round: srv.round, state: item.state || srv.name[s.ref] || "", key: item.key, moved: !!(item.ref && s.ref !== item.ref), item: item.text.slice(0, 70), ref: s.ref, step,
    line: s.line, none: s.none, advice: adv && { verb: adv.verb, label: adv.label, line: adv.line, none: adv.none, pending: adv.pending, revision: adv.revision },
    lit: s.lit, row: s.row.map((b) => `${b.dark ? "*" : ""}${b.word}${b.off ? " (off)" : ""}`), card: s.cardBtns.map((b) => `${b.lit ? "*" : ""}${b.word}${b.off ? " (off)" : ""}`),
    chips: s.chips, errs: s.errs, draft: s.draft == null ? null : s.draft.slice(0, 120), agentPane: s.agentPane, pops: s.pops, cardText: s.card };
  if (shots) { rec.shot = join(shots, `m${String(shotN++).padStart(3, "0")}.png`); await page.screenshot({ path: rec.shot }).catch(() => {}); }
  records.push(rec);
  writeFileSync(out, JSON.stringify({ found, records }, null, 1));          // as it goes: a long walk can be read before it ends
  // the deterministic rules
  const at = `${rec.state || rec.item} / ${step}`;
  if (s.strip && !s.strip.busy && !s.line && !s.none) note("EMPTY", at, `the strip says nothing: "${s.strip.text.slice(0, 60)}"`);
  if (s.line && !s.lit && !s.pops.length) note("NOLIT", at, `"${s.line.slice(0, 70)}" and no button is lit`);
  if (s.line && s.lit && adv?.label && !s.lit.word.startsWith(adv.label) && !(adv.verb === "fix")) note("WORD", at, `the line was judged for "${adv.label}" and "${s.lit.word}" is lit`);
  if (s.line && s.lit && !s.pops.length && (!s.lit.inView || s.lit.covered)) note("HIDDEN", at, `the lit "${s.lit.word}" (${s.lit.where}) is ${s.lit.inView ? "covered" : "off the screen"}`);
  return rec;
}

// ── the walk: a round per fresh world; each item opened, each of its buttons pressed once over the rounds ──────────────────────────
const done = new Set();                       // `${state or item}|${button}` pressed
const SEND = label("approve"), REDRAFT = label("redraft");
async function round(n) {
  const srv = await serve(n); srv.round = n;
  const page = await pageOn(srv);
  let pressedAny = false;
  try {
    const items = (await look(page)).rail;
    for (const it of items) {
      try {
      if (!(await openKey(page, it.key))) continue;
      let s = await settle(page);
      const id = srv.name[s.ref] || it.text.replace(/\d+[hm]\b|< ?1h/g, "").slice(0, 40).trim();
      it.state = srv.name[s.ref] || ""; it.ref = s.ref;
      if (only && !only.has(it.state)) continue;
      if (n === 0) await record(page, srv, it, "arrive", s);
      // what can be pressed: the row's buttons and menu items, the draft's Send and Redraft under it, and clearing the draft's text
      const offers = [...s.row.filter((b) => b.id !== "next" && b.word !== "▾" && !b.off).map((b) => ({ word: b.word, id: b.id, at: "row" })),
        ...s.cardBtns.filter((b) => !b.off && (b.word === SEND || b.word === REDRAFT) && !s.row.some((r) => r.word === b.word)).map((b) => ({ word: b.word, at: "card" }))];
      for (const m of await page.$$("[data-tq-row] [data-tq-more]")) {
        await m.click(); await wait(500);
        const items2 = await page.evaluate(() => [...document.querySelectorAll('[role="menuitem"]')].filter((e) => e.getBoundingClientRect().width > 0 && !e.classList.contains("Mui-disabled"))
          .map((e) => ({ word: e.innerText.trim(), id: e.getAttribute("data-tq-verb") || "" })));
        items2.forEach((x) => offers.push({ ...x, at: "menu" }));
        await closePops(page);
      }
      // ...the draft's text cleared first, while its Send is still the move: Send greys, and the strip must still say something
      if (s.draft != null && s.draft.trim()) offers.unshift({ word: "(clear the draft)", at: "clear" });
      // Send twice: refused by the mail server, then going
      const isSend = (o) => o.word === SEND || (/:approve$/.test(o.id || "") && o.word.startsWith(SEND));
      const plan = offers.flatMap((o) => (isSend(o) ? [{ ...o, fault: "reject" }, { ...o, fault: "" }] : [o]));
      for (const o of plan) {
        const k = `${id}|${o.word}|${o.fault ?? ""}`;
        if (done.has(k)) continue;
        done.add(k); pressedAny = true;
        if (!(await openKey(page, it.key))) break;
        const before = await settle(page, 8000);
        await srv.api("POST", "/api/test/fault", { fault: o.fault || "" });
        const t0 = Date.now();
        let ok = true;
        try {
        if (o.at === "row") { const h = await page.$(`[data-tq-row] [data-tq-verb="${o.id}"]`); ok = !!h && (await h.click(), true); }
        else if (o.at === "menu") {
          ok = false;
          for (const m of await page.$$("[data-tq-row] [data-tq-more]")) {
            await m.click(); await wait(500);
            const h = await page.evaluateHandle((w) => [...document.querySelectorAll('[role="menuitem"]')].find((e) => e.innerText.trim() === w) || null, o.word);
            if (h.asElement()) { await h.asElement().click(); ok = true; break; }
            await closePops(page);
          }
        } else if (o.at === "card") {
          ok = await page.evaluate((w) => { const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((x) => x.innerText.trim() === w && x.getBoundingClientRect().width > 0 && !x.disabled);
            b?.click(); return !!b; }, o.word);
        } else if (o.at === "clear") {
          const box = await page.$("[data-tq-task-page] textarea:not([aria-hidden='true']):not([readonly])");
          ok = !!box && (await box.click(), await page.keyboard.down("Control"), await page.keyboard.press("a"), await page.keyboard.up("Control"),
            await page.keyboard.press("Backspace"), true);
        }
        if (!ok) continue;
        await wait(2500);
        } catch (e) { note("CRASH", `${it.state || id} / ${o.word}`, e.message.split("\n")[0]); await closePops(page).catch(() => {}); continue; }
        const pops = (await look(page)).pops; void t0;
        const after = await settle(page);
        const step = `after ${o.word}${o.fault ? ` (mail server: ${o.fault})` : isSend(o) ? " (it goes)" : ""}`;
        await record(page, srv, it, step, after);
        // STALE: the item moved on the server and the screen still shows the line read before it moved
        const now = after.table && await srv.api("GET", `/api/advice?key=${encodeURIComponent(after.table)}`);
        const shown = page.advice[after.table];
        if (now?.verb && shown && !shown.pending && shown.revision !== now.revision && !pops.length)
          note("STALE", `${it.state || id} / ${step}`, `the screen shows the line read at ${shown.revision || "no revision"} ("${String(shown.line || shown.none || "").slice(0, 50)}"), the item is at ${now.revision} ("${String(now.line).slice(0, 50)}")`);
        await closePops(page);
        await srv.api("POST", "/api/test/fault", { fault: "" });
        // ...and the cleared draft written back, so the presses after it act on the draft as it was
        if (o.at === "clear") { const box = await page.$("[data-tq-task-page] textarea:not([aria-hidden='true']):not([readonly])"); if (box) { await box.click(); await page.keyboard.type(s.draft); } }
        if (!(await look(page)).rail.some((x) => x.key === it.key)) break;     // it left the rail: its next button waits for the next world
      }
      } catch (e) { note("CRASH", `${it.state || it.text.slice(0, 40)}`, e.message.split("\n")[0]); }
    }
  } finally { await page.close(); srv.stop(); }
  return pressedAny;
}

browser = await launch();
for (let n = 0; n < rounds; n++) {
  try { if (!(await round(n)) && n) break; } catch (e) { note("CRASH", `round ${n}`, e.message.split("\n")[0]); }
}
await browser.close();
writeFileSync(out, JSON.stringify({ found, records }, null, 1));
console.log(`${records.length} records, ${done.size} presses -> ${out}`);
if (found.length) { console.log(`${found.length} mismatch${found.length === 1 ? "" : "es"}:\n${found.join("\n")}`); process.exit(1); }
console.log("every line matched its screen on the deterministic rules");
