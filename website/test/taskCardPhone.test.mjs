// A strip's buttons never lose a button and never cover the title. At 390px the agent bar sat ON
// "Agent work" and its last button ran off the card (2026-09-18); below sm the bar takes the next
// line of a wrapping heading instead.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = fs.readFileSync(path.join(process.cwd(), "src", "TasksView.jsx"), "utf8");

test("a stage heading wraps below sm and its bar takes the whole next line", () => {
  const head = src.slice(src.indexOf("const WorkflowHeading = ("), src.indexOf("{chip}", src.indexOf("const WorkflowHeading = (")));
  assert.match(head, /flexWrap: \{ xs: "wrap", sm: "nowrap" \}/);
  assert.match(head, /flexBasis: \{ xs: "100%", sm: "auto" \}, order: \{ xs: 9, sm: 0 \}/);
});
test("the folded task strip follows the same rule", () => {
  const at = src.indexOf('onClick={() => setOpenStage("task")}');
  const strip = src.slice(at, src.indexOf("<ExpandMoreIcon", at));
  assert.match(strip, /flexWrap: \{ xs: "wrap", sm: "nowrap" \}/);
  assert.match(strip, /flexBasis: \{ xs: "100%", sm: "auto" \}, order: \{ xs: 9, sm: 0 \}/);
});
