// A step the agent's own shell, browser or desktop held is the AGENT's: its Approve or Dismiss, pressed in the agent's pane, never opens
// Close out over the agent it sets going again (the desktop run, 2026-11-04: the page read "close agent_working" a fifth of a second after
// Dismiss - the press was announced as "<review>:reject", and every "<id>:" press opened Close out as a draft's Send does).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a held step's press is not a Close out press", () => {
  assert.match(src, /heldRef\.current = new Set\(allReviews\.filter\(\(r\) => r\.Kind === "action"\)\.map\(\(r\) => String\(r\.ReviewId\)\)\);/);
  const m = src.match(/useEffect\(\(\) => onPressing\(\(id\) => \{([\s\S]*?)\}\), \[\]\);/);
  assert.ok(m, "the press handler");
  // the handler's own rule, run on the ids a press announces
  const rule = new Function("id", "heldRef", "VERB_SECTION", "openSecRef", m[1]);
  const VERB_SECTION = { close: new Set(["reply", "done"]), agent: new Set(["continue"]) };
  const opened = [], openSecRef = { current: (s) => opened.push(s) }, heldRef = { current: new Set(["7"]) };
  for (const id of ["7:approve", "7:reject", "8:approve", "done", "continue"]) rule(id, heldRef, VERB_SECTION, openSecRef);
  assert.deepEqual(opened, ["close", "close", "agent"]);      // a draft's Send (8) and Mark done still open Close out; the held step's never
});
