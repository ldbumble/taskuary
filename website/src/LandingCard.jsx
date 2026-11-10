// HOW A CODING TASK'S BRANCH LANDS (the owner, 2026-11-06: "rebase fast forward is a question on each one and they can ask"): in its Close
// out, the branch's diff against where the task started - files changed, + and - - with the whole diff a press away, then the one question.
// The agent's own pick (propose_land) is marked; nothing lands until the owner answers. A conflict lands nothing: the agent gets it.
// ...IN THE CODING CHAT IT IS A CARD OF ITS OWN (`inChat`, GeneralWorkspace.jsx), and the whole diff opens in the code viewer, a file a fold (DiffView);
// while it waits to land each part can be marked Keep or Revert, and the reverted ones are taken out of the branch first (landing.revert)
// ...THE DIFF OPENS LIKE A PULL REQUEST, the whole window wide (the owner, 2026-11-08): the file list on the left, the diffs on the right - inside
// a turn of the chat it was a column too narrow for either. The card's own list folds the generated files as that view does (diffView `generated`)
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, Dialog, DialogContent, IconButton, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { landingFiles, landingWords } from "./landing.js";
import { hunkText, parseUnified } from "./diffView.js";
import DiffView from "./DiffView.jsx";
import { plural } from "./timeWords.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { ALERT_INK, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const btn = { minHeight: 32, py: 0, px: 1.4, fontSize: 12.5, textTransform: "none" };

const FileLine = ({ f }) => (
  <Typography variant="caption" sx={{ ...mono, display: "block", color: DIM, fontSize: 11 }} noWrap>
    <Box component="span" sx={{ color: "var(--tq-success, #47654a)" }}>+{f.plus}</Box> <Box component="span" sx={{ color: "var(--tq-danger, #7a2f3c)" }}>-{f.minus}</Box> {f.path}
  </Typography>);
export const SHOWN = 8;
// the row's Review changes asks the task's own card to open its diff (TaskPage): `handled` says a card took it
export const LANDING_DIFF = "tq-landing-diff";

export default function LandingCard({ taskId, onChanged, onState, inChat = false }) {
  const [s, setS] = useState(null), [diff, setDiff] = useState(null), [busy, setBusy] = useState(""), [said, setSaid] = useState(""),
    [err, setErr] = useState(""), [sure, setSure] = useState(false), [marks, setMarks] = useState({}), [open, setOpen] = useState(false),
    [diffErr, setDiffErr] = useState(""), [filesOpen, setFiles] = useState(false);
  const load = () => api.get(`/api/tasks/${taskId}/landing`).then(({ data }) => { setS(data?.data || null); onState?.(data?.data || null); })
    .catch(() => { setS(null); onState?.(null); });
  useEffect(() => { setS(null); setDiff(null); setOpen(false); setSaid(""); setErr(""); setSure(false); setMarks({}); setFiles(false); load(); }, [taskId]);   // eslint-disable-line react-hooks/exhaustive-deps
  const seeRef = useRef(null);
  useEffect(() => {
    const on = (e) => { if (Number(e.detail?.taskId) === Number(taskId) && seeRef.current) { e.detail.handled = true; seeRef.current(); } };
    window.addEventListener(LANDING_DIFF, on); return () => window.removeEventListener(LANDING_DIFF, on);
  }, [taskId]);
  seeRef.current = null;
  if (!s || (!s.ask && !s.landed && !s.changed)) return null;
  const w = landingWords(s);
  // THE DIFF OPENS AT THE PRESS (the owner, 2026-11-09: it waited for the read, and the button felt dead for a second): the window first, saying
  // it is reading the changes, then the diff into it - or why it could not be read
  const readDiff = () => { setDiffErr(""); return api.get(`/api/tasks/${taskId}/landing`, { params: { full: true } }).then(({ data }) => setDiff(data?.data?.diff || ""))
    .catch((e) => { setDiff(null); setDiffErr(e?.response?.data?.detail || "The changes could not be read - close this and try again."); }); };
  const seeDiff = () => { if (open) return setOpen(false); setOpen(true); setDiff(null); readDiff(); };
  // ...AND THE ROW'S REVIEW CHANGES OPENS THIS SAME VIEW (the owner, 2026-11-10: "yes, keep it"): lit on work left to review after its session
  // is gone, it is one road to the diff - this card's - never a second viewer (TaskPage `diff`, LANDING_DIFF)
  seeRef.current = s ? () => { setOpen(true); setDiff(null); readDiff(); } : null;
  const answer = async (how) => {
    if (how === "discard" && !sure) { setSure(true); return; }
    setBusy(how); setErr(""); setSure(false);
    try { const { data } = await api.post(`/api/tasks/${taskId}/landing`, { how }); setSaid(data?.says || ""); load(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not land"); }
    setBusy("");
  };
  // NOT NOW (the owner, 2026-11-10): the push put off is a press too. Nothing goes; the card folds to its title and its buttons, none of them
  // filled; it is a line in the chat, and the agent is told not to ask for it again (landing.hold)
  const hold = async () => {
    setBusy("hold"); setErr(""); setSure(false);
    try { await api.post(`/api/tasks/${taskId}/landing/hold`); load(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It was not held"); }
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
  const label = (h) => (s.answers || []).find((a) => a.how === h)?.label || h;
  const rest = (s.answers || []).map((a) => a.how).filter((h) => h !== w.first && h !== w.second);
  const tip = s.push ? `up to ${String(s.push.tip || "").slice(0, 7)}${s.push.deploy ? ` · deploys to ${s.push.deploy}` : ""}` : s.own && s.ask ? `${plural(s.ahead, "commit")} ahead` : "";
  const sub = s.held ? w.held : [tip, `+${s.plus || 0} −${s.minus || 0}`, s.ask && s.proposal?.why].filter(Boolean).join(" · ");
  const link = { ...FOCUS_RING, display: "inline-block", fontSize: 11.5, color: "var(--tq-link, #55697a)", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } };
  const press = (h, tone0, tone = s.held ? "t" : tone0) => (
    <Button key={h} size="small" disableElevation disabled={!!busy} data-tq-land={h} variant={tone === "p" ? "contained" : tone === "s" ? "outlined" : "text"}
      title={tone === "p" ? w.hint : undefined}
      sx={{ ...btn, ...(h === "discard" ? { color: ALERT_INK, borderColor: BORDER } : tone === "p" ? {} : { color: tone === "s" ? INK : DIM, borderColor: BORDER }) }}
      startIcon={busy === h ? <CircularProgress size={12} color="inherit" /> : null}
      onClick={() => answer(h)}>{h === "discard" && sure ? `Yes, discard ${plural(s.ahead, "commit")}` : label(h)}</Button>);
  const url = s.landed?.url || (said.match(/https?:\/\/\S+/) || [""])[0];
  // ONE TITLE, ONE LINE UNDER IT, THE FILES FOLDED, ONE FILLED BUTTON (the owner, 2026-11-09: "compact the land" - it listed every changed file
  // over Push and Push & deploy): the press it waits on and how big it is, the commit and where it goes once, the files and the diff a press
  // away; once pressed it STAYS in its turn as the press it took and what came of it, as the held steps' card does (HeldSteps)
  return (
    <Box data-tq-landing="" data-tq-act-state={s.held ? "held" : s.ask ? "waiting" : s.landed ? "pressed" : "resting"}
      sx={inChat ? { my: 1, px: 1.25, py: 0.9, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" } : { mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
      <Typography data-tq-landing-title="" sx={{ fontSize: 13.5, fontWeight: s.held ? 600 : 700, color: s.held ? DIM : INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{w.title}</Typography>
      <Typography noWrap data-tq-landing-sub="" title={[sub, w.shared].filter(Boolean).join(" - ")} sx={{ fontSize: 11.5, color: FAINT }}>{sub}</Typography>
      {!!s.files?.length && !s.held && <Box sx={{ display: "flex", gap: 1.5, mt: 0.4 }}>
        <Typography {...pressable(() => setFiles((o) => !o))} data-tq-landing-files="" aria-expanded={filesOpen} sx={link}>
          {filesOpen ? "Hide the files" : "Show the files"}</Typography>
        <Typography {...pressable(seeDiff)} data-tq-landing-diff="" sx={link}>{reviewing ? "See the diff · review it" : "See the diff"}</Typography>
      </Box>}
      {filesOpen && <Box data-tq-landing-list="" sx={{ mt: 0.4 }}>
        {src.slice(0, SHOWN).map((f) => <FileLine key={f.path} f={f} />)}
        {src.length > SHOWN && <Typography variant="caption" sx={{ display: "block", color: FAINT }}>and {src.length - SHOWN} more</Typography>}
        {!!gen.length && <Box component="details" data-tq-landing-generated="" sx={{ "& > summary": { cursor: "pointer", color: FAINT, fontSize: 11 } }}>
          <summary>Generated · {plural(gen.length, "file")}</summary>{gen.map((f) => <FileLine key={f.path} f={f} />)}</Box>}
      </Box>}
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
          {diffErr && <Typography variant="body2" data-tq-diff-error="" sx={{ color: "var(--tq-danger, #7a2f3c)" }}>{diffErr}</Typography>}
          {diff !== null && <DiffView files={files} marks={reviewing ? marks : null} onMark={reviewing ? (k, m) => setMarks((x) => ({ ...x, [k]: m })) : null} />}
          {reviewing && !!picked.length && <Button size="small" variant="outlined" disabled={!!busy} data-tq-landing-revert="" sx={{ ...btn, mt: 0.75, color: "var(--tq-danger, #7a2f3c)", borderColor: BORDER }}
            startIcon={busy === "revert" ? <CircularProgress size={12} color="inherit" /> : null} onClick={revert}>
            Revert {plural(picked.length, "marked part")}</Button>}
        </DialogContent>
      </Dialog>
      {s.ask ? <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mt: 0.6 }}>
        {w.first && press(w.first, "p")}{w.second && press(w.second, "s")}{rest.map((h) => press(h, "t"))}
        {!!s.push && !s.held && !sure && <Button size="small" disabled={!!busy} data-tq-land-hold="" sx={{ ...btn, color: DIM }}
          startIcon={busy === "hold" ? <CircularProgress size={12} color="inherit" /> : null} onClick={hold}>Not now</Button>}
        {sure && <Button size="small" sx={{ ...btn, color: DIM }} onClick={() => setSure(false)}>Keep it</Button>}
      </Box> : s.landed && <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mt: 0.6 }}>
        {/* ...the press it took, drawn pressed, and what came of it on the same line */}
        <Button size="small" variant={s.landed.how === "discard" ? "outlined" : "contained"} disableElevation disabled data-tq-pressed={s.landed.how}
          sx={{ ...btn, "&.Mui-disabled": s.landed.how === "discard" ? { color: FAINT } : { bgcolor: "var(--tq-tint-sage, #dfe8dd)", color: "var(--tq-success, #47654a)" } }}>{w.done}</Button>
        <Typography data-tq-act-done="" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>{said ? said.replace(url, "").replace(/[:\s]+$/, "") : w.doneLine}
          {url && <> · <a href={url} target="_blank" rel="noreferrer">{url.replace(/^https?:\/\//, "").slice(0, 70)}</a></>}</Typography>
      </Box>}
      {err && <Typography role="alert" variant="body2" sx={{ mt: 0.7, color: ALERT_INK }}>{err}</Typography>}
    </Box>
  );
}
