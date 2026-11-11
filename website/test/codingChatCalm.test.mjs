import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { coalesced } from "../src/visible.js";

// A busy agent's hooks poke task-changed every few seconds; the coding chat read itself on each one, about once a second (2026-11-09)
const flush = () => new Promise((r) => setImmediate(r));

test("a burst of wake-ups is one read at once and one at the end of the gap", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let n = 0;
  const [wake, stop] = coalesced(async () => { n += 1; }, 2500);
  t.after(stop);
  wake(); t.mock.timers.tick(0); await flush();
  assert.equal(n, 1);
  for (let i = 0; i < 10; i++) { t.mock.timers.tick(200); wake(); await flush(); }     // ten pokes inside 2 s
  assert.equal(n, 1);
  t.mock.timers.tick(500); await flush();
  assert.equal(n, 2);                                                                  // ...one more read, at the end of the gap
  t.mock.timers.tick(10000); await flush();
  assert.equal(n, 2);                                                                  // nothing more without a poke
});

test("a wake during a read is one read after it, never two at a time", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let n = 0, open = 0, most = 0, done;
  const [wake, stop] = coalesced(() => { n += 1; open += 1; most = Math.max(most, open); return new Promise((r) => { done = () => { open -= 1; r(); }; }); }, 1000);
  t.after(stop);
  wake(); t.mock.timers.tick(0); await flush();
  t.mock.timers.tick(5000); wake(); wake(); await flush();
  assert.equal(n, 1);
  done(); await flush(); t.mock.timers.tick(0); await flush();
  assert.equal(n, 2); assert.equal(most, 1);
  done(); await flush();
  stop(); wake(); t.mock.timers.tick(5000); await flush();
  assert.equal(n, 2);
});

test("the coding chat reads on task-changed through the coalescer", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/GeneralWorkspace.jsx", import.meta.url)), "utf8");
  assert.match(src, /coalesced\(load, 2500\)[^\n]*onLive\("task-changed"[^\n]*wake\(\)/);
  // ...the conversation's own read (useConversation) asks by revision - an unchanged list answers "same" - so it reads each poke
  assert.match(src, /params: \{ rev: rev\.current \}/);
});
