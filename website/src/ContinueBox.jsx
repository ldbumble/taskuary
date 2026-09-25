import React, { useState } from "react";
import { Box, Button, Popover, TextField, Typography } from "@mui/material";
import api from "./api.js";

// CONTINUE SESSION (A19, the owner, 2026-09-25: "should work for both coding and non coding agents? Maybe add a new
// prompt inside that continue session"). The agent picks up where it left off - its own CLI session, or its saved
// conversation - and what you type here is the first thing it hears. Leave it empty to continue as is.
export default function ContinueBox({ task, anchor, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${task.TaskId}/continue-work`, { note: note.trim() || null });
      onClose?.(); onDone?.(data, note.trim());
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "it could not continue"); }
    finally { setBusy(false); }
  };
  return (
    <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
      <Box sx={{ p: 1.5, display: "grid", gap: 1, width: 300 }}>
        <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#41525f" }}>Continue session</Typography>
        <TextField size="small" multiline minRows={2} autoFocus placeholder="Anything to tell it as it picks up? (optional)"
          value={note} onChange={(e) => setNote(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) go(); }} />
        <Box sx={{ display: "flex", gap: 0.75 }}>
          <Button size="small" variant="contained" disableElevation disabled={busy} onClick={go}>
            {busy ? "Continuing…" : note.trim() ? "Continue with this" : "Continue as is"}</Button>
          <Button size="small" disabled={busy} onClick={onClose}>Cancel</Button>
        </Box>
        {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
      </Box>
    </Popover>
  );
}
