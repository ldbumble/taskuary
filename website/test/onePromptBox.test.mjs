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
  assert.match(src, /const ls = hand \|\| agent \? \[\] : itemLines/);
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

// THE ITEM'S BOX IS A TASK CHAT'S ROAD (walk 13: a question typed on a report went to the home Assistant, the box emptied, and the answer was kept
// only in the page - nothing ever stood on the report): his line starts the agent on the item, the one start Send to agent takes, so his line and
// its answer are that task's chat, stored and drawn there - no second door to the Assistant, no answer held in the page
test("a line in a report's own box starts the agent on it by the one start, never the Assistant's door", () => {
  const src = read("ItemSections.jsx"), ask = src.slice(src.indexOf("export function ItemAsk"), src.indexOf("export default function ItemSections"));
  assert.doesNotMatch(src, /\/api\/concierge\/say/, "no second road to the home Assistant");
  assert.doesNotMatch(ask, /useState\(\[\]\)/, "no answer kept in page state");
  assert.match(ask, /else if \(START\) await START\(\{ key: ask\.key, title \}, \{ verb: AGENT, text: q, files: pics\.paths \}\);/);
  assert.match(read("AssistantView.jsx"), /startsItems\(startOnItem\);/, "the start is the one Send to agent takes");
});

// ONE WAY IN ON WHAT TASKUARY MADE (the owner, 2026-11-24, a dashboard's row: "don't need both send to agent and message on bottom no?"): a report,
// a dashboard or an Advisor idea opens on the Agent tab with its own box, and his first line there starts the agent on it - so its row has no Send
// to agent; what came in from outside (an FYI, a mail, a meeting) keeps the one it has
test("a made item's row has no Send to agent and its box starts the agent on his first line; an FYI keeps its Send to agent", async () => {
  const { itemVerbs, madeHere } = await import("../src/funnelPile.js");
  const chips = ["regular_agent", "coding_agent", "report_off", "not_ours", "mine"].map((verb) => ({ verb, label: verb }));
  for (const k of ["report", "dashboard", "idea"]) assert.deepEqual(itemVerbs(k, chips).map((c) => c.verb), ["report_off", "not_ours", "mine"], k);
  for (const k of ["message", "meeting", "fyis"]) assert.deepEqual(itemVerbs(k, chips), chips, k);
  assert.ok(madeHere({ kind: "report", key: "report:1" }) && !madeHere({ kind: "fyi", key: "msg:1" }));
  assert.match(read("AssistantView.jsx"), /const verbs = inCard \? itemVerbs\(kind, chips\.filter\(\(c\) => c\.verb\)\) : \[\];/, "the row's words pass through it");
  const ask = read("ItemSections.jsx");
  assert.match(ask, /else if \(START\) await START\(\{ key: ask\.key, title \}, \{ verb: AGENT, text: q, files: pics\.paths \}\);/, "the box is the way in");
});

// ONE MOVE ON AN ARRIVAL IN THE LIST (the owner, 2026-11-25: under a marketing mail the row stood Make it a task, Send to coding agent, Send to
// agent, Not for me and Talk about it): Send to agent alone, and its press puts the mail on the item's box as a chip - his words start the work
test("an arrival's one move is Send to agent, and its press puts it on the box as a chip, the pressed one first", async () => {
  const { arrivalHand, arrivalMoves, handToItem, takeHands } = await import("../src/itemHand.js");
  const { label } = await import("../src/buttons.js");
  const promo = { key: "msg:7", mid: 7, who: "Trainly <news@trainly.example>", title: "Spring sale" };
  const other = { key: "msg:8", mid: 8, who: "Spendly", title: "Your receipt" }, filed = { key: "msg:9", mid: 9, tid: 4, who: "Erin Blake", title: "W-9" };
  assert.deepEqual(arrivalMoves(promo), ["regular_agent"]);
  assert.equal(label(arrivalMoves(promo)[0]), "Send to agent");
  assert.deepEqual(arrivalMoves(filed), [], "a line on a task already is the task's");
  assert.deepEqual(arrivalMoves(other, { tid: 5 }), [], "nor one that went to a task here");
  assert.equal(handToItem("fyis:1", arrivalHand(promo, [promo], {}, null)), false, "no box drawn to take it: the caller opens the agent box");
  let got = null; const off = takeHands("fyis:1", (h) => { got = h; });
  const started = [];
  assert.equal(handToItem("fyis:1", arrivalHand(other, [promo, other, filed], {}, async (lead, o) => started.push([lead.key, o]))), true);
  assert.equal(got.verb, "regular_agent");
  assert.deepEqual(got.items, [{ key: "msg:8", title: "Spendly: Your receipt" }, { key: "msg:7", title: "Trainly: Spring sale" }]);
  await got.start({ verb: got.verb, text: "Unsubscribe me from these", files: [], items: got.items });
  assert.equal(started[0][0], "msg:8");
  assert.match(started[0][1].text, /^Unsubscribe me from these\n\nTHE OTHER MESSAGES OF THIS LIST IT IS ABOUT \(read each with read_message\)\nm7 - Trainly: Spring sale$/);
  off(); assert.equal(handToItem("fyis:1", arrivalHand(promo, [promo], {}, null)), false);
});
