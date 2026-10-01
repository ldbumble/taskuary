import assert from "node:assert/strict";
import test from "node:test";
import { createPool, paneCap } from "../src/terminalPool.js";

const pool = () => { const gone = []; return [createPool((s) => gone.push(s.id)), gone]; };

test("a pane put away comes back as the same pane", () => {
  const [p] = pool(), s = { id: "a" };
  p.keep("a", s, 4);
  assert.equal(p.take("a"), s);
  assert.equal(p.take("a"), null, "taken means it is on screen again, not still kept");
});

test("over the cap the pane looked at longest ago goes first", () => {
  const [p, gone] = pool();
  for (const id of ["a", "b", "c"]) p.keep(id, { id }, 2);
  assert.deepEqual(gone, ["a"]);
  p.keep("b", p.take("b"), 2);                     // b looked at again: now c is the oldest
  p.keep("d", { id: "d" }, 2);
  assert.deepEqual(gone, ["a", "c"]);
  assert.equal(p.size(), 2);
});

test("a second pane on the same session replaces the first rather than leaking it", () => {
  const [p, gone] = pool();
  p.keep("a", { id: "first" }, 4); p.keep("a", { id: "second" }, 4);
  assert.deepEqual(gone, ["first"]);
  assert.equal(p.take("a").id, "second");
});

test("a session that ended is forgotten without being disposed twice", () => {
  const [p, gone] = pool(), s = { id: "a" };
  p.keep("a", s, 4); p.forget("a", { id: "other" });
  assert.equal(p.size(), 1, "forget only drops the pane it names");
  p.forget("a", s);
  assert.equal(p.size(), 0); assert.deepEqual(gone, []);
});

test("the cap follows Agents at once, clamped like the server", () => {
  assert.equal(paneCap("8"), 8); assert.equal(paneCap(undefined), 4);
  assert.equal(paneCap("0"), 1); assert.equal(paneCap("99"), 16); assert.equal(paneCap("-3"), 1);
});
