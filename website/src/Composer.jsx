// "Describe the report / workflow you want": one box that asks the composer for a draft, asks back what it will not guess,
// and hands the draft on. Reports draws it on its lists and the new workflow's page; New draws it on its Report and
// Workflow tabs (the owner, 2026-10-15), and hands the draft to Reports to open.
import React, { useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import { useVerbs } from "./actionRow.js";
import { openAppLink } from "./appLinks.js";
import { NL } from "./sourceShape.js";
import { PANEL2, DIM, FAINT, INK, ACCENT2, card } from "./theme.jsx";

export default function Composer({ onDraft, kind = "report" }) {
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [answers, setAnswers] = useState({});

  const go = async (withAnswers) => {
    setBusy(true);
    try {
      const endpoint = kind === "workflow" ? "/api/workflows/compose" : "/api/reports/compose";
      const { data } = await api.post(endpoint, { ask, answers: withAnswers || undefined });
      setOut(data);
      if (data.config) { onDraft(data.config, data); setAsk(""); setAnswers({}); setOut(null); }
    } catch (e) { setOut({ error: e?.response?.data?.detail || "the composer could not be reached" }); }
    setBusy(false);
  };

  // A MISS THAT NAMES ITS FIX (compose.py: no AI connected, a connection switched off) puts that fix on the row - the sentence
  // alone said where to go and gave nothing to press (2026-10-17). A miss the owner fixes by asking again leaves Build it as the move.
  const fix = out?.error && out?.fix?.href ? out.fix : null;
  useVerbs(`composer:${kind}`, fix ? [{ id: `composer:${kind}:fix`, group: "decide", tone: "s", label: fix.label, run: () => openAppLink(fix.href) }] : [], !!fix);
  const answered = out?.questions?.length && out.questions.every((q) => String(answers[q] || "").trim());
  return (
    <Box sx={{ ...card, p: 1.5, mb: 2, bgcolor: PANEL2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mb: 0.9 }}>
        <AutoAwesomeIcon sx={{ fontSize: 15, color: ACCENT2 }} />
        <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>
          {kind === "workflow" ? "Describe the workflow you want" : "Describe the report you want"}
        </Typography>
      </Box>
      <TextField fullWidth size="small" multiline minRows={2} value={ask} disabled={busy}
        sx={{ bgcolor: "#fff" }}
        placeholder={kind === "workflow"
          ? "Every Monday at 8, check Intacct for active employees that share a name, and open a task for finance per pair."
            + NL + "Every weekday at 7, read yesterday's failed imports and open a task for each one that did not retry."
          : "Read C:/exports/daily-*.csv every morning, total the units by site and flag anything under 70."
            + NL + "Every Monday, list the AP bills from Intacct due in the next 30 days and call out anything over 10k."}
        onChange={(e) => setAsk(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && ask.trim()) go(); }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.9 }}>
        <Button size="small" variant="contained" disableElevation disabled={busy || !ask.trim()}
          sx={{ whiteSpace: "nowrap", flexShrink: 0 }}
          onClick={() => go()} startIcon={busy ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />}>
          {busy ? "Working it out…" : "Build it"}
        </Button>
        <Typography sx={{ fontSize: 11, color: FAINT }}>
          It can only use connections you have set up — and it will ask rather than guess.
        </Typography>
      </Box>

      {out?.error && <Alert severity="warning" sx={{ mt: 1.25, fontSize: 12.5 }}>{out.error}</Alert>}
      {/* THE WORKFLOW DOOR, ASKED FOR A REPORT (the owner, 2026-10-18): said plainly, with the report drafted from the same reads */}
      {out?.verdict === "report" && out.report && <Alert severity="info" data-tq-report-verdict="" sx={{ mt: 1.25, fontSize: 12.5 }}
        action={<Button size="small" color="inherit" sx={{ whiteSpace: "nowrap" }}
          onClick={() => { onDraft(out.report, { ...out, explain: "Drafted as a report from what you described." }); setAsk(""); setOut(null); }}>Make it a report</Button>}>
        {out.explain}</Alert>}

      {/* it did not know something. Better here than as a silently wrong WHERE clause. */}
      {out?.questions?.length > 0 && (
        <Box sx={{ mt: 1.25, display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ fontSize: 11.5, color: DIM, fontWeight: 600 }}>
            A couple of things it will not guess at:
          </Typography>
          {out.questions.map((qq) => (
            <TextField key={qq} size="small" fullWidth label={qq} sx={{ bgcolor: "#fff" }}
              value={answers[qq] || ""} onChange={(e) => setAnswers({ ...answers, [qq]: e.target.value })} />
          ))}
          <Button size="small" variant="contained" disableElevation disabled={busy || !answered}
            onClick={() => go(answers)} sx={{ alignSelf: "flex-start" }}>Answer & build</Button>
        </Box>
      )}
    </Box>
  );
}
