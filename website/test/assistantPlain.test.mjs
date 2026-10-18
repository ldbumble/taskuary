// The canvas for a person who does not code (the 2026-10-17 audit): no AI says so once with the way to fix it, a refused Advisor
// press reads the advice again, a rail click shows its card, one headline count, and no words for screens that are gone.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");

test("no AI connected: the strip says it once and its one button opens Connections, AI (U3)", () => {
  assert.match(view, /data\.verb \|\| data\.none === "no_ai"/, "the no-AI answer is kept, not dropped as nothing");
  assert.match(view, /Connect an AI to get a suggestion on each item/);
  assert.match(view, /openAppLink\("#connections=AI"\)\}>Connect an AI<\/button>/);
});

test("a press refused as changed reads the advice again and says so (B6)", () => {
  const press = view.slice(view.indexOf("const pressAdvice"), view.indexOf("// Get me ready for this meeting"));
  assert.match(press, /status !== 409\) throw e/);
  assert.match(press, /await readAdvice\(key\)/);
  assert.match(view, /This changed - here's the updated suggestion\./);
  assert.match(view, /c\.revision \? await pressAdvice\(/, "a pressed chip carrying the Advisor's stamp takes the same road");
});

test("a row clicked on the rail scrolls its card to the top once it mounts (B15)", () => {
  assert.match(view, /toCard\.current = busy \|\| turnFlight\.current \? null : msgs\.length; surface\(key/, "a pull refused as busy lands no card to wait for");
  assert.match(view, /if \(!busy\) toCard\.current = null; return;/, "a pull that failed is forgotten when the turn ends");
  assert.match(view, /el\.scrollIntoView\(\{ block: "start" \}\)/);
});

test("the first screen has one headline count, and reports and FYI are to read (U6)", () => {
  assert.doesNotMatch(view, /m\.card\.away\}/, "the away line repeated SinceBlock's count");
  assert.match(cards, /READ = new Set\(\["reports", "fyi"\]\)/);
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
  assert.match(cards, />Send to agent<\/Button>/);
  assert.doesNotMatch(cards, /regular agent/i);
});

test("no screen points at the removed Timeline or Tasks tab", () => {
  for (const f of ["AssistantView.jsx", "assistantCards.jsx", "BoardView.jsx", "NewPlaybookDialog.jsx", "NewSheet.jsx", "ReportsView.jsx", "ConnectorsView.jsx"]) {
    const code = read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");   // what a comment says reaches nobody
    const strings = (code.match(/"[^"\n]*"|`[^`]*`|>[^<>{}\n]+</g) || []).join("\n");
    assert.doesNotMatch(strings, /on the Timeline|Timeline (post|feed|headline)|lives in Tasks|Saved in Tasks/, f);
  }
});
