// THE TRACK RECORD (the owner, 2026-10-25: "show the earned-trust track record, but NEVER send without approval"): each draft
// pattern as one read-only line under "Is it working?" - its kind and recipient domain, and what became of its drafts.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { recordRow } from "../src/workingNumbers.js";

test("a pattern reads as its kind, its domain and its non-zero outcomes", () => {
  assert.deepEqual(recordRow({ kind: "reply", domain: "vendor.example", as_drafted: 2, edited: 1, rejected: 0, total: 3 }),
    { label: "reply to vendor.example", cell: "3: 2 sent as drafted · 1 edited" });
});

test("the Settings section is numbers only - no button, no switch, and it says nothing is sent on it", () => {
  const src = readFileSync(new URL("../src/SettingsView.jsx", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("const WorkingNumbers"), src.indexOf("const AuditHistory"));
  assert.match(body, /NOTHING IS SENT WITHOUT YOUR PRESS/);
  assert.doesNotMatch(body, /<Button|<Switch|onClick/);
});
