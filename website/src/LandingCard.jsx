// HOW A CODING TASK'S BRANCH LANDS (the owner, 2026-11-06: "rebase fast forward is a question on each one and they can ask"): in its Close
// out, the branch's diff against where the task started - files changed, + and - - with the whole diff a press away, then the one question.
// The agent's own pick (propose_land) is marked; nothing lands until the owner answers. A conflict lands nothing: the agent gets it.
// ...IN THE CODING CHAT IT IS A CARD OF ITS OWN (`inChat`, GeneralWorkspace.jsx), and the whole diff opens in the code viewer, a file a fold (DiffView);
// while it waits to land each part can be marked Keep or Revert, and the reverted ones are taken out of the branch first (landing.revert)
// ...THE DIFF OPENS LIKE A PULL REQUEST, the whole window wide (the owner, 2026-11-08): the file list on the left, the diffs on the right - inside
// a turn of the chat it was a column too narrow for either. The card's own list folds the generated files as that view does (diffView `generated`)
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Dialog, DialogContent, IconButton, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { landingFiles, landingWords } from "./landing.js";
import { hunkText, parseUnified } from "./diffView.js";
import DiffView from "./DiffView.jsx";
import { plural } from "./timeWords.js";
import { ACCENT, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const btn = { minHeight: 32, py: 0, px: 1.4, fontSize: 12.5, textTransform: "none" };

const FileLine = ({ f }) => (
  <Typography variant="caption" sx={{ ...mono, display: "block", color: DIM, fontSize: 11 }} noWrap>
    <Box component="span" sx={{ color: "#47654a" }}>+{f.plus}</Box> <Box component="span" sx={{ color: "#7a2f3c" }}>-{f.minus}</Box> {f.path}
  </Typography>);
export const SHOWN = 8;

export default function LandingCard({ taskId, onChanged, onState, inChat = false }) {
  const [s, setS] = useState(null), [diff, setDiff] = useState(null), [busy, setBusy] = useState(""), [said, setSaid] = useState(""),
    [err, setErr] = useState(""), [sure, setSure] = useState(false), [marks, setMarks] = useState({}), [open, setOpen] = useState(false),
    [diffErr, setDiffErr] = useState("");
  const load = () => api.get(`/api/tasks/${taskId}/landing`).then(({ data }) => { setS(data?.data || null); onState?.(data?.data || null); })
    .catch(() => { setS(null); onState?.(null); });
  useEffect(() => { setS(null); setDiff(null); setOpen(false); setSaid(""); setErr(""); setSure(false); setMarks({}); load(); }, [taskId]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!s || (!s.ask && !s.landed && !s.changed)) return null;
  const w = landingWords(s);
  // THE DIFF OPENS AT THE PRESS (the owner, 2026-11-09: it waited for the read, and the button felt dead for a second): the window first, saying
  // it is reading the changes, then the diff into it - or why it could not be read
  const readDiff = () => { setDiffErr(""); return api.get(`/api/tasks/${taskId}/landing`, { params: { full: true } }).then(({ data }) => setDiff(data?.data?.diff || ""))
    .catch((e) => { setDiff(null); setDiffErr(e?.response?.data?.detail || "The changes could not be read - close this and try again."); }); };
  const seeDiff = () => { if (open) return setOpen(false); setOpen(true); setDiff(null); readDiff(); };
  const answer = async (how) => {
    if (how === "discard" && !sure) { setSure(true); return; }
    setBusy(how); setErr(""); setSure(false);
    try { const { data } = await api.post(`/api/tasks/${taskId}/landing`, { how }); setSaid(data?.says || ""); load(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not land"); }
    setBusy("");
  };
  // REVIEW: only on the agent's own branch while it waits to land - the base is every agent's, and what landed is history
  const files = diff ? parseUnified(diff) : [], { src, gen } = landingFiles(s.files);
  const reviewing = !!s.ask && !!s.own;
  const picked = Object.entries(marks).filter(([, v]) => v === "revert").map(([k]) => k);
  const revert = async () => {
    const parts = picked.map((k) => { const at = k.lastIndexOf("#"), path = k.slice(0, at), index = +k.slice(at + 1);
      const h = files.find((f) => f.path === path)?.hunks.find((x) => x.index === index); return h ? { path, index, text: hunkText(h) } : null; }).filter(Boolean);
    setBusy("revert"); setErr("");
    try { const { data } = await api.post(`/api/tasks/${taskId}/landing/revert`, { parts }); setSaid(data?.says || ""); setMarks({}); load(); readDiff(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Nothing was reverted"); }
    setBusy("");
  };
  return (
    <Box data-tq-landing="" sx={inChat ? { my: 1.5, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff" }
      : { mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
      <Typography sx={{ color: ACCENT, fontSize: 9.5, fontWeight: 600, letterSpacing: "1.5px", mb: 0.4 }}>LAND THE BRANCH</Typography>
      <Typography variant="body2" sx={{ color: INK }}>
        <Box component="span" sx={{ ...mono, fontWeight: 600 }}>{s.branch}</Box>
        {s.own ? <> into <Box component="span" sx={mono}>{s.base}</Box></> : null}
        <Box component="span" sx={{ color: DIM }}> · {w.stat}</Box>
      </Typography>
      {s.shared && <Typography variant="caption" data-tq-landing-shared="" sx={{ display: "block", color: FAINT }}>{w.shared}</Typography>}
      {!!s.files?.length && (
        <Box sx={{ mt: 0.5 }}>
          {src.slice(0, SHOWN).map((f) => <FileLine key={f.path} f={f} />)}
          {src.length > SHOWN && <Typography variant="caption" sx={{ display: "block", color: FAINT }}>and {src.length - SHOWN} more</Typography>}
          {!!gen.length && <Box component="details" data-tq-landing-generated="" sx={{ "& > summary": { cursor: "pointer", color: FAINT, fontSize: 11 } }}>
            <summary>Generated · {plural(gen.length, "file")}</summary>{gen.map((f) => <FileLine key={f.path} f={f} />)}</Box>}
          <Button size="small" sx={{ ...btn, minHeight: 0, p: 0, mt: 0.3, color: DIM, display: "flex" }} data-tq-landing-diff="" onClick={seeDiff}>
            {reviewing ? "See the diff · review it" : "See the diff"}</Button>
        </Box>)}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth={false} data-tq-landing-dialog=""
        slotProps={{ paper: { sx: { width: "min(1400px, 96vw)", height: "90vh", m: 1 } } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
          <Typography variant="body2" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>
            <Box component="span" sx={{ ...mono, fontWeight: 600 }}>{s.branch}</Box>
            {s.own ? <> into <Box component="span" sx={mono}>{s.base}</Box></> : null}
            <Box component="span" sx={{ color: DIM }}> · {w.stat}</Box></Typography>
          <IconButton size="small" aria-label="Close the diff" onClick={() => setOpen(false)}><CloseIcon fontSize="small" /></IconButton>
        </Box>
        <DialogContent sx={{ p: 2 }}>
          {reviewing && <Typography variant="caption" sx={{ display: "block", color: FAINT, mb: 0.75 }}>
            Mark a part Revert to take it out of {s.branch} before it lands - one commit on the branch, nothing else touched.</Typography>}
          {diff === null && !diffErr && <Typography variant="body2" data-tq-diff-loading="" sx={{ color: DIM, display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={14} color="inherit" />Loading the changes…</Typography>}
          {diffErr && <Typography variant="body2" data-tq-diff-error="" sx={{ color: "#7a2f3c" }}>{diffErr}</Typography>}
          {diff !== null && <DiffView files={files} marks={reviewing ? marks : null} onMark={reviewing ? (k, m) => setMarks((x) => ({ ...x, [k]: m })) : null} />}
          {reviewing && !!picked.length && <Button size="small" variant="outlined" disabled={!!busy} data-tq-landing-revert="" sx={{ ...btn, mt: 0.75, color: "#7a2f3c", borderColor: BORDER }}
            startIcon={busy === "revert" ? <CircularProgress size={12} color="inherit" /> : null} onClick={revert}>
            Revert {plural(picked.length, "marked part")}</Button>}
        </DialogContent>
      </Dialog>
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
