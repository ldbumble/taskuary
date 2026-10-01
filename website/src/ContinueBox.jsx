import React, { useState } from "react";
import { Box, Button, Popover, TextField, Typography } from "@mui/material";
import api from "./api.js";
import { MicButton } from "./ui.jsx";
import { AttachImage, ImageTray, usePromptImages } from "./promptImages.jsx";

// CONTINUE SESSION (A19, the owner, 2026-09-25: "should work for both coding and non coding agents? Maybe add a new
// prompt inside that continue session"). The agent picks up where it left off - its own CLI session, or its saved
// conversation - and what you type here is the first thing it hears. Leave it empty to continue as is.
// IN LINE, LIKE NEW (the owner, 2026-09-30: "shouldn't this show up in line of the assistant ... same as the new box ... with
// voice note/images"): on the canvas it is a card in the conversation, with the mic and pictures; elsewhere still a popover.
// `onPress` fires AT THE PRESS, before the server answers, so the rail can move the row to Agents working at once;
// `onFail(error)` if it could not continue
export default function ContinueBox({ task, anchor, onClose, onDone, inline = false, taskRef = "", onPress, onFail }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pics = usePromptImages();
  const said = note.trim() || pics.imgs.length;
  const go = async () => {
    setBusy(true); setErr("");
    onPress?.();
    try {
      const { data } = await api.post(`/api/tasks/${task.TaskId}/continue-work`, { note: note.trim() || null, images: pics.paths });
      onClose?.(); onDone?.(data, note.trim() || (pics.imgs.length ? "(images)" : ""));
    } catch (e) { const msg = e?.response?.data?.detail || e?.message || "it could not continue"; setErr(msg); onFail?.(msg); }
    finally { setBusy(false); }
  };
  const body = (
    <Box sx={{ p: 1.5, display: "grid", gap: 1, ...(inline ? {} : { width: 320 }) }}>
      <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#41525f" }}>Continue session{taskRef ? ` · ${taskRef}` : ""}</Typography>
      <TextField size="small" multiline minRows={inline ? 3 : 2} autoFocus placeholder="Anything to tell it as it picks up? (optional) - paste or drop a picture too"
        value={note} onChange={(e) => setNote(e.target.value)} disabled={busy} {...pics.drop}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) go(); }}
        InputProps={{ endAdornment: (
          <Box sx={{ display: "flex", alignSelf: "flex-start", gap: 0.25 }}>
            <AttachImage pics={pics} sx={{ width: 30, height: 30 }} />
            <MicButton size={18} sx={{ width: 30, height: 30, p: 0, color: "#6e685f" }} onText={(t) => setNote((v) => (v ? `${v} ${t}` : t))} />
          </Box>) }}
        sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7", alignItems: "flex-start" } }} />
      <ImageTray pics={pics} />
      <Box sx={{ display: "flex", gap: 0.75 }}>
        <Button size="small" variant="contained" disableElevation disabled={busy || pics.busy} onClick={go}>
          {busy ? "Continuing…" : said ? "Continue with this" : "Continue as is"}</Button>
        <Button size="small" disabled={busy} onClick={onClose}>Cancel</Button>
      </Box>
      {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
    </Box>
  );
  if (inline) return <Box data-tq-continue-card sx={{ border: "1px solid #d5d0c7", borderRadius: "12px", bgcolor: "#fffdfb" }}>{body}</Box>;
  return <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>{body}</Popover>;
}
