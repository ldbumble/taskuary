// THE TASK'S CODE CHANGES, AT ANY TIME (the owner, 2026-11-06: "where is the diff button to see code changed?"): the coding task header's quiet
// Changes button (TaskPage HeadPop) opens the whole diff of its work so far - every file changed since its first session started, committed or
// not (landing.changes) - in the one viewer an edit's own row uses (DiffView), each file a fold. Read fresh at every open, so it follows the work.
import React, { useEffect, useState } from "react";
import api from "./api.js";
import DiffView from "./DiffView.jsx";
import { parseUnified } from "./diffView.js";
import { plural } from "./timeWords.js";

export default function CodeChanges({ taskId }) {
  const [got, setGot] = useState(undefined);
  useEffect(() => { let on = true; api.get(`/api/tasks/${taskId}/changes`).then(({ data }) => on && setGot(data?.data || null)).catch(() => on && setGot(null));
    return () => { on = false; }; }, [taskId]);
  if (got === undefined) return <div className="tq-dv-empty" role="status">Reading the changes…</div>;
  if (!got) return <div className="tq-dv-empty" data-tq-changes="">No session of this task has worked in a checkout yet - nothing to compare.</div>;
  const files = parseUnified(got.diff), plus = files.reduce((t, f) => t + f.plus, 0), minus = files.reduce((t, f) => t + f.minus, 0);
  return <div data-tq-changes="">
    <div style={{ fontSize: 12.5, color: "#5f5a52", margin: "0 0 8px" }}>
      {files.length ? `${plural(files.length, "file")} changed (+${plus} −${minus})` : "Nothing changed yet"} since it started on {got.base} ({got.start})
      {got.cut ? " - the diff is long; this is its start" : ""}</div>
    {!!files.length && <DiffView files={files} />}
  </div>;
}
