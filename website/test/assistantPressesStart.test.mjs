// THE ASSISTANT MAY START AN AGENT (the owner, 2026-11-02: "why can't assistant start an agent. i'm okay with that. it itself should not be
// the agent"): an agent's job it writes into New carries `start` (concierge._new), and the card presses its own Send to agent once it can go.
// Its page acts likewise may press Send to agent / Send to coding agent - only an outward send stays the owner's.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("New's card presses its own start, once, when the Assistant wrote an agent's job into it", () => {
  const canvas = read("CanvasBrowse.jsx"), sheet = read("NewSheet.jsx");
  assert.match(canvas, /start=\{!!state\?\.start\}/);
  assert.match(sheet, /line = null, onSaid, start = false,/);
  assert.match(sheet, /if \(!start \|\| autoPressed\.current \|\| kind !== "agent" \|\| !canGo \|\| !agentsRead \|\| busy\) return;\s*\n\s*autoPressed\.current = true; submit\(\);/);
  // ...before the sheet's early return, so the hook runs on every draw
  assert.ok(sheet.indexOf("autoPressed.current = true") < sheet.indexOf("if (inline && !open) return null;"));
});

test("Send to agent and Send to coding agent are presses the page may make; a Send is not", async () => {
  const src = read("pageView.js");
  const words = new RegExp(/const SEND_WORDS = (\/.*\/i);/.exec(src)[1].slice(1, -2), "i");
  for (const l of ["Send to agent", "Send to coding agent", "Send to a general agent"]) assert.ok(!words.test(l), l);
  for (const l of ["Send", "Send test message", "Approve", "Forward"]) assert.ok(words.test(l), l);
});
