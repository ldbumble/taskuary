// WHAT IS TYPED AND NOT SENT STAYS IN ITS TASK'S BOX, AND THE ARROW SENDS WHILE THE AGENT WORKS (the owner, 2026-11-10; agent walk 2: a reload
// lost a half-written line, and the send arrow stood grey over typed words for as long as the agent's turn ran - Enter held the line, the arrow did not)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { holdUnsent, keepUnsent, unsent } from "../src/unsent.js";

const box = () => { const m = new Map(); return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("typed words are kept per task and come back as typed", () => {
  const s = box();
  keepUnsent(7, "tell Erin Thursday works  ", s); keepUnsent(8, "second task", s);
  assert.equal(unsent(7, s), "tell Erin Thursday works  ");
  assert.equal(unsent(8, s), "second task");
  assert.equal(unsent(9, s), "");
});

test("a sent or emptied box keeps nothing", () => {
  const s = box();
  keepUnsent(7, "half a line", s); keepUnsent(7, "", s);
  assert.equal(unsent(7, s), ""); assert.equal(s.m.size, 0);
  keepUnsent(7, "half a line", s); keepUnsent(7, "   \n", s);
  assert.equal(s.m.size, 0, "spaces alone are not a line");
});

test("no task, no storage and a storage that refuses are all the box alone", () => {
  const s = box(), refuses = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); }, removeItem() { throw new Error("blocked"); } };
  keepUnsent(null, "words", s); assert.equal(s.m.size, 0);
  assert.equal(unsent(null, s), "");
  assert.doesNotThrow(() => { keepUnsent(7, "words", refuses); keepUnsent(7, "", refuses); keepUnsent(7, "words", null); });
  assert.equal(unsent(7, refuses), ""); assert.equal(unsent(7, null), "");
});


// a composer as assistant-ui's: its text, and who listens to it
const composer = (text = "") => { const fns = new Set(); let t = text;
  return { getState: () => ({ text: t }), setText: (x) => { t = x; fns.forEach((f) => f()); }, subscribe: (f) => { fns.add(f); return () => fns.delete(f); }, type: (x) => { t = x; fns.forEach((f) => f()); } }; };

test("a box that stays while its task changes under it (the Assistant's walk) shows each task's own words", () => {
  const s = box(), c = composer(), was = { current: 7 };
  keepUnsent(8, "for Gail: the totals are fixed", s);
  let off = holdUnsent(c, 7, was, s);
  c.type("tell Erin Thursday works");                      // typed on the first task, not sent
  off(); off = holdUnsent(c, 8, was, s);                    // ...the walk moves on to the next
  assert.equal(c.getState().text, "for Gail: the totals are fixed", "the next task's box shows its own words");
  assert.equal(unsent(8, s), "for Gail: the totals are fixed", "and they are not overwritten with the last task's");
  assert.equal(unsent(7, s), "tell Erin Thursday works", "the first task keeps its own");
  off(); off = holdUnsent(c, 9, was, s);
  assert.equal(c.getState().text, "", "a task with nothing typed shows an empty box");
  assert.equal(unsent(9, s), "");
  off(); holdUnsent(c, 7, was, s);
  assert.equal(c.getState().text, "tell Erin Thursday works", "back on the first task, its words are back");
});

test("a box drawn afresh on its task puts its words back, and never over words already in it", () => {
  const s = box(); keepUnsent(7, "half a line", s);
  const c = composer(); holdUnsent(c, 7, { current: 7 }, s);
  assert.equal(c.getState().text, "half a line");
  const seeded = composer("rerun it with these notes"); holdUnsent(seeded, 7, { current: 7 }, s);
  assert.equal(seeded.getState().text, "rerun it with these notes");
});
