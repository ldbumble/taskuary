// AN UNTRUSTED SENDER'S TASK IS WORKED BY NO AGENT, AND SAYS SO WITH ITS ONE WAY ON (the owner, 2026-11-11): the chat shows what came in, this
// one plain line why nothing is working on it (origin.hold, the list's `hold`), and one lit action - Trust <sender>. The press records the
// trust and starts the agent as any task's (server.task_trust); what waited by the box is handed over with it. No "Run anyway": an agent
// either works a sender's words or it does not.
// ...ON THE TASK PAGE THE PRESS IS THE ROW'S (`onRow`, taskMoves.js trust): lit where he looks first, never only in a pane that may be folded
// (walk 14, 2026-11-24) - the chat keeps the line why, one Trust on the page. A chat with no row of its own (the walk, the wall) keeps it here.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";

// ...and where the press is the row's, the line says where it stands (walk 15 H2: "until you do" with no button in sight)
export const heldPointer = (hold) => `Press ${hold.person || "Trust them"}, first on the task's row.`;
export default function HeldStart({ taskId, hold, onChanged, onRow = false }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const trust = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${taskId}/trust`); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It was not trusted - try again."); setBusy(false); }
  };
  return (
    <Box data-tq-held-start="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
      <Typography sx={{ fontSize: 13.5, color: "var(--tq-text, #292824)" }}>{hold.line}{onRow ? ` ${heldPointer(hold)}` : ""}</Typography>
      {!onRow && <Box sx={{ display: "flex", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation disabled={busy} onClick={trust} data-tq-trust-sender=""
          startIcon={busy ? <CircularProgress size={12} color="inherit" /> : null} sx={{ fontSize: 12.5, minHeight: 30, textTransform: "none" }}>
          {busy ? "Starting…" : hold.person || "Trust them"}</Button>
      </Box>}
      {hold.after && <Typography variant="caption" sx={{ display: "block", color: "var(--tq-faint, #8a857b)", mt: 0.5 }} data-tq-trust-after="">{hold.after}</Typography>}
      {err && <Typography variant="caption" sx={{ display: "block", color: "var(--tq-danger, #8a3646)", mt: 0.5 }}>{err}</Typography>}
    </Box>);
}
