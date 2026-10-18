// A workflow run read back, step by step (taskuary/flow.py): the same top-to-bottom list as its editor - each step's status, time
// and headline, its output a click away - for the Reports list, a run's history and the run task's own card.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { ALERT, ALERT_INK, BORDER, DIM, FAINT, INK, PANEL2, ROLES, mono } from "./theme.jsx";
import api from "./api";
import { label as btnLabel } from "./buttons.js";
import { STATUS, recHead, runWords, secs } from "./workflowFlow.js";

const DOT = { repaired: "#a58bb5", ok: ROLES.done.solid, failed: ALERT, waiting: ROLES.working.solid, dry: "#8a9bab", skipped: "#cfc9bf" };
export const Dot = ({ status }) => <Box component="span" title={STATUS[status] || status}
  sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", flexShrink: 0, bgcolor: DOT[status] || "#cfc9bf" }} />;

// what a step came back with - from a test, or the last run
export function StepResult({ rec, compact }) {
  if (!rec) return null;
  return (
    <Box sx={{ mt: compact ? 0.5 : 0 }}>
      <Typography variant="caption" sx={{ display: "flex", alignItems: "center", gap: 0.75, color: rec.status === "failed" ? ALERT_INK : DIM, flexWrap: "wrap" }}>
        <Dot status={rec.status} /><Box component="span" sx={{ fontWeight: 600 }}>{STATUS[rec.status] || rec.status}</Box>
        {rec.ms != null && <span>· {secs(rec.ms)}</span>}
        {rec.rows != null && !/\brows?\b/.test(rec.head || "") && <span>· {rec.rows} row{rec.rows === 1 ? "" : "s"}</span>}
        {rec.head && rec.status !== "failed" && <span>· {rec.head}</span>}
      </Typography>
      {rec.error && <Typography variant="caption" sx={{ display: "block", color: ALERT_INK, mt: 0.25, whiteSpace: "pre-wrap" }}>{rec.error}</Typography>}
      {rec.why && rec.status !== "failed" && <Typography variant="caption" sx={{ display: "block", color: DIM, mt: 0.25 }}>why · {rec.why}</Typography>}
      {(rec.warnings || []).map((w) => <Typography key={w} variant="caption" sx={{ display: "block", color: "#7a5b2f", mt: 0.25 }}>⚠ {w}</Typography>)}
      {rec.body && <Box component="pre" sx={{ ...mono, fontSize: 11, lineHeight: 1.45, color: INK, whiteSpace: "pre-wrap", wordBreak: "break-word",
        bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1, p: 1, m: 0, mt: 0.6, maxHeight: compact ? 180 : 260, overflow: "auto" }}>{rec.body}</Box>}
    </Box>
  );
}

// a run read back: the same list, each step's status, time and headline, its output a click away, the fix when one failed - and
// every repair the run made to its own steps, with what broke, why, what changed, and Take it back (flow.undo)
export default function RunSteps({ steps, onFix, fixing, dense, repairs, sourceId, runId, onChanged }) {
  const [open, setOpen] = useState(null);
  const [undoing, setUndoing] = useState(false);
  const [said, setSaid] = useState("");
  if (!steps?.length) return null;
  const failed = steps.some((r) => r.status === "failed");
  // a step the APP broke (a sign-in expired, an AI missing - flow.app_fault) is fixed in that place, never by rewriting the steps
  const app = steps.find((r) => r.status === "failed" && r.app?.href)?.app;
  const takeBack = async () => {
    setUndoing(true); setSaid("");
    try { await api.post(`/api/workflows/${sourceId}/undo-repair`, { run_id: runId }); setSaid("The previous steps are back."); onChanged?.(); }
    catch (e) { setSaid(e?.response?.data?.detail || "It could not be taken back."); }
    finally { setUndoing(false); }
  };
  const live = (repairs || []).filter((x) => !x.undone);
  const shown = (v) => (typeof v === "string" ? v : JSON.stringify(v) ?? "");
  let n = 0;
  return (
    <Box data-tq-run-steps="" sx={{ mt: 0.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: failed ? ALERT_INK : DIM, fontWeight: 600, flex: 1, minWidth: 0 }}>{runWords(steps, true)}</Typography>
        {app && <Button size="small" variant="outlined" component="a" href={app.href} onClick={(e) => e.stopPropagation()}
          sx={{ fontSize: 12, py: 0.1 }} title={app.name}>{btnLabel("fix")}</Button>}
        {failed && !app && onFix && <Button size="small" variant="outlined" disabled={fixing} onClick={(e) => { e.stopPropagation(); onFix(); }}
          startIcon={fixing ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />} sx={{ fontSize: 12, py: 0.1 }}>{btnLabel("fix")}</Button>}
      </Box>
      {(repairs || []).map((x, k) => (
        <Box key={k} data-tq-self-repair="" sx={{ mb: 0.6, px: 1, py: 0.6, borderRadius: 1, border: "1px solid #ddd0e5", bgcolor: "#f7f3f9" }}>
          <Typography variant="caption" sx={{ display: "flex", alignItems: "baseline", gap: 1, color: INK, flexWrap: "wrap" }}>
            <Box component="span" sx={{ fontWeight: 600 }}>{x.undone ? "Taken back" : "Repaired itself"} · {x.label}</Box>
            <Box component="span" sx={{ color: DIM, flex: 1, minWidth: 160 }}>{x.why}</Box>
            {!x.undone && x === live[live.length - 1] && sourceId != null && runId != null &&
              <Button size="small" disabled={undoing} onClick={(e) => { e.stopPropagation(); takeBack(); }} sx={{ fontSize: 11.5, py: 0, minWidth: 0 }}>
                {btnLabel("take_back")}</Button>}
          </Typography>
          <Typography variant="caption" sx={{ display: "block", color: FAINT }}>what broke · {x.error}</Typography>
          {(x.diff || []).flatMap((d) => (d.keys || []).map((c) => (
            <Typography key={`${d.id}-${c.key}`} variant="caption" sx={{ display: "block", color: DIM, ...mono, fontSize: 10.5, wordBreak: "break-word" }}>
              {d.label || d.id} · {c.key}: {shown(c.was)} → {shown(c.now)}</Typography>)))}
        </Box>
      ))}
      {said && <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.5 }}>{said}</Typography>}
      {steps.map((r, i) => (
        <Box key={`${r.id}-${i}`} sx={{ display: "flex", gap: 1 }}>
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", width: 10, flexShrink: 0, pt: 0.75 }}>
            <Dot status={r.status} />
            {i < steps.length - 1 && <Box sx={{ flex: 1, width: "1px", bgcolor: BORDER, mt: 0.4 }} />}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0, pb: dense ? 0.4 : 0.6 }}>
            <Typography variant="caption" onClick={(e) => { e.stopPropagation(); setOpen(open === i ? null : i); }}
              sx={{ display: "flex", gap: 0.75, alignItems: "baseline", color: INK, cursor: r.body || r.error ? "pointer" : "default", minWidth: 0, lineHeight: 1.6 }}>
              <Box component="span" sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{r.status === "repaired" ? "↻" : `${++n}.`} {r.label}</Box>
              <Box component="span" sx={{ color: r.status === "failed" ? ALERT_INK : DIM, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
                {recHead(r)}</Box>
              <Box component="span" sx={{ color: FAINT, ml: "auto", whiteSpace: "nowrap", ...mono, fontSize: 10.5 }}>{r.status === "skipped" ? "skipped" : secs(r.ms)}</Box>
            </Typography>
            {open === i && <Box onClick={(e) => e.stopPropagation()}><StepResult rec={r} compact /></Box>}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export { RunSteps };
