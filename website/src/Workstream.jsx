// WHICH WORKSTREAM IS THIS UNDER (the owner, 2026-11-01): someone who runs a day job, a side product and a personal life over the same
// apps gets one small label on each task and idea, and on the task a picker that moves it - the same pattern the repo picker uses for
// "which checkout" (RepoSelect). Moving it teaches who belongs where; nothing else changes on the page.
import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import LayersIcon from "@mui/icons-material/LayersOutlined";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

let cache = null;          // one read per page load: the list changes only through the setup screen or an Advisor card
export const loadWorkstreams = (fresh = false) => {
  if (!cache || fresh) cache = api.get("/api/workstreams").then(({ data }) => data.data || []).catch(() => { cache = null; return []; });
  return cache;
};
export const useWorkstreams = () => {
  const [xs, setXs] = useState([]);
  useEffect(() => { let live = true; loadWorkstreams().then((d) => live && setXs(d)); return () => { live = false; }; }, []);
  return xs;
};

// the label: the workstream's name, quiet - it is context, not a control
export const WorkstreamLabel = ({ name, slug, sx = {} }) => {
  const xs = useWorkstreams();
  const shown = name || xs.find((w) => w.slug === slug)?.name;
  if (!shown) return null;
  return (
    // ...cut short on a narrow rail it ends in "…" and says its whole name on hover (the owner, 2026-11-08: "this is cut off??") - it was clipped
    // mid-word by the row's edge with nothing to say what it was
    <Box component="span" data-tq-workstream={slug || ""} title={`Workstream: ${shown}`}
      sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, fontSize: 11, color: FAINT, border: `1px solid ${BORDER}`,
        borderRadius: 1, px: 0.6, py: 0.05, lineHeight: 1.5, whiteSpace: "nowrap", minWidth: 0, maxWidth: "45%", ...sx }}>
      <LayersIcon sx={{ fontSize: 12, flexShrink: 0 }} />
      <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{shown}</Box>
    </Box>
  );
};

// the picker on the task: the workstream it is under, and a select that moves it
export const WorkstreamSelect = ({ taskId, value, onDone }) => {
  const xs = useWorkstreams();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!xs.length) return null;
  const pick = async (slug) => {
    setBusy(true); setErr("");
    try { await api.put(`/api/tasks/${taskId}/workstream`, { workstream: slug }); onDone?.(slug); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not move it"); }
    setBusy(false);
  };
  return (
    <Box data-tq-workstream-picker="" sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mt: 0.5 }}>
      <LayersIcon sx={{ fontSize: 15, color: DIM }} />
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>workstream</Typography>
      <select aria-label="which workstream" value={value?.slug || ""} disabled={busy} onChange={(e) => pick(e.target.value)}
        style={{ fontSize: 12.5, padding: "3px 6px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "#fff", color: INK, minWidth: 180 }}>
        {!value?.slug && <option value="">not placed yet…</option>}
        {xs.map((w) => <option key={w.slug} value={w.slug}>{w.name}{w.personal ? " (personal)" : ""}</option>)}
      </select>
      {err && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </Box>
  );
};
