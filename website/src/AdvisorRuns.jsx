import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogContent, DialogTitle, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { Empty } from "./ui.jsx";
import { label as btnLabel } from "./buttons.js";
import { plural } from "./timeWords.js";

/* THE ADVISOR'S RUNS FOR IDEAS ABOUT HIS JOB (lookout.py; the design review 2026-11-23: "silence is observable"): each run - what it
   looked at closely and from which angle, what it read, what it raised, what it held and why, and what it used - beside the report's
   own History, in the same two columns. Read from /api/advisor/lookout; nothing here acts. */
export default function AdvisorRuns({ onClose }) {
  const [got, setGot] = useState(null);
  const [pick, setPick] = useState(0);
  const [lost, setLost] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    setLost(false);
    api.get("/api/advisor/lookout").then(({ data }) => setGot(data)).catch(() => setLost(true));
  }, [tries]);
  const runs = got?.items || [];
  const cur = runs[pick];
  const said = (r) => r.raised?.length ? `raised ${r.raised.length}` : "raised nothing";
  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth onClick={(e) => e.stopPropagation()}>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, fontSize: 15 }}>
        Advisor — its looks for ideas about your job
        <Typography variant="caption" sx={{ color: FAINT }}>{got ? `${plural(runs.length, "run")} kept` : lost ? "" : "loading…"}</Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={onClose} startIcon={<CloseIcon sx={{ fontSize: 14 }} />}>Close</Button>
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1, minHeight: 420 }}>
        {got?.skipped?.why && <Typography variant="caption" sx={{ color: DIM }}>
          <Box component="span" sx={{ fontWeight: 600 }}>last skipped · </Box>{(got.skipped.at || "").slice(0, 16)} — {got.skipped.why}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5, flex: 1 }}>
          <Box sx={{ width: 260, flexShrink: 0, borderRight: `1px solid ${BORDER}`, pr: 1, overflowY: "auto", maxHeight: "70vh" }}>
            {lost && <Alert severity="warning" sx={{ fontSize: 12 }} action={<Button color="inherit" size="small" onClick={() => setTries((n) => n + 1)}>{btnLabel("try_again")}</Button>}>
              The Advisor's runs could not be loaded.</Alert>}
            {!lost && got && !runs.length && <Empty>No runs kept yet — they start with its next look.</Empty>}
            {!got && !lost && <CircularProgress size={16} />}
            {runs.map((r, i) => (
              <Box key={r.at + i} onClick={() => setPick(i)}
                sx={{ px: 1, py: 0.6, mb: 0.4, borderRadius: 1, cursor: "pointer", bgcolor: pick === i ? "var(--tq-inset, #eef3ea)" : "transparent",
                  border: `1px solid ${pick === i ? "var(--tq-border, #cfd8c8)" : "transparent"}`, "&:hover": { bgcolor: "var(--tq-panel, #f4f3ef)" } }}>
                <Typography variant="caption" sx={{ display: "block", color: INK, fontWeight: 600, lineHeight: 1.4 }}>{(r.at || "").slice(0, 16)}</Typography>
                <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.4 }}>
                  {said(r)}{r.held?.length ? ` · held ${r.held.length}` : ""}{r.used ? ` · ${r.used.replace(/ \(ceiling.*\)$/, "")}` : ""}
                </Typography>
              </Box>
            ))}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0, overflowY: "auto", maxHeight: "70vh" }}>
            {cur ? <Run r={cur} /> : got && <Typography variant="caption" sx={{ color: FAINT }}>Pick a run on the left.</Typography>}
          </Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

function Part({ head, items, render = (x) => x }) {
  if (!items?.length) return null;
  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="caption" sx={{ fontWeight: 600, color: "var(--tq-warning, #6b5f45)" }}>{head} · {items.length}</Typography>
      {items.map((x, i) => (
        <Typography key={i} variant="caption" sx={{ display: "block", color: DIM, pl: 1, borderLeft: `2px solid ${BORDER}`, mt: 0.3, whiteSpace: "pre-wrap" }}>{render(x)}</Typography>
      ))}
    </Box>
  );
}

function Run({ r }) {
  return (
    <>
      <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{(r.at || "").slice(0, 16)} · {r.raised?.length ? `raised ${plural(r.raised.length, "idea")}` : "raised nothing"}</Typography>
      {r.used && <Typography variant="caption" sx={{ display: "block", color: DIM }}>used: {r.used}</Typography>}
      <Part head="looked at closely" items={r.deep} render={([a, lens]) => `${a.replace(":", ": ")} — from the ${lens} angle`} />
      <Part head="read further" items={r.reads} />
      <Part head="raised" items={r.raised} />
      <Part head="updated" items={r.updated} />
      <Part head="held, and why" items={r.held} render={([t, why]) => `${t} — ${why}`} />
      {!r.deep?.length && !r.reads?.length && !r.raised?.length && !r.held?.length &&
        <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 1 }}>It looked at what arrived and found nothing worth your time.</Typography>}
    </>
  );
}
