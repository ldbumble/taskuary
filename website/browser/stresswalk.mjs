// THE WALK HAMMERED (the owner, 2026-11-02: "clicking the walk-through buttons 10 times, clicking Next on 50 tasks in a row, hitting Next then
// Back quickly ... everything still looks smooth and no crazy stuff"). What the stress-walk-* files share: a big world or a one-row world
// (POST /api/fixture/walk/big), the walk's answers held 0/300/1500 ms in the page, a recorder that samples every animation frame, and the
// checks every scenario ends on. Long: not in test:browser - run them by name.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { startHarness } from "./harness.mjs";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const SHOTS = process.env.STRESS_SHOTS || path.join(process.env.TEMP || "/tmp", "stress-walk");
const WALK = /\/api\/(concierge\/(stream|next|act)|walk\/|funnel\/settle|operations\/[^/]+\/execute)/;

// one server per file, a fresh page and world per case: `delay` ms on every walk answer (held in the page, as a slow brain is)
export async function server(t) { const h = await startHarness(); t.after(() => h.close()); return h; }
export async function open(h, { width = 1440, height = 900, delay = 0, world = {} } = {}) {
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then(async (r) => { if (!r.ok) throw new Error(`${p}: ${r.status} ${await r.text()}`); return r.json(); });
  const seeded = await api("/api/fixture/walk/big", world);
  // keys said by their titles in a failure, as the world was laid out
  const titles = new Map((await api("/api/funnel/pile")).items.flatMap((i) => [i.key, ...(i.aliases || [])].map((k) => [k, i.title])));
  const name = (s) => String(s).replace(/processing:pi_\w+|fyis:[\w:,-]+|meeting:[^,|/ ]+ [^,|/ ]+/g, (k) => titles.has(k) ? `"${String(titles.get(k)).slice(0, 40)}"` : k);
  const page = await h.newPage(), errors = [];
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  if (delay) await page.evaluateOnNewDocument((ms, src) => {
    const re = new RegExp(src), open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send, f0 = window.fetch;
    XMLHttpRequest.prototype.open = function (m, url, ...rest) { this.__url = String(url); return open.call(this, m, url, ...rest); };
    XMLHttpRequest.prototype.send = function (...a) {
      if (re.test(this.__url)) for (const k of ["onreadystatechange", "onloadend", "onload"]) { const f = this[k]; if (f) this[k] = (...e) => setTimeout(() => f.apply(this, e), ms); }
      return send.apply(this, a);
    };
    window.fetch = (u, ...a) => re.test(String(u?.url || u)) ? f0(u, ...a).then((r) => new Promise((ok) => setTimeout(() => ok(r), ms))) : f0(u, ...a);
  }, delay, WALK.source);
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { const s = m.text();
    if (m.type() === "error" && !/Failed to load resource|ERR_BLOCKED_BY_CLIENT|fonts\.g/.test(s)) errors.push(`console: ${s.slice(0, 300)}`);
    if (/unique "key"|same key/.test(s)) errors.push(`react key: ${s.slice(0, 300)}`); });
  // THE BUILT APP by default - the bundle the server itself serves (taskuary/web), as the owner runs it: frame times on the dev server are
  // React's development build's, several times slower. STRESS_DEV=1 runs the dev server instead (React's key warnings speak only there).
  // The built page talks to its own origin: the harness's guard and websocket fence, which allow the dev server's alone, let it through.
  const built = !process.env.STRESS_DEV;
  if (built) {
    page.off("request", page.fixtureRequestGuard);
    page.on("request", (r) => (new URL(r.url()).origin === h.fixtureApi ? r.continue() : page.fixtureRequestGuard(r)));
    await page.evaluateOnNewDocument(() => { const N = Object.getPrototypeOf(window.WebSocket); if (N?.prototype instanceof EventTarget) window.WebSocket = N; });
  }
  await page.goto(built ? h.fixtureApi : h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(1500);
  await newChat(page);              // each case on a chat of its own: what the case before it said is not this one's
  return { page, errors, api, seeded, name, close: () => page.close().catch(() => {}) };
}

// ── what is on the screen ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
export const look = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
  const card = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter(vis).pop();
  const live = [...document.querySelectorAll(".tq-chat-body .tq-live-card, .tq-chat-body .tq-canvas-live")].filter(vis).some((e) => e.innerText.trim().length > 10);
  const rows = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")];
  return {
    card: card?.getAttribute("data-tq-canvas-item") || null, item: live, dots: [...document.querySelectorAll(".tq-typing")].some(vis),
    end: [...document.querySelectorAll("button")].some((b) => /^Walk me through/.test(b.textContent.trim()) && vis(b)) || [...document.querySelectorAll(".tq-pile-empty")].some(vis),
    ring: rows.filter((e) => e.classList.contains("current") || e.classList.contains("inbatch")).map((e) => e.getAttribute("data-tq-key")),
    rail: rows.filter((e) => !e.classList.contains("landing")).map((e) => [e.closest("[data-tq-run]")?.dataset.tqRun, e.getAttribute("data-tq-key")]),
    heads: Object.fromEntries([...document.querySelectorAll("[data-tq-run]")].map((b) => [b.dataset.tqRun, +(b.querySelector(".tq-pile-head em")?.textContent || 0)])),
    next: (() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); return b ? { on: !b.disabled, text: b.textContent.trim() } : null; })(),
    back: (() => { const b = document.querySelector("[data-tq-walk-back]"); return b ? !b.disabled : null; })(),
    errorReceipts: [...document.querySelectorAll(".tq-msg")].filter((e) => /went wrong|failed|could not|error/i.test(e.innerText)).map((e) => e.innerText.slice(0, 120)),
    folded: [...document.querySelectorAll("[data-tq-folded]")].map((e) => e.getAttribute("data-tq-folded")),
    lines: [...document.querySelectorAll(".tq-msg:not(.you)")].map((e) => e.innerText.replace(/\s+/g, " ").trim().slice(0, 60)),
    cheer: [...document.querySelectorAll(".tq-pile-cheer, [data-tq-cheer]")].map((e) => e.textContent.trim()).join(" "),
  };
});

// every animation frame: the card on the table, item/dots/end, the ring, and the rail's order (keys by their drawn top)
export const record = (page) => page.evaluate(() => {
  window.__sf = []; window.__sp = []; window.__srec = true; window.__slast = null;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
  const tick = () => {
    if (!window.__srec) return;
    const card = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter(vis).pop();
    const live = [...document.querySelectorAll(".tq-chat-body .tq-live-card, .tq-chat-body .tq-canvas-live")].filter(vis).some((e) => e.textContent.trim().length > 10);
    const rows = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter((e) => !e.classList.contains("landing"));
    const keys = rows.map((e) => e.getAttribute("data-tq-key")), order = keys.join("|"), changed = order !== window.__slast;
    window.__slast = order;
    window.__sf.push({ t: performance.now(), card: card?.getAttribute("data-tq-canvas-item") || null, item: live,
      dots: [...document.querySelectorAll(".tq-typing")].some(vis),
      end: [...document.querySelectorAll("button")].some((b) => /^Walk me through/.test(b.textContent.trim()) && vis(b)) || [...document.querySelectorAll(".tq-pile-empty")].some(vis),
      ring: rows.filter((e) => e.classList.contains("current")).map((e) => e.getAttribute("data-tq-key")).join(","),
      bk: (() => { const b = document.querySelector("[data-tq-walk-back]"); return b ? !b.disabled : null; })(),
      nx: (() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); return b ? !b.disabled : null; })(),
      // ...and on a frame with nothing on the table, what the chat's last lines are, for the failure to say
      dbg: live ? undefined : [...document.querySelectorAll(".tq-chat-body .tq-msg")].slice(-3).map((e) => { const r = e.getBoundingClientRect();
        return `${e.className.replace(/\s+/g, ".")}:${e.textContent.trim().length}@${Math.round(r.top)}-${Math.round(r.bottom)}`; }).join(" "),
      dup: changed && keys.length !== new Set(keys).size ? keys.filter((k, i) => keys.indexOf(k) !== i) : null, order: changed ? order : null });
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
export const stopRecord = (page) => page.evaluate(() => { window.__srec = false; const p = window.__sp || []; window.__sp = []; return { f: window.__sf || [], p }; });

// what the frames say: the longest blank run (no item, no dots, no end), dup rows, and rows that changed order
export function frames({ f: fs0, p: presses = [] }) {
  let blank = 0, run = 0, from = null, blankAt = null, blankCtx = null;
  for (let i = 1; i < fs0.length; i++) {
    const f = fs0[i];
    if (!f.item && !f.dots && !f.end) { if (from === null) from = fs0[i - 1].t; run = f.t - from; if (run > blank) { blank = run; blankAt = Math.round(from - fs0[0].t); blankCtx = [`${fs0[i].card}|${fs0[i].ring}`, fs0[i].dbg]; } } else from = null;
  }
  const dups = [...new Set(fs0.filter((f) => f.dup).map((f) => f.dup.join(",")))];
  // ROWS NEVER MOVE: two rows drawn in one frame and the next keep their order (a row may come or go, never pass another)
  // ...and the ring's way down the rail, read in the frame it moved: each step down or up
  const moved = [], steps = [], ups = [];
  let at = null, was = null;
  for (const f of fs0) {
    if (f.order !== null) {
      const now = new Map(f.order.split("|").filter(Boolean).map((k, i) => [k, i]));
      if (at) {
        const both = [...now.keys()].filter((k) => at.has(k));
        for (let i = 1; i < both.length; i++) if (at.get(both[i - 1]) > at.get(both[i])) { moved.push(`${both[i - 1]} / ${both[i]}`); break; }
      }
      at = now;
    }
    if (f.ring && f.ring !== was) {
      const a = at?.get(was?.split(",")[0]), b = at?.get(f.ring.split(",")[0]);
      if (a != null && b != null) { steps.push(Math.sign(b - a)); if (b < a) ups.push(`${was} -> ${f.ring}`); }
      was = f.ring;
    }
  }
  const gaps = fs0.slice(1).map((f, i) => f.t - fs0[i].t);
  // PRESS TO DRAW: from a press to the first frame whose ring is not the one it was pressed on (presses that moved nothing are not counted)
  const lat = [];
  for (const [n, p] of presses.entries()) {
    const i = fs0.findIndex((f) => f.t >= p);
    if (i < 1) continue;
    const was = fs0[i - 1], j = fs0.findIndex((f, k) => k >= i && (f.ring !== was.ring || f.card !== was.card));
    if (j > 0 && fs0[j].t - p < 3000 && !(fs0[j].t > presses[n + 1])) lat.push(fs0[j].t - p);
  }
  lat.sort((a, b) => a - b);
  // A BUTTON THAT GREYS FOR A MOMENT: on, then greyed (or gone) under a second, then on again - a press in that moment is lost
  const flicker = (k) => { let n = 0, off = null, on = false;
    for (const f of fs0) { if (f[k]) { if (on && off !== null && f.t - off < 1000) n++; on = true; off = null; } else if (on && off === null) off = f.t; }
    return n; };
  const pct = (q) => lat.length ? Math.round(lat[Math.min(lat.length - 1, Math.floor(q * lat.length))]) : null;
  return { n: fs0.length, blank: Math.round(blank), blankAt, dups, moved: [...new Set(moved)].slice(0, 5), worstFrame: Math.round(Math.max(0, ...gaps)),
    down: steps.filter((x) => x > 0).length, up: steps.filter((x) => x < 0).length, ups: ups.slice(0, 3), blankCtx, draw: { p50: pct(0.5), p95: pct(0.95), max: pct(1), n: lat.length }, flicker: { back: flicker("bk"), next: flicker("nx") } };
}

// SETTLED: the ring, dots and the rail unchanged for ~1.5 s
export async function settle(page, ms = 30000) {
  let last = "", same = 0, s;
  for (const t0 = Date.now(); Date.now() - t0 < ms; ) {
    s = await look(page);
    const sig = JSON.stringify([s.ring, s.card, s.dots, s.rail, s.next?.on]);
    same = sig === last && !s.dots ? same + 1 : 0; last = sig;
    if (same >= 6) return s;
    await sleep(250);
  }
  return s;
}

// THE CHECKS ONCE SETTLED: the ring, the card and the server's walk.on agree; the rail is the server's pile, once each; heads count it
export async function agree(page, api, why, { refolds = 0 } = {}) {
  const s = await settle(page);
  const [keys, pile] = await Promise.all([api("/api/fixture/walk/keys", {}), api("/api/funnel/pile")]);
  const items = pile.items || [], on = keys.on || "";
  const alias = (k) => items.find((i) => i.key === k || (i.aliases || []).includes(k))?.key || k;
  const rk = s.rail.map(([, k]) => k), dup = rk.filter((k, i) => rk.indexOf(k) !== i);
  if (dup.length) why.push(`row drawn twice: ${dup}`);
  const server = new Set(items.map((i) => i.key)), extra = rk.filter((k) => !server.has(k) && !items.some((i) => (i.aliases || []).includes(k)));
  if (extra.length) why.push(`rail rows the server does not have: ${extra.slice(0, 5)}`);
  // tasks are never capped: the Tasks band draws every row its heading counts; the headings add up to the server's pile
  const inTasks = s.rail.filter(([b]) => b === "task").length;
  if (s.heads.task !== undefined && inTasks !== s.heads.task) why.push(`Tasks heading says ${s.heads.task}, ${inTasks} rows drawn`);
  const sum = Object.values(s.heads).reduce((a, b) => a + b, 0);
  if (sum !== items.length) why.push(`headings add up to ${sum}, the server's pile has ${items.length}`);
  if (s.end) { if (s.ring.length) why.push(`walk ended but ${s.ring} still ringed`); }
  else if (on) {
    const ring = s.ring.map(alias);
    if (!ring.includes(alias(on)) && !(keys.walk?.members || []).some((m) => ring.includes(alias(m)))) why.push(`server walk on ${on}, ring on ${s.ring.join(",") || "nothing"}`);
    if (s.card && alias(s.card) !== alias(on) && !s.ring.map(alias).includes(alias(s.card)) && !/^batch|fyi/.test(s.card)) why.push(`card ${s.card} is not the walk's ${on}`);
  }
  if (s.errorReceipts.length) why.push(`error lines: ${s.errorReceipts.slice(0, 3).join(" | ")}`);
  const nexts = s.lines.filter((l) => /^Next\.?$/.test(l)).length;
  if (nexts) why.push(`${nexts} bare "Next." lines`);
  // one folded line per item walked past - a Back walks onto an item again, and that is one line more (`refolds` allowed)
  const twice = s.folded.filter((k, i) => s.folded.indexOf(k) !== i);
  if (twice.length > refolds) why.push(`${twice.length} items folded twice in the chat: ${[...new Set(twice)].slice(0, 3).join(" | ")}`);
  if (!(await page.evaluate(() => new Promise((ok) => { const t = performance.now(); setTimeout(() => ok(performance.now() - t < 500), 0); })))) why.push("page not responsive");
  return { s, keys, items };
}

export async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true });
  const f = path.join(SHOTS, `${name.replace(/[^\w.-]+/g, "_")}.png`);
  await page.screenshot({ path: f }).catch(() => {});
  return f;
}

// ── the presses ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
export const next = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); if (b && !b.disabled) { (window.__sp ||= []).push(performance.now()); b.click(); return true; } return false; });
export const back = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-walk-back]"); if (b && !b.disabled) { (window.__sp ||= []).push(performance.now()); b.click(); return true; } return false; });
export const walkChip = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((x) => (/^Walk me through/.test(x.textContent.trim()) || x.matches(".tq-welcome .tq-chip.primary")) && x.offsetParent && !x.disabled);
  b?.click(); return !!b;
});
// New chat, once it can be pressed: the empty chat's welcome with its Walk me through
export async function newChat(page) {
  await page.waitForFunction(() => { const b = document.querySelector('button[aria-label^="New chat"]'); return b && !b.disabled; }, { timeout: 30000 });
  await page.evaluate(() => document.querySelector('button[aria-label^="New chat"]')?.click());
  await page.waitForFunction(() => !document.querySelector(".tq-msg:not(.tq-welcome-msg)") && !!document.querySelector(".tq-welcome .tq-chip.primary:not([disabled])"), { timeout: 20000 });
  await sleep(600);
}
export const clickRow = (page, key) => page.evaluate((k) => { const c = document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`); if (c) (window.__sp ||= []).push(performance.now()); c?.click(); return !!c; }, key);
// the ringed row's place on the rail (0 the top), and a press sequence at a pace: "N" Next, "B" Back
export const ringAt = async (page) => { const s = await look(page); return s.rail.findIndex(([, k]) => s.ring.includes(k)); };
export async function presses(page, seq, pace) { for (const p of seq) { if (p === "N") await next(page); else if (p === "B") await back(page); await sleep(pace); } }
export const firstRow = (page) => page.$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (e) => e.getAttribute("data-tq-key"));
// the walk on the rail's first row, clicked, as the owner starts it
export async function start(page) {
  const k = await firstRow(page);
  await clickRow(page, k);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, k);
  await settle(page);
  return k;
}

// EVERY CASE AT EVERY SIZE AND SPEED: `cases` [{id, world, run(ctx) -> {extra metrics}}], each on a fresh page and world at 1440x900 and
// 1280x800 with the walk's answers held 0/300/1500 ms; recorded every frame from the first press to settled; then `agree`.
// STRESS_CASES=<id>@1440/300,... picks some.
export async function matrix(t, cases, { sizes = [[1440, 900], [1280, 800]], delays = [0, 300, 1500] } = {}) {
  const only = (process.env.STRESS_CASES || "").split(",").filter(Boolean), h = await server(t), rows = [];
  for (const c of cases) for (const [w, hh] of sizes) for (const delay of delays) {
    const id = `${c.id}@${w}/${delay}`;
    if (only.length && !only.some((o) => id.includes(o))) continue;
    const why = [], ctx = await open(h, { width: w, height: hh, delay, world: c.world || {} });
    const { page, errors, api, name } = ctx;
    try {
      const out = await c.run({ ...ctx, why, delay, record: () => record(page) }) || {};
      const f = out.frames || frames(await stopRecord(page));
      if (f.blank > 100) why.push(`blank ${f.blank} ms at ${f.blankAt} ms (${f.blankCtx?.join(" ; ")})`);
      if (f.dups.length) why.push(`rows twice: ${f.dups.slice(0, 3)}`);
      if (f.moved.length) why.push(`rows reordered: ${f.moved}`);
      const { s } = await agree(page, api, why, { refolds: out.refolds ?? 99 });
      if (c.check) await c.check({ ...ctx, why, s, out });
      if (errors.length) why.push(...errors.slice(0, 5));
      const r = { id, frames: f.n, blankMs: f.blank, worstFrameMs: f.worstFrame, draw: f.draw, flicker: f.flicker, ...(out.metrics || {}), why: why.map(name) };
      if (why.length) r.shot = await shot(page, `${c.id}-${w}-${delay}`);
      rows.push(r);
    } catch (e) { rows.push({ id, why: [name(String(e.stack || e).slice(0, 600))], shot: await shot(page, `${c.id}-${w}-${delay}-threw`) }); }
    report([rows.at(-1)]);
    await ctx.close();
  }
  return rows;
}
export const report = (rows) => { for (const r of rows) console.log(JSON.stringify(r)); };
export const verdict = (rows) => { const bad = rows.filter((r) => r.why?.length); assert.deepEqual(bad, [], `${bad.length} of ${rows.length} cases failed`); };
