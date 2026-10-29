// WHAT THE BUILDER WILL NOT GUESS AT, each asked with its answer's own control (builderAsks.js): a repository from the list the
// New card's coding picker reads (/api/repos), a schedule on the editors' own SchedulePicker, a choice as a select, anything
// else a text box. Shared by the describe box (Composer) and the source cards' "let AI fill this in" (ReportsView).
import React, { useEffect, useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import api from "./api";
import { SchedulePicker, scheduleWords } from "./WorkflowEditor.jsx";
import { OTHER, pickRows } from "./builderAsks.js";
import { BORDER, FAINT, INK } from "./theme.jsx";

const sel = { fontSize: 12.5, padding: "6px 6px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "#fff", color: INK, minWidth: 240, maxWidth: "100%" };
const Q = ({ a, children }) => (
  <Box data-tq-ask={a.kind}>
    <Typography sx={{ fontSize: 12, color: INK, mb: 0.4 }}>{a.q}</Typography>
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>{children}</Box>
  </Box>
);

function Pick({ a, rows, value, set, disabled, other }) {
  const [typing, setTyping] = useState(false);
  return (
    <Q a={a}>
      <select aria-label={a.q} value={typing ? OTHER : value} disabled={disabled} style={sel}
        onChange={(e) => { const v = e.target.value; setTyping(v === OTHER); set(v === OTHER ? "" : v); }}>
        <option value="">choose…</option>
        {pickRows(rows, typing ? "" : value).map((r) => <option key={r} value={r}>{r}</option>)}
        <option value={OTHER}>{other}</option>
      </select>
      {typing && <TextField size="small" autoFocus value={value} disabled={disabled} placeholder={a.kind === "repo" ? "owner/name" : ""}
        sx={{ bgcolor: "#fff", flex: 1, minWidth: 180 }} onChange={(e) => set(e.target.value)} />}
    </Q>
  );
}

function Schedule({ a, set, disabled }) {
  const [sched, setSched] = useState({ mode: "daily", at: "08:00", days: [1], day: 1, minutes: 60, cron: "" });
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (touched) set(scheduleWords(sched)); }, [sched, touched]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Q a={a}>
      <Box sx={disabled ? { pointerEvents: "none", opacity: 0.6 } : null}>
        <SchedulePicker sched={sched} setSched={(f) => { setTouched(true); setSched(f); }} />
      </Box>
      {!touched && <Typography variant="caption" sx={{ color: FAINT }}>not chosen yet</Typography>}
    </Q>
  );
}

export default function BuilderAsks({ asks, answers, setAnswers, disabled }) {
  const wantsRepos = asks.some((a) => a.kind === "repo");
  const [repos, setRepos] = useState(null);
  useEffect(() => {
    if (!wantsRepos || repos) return undefined;
    let live = true;
    api.get("/api/repos").then(({ data }) => live && setRepos((data.data || []).map((r) => r.repo))).catch(() => live && setRepos([]));
    return () => { live = false; };
  }, [wantsRepos, repos]);
  const set = (q) => (v) => setAnswers((x) => ({ ...x, [q]: v }));
  return asks.map((a) => {
    const value = answers[a.q] || "";
    // a repository question with no list to pick from (none known yet, or the list failed) is asked as text, as it always was
    if (a.kind === "repo" && repos === null) return <Q key={a.q} a={a}><select aria-label={a.q} disabled style={sel}><option>loading the list…</option></select></Q>;
    if (a.kind === "repo" && repos.length) return <Pick key={a.q} a={a} rows={repos} value={value} set={set(a.q)} disabled={disabled} other="Another repository…" />;
    if (a.kind === "choice") return <Pick key={a.q} a={a} rows={a.options} value={value} set={set(a.q)} disabled={disabled} other="Something else…" />;
    if (a.kind === "schedule") return <Schedule key={a.q} a={a} set={set(a.q)} disabled={disabled} />;
    return <TextField key={a.q} size="small" fullWidth label={a.q} sx={{ bgcolor: "#fff" }} disabled={disabled} data-tq-ask="text"
      value={value} onChange={(e) => set(a.q)(e.target.value)} />;
  });
}
