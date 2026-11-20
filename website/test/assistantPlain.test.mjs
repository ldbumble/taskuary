// The canvas for a person who does not code (the 2026-10-17 audit): no AI says so once with the way to fix it, a refused Advisor
// press reads the advice again, a rail click shows its card, one headline count, and no words for screens that are gone.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");

test("no AI connected: no strip says it, and nothing is added to the row or lit for it (U3; the owner, 2026-11-15)", () => {
  assert.match(read("tableState.js"), /data\.verb \|\| data\.none \|\| data\.state/, "a none answer is kept, not dropped as nothing");
  assert.doesNotMatch(view, /noai:connect|aiOff:/);
  assert.match(read("ActionRow.jsx"), /const pick = advised\?\.none \? \{ verb: "next" \} : advised;/);
  assert.doesNotMatch(read("advice.js"), /no_ai|needs_ai/);
});

test("a press refused as changed reads the advice again, and the row lights the new pick (B6)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// Get me ready for this meeting"));
  assert.match(press, /status !== 409\) throw e/);
  assert.match(press, /await readAdvice\(key\)/);
  // ...said by no strip since 2026-10-26: the row relights
  assert.doesNotMatch(view, /This changed - reading it again/);
  assert.match(view, /if \(c\.revision\) await pressAdvice\(/, "a pressed chip carrying its decision's stamp takes the same road");
});

test("a decided press presses the row's REAL button when the row has it - only a verb it lacks is proposed (the walk's INLINE)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// ANSWER IT has nothing to send"));
  assert.match(press, /const real = advisedIn\(rowNow\(\)\.list\.filter\(\(v\) => !String\(v\.id\)\.startsWith\("advice:"\)\), a\);\n\s+if \(real\) \{ pressRow\(real\.id, null, anchor\); return null; \}/);
  assert.ok(press.indexOf("pressRow(real.id") < press.indexOf("proposeDirect("), "the row's button first, the proposal road last");
});

test("the first screen has one headline count, and reports and FYI stay on the rail (U6)", () => {
  assert.doesNotMatch(view, /m\.card\.away\}/, "the away line repeated SinceBlock's count");
  // which sections are reading is lanes.json's `to_read`, never a list of its own in the card
  assert.match(cards, /isRead = \(g\) => !!SECTION\[g\.key\]\?\.to_read, act = groups\.filter\(\(g\) => !isRead\(g\)\)/);
  assert.doesNotMatch(cards, /To read/);
  assert.doesNotMatch(cards, /tq-day-h">Waiting · /);
});

test("the empty pile's setup chip is not a second 'set up' (U14), and the set-up ask names coding only with a coding tool", () => {
  assert.match(view, /\{ verb: "tour", label: "Change my setup", bar: true \}/);
  // ...and no Set something up beside it: the empty rail's New is the sidebar's own door, and leads there (the owner, 2026-11-10)
  assert.doesNotMatch(view, /label: "Set something up"/);
  assert.doesNotMatch(view, /no repository is touched/);
});

// ONE AI PICKER, THE COMPOSER'S (the owner, 2026-10-29): the chat header's "Which AI speaks here" popover is gone - the model picker at the
// foot of the box picks this chat's AI (chatAi, /api/concierge/chat-ai); a new chat's default and changing it stay in Settings -> AI defaults
test("the chat's one AI picker is the composer's - no header picker, nothing here changes the default", () => {
  const head = view.slice(view.indexOf('<div className="tq-chat-head">'), view.indexOf("{remindOn && <RemindPicker"));
  assert.ok(head.length > 100, "the header was found");
  assert.doesNotMatch(view, /Which AI speaks here|TuneIcon|setAiEl|pickAi/);
  assert.doesNotMatch(view, /"\/api\/concierge\/ai"/, "the default is Settings' to change");
  assert.match(view, /data-tq-model-pick=""/);
  assert.match(view, /api\.post\("\/api\/concierge\/chat-ai"/);
});

test("plain words: the FYI rows (J)", () => {
  assert.doesNotMatch(view, /Your coding tool's AI is the default/);
  assert.doesNotMatch(view, /`dropped: \$\{r\.dropped\}/, "a raw drop reason");
  assert.doesNotMatch(view, /r\.event, r\.tier/, "an event id like item.shown");
  assert.match(cards, />\{btn\("regular_agent"\)\}<\/Button>/);
  assert.doesNotMatch(cards, /regular agent/i);
});

test("no screen points at the removed Timeline or Tasks tab", () => {
  for (const f of ["AssistantView.jsx", "assistantCards.jsx", "BoardView.jsx", "NewPlaybookDialog.jsx", "NewSheet.jsx", "ReportsView.jsx", "ConnectorsView.jsx"]) {
    const code = read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");   // what a comment says reaches nobody
    const strings = (code.match(/"[^"\n]*"|`[^`]*`|>[^<>{}\n]+</g) || []).join("\n");
    assert.doesNotMatch(strings, /on the Timeline|Timeline (post|feed|headline)|lives in Tasks|Saved in Tasks/, f);
  }
});

// NEW'S BOX ANSWERS NOTHING ITSELF (F1, the walks 2026-11-18): its words go to the one start and its task opens - there is no answer under it
test("New's box draws no answer of its own under it", () => {
  assert.doesNotMatch(read("NewSheet.jsx"), /data-tq-new-said|saidBack/);
});
