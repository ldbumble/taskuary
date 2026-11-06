import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// COPY IN THE CORNER (the owner, 2026-11-05: "should have added copy button on corner for text stuff to copy")
test("an answer and a code block copy at their corner", () => {
  assert.match(read("md.jsx"), /pre: Pre,/);
  assert.match(read("md.jsx"), /<CopyCorner text=\{\(\) => box\.current\?\.innerText \|\| ""\} \/>/);
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /\{chat && !!said && !running && <CopyCorner text=\{said\} label="Copy this answer" \/>\}/);
  const css = readFileSync(new URL("../src/copyCorner.css", import.meta.url), "utf8");
  assert.match(css, /\.tq-copy-host:hover > \.tq-copy/, "unseen until the block is hovered");
});
