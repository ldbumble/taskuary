// THE ASSISTANT SEES THE PAGE AND BRINGS THINGS UP - IT NEVER WORKS IN THEM (the owner, 2026-11-18: "it should just open the task, not do
// anything on the tasks. That's on the agent to do"). The server's half is taskuary/pageview.py.
//
// The page is read off the page: what the owner sees is what the Assistant is told when he asks it something. The view on the canvas - a
// browse card ([data-tq-browse]), a task's view ([data-tq-task-page]), a page marked [data-tq-view] - gives its fields and its buttons from
// the DOM, and a page adds only what the DOM cannot say: data-tq-secret on a secret, a setting's row (data-tq-knob), and its item and title
// through useViewExtras.
//
// What comes back is one of two things: `open` - another page brought up, the way its sidebar button brings it - or `point` - a box or a
// button outlined where it stands, for the owner to use. Nothing is typed, filled or pressed: the page is his, the work in a task its agent's.
// And nothing moves under his hands: an open waits for no one typing on the page, and never takes the focus from the box he types in.
import { useEffect, useRef } from "react";
import { rowNow } from "./actionRow.js";

const ROOTS = "[data-tq-browse], [data-tq-task-page], [data-tq-view]";
const SKIP = ".tq-chat-pop, .tq-dock, [data-tq-view-skip]";
const MAX_FIELDS = 40, MAX_BUTTONS = 40;
// a secret by its key or the words on its box - the same words the server checks again (pageview.py)
const SECRET_WORDS = /(password|passphrase|secret|token|api[ _-]?key|private key|access key|client key|xox[bp]-)/i;
export const isSecret = (key = "", label = "") => {
  const k = String(key || "").toLowerCase();
  return k === "secret" || /_(secret|password|token|key)$/.test(k) || SECRET_WORDS.test(String(label || "")) || SECRET_WORDS.test(k);
};

// ── EXTRAS: what a page holds that is no box on it ──
// root element, or an area's name for a page drawn inside a frame it does not own (Reports) -> () => {item, title}
const extras = new Map();      // key -> Set of getters: the reports frame and the routine open in it each add their own
export function useViewExtras(ref, spec) {
  const latest = useRef(spec); latest.current = spec;
  useEffect(() => {
    const el = typeof ref === "string" ? ref : ref.current;
    if (!el) return undefined;
    const get = () => latest.current;
    if (!extras.has(el)) extras.set(el, new Set());
    extras.get(el).add(get);
    return () => { extras.get(el)?.delete(get); if (!extras.get(el)?.size) extras.delete(el); };
  });
}
const extrasOf = (root, area) => {
  const all = [...(extras.get(root) || []), ...(extras.get(area) || [])].map((g) => g() || {});
  return { item: all.find((x) => x.item)?.item || null, title: all.find((x) => x.title)?.title || "" };
};

// ── THE VIEW ON SCREEN ──
const shown = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
const inView = (el) => { const r = el.getBoundingClientRect(), h = window.innerHeight, w = window.innerWidth;
  return Math.max(0, Math.min(r.bottom, h) - Math.max(r.top, 0)) * Math.max(0, Math.min(r.right, w) - Math.max(r.left, 0)); };
const areaOf = (root) => root.getAttribute("data-tq-browse") || (root.hasAttribute("data-tq-task-page") ? "task" : root.getAttribute("data-tq-view") || "");
// the view the owner is looking at: of those on the canvas, the one most in sight - a task's view inside a browse card is the card's
// ...never the top bar's Chat / Board / Game switch (the assistant audit, 2026-11-02): its tabs wear data-tq-view too, so with no card on the
// chat the widest tab was "the page" - the Assistant was told the owner was on the Board, with nothing on it
// ...and A DIALOG OVER THE PAGE IS THE PAGE (the owner, 2026-11-02): Search everything, the Hub's Write one, the bell's list sit in a portal
// over a wider page beneath - the one opened last, on top, is what the owner is looking at
const overPage = (el) => !!el.closest(".MuiModal-root");
export function currentRoot() {
  const all = [...document.querySelectorAll(ROOTS)].filter((el) => shown(el) && !el.closest(".tq-chat-pop, [data-tq-view-switch]") && !el.parentElement?.closest(ROOTS));
  const top = all.filter(overPage);
  if (top.length) return top[top.length - 1];
  let best = null, area = -1;
  all.forEach((el) => { const a = inView(el); if (a >= area) { best = el; area = a; } });
  return best;
}
const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60);
const words = (el) => String(el?.innerText ?? el?.textContent ?? "").replace(/\s+/g, " ").trim();
const firstLine = (el) => String(el?.innerText || "").split("\n").map((s) => s.trim()).find(Boolean) || "";
function labelOf(el) {
  const knob = el.closest("[data-tq-knob]");
  if (knob) return firstLine(knob.firstElementChild || knob);
  const own = el.getAttribute("data-tq-label") || el.closest("[data-tq-field]")?.getAttribute("data-tq-label");
  if (own) return own;
  const l = el.labels?.[0] ? words(el.labels[0]).replace(/\s*\*$/, "") : "";
  return l || el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.getAttribute("name") || el.getAttribute("title") || "";
}
const keyOf = (el, label) => el.closest("[data-tq-knob]")?.getAttribute("data-tq-knob")?.split(/\s+/)[0]
  || el.getAttribute("data-tq-field") || el.closest("[data-tq-field]")?.getAttribute("data-tq-field") || el.getAttribute("name") || slug(label);
const comboValue = (el) => el.parentElement?.querySelector("input.MuiSelect-nativeInput")?.value ?? words(el);

function domFields(root) {
  const out = [], seen = new Map();
  root.querySelectorAll("input, textarea, select, [role=combobox]").forEach((el) => {
    if (out.length >= MAX_FIELDS || el.closest(SKIP) || !shown(el)) return;
    if (el.matches("input[type=hidden], input[type=file], input[type=submit], input[type=button], input[type=radio], input.MuiSelect-nativeInput")) return;
    if (el.matches("input") && el.getAttribute("role") === "combobox" && el.readOnly) return;
    const label = labelOf(el); if (!label) return;
    let key = keyOf(el, label); const n = (seen.get(key) || 0) + 1; seen.set(key, n); if (n > 1) key = `${key}#${n}`;
    const check = el.matches("input[type=checkbox]"), combo = el.matches("[role=combobox]:not(input)");
    const secret = !check && (el.matches("input[type=password]") || el.hasAttribute("data-tq-secret") || isSecret(key, label));
    const f = { key, label: label.slice(0, 120), kind: check ? "switch" : combo || el.tagName === "SELECT" ? "choice" : "text", el };
    if (secret) Object.assign(f, { secret: true, state: el.value ? "typed" : /saved/i.test(label) ? "saved" : "empty" });
    else f.value = check ? (el.checked ? "on" : "off") : combo ? comboValue(el) : String(el.value ?? "");
    if (el.tagName === "SELECT") f.options = [...el.options].map((o) => o.text).slice(0, 20);
    if (el.disabled || el.getAttribute("aria-disabled") === "true") f.disabled = true;
    out.push(f);
  });
  return out;
}
// ...and a Search hit (role=option) is one by data-tq-view-press
function domButtons(root) {
  const out = [], seen = new Map();
  root.querySelectorAll("button, [role=button], [role=tab], [data-tq-view-press]").forEach((el) => {
    if (out.length >= MAX_BUTTONS || el.closest(SKIP) || !shown(el) || el.matches("[role=combobox], [aria-haspopup=listbox]")) return;
    const label = (el.getAttribute("aria-label") || words(el) || el.getAttribute("title") || "").slice(0, 80); if (!label) return;
    let id = el.getAttribute("data-tq-view-btn") || slug(label); const n = (seen.get(id) || 0) + 1; seen.set(id, n); if (n > 1) id = `${id}#${n}`;
    out.push({ id, label, enabled: !(el.disabled || el.getAttribute("aria-disabled") === "true"), el });
  });
  return out;
}
// a task's own buttons are its row's (the dock draws them): pointed at, they light where the row stands (setLighter)
const rowButtons = () => (rowNow().list || []).filter((v) => !["next", "back"].includes(v.group) && v.label)
  .map((v) => ({ id: `row:${v.id}`, label: v.label, enabled: !v.disabled, row: v.id }));

const lastResult = new Map();     // area -> the last Test / Preview answer the page reported (viewResult): read with the view, when he asks
// everything about the view, live: the elements too - `context` is what leaves the page
export function readView(root = currentRoot()) {
  if (!root) return null;
  const area = areaOf(root), x = extrasOf(root, area), fields = domFields(root);
  // ...one button per name: a row verb the page also draws (a draft's Send under it) is the row's, lit where the page draws it
  const dom = domButtons(root), rows = area === "task" ? rowButtons() : [], seen = new Set();
  const buttons = [...rows.map((b) => ({ ...b, el: dom.find((d) => norm(d.label) === norm(b.label))?.el })), ...dom]
    .filter((b) => { const k = norm(b.label); if (seen.has(k)) return false; seen.add(k); return true; });
  const title = x.title || root.getAttribute("data-tq-view-label") || root.querySelector("[data-tq-view-label]")?.getAttribute("data-tq-view-label") || "";
  return { root, area, title, item: x.item || null, fields, buttons, last: lastResult.get(area) || null };
}
// ...and what leaves it: no element, and never a secret's value - its state only
export function context(root = currentRoot()) {
  const v = readView(root);
  if (!v) return null;
  const text = words(v.root).slice(0, 600);
  return { area: v.area, title: v.title, ...(v.item ? { item: v.item } : {}),
    fields: v.fields.map(({ key, label, kind, value, secret, state, options, disabled }) => (secret || isSecret(key, label)
      ? { key, label, kind, secret: true, state: state || "empty" } : { key, label, kind, value: String(value ?? "").slice(0, 200), ...(options ? { options } : {}), ...(disabled ? { disabled } : {}) })),
    buttons: v.buttons.map(({ id, label, enabled }) => ({ id, label, enabled })),
    ...(v.last ? { last: v.last } : {}), ...(text ? { text } : {}) };
}

// ── THE PAGE'S OWN ANSWERS: a Test, a Preview - read with the view the next time he asks ──
export function viewResult({ action = "test", ok = false, detail = "" } = {}) {
  const root = currentRoot(); if (!root) return;
  lastResult.set(areaOf(root), { action, ok: !!ok, detail: String(detail || "").slice(0, 400), at: new Date().toISOString().slice(0, 19) });
}

// ── LIGHTING: the real thing, outlined where it stands (the setup's outline, data-tq-setup-lit) - a task's row through the chat's light ──
let lighter = null, lit = [];
export const setLighter = (f) => { lighter = f; };
function unlight() { lit.forEach((el) => el.removeAttribute("data-tq-setup-lit")); lit = []; }
function light(el) {
  const t = el?.closest?.(".MuiInputBase-root, .MuiSwitch-root, .MuiButton-root, [data-tq-knob], [role=combobox]") || el;
  if (!t) return null;
  t.setAttribute("data-tq-setup-lit", "view"); lit.push(t);
  t.scrollIntoView?.({ block: "center", behavior: "smooth" });
  return t;
}
if (typeof document !== "undefined") document.addEventListener("pointerdown", (e) => { if (e.isTrusted) unlight(); }, true);

// ── RUNNING WHAT CAME BACK ──
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (s) => String(s || "").trim().toLowerCase();
const find = (list, name, ...keys) => { const n = norm(name); if (!n) return null;
  for (const k of keys) { const hit = list.find((x) => norm(x[k]) === n); if (hit) return hit; }
  return list.find((x) => norm(x[keys[keys.length - 1]]).includes(n)) || null; };
let opener = null;
export const setOpener = (f) => { opener = f; };   // AssistantView's browse(): an area brought up the way its sidebar button brings it

async function waitRoot(area, knob) {
  for (let i = 0; i < 60; i++) {
    const r = currentRoot();
    if (r && areaOf(r) === area && (!knob || r.querySelector(`[data-tq-knob~="${CSS.escape(knob)}"]`))) return r;
    await wait(100);
  }
  return currentRoot();
}
// ...a page's frame label is written for the model (CanvasBrowse: "the Reports page - nothing opened on it yet"); the owner's step names the
// page only - "Opened the Reports page, Reports section - nothing opened on it yet" was a step in the chat (the Assistant stress run, 2026-11-03)
export const shownTitle = (t) => String(t || "").replace(/ - nothing opened on it yet$/, "");
const step = (n, summary, status = "done", kind = "run") => ({ id: `view-${Date.now()}-${n}`, kind, summary, status });
const typable = (el) => !!el?.matches?.("input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]), textarea, [contenteditable=true]");
// HE IS TYPING ON THE PAGE: a box of the page itself holds the focus (the chat's own box is not the page)
export const typingOnPage = (el = typeof document === "undefined" ? null : document.activeElement) => typable(el) && !el.closest(SKIP);
// ...and an open never takes the box he types in: a page that comes up with a box of its own focused (a new connection's name) gives the
// focus back, so his next words land where he was typing (2026-11-18: "No SQL Server, use my CSV" became a connection's name)
export function keepFocus(had) {
  if (!typable(had)) return () => {};
  const back = (e) => { if (had.isConnected && e.target !== had) had.focus(); };
  document.addEventListener("focusin", back, true);
  return () => document.removeEventListener("focusin", back, true);
}

// one op, on the live page: an open brings a page up, a point outlines a thing on it - nothing else is the Assistant's to do there
export const OPS = ["open", "point"];
async function runOne(op, n) {
  if (op.op === "open") {
    if (!opener) return step(n, "Could not bring that page up here", "error");
    if (typingOnPage()) return step(n, "Left the page as it is while you type", "done", "read");
    const { op: _o, area, ...state } = op;
    const letGo = keepFocus(document.activeElement);
    try {
      opener(area, state);
      const r = await waitRoot(area, state.knob);
      // ...Search's hits land a beat after its words
      for (let i = 0; area === "search" && state.query && i < 40 && !r?.querySelector('[data-tq-search-settled="true"]'); i++) await wait(100);
      await wait(150);                              // ...its frame names what is open once the card has drawn
      return step(n, `Opened ${shownTitle(r && readView(r)?.title) || area}`, "done", "read");
    } finally { letGo(); }
  }
  const v = readView();
  if (!v) return step(n, "Nothing is open to point at", "error");
  const name = op.button || op.target;
  const b = find(v.buttons, name, "id", "label"), f = b ? null : find(v.fields, name, "key", "label");
  if (b?.row && lighter) lighter(b.row, b.label);
  if (b?.el || f?.el) light(b?.el || f.el);
  else if (b?.row) light(document.querySelector(`.tq-dock [data-tq-verb="${CSS.escape(b.row)}"]`));
  if (!b && !f) return step(n, `Could not find ${name} on the page`, "error");
  return step(n, `Pointed at ${b?.label || f?.label}`, "done", "read");
}
// the ops in order, each a step the chat draws as it lands
export async function run(ops = [], onStep = () => {}) {
  const steps = [];
  for (const [i, op] of ops.filter((o) => OPS.includes(o?.op)).entries()) {
    let s;
    try { s = await runOne(op, i); } catch (e) { s = step(i, `Could not do that - ${e?.message || "it failed"}`, "error"); }
    steps.push(s); onStep([...steps]);
  }
  return { steps };
}
