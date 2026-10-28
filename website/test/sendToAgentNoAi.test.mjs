// SEND TO AGENT WITH NO AI IS THE SAME EVERYWHERE (trust audit F3, 2026-10-28): greyed, "connect one first" its hover - on a task it was,
// on a report's or a mail's card it stood live and opened a "No AI connected" box. One check (capabilities.cannotStart) for every card.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");

test("a card's Send to agent on the row reads the same check as the task page's", () => {
  assert.match(src("capabilities.js"), /export const NO_AI_WHY = "No AI is connected - connect one first";/);
  const view = src("AssistantView.jsx");
  assert.match(view, /const actions = \{ noAi: cannotStart\(caps\),/);
  assert.match(view, /const off = c\.verb === "regular_agent" \? actions\.noAi \|\| "" : "";/);
  assert.match(view, /title: off \|\| c\.hint, disabled: actions\.busy \|\| !!off,/);
  // ...and an FYI handful's own Send to agent under one of its lines
  assert.match(src("assistantCards.jsx"), /disabled=\{!!busy \|\| !!noAi\} onClick=\{\(\) => setAsking\(\{ key: i\.key, coding: false \}\)\}/);
});
