// Some work is not ours to do: hand it to the person whose job it is, with the AI writing
// the forward message out of the task's own context (systems, ids, errors) so you are not
// retyping the thread into an email. Its own module because two places offer it: the Tasks
// header bar, and the Timeline panel you get by hovering a row - same form, wherever you
// happened to notice the task.
import React, { useEffect, useState } from "react";
import { Autocomplete, Box, Button, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import api from "./api";
import { FAINT, selSx } from "./theme.jsx";

const msgOf = (e, fallback) => (e?.response?.status === 404
  ? "This needs the new server — restart Taskuary and try again."
  : e?.response?.data?.detail || fallback);

export const Handoff = ({ taskId, onSent }) => {
  const [to, setTo] = useState("");
  const [channel, setChannel] = useState("email");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [people, setPeople] = useState([]);
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get("/api/people").then(({ data }) => setPeople(data.data || [])).catch(() => {}); }, []);
  const call = async (body) => (await api.post(`/api/tasks/${taskId}/handoff`, body)).data;
  const draft = async () => {
    setBusy("draft"); setErr("");
    try { setText((await call({ to, channel, draft_only: true })).draft); }
    catch (e) { setErr(msgOf(e, "Could not write the message")); }
    setBusy("");
  };
  const send = async () => {
    setBusy("send"); setErr("");
    try { const d = await call({ to, channel, text }); setSent(d.sent); onSent?.(); }
    catch (e) { setErr(msgOf(e, "Could not send it")); }
    setBusy("");
  };
  if (sent) return (
    <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>
      ✓ sent to {(sent.to || []).join(", ") || "the chat"} by {sent.channel}
    </Typography>
  );
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Select size="small" value={channel} onChange={(e) => setChannel(e.target.value)} sx={{ ...selSx, minWidth: 110 }}>
          <MenuItem value="email" sx={{ fontSize: 12.5 }}>email</MenuItem>
          <MenuItem value="teams" sx={{ fontSize: 12.5 }}>Teams chat</MenuItem>
        </Select>
        <Autocomplete freeSolo size="small" sx={{ flex: 1, minWidth: 220 }} options={people.map((p) => p.Email)}
          value={to} onInputChange={(_e, v) => setTo(v || "")}
          getOptionLabel={(o) => String(o)}
          renderOption={(props, o) => {
            const p = people.find((x) => x.Email === o);
            return <li {...props} style={{ fontSize: 12.5 }}>{p?.Name || o}<span style={{ color: FAINT }}>&nbsp;· {o}</span></li>;
          }}
          renderInput={(params) => <TextField {...params} placeholder="who should own this — email address" />} />
        <Button size="small" onClick={draft} disabled={!!busy}>
          {busy === "draft" ? <CircularProgress size={12} /> : text ? "Rewrite" : "Draft with AI"}
        </Button>
      </Box>
      <TextField multiline minRows={4} size="small" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="What they need to know. Draft with AI writes it from this task's own context — you edit before it goes." />
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Button size="small" variant="contained" disableElevation disabled={!!busy || !to.trim() || !text.trim()}
          startIcon={busy === "send" ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <ForwardToInboxIcon sx={{ fontSize: 15 }} />}
          onClick={send}>Send it</Button>
        {err && <Typography variant="caption" sx={{ color: "#b91c1c" }}>{err}</Typography>}
      </Box>
    </Box>
  );
};
