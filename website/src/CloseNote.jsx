import React, { useState } from "react";
import { Box, Button, Popover, TextField, Typography } from "@mui/material";
import { MicButton } from "./ui.jsx";

// CLOSE WITH A NOTE (the owner, 2026-10-05: "i called him, i should be able to write free note to close out task"): work done
// off the app has no reply to send, so what came of it is the close-out - kept on the task as a note, and the task closes.
// IN LINE, LIKE NEW AND CONTINUE (same day: "inline with new box and then button on bottom like we have for add to session"):
// on the canvas a card in the conversation, elsewhere a popover - never a box built into the task card.
// `onSubmit(note)` runs the close (the task view's own Mark done road) and throws if it could not.
export default function CloseNote({ anchor, onClose, onSubmit, inline = false, taskRef = "" }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    if (!note.trim() || busy) return;
    setBusy(true); setErr("");
    try { await onSubmit(note.trim()); onClose?.(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "it could not be closed"); }
    finally { setBusy(false); }
  };
  const body = (
    <Box sx={{ p: 1.5, display: "grid", gap: 1, ...(inline ? {} : { width: 340 }) }}>
      <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#41525f" }}>Close out with a note{taskRef ? ` · ${taskRef}` : ""}</Typography>
      <TextField size="small" multiline minRows={inline ? 3 : 2} autoFocus placeholder="What came of it - a call, a fix, a decision"
        value={note} onChange={(e) => setNote(e.target.value)} disabled={busy}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) go(); }}
        InputProps={{ endAdornment: (
          <Box sx={{ display: "flex", alignSelf: "flex-start" }}>
            <MicButton size={18} sx={{ width: 30, height: 30, p: 0, color: "#6e685f" }} onText={(t) => setNote((v) => (v ? `${v} ${t}` : t))} />
          </Box>) }}
        sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7", alignItems: "flex-start" } }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Button size="small" variant="contained" disableElevation disabled={busy || !note.trim()} onClick={go}>
          {busy ? "Closing…" : "Close out"}</Button>
        <Button size="small" disabled={busy} onClick={onClose}>Cancel</Button>
        <Typography variant="caption" sx={{ color: "#8b857b", ml: "auto" }}>Kept on the task. Nothing is sent.</Typography>
      </Box>
      {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
    </Box>
  );
  if (inline) return <Box data-tq-close-note-card sx={{ border: "1px solid #d5d0c7", borderRadius: "12px", bgcolor: "#fffdfb" }}>{body}</Box>;
  return <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>{body}</Popover>;
}
