// THE RAIL IS ONE TAB STOP (owner-approved, 2026-10-20): a listbox with a roving tabindex - Up/Down move the focus ring, Enter opens
// the row as a click does, Escape gives focus back. Nothing drawn but a focus outline. (JSX cannot load under bare node: read the source.)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = src("AssistantView.jsx"), css = src("assistantView.css");

test("the rail is a listbox whose rows are options, exactly one of them in the Tab order", () => {
  assert.match(view, /className="tq-pile" data-tq-keep ref=\{wrapRef\} role="listbox" aria-label="Your list" onKeyDown=\{railKey\}/);
  assert.match(view, /<div className="card" role="option" aria-selected=\{isCur\} aria-disabled=\{i\.settling \? true : undefined\}\s+tabIndex=\{i\.key === tabKey \? 0 : -1\}/);
  // the stop is the row the keyboard was last on, else the row on the table, else the first row drawn
  assert.match(view, /const tabKey = stops\.includes\(kbdKey\) \? kbdKey : stops\.includes\(curKey\) \? curKey : stops\[0\];/);
  assert.match(view, /const stops = bands\.flatMap\(\(\{ level, items: rows \}\) => shownIn\(level, rows\)\)\.filter\(\(i\) => !i\.settling\)/,
    "only rows the rail draws and a click can open");
  assert.match(view, /const shown = shownIn\(level, rows\);/, "the stops and the drawing read one cap");
});

test("Up/Down move the ring, Enter is the click, Escape returns focus to where it came from", () => {
  const key = view.slice(view.indexOf("const railKey = (e) =>"), view.indexOf("// A ROW THAT JOINS"));
  assert.match(key, /\["ArrowDown", "ArrowUp", "Enter", "Escape"\]\.includes\(e\.key\)\) return;/, "every other key is left alone");
  assert.match(key, /if \(e\.key === "Enter"\) \{ all\[at\]\.click\(\); return; \}/);
  assert.match(key, /if \(b\?\.isConnected\) b\.focus\(\); else all\[at\]\.blur\(\);/);
  assert.match(key, /at \+ \(e\.key === "ArrowDown" \? 1 : -1\)/);
  assert.match(view, /onFocus=\{\(e\) => \{ if \(!wrapRef\.current\?\.contains\(e\.relatedTarget\)\) kbdBack\.current = e\.relatedTarget \|\| null; \}\}/);
});

test("the only thing drawn for it is a focus outline", () => {
  assert.match(css, /\.tq-pile-row \.card:focus-visible \{ outline: 2px solid #55697a; outline-offset: -2px; \}/);
  assert.match(css, /\.tq-pile-row \.card:focus \{ outline: none; \}/, "a mouse click draws no ring");
});
