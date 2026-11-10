// A START HELD FOR A NEW SENDER IS SAID IN THE CHAT, with its one way on (the owner, 2026-11-09): a coding task held because its sender was new
// opened on "waiting to start" over an empty chat, and Came from said "anything risky waits for your OK" with nothing to press. The chat says
// who sent it and why nothing started by itself (funnel.agent_story's held line, the router's held_note). Two ways on, both through the hold's
// own release (server.release_task): Run anyway starts this task once and the sender stays unknown; Trust sender vouches for them as well.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { ALERT } from "./theme.jsx";

export default function HeldStart({ taskId, line, onChanged }) {
  const [busy, setBusy] = useState(""), [err, setErr] = useState("");
  const run = async (trust) => {
    setBusy(trust ? "trust" : "once"); setErr("");
    try { await api.post(`/api/tasks/${taskId}/release`, { trust }); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not start - try again."); setBusy(""); }
  };
  const btn = (trust, label, props) => (
    <Button size="small" disableElevation disabled={!!busy} onClick={() => run(trust)} {...props}
      startIcon={busy === (trust ? "trust" : "once") ? <CircularProgress size={12} color="inherit" /> : null}
      sx={{ fontSize: 12.5, minHeight: 30, textTransform: "none" }}>{busy === (trust ? "trust" : "once") ? "Starting…" : label}</Button>);
  return (
    <Box data-tq-held-start="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
      <Typography sx={{ fontSize: 13.5, color: "var(--tq-text, #292824)" }}>{line}</Typography>
      <Box sx={{ display: "flex", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
        {btn(false, "Run anyway", { variant: "contained", "data-tq-run-anyway": "" })}
        {btn(true, "Trust sender", { variant: "outlined", "data-tq-trust-sender": "" })}
      </Box>
      {err && <Typography variant="caption" sx={{ display: "block", color: "var(--tq-danger, #8a3646)", mt: 0.5 }}>{err}</Typography>}
    </Box>);
}
