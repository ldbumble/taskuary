// The canvas for a person who does not code (the 2026-10-17 audit): no AI says so once with the way to fix it, a refused Advisor
// press reads the advice again, a rail click shows its card, one headline count, and no words for screens that are gone.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");

test("no AI connected: no strip says it, and nothing is added to the row - a row's own Connect an AI is lit where it has one (U3)", () => {
  assert.match(read("tableState.js"), /data\.verb \|\| data\.none \|\| data\.state/, "the no-AI answer is kept, not dropped as nothing");
  // ...the strip that asked for an AI is gone (the owner, 2026-10-26: "remove the advisor"), and with it its button: setup is where an AI
  // is connected, and a failed run's Result says why and where (the same day: "if you don't get through ai setup the whole thing doesn't work")
  assert.doesNotMatch(view, /noai:connect/, "and no Connect an AI added to the row (the owner, 2026-10-26: \"why would we need connect an ai?\")");
  assert.match(read("ActionRow.jsx"), /const conn = move === "ai" \? verbs\.list\.find\(\(v\) => v\.label === CONNECT_AI && !v\.disabled\) : null;/);
  assert.doesNotMatch(view, /adviceNone\("no_ai"\)/);
  // ...and only where the move needs an AI: a rule decides the rest with none connected (`needs_ai`, advisor.decide)
  assert.match(view, /aiOff: caps\.ai === false,/);
  assert.match(read("advice.js"), /advice\.none === "no_ai" \|\| \(aiOff && !!advice\.needs_ai\)/);
});

test("a press refused as changed reads the advice again, and the row lights the new pick (B6)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// Get me ready for this meeting"));
  assert.match(press, /status !== 409\) throw e/);
  assert.match(press, /await readAdvice\(key\)/);
  // ...said by no strip since 2026-10-26: the row relights; the Advisor's own button says it on the chat's error line (ActionRow onErr)
  assert.doesNotMatch(view, /This changed - reading it again/);
  assert.match(read("ActionRow.jsx"), /This changed - here's the updated suggestion\./);
  assert.match(view, /if \(c\.revision\) await pressAdvice\(/, "a pressed chip carrying the Advisor's stamp takes the same road");
});

test("an Advisor press presses the row's REAL button when the row has it - only a verb it lacks is proposed (the walk's INLINE)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// ANSWER IT has nothing to send"));
  assert.match(press, /const real = advisedIn\(rowNow\(\)\.list\.filter\(\(v\) => !String\(v\.id\)\.startsWith\("advice:"\)\), a\);\n\s+if \(real\) \{ pressRow\(real\.id, null, anchor\); return null; \}/);
  assert.ok(press.indexOf("pressRow(real.id") < press.indexOf("proposeDirect("), "the row's button first, the proposal road last");
  assert.match(read("ActionRow.jsx"), /await onPropose\(advice, anchor \|\| e\?\.currentTarget \|\| null\)/, "the press carries its anchor, so Remind me opens its picker there");
});

test("every item put on the table goes through putOnTable, which pins its card to the top and keeps it there (B15, SEEN)", () => {
  // ONE road: the turn's landing, the Board's open, a browse card, an unfold - none sets Current on its own any more
  assert.match(view, /const putOnTable = useCallback\(\(card, how = "pile"\) => \{/);
  assert.match(view, /if \(!same\) putOnTable\(card\);\n\s+if \(!ahead \|\| ahead\.say !== data\.say\) say\(data\.say\);/, "landed");
  assert.match(view, /putOnTable\(line\.card\);\n\s+if \(line\.text\) say\(line\.text\);/, "a line drawn ahead of its answer (drawAhead)");
  assert.match(view, /pull\(`task:\$\{req\.tid\}`\); return;/, "the Board's open goes the rail's road - no bare card for a walk on the phone (2026-10-23)");
  assert.match(view, /putOnTable\(null, "view"\);\s+\/\/ its top in view/, "a browse card");
  assert.match(view, /if \(onTable\) \{ setFoldedKey\(null\); browseDown\(\); putOnTable\(null, "view"\); \}/, "the folded item opened again");
  assert.equal((view.match(/setCurrent\(/g) || []).length, 1, "Current is set in one place");
  assert.doesNotMatch(view, /toCard/);
  // the pin: the card's top to the top of the body, on mount and on every resize, until the owner scrolls
  assert.match(view, /if \(Math\.abs\(off\) > 2\) body\.scrollTop \+= off;/);
  assert.match(view, /const ro = new ResizeObserver\(\(\) => \{ if \(keepTable\(\)\) return;/);
  assert.match(view, /el\.addEventListener\("wheel", own, \{ passive: true \}\)/);
  // ...a receipt under it keeps the card in view; an answer or a proposal to confirm lets go
  assert.match(view, /if \(pin\.current && m && \(m\.proposal \|\| \(!m\.card && m\.role !== "receipt" && m\.role !== "browse"\)\)\) pin\.current = false;/);
});

test("the first screen has one headline count, and reports and FYI are to read (U6)", () => {
  assert.doesNotMatch(view, /m\.card\.away\}/, "the away line repeated SinceBlock's count");
  // which sections are reading is lanes.json's `to_read`, never a list of its own in the card
  assert.match(cards, /isRead = \(g\) => !!SECTION\[g\.key\]\?\.to_read/);
  assert.match(cards, /To read · /);
  assert.doesNotMatch(cards, /tq-day-h">Waiting · /);
});

test("the empty pile's setup chip is not a second 'set up' (U14), and the set-up ask names coding only with a coding tool", () => {
  assert.match(view, /\{ verb: "tour", label: "Change my setup" \}/);
  assert.match(view, /nothing changes until you say so\."\n\s+\+ \(canCode \?/);
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

test("plain words: the Advisor's notes and the FYI rows (J)", () => {
  assert.doesNotMatch(view, /Your coding tool's AI is the default/);
  assert.doesNotMatch(view, /`dropped: \$\{r\.dropped\}/, "a raw drop reason");
  assert.doesNotMatch(view, /r\.event, r\.tier/, "an event id like item.shown");
  assert.match(view, /No AI connected yet - connect one under Connections, AI\./);
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
