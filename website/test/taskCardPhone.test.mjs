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
test("From shows three lines on a phone and opens on a tap; the bar wraps at the view's foot", () => {
  assert.match(src, /const PHONE_FROM = \(open\) => \(open \? \{\} : \{ \[`@media \$\{PHONE_MQ\}`\]: \{ maxHeight: 132, overflow: "hidden"/);
  assert.match(src, /onClickCapture=\{sessionView \? undefined : phoneFromTap\}/);
  assert.match(src, /if \(fromOpen \|\| !window\.matchMedia\?\.\(PHONE_MQ\)\.matches\) return;\n\s+e\.preventDefault\(\); e\.stopPropagation\(\); setFromOpen\(true\);/);
  assert.match(src, /\{!inRow && !sessionView && \(\s+<Box data-tq-task-bar=""[^>]*flexWrap: "wrap"/, "the bar it lost wraps at the view's foot");
});
