// THE BUGS THAT CAME BACK (the owner, 2026-11-06: "do you fix the bugs I give you?"): a typed line drawn twice, the files staying in the box after
// Send, "nothing to decide" on an FYI handful, and the chips on a row of their own over a box
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";



const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const you = (text) => ({ role: "user", content: [{ type: "text", text }] });
const agent = (text) => ({ role: "assistant", content: [{ type: "text", text }] });
const LINE = "the second site - I see you have it at 4 million?";





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
  // ...and a coding CLI's files reach it named after the words by their paths - the server's one road names them (waitroom._lines)
  assert.match(read("GeneralWorkspace.jsx"), /attachments: files\.map\(\(a\) => a\.path\), line_id: id/);
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
