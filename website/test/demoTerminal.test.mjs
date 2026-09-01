import test from "node:test";
import assert from "node:assert/strict";
import { demoTerminalRecording } from "../src/demoTerminal.js";

test("the demo serves one recorded session to both terminal views", () => {
  const source = {
    "/api/terminals": { data: [{ sid: "demo1", taskId: 9, agent: "codex", cwd: "~/repo", alive: true }] },
    "/api/tasks/detail": { 9: { task: { Title: "Fix the report" }, session: { files: ["report.js"] }, runs: [] } },
    "/api/runs/live": { data: [{ TaskId: 9, kind: "run", tail: ["→ Edit: report.js", "· tests pass"] }] },
  };
  const recording = demoTerminalRecording("demo1", source);
  assert.equal(recording.alive, true);
  assert.match(recording.scrollback, /codex · Fix the report/);
  assert.deepEqual(recording.lines.slice(-2), ["→ Edit: report.js", "· tests pass"]);
});

test("an unknown demo session stays absent instead of inventing a terminal", () => {
  assert.equal(demoTerminalRecording("missing", { "/api/terminals": { data: [] } }), null);
});
