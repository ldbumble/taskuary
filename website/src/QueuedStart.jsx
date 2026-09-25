// A QUEUED START, said the same way wherever the task shows (T10, the owner, 2026-09-25). It read "starts by itself
// when it can" on a start that had already failed, and neither page offered the Retry or Cancel the server has had
// since PW-087. What it waits for, or why it could not start - and the two moves.
import React, { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { ALERT, ROLES } from "./theme.jsx";

export default function QueuedStart({ taskId, queued, onChanged, compact = false }) {
  const [busy, setBusy] = useState(""), [err, setErr] = useState("");
  if (!queued) return null;
  const failed = queued.state === "failed";
  const act = (e, what) => {
    e.stopPropagation();
    setBusy(what); setErr("");
    (what === "retry" ? api.post(`/api/tasks/${taskId}/dispatch/retry`) : api.delete(`/api/tasks/${taskId}/dispatch`))
      .then(() => onChanged?.())
      .catch((x) => setErr(x?.response?.data?.detail || "That did not go through."))
      .finally(() => setBusy(""));
  };
  const c = failed ? { bg: "#f3e7e9", bd: ALERT, ink: ALERT } : { bg: ROLES.working.tint, bd: ROLES.working.solid, ink: ROLES.working.ink };
  return (
    <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.75, px: 1.1, py: 0.8, bgcolor: c.bg, border: `1px solid ${c.bd}55`,
      borderLeft: `3px solid ${c.bd}`, borderRadius: 1.25 }}>
      <Typography variant="caption" sx={{ color: c.ink, fontWeight: 700, display: "block", fontSize: compact ? 10 : 11.5, lineHeight: 1.4 }}>
        {failed ? "⏳ Could not start" : queued.behind ? `⏳ Waiting on ${queued.behind}` : "⏳ Waiting for a free agent slot"}
        {!failed && queued.behindTitle ? ` — “${queued.behindTitle}”` : ""}
      </Typography>
      <Typography variant="caption" sx={{ color: c.ink, display: "block", fontSize: compact ? 9.5 : 11, lineHeight: 1.45, mt: 0.2 }}>
        {failed ? (queued.lastError || "it ran out of tries") + " - it will not try again by itself"
          : `${queued.why ? `${queued.why} · ` : queued.reason ? `${queued.reason} · ` : ""}starts by itself when a slot frees up`}
      </Typography>
      <Box sx={{ display: "flex", gap: 0.75, mt: 0.6 }}>
        {failed && <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={(e) => act(e, "retry")}
          sx={{ fontSize: 10.5, minHeight: 24, py: 0, px: 1.1 }}>{busy === "retry" ? "Starting…" : "Start now"}</Button>}
        <Button size="small" disabled={!!busy} onClick={(e) => act(e, "cancel")}
          sx={{ fontSize: 10.5, minHeight: 24, py: 0, px: 1.1 }}>{busy === "cancel" ? "Cancelling…" : "Cancel"}</Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: ALERT, display: "block", mt: 0.4 }}>{err}</Typography>}
    </Box>
  );
}
