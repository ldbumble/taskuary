// HOW A CODING TASK'S BRANCH LANDS (the owner, 2026-11-06: "rebase fast forward is a question on each one and they can ask"): in its Close
// out, the branch's diff against where the task started - files changed, + and - - with the whole diff a press away, then the one question.
// The agent's own pick (propose_land) is marked; nothing lands until the owner answers. A conflict lands nothing: the agent gets it.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { landingWords } from "./landing.js";
import { plural } from "./timeWords.js";
import { ACCENT, BORDER, DIM, FAINT, INK, PANEL2, mono } from "./theme.jsx";

const btn = { minHeight: 32, py: 0, px: 1.4, fontSize: 12.5, textTransform: "none" };

export default function LandingCard({ taskId, onChanged }) {
  const [s, setS] = useState(null), [diff, setDiff] = useState(null), [busy, setBusy] = useState(""), [said, setSaid] = useState(""),
    [err, setErr] = useState(""), [sure, setSure] = useState(false);
  const load = () => api.get(`/api/tasks/${taskId}/landing`).then(({ data }) => setS(data?.data || null)).catch(() => setS(null));
  useEffect(() => { setS(null); setDiff(null); setSaid(""); setErr(""); setSure(false); load(); }, [taskId]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!s || (!s.ask && !s.landed && !s.changed)) return null;
  const w = landingWords(s);
  const seeDiff = () => diff !== null ? setDiff(null)
    : api.get(`/api/tasks/${taskId}/landing`, { params: { full: true } }).then(({ data }) => setDiff(data?.data?.diff || "")).catch(() => setDiff(""));
  const answer = async (how) => {
    if (how === "discard" && !sure) { setSure(true); return; }
    setBusy(how); setErr(""); setSure(false);
    try { const { data } = await api.post(`/api/tasks/${taskId}/landing`, { how }); setSaid(data?.says || ""); load(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not land"); }
    setBusy("");
  };
  return (
    <Box data-tq-landing="" sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
      <Typography sx={{ color: ACCENT, fontSize: 9.5, fontWeight: 600, letterSpacing: "1.5px", mb: 0.4 }}>LAND THE BRANCH</Typography>
      <Typography variant="body2" sx={{ color: INK }}>
        <Box component="span" sx={{ ...mono, fontWeight: 600 }}>{s.branch}</Box>
        {s.own ? <> into <Box component="span" sx={mono}>{s.base}</Box></> : null}
        <Box component="span" sx={{ color: DIM }}> · {w.stat}</Box>
      </Typography>
      {!!s.files?.length && (
        <Box sx={{ mt: 0.5 }}>
          {s.files.slice(0, 8).map((f) => (
            <Typography key={f.path} variant="caption" sx={{ ...mono, display: "block", color: DIM, fontSize: 11 }} noWrap>
              <Box component="span" sx={{ color: "#47654a" }}>+{f.plus}</Box> <Box component="span" sx={{ color: "#7a2f3c" }}>-{f.minus}</Box> {f.path}
            </Typography>))}
          {s.files.length > 8 && <Typography variant="caption" sx={{ color: FAINT }}>and {s.files.length - 8} more</Typography>}
          <Button size="small" sx={{ ...btn, minHeight: 0, p: 0, mt: 0.3, color: DIM }} data-tq-landing-diff="" onClick={seeDiff}>
            {diff !== null ? "Hide the diff" : "See the diff"}</Button>
        </Box>)}
      {diff !== null && (
        <Box component="pre" sx={{ ...mono, fontSize: 11, lineHeight: 1.45, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1, p: 1,
          mt: 0.5, maxHeight: 360, overflow: "auto", whiteSpace: "pre" }}>{diff || "No diff to show."}</Box>)}
      {s.ask && <>
        <Typography variant="body2" sx={{ mt: 0.9, color: INK, fontWeight: 600 }}>How should it land?</Typography>
        {w.proposal && <Typography variant="caption" data-tq-landing-proposal="" sx={{ display: "block", color: DIM }}>{w.proposal}</Typography>}
        <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 0.7 }}>
          {s.answers.map((a) => (
            <Button key={a.how} size="small" disableElevation disabled={!!busy} data-tq-land={a.how}
              variant={s.proposal?.how === a.how ? "contained" : "outlined"}
              sx={{ ...btn, ...(a.how === "discard" ? { color: "#7a2f3c", borderColor: BORDER } : s.proposal?.how === a.how ? {} : { color: INK, borderColor: BORDER }) }}
              startIcon={busy === a.how ? <CircularProgress size={12} color="inherit" /> : null}
              onClick={() => answer(a.how)}>{a.how === "discard" && sure ? `Yes, discard ${plural(s.ahead, "commit")}` : a.label}</Button>))}
          {sure && <Button size="small" sx={{ ...btn, color: DIM }} onClick={() => setSure(false)}>Keep it</Button>}
        </Box>
        <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.5 }}>{w.hint}</Typography>
      </>}
      {said && <Typography variant="body2" sx={{ mt: 0.7, color: "#47654a" }}>{said}</Typography>}
      {!said && s.landed && <Typography variant="body2" sx={{ mt: 0.7, color: "#47654a" }}>✓ {w.landed}</Typography>}
      {err && <Typography variant="body2" sx={{ mt: 0.7, color: "#7a2f3c" }}>{err}</Typography>}
    </Box>
  );
}
