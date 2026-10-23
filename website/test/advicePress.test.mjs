// LIT AND PRESSED (the deep dive, 2026-10-20): nothing recorded whether the button the Advisor lit was the one pressed. Every press on
// the row - Next included - is heard BEFORE it runs (the line still stands), and the page posts what was lit, what was pressed and the
// revision it was judged at. Nothing on screen changes for it, and a listener that throws never stops the press.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { onPressing, press, put } from "../src/actionRow.js";
import { verbOfRow } from "../src/buttons.js";

test("a press is heard before its handler runs, with the row id, and a listener that throws is not the press's problem", async () => {
  const order = [];
  put("t", [{ id: "done", group: "more", label: "Mark done", run: () => order.push("ran") }]);
  const off = onPressing((id) => order.push(`heard ${id}`));
  const bad = onPressing(() => { throw new Error("lost"); });
  press("done");
  off(); bad(); put("t", null);
  assert.deepEqual(order, ["heard done", "ran"]);
});

test("the row's ids are recorded as the Advisor's verbs: Mark done is close, Remind me is defer", () => {
  assert.equal(verbOfRow("done"), "close");
  assert.equal(verbOfRow("remind"), "defer");
  assert.equal(verbOfRow("12:approve"), "approve");
});

test("the desk posts EVERY press - lit or not - with what its row had filled and what else it offered (phase B, 2026-10-23)", () => {
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(view, /useEffect\(\(\) => onPressing\(notePress\), \[notePress\]\);/);
  assert.match(view, /notePressed\(api, \{ key, surface: "desk", \.\.\.deskPress\(rowNow\(\), pickRef\.current, id\), advised: a\?\.verb \|\| null, revision: a\?\.revision \|\| null \}\);/);
  // the gate is gone: no line shown is no reason to drop the press - only the Tasks tab's own presses are left to that tab
  assert.doesNotMatch(view, /if \(!a\?\.key \|\| !a\.verb \|\| !pressed\) return;/);
  assert.match(view, /if \(!activeRef\.current\) return;/);
  assert.match(view, /pickRef\.current = stripPick \|\| setupLit;/);
  // a move the row has no button for is recorded where it is pressed - once, never also through the row
  assert.match(view, /if \(real\) \{ pressRow\(real\.id, null, anchor\); return null; \}\n\s+notePress\(liveVerb\(a\.verb\)\);/);
});
