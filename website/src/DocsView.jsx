// Operator documents, Stripe-style like Settings: a landing of doc cards, drilling into
// an editor page with a Docs breadcrumb and a horizontal tab bar to switch documents.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import HistoryEduIcon from "@mui/icons-material/HistoryEdu";
import api from "./api";
import { FAINT, INK } from "./theme.jsx";
import { Crumb, UnderTabs, LandingCard } from "./ui.jsx";

const DOCS = {
  soul: { label: "SOUL.md", icon: <AutoStoriesIcon sx={{ fontSize: 19, color: "#4f46e5" }} />,
    blurb: "The funnel's constitution AND the base system prompt: what counts as a task, how we respond, escalation rules, the repository map. Injected into every triage and every draft." },
  coder: { label: "CODER.md", icon: <SmartToyIcon sx={{ fontSize: 19, color: "#4f46e5" }} />,
    blurb: "The coding agent's rules, stacked on top of SOUL.md for every coder run: how to close out, what it may fix itself, what must escalate, and how to answer the sender." },
  digest: { label: "DIGEST.md", icon: <HistoryEduIcon sx={{ fontSize: 19, color: "#4f46e5" }} />,
    blurb: "The nightly memory distillation — rebuilt every morning at 5:30 from the day's activity, injected into every agent prompt. Editable, but the next refresh overwrites it." },
};
const NAMES = Object.keys(DOCS);

export default function DocsView() {
  const [docName, setDocName] = useState(null);   // null = landing
  const [docs, setDocs] = useState({ soul: "", coder: "", digest: "" });
  const [saved, setSaved] = useState({ soul: "", coder: "", digest: "" });
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await Promise.all(NAMES.map((n) => api.get(`/api/doc/${n}`)));
      const d = Object.fromEntries(NAMES.map((n, i) => [n, res[i].data.content || ""]));
      setDocs(d); setSaved(d); setLoaded(true);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load documents"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    await api.put(`/api/doc/${docName}`, { content: docs[docName] });
    setSaved({ ...saved, [docName]: docs[docName] });
  };

  if (!loaded && !err) return <CircularProgress size={22} sx={{ m: 4 }} />;

  if (docName) {
    return (
      <Box sx={{ maxWidth: 1100 }}>
        <Crumb section="Docs" onBack={() => setDocName(null)} title={DOCS[docName].label} />
        <UnderTabs tabs={NAMES.map((n) => DOCS[n].label)} value={DOCS[docName].label}
          onChange={(label) => setDocName(NAMES.find((n) => DOCS[n].label === label))} />
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, mb: 1.5 }}>
          <Typography variant="body2" sx={{ color: FAINT, flex: 1 }}>{DOCS[docName].blurb}</Typography>
          <Button size="small" variant="contained" disableElevation disabled={docs[docName] === saved[docName]} onClick={save}>
            {docs[docName] === saved[docName] ? "Saved" : "Save"}
          </Button>
        </Box>
        <TextField fullWidth multiline minRows={18} maxRows={32} value={docs[docName]}
          onChange={(e) => setDocs({ ...docs, [docName]: e.target.value })} sx={{ bgcolor: "#fff" }}
          inputProps={{ style: { fontFamily: "'JetBrains Mono', Consolas, monospace", fontSize: 12, lineHeight: 1.55, color: INK } }} />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1160 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>Operator documents</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3 }}>
        {NAMES.map((n) => (
          <LandingCard key={n} icon={DOCS[n].icon} title={DOCS[n].label} desc={DOCS[n].blurb}
            onOpen={() => setDocName(n)} />
        ))}
      </Box>
    </Box>
  );
}
