import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { planTask } from "../src/newTask.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const rows = [{ repo: "northwind/ledger", has_path: true }, { repo: "northwind/portal", has_path: false }, { repo: "org/app", has_path: true }];

test("the chosen repository becomes the new task's repo tag, and a chat has none", () => {
  assert.match(planTask("northwind/ledger", "terminal", false, true).tags, /repo:northwind\/ledger/);
  assert.equal(planTask(null, "terminal", false, true).tags, "stay:open");                 // auto, nothing named: no tag
  assert.equal(planTask(null, "terminal", false, true).kind, "coding");
});

test("New is a card in the conversation, not a popup: the button posts it, a link opens it, closing removes it", () => {
  const view = read("AssistantView.jsx"), feed = read("FeedView.jsx"), browse = read("CanvasBrowse.jsx"), sheet = read("NewSheet.jsx");
  assert.match(feed, /n\.key === "new" && !onGo \? setNewOpen\(true\) : onGo\?\.\(n\.go, n\.key\)/);   // the dialog survives only where there is no canvas
  assert.match(view, /request\.kind === "new"\) browseRef\.current\?\.\("new", request\.state \|\| \{\}\)/);
  assert.match(view, /browseClose: \(id\) => setMsgs\(\(m\) => m\.filter\(\(x\) => x\.id !== id\)\)/);
  assert.match(browse, /area === "new"\) return \(/);
  assert.match(browse, /<NewSheet key=\{.+?\} inline open onClose=\{onClose\}/);
  assert.match(sheet, /if \(e\.key === "Escape"\) close\(\)/);                               // Esc closes the card
});

test("New is one box that hands the words to the one start: no tabs, and no agent, model or repository to pick (TQ-1397)", () => {
  const sheet = read("NewSheet.jsx"), browse = read("CanvasBrowse.jsx"), board = read("BoardView.jsx");
  assert.match(sheet, /initialKind = "chat"/);                                                  // opened by the owner: the one box
  assert.match(browse, /initialKind=\{state\?\.kind \|\| "chat"\}/);                            // ...a card the Assistant wrote keeps its kind
  assert.doesNotMatch(board, /initialKind="agent"/);
  assert.doesNotMatch(sheet, /data-tq-new-kinds|role="tab"|NewRepo|AgentPicker|\/api\/repos|Who works it/);
  // ...THE ONE START (F1, the walks 2026-11-18): his words and files to /api/start, its task opened - never the Assistant's model picking a form
  assert.match(sheet, /api\.post\("\/api\/start", \{ text: about, images: pics\.paths \|\| \[\] \}\)/);
  assert.doesNotMatch(sheet, /concierge\/say|goStraight|setMade/);
  assert.doesNotMatch(sheet, /askAssistant\(/);
});
