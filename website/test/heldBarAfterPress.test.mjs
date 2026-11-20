// A HELD BROWSER STEP'S BAR ONCE ITS PRESS IS ANSWERED (the owner's live app, 2026-11-19: he approved a held step, it ran at 11:25:31 and
// the decide answered - and the bar's Approve still read "running…": busy was cleared only on a failure, the bar waiting for the task's
// re-read to take it away, minutes behind a slow server). The answer ends the press: what it did, or why not.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { afterPress } from "../src/press.js";

test("an answered press is never still busy: what it did, or why it did not", () => {
  assert.deepEqual(afterPress({ kind: "ok", data: { ok: true } }, "approve"), { busy: "", done: "approve", err: "" });
  assert.deepEqual(afterPress({ kind: "already", data: { already: true } }, "approve"), { busy: "", done: "approve", err: "" });
  const f = afterPress({ kind: "failed", data: { ok: false }, why: "The page had moved on." }, "approve");
  assert.deepEqual(f, { busy: "", done: "", err: "The page had moved on." });
  assert.equal(afterPress({ kind: "unknown", data: null, why: "" }, "reject").busy, "");
});

