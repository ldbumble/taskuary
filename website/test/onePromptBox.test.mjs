import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// ONE PROMPT BOX, ONE ATTACHMENT LOOK (the owner, 2026-11-05: "Don't have separate code. It's the same prompt box, just with the Came from
// attached and your prompt in one"; "don't let it grow too big if there are many attachments")
test("an item's Agent tab types into the task chat's own box, at the pane's foot, with no No agent yet card", () => {
  const items = read("ItemSections.jsx"), cards = read("assistantCards.jsx");
  assert.match(items, /import \{ PromptBox \} from "\.\/AgentSummary\.jsx";/);
  assert.match(items, /<Box sx=\{\{ position: "sticky", bottom: 0, bgcolor: SHADE/);
  assert.doesNotMatch(items, /InputBase/);
  assert.doesNotMatch(cards, /data-tq-(report|dash|idea|fyi)-agent="">\s*<div className="tq-thr-h"><b>No agent yet/);
  assert.match(read("AgentSummary.jsx"), /\{box && <PromptBox text=\{text\} setText=\{setText\}/, "a task's first box is the same one");
});
test("the item, the paperclip's files and a dropped picture are one chip each, in one line inside the box", () => {
  const imgs = read("promptImages.jsx");
  assert.match(imgs, /export function AttachChip\(/);
  assert.match(imgs, /display: "flex", flexWrap: "nowrap", alignItems: "center", gap: 0\.5, minWidth: 0, maxWidth: "100%", overflowX: "auto"/);
  assert.match(read("AgentSummary.jsx"), /<AttachRow sx=\{\{ pt: 0\.5 \}\}>\{chips\}\{fileChips\(pics, cannot\)\}\{fileState\(pics\)\}<\/AttachRow>/);
  assert.match(read("ItemSections.jsx"), /<AttachChip key=\{i\.key\} data-tq-item-chip=\{i\.key\} name=\{i\.title\}/);
  assert.match(read("GeneralWorkspace.jsx"), /<AttachRow className="tq-aui-attachments"/);
});
