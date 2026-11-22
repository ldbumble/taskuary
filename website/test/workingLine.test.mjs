// A REAL ANSWER COUNTS ITS SECONDS (the owner, 2026-10-20: "working... Ns"): a CLI brain took 4-51 s behind three silent dots,
// which read as hung. The count joins the dots on a typed ask's real answer - never the demo's script, never Next or the phone -
// and lives in its own component, so the chat around it does not redraw every second.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { workingLine } from "../src/agentWork.js";

const src = fs.readFileSync(path.join(import.meta.dirname, "../src/AssistantView.jsx"), "utf8");

test("nothing in the first second, then whole seconds that never run ahead", () => {
  assert.equal(workingLine(0), "");
  assert.equal(workingLine(999), "");
  assert.equal(workingLine(1000), "Working… 1s");
  assert.equal(workingLine(6999), "Working… 6s");
  assert.equal(workingLine(65400), "Working… 1m 05s");
});


// THE TURN'S HEAD AND ITS WORKING LINE ARE THE CHAT'S OWN TYPE (the owner, again on 2026-11-18: "AGENT · 11:04 PM · working 2m 41s" in tiny
// monospace capitals beside a monospace working line): no rule in the chat's sheet sets them in a code face or in capitals
test("the turn's head and the working line are set in the app's font and case", async () => {
  const fs = await import("node:fs");
  const css = fs.readFileSync(new URL("../src/generalWorkspace.css", import.meta.url), "utf8");
  const rules = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].filter(([, sel]) => /\.tq-aui-role\b|\.tq-aui-thinking span|\.tq-aui-working-line/.test(sel));
  assert.ok(rules.length >= 2);
  for (const [, sel, body] of rules) assert.doesNotMatch(body, /monospace|Cascadia|Consolas|uppercase/i, `${sel.trim()} sets ${body.trim()}`);
});

// THE DETAIL LEVEL'S STOPS ARE BUTTONS (the UX walk, 2026-11-18: a slider's "Everything" was no button to press): one each, the current pressed
test("the chat's detail control offers each level as a button", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("../src/DetailSlider.jsx", import.meta.url), "utf8");
  assert.match(src, /<ToggleButtonGroup exclusive/);
  assert.doesNotMatch(src, /<Slider\b/);
});
