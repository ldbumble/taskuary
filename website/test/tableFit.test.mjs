// A TABLE NEVER WRAPS WHILE THERE IS ROOM (the owner, 2026-11-24, a trending-repositories report in the 640px frame: "elementalsoul/s" broken
// mid-word, "What it is" in tall rows, half the screen empty - "I hate wrapped text ... make font smaller or make the report a little bigger").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fitTable, shortColumn, SMALLER } from "../src/tableFit.js";

test("a table takes the frame's room first, then the chat's, then a smaller font, and only then wraps - and scrolls last", () => {
  const at = (need, least = 400) => fitTable({ need, least, room: 620, chat: 1000, font: 13.5 });
  assert.deepEqual(at(600), { width: 0, font: 13.5, wrap: false, scroll: false }, "fits as it is");
  assert.deepEqual(at(940), { width: 940, font: 13.5, wrap: false, scroll: false }, "the frame widens to it before anything wraps");
  const small = at(1100);
  assert.equal(small.font, SMALLER); assert.equal(small.wrap, false); assert.ok(small.width <= 1000, "one notch down and it fits whole");
  const wraps = at(1800, 700);
  assert.deepEqual([wraps.width, wraps.font, wraps.wrap, wraps.scroll], [1000, SMALLER, true, false], "then it wraps at its words, at the chat's width");
  assert.equal(at(3000, 1400).scroll, true, "too wide even wrapped: it scrolls inside its frame");
  assert.equal(fitTable({ need: 1100, room: 620, chat: 1000, font: 12 }).font, 12, "never below the one notch");
});

test("a numeric or short column never wraps; a column of sentences does", () => {
  assert.ok(shortColumn(["1", "2", "15"])); assert.ok(shortColumn(["$1,204", "12%", "3.5k"]));
  assert.ok(shortColumn(["elementalsoul/sigil", "northwind/ledger"]), "a repository slug is one word: never broken");
  assert.ok(shortColumn(["Python", "TypeScript", ""]));
  assert.ok(!shortColumn(["A terminal UI for watching your agents work", "Rust"]), "words wrap at their spaces");
});

test("every table fits by the one rule: markdown and a view's table alike, the frame reading the one width", () => {
  const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  assert.match(src("md.jsx"), /table: FitTable/); assert.match(src("ViewSpec.jsx"), /useTableFit\(ref, \[names, objs\]\)/);
  assert.doesNotMatch(src("ViewSpec.jsx"), /--tq-view-need/, "the view's own measure is gone");
  assert.match(src("appTheme.css"), /max-width: min\(100%, max\(var\(--tq-turn-item\), var\(--tq-fit-w, 0px\)\)\)/);
  assert.match(src("appTheme.css"), /\[data-tq-fit\]\[data-tq-fit\] th, \[data-tq-fit\]\[data-tq-fit\] td, \[data-tq-fit\]\[data-tq-fit\] a \{ overflow-wrap: normal; word-break: normal; \}/);
});
