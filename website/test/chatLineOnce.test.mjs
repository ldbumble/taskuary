// THE BUGS THAT CAME BACK (the owner, 2026-11-06: "do you fix the bugs I give you?"): a typed line drawn twice, the files staying in the box after
// Send, "nothing to decide" on an FYI handful, and the chips on a row of their own over a box
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const you = (text) => ({ role: "user", content: [{ type: "text", text }] });


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
