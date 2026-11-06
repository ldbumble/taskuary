import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// NO STOP ICON ON A CHAT TASK (the owner, 2026-11-05: "we don't need the stop agent button ... it does nothing"); a turn the pane did not start
// is stopped from the chat box's own stop
test("a chat task has no strip stop; the box stops any turn at work", () => {
  assert.match(read("TaskPage.jsx"), /onStop=\{sessionView && k === "agent" && !home \? \(\) => press\("save-end"\) : null\}/);
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /\{working && <ThreadPrimitive\.If running=\{false\}><button type="button" className="tq-aui-cancel" data-tq-stop-turn="" aria-label="Stop response"/);
  assert.match(ws, /onClick=\{onStop\}><CloseIcon fontSize="small" \/><\/button><\/ThreadPrimitive\.If>\}/);
});
