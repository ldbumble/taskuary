import test from "node:test";
import assert from "node:assert/strict";
import { syncFace, syncStatusDelay } from "../src/syncTiming.js";
import { setLocale } from "../src/i18n.js";

setLocale("en");   // English contract below; pt-BR face is pinned in its own test

test("sync status checks quietly when the scheduled refresh is far away", () => {
  assert.equal(syncStatusDelay({ nextAt: 600_000, now: 0 }), 30_000);
});

test("sync status watches closely around the scheduled refresh", () => {
  assert.equal(syncStatusDelay({ nextAt: 20_000, now: 0 }), 500);
  assert.equal(syncStatusDelay({ nextAt: 10_000, now: 20_000 }), 500);
});

test("an observed running sync is followed every two seconds", () => {
  assert.equal(syncStatusDelay({ running: true, nextAt: 600_000, now: 0 }), 2000);
});

test("the sync clock reads the same on the Timeline and in the pipe", () => {
  const at = new Date(2026, 8, 3, 10, 42);
  const face = { every: 10, lastAt: at, nextIn: 271 };
  assert.equal(syncFace(face), "synced 10:42 AM · next in 4:31");
  assert.equal(syncFace({ ...face, terse: true }), "synced 10:42 AM");
  assert.equal(syncFace({ ...face, nextIn: 0 }), "synced 10:42 AM · next sync due now");
});

test("a running sync and a disabled one say so in both faces", () => {
  assert.equal(syncFace({ busy: true, what: "reading Outlook" }), "reading Outlook");
  assert.equal(syncFace({ busy: true, what: "reading Outlook", terse: true }), "syncing…");
  assert.equal(syncFace({ every: 0 }), "background sync off");
  assert.equal(syncFace({ every: 0, terse: true }), "sync off");
});

test("no poll yet never invents a time", () => {
  assert.equal(syncFace({ every: 10, lastAt: null, nextIn: null }), "synced —");
});

test("the sync clock follows the pt-BR locale", () => {
  setLocale("pt-BR");
  try {
    assert.equal(syncFace({ every: 10, lastAt: new Date(2026, 8, 3, 10, 42), nextIn: 271, failed: ["Outlook"] }),
      "sincronizado 10:42 · próxima em 4:31 · falha em Outlook");
    assert.equal(syncFace({ every: 0 }), "sincronização em segundo plano desligada");
  } finally { setLocale("en"); }
});
