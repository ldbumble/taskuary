// MIXED USE, STRESSED (the owner, 2026-11-02: the "no crazy stuff" check): what every stress-mixed-*.test.mjs boots and checks - the page
// instrumented before its first script (errors, React warnings, blank frames, listeners and intervals held), a server delay on every
// /api/ answer, and the looks: one ring and one table, rows on one line, no box over another.
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { startHarness } from "./harness.mjs";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const SHOTS = process.env.STRESS_SHOTS || path.join(os.tmpdir(), "taskuary-stress-mixed");
mkdirSync(SHOTS, { recursive: true });
export const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) }).catch(() => {});

// in the page before the app: a count of what is attached and never let go, and every run of frames the canvas drew nothing in
const INSTRUMENT = () => {
  const held = { listeners: 0, intervals: new Set() }, add = EventTarget.prototype.addEventListener, rm = EventTarget.prototype.removeEventListener;
  const seen = new WeakMap();
  EventTarget.prototype.addEventListener = function (type, f, o) {
    if (f && (this === window || this === document)) { const k = `${type}|${!!(o === true || o?.capture)}`; const m = seen.get(f) || new Set();
      if (!m.has(k)) { m.add(k); seen.set(f, m); held.listeners++; } }
    return add.call(this, type, f, o);
  };
  EventTarget.prototype.removeEventListener = function (type, f, o) {
    if (f && (this === window || this === document)) { const k = `${type}|${!!(o === true || o?.capture)}`, m = seen.get(f); if (m?.delete(k)) held.listeners--; }
    return rm.call(this, type, f, o);
  };
  const si = window.setInterval, ci = window.clearInterval;
  window.setInterval = function (...a) { const id = si.apply(this, a); held.intervals.add(id); return id; };
  window.clearInterval = function (id) { held.intervals.delete(id); return ci.call(this, id); };
  window.__held = () => ({ listeners: held.listeners, intervals: held.intervals.size, nodes: document.getElementsByTagName("*").length, chat: document.querySelector(".tq-chat-body")?.getElementsByTagName("*").length || 0, msgs: document.querySelectorAll(".tq-chat-body .tq-msg").length,
    heap: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null });
  // a blank frame: the main column shows no words and no dots - a run of them past 100 ms is a flash the owner sees
  const blanks = []; let since = null, armed = false;
  const tick = () => {
    const body = document.querySelector(".tq-chat-body, .tq-canvas, main");
    if (armed && body) {
      const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
      const words = (body.innerText || "").trim().length > 10 || [...document.querySelectorAll(".tq-typing")].some(vis);
      const t = performance.now();
      if (!words) since ??= t;
      else { if (since != null && t - since > 100) blanks.push({ at: Math.round(since), ms: Math.round(t - since), hash: location.hash }); since = null; }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  window.__blanks = { arm: () => { armed = true; since = null; }, take: () => blanks.splice(0) };
};

// `delay`: every /api/ answer held that long in the page - the server's work done, the page hearing of it late
const DELAY = (ms) => {
  if (!ms) return;
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, url, ...rest) { this.__url = String(url); return open.call(this, m, url, ...rest); };
  XMLHttpRequest.prototype.send = function (...a) {
    if (/\/api\//.test(this.__url)) for (const k of ["onreadystatechange", "onloadend", "onload"]) { const f = this[k]; if (f) this[k] = (...e) => setTimeout(() => f.apply(this, e), ms); }
    return send.apply(this, a);
  };
};

// React's own warnings, console errors, uncaught errors - each a failure, minus the network refusals the fixture makes on purpose
const NOISE = /blockedbyclient|ERR_BLOCKED_BY_CLIENT|fonts\.g|Failed to load resource|net::ERR_ABORTED|status of 40[134]|WebSocket connection to .* failed/;
export async function bootMixed(t, { width = 1440, height = 900, delay = 0, harness = null } = {}) {
  const h = harness || await startHarness();
  if (!harness) t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.evaluateOnNewDocument(INSTRUMENT);
  await page.evaluateOnNewDocument(DELAY, delay);
  page.on("pageerror", (e) => errors.push(`uncaught: ${e.message}`));
  page.on("console", (m) => { const s = m.text(); if ((m.type() === "error" || /^Warning: /.test(s)) && !NOISE.test(s)) errors.push(`${m.type()}: ${s.slice(0, 400)}`); });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then(async (r) => { if (!r.ok) throw new Error(`${p}: ${r.status} ${await r.text()}`); return r.json(); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(1500);
  await page.evaluate(() => window.__blanks.arm());
  return { h, page, errors, api };
}

export const held = (page) => page.evaluate(() => window.__held());
export const blanks = (page) => page.evaluate(() => window.__blanks.take());
export const settled = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

// the walk as drawn: the ringed rail row(s), the table's item(s), the dock row's words, the pop-up, spinners still turning
export const look = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  const pop = document.querySelector("[data-tq-chat-pop]");
  return {
    ring: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => e.getAttribute("data-tq-key")),
    items: [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter(vis).map((e) => e.getAttribute("data-tq-canvas-item")),
    keys: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].map((e) => e.getAttribute("data-tq-key")),
    row: (document.querySelector("[data-tq-row]")?.innerText || "").replace(/\s+/g, " "),
    pop: pop ? !pop.hidden : null, pending: !!document.querySelector(".tq-pending"),
    dots: [...document.querySelectorAll(".tq-typing")].filter(vis).length,
    spin: [...document.querySelectorAll(".MuiCircularProgress-indeterminate, .MuiLinearProgress-indeterminate, [role=progressbar]:not([aria-valuenow])")].filter(vis).map((e) => `${String(e.className).split(" ")[0]}:${e.getAttribute("aria-label") || ""}:${(e.closest("[data-tq-canvas-item], [data-tq-row], section, li, div")?.innerText || "").replace(/\s+/g, " ").slice(0, 60)}`),
    banners: [...document.querySelectorAll("[role=alert], .MuiAlert-root, .MuiSnackbar-root, .tq-error, [data-tq-error]")].filter(vis).map((e) => e.innerText.replace(/\s+/g, " ").slice(0, 120))
      .concat((document.body.innerText.match(/[^\n]*(Network Error|went wrong|Request failed|could ?n[o']t reach|not answering|status code 5\d\d)[^\n]*/gi) || []).map((x) => x.slice(0, 120))),
    cards: [...document.querySelectorAll("[data-tq-canvas-item]")].filter(vis).map((e) => e.getAttribute("data-tq-canvas-item")),
    hash: location.hash,
  };
});

// waits for the walk to stand still: the same ring, items and dots for ~1.5 s
export async function still(page, ms = 20000) {
  let last = "", same = 0, s;
  for (const t0 = Date.now(); Date.now() - t0 < ms; ) {
    s = await look(page);
    const sig = JSON.stringify([s.ring, s.items, s.dots, s.pending, s.keys.length, s.spin.length]);
    same = sig === last && !s.dots && !s.pending && !s.spin.length ? same + 1 : 0; last = sig;
    if (same >= 6) return s;
    await sleep(250);
  }
  return s;
}

// ONE TABLE, ONE RING: the row ringed on the rail is the one item on the table
export function oneTable(s, where) {
  assert.ok(s.ring.length <= 1, `${where}: more than one ring ${JSON.stringify(s.ring)}`);
  assert.ok(new Set(s.items).size <= 1, `${where}: more than one item on the table ${JSON.stringify(s.items)}`);
  if (s.ring.length && s.items.length) assert.equal(s.items[0], s.ring[0], `${where}: the ring and the table disagree ${JSON.stringify(s)}`);
  assert.equal(new Set(s.cards).size, s.cards.length, `${where}: a card drawn twice ${JSON.stringify(s.cards)}`);
  // ...and once it stands still nothing still turns: no dots, no spinner, no pending line (`still` waited for them)
  assert.ok(!s.dots && !s.pending && !s.spin.length, `${where}: a spinner or the dots are still up ${JSON.stringify({ dots: s.dots, pending: s.pending, spin: s.spin })}`);
}

// THE ROW IS ONE LINE (row-one-line.test.mjs): every drawn row's buttons on one line, nothing past its edge, Next and the lit move unfolded
export const rowLook = (page) => page.evaluate(() => {
  const seen = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  // a button some scroller round it cuts: less of it drawn than it is (the dock clips what runs past its end)
  const cut = (bs) => bs.filter(seen).filter((b) => { const r = b.getBoundingClientRect(); let l = r.left, rt = r.right;
    for (let n = b.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n); if (s.overflowX !== "visible") { const c = n.getBoundingClientRect(); l = Math.max(l, c.left); rt = Math.min(rt, c.right); } }
    return rt - l < r.width - 3; }).map((b) => b.textContent.trim() || b.getAttribute("aria-label"));   // ...a 1-2px edge under the dock's border is not a cut
  return [...document.querySelectorAll("[data-tq-row] .tq-arow-verbs, [data-tq-task-bar]")].filter(seen).map((box) => {
    const kids = [...box.children].filter(seen), r = box.getBoundingClientRect();
    return { height: Math.round(r.height), tall: Math.round(Math.max(0, ...kids.map((k) => k.getBoundingClientRect().height))), over: box.scrollWidth - box.clientWidth,
      tops: [...new Set(kids.map((k) => Math.round(k.getBoundingClientRect().top + k.getBoundingClientRect().height / 2)))],
      broken: [...box.querySelectorAll("button")].filter(seen).filter((k) => k.getBoundingClientRect().height > 50).map((k) => k.textContent),
      next: !!box.querySelector("[data-tq-next]"), labels: [...box.querySelectorAll("button")].filter(seen).map((k) => k.textContent.trim()).filter(Boolean),
      page: document.documentElement.scrollWidth - innerWidth, vw: innerWidth, navCut: cut([...box.querySelectorAll("[data-tq-next], [data-tq-walk-back]")]),
      cut: cut([...box.querySelectorAll("button:not([data-tq-next]):not([data-tq-walk-back])")]) };
  });
});
export function oneLine(rows, where) {
  for (const r of rows) {
    const say = (why) => `${where}: ${why} ${JSON.stringify(r)}`;
    assert.ok(r.tops.length <= 1, say("the row's buttons sit on more than one line"));
    assert.ok(r.height <= r.tall + 2, say("the row is taller than one line"));
    assert.ok(r.over <= 1, say("the row runs past its edge"));
    assert.deepEqual(r.broken, [], say("a label broke onto two lines"));
    assert.ok(r.page <= 1, say("the page scrolls sideways"));
    // ...at every width, 900 beside the rail too: the stage moves are on the spine there and the bar is Back and Next alone, and an FYI batch's
    // "All read, next" says "All read" on a squeezed bar (the owner, 2026-11-03)
    assert.deepEqual(r.navCut, [], say("Back or Next is cut off"));
  }
}

// NO BOX OVER ANOTHER: every visible button, rail row and spine line against every other one that is not its own ancestor - the pop-up
// and an open menu float over the page on purpose, so they are held only against their own
export const overlaps = (page) => page.evaluate(() => {
  // each box as drawn: cut by every scroller round it - a row scrolled up under a sticky heading is not drawn there
  const box = (e) => {
    const r = e.getBoundingClientRect(); let { left, right, top, bottom } = r;
    for (let n = e.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.overflowX !== "visible" || s.overflowY !== "visible") { const c = n.getBoundingClientRect();
        left = Math.max(left, c.left); right = Math.min(right, c.right); top = Math.max(top, c.top); bottom = Math.min(bottom, c.bottom); }
      if (s.position === "fixed") break;
    }
    return { left, right, top, bottom, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
  };
  const hit = (a, b) => a.left + 1 < b.right && b.left + 1 < a.right && a.top + 1 < b.bottom && b.top + 1 < a.bottom;
  const seen = (e) => { const r = box(e); if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) return false;
    for (let n = e; n && n !== document.body; n = n.parentElement) { const s = getComputedStyle(n); if (s.visibility === "hidden" || s.display === "none" || +s.opacity === 0) return false; }
    return true; };
  const layer = (e) => e.closest("[data-tq-chat-pop], [role=menu], [role=dialog], [role=tooltip], .MuiPopover-root, .MuiModal-root") || document.body;
  const els = [...document.querySelectorAll("button, [data-tq-tab-line], [data-tq-rail] .tq-pile-row")].filter(seen);
  const out = [];
  for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i], b = els[j];
    if (a.contains(b) || b.contains(a) || layer(a) !== layer(b)) continue;
    // the top of the pair at its centre must be one of the pair: a box drawn over another hides it (a box merely clipped under a scroller is not drawn)
    if (hit(box(a), box(b))) {
      const r = box(a), s = box(b), x = (Math.max(r.left, s.left) + Math.min(r.right, s.right)) / 2, y = (Math.max(r.top, s.top) + Math.min(r.bottom, s.bottom)) / 2;
      const top = document.elementFromPoint(x, y);
      if (top && (a.contains(top) || b.contains(top))) out.push(`${(a.textContent || a.getAttribute("aria-label") || "").trim().slice(0, 30)} x ${(b.textContent || b.getAttribute("aria-label") || "").trim().slice(0, 30)}`);
    }
  }
  return out;
});

// words cut off: a line of text that runs past its box with no ellipsis to say so
export const cutOff = (page) => page.evaluate(() => {
  const seen = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
  return [...document.querySelectorAll("button, .tq-msg, [data-tq-rail] .tq-pile-row .card, h1, h2, h3")].filter(seen).filter((e) => {
    const s = getComputedStyle(e);
    return s.overflowX !== "visible" && s.textOverflow !== "ellipsis" && e.scrollWidth > e.clientWidth + 2 && !e.querySelector("[style*=ellipsis], .MuiTypography-noWrap");
  }).map((e) => e.textContent.trim().slice(0, 40));
});

export async function type(page, words) {
  const box = await page.waitForSelector(".tq-compose textarea:not([disabled])", { timeout: 20000 });
  await box.click({ clickCount: 3 }); await box.type(words); await page.keyboard.press("Enter");
}
export const pressNext = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); if (b && !b.disabled) { b.click(); return true; } return false; });
export const pressBack = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-walk-back]"); if (b && !b.disabled) { b.click(); return true; } return false; });
export const clickText = (page, re) => page.evaluate((src) => {
  const b = [...document.querySelectorAll("button, [role=button]")].find((n) => new RegExp(src).test(n.textContent.trim()) && !n.disabled && n.getBoundingClientRect().width > 0);
  b?.click(); return !!b;
}, re.source);
export const startWalk = async (page) => { await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through/.test(b.textContent.trim())), { timeout: 20000 });
  await clickText(page, /^Walk me through/); return still(page); };
// what the server says waits: the rail as the server builds it
export const serverKeys = async (api) => (await api("/api/fixture/walk/keys", {}));

export function clean(errors, where) { assert.deepEqual(errors.splice(0), [], `${where}: console errors, React warnings or uncaught exceptions`); }
export async function noBlank(page, where) { const b = await blanks(page); assert.deepEqual(b, [], `${where}: blank frames over 100 ms`); }
