// A task whose agent finished leads with Mark done on the desktop card - the server's move for it (funnel_presentation.move_of), which
// the phone reads too (the owner, 2026-10-22): never "who should take it?" over work that is over.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("a finished agent's task leads with Mark done, read off the server's move", () => {
  const cards = src("assistantCards.jsx");
  assert.match(cards, /const reported = \(!!reportOf\(doc\) \|\| card\.shows\?\.move === btn\("close"\)\) && \(own \|\| mineAlone\);/);
  // ...and the move that reads is the one the reported branch draws: Mark done, its own button
  assert.match(cards, /\{reported \? \(\s*<YourMove title=\{btn\("close"\)\}/);
});
