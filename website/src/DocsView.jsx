// Operator documents, Stripe-style like Settings: a landing of doc cards, drilling into
// an editor page with a Docs breadcrumb and a horizontal tab bar to switch documents.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import HistoryEduIcon from "@mui/icons-material/HistoryEdu";
import PsychologyIcon from "@mui/icons-material/Psychology";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import RateReviewIcon from "@mui/icons-material/RateReview";
import api from "./api";
import { FAINT, INK } from "./theme.jsx";
import { Crumb, UnderTabs, LandingCard } from "./ui.jsx";

const DOCS = {
  soul: { label: "SOUL.md", icon: <AutoStoriesIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
    blurb: "The funnel's constitution AND the base system prompt: what counts as a task, how we respond, escalation rules, the repository map. Injected into every triage and every draft." },
  triage: { label: "TRIAGE.md", icon: <FilterAltIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
    blurb: "The triage brain's instructions — what makes a message a task, a question, or FYI, and which way to lean when torn. Ships as a sensible default; edit it to reshape every verdict. Keep the JSON answer line, or triage falls back to keyword heuristics. Blank it to restore the default." },
  style: { label: "STYLE.md", icon: <RateReviewIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
    blurb: "How you write replies — greeting, tone, length, phrasing — layered onto SOUL.md for every draft. Write it yourself, or Generate from history distills it from your last three months of sent mail; your own lines outside the marked block always survive a regenerate." },
  coder: { label: "CODER.md", icon: <SmartToyIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
    blurb: "The coding agent's rules, stacked on top of SOUL.md for every coder run: how to close out, what it may fix itself, what must escalate, and how to answer the sender." },
  digest: { label: "DIGEST.md", icon: <HistoryEduIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
    blurb: "Your morning brief — what's in flight, who waits on whom. Written by the Morning digest report: the same brief lands on your Timeline daily, its prompt is edited on the Reports tab (that decides what goes in here), and deleting that report turns it off." },
  learned: { label: "LEARNED.md", icon: <PsychologyIcon sx={{ fontSize: 19, color: "#2f6b4f" }} />,
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
    <Box sx={{ mb: 2.5, p: 1.75, bgcolor: "#fff", border: "1px solid #dce1d8", borderRadius: 2,
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
      {msg && <Typography variant="caption" sx={{ color: msg.startsWith("saved") ? "#4d6b3f" : "#8f4a41" }}>{msg}</Typography>}
    </Box>
  );
};

export default function DocsView() {
  const [docName, setDocName] = useState(null);   // null = landing
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

  if (docName) {
    return (
      <Box sx={{ maxWidth: 1100, mx: "auto" }}>
        <Crumb section="Docs" onBack={() => setDocName(null)} title={DOCS[docName].label} />
        <UnderTabs tabs={NAMES.map((n) => DOCS[n].label)} value={DOCS[docName].label}
          onChange={(label) => { setGenMsg(""); setDocName(NAMES.find((n) => DOCS[n].label === label)); }} />
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, mb: 1.5 }}>
          <Typography variant="body2" sx={{ color: FAINT, flex: 1 }}>{DOCS[docName].blurb}</Typography>
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
            color: genMsg.startsWith("✓") ? "#4d6b3f" : "#8f4a41" }}>{genMsg}</Typography>
        )}
        {/* the receipts: exactly what the model read and what each line voted for - so the
            block in the doc is traceable back to your own mail, not a vibe */}
        {genEv?.length > 0 && GEN[docName] && (
          <Box sx={{ mb: 1.5, p: 1.25, bgcolor: "#fff", border: "1px solid #dce1d8", borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: "#1f6b64", fontWeight: 700, letterSpacing: 1, display: "block", mb: 0.5 }}>
              WHAT IT READ — AND WHAT EACH LINE DID
            </Typography>
            <Box sx={{ maxHeight: 260, overflowY: "auto" }}>
              {genEv.map((l, i) => (
                <Typography key={i} variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap",
                  fontFamily: l.startsWith("  ") ? "'JetBrains Mono', Consolas, monospace" : "inherit",
                  fontSize: l.startsWith("  ") ? 10.5 : 11.5, color: l.startsWith("  ") ? FAINT : INK }}>{l}</Typography>
              ))}
            </Box>
          </Box>
        )}
        <TextField fullWidth multiline minRows={18} maxRows={32} value={docs[docName]}
          onChange={(e) => setDocs({ ...docs, [docName]: e.target.value })} sx={{ bgcolor: "#fff" }}
          inputProps={{ style: { fontFamily: "'JetBrains Mono', Consolas, monospace", fontSize: 12, lineHeight: 1.55, color: INK } }} />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1160, mx: "auto" }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>Operator documents</Typography>
      <OwnerCard />
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, gap: 3 }}>
        {NAMES.map((n) => (
          <LandingCard key={n} icon={DOCS[n].icon} title={DOCS[n].label} desc={DOCS[n].blurb}
            onOpen={() => setDocName(n)} />
        ))}
      </Box>
    </Box>
  );
}
