// A DOOR FOR WHAT FITS NO TAB (Gabi, TQ-1358: "we should have a 'chat with Taskuary' option. some things dont fit into these categories"):
// New's last tab hands its words to the Assistant's chat as a line typed there - and is not offered on the Board, where no chat is on screen.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { askAssistant, takeAsk } from "../src/askAssistant.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("New has a Chat with Taskuary tab, last, whose press says the words in the chat and closes the sheet", () => {
  const src = read("NewSheet.jsx");
  assert.ok(src.indexOf('key: "playbook"') < src.indexOf('key: "chat", mark: "💬", label: "Chat with Taskuary"'));
  assert.match(src, /kind === "chat"\) \{[\s\S]{0,200}askAssistant\(about\);[^\n]*onClose\?\.\(\);/);
  assert.match(src, /kind === "chat" \? "Ask Taskuary"/);
  assert.match(src, /KINDS\.filter\(\(k\) => chat \|\| k\.key !== "chat"\)/);
});

test("the Board's sheet leaves the chat door out", () => {
  assert.match(read("BoardView.jsx"), /<NewSheet open=\{newOpen\}[^\n]*initialKind="agent" chat=\{false\}/);
});

test("the words wait for the Assistant and are taken once", () => {
  globalThis.window ??= new EventTarget();
  askAssistant("what's still open with Payworth?");
  assert.equal(takeAsk(), "what's still open with Payworth?");
  assert.equal(takeAsk(), null);
});
