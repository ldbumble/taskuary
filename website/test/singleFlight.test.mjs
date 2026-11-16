// ONE READ OF A TASK'S CONVERSATION AT A TIME (the owner's live app, 2026-11-16: six identical GETs of one task's list in the same second, every few
// seconds): every view and listener reads through one shared read per task
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { shared } from "../src/singleFlight.js";

test("reads asked while one is on its way join it; the next after it lands is its own", async () => {
  const inflight = new Map(); let calls = 0, done;
  const start = () => { calls += 1; return new Promise((r) => { done = r; }); };
  const six = Array.from({ length: 6 }, () => shared(inflight, 7, start));
  await Promise.resolve();
  assert.equal(calls, 1);
  done({ data: { rev: "a" } });
  const got = await Promise.all(six);
  assert.ok(got.every((g) => g === got[0]));
  shared(inflight, 7, start); await Promise.resolve(); assert.equal(calls, 2, "a read after the first landed is a new one");
  shared(inflight, 8, start); await Promise.resolve(); assert.equal(calls, 3, "another task's read is its own");
});

test("the chat's list is read through the shared read", () => {
  const src = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /shared\(READS, tid, \(\) => api\.get\(`\/api\/tasks\/\$\{tid\}\/conversation`/);
  assert.equal((src.match(/\/conversation`/g) || []).length, 1, "one place reads it");
});
