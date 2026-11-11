import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// A PRESS IS AN EVENT (the owner, 2026-11-09): "You changed its workstream." was drawn in a bubble under "You", as if typed
const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
const at = ws.indexOf("export const pressLine"), src = ws.slice(at, ws.indexOf(String.fromCharCode(10), at));
const pressLine = new Function(`${src.replace("export ", "")}; return pressLine;`)();

test("a press reads as an event line: its words, no stop, then the time", () => {
  assert.equal(pressLine("You changed its workstream.", "3:12 PM"), "You changed its workstream · 3:12 PM");
  assert.equal(pressLine("You set a reminder for 9:00 AM.", ""), "You set a reminder for 9:00 AM");
});

test("a press is drawn as the quiet event line, never the owner's bubble", () => {
  // ...an item of the server's list (kind `press`): its own row, no bubble and no "You" head
  assert.match(ws, /className=\{`tq-aui-message tq-aui-press\$\{prev && \(prev\.kind === "press" \|\| prev\.kind === "note"\) \? " tq-aui-press-more" : ""\}`\} data-tq-item=\{x\.id\} data-tq-chat-press=""/);
  assert.match(ws, /<div className="tq-aui-press-line">\{pressLine\(x\.text, x\.at \? when\(String\(x\.at\)\) : ""\)\}<\/div>/);
});
