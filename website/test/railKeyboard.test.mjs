// THE RAIL IS ONE TAB STOP (owner-approved, 2026-10-20): a listbox with a roving tabindex - Up/Down move the focus ring, Enter opens
// the row as a click does, Escape gives focus back. Nothing drawn but a focus outline. (JSX cannot load under bare node: read the source.)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = src("AssistantView.jsx"), css = src("assistantView.css");


test("Up/Down move the ring, Enter is the click, Escape returns focus to where it came from", () => {
  const key = view.slice(view.indexOf("const railKey = (e) =>"), view.indexOf("// A ROW THAT JOINS"));
  assert.match(key, /\["ArrowDown", "ArrowUp", "Enter", "Escape"\]\.includes\(e\.key\)\) return;/, "every other key is left alone");
  assert.match(key, /if \(e\.key === "Enter"\) \{ all\[at\]\.click\(\); return; \}/);
  assert.match(key, /if \(b\?\.isConnected\) b\.focus\(\); else all\[at\]\.blur\(\);/);
  assert.match(key, /at \+ \(e\.key === "ArrowDown" \? 1 : -1\)/);
  assert.match(view, /onFocus=\{\(e\) => \{ if \(!wrapRef\.current\?\.contains\(e\.relatedTarget\)\) kbdBack\.current = e\.relatedTarget \|\| null; \}\}/);
});
