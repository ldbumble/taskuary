import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-14: "no need while it's working to tell you what it's doing in 2 places"
test("an agent whose steps stream into the thread keeps only the dots, not a second copy of its newest step", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const atWork = dock \|\| work\?\.steps\?\.length \? <Thinking provider=\{dock \? provider : name\} \/>\s*: <AgentBand /);
  assert.match(ws, /<ThreadPrimitive\.If running>\s*\{atWork\}/);
  assert.match(ws, /\{serverBusy && atWork\}/);
});

// ...and "should we not have the time on the fyi messages ... it should be white similar to messages showing up in tasks"
test("each fyi line says when it came, on a white box", () => {
  assert.match(read("assistantCards.jsx"), /\{\(i\.since \|\| i\.when\) && <span className="at">\{fmtDateTime\(i\.since \|\| i\.when\)\}<\/span>\}/);
  assert.match(read("assistantView.css"), /\.tq-fyi-box \{[^}]*background: #fffdfb;/);
});

// the owner, 2026-10-14: "we need to have general agent closed until i reopen and then continue session"
test("a closed task's conversation shows why it cannot be typed into, in place of the composer", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const closedChat = !dock && \["done", "dropped"\]\.includes\(String\(task\?\.Status \|\| ""\)\);/);
  assert.match(ws, /\{closedChat \? <div className="tq-aui-hint" role="status"[\s\S]*?This task is closed\. Press \{btn\("reopen"\)\}, then \{btn\("continue"\)\}[\s\S]*?: <>\s*<ComposerPrimitive\.Root/);
});

// ONE DOOR (the owner, 2026-10-26: "before I hit continue it has a space to type into the agent? coding agents don't have that"): the
// chat agent's box goes exactly when the row offers Continue - an open conversation keeps it, as its way on (2026-09-29)
test("a chat agent's box is gone exactly when the row offers Continue", () => {
  const ws = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");
  assert.match(ws, /: noComposer \? null : <>\s*<ComposerPrimitive\.Root/);
  assert.match(page, /noComposer=\{isGeneral && continueHere\}/);
  assert.match(page, /const continueHere = !liveSession && notDone && \(barContinue \|\| \(stage !== "agent" && canContinue\)\);/);
});
