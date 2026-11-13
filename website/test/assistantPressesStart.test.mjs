// THE ASSISTANT MAY START AN AGENT (the owner, 2026-11-02: "why can't assistant start an agent. i'm okay with that. it itself should not be
// the agent"): an agent's job it writes into New carries `start` (concierge._new), and the card presses its own Send to agent once it can go.
// Its page acts likewise may press Send to agent / Send to coding agent - only an outward send stays the owner's.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

// ...and since 2026-11-12 the job is MADE by the Assistant and its task opened (the owner: "assistant tab should not open new but open task
// directly", concierge._made_now): no card filled in and pressed on the way
test("an agent's job the Assistant made opens its task from New's box; no card presses itself", () => {
  const canvas = read("CanvasBrowse.jsx"), sheet = read("NewSheet.jsx");
  assert.doesNotMatch(canvas, /state\?\.start/);
  assert.doesNotMatch(sheet, /autoPressed|start = false/);
  assert.ok(sheet.includes('const made = /^#?task=(\\d+)$/.exec(data?.open || "");'));
  assert.ok(sheet.includes("if (made) { setOk(String(data.say || \"\")); onDone?.(); openIt(Number(made[1]));"));
});

test("the Assistant's press is made once per line, however often its card is drawn again", async () => {
  // a card drawn again pressed Send to agent again on a job already started (2026-11-02)
  const { firstPressOf } = await import("../src/newTask.js");
  assert.equal(firstPressOf(4711), true);
  assert.equal(firstPressOf(4711), false);
  assert.equal(firstPressOf("4711"), false);                  // the same line, however the id arrives
  assert.equal(firstPressOf(4712), true);                     // another line is another press
  assert.equal(firstPressOf(null), true); assert.equal(firstPressOf(null), true);   // no line: the card's own once is all there is
});

test("Send to agent and Send to coding agent are presses the page may make; a Send is not", async () => {
  const src = read("pageView.js");
  const words = new RegExp(/const SEND_WORDS = (\/.*\/i);/.exec(src)[1].slice(1, -2), "i");
  for (const l of ["Send to agent", "Send to coding agent", "Send to a general agent"]) assert.ok(!words.test(l), l);
  for (const l of ["Send", "Send test message", "Approve", "Forward"]) assert.ok(words.test(l), l);
});

test("a general agent's job written into New has words to go: its own box holds them, not the field it no longer draws", async () => {
  // New → "have an agent write a welcome note" came back start:true, the card said "pressed Send to agent" and nothing started: the job's
  // words sit in the chat's box (PromptBox), the readiness was the plain field's (AboutField onReady), never drawn for that card
  const { hasWords } = await import("../src/newTask.js");
  assert.equal(hasWords({ agentBox: true, words: "write a welcome note for Gail", field: false }), true);
  assert.equal(hasWords({ agentBox: true, words: "   ", field: true }), false);
  assert.equal(hasWords({ agentBox: false, words: "", field: true }), true);
  assert.equal(hasWords({ agentBox: false, words: "typed", field: false }), false);
  assert.match(read("NewSheet.jsx"), /const canGo = hasWords\(\{ agentBox, words, field: hasAbout \}\) &&/);
});
