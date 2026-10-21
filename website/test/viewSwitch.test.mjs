// One switch, three views (the owner, 2026-10-15: "remove the task option in chat/task/game ... Chat, Board, then Game. make
// it a little bigger so they are more obvious ... Remove the Board by itself").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("the top bar is Chat | Board | Game, in that order, with no Board button and no Task mode", () => {
  const page = read("TaskHubPage.jsx"), view = read("AssistantView.jsx");
  const keys = [...page.matchAll(/\{ k: "(\w+)", label: "(\w+)"/g)].map((m) => m[2]);
  assert.deepEqual(keys, ["Chat", "Board", "Game"]);
  assert.doesNotMatch(page, /data-tq-view-switch=\{tab === "Board" \? "assistant" : "board"\}/);   // the lone Board button
  assert.doesNotMatch(view, />Task<\/button>/);
  assert.match(page, /height: 34/);                                     // bigger than the 30px pill it replaces
});

test("Board opens the Board; Chat and Game are the Assistant, walked or not", () => {
  const page = read("TaskHubPage.jsx");
  assert.match(page, /onView=\{\(v\) => \{ if \(v === "board"\) \{ go\("Board"\); return; \} pickAsstGame\(v === "game"\); go\("Assistant"\); \}\}/);
});

test("the Board's New task opens on New's agent tab", () => {
  const sheet = read("NewSheet.jsx");
  assert.match(sheet, /initialKind = "send", initialHow = "", initialText = "", line = null, onSaid \}\) \{\n  const \[kind, setKind\] = useState\(initialKind\);/);
  assert.match(sheet, /setKind\(initialKind\); \}, \[open, initialKind\]\);/);
});
