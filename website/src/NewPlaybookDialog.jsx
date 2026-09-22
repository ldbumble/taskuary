import React, { Suspense, lazy, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, TextField, Typography } from "@mui/material";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";

const GeneralWorkspace = lazy(() => import("./GeneralWorkspace.jsx"));
const failure = (e) => e?.response?.data?.detail || e.message || "Could not start playbook setup.";

export default function NewPlaybookDialog({ connectorType = "", onClose, onManual }) {
  const [mode, setMode] = useState("");
  const [query, setQuery] = useState("");
  const [before, setBefore] = useState(0);
  const [rows, setRows] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [task, setTask] = useState(null);

  useEffect(() => {
    if (mode !== "email") return undefined;
    let live = true;
    setLoading(true); setError("");
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get(`/api/playbooks/examples?q=${encodeURIComponent(query)}&before=${before}`);
        if (live) { setRows((old) => before ? [...old, ...data.data] : data.data); setNext(data.next); }
      } catch (e) { if (live) setError(failure(e)); }
      finally { if (live) setLoading(false); }
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [mode, query, before]);

  const start = async () => {
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/api/playbooks/setup", {
        text: text.trim(), message_id: mode === "email" ? selected?.MessageId : null, connector_type: connectorType,
      });
      setTask(data.task);
    } catch (e) { setError(failure(e)); }
    finally { setBusy(false); }
  };

  return <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth={task ? "lg" : "sm"}
    aria-labelledby="new-playbook-title" PaperProps={{ sx: task ? { height: "85vh" } : { maxHeight: "90vh" } }}>
    <DialogTitle id="new-playbook-title">{task ? "Build your playbook with AI" : "New playbook"}</DialogTitle>
    {task ? <DialogContent sx={{ display: "flex", flexDirection: "column", minHeight: 0, p: 0 }}>
      <Typography sx={{ px: 3, pb: 1, color: "text.secondary", fontSize: 13 }}>
        Your assistant will draft the steps and review rules with you. Approve the finished draft on the task.
      </Typography>
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <Suspense fallback={<CircularProgress sx={{ m: 3 }} />}><GeneralWorkspace task={task} compact /></Suspense>
      </Box>
    </DialogContent> : <DialogContent>
      <Typography sx={{ color: "text.secondary", mb: 2 }}>
        A playbook teaches your assistant how to handle a recurring request. Start with an example, or describe what you need.
      </Typography>
      {connectorType && <Alert severity="info" sx={{ mb: 2 }}>For your {connectorType} connection</Alert>}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1.5, mb: 2 }}>
        {[{ value: "email", title: "Use a past email", detail: "Choose a request you have received.", icon: <MailOutlineIcon /> },
          { value: "scratch", title: "Start from scratch", detail: "Tell the assistant what should happen.", icon: <AutoAwesomeIcon /> }].map((choice) =>
          <Button key={choice.value} variant={mode === choice.value ? "contained" : "outlined"} aria-pressed={mode === choice.value}
            disabled={busy} onClick={() => { setMode(choice.value); setError(""); }}
            sx={{ alignItems: "flex-start", flexDirection: "column", textAlign: "left", textTransform: "none", p: 2, gap: 0.75 }}>
            {choice.icon}<Box component="span" sx={{ fontWeight: 700 }}>{choice.title}</Box>
            <Box component="span" sx={{ fontSize: 12, fontWeight: 400 }}>{choice.detail}</Box>
          </Button>)}
      </Box>
      {mode === "email" && <>
        <TextField fullWidth size="small" label="Search past emails" placeholder="Subject, sender, or a phrase"
          value={query} disabled={busy} onChange={(e) => { setQuery(e.target.value); setBefore(0); setRows([]); }} />
        <Typography sx={{ fontSize: 12, color: "text.secondary", my: 1 }}>Searches incoming email already imported into Taskuary, including older mail.</Typography>
        <Box sx={{ maxHeight: 230, overflowY: "auto", mb: 1 }} aria-label="Past emails" aria-busy={loading}>
          {rows.map((row) => <Button key={row.MessageId} fullWidth aria-pressed={selected?.MessageId === row.MessageId}
            disabled={busy} onClick={() => setSelected(row)} variant={selected?.MessageId === row.MessageId ? "outlined" : "text"}
            sx={{ display: "block", textAlign: "left", textTransform: "none", px: 1.5, py: 1, mb: 0.5 }}>
            <Typography sx={{ fontWeight: 600, fontSize: 13 }}>{row.Subject || "(no subject)"}</Typography>
            <Typography sx={{ fontSize: 12, color: "text.secondary" }}>{row.FromName || row.FromEmail} · {(row.SentAt || "").slice(0, 10)}</Typography>
          </Button>)}
          {loading && <CircularProgress size={20} sx={{ m: 1 }} aria-label="Searching emails" />}
          {!loading && !rows.length && <Typography sx={{ py: 2, fontSize: 13 }}>
            {query ? "No emails match. Try another search or start from scratch." : "No imported emails yet. You can start from scratch."}
          </Typography>}
          {next && !loading && <Button onClick={() => setBefore(next)} disabled={busy}>Load more emails</Button>}
        </Box>
        {selected && <Box sx={{ bgcolor: "action.hover", p: 1.5, mb: 2, borderRadius: 1 }}>
          <Typography sx={{ fontSize: 12, fontWeight: 700 }}>Selected example: {selected.Subject || "(no subject)"}</Typography>
          <Typography sx={{ fontSize: 12, whiteSpace: "pre-wrap", maxHeight: 120, overflowY: "auto", mt: 0.75 }}>{selected.BodyText || "This email has no text preview."}</Typography>
          <Button size="small" disabled={busy} onClick={() => setSelected(null)}>Remove example</Button>
        </Box>}
      </>}
      {mode && <TextField fullWidth multiline minRows={3} label={mode === "email" ? "Anything to add? (optional)" : "What should this playbook do?"}
        placeholder="When someone asks for updated item numbers, gather the latest data and prepare a summary for my review."
        value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />}
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {mode && <Typography sx={{ color: "text.secondary", fontSize: 12, mt: 1.5 }}>The assistant will help you define the steps, connections, and what needs your approval.</Typography>}
    </DialogContent>}
    <DialogActions sx={{ px: 3, pb: 2, flexWrap: "wrap", gap: 1 }}>
      {task ? <>
        <Button href={`#task=${task.TaskId}`} onClick={onClose}>Open task</Button>
        <Typography sx={{ mr: "auto", fontSize: 12, color: "text.secondary" }}>Saved in Tasks so you can return later.</Typography>
        <Button onClick={onClose}>Close</Button>
      </> : <>
        <Button onClick={onManual} disabled={busy} sx={{ mr: "auto" }}>Write manually</Button>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" onClick={start} disabled={busy || !mode || (mode === "email" ? !selected : !text.trim())}
          startIcon={busy ? <CircularProgress size={16} color="inherit" /> : <AutoAwesomeIcon />}>{busy ? "Starting…" : "Set up with AI"}</Button>
      </>}
    </DialogActions>
  </Dialog>;
}
