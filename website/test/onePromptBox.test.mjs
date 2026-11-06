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
  assert.match(read("AgentSummary.jsx"), /<PromptBox text=\{text\} setText=\{setText\}/, "a to-do's first box is the same one");
});
test("the item, the paperclip's files and a dropped picture are one chip each, in one line inside the box", () => {
  const imgs = read("promptImages.jsx");
  assert.match(imgs, /export function AttachChip\(/);
  assert.match(imgs, /display: "flex", flexWrap: "nowrap", alignItems: "center", gap: 0\.5, minWidth: 0, maxWidth: "100%", overflow: "hidden"/);
  assert.doesNotMatch(imgs, /overflowX: "auto"/, "the row never scrolls sideways: a few chips, then +N more (the owner, 2026-11-06)");
  // ...on the box's one thin line, left of the words (the owner, 2026-11-06: "keep the prompt box thin")
  assert.match(read("AgentSummary.jsx"), /\{chips && <AttachRow className="tq-aui-attachments" sx=\{INLINE_CHIPS\}>\{chips\}<\/AttachRow>\}/);
  assert.match(read("AgentSummary.jsx"), /chips=\{any \? <>\{chips\}\{fileChips\(pics, cannot\)\}\{fileState\(pics\)\}<\/> : null\}/);
  assert.match(imgs, /export const INLINE_CHIPS = \{ flex: "0 1 auto", maxWidth: "34%"/);
  assert.match(read("ItemSections.jsx"), /<AttachChip key=\{i\.key\} data-tq-item-chip=\{i\.key\} name=\{i\.title\}/);
  assert.match(read("GeneralWorkspace.jsx"), /<OneBox root=\{ComposerPrimitive\.Root\}/);
});

// ...AND IT LOOKS THE ONE BOX: the chat composer's own classes, paperclip left and the filled Send, so a task's first words (which start its
// agent) leave the box as it was (the scenario run, 2026-11-06)
test("the box before an agent wears the chat composer's classes", () => {
  const box = read("AgentSummary.jsx");
  assert.match(box, /return <Root className="tq-aui-composer" data-tq-one-box="" \{\.\.\.rootProps\}>/);
  assert.match(box, /<OneBox rootProps=\{\{ "data-tq-prompt-box": ""/);
  assert.match(box, /<Box component="textarea" className="tq-aui-input"/);
  assert.match(box, /<button type="submit" className="tq-aui-send"/);
  const one = box.slice(box.indexOf("export function OneBox"));
  assert.ok(one.indexOf('className="tq-aui-attach"') < one.indexOf("{input}"), "the paperclip comes first, as in the chat");
  assert.match(read("ItemSections.jsx"), /import "\.\/generalWorkspace\.css";/);
});

// MANY ATTACHMENTS: a few chips, then "+N more" that opens the whole list - one chip everywhere (the owner, 2026-11-06)
test("an attachment row shows a few, then +N more, and every file chip is the one AttachChip", async () => {
  const { attachSplit, ATTACH_FEW } = await import("../src/promptImages.jsx").catch(() => ({}));
  const src = read("promptImages.jsx");
  assert.match(src, /export const attachSplit = \(n, few = ATTACH_FEW\) => \(n > few \+ 1 \? few : n\)/);
  assert.match(src, /name=\{`\+\$\{more\.length\} more`\}/);
  assert.match(src, /<Popover open=\{!!at\}/);
  if (attachSplit) { assert.equal(attachSplit(2), 2); assert.equal(attachSplit(ATTACH_FEW + 1), ATTACH_FEW + 1); assert.equal(attachSplit(9), ATTACH_FEW); }
  for (const f of ["ReplyFiles.jsx", "Attachments.jsx"]) {
    assert.match(read(f), /<AttachRow/, f); assert.match(read(f), /<AttachChip /, f);
  }
  assert.doesNotMatch(read("ReplyFiles.jsx"), /<Chip /);
});
