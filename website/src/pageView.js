// THE ASSISTANT SEES THE PAGE, AND ACTS ON IT AS THE OWNER WOULD (the owner, 2026-10-30: "the assistant should be able to interact directly
// with the current view or page" - and the same day, revised: "Nothing should really change in terms of how things work").
// docs/superpowers/specs/2026-10-30-assistant-sees-the-page-design.md; the server's half is taskuary/pageview.py.
//
// The page is read off the page: what the owner sees is what the Assistant is told. The view on the canvas - a browse card
// ([data-tq-browse]), a task's view ([data-tq-task-page]), a page marked [data-tq-view] - gives its fields and its buttons from the DOM,
// and a page adds only what the DOM cannot say: data-tq-send on an outward send, data-tq-secret on a secret, a setting's row
// (data-tq-knob), and EXTRAS - a field or a button with no box of its own (a task's title, the describe-it that runs a report's composer) -
// through useViewExtras. A task's buttons are its row's verbs (actionRow.js), pressed the row's own road.
//
// It is read ONLY WHEN ASKED - a line typed to the chat, or a "with AI" door - and acts only on what came back for that ask. Each act runs
// through the page's own handler (a box's own onChange, a button's own click, the row's press) and is a step in the chat. An outward send
// is never pressed: it is lit for the owner (the router, 2026-10-19). A secret never leaves the page: its state goes, never its value.
import { useEffect, useRef } from "react";
import { press as rowPress, rowNow } from "./actionRow.js";
import { verbOfRow } from "./buttons.js";

const ROOTS = "[data-tq-browse], [data-tq-task-page], [data-tq-view]";
const SKIP = ".tq-chat-pop, .tq-dock, [data-tq-view-skip]";
const MAX_FIELDS = 40, MAX_BUTTONS = 40;
// the same words the server checks again (pageview.py): a send by its verb or its label, a secret by its key or the words on its box
export const SEND_VERBS = new Set(["approve", "send", "accept_invite", "decline_invite", "propose_time", "share", "forward", "send-handoff", "email"]);
// ..."Send to agent" starts work here and sends nothing out: it is the owner's kind of press, like Mark done
const SEND_WORDS = /^\s*(send(?! to (an? )?agent)|approve|post|forward|reply all|email (it|them|him|her)|share by email)\b/i;
const SECRET_WORDS = /(password|passphrase|secret|token|api[ _-]?key|private key|access key|client key|xox[bp]-)/i;
export const isSecret = (key = "", label = "") => {
  const k = String(key || "").toLowerCase();
  return k === "secret" || /_(secret|password|token|key)$/.test(k) || SECRET_WORDS.test(String(label || "")) || SECRET_WORDS.test(k);
};
export const isSend = (b) => !!b && (!!b.send || SEND_VERBS.has(String(b.id || "").split(":").pop().toLowerCase())
  || SEND_VERBS.has(String(verbOfRow(String(b.id || "").replace(/^row:/, "")) || "")) || SEND_WORDS.test(String(b.label || "")));

// ── EXTRAS: what a page holds that is no box on it ──
// root element, or an area's name for a page drawn inside a frame it does not own (Reports) ->
//   () => {item, title, fields: [{key, label, value, set}], buttons: [{id, label, press, send}]}
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
  return { item: all.find((x) => x.item)?.item || null, title: all.find((x) => x.title)?.title || "",
    fields: all.flatMap((x) => x.fields || []), buttons: all.flatMap((x) => x.buttons || []) };
};

// ── THE VIEW ON SCREEN ──
const shown = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
const inView = (el) => { const r = el.getBoundingClientRect(), h = window.innerHeight, w = window.innerWidth;
  return Math.max(0, Math.min(r.bottom, h) - Math.max(r.top, 0)) * Math.max(0, Math.min(r.right, w) - Math.max(r.left, 0)); };
const areaOf = (root) => root.getAttribute("data-tq-browse") || (root.hasAttribute("data-tq-task-page") ? "task" : root.getAttribute("data-tq-view") || "");
// the view the owner is looking at: of those on the canvas, the one most in sight - a task's view inside a browse card is the card's
export function currentRoot() {
  const all = [...document.querySelectorAll(ROOTS)].filter((el) => shown(el) && !el.closest(".tq-chat-pop") && !el.parentElement?.closest(ROOTS));
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
function domButtons(root) {
  const out = [], seen = new Map();
  root.querySelectorAll("button, [role=button], [role=tab]").forEach((el) => {
    if (out.length >= MAX_BUTTONS || el.closest(SKIP) || !shown(el) || el.matches("[role=combobox], [aria-haspopup=listbox]")) return;
    const label = (el.getAttribute("aria-label") || words(el) || el.getAttribute("title") || "").slice(0, 80); if (!label) return;
    let id = el.getAttribute("data-tq-view-btn") || slug(label); const n = (seen.get(id) || 0) + 1; seen.set(id, n); if (n > 1) id = `${id}#${n}`;
    out.push({ id, label, enabled: !(el.disabled || el.getAttribute("aria-disabled") === "true"), ...(el.hasAttribute("data-tq-send") ? { send: true } : {}), el });
  });
  return out;
}
// a task's own buttons are its row's (the dock draws them, the task registers them): pressed the row's road, the same as a click there
const rowButtons = () => (rowNow().list || []).filter((v) => !["next", "back"].includes(v.group) && v.label)
  .map((v) => ({ id: `row:${v.id}`, label: v.label, enabled: !v.disabled, row: v.id, of: v.of, ...(isSend({ id: v.id, label: v.label }) ? { send: true } : {}) }));

let lastResult = new Map();     // area -> the last Test / Preview answer the page reported (viewResult)
let rev = 0, results = 0, latest = null;
// everything about the view, live: the elements and handlers too - `context` is what leaves the page
export function readView(root = currentRoot()) {
  if (!root) return null;
  const area = areaOf(root), x = extrasOf(root, area);
  const fields = [...(x.fields || []).map((f) => ({ ...f, kind: f.kind || "text", extra: true })), ...domFields(root)];
  // ...one button per name: a row verb the page also draws (a draft's Send under it, Mark done in Close out) is the row's, pressed the row's
  // road, and lit where the page draws it
  const dom = domButtons(root), rows = area === "task" ? rowButtons() : [], seen = new Set();
  const buttons = [...(x.buttons || []).map((b) => ({ ...b, enabled: b.enabled !== false, extra: true })),
    ...rows.map((b) => ({ ...b, el: dom.find((d) => norm(d.label) === norm(b.label))?.el })), ...dom]
    .filter((b) => { const k = norm(b.label); if (seen.has(k)) return false; seen.add(k); return true; });
  const title = x.title || root.getAttribute("data-tq-view-label") || root.querySelector("[data-tq-view-label]")?.getAttribute("data-tq-view-label") || "";
  return { root, area, title, item: x.item || null, fields, buttons, last: lastResult.get(area) || null };
}
// ...and what leaves it: no element, no handler, and never a secret's value - its state only
export function context(root = currentRoot()) {
  const v = readView(root);
  if (!v) return null;
  const text = words(v.root).slice(0, 600);
  return { area: v.area, title: v.title, ...(v.item ? { item: v.item } : {}), rev,
    fields: v.fields.map(({ key, label, kind, value, secret, state, options, disabled }) => (secret || isSecret(key, label)
      ? { key, label, kind, secret: true, state: state || "empty" } : { key, label, kind, value: String(value ?? "").slice(0, 200), ...(options ? { options } : {}), ...(disabled ? { disabled } : {}) })),
    buttons: v.buttons.map(({ id, label, enabled, send }) => ({ id, label, enabled, ...(send || isSend({ id, label }) ? { send: true } : {}) })),
    ...(v.last ? { last: v.last } : {}), ...(text ? { text } : {}) };
}
// ...the same card whatever its line says about it now: "not set up" turning "connected" after a Save is still the conversation's subject
export const subjectOf = (v) => (v ? `${v.area}|${v.item?.id ?? shortTitle(v)}` : "");

// ── THE PAGE'S OWN ANSWERS: a Test, a Preview - what the Assistant hears next ──
export function viewResult({ action = "test", ok = false, detail = "" } = {}) {
  const root = currentRoot(); if (!root) return;
  const at = new Date().toISOString().slice(0, 19);
  latest = { action, ok: !!ok, detail: String(detail || "").slice(0, 400), at };
  lastResult.set(areaOf(root), latest);
  rev += 1; results += 1;
  emit({ kind: "result", text: `${action} ${ok ? "passed" : "failed"}${detail ? `: ${String(detail).slice(0, 200)}` : ""}` });
}

// ── A HELP SESSION: only while the owner is talking to it about this page (asked in the chat, or pressed a door) ──
let session = null;            // { subject, title, auto }
const listeners = new Set();
export const onReact = (f) => { listeners.add(f); return () => listeners.delete(f); };
// ...named the way the chat says it: "the LinkedIn connector card", not the frame's whole line about it
const shortTitle = (v) => { const t = String(v.item?.ref ? `${v.item.ref}` : v.title || v.area || "this page").split(/ \(| - nothing|, its | · /)[0].trim();
  return /^(the |TQ-)/i.test(t) ? t : `the ${t}`; };
// `door`: opened by a "with AI" button - a setup the owner asked to be walked through, whose x asks before it ends it
export const startSession = (v = context(), door = false) => { if (!v) return null; const subject = subjectOf(v);
  if (session?.subject !== subject) session = { subject, title: shortTitle(v), auto: 0, door }; else { session.auto = 0; session.door = session.door || door; }
  return session; };
export const endSession = () => { session = null; clearTimeout(settle.t); settle.key = null; };
export const sessionNow = () => session;
const live = () => !!session && subjectOf(context()) === session.subject;
function emit(ev) {
  if (acting || !live()) return;                              // no session, nothing: someone setting it up by hand never triggers it
  listeners.forEach((f) => { try { f(ev, session); } catch { /* a listener's trouble is never the page's */ } });
}
// THE OWNER'S OWN EDITS, heard only inside a session: a box settles 1.5 s after its last keystroke or when it loses focus; a Save at once
const settle = { t: 0, key: null, label: "" };
const fieldOf = (el) => el?.closest?.(ROOTS) && el.matches?.("input, textarea, select") ? el : null;
function edited(e) {
  if (!e.isTrusted || acting || !session) return;
  const el = fieldOf(e.target); if (!el || el.closest(SKIP)) return;
  rev += 1;
  const label = labelOf(el), secret = el.matches("input[type=password]") || isSecret(keyOf(el, label), label);
  clearTimeout(settle.t); settle.key = el; settle.label = secret ? `${label} (typed - its value is yours)` : label;
  settle.t = setTimeout(fire, 1500);
}
function fire() { if (!settle.key) return; const label = settle.label; settle.key = null; clearTimeout(settle.t); emit({ kind: "edit", text: `changed ${label}` }); }
function left(e) { if (e.isTrusted && settle.key && e.target === settle.key) fire(); }
function clicked(e) {
  if (!e.isTrusted || acting || !session) return;
  const b = e.target?.closest?.("button"); if (!b || b.closest(SKIP) || !b.closest(ROOTS)) return;
  const label = words(b);
  if (/^(save|connect|save & run now|save and run)\b/i.test(label)) { if (settle.key) { settle.key = null; clearTimeout(settle.t); } rev += 1; emit({ kind: "saved", text: `pressed ${label}` }); }
}
// ...and THE OWNER'S HAND WINS: a click or a key on the page while the Assistant's acts are running drops the rest
let acting = false, stopped = false;
function hand(e) { if (e.isTrusted && acting && !e.target?.closest?.(".tq-chat-pop")) stopped = true; }
if (typeof document !== "undefined") {
  document.addEventListener("input", edited, true); document.addEventListener("change", edited, true);
  document.addEventListener("focusout", left, true); document.addEventListener("click", clicked, true);
  document.addEventListener("pointerdown", hand, true); document.addEventListener("keydown", hand, true);
  document.addEventListener("pointerdown", (e) => { if (e.isTrusted && !acting) unlight(); }, true);
}
export const stop = () => { stopped = true; };

// ── LIGHTING: the real thing, outlined where it stands (the setup's outline, data-tq-setup-lit) - a task's row through the Advisor's fill ──
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
// ...a box it filled flashes once - only that one: a button it lit for the owner stays lit
const flash = (el) => { const t = light(el); if (t) setTimeout(() => { t.removeAttribute("data-tq-setup-lit"); lit = lit.filter((x) => x !== t); }, 1400); };

// ── RUNNING WHAT CAME BACK ──
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (s) => String(s || "").trim().toLowerCase();
const find = (list, name, ...keys) => { const n = norm(name); if (!n) return null;
  for (const k of keys) { const hit = list.find((x) => norm(x[k]) === n); if (hit) return hit; }
  return list.find((x) => norm(x[keys[keys.length - 1]]).includes(n)) || null; };
const busyOf = (el) => !!el && (el.disabled || !!el.querySelector?.(".MuiCircularProgress-root"));
let opener = null;
export const setOpener = (f) => { opener = f; };   // AssistantView's browse(): an area brought up the way its sidebar button brings it

function setDom(el, value) {
  if (el.matches("input[type=checkbox]")) {
    const on = /^(on|true|1|yes|enabled?)$/i.test(String(value).trim());
    if (el.checked !== on) el.click();
    return;
  }
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  if (el.tagName === "SELECT") { const o = [...el.options].find((x) => norm(x.text) === norm(value) || norm(x.value) === norm(value)); if (o) value = o.value; }
  el.focus?.();
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, String(value));
  el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
  el.blur?.();                                  // a box that saves when it is left (a setting's) saves now, as the owner's Tab would
}
async function pickCombo(el, value) {
  el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
  for (let i = 0; i < 20; i++) {
    const opts = [...document.querySelectorAll("[role=listbox] [role=option]")];
    if (opts.length) { const o = opts.find((x) => norm(words(x)) === norm(value) || norm(x.getAttribute("data-value")) === norm(value));
      if (o) { o.click(); return true; } document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); return false; }
    await wait(50);
  }
  return false;
}
async function waitRoot(area, knob) {
  for (let i = 0; i < 60; i++) {
    const r = currentRoot();
    if (r && areaOf(r) === area && (!knob || r.querySelector(`[data-tq-knob~="${CSS.escape(knob)}"]`))) return r;
    await wait(100);
  }
  return currentRoot();
}
const step = (n, summary, status = "done", kind = "run") => ({ id: `view-${Date.now()}-${n}`, kind, summary, status });
const cut = (s, n = 60) => { s = String(s ?? ""); return s.length > n ? `${s.slice(0, n - 1)}…` : s; };

// one op, on the live page, checked again here: still there, still enabled, a send never pressed, a secret never set
async function runOne(op, n) {
  // ...a refusal is not a failure: it is the line the owner drew, said as a step like any other
  if (op.op === "refused") return step(n, `${op.target} ${op.why || "is yours to do"}`, "done", "read");
  if (op.op === "open") {
    if (!opener) return step(n, "Could not bring that page up here", "error");
    const { op: _o, area, ...state } = op;
    opener(area, state);
    const r = await waitRoot(area, state.knob);
    await wait(150);                              // ...its frame names what is open once the card has drawn
    return step(n, `Opened ${(r && readView(r)?.title) || area}`, "done", "read");
  }
  const v = readView();
  if (!v) return step(n, "Nothing is open to work on", "error");
  if (op.op === "set") {
    const f = find(v.fields, op.field, "key", "label");
    if (!f) return step(n, `Could not find ${op.field} on the page`, "error");
    if (f.secret || isSecret(f.key, f.label)) return step(n, `${f.label} is yours to paste into its field - I never see or type a secret`, "done", "read");
    if (f.disabled) return step(n, `${f.label} is greyed out`, "error");
    if (f.extra) await f.set(op.value);
    else if (f.kind === "choice" && f.el.matches("[role=combobox]")) { if (!(await pickCombo(f.el, op.value))) return step(n, `${f.label} has no ${cut(op.value)}`, "error"); }
    else setDom(f.el, op.value);
    if (f.el) flash(f.el);
    if (f.said) return step(n, f.said(op.value));      // an extra that runs something says what it ran ("Asked the builder for ...")
    return step(n, f.kind === "switch" ? `Turned ${/^(on|true|1|yes|enabled?)$/i.test(String(op.value).trim()) ? "on" : "off"} ${f.label}` : `Set ${f.label} to ${cut(op.value)}`);
  }
  const name = op.button || op.target;
  const b = find(v.buttons, name, "id", "label"), f = b ? null : find(v.fields, name, "key", "label");
  if (op.op === "point" || (b && isSend(b))) {
    // AN OUTWARD SEND IS THE OWNER'S (the owner, 2026-10-30): lit where it stands, never pressed - whatever asked for the press
    if (b?.row && lighter) lighter(b.row, b.label);
    if (b?.el || f?.el) light(b?.el || f.el);
    else if (b?.row) light(document.querySelector(`.tq-dock [data-tq-verb="${CSS.escape(b.row)}"]`));
    if (!b && !f) return step(n, `Could not find ${name} on the page`, "error");
    const what = b?.label || f?.label;
    return step(n, b && isSend(b) ? `Lit ${what} for you - a send is yours to press` : `Pointed at ${what}`, "done", "read");
  }
  if (!b) return step(n, `Could not find ${name} on the page`, "error");
  if (!b.enabled) return step(n, `${b.label} is greyed out`, "error");
  const before = lastResult.get(v.area)?.at;
  if (b.extra) await b.press();
  else if (b.row) await rowPress(b.row, null, null, b.of);
  else {
    b.el.click();
    await wait(250);
    for (let i = 0; i < 80 && b.el.isConnected && busyOf(b.el); i++) await wait(250);
    await wait(300);                              // ...the page's own answer (its Test line) draws a beat after the button lets go
  }
  const res = lastResult.get(v.area);
  const said = res && res.at !== before ? ` - ${res.ok ? "passed" : "failed"}${res.detail ? `: ${cut(res.detail, 120)}` : ""}` : "";
  return step(n, `Pressed ${b.label}${said}`, res && res.at !== before && !res.ok ? "error" : "done");
}
// the ops in order, each a step the chat draws as it lands; the owner's own hand on the page, or the chat's Stop, drops the rest
// ...and what the page answered to a press of its own (a Test's result) - the Assistant hears it next, as the walk heard a Test
export async function run(ops = [], onStep = () => {}) {
  const steps = [], had = results;
  acting = true; stopped = false;
  try {
    for (let i = 0; i < ops.length; i++) {
      if (stopped) { steps.push(step(i, "Stopped - your hand on the page wins", "error", "read")); onStep([...steps]); break; }
      let s;
      try { s = await runOne(ops[i], i); } catch (e) { s = step(i, `Could not do that - ${e?.message || "it failed"}`, "error"); }
      steps.push(s); onStep([...steps]);
      await wait(120);
    }
  } finally { acting = false; }
  return { steps, result: results !== had ? latest : null };
}

// ── THE DOORS: "Get AI to set it up", "Set up with AI", "Fix with AI" - each opens the chat with its ask ──
export const HELP = "tq-view-help", EARLIER = "tq-view-earlier";
export const openHelp = (line, opts = {}) => window.dispatchEvent(new CustomEvent(HELP, { detail: { line, ...opts } }));
export const sayEarlier = (record) => window.dispatchEvent(new CustomEvent(EARLIER, { detail: record }));
