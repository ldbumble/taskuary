import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-14: "no need while it's working to tell you what it's doing in 2 places"
// ...and the closeout-in-chat spec, 2026-11-04: one "Working on this…" line, the steps folded under it (WorkSteps), alone until they come (AtWork)
test("an agent whose steps stream into the thread says it is working once, not a second copy of its newest step", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const atWork = dock \? <Thinking provider=\{provider\} \/> : <AtWork /);
  assert.match(ws, /return folded && level !== "summary" \? null : <AgentBand \{\.\.\.props\} since=/);
  assert.match(ws, /<ThreadPrimitive\.If running>\s*\{atWork\}/);
  assert.match(ws, /\{serverBusy && atWork\}/);
});

// ...and "should we not have the time on the fyi messages ... it should be white similar to messages showing up in tasks"
test("each fyi line says when it came, on a white box", () => {
  assert.match(read("assistantCards.jsx"), /\{\(i\.since \|\| i\.when\) && <span className="at">\{fmtDateTime\(i\.since \|\| i\.when\)\}<\/span>\}/);
  assert.match(read("assistantView.css"), /\.tq-fyi-box \{[^}]*background: var\(--tq-panel, #fffdfb\);/);
});

// the owner, 2026-10-14: "we need to have general agent closed until i reopen and then continue session"
test("a closed task's conversation shows why it cannot be typed into, in place of the composer", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const closedChat = !dock && !chat && \["done", "dropped"\]\.includes\(String\(task\?\.Status \|\| ""\)\);/);
  // ...a coding source names Reopen, then Continue; a chat task keeps its box under "Type to reopen it" (the owner, 2026-11-07)
  assert.match(ws, /\{closedChat && road \? <div className="tq-aui-hint" role="status"[\s\S]*?This task is closed\. Press \{btn\("reopen"\)\}, then \{btn\("continue"\)\}[\s\S]*?: noComposer \? null : <>[\s\S]*?This task is closed\. Type to reopen it\.[\s\S]{0,1200}?<OneBox root=\{ComposerPrimitive\.Root\}/);
});

// ONE DOOR (the owner, 2026-10-26: "before I hit continue it has a space to type into the agent? coding agents don't have that"): the
// chat agent's box goes exactly when the row offers Continue - an open conversation keeps it, as its way on (2026-09-29)
test("a chat agent's box is gone exactly when the row offers Continue", () => {
  const ws = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");
  assert.match(ws, /: noComposer \? null : <>[\s\S]{0,1200}?<OneBox root=\{ComposerPrimitive\.Root\}/);
  assert.match(page, /noComposer=\{isGeneral && continueHere && !chatPane\}/);
  assert.match(page, /const continueHere = !liveSession && notDone && \(barContinue \|\| \(stage !== "agent" && canContinue\)\);/);
});
