// WHAT A CHAT ANSWER RENDERS AS: md.jsx draws markdown only when looksMd says the text is markdown. An answer that
// was only a fenced ascii diagram read as prose - every line a paragraph, the boxes in pieces (2026-10-06).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { looksMd, refParts } from "../src/mdText.js";

test("a fence, inline code or a link is markdown; plain prose and an email's asterisk are not", () => {
  for (const s of ["```\n┌──┐\n│ a │\n└──┘\n```", "Run `Get-ChildItem -Recurse` there", "Start at [the portal](https://entra.example/users)",
                   "## Heading", "| a | b |", "**bold**", "- item"]) assert.ok(looksMd(s), s);
  for (const s of ["Morning, Dana. Two are waiting on you.", "Price is 5 * 3 today", "", null]) assert.ok(!looksMd(s), String(s));
});

test("a task's ref is one word in a table cell", () => {
  assert.deepEqual(refParts("TQ-0001 and TQ-12"), ["", "TQ-0001", " and ", "TQ-12", ""]);
  assert.deepEqual(refParts("no ref here"), ["no ref here"]);
  const md = fs.readFileSync(new URL("../src/md.jsx", import.meta.url), "utf8");
  assert.match(md, /td: Td/); assert.match(md, /"& \.ref": \{ whiteSpace: "nowrap" \}/);
});

test("a long URL or path breaks inside the column instead of running past it", () => {
  const md = fs.readFileSync(new URL("../src/md.jsx", import.meta.url), "utf8");
  const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  assert.match(md, /lineHeight: 1\.55, overflowWrap: "break-word"/);
  assert.match(css, /\.tq-msg \.body \{[^}]*overflow-wrap: break-word/);
});
