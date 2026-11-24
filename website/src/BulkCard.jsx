// ONE CARD FOR A BULK JOB (bulkCard.js, taskuary/bulkcard.py): the count, a row each - whom or what it goes to, its one line, what to check -
// with a tick box; the first few opened in their single form to review, any other opened the same way; one press does every ticked one, each
// by its own road, and a bar IN the card says how far it is, failures counted as they come, Stop for the rest. Its agent hears the run once.
import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, Checkbox, LinearProgress, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import ActionCard from "./ActionCard.jsx";
import { cardOf, isCardReview } from "./actionCard.js";
import { countOf, pressOf, progress, rowOf, rowState, running } from "./bulkCard.js";
import { MovedPast } from "./PassedCard.jsx";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import api from "./api";
import Artifact from "./Artifact.jsx";

const SAMPLE = 2;      // ...review a few: the first ones stand open in their single form

// `past`: the chat moved past it (or its rows say so: set aside, none left waiting) - drawn as it stood while it waited, greyed (MovedPast)
export default function BulkCard({ rows = [], tid, onChanged, past: given = false }) {
  const key = rows[0]?.Batch, [run, setRun] = useState(null), [skip, setSkip] = useState(() => new Set()), [open, setOpen] = useState(() => new Set());
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const read = useCallback(() => api.get(`/api/reviews/batch/${key}`).then(({ data }) => setRun(data)).catch(() => {}), [key]);
  // ...and read again whenever the rows it counts change (recorded: every row stood ✓ while the bar read "0 of 30" a second behind them)
  const marks = rows.map((r) => `${r.ReviewId}:${r.Status}`).join(",");
  useEffect(() => { read(); }, [read, marks]);
  // ...read again while it runs, never blocking the page: a row at a time lands on GitHub or in the outbox
  // ...keyed on WHETHER it runs, never on the page's onChanged (2026-11-17): each row done pokes task-changed, the task page redraws with a
  // new arrow, and a poll keyed on it was torn down before its second came - the bar read "0 of 25" and Stop the rest stood lit to the end
  const changed = useRef(onChanged); changed.current = onChanged;
  const live = running(run);
  useEffect(() => { if (!live) return undefined; const t = setInterval(() => { read(); changed.current?.(); }, 1000); return () => clearInterval(t); }, [live, read]);
  const raw = rows.map((r) => [r, rowState(r, run)]), past = given || (!running(run) && raw.some(([, s]) => s.aside) && !raw.some(([, s]) => s.waiting));
  const states = raw.map(([r, s]) => [r, s.aside ? { waiting: true } : s]), waiting = states.filter(([, s]) => s.waiting), n = waiting.filter(([r]) => !skip.has(r.ReviewId)).length;
  const go = async () => {
    setBusy(true); setErr("");
    try { const { data } = await api.post(`/api/reviews/batch/${key}/run`, { skip: [...skip].filter((id) => waiting.some(([r]) => r.ReviewId === id)) }); setRun(data); }
    catch (e) { setErr(e?.response?.data?.detail || "It did not start - try again"); }
    finally { setBusy(false); onChanged?.(); }
  };
  const stop = () => api.post(`/api/reviews/batch/${key}/cancel`).then(({ data }) => setRun(data)).catch(() => {});
  const flip = (set, id) => set((s) => { const x = new Set(s); if (x.has(id)) x.delete(id); else x.add(id); return x; });
  const shown = (r, i) => open.has(r.ReviewId) || (i < SAMPLE && rowState(r, run).waiting && !running(run) && !open.has(-r.ReviewId));
  return (<MovedPast on={past}>
    <Artifact data-tq-bulk-card={key} sx={{ p: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.75 }}>
        <Typography sx={{ fontWeight: 600, color: INK, fontSize: 14 }}>{countOf(rows)} - review a few, then do them all</Typography>
      </Box>
      {(running(run) || run?.state === "finished" || run?.state === "stopped") && <Box data-tq-bulk-progress="" sx={{ mb: 1 }}>
        <LinearProgress variant="determinate" value={progress(run)} sx={{ height: 6, borderRadius: 3 }} />
        <Typography variant="caption" sx={{ color: DIM }}>
          {`${(run.done || 0) + (run.failed || 0) + (run.left || 0)} of ${run.total} · ${run.done || 0} done`}{run.failed ? ` · ${run.failed} failed` : ""}{run.left ? ` · ${run.left} left out` : ""}
          {run.state === "stopped" ? ` · stopped${waiting.length && !past ? " - the rest still waits" : ""}` : run.state === "cancelling" ? " · stopping after this one" : run.state === "finished" ? " · finished" : ""}</Typography>
      </Box>}
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, maxHeight: 420, overflowY: "auto" }}>
        {states.map(([r, s], i) => { const w = rowOf(r); return (
          <Box component="li" key={r.ReviewId} data-tq-bulk-row={r.ReviewId} sx={{ borderTop: i ? `1px solid ${BORDER}` : "none", py: 0.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
              {s.waiting ? <Checkbox size="small" checked={!skip.has(r.ReviewId)} disabled={running(run)} onChange={() => flip(setSkip, r.ReviewId)} sx={{ p: 0.25 }}
                inputProps={{ "aria-label": `Include ${w.target}` }} /> : <Box component="span" sx={{ width: 26, textAlign: "center", color: s.done ? "var(--tq-ok, #3d7a4f)" : FAINT }}>{s.done ? "✓" : s.failed ? "!" : "–"}</Box>}
              <Typography sx={{ fontSize: 13, color: INK, flexShrink: 0, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: skip.has(r.ReviewId) ? "line-through" : "none" }}>{w.target}</Typography>
              <Typography sx={{ fontSize: 13, color: DIM, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.line}</Typography>
              {w.flags.map((f) => <Typography key={f} variant="caption" sx={{ color: "var(--tq-warn, #8a4b1c)" }}>{f}</Typography>)}
              {s.failed && <Typography variant="caption" sx={{ color: "var(--tq-danger, #7a2f3c)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.failed}>{s.failed}</Typography>}
              {s.waiting && <Button size="small" onClick={() => flip(setOpen, shown(r, i) ? -r.ReviewId : r.ReviewId)} sx={{ minWidth: 0 }}>{shown(r, i) ? "Hide" : "Open"}</Button>}
            </Box>
            {s.waiting && shown(r, i) && <Box sx={{ pl: 4, pb: 1 }}>
              {isCardReview(r) ? <ActionCard row={cardOf(r)} tid={tid} onChanged={onChanged} past={past} /> : <ReviewDecision review={r} onChanged={onChanged} past={past} />}</Box>}
          </Box>); })}
      </Box>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1 }}>
        {running(run) ? <Button size="small" variant="outlined" onClick={stop} disabled={run.state === "cancelling"} data-tq-bulk-stop="">Stop the rest</Button>
          : waiting.length > 0 && <Button size="small" variant="contained" disableElevation disabled={busy || !n} onClick={go} data-tq-bulk-press="">{pressOf(rows, n)}</Button>}
        {!!err && <Typography variant="caption" role="alert" sx={{ color: "var(--tq-danger, #7a2f3c)" }}>{err}</Typography>}
        <Box sx={{ flex: 1 }} />
        {!running(run) && skip.size > 0 && <Typography variant="caption" sx={{ color: FAINT }}>{skip.size} left out</Typography>}
      </Box>
    </Artifact></MovedPast>);
}
