// HINTS ON A LONG PRESS (owner-approved, 2026-10-20): tooltips were turned off on touch, and with them every hint a phone had. A finger
// held still ~500 ms shows the control's hint and its release fires nothing; a tap is a tap; a mouse is untouched.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { HOLD_MS, hintOf, installTouchHints, placeHint } from "../src/touchHint.js";

// a document of one button, with timers the test turns by hand
function world({ attrs = { title: "Closes the task" }, inside = "" } = {}) {
  const on = {}, body = [], q = [];
  let clock = 0;
  const timers = { setTimeout: (f, ms) => { q.push({ at: clock + ms, f }); return q.length; }, clearTimeout: (id) => { if (q[id - 1]) q[id - 1].f = null; } };
  const tick = (ms) => { clock += ms; for (const t of q) if (t.f && t.at <= clock) { const f = t.f; t.f = null; f(); } };
  const btn = { getAttribute: (k) => attrs[k] ?? null,
    closest: (sel) => (sel.includes("xterm") || sel.includes("input") ? (inside ? btn : null) : sel === "[title]" ? (attrs.title ? btn : null) : attrs["aria-label"] ? btn : null) };
  const doc = { body: { appendChild: (el) => body.push(el) }, defaultView: { innerWidth: 390 },
    createElement: () => { const el = { style: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, remove() { body.splice(body.indexOf(el), 1); },
      getBoundingClientRect: () => ({ width: 120, height: 30 }) }; return el; },
    addEventListener: (k, f) => { on[k] = f; }, removeEventListener: (k) => { delete on[k]; } };
  const fire = (k, e = {}) => { const ev = { target: btn, clientX: 100, clientY: 300, pointerType: "touch", prevented: false, stopped: false,
    preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...e }; on[k]?.(ev); return ev; };
  const off = installTouchHints(doc, { timers });
  return { body, fire, tick, off };
}

test("a finger held still on a control shows its hint, and the release fires no button", () => {
  const w = world();
  w.fire("pointerdown"); w.tick(HOLD_MS - 1);
  assert.equal(w.body.length, 0, "not before the hold");
  w.tick(1);
  assert.equal(w.body.length, 1); assert.equal(w.body[0].textContent, "Closes the task"); assert.equal(w.body[0].attrs.role, "tooltip");
  w.fire("pointerup");
  const click = w.fire("click");
  assert.ok(click.prevented && click.stopped, "the held press is a question, not a press");
  w.tick(2000);
  assert.equal(w.body.length, 0, "and it goes by itself");
  w.off();
});

test("a tap is a tap, a finger that moves is a scroll, and a mouse is left alone", () => {
  const w = world();
  w.fire("pointerdown"); w.tick(120); w.fire("pointerup");
  const tap = w.fire("click");
  assert.ok(!tap.prevented && !tap.stopped); assert.equal(w.body.length, 0);
  w.fire("pointerdown"); w.fire("pointermove", { clientX: 100, clientY: 330 }); w.tick(HOLD_MS);
  assert.equal(w.body.length, 0, "moved past the slop: no hint");
  w.fire("pointerdown", { pointerType: "mouse" }); w.tick(HOLD_MS);
  assert.equal(w.body.length, 0, "a mouse has its tooltips");
  w.off();
});

test("the browser's own long-press menu does not open over a hint, and the next press starts clean", () => {
  const w = world();
  w.fire("pointerdown"); w.tick(HOLD_MS);
  assert.equal(w.fire("contextmenu").prevented, true);
  w.fire("pointerdown"); assert.equal(w.body.length, 0, "a new press takes the hint down");
  w.fire("pointerup"); assert.equal(w.fire("click").prevented, false);
  w.off();
});

test("the hint is the control's title, else its own name - never a text field's or a terminal's", () => {
  const el = (attrs, inside = false) => ({ getAttribute: (k) => attrs[k] ?? null,
    closest(sel) { return sel.includes("xterm") ? (inside ? this : null) : sel === "[title]" ? (attrs.title ? this : null) : attrs["aria-label"] ? this : null; } });
  assert.equal(hintOf(el({ title: " Remind me tomorrow " })), "Remind me tomorrow");
  assert.equal(hintOf(el({ "aria-label": "Open full task" })), "Open full task");
  assert.equal(hintOf(el({ title: "Type here" }, true)), "");
  assert.equal(hintOf(el({})), "");
  assert.equal(hintOf(null), "");
});

test("the bubble sits above the finger and on the screen", () => {
  assert.deepEqual(placeHint({ x: 380, y: 300 }, 120, 30, 390), { left: 262, top: 242 });
  assert.deepEqual(placeHint({ x: 10, y: 20 }, 120, 30, 390), { left: 8, top: 48 }, "under it at the top edge");
});

test("the app installs it once, beside the one-line strip", () => {
  assert.match(readFileSync(new URL("../src/main.jsx", import.meta.url), "utf8"), /import \{ installTouchHints \} from "\.\/touchHint\.js";\ninstallTouchHints\(\);/);
});
