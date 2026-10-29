// "Describe the report / workflow you want": one box that asks the composer for a draft, asks back what it will not guess,
// and hands the draft on. Reports draws it on its lists and the new workflow's page; New draws it on its Report and
// Workflow tabs (the owner, 2026-10-15), and hands the draft to Reports to open.
import React, { useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Tooltip, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import { useVerbs } from "./actionRow.js";
import { label as btnLabel } from "./buttons.js";
import { openAppLink } from "./appLinks.js";
import { NL } from "./sourceShape.js";
import { DASH } from "./words.js";
import { PANEL2, DIM, FAINT, INK, ACCENT2, card } from "./theme.jsx";
import BuilderAsks from "./BuilderAsks.jsx";
import { answerState, answersFor, asksOf } from "./builderAsks.js";

export default function Composer({ onDraft, kind = "report", initial = "" }) {
  const [ask, setAsk] = useState(initial);   // the words the Assistant wrote it up with (concierge._new)
  const [busy, setBusy] = useState("");      // "build" | "answer": which press is running, so its own button spins
  const [out, setOut] = useState(null);
  const [answers, setAnswers] = useState({});
  const running = useRef(false), last = useRef(undefined);

  // ANSWER & BUILD LOOKED FROZEN (the owner, 2026-10-29): the press now spins and says so, a second press while it runs is
  // dropped, and a miss keeps the questions and their answers on screen with Try again - it used to wipe them with the error
  const go = async (withAnswers) => {
    if (running.current) return;
    running.current = true; last.current = withAnswers; setBusy(withAnswers ? "answer" : "build");
    const keep = (o, e) => ({ ...e, ...(withAnswers && !e.questions ? { asks: o?.asks, questions: o?.questions } : {}) });
    try {
      const endpoint = kind === "workflow" ? "/api/workflows/compose" : kind === "dashboard" ? "/api/dashboards/compose" : "/api/reports/compose";
      const { data } = await api.post(endpoint, { ask, answers: withAnswers || undefined });
      setOut((o) => data.error ? keep(o, data) : data);
      if (data.config && !data.error) { onDraft(data.config, data); setAsk(""); setAnswers({}); setOut(null); }
    } catch (e) {
      const why = e?.response?.data?.detail;
      setOut((o) => keep(o, { error: typeof why === "string" && why ? why : "The builder could not be reached." }));
    }
    running.current = false; setBusy("");
  };

  // A MISS THAT NAMES ITS FIX (compose.py: no AI connected, a connection switched off) puts that fix on the row - the sentence
  // alone said where to go and gave nothing to press (2026-10-17). A miss the owner fixes by asking again leaves Build it as the move.
  const fix = out?.error && out?.fix?.href ? out.fix : null;
  useVerbs(`composer:${kind}`, fix ? [{ id: `composer:${kind}:fix`, group: "decide", tone: "s", label: fix.label, run: () => openAppLink(fix.href) }] : [], !!fix);
  const asks = asksOf(out), can = answerState(asks, answers, busy);
  return (
    <Box sx={{ ...card, p: 1.5, mb: 2, bgcolor: PANEL2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mb: 0.9 }}>
        <AutoAwesomeIcon sx={{ fontSize: 15, color: ACCENT2 }} />
        <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>
          {kind === "workflow" ? "Describe the workflow you want" : kind === "dashboard" ? DASH.describe : "Describe the report you want"}
        </Typography>
      </Box>
      <TextField fullWidth size="small" multiline minRows={2} value={ask} disabled={busy}
        sx={{ bgcolor: "#fff" }}
        placeholder={kind === "dashboard" ? DASH.example : kind === "workflow"
          ? "Every Monday at 8, check Intacct for active employees that share a name, and open a task for finance per pair."
            + NL + "Every weekday at 7, read yesterday's failed imports and open a task for each one that did not retry."
          : "Read C:/exports/daily-*.csv every morning, total the units by site and flag anything under 70."
            + NL + "Every Monday, list the AP bills from Intacct due in the next 30 days and call out anything over 10k."}
        onChange={(e) => setAsk(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && ask.trim()) go(); }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.9 }}>
        <Button size="small" variant="contained" disableElevation disabled={!!busy || !ask.trim()}
          sx={{ whiteSpace: "nowrap", flexShrink: 0 }}
          onClick={() => go()} startIcon={busy === "build" ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />}>
          {busy === "build" ? "Working it out…" : "Build it"}
        </Button>
        <Typography sx={{ fontSize: 11, color: FAINT }}>
          It can only use connections you have set up — and it will ask rather than guess.
        </Typography>
      </Box>

      {/* ...and in the message itself (owner-approved, 2026-10-21: every "no AI" line carries its Connect an AI) */}
      {out?.error && <Alert severity="warning" sx={{ mt: 1.25, fontSize: 12.5, alignItems: "center" }}
        action={fix ? <Button size="small" variant="outlined" data-tq-composer-fix="" sx={{ whiteSpace: "nowrap" }}
          onClick={() => openAppLink(fix.href)}>{fix.label}</Button>
          : <Button size="small" color="inherit" data-tq-composer-retry="" disabled={!!busy} sx={{ whiteSpace: "nowrap" }}
            onClick={() => go(last.current)}>{btnLabel("try_again")}</Button>}>{out.error}</Alert>}
      {/* THE WORKFLOW DOOR, ASKED FOR A REPORT (the owner, 2026-10-18): said plainly, with the report drafted from the same reads */}
      {out?.verdict === "report" && out.report && <Alert severity="info" data-tq-report-verdict="" sx={{ mt: 1.25, fontSize: 12.5 }}
        action={<Button size="small" color="inherit" sx={{ whiteSpace: "nowrap" }}
          onClick={() => { onDraft(out.report, { ...out, explain: "Drafted as a report from what you described." }); setAsk(""); setOut(null); }}>{btnLabel("make_report")}</Button>}>
        {out.explain}</Alert>}

      {/* it did not know something. Better here than as a silently wrong WHERE clause. */}
      {asks.length > 0 && (
        <Box sx={{ mt: 1.25, display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ fontSize: 11.5, color: DIM, fontWeight: 600 }}>
            A couple of things it will not guess at:
          </Typography>
          <BuilderAsks asks={asks} answers={answers} setAnswers={setAnswers} disabled={busy} />
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {/* a disabled button hears no hover, so the span carries the why */}
            <Tooltip title={can.hint} placement="top-start"><span>
              <Button size="small" variant="contained" disableElevation disabled={can.disabled} data-tq-answer-build=""
                aria-busy={busy === "answer"} onClick={() => go(answersFor(asks, answers))}
                startIcon={busy === "answer" ? <CircularProgress size={12} sx={{ color: "inherit" }} /> : null}>
                {busy === "answer" ? "Building…" : "Answer & build"}</Button>
            </span></Tooltip>
            {busy === "answer" ? <Typography role="status" sx={{ fontSize: 11, color: FAINT }}>Building it from your answers…</Typography>
              : can.left > 0 && !can.disabled && <Typography sx={{ fontSize: 11, color: FAINT }}>{can.hint}.</Typography>}
          </Box>
        </Box>
      )}
    </Box>
  );
}
