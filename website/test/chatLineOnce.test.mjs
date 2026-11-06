// THE BUGS THAT CAME BACK (the owner, 2026-11-06: "do you fix the bugs I give you?"): a typed line drawn twice, the files staying in the box after
// Send, "nothing to decide" on an FYI handful, and the chips on a row of their own over a box
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { notShown, stillHeld } from "../src/heldLines.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const you = (text) => ({ role: "user", content: [{ type: "text", text }] });
const agent = (text) => ({ role: "assistant", content: [{ type: "text", text }] });
const LINE = "the second site - I see you have it at 4 million?";

// 1. ONE LINE, ONCE. Typed while the agent had a question open, the line took the answer's road: held at the foot as the owner's AND appended to
// the chat's own thread, which drew it as the turn's "You" bubble - so it stood twice, the second under the agent's first step, for the whole turn
test("a held line the chat already draws is not drawn again under the agent's step", () => {
  const held = [{ id: "h", text: LINE, after: 2, drawn: 2 }];
  const server = [you("first"), agent("Which site?"), you("second"), agent("Want the totals?")];
  const thread = [...server, you(LINE), agent("")];          // the answer road: the runtime appended it and its turn is streaming
  assert.deepEqual(stillHeld(held, server), held, "the server has not filed it yet");
  assert.deepEqual(notShown(stillHeld(held, server), thread), [], "...but the thread on screen draws it: once is enough");
  // ...and a line the thread does not draw yet (typed mid-turn, waiting for the turn ahead) stays drawn, held
  assert.deepEqual(notShown(held, server), held);
  // ...nor does a line the owner said before the hold take it away
  assert.deepEqual(notShown([{ id: "y", text: "yes", after: 1, drawn: 1 }], [you("yes")]).length, 1);
});

test("Taskuary's own brief is not the owner's line: a held line waits for theirs", () => {
  const brief = { role: "user", brief: true, content: [{ type: "text", text: "New mail on this task from Erin Blake" }] };
  const held = [{ id: "h", text: LINE, after: 1, drawn: 1 }];
  assert.deepEqual(stillHeld(held, [you("first"), brief]), held, "a brief filed ahead of it is no copy of it");
  assert.deepEqual(stillHeld(held, [you("first"), brief, you(LINE)]), []);
  const meta = { role: "user", metadata: { custom: { brief: true } }, content: [{ type: "text", text: "Taskuary's instructions" }] };
  assert.deepEqual(notShown(held, [you("first"), meta]), held, "the thread marks a brief on its metadata");
});

test("the chat draws its held lines through notShown, and a failed answer takes its held copy back", () => {
  const gw = read("GeneralWorkspace.jsx");
  assert.match(gw, /notShown\(held, mineDrawn\)\.map\(\(l\) =>/);
  assert.doesNotMatch(gw, /\{held\.map\(\(l\) => <div key=\{l\.id\}/);
  assert.match(gw, /\.catch\(\(x\) => \{ setHeld\(\(h\) => h\.filter\(\(l\) => l\.id !== id\)\); c\.setText\(w\)/);
  // ...and the coding chat matches its held lines the same way: by the words however spelled, after the hold
  assert.match(read("CodingChat.jsx"), /stillHeld\(h, rows\.filter\(\(r\) => r\.kind === "you"\)/);
});

// 2. THE FILES LEAVE THE BOX WITH THE SEND. They were cleared only when the agent's whole turn was done - minutes of chips over a box that had
// already sent them - and a line typed while it worked never sent them at all
test("the chat box lets go of its files once the send is accepted, and keeps them when it fails", () => {
  const gw = read("GeneralWorkspace.jsx");
  assert.match(gw, /const sentFiles = attachmentsRef\.current\.map\(\(a\) => a\.path\)/);
  assert.match(gw, /if \(event\.type !== "error"\) took\(\);/, "the first word back from the server is the send accepted");
  assert.doesNotMatch(gw, /onClearAttachments\(\); onSent\(event\.payload\)/, "never every file at the turn's end: one added meanwhile stays");
  // ...a line held while it works carries the box's files, and puts them back if it did not go
  assert.match(gw, /\{ text: w, attachments: files\.map\(\(a\) => a\.path\) \}/);
  assert.match(gw, /onAttachBack\(files\)/);
  assert.match(gw, /const clearAttachments = useCallback\(\(paths\) =>/);
});

// 3. AN FYI HANDFUL IS "6 messages": the row and the section already say FYI
test("an FYI handful's chip, title and kicker say how many, not 'nothing to decide'", () => {
  const cards = read("assistantCards.jsx");
  assert.doesNotMatch(cards, /`\$\{plural\(n, "message"\)\} - nothing to decide`/);
  assert.doesNotMatch(cards, /`\$\{plural\(n, "message"\)\} · nothing to decide`/);
  assert.doesNotMatch(cards, /kicker=\{`\$\{items\.length\} fyi · nothing to decide`\}/);
  assert.match(cards, /title=\{batch \? plural\(n, "message"\) : card\.title\}/);
});

// 4. EVERY BOX: the Came-from chip and the files on the box's own line, left of the words - never a row of their own over it
test("every prompt box carries its chips inside, on the words' line", () => {
  assert.match(read("AgentSummary.jsx"), /<AttachImage pics=\{pics\} size=\{18\} sx=\{\{ width: 30, height: 30 \}\} \/>\s*\{!!\(chips \|\| pics\.imgs\.length \|\| pics\.busy \|\| pics\.err\) && <AttachRow sx=\{INLINE_CHIPS\}>/);
  assert.match(read("GeneralWorkspace.jsx"), /<ComposerPrimitive\.Root className="tq-aui-composer"[\s\S]{0,900}<AttachRow className="tq-aui-attachments" sx=\{INLINE_CHIPS\}>/);
  assert.match(read("CodingChat.jsx"), /<form className="tq-aui-composer" onSubmit=\{send\}>\s*\{came && <AttachRow className="tq-aui-attachments" sx=\{INLINE_CHIPS\}>/);
  const dock = read("AssistantView.jsx");
  assert.doesNotMatch(dock, /<ImageTray pics=\{pics\} cannot=\{dockCannot\} sx=\{\{ width: "100%", mb: 0\.75 \}\} \/>/, "the dock's files are not a row over its box");
  assert.match(dock, /<AttachImage pics=\{pics\} sx=\{\{ color: DIM \}\} \/>\s*<ImageTray pics=\{pics\} cannot=\{dockCannot\} sx=\{DOCK_CHIPS\} \/>/);
});
