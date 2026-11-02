// THE DOORS NEVER REACH THE VIEW (the owner, 2026-11-02): "Set up with AI", "Fix with AI", "Get AI to set it up" and "let AI fill this in"
// open the Assistant itself, so the chat must never press them - each wears data-tq-view-skip, which pageView.js leaves out of what it reads.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const dir = new URL("../src/", import.meta.url);
const files = fs.readdirSync(dir).filter((f) => /\.(jsx|js)$/.test(f) && !f.endsWith(".min.js"));
const read = (f) => fs.readFileSync(new URL(f, dir), "utf8");
// every <Button ...>...</Button> in the source, with where it stands
const buttons = (src) => [...src.matchAll(/<Button\b[\s\S]*?<\/Button>/g)].map((m) => m[0]);
// a door: it opens the chat (openHelp), is marked as the AI's setup, or is the AI's own fix (the sparkle beside onFix)
const isDoor = (b) => /openHelp\(|data-tq-setup-ai|Get AI to set it up|Set up with AI|let AI fill this in/.test(b) || (/AutoAwesomeIcon/.test(b) && /onFix\(/.test(b));

test("pageView leaves out anything marked data-tq-view-skip", () => {
  assert.match(read("pageView.js"), /const SKIP = "[^"]*\[data-tq-view-skip\][^"]*";/);
});

test("every button that opens the Assistant, on every page, is kept out of the view", () => {
  const doors = files.flatMap((f) => buttons(read(f)).filter(isDoor).map((b) => ({ f, b })));
  assert.ok(doors.length >= 5, `found only ${doors.length} doors - the scan is not reading the pages`);
  for (const { f, b } of doors) assert.match(b, /data-tq-view-skip/, `${f}: ${b.slice(0, 160)}`);
});

test("the named doors each carry the mark", () => {
  assert.match(read("SetupWithAi.jsx"), /data-tq-setup-ai=\{kind\} data-tq-view-skip=""/);
  assert.match(read("ConnectorsView.jsx"), /data-tq-ai-setup="start" data-tq-view-skip=""/);
  assert.match(read("ReportsView.jsx"), /data-tq-setup-ai="sources" data-tq-view-skip=""/);
  assert.match(read("RunSteps.jsx"), /onFix && <Button [^>]*data-tq-view-skip=""/);
  assert.match(read("NewPlaybookDialog.jsx"), /onClick=\{start\} data-tq-view-skip=""/);
  // ...New's own press on its Playbook tab is that tab's Set up with AI: skipped there, and only there
  assert.match(read("NewSheet.jsx"), /\{\.\.\.\(kind === "playbook" \? \{ "data-tq-view-skip": "" \} : \{\}\)\}/);
});

// ...a new door is a new caller of openHelp: this list makes it look at the mark. ConnectorsView opens it from useAiWalk, whose one button is
// AiWalkButton; WorkflowEditor hands it to RunSteps as its Fix - both marked above
test("the pages that open the Assistant are the ones whose doors are checked here", () => {
  const callers = files.filter((f) => f !== "pageView.js" && read(f).includes("openHelp(")).sort();
  assert.deepEqual(callers, ["ConnectorsView.jsx", "ReportsView.jsx", "SetupWithAi.jsx", "WorkflowEditor.jsx"]);
});
