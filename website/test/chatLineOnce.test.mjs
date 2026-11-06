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
  // ...and a coding source's lines are held the same way, on the same road: its typed lines are the thread's own (chatStream.rowMessages)
  assert.match(gw, /\(road \? road\(w, files\.map\(\(a\) => a\.path\)\) : api\.post\(`\/api\/tasks\/\$\{task\.TaskId\}\/assistant\/messages`/);
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
  const one = read("AgentSummary.jsx").slice(read("AgentSummary.jsx").indexOf("export function OneBox"));
  const at = (k) => one.indexOf(k);
  assert.ok(at('className="tq-aui-attach"') < at("{chips && <AttachRow") && at("{chips && <AttachRow") < at("{input}") && at("{input}") < at("<MicButton")
    && at("<MicButton") < at("{extra}") && at("{extra}") < at("{send}"), "paperclip, chips, words, mic, the box's own buttons, Send");
  assert.match(read("GeneralWorkspace.jsx"), /<OneBox root=\{ComposerPrimitive\.Root\}/);
  const dock = read("AssistantView.jsx");
  assert.doesNotMatch(dock, /<ImageTray pics=\{pics\} cannot=\{dockCannot\} sx=\{\{ width: "100%", mb: 0\.75 \}\} \/>/, "the dock's files are not a row over its box");
  assert.match(dock, /<AttachImage pics=\{pics\} sx=\{\{ color: DIM \}\} \/>\s*<ImageTray pics=\{pics\} cannot=\{dockCannot\} sx=\{DOCK_CHIPS\} \/>/);
});

// ONE BOX, ONE COMPONENT (the owner, 2026-11-06: "you moved the attached thing to the same line but you removed mic and attach icons???"): the
// coding chat's box was a form of its own, a bare textarea. Every box with the composer's class is drawn by AgentSummary.OneBox, and OneBox
// draws the paperclip and the mic whatever it is handed - so neither can go missing from one box again
test("every tq-aui-composer is the one OneBox, and it always has the paperclip and the mic", async () => {
  const { readdirSync } = await import("node:fs");
  const src = new URL("../src/", import.meta.url);
  const drawn = readdirSync(src).filter((f) => /\.jsx?$/.test(f)).flatMap((f) => (readFileSync(new URL(f, src), "utf8").match(/className="tq-aui-composer"/g) || []).map(() => f));
  assert.deepEqual(drawn, ["AgentSummary.jsx"], "only OneBox wears the composer's class");
  const box = read("AgentSummary.jsx"), one = box.slice(box.indexOf("export function OneBox"), box.indexOf("export const micInto"));
  assert.match(one, /return <Root className="tq-aui-composer"/);
  assert.match(one, /<IconButton size="small" className="tq-aui-attach"[^>]*onClick=\{\(\) => pick\.current\?\.click\(\)\}/);
  assert.match(one, /<MicButton size=\{18\} [^>]*onText=\{onMic\} \/>/);
  assert.doesNotMatch(one, /\{(onFiles|onMic) &&|\{!?\w+ \? <IconButton|\{\w+ && <MicButton/, "neither is drawn on a condition");
  // ...used by every box: the one chat (general and coding alike), a task's first box and an item's (PromptBox)
  assert.match(read("GeneralWorkspace.jsx"), /<OneBox root=\{ComposerPrimitive\.Root\}/);
  assert.match(box, /<PromptBox /);
  assert.match(read("ItemSections.jsx"), /<PromptBox /);
  // ...and a coding CLI's files reach it named after the words by their paths
  assert.match(read("GeneralWorkspace.jsx"), /const said = withImages\(w, files\);/);
});

// ...AND EVERY BOX ON A TASK PAGE (the owner, 2026-11-06: "stop building each unique prompt box. it should be shared"): Continue's note and the
// Send to agent / Run another agent form are the one PromptBox too, and no box that talks to an agent draws a field of its own
test("every box on a task page that talks to an agent is the one PromptBox / OneBox - no field of its own", () => {
  const own = /<TextField\b|<textarea\b|component="textarea"|<InputBase\b/;
  for (const f of ["ContinueBox.jsx", "ItemSections.jsx"]) {
    assert.doesNotMatch(read(f), own, `${f} draws a field of its own`);
    assert.match(read(f), /<PromptBox /, f);
  }
  const run = read("RunForm.jsx"), form = run.slice(run.indexOf("export function RunForm"), run.indexOf("export function AgentAsk"));
  assert.doesNotMatch(form, own); assert.match(form, /<PromptBox text=\{value\}/);
  const gw = read("GeneralWorkspace.jsx"), thread = gw.slice(gw.indexOf("function AssistantThread("), gw.indexOf("export function GeneralWorkspace("));
  assert.doesNotMatch(thread, own); assert.match(thread, /<OneBox /);
  const box = read("AgentSummary.jsx"), mine = box.slice(box.indexOf("export function NoAgentChat"));
  assert.equal((mine.match(own) || []).length, 1, "the one field is PromptBox's own");
  assert.match(mine, /<PromptBox /);
});
