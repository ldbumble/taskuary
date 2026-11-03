// THE BUTTON STRESS (the owner, 2026-11-02: "hitting all the buttons - reply, mark done, continue and everything - still looks smooth and no
// crazy stuff"; "click every button on every task with 100 tasks or 1, clicking buttons fast/slow, multiple times"). Every press lands on a
// fresh copy of its item kind (fixture_changes stress/seed), in a world of ~100 items or of that one item alone (stress/clear), pressed with
// the mouse at the button's place - once, twice fast, three times fast, or once and then another button - and what it left is read back:
// what the server wrote (stress/count, before and after), the requests the page made, page errors and React warnings, receipts, whether
// the card came back after it went, where the walk stood, cut-off text and a page that scrolls sideways. Invented people only.
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { startHarness } from "./harness.mjs";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FILL = ["general", "owed", "draft", "fyi", "general", "owed", "fyi", "report", "goal", "general"];

export async function stressWorld(t, { width = 1440, height = 900, fill = 0, only = false, shots = "" } = {}) {
  const h = await startHarness();
  t?.after?.(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const errors = [], reqs = [], refused = [];   // refused: the demo's own 403 - a send or a start it never makes
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { const s = m.text(); if (/status of 403/.test(s)) return; if (m.type() === "error" || (m.type() === "warning" && /React|Warning:|key|act\(/.test(s))) errors.push(`${m.type()}: ${s.slice(0, 300)}`); });
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/") && r.method() !== "GET" && !u.pathname.startsWith("/api/fixture/")) reqs.push({ t: Date.now(), m: r.method(), p: u.pathname }); });
  page.on("response", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/") && r.status() >= 400 && !u.pathname.startsWith("/api/fixture/")) (r.status() === 403 ? refused : errors).push(`http ${r.status()} ${r.request().method()} ${u.pathname}`); });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
    body: body && JSON.stringify(body) }).then((r) => r.json());
  // A SEND THAT GOES: the demo sends nothing, so the channel's answer is played here, as send-stays-on-closeout plays it - recorded as sent
  // on the server, and counted: two sends of one reply is the thing this whole run is looking for
  const sent = {};
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      sent[rid] = (sent[rid] || 0) + 1;
      await fetch(`${h.fixtureApi}/api/fixture/review/${rid}/sent`, { method: "POST", body: "{}", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" } });
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  if (fill) for (let i = 0; i < fill; i++) await api("/api/fixture/stress/seed", { kind: FILL[i % FILL.length] });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(2000);
  if (shots) await mkdir(shots, { recursive: true });
  return { h, page, errors, reqs, refused, sent, api, only, shots, width, height };
}

const railRows = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((e) => ({ key: e.getAttribute("data-tq-key"), cur: e.classList.contains("current"),
  text: e.innerText.replace(/\s+/g, " ").slice(0, 120) })));

// the item on the table: its rail row pressed (scrolled into reach first), or - a task the rail does not draw - its link
export async function openItem(w, it) {
  const { page } = w;
  let key = null;
  for (let i = 0; i < 40 && !key; i++) {
    key = await page.evaluate((title) => {
      const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].find((e) => e.innerText.includes(title));
      // ...a capped band (Reports, FYI) opened by its chevron first: a hundred items draw only its first rows
      if (!r) document.querySelectorAll('[data-tq-section-head] .fold[aria-expanded="false"]').forEach((f) => f.click());
      if (!r) { const sc = document.querySelector("[data-tq-rail]"); [sc, ...sc.querySelectorAll("*")].forEach((x) => { if (x.scrollHeight > x.clientHeight + 4) x.scrollTop += 600; }); return null; }
      r.scrollIntoView({ block: "center" }); r.querySelector(".card")?.click(); return r.getAttribute("data-tq-key");
    }, it.title);
    if (!key) await sleep(250);
  }
  if (!key && it.taskId) await page.evaluate((id) => { location.hash = `task=${id}`; }, it.taskId);
  if (!key && !it.taskId) return null;
  if (it.taskId) await page.waitForSelector(`[data-tq-task-page="${it.taskId}"]`, { timeout: 20000 }).catch(() => {});
  else await page.waitForFunction((k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, key).catch(() => {});
  await page.waitForNetworkIdle({ idleTime: 400, timeout: 8000 }).catch(() => {});
  await sleep(1200);
  return key || `task:${it.taskId}`;
}

// a button by its verb id on the row, a spine, a pane or a strip; `text:<re>@<scope>` by its words; `menu:<more>/<verb>` inside a ▾
const FIND = `(spec) => {
  const vis = (b) => b && b.offsetParent && b.getBoundingClientRect().width > 0 && !b.disabled && b.getAttribute("aria-disabled") !== "true";
  if (spec.startsWith("text:")) { const [re, scope] = spec.slice(5).split("@"); const rx = new RegExp(re);
    return [...document.querySelectorAll((scope || "body") + " button, " + (scope || "body") + " [role=menuitem]")].find((b) => vis(b) && rx.test(b.textContent.trim())); }
  if (spec.startsWith("item:")) return [...document.querySelectorAll("[role=menu] [role=menuitem]")].find((b) => vis(b) && b.dataset.tqVerb === spec.slice(5));
  if (spec === "next") return [...document.querySelectorAll("[data-tq-row] [data-tq-next]")].find(vis);
  if (spec.startsWith("more:")) return [...document.querySelectorAll("[data-tq-more]")].find((b) => vis(b) && b.dataset.tqMore === spec.slice(5));
  return [...document.querySelectorAll('[data-tq-row] button[data-tq-verb="' + spec + '"], [data-tq-spine-moves] button[data-tq-verb="' + spec + '"], [data-tq-pane-moves] button[data-tq-verb="' + spec + '"], [data-tq-pane-strip] button[data-tq-verb="' + spec + '"]')].find(vis);
}`;
export async function where(page, spec) {
  return page.evaluate((src, spec) => { const b = new Function("return " + src)()(spec); if (!b) return null; b.scrollIntoView({ block: "nearest" });
    const r = b.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2, top = document.elementFromPoint(x, y);
    // ...and what a hand would hit there: a button something else covers is a button nobody can press
    const over = top && !b.contains(top) ? `${top.tagName.toLowerCase()}.${String(top.className?.baseVal ?? top.className).split(" ")[0]} "${(top.innerText || "").trim().slice(0, 30)}"` : null;
    return { x, y, label: b.textContent.trim().slice(0, 40), over }; }, FIND, spec);
}
export const covered = [];
// pressed with the mouse where it stands, `n` times `gap` ms apart - a second press lands on whatever stands there by then, as a hand's does
export async function hit(page, spec, n = 1, gap = 70) {
  // ...once it stands still: a card scrolling into view moves its button under the hand (a hand waits for it to land, and so does this)
  let at = await where(page, spec);
  for (let i = 0; at && i < 15; i++) { await sleep(120); const again = await where(page, spec); if (again && Math.abs(again.x - at.x) < 1 && Math.abs(again.y - at.y) < 1) { at = again; break; } at = again; }
  if (!at) return null;
  if (at.over) covered.push(`${at.label} under ${at.over}`);
  for (let i = 0; i < n; i++) { await page.mouse.click(at.x, at.y); if (i < n - 1) await sleep(gap); }
  return at.label;
}
// a press that sits in a ▾: the ▾ opened, then its entry
async function hitPath(page, steps, n, gap) {
  for (const [i, s] of steps.entries()) {
    const last = i === steps.length - 1;
    for (let k = 0; k < 25 && !(await where(page, s)); k++) await sleep(200);
    const got = await hit(page, s, last ? n : 1, gap);
    if (!got) return { ok: false, at: s };
    if (!last) await sleep(450);
  }
  return { ok: true };
}

// what one look at the page reads: the item's card, the walk, the receipts, the busy buttons, what is cut off
const LOOK = (tid) => {
  const vis = (e) => !!e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0 && getComputedStyle(e).visibility !== "hidden";
  const card = tid ? [...document.querySelectorAll(`[data-tq-task-page="${tid}"]`)].some((e) => vis(e) && !e.closest("[data-tq-folded]")) : null;
  const ell = (b) => [b, ...b.querySelectorAll("*")].some((e) => getComputedStyle(e).textOverflow === "ellipsis");
  const cut = [...document.querySelectorAll("button")].filter((b) => vis(b) && b.textContent.trim() && b.scrollWidth > b.clientWidth + 2 && getComputedStyle(b).overflow !== "visible" && !ell(b))
    .map((b) => b.textContent.trim().slice(0, 30));
  return { card, on: document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || null,
    main: document.querySelector(`[data-tq-task-page="${tid}"] [data-tq-task-body]`)?.dataset.tqMain || null,
    receipts: [...document.querySelectorAll(".tq-msg.receipt, .tq-msg")].slice(-4).map((e) => e.innerText.replace(/\s+/g, " ").trim().slice(0, 200)),
    alerts: [...document.querySelectorAll("[role=alert]")].filter(vis).map((e) => e.innerText.replace(/\s+/g, " ").trim().slice(0, 200)),
    busy: [...document.querySelectorAll("button[aria-busy=true], button .MuiCircularProgress-root")].filter(vis).length,
    sideways: document.scrollingElement.scrollWidth > innerWidth + 1, cut,
    rows: document.querySelectorAll("[data-tq-rail] .tq-pile-row").length };
};

// what to do once a press opened its box: the words typed and its own button pressed - `n` times, as the first press was
export const FINISH = {
  "close-note": async (page, n, gap) => { await page.waitForSelector("[data-tq-close-note-card] textarea, [data-tq-close-note-card] input", { visible: true, timeout: 8000 });
    await page.keyboard.type("Handled on the phone with Erin Blake."); return hit(page, "text:^Close with a note$@[data-tq-close-note-card]", n, gap); },
  remind: async (page, n, gap) => { await until(page, "text:^Tomorrow$"); return hit(page, "text:^Tomorrow$", n, gap); },
  kind: async (page, n, gap) => { await until(page, "text:^your task"); return hit(page, "text:^your task", n, gap); },
  priority: async (page, n, gap) => { await until(page, "text:^important$"); return hit(page, "text:^important$", n, gap); },
  reshape: async (page, n, gap) => { const f = await page.waitForSelector('input[placeholder^="the other job"]', { visible: true, timeout: 8000 });
    await f.type("Check the vendor's bank details"); return hit(page, "text:^Break it in two$", n, gap); },
  hand: async (page, n, gap) => { const f = await page.waitForSelector('input[placeholder^="who should own this"]', { visible: true, timeout: 8000 });
    await f.type("erin@northwind.example"); await page.keyboard.press("Enter"); await sleep(300);
    const box = await page.$('textarea[placeholder^="What they need to know"]'); if (box) await box.type("Can you take this one? The vendor wants an answer today.");
    await until(page, "text:^Send it$"); return hit(page, "text:^Send it$", n, gap); },
};
async function until(page, spec, ms = 8000) { for (const end = Date.now() + ms; Date.now() < end; await sleep(150)) if (await where(page, spec)) return true; return false; }

const ERRWORDS = /could not|couldn.t|went wrong|failed|error|not found|try again|refused|unknown|Failed/i;
const DEMO = /This is the demo/;

/* one press of one button on a fresh item: `mode` once | twice | thrice | then:<spec> (another button 150ms after). Returns what it left. */
export async function press(w, kind, button, mode, { finish = FINISH[button.id], spec = button.spec || button.id } = {}) {
  const { page, api, errors, reqs } = w;
  if (w.only) await api("/api/fixture/stress/clear", {});
  const it = await api("/api/fixture/stress/seed", { kind });
  if (w.only) await sleep(1500);
  // the chat window a press before opened (a refusal said in it) shut, so it covers no move of this item's
  await page.evaluate(() => document.querySelector('[aria-label="Close the chat"]')?.click());
  await page.mouse.move(720, 40);   // the hand off the pill and the cards: a pill grown under a resting mouse covers the moves beside it
  const key = await openItem(w, it);
  const out = { kind, button: button.id, mode, title: it.title, taskId: it.taskId, problems: [] };
  const say = (m) => out.problems.push(m);
  if (!key) { say("its row never came"); return out; }
  const rows0 = await railRows(page);
  const i0 = rows0.findIndex((r) => r.key === key);
  out.below = i0 >= 0 ? rows0[i0 + 1]?.key || null : null;
  const before = await api(`/api/fixture/stress/count?task_id=${it.taskId || 0}`);
  const sends = () => Object.values(w.sent).reduce((a, b) => a + b, 0), s0 = sends();
  const c0 = covered.length, e0 = errors.length, r0 = reqs.length, n = mode === "twice" ? 2 : mode === "thrice" ? 3 : 1;
  const steps = Array.isArray(spec) ? spec : [spec];
  for (let k = 0; k < 20 && !(await where(page, steps[0])); k++) await sleep(250);
  if (!(await where(page, steps[0]))) { say(`no ${steps[0]} to press: ${JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button, [data-tq-spine-moves] button, [data-tq-pane-moves] button, [data-tq-pane-strip] button")].filter((b) => b.offsetParent).map((b) => `${b.dataset.tqVerb || ""}=${b.textContent.trim().slice(0, 20)}${b.disabled ? "(off)" : ""}`)))}`); return out; }
  const t0 = Date.now();
  const went = await hitPath(page, steps, finish ? 1 : n, 70);
  if (!went.ok) say(`could not reach ${went.at}`);
  if (finish) { try { if (!(await finish(page, n, 70))) say("its box had no button to finish with"); } catch (e) { say(`its box: ${e.message.slice(0, 160)}`); } }
  if (mode.startsWith("then:")) { await sleep(150); if (!(await hit(page, mode.slice(5)))) out.secondMissing = true; }
  for (const c of covered.slice(c0)) say(`pressed a covered button: ${c}`);
  // the next five seconds, every 150ms: did the card go and come back, did the walk move and move back
  const looks = [];
  for (let end = Date.now() + 5000; Date.now() < end;) { looks.push({ t: Date.now() - t0, ...(await page.evaluate(LOOK, it.taskId || 0)) }); await sleep(150); }
  const last = looks.at(-1);
  if (it.taskId) {
    const flips = looks.map((l) => l.card).filter((c, i, a) => i && c !== a[i - 1]).length;
    if (flips > 1) say(`the card went and came back (${looks.map((l) => (l.card ? 1 : 0)).join("")})`);
  }
  const ons = looks.map((l) => l.on).filter((o, i, a) => !i || o !== a[i - 1]);
  if (ons.length > 2) say(`the walk moved more than once: ${ons.join(" > ")}`);
  if (ons.length === 3 && ons[0] === ons[2]) say(`the walk moved and came back: ${ons.join(" > ")}`);
  if (looks.some((l) => l.busy) && last.busy) say("a button still busy after 5s");
  if (last.sideways) say("the page scrolls sideways");
  if (last.cut.length) say(`cut-off button text: ${last.cut.join(" | ")}`);
  for (const a of last.alerts) if (ERRWORDS.test(a) && !DEMO.test(a)) say(`alert: ${a}`);
  const newReceipts = [...new Set(looks.flatMap((l) => l.receipts))].filter((s) => !looks[0].receipts.includes(s) || false);
  for (const s of newReceipts) if (ERRWORDS.test(s) && !DEMO.test(s)) say(`receipt: ${s}`);
  out.receipts = newReceipts;
  const after = await api(`/api/fixture/stress/count?task_id=${it.taskId || 0}`);
  out.delta = diff(before, after); out.said = after.said;
  out.chat = await page.evaluate(() => (document.querySelector(".tq-chat-pop-body")?.innerText || "").replace(/\s+/g, " ").trim().slice(-300));
  if (sends() > s0) out.delta.sends = [0, sends() - s0];
  if (sends() - s0 > 1) say(`sent ${sends() - s0} times`);
  out.requests = reqs.slice(r0).map((r) => `${r.m} ${r.p.replace(/\d+/g, "#")}`);
  out.errors = errors.slice(e0); out.refused = w.refused.splice(0);
  for (const e of out.errors) say(e);
  out.on = last.on; out.main = last.main; out.card = last.card; out.rows = last.rows;
  if (w.shots) {
    const base = path.join(w.shots, `${w.only ? "one" : "many"}-${kind}-${button.id.replace(/[^\w-]+/g, "_")}-${mode.replace(/[^\w-]+/g, "_")}`);
    await page.screenshot({ path: `${base}-1440.png` });
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 }); await sleep(700);
    const small = await page.evaluate(LOOK, it.taskId || 0);
    if (small.sideways) say("1280x800: the page scrolls sideways");
    if (small.cut.length) say(`1280x800: cut-off button text: ${small.cut.join(" | ")}`);
    await page.screenshot({ path: `${base}-1280.png` });
    await page.setViewport({ width: w.width, height: w.height, deviceScaleFactor: 1 }); await sleep(400);
  }
  // off the table for the next press: the walk's table emptied by Escape, the link cleared
  await page.keyboard.press("Escape").catch(() => {});
  await page.evaluate(() => { if (location.hash) location.hash = ""; });
  return out;
}

// every button a fresh item of `kind` offers: its moves by verb, each ▾'s entries, Close out's own by their words, and Next and Back
export async function inventory(w, kind) {
  const { page, api } = w;
  if (w.only) await api("/api/fixture/stress/clear", {});
  const it = await api("/api/fixture/stress/seed", { kind });
  if (!(await openItem(w, it))) return [];
  const flat = await page.evaluate(() => {
    const vis = (b) => b.offsetParent && b.getBoundingClientRect().width > 0;
    const moves = [...document.querySelectorAll("[data-tq-row] button, [data-tq-spine-moves] button, [data-tq-pane-moves] button, [data-tq-pane-strip] button")].filter(vis);
    const out = [];
    for (const b of moves) {
      if (b.hasAttribute("data-tq-next")) out.push({ id: "next", label: b.textContent.trim(), off: b.disabled });
      else if (b.hasAttribute("data-tq-back")) out.push({ id: "back", label: "Back", off: b.disabled });
      else if (b.dataset.tqMore) out.push({ more: b.dataset.tqMore });
      else if (b.dataset.tqVerb) out.push({ id: b.dataset.tqVerb, label: b.textContent.trim().slice(0, 40), off: b.disabled });
    }
    for (const b of [...document.querySelectorAll("[data-tq-closeout] button")].filter(vis)) {
      const t = b.textContent.trim();
      if (/^(Send|Redraft|Send anyway|Approve)$/.test(t)) out.push({ id: `closeout-${t.toLowerCase().replace(/\s+/g, "-")}`, spec: `text:^${t}$@[data-tq-closeout]`, label: t, off: b.disabled });
    }
    return out;
  });
  const seen = new Set(), list = [];
  for (const b of flat) {
    if (b.more) {
      await hit(page, `more:${b.more}`); await sleep(450);
      const items = await page.$$eval("[role=menu] [role=menuitem]", (m) => m.map((x) => ({ verb: x.dataset.tqVerb, label: x.textContent.trim().slice(0, 40), off: x.getAttribute("aria-disabled") === "true" })));
      await page.keyboard.press("Escape"); await sleep(300);
      for (const m of items) if (m.verb && !seen.has(m.verb)) { seen.add(m.verb); list.push({ id: m.verb, label: m.label, off: m.off, spec: [`more:${b.more}`, `item:${m.verb}`] }); }
    } else if (!seen.has(b.id)) { seen.add(b.id); list.push(b); }
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page.evaluate(() => { if (location.hash) location.hash = ""; });
  return list;
}

// what changed on the server between two counts, as {path: [before, after]}
export function diff(a, b, at = "") {
  const out = {};
  for (const k of new Set([...Object.keys(a || {}), ...Object.keys(b || {})])) {
    const x = a?.[k], y = b?.[k], p = at ? `${at}.${k}` : k;
    if (x && y && typeof x === "object" && !Array.isArray(x)) Object.assign(out, diff(x, y, p));
    else if (JSON.stringify(x) !== JSON.stringify(y)) out[p] = [x ?? null, y ?? null];
  }
  return out;
}
// a delta as counts: what a press added, so one press and a double press compare by their shape, not their ids
export const shape = (d) => Object.fromEntries(Object.entries(d).filter(([k]) => !/WatchedAt|^said/.test(k)).map(([k, [x, y]]) => [k,
  typeof y === "number" || typeof x === "number" ? (y || 0) - (x || 0) : Array.isArray(y) ? y.map((r) => String(r).replace(/^\d+:/, "")).join(",") : y]));
