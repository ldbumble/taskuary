import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


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


// SEND TO AGENT OPENS THE AGENT'S OWN CANVAS (the owner, 2026-11-17: "why do i see the dashboard? it should be blank agent chat canvas" ... "keep the
// blue pill in the prompt box and tell the user to write prompt on the report in the prompt box"): the press adds a blank Agent section and opens it,
// the item a chip on its box, one line saying to write there; the item's own reading is not drawn on that canvas
test("Send to agent on a report, a dashboard or an FYI opens a blank Agent canvas with the item a chip on its box", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("../src/ItemSections.jsx", import.meta.url), "utf8");
  assert.match(src, /const sections = hand && !all\.some\(\(s\) => s\.key === "agent" && s\.body\)/);
  assert.match(src, /useEffect\(\(\) => \{ if \(hand\) setOpen\(boxAt\);/);
  assert.doesNotMatch(src, /data-tq-item-agent-hint/, "the canvas is blank - the box asks");
  assert.match(src, /What should the agent do with this \$\{noun\}\?/);
  assert.match(src, /const ls = hand \? \[\] : itemLines/);
  assert.match(src, /data-tq-item-chip=\{i\.key\}/, "the item stays a chip on the box");
});

// ...AND WHAT HE TYPES THERE "SAYS REPORT NAME THEN YOUR PROMPT" (the owner, 2026-11-17): his line's bubble carries the report as a pill, the list's
// `came`; the report itself is the task's Came from - the old "The report" strip over the chat is gone
test("his first line on a report he sent on draws the report as a pill, then his words", async () => {
  const fs = await import("node:fs");
  const gw = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8"), tp = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(gw, /<div data-tq-line-came=""[^]*?\{!!x\.came && <AttachChip name=\{x\.came\}/);          // ...beside his files' pills (2026-11-17)
  assert.doesNotMatch(tp, /setReportOpen|>The report</);
});

test("a paste that carries words is those words; its files are taken only when no words come with them", async () => {
  const { pastedFiles } = await import("../src/promptPaste.js");
  const png = { name: "image.png", type: "image/png" }, pdf = { name: "notes.pdf", type: "application/pdf" };
  const clip = (text, files) => ({ getData: (k) => (k === "text/plain" ? text : ""), files });
  assert.deepEqual(pastedFiles(clip("Q3 totals\t1,200", [png])), [], "a row from a sheet, with its picture, is the row");
  assert.deepEqual(pastedFiles(clip("", [png])), [png], "a screenshot alone is attached");
  assert.deepEqual(pastedFiles(clip("  \n", [png])), [png], "white space is not words");
  assert.deepEqual(pastedFiles(clip("", [png, pdf]), (f) => f.type.startsWith("image/")), [png], "a box that takes pictures only");
  assert.deepEqual(pastedFiles(null), []);
  assert.match(read("promptImages.jsx"), /const files = pastedFiles\(e\.clipboardData, takes\);/, "the one paste road reads it");
});

// ...HIS WORDS START IT, AND SEND IS LIT ONLY WHEN THEY CAN (the stress round, 2026-11-18): a picture put on the item's box with nothing typed
// lit Send - the box counts a file as something to send - and the press did nothing, since the item's box goes on words alone
test("the item's Send is lit only once words are in it, so a file alone never lights a press that does nothing", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("../src/ItemSections.jsx", import.meta.url), "utf8");
  const send = src.match(/const send = async \(\) => \{\n\s*const q = text\.trim\(\);\n\s*if \(([^)]*)\) return;/);
  assert.ok(send, "send reads its words first");
  assert.match(send[1], /^!q\b/, "no words, no send");
  assert.match(src, /<PromptBox [^>]*sendOff=\{!text\.trim\(\)\}/, "...and the button says so: unlit while no words are in it");
});

// ...AND WHAT HE TYPED BEFORE HE PRESSED IT STAYS HIS (the stress round, 2026-11-18): Send to agent moves the item's box from the section it is
// about to the blank Agent section, and a box holding its own words was a new box there - empty. The item holds the box's words and files
test("the item's box keeps his words and files when Send to agent moves it to the Agent section", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("../src/ItemSections.jsx", import.meta.url), "utf8");
  const ask = src.slice(src.indexOf("export function ItemAsk"), src.indexOf("export default function ItemSections"));
  assert.doesNotMatch(ask, /\[text, setText\] = useState|usePromptImages\(/, "the box keeps no words or files of its own");
  assert.match(ask, /const \{ text, setText, pics \} = draft;/);
  assert.match(src, /const \[text, setText\] = useState\(""\), pics = usePromptImages\(\{ files: true \}\), draft = \{ text, setText, pics \};/);
  assert.match(src, /useEffect\(\(\) => \{ setText\(""\); pics\.clear\(\); \}, \[itemKey\]\);/, "...a new item starts them empty");
});
