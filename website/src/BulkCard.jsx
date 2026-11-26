import { useCallback, useEffect, useRef, useState } from "react";
import { Box, LinearProgress, Typography } from "@mui/material";
import ReviewDecision, { ActReview } from "./ReviewDecision.jsx";
import { cardOf, isCardReview } from "./actionCard.js";
import { countOf, pressOf, progress, rowOf, rowOpens, rowState, running } from "./bulkCard.js";
import { MovedPast } from "./PassedCard.jsx";
import { ReviewCard } from "./Artifact.jsx";
import { DIM, FAINT } from "./theme.jsx";
import api from "./api";

// MANY OF ONE ACT IS THE SAME CARD WITH ITS ROWS (bulkCard.js, taskuary/bulkcard.py): the count, a row each - whom or what it goes to, its one line,
// what to check - with a tick box; the first few opened in their own card to review; one press does every ticked one, each by its own road, and a
// bar IN the card says how far it is, failures counted as they come, Stop for the rest. Its agent hears the run once.
const SAMPLE = 2;      // ...review a few: the first ones stand open in their single form
export default function BulkReview({ rows = [], tid, onChanged, past: given = false }) {
  const key = rows[0]?.Batch, [run, setRun] = useState(null), [skip, setSkip] = useState(() => new Set()), [open, setOpen] = useState(() => new Set());
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const read = useCallback(() => api.get(`/api/reviews/batch/${key}`).then(({ data }) => setRun(data)).catch(() => {}), [key]);
  // ...read again whenever the rows it counts change (recorded: every row stood ✓ while the bar read "0 of 30" a second behind them)
  const marks = rows.map((r) => `${r.ReviewId}:${r.Status}`).join(",");
  useEffect(() => { read(); }, [read, marks]);
  // ...and while it runs, keyed on WHETHER it runs, never on the page's onChanged (2026-11-17: a poll keyed on it was torn down each redraw)
  const changedRef = useRef(onChanged); changedRef.current = onChanged;
  const live = running(run);
  useEffect(() => { if (!live) return undefined; const t = setInterval(() => { read(); changedRef.current?.(); }, 1000); return () => clearInterval(t); }, [live, read]);
  const raw = rows.map((r) => [r, rowState(r, run)]), past = given || (!live && raw.some(([, s]) => s.aside) && !raw.some(([, s]) => s.waiting));
  const states = raw.map(([r, s]) => [r, s.aside ? { waiting: true } : s]), waiting = states.filter(([, s]) => s.waiting), n = waiting.filter(([r]) => !skip.has(r.ReviewId)).length;
  const go = async () => {
    setBusy(true); setErr("");
    try { const { data } = await api.post(`/api/reviews/batch/${key}/run`, { skip: [...skip].filter((id) => waiting.some(([r]) => r.ReviewId === id)) }); setRun(data); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not start - try again"); }
    finally { setBusy(false); onChanged?.(); }
  };
  const stop = () => api.post(`/api/reviews/batch/${key}/cancel`).then(({ data }) => setRun(data)).catch(() => {});
  const flip = (setter, id) => setter((s) => { const x = new Set(s); if (x.has(id)) x.delete(id); else x.add(id); return x; });
  const shownRow = (r, i) => rowOpens(r.ReviewId, i, { open, live, sample: SAMPLE });
  const items = states.map(([r, s], i) => { const w = rowOf(r); return { id: r.ReviewId, target: w.target, line: w.line, flags: w.flags, failed: s.failed || "",
    mark: s.done ? "✓" : s.failed ? "!" : "–", struck: skip.has(r.ReviewId), ...(s.waiting ? { checked: !skip.has(r.ReviewId), locked: live, onCheck: () => flip(setSkip, r.ReviewId) } : {}),
      open: shownRow(r, i), onOpen: () => flip(setOpen, shownRow(r, i) ? -r.ReviewId : r.ReviewId),
      body: isCardReview(r) ? <ActReview row={cardOf(r)} tid={tid} onChanged={onChanged} past={past} /> : <ReviewDecision review={r} onChanged={onChanged} past={past} /> }; });
  const ran = live || ["finished", "stopped"].includes(run?.state);
  return (<MovedPast on={past}>
    <ReviewCard id={key} kind="bulk" state={live ? "going" : waiting.length ? "waiting" : "done"} data-tq-bulk-card={key} label={`${countOf(rows)} - review a few, then do them all`}
      before={ran && <Box data-tq-bulk-progress="" sx={{ mb: 1 }}>
        <LinearProgress variant="determinate" value={progress(run)} sx={{ height: 6, borderRadius: 3 }} />
        <Typography variant="caption" sx={{ color: DIM }}>
          {`${(run.done || 0) + (run.failed || 0) + (run.left || 0)} of ${run.total} · ${run.done || 0} done`}{run.failed ? ` · ${run.failed} failed` : ""}{run.left ? ` · ${run.left} left out` : ""}
          {run.state === "stopped" ? ` · stopped${waiting.length && !past ? " - the rest still waits" : ""}` : run.state === "cancelling" ? " · stopping after this one" : run.state === "finished" ? " · finished" : ""}</Typography>
      </Box>} items={items}
      press={live ? [{ id: "stop", label: "Stop the rest", tone: "s", disabled: run.state === "cancelling", run: stop, attrs: { "data-tq-bulk-stop": "" } }]
        : waiting.length ? [{ id: "run", label: pressOf(rows, n), tone: "p", disabled: busy || !n, run: go, attrs: { "data-tq-bulk-press": "" } }] : []}
      tail={<>{!!err && <Typography variant="caption" role="alert" sx={{ color: "var(--tq-danger, #7a2f3c)" }}>{err}</Typography>}
        {!live && skip.size > 0 && <Typography variant="caption" sx={{ color: FAINT, ml: "auto" }}>{skip.size} left out</Typography>}</>} />
  </MovedPast>);
}
