// WHAT RIDES WITH THE REPLY.
//
// A draft read "Attached are the PTO accrual files for the 8/31 payroll" and the card showed
// nothing, because nothing in Taskuary could attach a file at all - approving it would have sent an
// external recipient a mail promising two workbooks and carrying none (the owner, 2026-09-14: "we
// need UI to show the attachment here... otherwise it looks like it sends without attachment").
//
// So the card says what is going: every file by name and size, one click to take one off, one to add
// one - and when the words promise an attachment that is not there, a line saying so. It never
// blocks the send; the owner can always mean "attached in my last mail".
import React, { useRef, useState } from "react";
import { Box, Button, Chip, CircularProgress, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import api from "./api.js";
import { ALERT_INK, DIM } from "./theme.jsx";
import { promisesFiles, sizeText } from "./replyFiles.js";

export default function ReplyFiles({ reviewId, files = [], text = "", channel = "email", onChanged }) {
  const pick = useRef(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const mail = String(channel || "email").toLowerCase() === "email";

  const add = async (chosen) => {
    const list = [...(chosen || [])];
    if (!list.length) return;
    setErr(""); setBusy("adding");
    try {
      for (const file of list) {
        await api.post(`/api/reviews/${reviewId}/attachment`, file,
          { params: { name: file.name }, headers: { "Content-Type": file.type || "application/octet-stream" } });
      }
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not attach that file"); }
    finally { setBusy(""); if (pick.current) pick.current.value = ""; }
  };
  const drop = async (name) => {
    setErr(""); setBusy(name);
    try {
      await api.delete(`/api/reviews/${reviewId}/attachment`, { params: { name } });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not remove that file"); }
    finally { setBusy(""); }
  };

  const missing = !files.length && promisesFiles(text);
  return (
    <Box sx={{ mb: 0.75 }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75 }}>
        {files.map((f) => (
          <Chip key={f.name} size="small" icon={<AttachFileIcon sx={{ fontSize: 14 }} />}
            label={`${f.name} · ${sizeText(f.size)}`} disabled={busy === f.name}
            onDelete={() => drop(f.name)} sx={{ maxWidth: 320 }} />
        ))}
        {mail ? (
          <Button size="small" onClick={() => pick.current?.click()} disabled={busy === "adding"}
            startIcon={busy === "adding" ? <CircularProgress size={11} /> : <AttachFileIcon sx={{ fontSize: 14 }} />}
            sx={{ color: DIM, textTransform: "none", fontSize: 11.5 }}>
            {busy === "adding" ? "Attaching…" : files.length ? "Attach another" : "Attach a file"}
          </Button>
        ) : (
          <Typography variant="caption" sx={{ color: DIM }}>
            A {channel} message cannot carry a file — answer by email to attach one.
          </Typography>
        )}
        <input ref={pick} hidden type="file" multiple onChange={(e) => add(e.target.files)} />
      </Box>
      {missing && mail && (
        <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: ALERT_INK }}>
          This draft mentions an attachment and nothing is attached — it will send with the words only.
        </Typography>
      )}
      {err && <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: ALERT_INK }}>{err}</Typography>}
    </Box>
  );
}
