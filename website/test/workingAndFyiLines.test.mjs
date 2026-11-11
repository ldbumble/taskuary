import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


// ...and "should we not have the time on the fyi messages ... it should be white similar to messages showing up in tasks"
test("each fyi line says when it came, on a white box", () => {
  assert.match(read("assistantCards.jsx"), /\{\(i\.since \|\| i\.when\) && <span className="at">\{fmtDateTime\(i\.since \|\| i\.when\)\}<\/span>\}/);
  assert.match(read("assistantView.css"), /\.tq-fyi-box \{[^}]*background: var\(--tq-panel, #fffdfb\);/);
});


// ONE DOOR (the owner, 2026-10-26: "before I hit continue it has a space to type into the agent? coding agents don't have that"): the
// chat agent's box goes exactly when the row offers Continue - an open conversation keeps it, as its way on (2026-09-29)
test("a chat agent's box is gone exactly when the row offers Continue", () => {
  const ws = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");
  assert.match(ws, /: noComposer \? null : <>[\s\S]{0,1200}?<OneBox root=\{ComposerPrimitive\.Root\}/);
  assert.match(page, /noComposer=\{isGeneral && continueHere && !chatPane\}/);
  assert.match(page, /const continueHere = !liveSession && notDone && \(barContinue \|\| \(stage !== "agent" && canContinue\)\);/);
});
