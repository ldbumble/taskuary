// Operator documents: the markdown the agents actually read. A list on the left, the file
// open beside it - these six are read against each other, so hiding five behind a landing
// grid cost a round trip every time you wanted to compare two.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import HistoryEduIcon from "@mui/icons-material/HistoryEdu";
import PsychologyIcon from "@mui/icons-material/Psychology";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import RateReviewIcon from "@mui/icons-material/RateReview";
import api from "./api";
import { FAINT, INK, mono } from "./theme.jsx";

const DOCS = {
  soul: { label: "SOUL.md", icon: <AutoStoriesIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "The funnel's constitution AND the base system prompt: what counts as a task, how we respond, escalation rules, the repository map. Injected into every triage and every draft." },
  triage: { label: "TRIAGE.md", icon: <FilterAltIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "The triage brain's instructions — what makes a message a task, a question, or FYI, and which way to lean when torn. Ships as a sensible default; edit it to reshape every verdict. Keep the JSON answer line, or triage falls back to keyword heuristics. Blank it to restore the default." },
  style: { label: "STYLE.md", icon: <RateReviewIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "How you write replies — greeting, tone, length, phrasing — layered onto SOUL.md for every draft. Write it yourself, or Generate from history distills it from your last three months of sent mail; your own lines outside the marked block always survive a regenerate." },
  coder: { label: "CODER.md", icon: <SmartToyIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "The coding agent's rules, stacked on top of SOUL.md for every coder run: how to close out, what it may fix itself, what must escalate, and how to answer the sender." },
  digest: { label: "DIGEST.md", icon: <HistoryEduIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "Your morning brief — what's in flight, who waits on whom. Written by the Morning digest report: the same brief lands on your Timeline daily, its prompt is edited on the Reports tab (that decides what goes in here), and deleting that report turns it off." },
  learned: { label: "LEARNED.md", icon: <PsychologyIcon sx={{ fontSize: 19, color: "#55697a" }} />,
    blurb: "What the system has learned about YOU — style, responsibilities, what deserves a task — distilled from your verdicts: edited drafts, rejections, reclassifications. Hypotheses graduate on evidence; every line is yours to edit or delete, and SOUL.md always outranks it." },
};
const NAMES = Object.keys(DOCS);

// Docs that can bootstrap themselves from the mailbox's own past: the button reads ~3
// months of mail server-side and fills the doc's marked block - hand-written lines
// outside the markers always survive.
const GEN = {
  triage: "reads 3 months of your mailbox — what you answered vs let sit — and writes what matters into the marked block",
  style: "reads 3 months of your sent mail and distills how you write into the marked block",
};

// Your name, in one place. The documents refer to the owner nine times between them; typed
// literally, changing it meant finding every one - so they carry {{owner}} tokens and this is
// where the actual name lives. Saving also rewrites any literal name still in the docs.
const OwnerCard = () => {
  const [who, setWho] = useState(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      setWho(data);
      setName(data.owner === "the owner" ? "" : data.owner || "");
      setEmail(data.owner_email || "");
    }).catch(() => setWho({}));
  }, []);
  const save = async () => {
    setMsg("");
    try {
      const { data } = await api.put("/api/owner", { name: name.trim(), email: email.trim() || null });
      setMsg(`saved ✓${data.retokened?.length ? ` — ${data.retokened.join(", ")} rewritten to use it everywhere` : ""}`);
    } catch (e) { setMsg(e?.response?.data?.detail || "could not save"); }
  };
  if (!who) return null;
  return (
    <Box sx={{ mb: 2.5, p: 1.75, bgcolor: "#fff", border: "1px solid #e1dcd5", borderRadius: 2,
      display: "flex", gap: 1.25, alignItems: "center", flexWrap: "wrap" }}>
      <Box sx={{ minWidth: 260, flex: 1 }}>
        <Typography variant="body2" sx={{ color: INK, fontWeight: 700 }}>Who the documents speak for</Typography>
        <Typography variant="caption" sx={{ color: FAINT }}>
          One field, every mention: the docs say {"{{owner}}"} and this fills it in — signatures, escalation
          rules, the coder's instructions. Saving also converts any name still typed into them.
        </Typography>
      </Box>
      <TextField size="small" label="Your name" value={name} onChange={(e) => setName(e.target.value)}
        sx={{ bgcolor: "#fff", width: 200 }} />
      <TextField size="small" label="Email" value={email} onChange={(e) => setEmail(e.target.value)}
        sx={{ bgcolor: "#fff", width: 230 }} />
      <Button size="small" variant="contained" disableElevation disabled={!name.trim()} onClick={save}>Save</Button>
      {msg && <Typography variant="caption" sx={{ color: msg.startsWith("saved") ? "#47654a" : "#6b2733" }}>{msg}</Typography>}
    </Box>
  );
};

export default function DocsView() {
  const [docName, setDocName] = useState(NAMES[0]);
  const [docs, setDocs] = useState(Object.fromEntries(NAMES.map((n) => [n, ""])));
  const [saved, setSaved] = useState(Object.fromEntries(NAMES.map((n) => [n, ""])));
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [genBusy, setGenBusy] = useState(false);
  const [genMsg, setGenMsg] = useState("");   // provenance line, or the plain reason it couldn't
  const [genWhat, setGenWhat] = useState(""); // live progress while it reads the mailbox
  const [genEv, setGenEv] = useState(null);   // the receipts: what was read, line by line
  // the generation is inspectable, not a vibe: poll its status while it runs so the button
  // narrates ("reading you@... — 240 sent so far"), then show the exact evidence it judged
  useEffect(() => {
    if (!genBusy) return undefined;
    const t = setInterval(async () => {
      try {
        const { data } = await api.get("/api/doc/generate/status");
        setGenWhat(data.what || "");
      } catch { /* status is a nicety, never an error */ }
    }, 1200);
    return () => clearInterval(t);
  }, [genBusy]);

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

  // A list you can see is worth more than a landing you have to go back to: switching
  // documents used to mean breadcrumb → grid → card, and these six are read together.
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "300px minmax(0,1fr)" },
      gap: 3, alignItems: "start" }}>

      <Box sx={{ position: { md: "sticky" }, top: { md: 62 } }}>
        <Typography sx={{ color: INK, fontWeight: 700, fontSize: 16, mb: 1.5 }}>Operator documents</Typography>
        {NAMES.map((n) => (
          <Box key={n} onClick={() => { setGenMsg(""); setGenEv(null); setDocName(n); }}
            sx={{ p: 1.4, mb: 0.75, borderRadius: 2, cursor: "pointer",
              bgcolor: n === docName ? "#fff" : "transparent",
              border: `1px solid ${n === docName ? "#d8cfbe" : "transparent"}`,
              boxShadow: n === docName ? "0 1px 3px rgba(30,50,38,.06)" : "none",
              "&:hover": { bgcolor: n === docName ? "#fff" : "#f4f1ec" } }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Box sx={{ display: "flex", opacity: n === docName ? 1 : .65 }}>{DOCS[n].icon}</Box>
              <Typography sx={{ ...mono, fontSize: 12, fontWeight: 600, color: INK, flex: 1 }}>{DOCS[n].label}</Typography>
              {n === docName && (
                <Box component="span" sx={{ px: 0.7, height: 17, display: "inline-flex", alignItems: "center",
                  borderRadius: 1.25, bgcolor: "#55697a", color: "#fff", fontSize: 9.5, fontWeight: 700 }}>open</Box>
              )}
            </Box>
            <Typography noWrap sx={{ fontSize: 11.5, color: FAINT, pt: 0.5 }}>{DOCS[n].blurb}</Typography>
          </Box>
        ))}
        <Box sx={{ mt: 2 }}><OwnerCard /></Box>
      </Box>

      <Box sx={{ minWidth: 0 }}>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, mb: 1.5 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ ...mono, color: INK, fontWeight: 700, fontSize: 17 }}>{DOCS[docName].label}</Typography>
            <Typography variant="body2" sx={{ color: FAINT, pt: 0.75 }}>{DOCS[docName].blurb}</Typography>
          </Box>
          {GEN[docName] && (
            <Button size="small" variant="outlined" disabled={genBusy} title={GEN[docName]}
              startIcon={genBusy ? <CircularProgress size={12} /> : null}
              onClick={async () => {
                setGenBusy(true); setGenMsg(""); setGenEv(null); setGenWhat("starting…");
                try {
                  const { data } = await api.post(`/api/doc/${docName}/generate`);
                  setGenMsg(`✓ ${data.detail}`); await load();
                  try { setGenEv((await api.get("/api/doc/generate/status")).data.evidence || null); } catch { /* receipts optional */ }
                } catch (e) { setGenMsg(e?.response?.data?.detail || "generation failed"); }
                setGenBusy(false); setGenWhat("");
              }}>{genBusy ? (genWhat || "Reading your mail…") : "Generate from history"}</Button>
          )}
          {docName === "learned" && (
            <Button size="small" variant="outlined" onClick={async () => {
              // consolidate now instead of waiting for the threshold; reload to show the rewrite
              try { await api.post("/api/learn/reflect"); await load(); } catch { /* no AI connected */ }
            }}>Reflect now</Button>
          )}
          <Button size="small" variant="contained" disableElevation disabled={docs[docName] === saved[docName]} onClick={save}>
            {docs[docName] === saved[docName] ? "Saved" : "Save"}
          </Button>
        </Box>
        {genMsg && GEN[docName] && (
          <Typography variant="caption" sx={{ display: "block", mb: 1,
            color: genMsg.startsWith("✓") ? "#47654a" : "#6b2733" }}>{genMsg}</Typography>
        )}
        {/* the receipts: exactly what the model read and what each line voted for - so the
            block in the doc is traceable back to your own mail, not a vibe */}
        {genEv?.length > 0 && GEN[docName] && (
          <Box sx={{ mb: 1.5, p: 1.25, bgcolor: "#fff", border: "1px solid #e1dcd5", borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700, letterSpacing: 1, display: "block", mb: 0.5 }}>
              WHAT IT READ — AND WHAT EACH LINE DID
            </Typography>
            <Box sx={{ maxHeight: 260, overflowY: "auto" }}>
              {genEv.map((l, i) => (
                <Typography key={i} variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap",
                  fontFamily: l.startsWith("  ") ? "'IBM Plex Mono', Consolas, monospace" : "inherit",
                  fontSize: l.startsWith("  ") ? 10.5 : 11.5, color: l.startsWith("  ") ? FAINT : INK }}>{l}</Typography>
              ))}
            </Box>
          </Box>
        )}
        <TextField fullWidth multiline minRows={22} maxRows={40} value={docs[docName]}
          onChange={(e) => setDocs({ ...docs, [docName]: e.target.value })} sx={{ bgcolor: "#fff" }}
          inputProps={{ style: { fontFamily: "'IBM Plex Mono', Consolas, monospace", fontSize: 12, lineHeight: 1.6, color: INK } }} />
        <Typography variant="caption" sx={{ color: FAINT, display: "block", pt: 1.25, lineHeight: 1.6 }}>
          Editing this changes the funnel on the very next message. Nothing here is sent anywhere —
          these files live beside your database.
        </Typography>
      </Box>
    </Box>
  );
}
