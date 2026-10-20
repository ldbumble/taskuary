// The canvas for a person who does not code (the 2026-10-17 audit): no AI says so once with the way to fix it, a refused Advisor
// press reads the advice again, a rail click shows its card, one headline count, and no words for screens that are gone.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");

test("no AI connected: the strip says it once and its one button opens Connections, AI (U3)", () => {
  assert.match(read("tableState.js"), /if \(data\.verb \|\| data\.none\)/, "the no-AI answer is kept, not dropped as nothing");
  assert.match(view, /Connect an AI to get a suggestion on each item/);
  assert.match(view, /openAppLink\(place\("ai"\)\.href\)\}>Connect an AI<\/button>/);
  // ...and the capability says so too: one answer for "is an AI connected" (capabilities.js)
  assert.match(view, /caps\.ai === false \|\| \(advice\?\.none === "no_ai" && advice\.for === table\.key\)/);
});

test("a press refused as changed reads the advice again and says so (B6)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// Get me ready for this meeting"));
  assert.match(press, /status !== 409\) throw e/);
  assert.match(press, /await readAdvice\(key\)/);
  assert.match(view, /This changed - here's the updated suggestion\./);
  assert.match(view, /c\.revision \? await pressAdvice\(/, "a pressed chip carrying the Advisor's stamp takes the same road");
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
  assert.match(view, /putOnTable\(card, "card"\);/, "the Board's open");
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

test("plain words: the AI popover, the Advisor's notes and the FYI rows (J)", () => {
  assert.doesNotMatch(view, /Your coding tool's AI is the default/);
  assert.match(view, /export const aiSays = /);
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
