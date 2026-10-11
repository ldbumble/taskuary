// THE AGENT WORK CARD: everything a session did and thought, in one shape for every CLI and the general agent (the owner,
// 2026-10-10: "make sure the agent work section carries enough info to let user know everything the agent did and thought
// about. You can do short the long version with more button maybe but make sure it's full and complete record but don't
// duplicate sections"). Short: the result, once, and what it made. "Full record": what it decided and changed, its plan,
// the files it wrote, then every step - told, thought, tool, said - in order. Earlier sessions fold under it.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { Md } from "./md.jsx";
import PublishedPages from "./PublishedPages.jsx";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import { hasMore, recordFacts, recordSteps, reportParts, sourceLabel } from "./agentRecord.js";

const head = { fontSize: 11, fontWeight: 600, color: FAINT, letterSpacing: ".04em", textTransform: "uppercase", mb: 0.35 };

// long text folds to a few lines; the caller draws the Show more (useTall says whether one is needed)
const useTall = (height) => {
  const ref = useRef(null), [tall, setTall] = useState(false);
  useEffect(() => { if (ref.current) setTall(ref.current.scrollHeight > height + 24); });
  return [ref, tall];
};
const folded = (tall, open, height) => ({ maxHeight: open || !tall ? "none" : height, overflow: "hidden",
  ...(tall && !open ? { maskImage: "linear-gradient(#000 70%, transparent)" } : {}) });
const link = { fontSize: 11, minHeight: 0, p: 0, minWidth: 0 };

const Step = ({ s }) => {
  const [open, setOpen] = useState(false);
  if (s.k === "tool") return (
    <Box>
      <Box onClick={s.detail ? () => setOpen(!open) : undefined} title={s.detail || s.text}
        sx={{ display: "flex", gap: 1, ...mono, fontSize: 11.5, color: DIM, minWidth: 0, cursor: s.detail ? "pointer" : "default" }}>
        <Box component="span" sx={{ color: INK, fontWeight: 600, flexShrink: 0 }}>{s.name}</Box>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", ...(s.detail ? { fontFamily: "inherit" } : {}) }}>
          {s.text}{s.detail && <Box component="span" sx={{ color: FAINT }}>{open ? " ▾" : " ▸"}</Box>}</Box>
      </Box>
      {open && s.detail && <Box sx={{ ...mono, fontSize: 11, whiteSpace: "pre-wrap", overflowWrap: "anywhere", bgcolor: PANEL2, p: 0.75, borderRadius: 1, mt: 0.3, color: INK }}>{s.detail}</Box>}
    </Box>);
  if (s.k === "plan") return (
    <Box sx={{ fontSize: 12, color: DIM }}>
      <Box component="span" sx={{ fontWeight: 600 }}>Plan</Box>
      {s.items.map((i, n) => <Box key={n} sx={{ pl: 1 }}>{i.status === "completed" ? "✓" : i.status === "in_progress" ? "▸" : "○"} {i.text}</Box>)}
    </Box>);
  if (s.k === "result") return <Typography sx={{ fontSize: 12, color: FAINT, fontStyle: "italic" }}>Its answer — shown above.</Typography>;
  if (s.k === "error") return <Typography sx={{ fontSize: 12, color: "#8a3646" }}>⚠ {s.text}</Typography>;
  if (s.k === "gap") return <Typography sx={{ fontSize: 11.5, color: FAINT }}>… {s.text}</Typography>;
  if (s.k === "screen") return (
    <Box sx={{ ...mono, fontSize: 11, whiteSpace: "pre-wrap", bgcolor: PANEL2, p: 1, borderRadius: 1, maxHeight: 420, overflow: "auto", color: INK }}>{s.text}</Box>);
  // told / thought / said: a label, the words folded to a few lines until clicked
  const label = { you: "Told", thought: "Thought", said: "Said" }[s.k] || s.k;
  const long = s.text.length > 320;
  return (
    <Box sx={{ display: "flex", gap: 1, fontSize: 12.5, minWidth: 0 }}>
      <Typography sx={{ fontSize: 11, fontWeight: 600, color: FAINT, width: 52, flexShrink: 0, pt: "2px" }}>{label}</Typography>
      <Box onClick={long ? () => setOpen(!open) : undefined} sx={{ flex: 1, minWidth: 0, cursor: long ? "pointer" : "default",
        color: s.k === "thought" ? DIM : INK, fontStyle: s.k === "thought" ? "italic" : "normal",
        ...(long && !open ? { maxHeight: 64, overflow: "hidden", maskImage: "linear-gradient(#000 55%, transparent)" } : {}) }}>
        {s.k === "said" ? <Md text={s.text} /> : <Box sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{s.text}</Box>}
      </Box>
    </Box>);
};

const Full = ({ s }) => {
  const steps = recordSteps(s), parts = reportParts(s);
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.2, mt: 1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
      {parts.map(([k, v]) => <Box key={k}><Typography sx={head}>{k}</Typography><Box sx={{ fontSize: 12.5, color: INK }}><Md text={v} /></Box></Box>)}
      {!!s.plan?.length && <Box><Typography sx={head}>Its plan</Typography><Step s={{ k: "plan", items: s.plan }} /></Box>}
      {!!s.files?.length && <Box><Typography sx={head}>Files it wrote · {s.files.length}</Typography>
        {s.files.map((f) => <Typography key={f} noWrap title={f} sx={{ ...mono, fontSize: 11.5, color: INK }}>{f}</Typography>)}</Box>}
      {!!steps.length && <Box>
        <Typography sx={head}>{s.source === "conversation" ? "The working behind its answers" : "Every step"} · {steps.length}
          {s.source && <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> — from {sourceLabel(s.source)}</Box>}</Typography>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.6, maxHeight: 640, overflow: "auto", pr: 0.5 }}>
          {steps.map((x, i) => <Step key={i} s={x} />)}
        </Box>
      </Box>}
    </Box>);
};

// one session: facts, the result (folded when long), what it made, and the full record behind one button
export const SessionRecord = ({ s, pages = [], startOpen = false }) => {
  const [full, setFull] = useState(startOpen), [more, setMore] = useState(false);
  const [ref, tall] = useTall(220);
  return (
    <Box>
      <Typography sx={{ fontSize: 11.5, color: FAINT, mb: 0.5 }}>{recordFacts(s).join(" · ")}</Typography>
      {s.result ? <Box ref={ref} sx={{ fontSize: 13, color: INK, ...folded(tall, more, 220) }}><Md text={s.result} /></Box>
        : <Typography sx={{ fontSize: 12.5, color: DIM }}>It ended without a written result{s.steps?.length ? " — its steps are in the full record." : "."}</Typography>}
      {!!pages.length && <Box sx={{ mt: 1 }}><PublishedPages pages={pages} /></Box>}
      {(tall || hasMore(s)) && <Box sx={{ display: "flex", gap: 2, mt: 0.6 }}>
        {tall && <Button size="small" sx={link} onClick={() => setMore(!more)}>{more ? "Show less" : "Show more"}</Button>}
        {hasMore(s) && <Button size="small" sx={link} onClick={() => setFull(!full)}>{full ? "Hide the full record" : "Full record"}</Button>}
      </Box>}
      {full && <Full s={s} />}
    </Box>);
};

export const AgentRecord = ({ taskId, pages = [], stamp }) => {
  const [rec, setRec] = useState(null);
  useEffect(() => {
    let live = true;
    api.get(`/api/tasks/${taskId}/record`).then(({ data }) => live && setRec(data)).catch(() => live && setRec({ sessions: [] }));
    return () => { live = false; };
  }, [taskId, stamp]);
  if (!rec) return <CircularProgress size={12} />;
  const [now, ...before] = rec.sessions || [];
  if (!now && !pages.length) return null;
  return (
    <Box sx={{ width: "100%", bgcolor: PANEL, px: 1.35, py: 1.15, border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>
      {now ? <SessionRecord s={now} pages={pages} /> : <PublishedPages pages={pages} />}
      {!!before.length && <Box sx={{ mt: 1.2, pt: 1, borderTop: `1px solid ${BORDER}` }}>
        <Typography sx={head}>Earlier sessions · {before.length}</Typography>
        {before.map((s) => <Earlier key={s.sid} s={s} />)}
      </Box>}
    </Box>);
};

const Earlier = ({ s }) => {
  const [open, setOpen] = useState(false);
  const line = String(s.result || "").split(/\n\s*\n/)[0].replace(/[#*_`>]/g, "").trim();
  return (
    <Box sx={{ py: 0.5, borderBottom: `1px dashed ${BORDER}`, "&:last-of-type": { borderBottom: 0 } }}>
      <Box onClick={() => setOpen(!open)} sx={{ display: "flex", gap: 1, cursor: "pointer", fontSize: 12.5, minWidth: 0 }}>
        <Box component="span" sx={{ color: FAINT, width: 12 }}>{open ? "▾" : "▸"}</Box>
        <Box component="span" sx={{ color: DIM, flexShrink: 0 }}>{s.cli || s.by} · {String(s.at || "").slice(0, 16)}</Box>
        {!open && <Box component="span" sx={{ color: INK, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line || "no written result"}</Box>}
      </Box>
      {open && <Box sx={{ pl: 2.5, pt: 0.5 }}><SessionRecord s={s} /></Box>}
    </Box>);
};
