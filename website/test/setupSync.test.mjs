import test from "node:test";
import assert from "node:assert/strict";
import { firstSyncProgress, startFirstSync } from "../src/setupSync.js";

const reader = (ingest, state) => ({ get: async (url) => ({ data: url === "/api/setup" ? state : ingest }) });

test("first sync calls the real poll and accepts an already running read", async () => {
  const calls = [];
  for (const report of ["running", "busy"]) {
    assert.equal(await startFirstSync({ post: async (url) => { calls.push(url); return { data: { report } }; } }), report);
  }
  assert.deepEqual(calls, ["/api/ingest/poll", "/api/ingest/poll"]);
  await assert.rejects(startFirstSync({ post: async () => ({ data: {} }) }), /did not start/);
});

test("a started HTTP request is not a first useful result", async () => {
  const state = { steps: [{ key: "sync", done: false }], pending: false };
  assert.equal((await firstSyncProgress(reader({ status: { state: "running" } }, state))).phase, "reading");
  assert.equal((await firstSyncProgress(reader({ status: { state: "running" } }, { ...state, steps: [{ key: "sync", done: true }] }))).phase, "reading");
  assert.equal((await firstSyncProgress(reader({ status: { state: "idle" } }, { ...state, pending: true }))).phase, "reading");
  const empty = await firstSyncProgress(reader({ status: { state: "idle" } }, state));
  assert.equal(empty.phase, "empty");
  assert.match(empty.message, /source scope/);
});

test("source and AI failures remain visible even when older items exist", async () => {
  const result = await firstSyncProgress(reader({ status: { state: "idle" }, failed: ["gmail"], triageError: "AI key rejected" },
    { steps: [{ key: "sync", done: true }] }));
  assert.equal(result.phase, "failed");
  assert.match(result.message, /gmail/);
  assert.match(result.message, /AI key rejected/);
});

test("a genuine first result carries the review sample to the panel", async () => {
  const state = { steps: [{ key: "sync", done: true }], first_items: [{ MessageId: 41, Subject: "Invented request" }] };
  const result = await firstSyncProgress(reader({ status: { state: "idle" } }, state));
  assert.equal(result.phase, "ready");
  assert.deepEqual(result.state.first_items, state.first_items);
});
