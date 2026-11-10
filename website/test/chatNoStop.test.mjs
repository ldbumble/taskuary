import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// NO STOP ICON ON A CHAT TASK (the owner, 2026-11-05: "we don't need the stop agent button ... it does nothing"); a turn the pane did not start
// is stopped from the chat box's own stop
test("a chat task has no strip stop; the box stops any turn at work", () => {
  assert.doesNotMatch(read("TaskPage.jsx"), /onStop=|data-tq-strip-stop|STRIP_LIVE_H/, "no strip of any task carries a stop");
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /\{\(road \? stopShown : working\) && <ThreadPrimitive\.If running=\{false\}><button type="button" className="tq-aui-cancel" data-tq-stop-turn="" aria-label="Stop response"/);
  // ...in the DOCK only: a task's chat stops on the x of its running turn, never a second stop in its box (the owner, 2026-11-10: "we should
  // have x button for agent to stop in middle of the work")
  assert.match(ws, /extra=\{dock && <><ComposerPrimitive\.Cancel/);
  assert.match(ws, /onClick=\{onStop\}><CloseIcon fontSize="small" \/><\/button><\/ThreadPrimitive\.If>\}/);
});
