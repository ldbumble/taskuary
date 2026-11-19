// ONE OVERLAY AT A TIME, EACH WITH A CLOSE IN SIGHT, AND TYPING LANDS IN THE BOX HE CAN SEE (the 2026-11-18 walks: Search stayed open over a
// page that moved and swallowed two instructions; "Report this bug" lost its Close and sat under Search taking every word; a picture's viewer
// dropped "Post them..." without a word)
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { boxBeneath, typesText } from "../src/overlays.js";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("every overlay of the walks goes through the one road, and the ones with no box of their own type through", () => {
  assert.match(read("SearchEverything.jsx"), /useOverlay\(open, onClose\);/);
  assert.match(read("BugReportDialog.jsx"), /useOverlay\(open, onClose\);/);
  assert.match(read("PublishedPages.jsx"), /useOverlay\(!!file, onClose, \{ typeThrough: true \}\);/);
  assert.match(read("md.jsx"), /useOverlay\(!!url, onClose, \{ typeThrough: true \}\);/);
  assert.match(read("md.jsx"), /useOverlay\(big, \(\) => setBig\(false\), \{ typeThrough: true \}\);/);
  const road = read("overlays.js");
  assert.match(road, /window\.dispatchEvent\(new CustomEvent\(OPENED, \{ detail: me \}\)\)/, "opening one shuts the one before it");
  assert.match(road, /const off = onStep\(moved\);/, "the page moving under it shuts it");
});

test("each has a close in sight, whatever it is doing", () => {
  assert.match(read("SearchEverything.jsx"), /aria-label="Close search" data-tq-search-close=""/);
  const bug = read("BugReportDialog.jsx");
  assert.match(bug, /aria-label="Close" data-tq-bug-close="" onClick=\{onClose\}/);
  assert.match(bug, /<Dialog open=\{open\} onClose=\{onClose\}/, "Esc shuts it busy or not");
});

test("a typed character is text; a shortcut, an arrow or Esc is not", () => {
  assert.equal(typesText({ key: "P" }), true);
  assert.equal(typesText({ key: " " }), true);
  for (const e of [{ key: "Escape" }, { key: "ArrowDown" }, { key: "k", ctrlKey: true }, { key: "Enter" }]) assert.equal(typesText(e), false, e.key);
});

test("the box beneath is the agent's box in sight, else the chat's - never one inside an overlay", () => {
  const el = (cls, { shown = true, modal = false } = {}) => ({ cls, disabled: false, getClientRects: () => (shown ? [1] : []), closest: (q) => (modal && q === ".MuiModal-root" ? {} : null) });
  const doc = (map) => ({ querySelectorAll: (q) => map[q] || [] });
  const agent = el("agent"), chat = el("chat");
  assert.equal(boxBeneath(doc({ ".tq-aui-input": [agent], ".tq-compose-field textarea": [chat] })), agent);
  assert.equal(boxBeneath(doc({ ".tq-aui-input": [el("hidden", { shown: false })], ".tq-compose-field textarea": [chat] })), chat);
  assert.equal(boxBeneath(doc({ ".tq-aui-input": [el("over", { modal: true })] })), null);
});

// ...AND A MENU (recorded with a real mouse and keyboard, 2026-11-18): typed into the Change menu, its type-ahead ate the words; clicked past it
// into the box, the focus went back to Change, the words were lost on it and their space pressed Change again
test("a character typed into an open menu, or a click past it, shuts it and his words go on into the box, in order", async () => {
  const { typeThroughMenus } = await import("../src/overlays.js");
  const on = {}, frames = [], said = [], escapes = [];
  let open = true, focused = null;
  const box = { disabled: false, getClientRects: () => [1], closest: () => null, focus() { if (!open) focused = box; } };
  box.closest = (q) => (q.includes("textarea") ? box : null);
  const menu = { dispatchEvent: (e) => { escapes.push(e.key); open = false; } };
  const inMenu = { closest: (q) => (q.includes("role=menu") ? menu : null) }, backdrop = { closest: (q) => (q === ".MuiMenu-root" ? {} : null) };
  const doc = { querySelector: (q) => (q === ".MuiMenu-root" && open ? {} : null), querySelectorAll: (q) => (q === ".tq-aui-input" ? [box] : []),
    get activeElement() { return focused; }, elementFromPoint: () => box, execCommand: (_c, _u, t) => said.push(t) };
  const win = { document: doc, addEventListener: (n, f) => { on[n] = f; }, requestAnimationFrame: (f) => frames.push(f) };
  globalThis.KeyboardEvent ??= class { constructor(type, o) { Object.assign(this, { type, ...o }); } };
  typeThroughMenus(win);
  const key = (k, target) => { const e = { key: k, target, preventDefault() { this.stopped = true; }, stopPropagation() {} }; on.keydown(e); return e; };
  const run = () => { while (frames.length) frames.shift()(); };
  assert.ok(key("h", inMenu).stopped); key("i", { closest: () => null }); run();
  assert.deepEqual([escapes, said], [["Escape"], ["hi"]], "typed into the menu: shut, and every key in the box in order");
  open = true; focused = null; said.length = 0;
  on.pointerdown({ target: backdrop, clientX: 5, clientY: 5 });
  assert.ok(key(" ", { closest: () => null }).stopped, "the space typed on the button the menu handed the focus back to never presses it");
  key("n", { closest: () => null }); open = false; run();
  assert.deepEqual(said, [" n"]);
});
