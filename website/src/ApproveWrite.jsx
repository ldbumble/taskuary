// APPROVE THIS WRITE ON SETUP (the owner, 2026-11-25): a routine's or report's step that writes to a connected system says so where it is set
// up, with its own approval. Its press is the run card's "Always approve this step" (flow.grant, the same standing yes), so the scheduled runs
// write without a card; Take back is Settings' own Remove (/api/trusted/remove). It is the step AS SAVED that is approved: one changed here
// says so, and its saved change waits for a press again.
import React, { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { ALERT_INK, BORDER, DIM, FAINT, INK, PANEL2 } from "./theme.jsx";

// the same step, by its content: key order and its name aside (flow.step_key leaves the label out too)
const stable = (o) => Array.isArray(o) ? `[${o.map(stable).join(",")}]`
  : o && typeof o === "object" ? `{${Object.keys(o).filter((k) => k !== "label").sort().map((k) => `${k}:${stable(o[k])}`).join(",")}}` : JSON.stringify(o);
export const sameStep = (a, b) => stable(a) === stable(b);

// {step id: {step, key, what, approved}} - the saved routine's or report's writes, read again whenever what is saved changes
export function useWrites(sid, saved) {
  const [ws, setWs] = useState({});
  const load = () => (sid ? api.get(`/api/sources/${sid}/writes`).then(({ data }) => setWs(Object.fromEntries((data?.data || []).map((w) => [w.step, w]))))
    .catch(() => setWs({})) : Promise.resolve(setWs({})));
  useEffect(() => { load(); }, [sid, saved]);   // eslint-disable-line react-hooks/exhaustive-deps
  return [ws, load];
}

export default function ApproveWrite({ sid, w, changed = false, onChanged }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  if (!sid || !w) return null;
  const press = async (fn) => {
    setBusy(true); setErr("");
    try { await fn(); await onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "That did not go through - try again."); }
    finally { setBusy(false); }
  };
  const approve = () => press(() => api.post(`/api/sources/${sid}/always`, { step: w.step, key: w.key }));
  const takeBack = () => press(() => api.post("/api/trusted/remove", { kind: "routine_write", key: { source_id: String(sid), key: w.key } }));
  const on = w.approved && !changed;
  return (
    <Box data-tq-approve-write={on ? "approved" : changed ? "changed" : "waits"} onClick={(e) => e.stopPropagation()}
      sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: PANEL2, px: 1.25, py: 0.9, display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      <Box sx={{ flex: 1, minWidth: 180 }}>
        <Typography sx={{ fontSize: 12.5, color: INK, fontWeight: 600 }}>{on ? `Approved: ${w.what}` : `This step will ${w.what}`}</Typography>
        <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
          {changed ? "Changed since it was saved - save it, and its write waits for your press until you approve it again."
            : on ? "Its scheduled runs write without asking. Change the step and it asks again."
            : "Each run waits for your press on this write - approve it here and the scheduled runs write without a card."}</Typography>
        {err && <Typography variant="caption" role="alert" sx={{ color: ALERT_INK, display: "block" }}>{err}</Typography>}
      </Box>
      {!changed && (on
        ? <Button size="small" variant="outlined" disabled={busy} onClick={takeBack} sx={{ color: DIM, borderColor: BORDER }}>{busy ? "Taking back…" : "Take back"}</Button>
        : <Button size="small" variant="outlined" disabled={busy} onClick={approve}>{busy ? "Approving…" : "Approve this write"}</Button>)}
    </Box>
  );
}
