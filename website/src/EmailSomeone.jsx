// EMAIL SOMEONE, from inside a task - whoever started it (the owner, 2026-10-09: "even though i started it from the new button
// i want to be able to create email to send to someone and notify it's done ... choose sender/attachments/draft message with
// ai"). Who it goes to, what it should say, which of the task's files ride on it; the AI writes it from those words AND what the
// work found (outbox.task_email). It waits in Close out as one of the task's emails - edit it, attach more, Approve & send - and
// the task closes once it is sent. Nothing is sent from here.
import React, { useEffect, useState } from "react";
import { Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, TextField, Typography } from "@mui/material";
import api from "./api";
import { EmailRecipients } from "./NewSheet.jsx";
import { DIM, FAINT } from "./theme.jsx";

// the task's own files: what its agents saved or showed, and what came in with its messages
export const taskFiles = (detail) => [
  // ...not the session records: those are Taskuary's own notes on a run, not something to hand anybody
  ...(detail?.artifacts || []).filter((a) => a.url && a.kind !== "coding_session").map((a) => ({ key: `artifact:${a.id}`, kind: "artifact", id: a.id, name: a.name })),
  ...(detail?.attachments || []).filter((a) => a.Path || a.saved || a.url)
    .map((a) => ({ key: `attachment:${a.AttachmentId ?? a.id}`, kind: "attachment", id: a.AttachmentId ?? a.id, name: a.Name ?? a.name })),
];

const Label = ({ children }) => <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: DIM, mb: 0.5 }}>{children}</Typography>;

export default function EmailSomeone({ open, task, detail, onClose, onDrafted }) {
  const [targets, setTargets] = useState([]);
  const [to, setTo] = useState([]), [cc, setCc] = useState([]);
  const [about, setAbout] = useState(""), [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const files = taskFiles(detail);
  useEffect(() => {
    if (!open) return;
    setErr(""); setTo([]); setCc([]); setPicked(new Set()); setAbout("");
    api.get("/api/send-targets").then(({ data }) => setTargets((data.data || []).find((t) => t.channel === "email")?.to || []))
      .catch(() => setTargets([]));
  }, [open]);
  const flip = (k) => setPicked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const go = async () => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/tasks/${task.TaskId}/emails`, { to: to[0], cc, about,
        attach: files.filter((f) => picked.has(f.key)).map(({ kind, id }) => ({ kind, id })) });
      onDrafted?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not draft it"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={() => !busy && onClose?.()} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle>Email someone · {detail?.ref || ""}</DialogTitle>
      <DialogContent sx={{ pt: "8px !important", display: "flex", flexDirection: "column", gap: 1.6 }}>
        <Typography variant="body2" sx={{ color: DIM }}>
          The AI writes it from what you say here and what the work on this task found. It waits in Close out for you to edit and
          approve - nothing is sent now - and the task closes once it is sent.
        </Typography>
        <Box>
          <Label>To</Label>
          {/* one person: each email the task owes goes to one recipient; copy anyone else in */}
          <EmailRecipients value={to} onChange={(v) => setTo(v.slice(-1))} options={targets} placeholder="Search contacts or type an email address" />
        </Box>
        <Box>
          <Label>CC</Label>
          <EmailRecipients value={cc} onChange={setCc} options={targets} placeholder="Optional" />
        </Box>
        <Box>
          <Label>What should it say?</Label>
          <TextField fullWidth multiline minRows={3} value={about} onChange={(e) => setAbout(e.target.value)}
            placeholder="Let them know it's done, and that the template is attached"
            sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
          <Typography variant="caption" sx={{ color: FAINT }}>Left empty, it tells them the task is done.</Typography>
        </Box>
        <Box>
          <Label>Attach</Label>
          {files.length ? files.map((f) => (
            <FormControlLabel key={f.key} sx={{ display: "flex", m: 0, "& .MuiTypography-root": { fontSize: 12.5 } }}
              control={<Checkbox size="small" checked={picked.has(f.key)} onChange={() => flip(f.key)} />} label={f.name} />
          )) : <Typography variant="caption" sx={{ color: FAINT }}>No files on this task yet.</Typography>}
          <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>Anything else: Attach a file on the draft.</Typography>
        </Box>
        {err && <Typography variant="body2" sx={{ color: "#a33b3b" }}>{err}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" disableElevation onClick={go} disabled={busy || !to.length}>
          {busy ? <CircularProgress size={15} /> : "Draft with AI"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
