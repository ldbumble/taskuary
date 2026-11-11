// AN UNTRUSTED SENDER'S TASK IS WORKED BY NO AGENT, AND SAYS SO WITH ITS ONE WAY ON (the owner, 2026-11-11): the chat shows what came in, this
// one plain line why nothing is working on it (origin.hold, the list's `hold`), and one lit action - Trust <sender>. The press records the
// trust and starts the agent as any task's (server.task_trust); what waited by the box is handed over with it. No "Run anyway": an agent
// either works a sender's words or it does not.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";

export default function HeldStart({ taskId, hold, onChanged }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const trust = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${taskId}/trust`); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It was not trusted - try again."); setBusy(false); }
  };
  return (
    <Box data-tq-held-start="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
      <Typography sx={{ fontSize: 13.5, color: "var(--tq-text, #292824)" }}>{hold.line}</Typography>
      <Box sx={{ display: "flex", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation disabled={busy} onClick={trust} data-tq-trust-sender=""
          startIcon={busy ? <CircularProgress size={12} color="inherit" /> : null} sx={{ fontSize: 12.5, minHeight: 30, textTransform: "none" }}>
          {busy ? "Starting…" : hold.person || "Trust them"}</Button>
      </Box>
      {err && <Typography variant="caption" sx={{ display: "block", color: "var(--tq-danger, #8a3646)", mt: 0.5 }}>{err}</Typography>}
    </Box>);
}
