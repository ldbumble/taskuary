// THE AGENT'S CHECK-BACK, ON ITS TASK (the owner, 2026-11-06): a small chip - "Checks back Tue 9 AM", what it will verify on hover - and its ×
// cancels it (DELETE /api/tasks/{id}/check-back, owner-only). One per task: a new one replaces the old on the server. Desktop only; the phone
// is told nothing. `task`: the row (TaskId, CheckBackAt, CheckBackWhat, Status); `onChanged` re-reads it after the ×.
import React, { useState } from "react";
import { Box } from "@mui/material";
import AlarmIcon from "@mui/icons-material/AccessTime";
import api from "./api";
import { AttachChip } from "./promptImages.jsx";
import { checkBackLine, checkBackOf } from "./checkBack.js";

export default function CheckBackChip({ task, onChanged = null, sx }) {
  const cb = checkBackOf(task), [gone, setGone] = useState(""), [err, setErr] = useState("");
  if (!cb || gone === cb.at) return null;
  const line = checkBackLine(cb.at);
  if (!line) return null;
  const cancel = async () => {
    setErr("");
    try { await api.delete(`/api/tasks/${task.TaskId}/check-back`); setGone(cb.at); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "That did not cancel - try again."); }
  };
  return <Box component="span" data-tq-check-back={cb.at} sx={{ display: { xs: "none", md: "inline-flex" }, alignItems: "center", gap: 0.5, minWidth: 0, ...sx }}>
    <AttachChip name={line} title={cb.what ? `${line}: ${cb.what}` : line} icon={<AlarmIcon sx={{ fontSize: 13, color: "var(--tq-link, #55697a)", flexShrink: 0 }} />}
      onRemove={cancel} aria-label={line} />
    {err && <Box component="span" role="alert" sx={{ fontSize: 11, color: "var(--tq-danger, #7a2f3c)" }}>{err}</Box>}
  </Box>;
}
