import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pressable } from "../src/pressable.js";

// MOUSE-ONLY CONTROLS (the UI audit, 2026-10-21): setup's and the catalogue's cards, the rail's section heads and fold arrows, the task
// page's section heads, To's "change", "+ loop someone in" and New's tabs - Tab skipped every one
const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("pressable is a button for the keyboard: Tab reaches it, Enter and Space press it, a key meant for a child is the child's", () => {
  const hits = [], p = pressable((e) => hits.push(e.key || "click"));
  assert.equal(p.role, "button"); assert.equal(p.tabIndex, 0);
  const key = (k, inner = false) => { const el = {}; let stopped = false;
    p.onKeyDown({ key: k, target: inner ? {} : el, currentTarget: el, preventDefault: () => { stopped = true; } }); return stopped; };
  assert.equal(key("Enter"), true); assert.equal(key(" "), true); assert.equal(key("a"), false); assert.equal(key("Enter", true), false);
  assert.deepEqual(hits, ["Enter", " "]);
  assert.deepEqual(pressable(() => {}, false), {}, "a card with nothing to press stays out of the Tab order");
  assert.deepEqual(pressable(undefined), {});
});
