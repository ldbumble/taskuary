// A START HELD FOR A NEW SENDER IS SAID IN THE CHAT, with its one way on (the owner, 2026-11-09): a coding task held because its sender was new
// opened on "waiting to start" over an empty chat, and Came from said "anything risky waits for your OK" with nothing to press. The chat says
// who sent it and why nothing started by itself (funnel.agent_story's held line, the router's held_note), and Run anyway starts the agent
// through the hold's own release (server.release_task) - the words still came from outside, and the agent runs as it does for any such task.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { ALERT } from "./theme.jsx";

export default function HeldStart({ taskId, line, onChanged }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const run = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${taskId}/release`, {}); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not start - try again."); setBusy(false); }
  };
  return (
    <Box data-tq-held-start="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
      <Typography sx={{ fontSize: 13.5, color: "#292824" }}>{line}</Typography>
      <Button size="small" variant="contained" disableElevation disabled={busy} data-tq-run-anyway="" onClick={run}
        startIcon={busy ? <CircularProgress size={12} color="inherit" /> : null} sx={{ mt: 0.75, fontSize: 12.5, minHeight: 30, textTransform: "none" }}>
        {busy ? "Starting…" : "Run anyway"}</Button>
      {err && <Typography variant="caption" sx={{ display: "block", color: ALERT, mt: 0.5 }}>{err}</Typography>}
    </Box>);
}
