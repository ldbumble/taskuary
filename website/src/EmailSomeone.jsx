// SEND OUT RESULTS, from inside a task - whoever started it (the owner, 2026-10-09: "even though i started it from the new button
// i want to be able to create email to send to someone and notify it's done ... choose sender/attachments/draft message with
// ai"; then "add from mailbox picker and teams/chat too"). An email - From, To, CC, which of the task's files ride on it - or a
// chat message into one chat; and what it should say. The AI writes it from those words AND what the work found
// (outbox.task_email). It waits in Close out as one of the task's outputs - edit it, attach more, Approve & send - and the task
// closes once it is sent. Nothing is sent from here.
import React, { useEffect, useState } from "react";
import { Autocomplete, Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  MenuItem, Select, TextField, Typography } from "@mui/material";
import api from "./api";
import { EmailRecipients } from "./NewSheet.jsx";
import { recipientLabel, recipientOptions } from "./recipientOptions.js";
import { ACCENT, BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { ChannelIcon } from "./ui.jsx";

// what a task can send on (slots.KINDS): email, and the chats outbound.send_out carries
export const TASK_CHANNELS = ["email", "teams", "whatsapp", "telegram", "imessage", "discord"];
// the task's own files: what its agents saved or showed, and what came in with its messages
export const taskFiles = (detail) => [
  // ...not the session records: those are Taskuary's own notes on a run, not something to hand anybody
  ...(detail?.artifacts || []).filter((a) => a.url && a.kind !== "coding_session").map((a) => ({ key: `artifact:${a.id}`, kind: "artifact", id: a.id, name: a.name })),
  ...(detail?.attachments || []).filter((a) => a.Path || a.saved || a.url)
    .map((a) => ({ key: `attachment:${a.AttachmentId ?? a.id}`, kind: "attachment", id: a.AttachmentId ?? a.id, name: a.Name ?? a.name })),
];

const Label = ({ children }) => <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: DIM, mb: 0.5 }}>{children}</Typography>;
const field = { "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } };

export default function EmailSomeone({ open, task, detail, onClose, onDrafted }) {
  const [targets, setTargets] = useState([]), [boxes, setBoxes] = useState([]);
  const [channel, setChannel] = useState("email"), [from, setFrom] = useState("");
  const [to, setTo] = useState([]), [chat, setChat] = useState(null), [cc, setCc] = useState([]);
  const [about, setAbout] = useState(""), [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const files = taskFiles(detail);
  const email = channel === "email";
  useEffect(() => {
    if (!open) return;
    setErr(""); setTo([]); setChat(null); setCc([]); setPicked(new Set()); setAbout("");
    api.get("/api/send-targets").then(({ data }) => {
      const list = (data.data || []).filter((t) => TASK_CHANNELS.includes(t.channel));
      setTargets(list); setChannel((c) => (list.some((t) => t.channel === c) ? c : list[0]?.channel || "email"));
    }).catch(() => setTargets([]));
    api.get("/api/mailboxes").then(({ data }) => { setBoxes(data.data || []); setFrom(data.data?.[0]?.address || ""); }).catch(() => setBoxes([]));
  }, [open]);
  const people = targets.find((t) => t.channel === channel)?.to || [];
  const flip = (k) => setPicked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const ready = email ? !!to.length : !!chat;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/tasks/${task.TaskId}/emails`, email
        ? { channel, to: to[0], cc, about, mailbox: from || null, attach: files.filter((f) => picked.has(f.key)).map(({ kind, id }) => ({ kind, id })) }
        : { channel, to: chat.to, name: chat.name || "", about });
      onDrafted?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not draft it"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={() => !busy && onClose?.()} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle>Send out results · {detail?.ref || ""}</DialogTitle>
      <DialogContent sx={{ pt: "8px !important", display: "flex", flexDirection: "column", gap: 1.6 }}>
        <Typography variant="body2" sx={{ color: DIM }}>
          The AI writes a short summary of what this task's work delivered, for the person you pick. It waits in Close out for you
          to edit and approve - nothing is sent now - and the task closes once it is sent.
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
            : <Autocomplete key={channel} size="small" fullWidth openOnFocus autoHighlight options={people} value={chat}
                onChange={(_e, v) => setChat(v)} getOptionLabel={recipientLabel} isOptionEqualToValue={(o, v) => o.to === v.to}
                filterOptions={(o, st) => recipientOptions(o, st.inputValue)}
                noOptionsText={people.length ? "No matching conversation" : "nothing known on this channel yet"}
                renderOption={(props, t) => (
                  <Box component="li" {...props} key={t.to} sx={{ display: "block !important", fontSize: 12.5 }}>
                    <Box sx={{ fontWeight: 600 }}>{t.name || t.to}</Box>
                    {t.hint && <Box sx={{ fontSize: 10.5, color: FAINT }}>{t.hint}</Box>}
                  </Box>
                )}
                renderInput={(params) => <TextField {...params} placeholder="Search people and conversations" sx={field} />} />}
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
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>Anything else: Attach a file on the draft.</Typography>
          </Box>
        )}
        {err && <Typography variant="body2" sx={{ color: "#a33b3b" }}>{err}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" disableElevation onClick={go} disabled={busy || !ready}>
          {busy ? <CircularProgress size={15} /> : "Draft with AI"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
