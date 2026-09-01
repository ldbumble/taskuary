import test from "node:test";
import assert from "node:assert/strict";
import { continueCoding } from "../src/continueCoding.js";

test("continuing uses the exact-checkout route when the desktop supports it", async () => {
  const calls = [];
  const client = { post: async (url, body) => {
    calls.push([url, body]);
    return { data: { session: { sid: "continued" } } };
  } };

  const out = await continueCoding(client, 287, "make the changes", "claude");
  assert.equal(out.data.session.sid, "continued");
  assert.deepEqual(calls, [["/api/tasks/287/continue", { instruction: "make the changes" }]]);
});

test("an already-running older desktop falls back to its existing dispatch route", async () => {
  const calls = [];
  const client = { post: async (url, body) => {
    calls.push([url, body]);
    if (url.endsWith("/continue")) {
      const error = new Error("route missing");
      error.response = { status: 404, data: { detail: "Not Found" } };
      throw error;
    }
    return { data: { session: { sid: "fallback" } } };
  } };

  const out = await continueCoding(client, 287, "make the changes", "claude");
  assert.equal(out.data.session.sid, "fallback");
  assert.deepEqual(calls, [
    ["/api/tasks/287/continue", { instruction: "make the changes" }],
    ["/api/tasks/287/dispatch", { agent: "claude", instruction: "make the changes" }],
  ]);
});

test("a real missing task is not mistaken for a missing route", async () => {
  const missing = new Error("task missing");
  missing.response = { status: 404, data: { detail: "task not found" } };
  const client = { post: async () => { throw missing; } };
  await assert.rejects(() => continueCoding(client, 287, "make the changes", "claude"), missing);
});
