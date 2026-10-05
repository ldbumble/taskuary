// CLOSE WITH A NOTE (the owner, 2026-10-05: "i called him, i should be able to write free note to close out task"): work done
// off the app has no reply to send, so what came of it is the close-out - written on the task, and the task closes with it.
import React, { useState } from "react";
import { Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import { ACCENT2, BORDER, FAINT } from "./theme.jsx";

export default function CloseNote({ busy, onClose }) {
  const [note, setNote] = useState("");
  const go = () => note.trim() && !busy && onClose(note.trim());
  return (
    <Box sx={{ mt: 1.2, pt: 1, borderTop: `1px solid ${BORDER}` }}>
      <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.25, fontSize: 9, fontWeight: 750, display: "block", mb: 0.5 }}>
        Close with a note</Typography>
      <TextField multiline minRows={2} maxRows={8} fullWidth size="small" value={note} onChange={(e) => setNote(e.target.value)}
        placeholder="What came of it - a call, a fix, a decision"
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } }}
        sx={{ "& .MuiInputBase-input": { fontSize: 13 } }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75 }}>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>Kept on the task. Nothing is sent.</Typography>
        <Button size="small" variant="contained" disableElevation disabled={busy || !note.trim()} onClick={go}
          startIcon={busy ? <CircularProgress size={11} /> : null} sx={{ fontSize: 11.5, minHeight: 28 }}>
          {busy ? "Closing…" : "Close out"}</Button>
      </Box>
    </Box>
  );
}
