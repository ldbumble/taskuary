import { taskSource } from "./taskSource.mjs";
// A strip's buttons never lose a button and never cover the title. At 390px the agent bar sat ON
// "Agent work" and its last button ran off the card (2026-09-18); below sm the bar takes the next
// line of a wrapping heading instead.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = taskSource();

test("a stage heading wraps below sm and its bar takes the whole next line", () => {
  const head = src.slice(src.indexOf("const WorkflowHeading = ("), src.indexOf("{chip}", src.indexOf("const WorkflowHeading = (")));
  assert.match(head, /flexWrap: \{ xs: "wrap", sm: "nowrap" \}/);
  assert.match(head, /flexBasis: \{ xs: "100%", sm: "auto" \}, order: \{ xs: 9, sm: 0 \}/);
});
// ...and the folded task strip has no bar to wrap any more: the Tasks tab's bar sits under the view (section 1's redesign, 2026-10-16)
// ...and From is a column now, three lines on a phone until a tap opens it (the redesign, owner-approved 2026-10-21)
// ...AND THE STACKED PAGE IS THE VIEW'S HEIGHT, its box at the foot on every kind (F4, the owner 2026-11-08): the chat takes what From
// leaves, never under 280px, and a to-do's From is the whole page with its box sticky at its foot - never clamped to three lines over it
test("a stacked page fills the view: the chat takes the rest, a to-do's box sits at its foot", () => {
  const cols = src.slice(src.indexOf("const COLUMNS = {"), src.indexOf("// THE SHADE AND THE FOCUS"));
  assert.match(cols, /display: "flex", flexDirection: "column", rowGap: 2, flex: "1 1 0", minHeight: 0/);
  assert.match(cols, /"& > \[data-tq-from\]:has\(> \[data-tq-solo-box\]\)": \{ flex: "1 1 0" \}/);
  assert.match(cols, /"& > \[data-tq-work\]": \{ flex: "1 0 auto", minHeight: 0 \}/);
  assert.match(cols, /"& > \[data-tq-work\]:empty": \{ display: "none" \}/, "a to-do's empty work box takes none of its From's room");
  assert.match(cols, /"& \[data-tq-agent-room=chat\]": \{ minHeight: 280 \}/);
  assert.match(src, /PHONE_FROM\(fromOpen \|\| solo\)/, "a to-do's From is never clamped over its own box");
});
test("From shows three lines on a phone and opens on a tap; the bar wraps at the view's foot", () => {
  assert.match(src, /const PHONE_FROM = \(open\) => \(open \? \{\} : \{ \[`@media \$\{PHONE_MQ\}`\]: \{ maxHeight: 132, overflow: "hidden"/);
  assert.match(src, /onClickCapture=\{stacked && !solo \? phoneFromTap : undefined\}/);
  assert.match(src, /if \(fromOpen \|\| !window\.matchMedia\?\.\(PHONE_MQ\)\.matches\) return;\n\s+e\.preventDefault\(\); e\.stopPropagation\(\); setFromOpen\(true\);/);
  // ...one line, never wrapped (the owner, 2026-10-23): what does not fit folds into its ▾ (foldBar.js)
  assert.match(src, /\{!inRow && !sessionView && \(\s+<Box data-tq-task-bar="" ref=\{bar\.ref\}[^>]*flexWrap: "nowrap"/,"the bar it lost stays one line at the view's foot");
});
