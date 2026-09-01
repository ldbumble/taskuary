// Turn the demo's recorded session list + task detail into the two terminal response shapes
// used by the application. Kept pure so the demo contract is covered without a browser.
export const demoTerminalRecording = (sid, source) => {
  const terminal = (source["/api/terminals"]?.data || []).find((t) => String(t.sid) === String(sid));
  if (!terminal) return null;
  const detail = source["/api/tasks/detail"]?.[String(terminal.taskId)] || {};
  const live = (source["/api/runs/live"]?.data || []).find((r) =>
    r.TaskId === terminal.taskId && r.kind === "run") ||
    (source["/api/runs/live"]?.data || []).find((r) => r.TaskId === terminal.taskId);
  let trace = [];
  const run = (detail.runs || []).find((r) => r.Status === "running");
  try { trace = JSON.parse(run?.TraceJson || "[]").map((e) => e.detail).filter(Boolean); }
  catch { trace = []; }
  const activity = trace.length ? trace : (live?.tail || detail.session?.tail || terminal.tail || []);
  const files = live?.files || detail.session?.files || terminal.files || [];
  const lines = [
    `${terminal.agent || terminal.label || "coder"} · ${detail.task?.Title || `TQ-${terminal.taskId}`}`,
    `${terminal.cwd || "repository"}${files.length ? ` · ${files.join(", ")}` : ""}`,
    "",
    ...activity,
  ].filter((line, i, all) => line || (i > 0 && all[i - 1]));
  return { ...terminal, alive: terminal.alive !== false, lines, tail: lines,
    scrollback: lines.join("\n") };
};
