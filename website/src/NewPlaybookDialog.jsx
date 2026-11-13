import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogContent, DialogTitle, TextField, Typography } from "@mui/material";
import { ButtonBar } from "./ButtonBar.jsx";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import SetupWithAi from "./SetupWithAi.jsx";
import { openAppLink } from "./appLinks.js";

const failure = (e) => e?.response?.data?.detail || e.message || "Could not start playbook setup.";

// `initialText`: the words New's Playbook tab (or the Assistant) wrote - From scratch, filled in. `autoStart`: Set up with AI was pressed there
export default function NewPlaybookDialog({ connectorType = "", initialText = "", autoStart = false, onClose, onManual }) {
  const [mode, setMode] = useState(initialText.trim() ? "scratch" : "");
  const [query, setQuery] = useState("");
  const [before, setBefore] = useState(0);
  const [rows, setRows] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [text, setText] = useState(initialText);
  const [error, setError] = useState("");

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

  // SET UP WITH AI BUILDS IT HERE (the owner, 2026-11-13): no agent task - the Assistant drafts the playbook, checks it and saves it, and
  // the strip below says each step and asks what only you can say; done, the playbook opens (taskuary/build.py)
  const [building, setBuilding] = useState(autoStart && !!initialText.trim()), busy = building;
  const start = () => { setError(""); setBuilding(true); };

  return <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="new-playbook-title" PaperProps={{ sx: { maxHeight: "90vh" } }}>
    <DialogTitle id="new-playbook-title">New playbook</DialogTitle>
    {building ? <DialogContent>
      <SetupWithAi kind="playbook" words={(text.trim() || "Build a playbook from this email.") + (connectorType ? ` For the ${connectorType} connection.` : "")}
        messageId={mode === "email" ? selected?.MessageId : null} auto
        onDone={(v) => { onClose?.(); openAppLink(v.link); }} />
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
            {choice.icon}<Box component="span" sx={{ fontWeight: 600 }}>{choice.title}</Box>
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
          <Typography sx={{ fontSize: 12, fontWeight: 600 }}>Selected example: {selected.Subject || "(no subject)"}</Typography>
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
    <ButtonBar>
      {building ? <Button onClick={onClose}>Close</Button> : <>
        <Button variant="contained" onClick={start} data-tq-view-skip="" disabled={!mode || (mode === "email" ? !selected : !text.trim())}
          startIcon={<AutoAwesomeIcon sx={{ fontSize: 15 }} />}>Set up with AI</Button>
        <Button onClick={onManual}>Write manually</Button>
        <Button onClick={onClose}>Cancel</Button>
      </>}
    </ButtonBar>
  </Dialog>;
}
