// EMAIL A SUMMARY - one of Share's ways since 2026-10-23 (Share.jsx), and a chat reply's "by email with the file" - from inside a task - whoever started it (the owner, 2026-10-09: "even though i started it from the new button
// i want to be able to create email to send to someone and notify it's done ... choose sender/attachments/draft message with
// ai"; then "add from mailbox picker and teams/chat too"). An email - From, To, CC, which of the task's files ride on it - or a
// chat message into one chat; and what it should say. The AI writes it from those words AND what the work found
// (outbox.task_email). It waits in Close out as one of the task's outputs - edit it, attach more, Send - and the task
// stays open until Mark done (slots._left). Nothing is sent from here.
import React, { useEffect, useState } from "react";
import { Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  MenuItem, Select, TextField, Typography } from "@mui/material";
import api from "./api";
import { ChatRecipient, EmailRecipients } from "./NewSheet.jsx";
import { ACCENT, BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { ChannelIcon } from "./ui.jsx";
import { label } from "./buttons.js";
import { deliverables } from "./taskOutputs.js";

// what a task can send on (slots.KINDS): email, and the chats outbound.send_out carries
export const TASK_CHANNELS = ["email", "teams", "whatsapp", "telegram", "imessage", "discord"];
const NOTES = new Set(["coding_session", "agent_result"]);
// the task's own files: what its agents saved or showed, and what came in with its messages
// ...and the files its agents left in the task's outputs folder (outputs.py, `outputs`: GET /api/task-outputs) - the workbook itself, which
// the list never offered (2026-10-28); a page shown FROM that folder is the same file, offered once (agentRecord.madeOnce)
export const taskFiles = (detail, outputs = []) => {
  const pages = (detail?.artifacts || []).filter((a) => a.url && !NOTES.has(a.kind)), seen = new Set(pages.map((a) => String(a.name || "").toLowerCase()));
  return [
    // ...not the session records nor the answers saved from them: those are Taskuary's own notes on a run, not something to hand anybody -
    // a task worked twenty times offered twenty of them (2026-10-28) - and each thing an agent made once, its newest (taskOutputs.deliverables)
    ...deliverables([...pages, ...(outputs || []).filter((o) => !seen.has(String(o.name || "").toLowerCase()))]).made
      .map((a) => a.kind === "output" ? { key: `output:${a.path}`, kind: "output", path: a.path, name: a.name }
        : { key: `artifact:${a.id}`, kind: "artifact", id: a.id, name: a.name }),
    ...(detail?.attachments || []).filter((a) => a.Path || a.saved || a.url)
      .map((a) => ({ key: `attachment:${a.AttachmentId ?? a.id}`, kind: "attachment", id: a.AttachmentId ?? a.id, name: a.Name ?? a.name })),
  ];
};

const Label = ({ children }) => <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: DIM, mb: 0.5 }}>{children}</Typography>;
const field = { "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } };

export default function EmailSomeone({ open, task, detail, onClose, onDrafted }) {
  const [targets, setTargets] = useState([]), [boxes, setBoxes] = useState([]);
  const [channel, setChannel] = useState("email"), [from, setFrom] = useState("");
  const [to, setTo] = useState([]), [chat, setChat] = useState(null), [cc, setCc] = useState([]);
  const [about, setAbout] = useState(""), [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), [outputs, setOutputs] = useState([]);
  const files = taskFiles(detail, outputs);
  const email = channel === "email";
  useEffect(() => {
    if (!open) return;
    setErr(""); setTo([]); setChat(null); setCc([]); setPicked(new Set()); setAbout("");
    if (task?.TaskId) api.get(`/api/task-outputs/${task.TaskId}`).then(({ data }) => setOutputs(data?.data || [])).catch(() => setOutputs([]));
    api.get("/api/send-targets").then(({ data }) => {
      const list = (data.data || []).filter((t) => TASK_CHANNELS.includes(t.channel));
      setTargets(list); setChannel((c) => (list.some((t) => t.channel === c) ? c : list[0]?.channel || "email"));
    }).catch(() => setTargets([]));
    // From starts on the mailbox this task's mail came in on (outbound.task_mailbox) - a second mailbox's work answered from the first was the wrong hat
    api.get("/api/mailboxes", { params: { task: task?.TaskId } })
      .then(({ data }) => { setBoxes(data.data || []); setFrom(data.default || data.data?.[0]?.address || ""); }).catch(() => setBoxes([]));
  }, [open]);
  const people = targets.find((t) => t.channel === channel)?.to || [];
  const flip = (k) => setPicked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const ready = email ? !!to.length : !!chat;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/tasks/${task.TaskId}/emails`, email
        ? { channel, to: to[0], cc, about, mailbox: from || null, attach: files.filter((f) => picked.has(f.key)).map(({ kind, id, path }) => (kind === "output" ? { kind, path } : { kind, id })) }
        : { channel, to: chat.to, name: chat.name || "", about });
      onDrafted?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not draft it"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={() => !busy && onClose?.()} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle>{label("share")} · {detail?.ref || ""}</DialogTitle>
      <DialogContent sx={{ pt: "8px !important", display: "flex", flexDirection: "column", gap: 1.6 }}>
        <Typography variant="body2" sx={{ color: DIM }}>
          The AI writes a short summary of what this task's work delivered, for the person you pick. It waits in Close out for you
          to edit and send - nothing is sent now. Sending it leaves the task open until you Mark done.
        </Typography>
        {targets.length > 1 && (
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
            {targets.map((t) => (
              <Box key={t.channel} component="button" type="button" onClick={() => { setChannel(t.channel); setTo([]); setChat(null); setCc([]); }}
                sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 1.2, py: 0.6, cursor: "pointer", bgcolor: "#fff",
                  border: `1px solid ${channel === t.channel ? ACCENT : BORDER}`, borderRadius: 2, font: "inherit",
                  boxShadow: channel === t.channel ? `inset 0 0 0 1px ${ACCENT}` : "none",
                  fontSize: 12.5, fontWeight: 600, color: channel === t.channel ? INK : DIM }}>
                <ChannelIcon channel={t.channel} sx={{ fontSize: 15 }} />{t.channel}
              </Box>
            ))}
          </Box>
        )}
        {email && boxes.length > 1 && (
          <Box>
            <Label>From</Label>
            <Select size="small" fullWidth value={from} onChange={(e) => setFrom(e.target.value)} sx={{ fontSize: 13, bgcolor: "#fcfaf7" }}>
              {boxes.map((b) => <MenuItem key={b.address} value={b.address} sx={{ fontSize: 13 }}>{b.address}
                <Typography component="span" sx={{ ml: 1, fontSize: 11, color: FAINT }}>{b.card}</Typography></MenuItem>)}
            </Select>
          </Box>
        )}
        <Box>
          <Label>To</Label>
          {email
            // one person: each message the task owes goes to one recipient; copy anyone else in
            ? <EmailRecipients value={to} onChange={(v) => setTo(v.slice(-1))} options={people} placeholder="Search contacts or type an email address" />
            : <ChatRecipient key={channel} channel={channel} options={people} value={chat} onChange={setChat} />}
        </Box>
        {email && (
          <Box>
            <Label>CC</Label>
            <EmailRecipients value={cc} onChange={setCc} options={people} placeholder="Optional" />
          </Box>
        )}
        <Box>
          <Label>Anything to add?</Label>
          <TextField fullWidth multiline minRows={3} value={about} onChange={(e) => setAbout(e.target.value)}
            placeholder="Optional - e.g. the template is attached; they can start using it Monday" sx={field} />
          <Typography variant="caption" sx={{ color: FAINT }}>Left empty, it is just the results.</Typography>
        </Box>
        {email && (
          <Box>
            <Label>Attach</Label>
            {files.length ? files.map((f) => (
              <FormControlLabel key={f.key} sx={{ display: "flex", m: 0, "& .MuiTypography-root": { fontSize: 12.5 } }}
                control={<Checkbox size="small" checked={picked.has(f.key)} onChange={() => flip(f.key)} />} label={f.name} />
            )) : <Typography variant="caption" sx={{ color: FAINT }}>No files on this task yet.</Typography>}
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>Anything else: {label("attach")} on the draft.</Typography>
          </Box>
        )}
        {err && <Typography variant="body2" sx={{ color: "#a33b3b" }}>{err}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" disableElevation onClick={go} disabled={busy || !ready}>
          {busy ? <CircularProgress size={15} /> : label("redraft", "none")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
