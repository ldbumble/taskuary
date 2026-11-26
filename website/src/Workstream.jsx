// WHICH PROFILE IS THIS UNDER (the owner, 2026-11-01 and 2026-11-26): someone who runs a day job, a side business and a personal life
// over the same apps keeps a profile for each, as a browser does. With two or more, a task says which it is under - a quiet word, and
// a picker that moves it - and a connection card says whose account it is. With one, none of this is drawn: the server lists none
// (workstreams.shown). The code's word for a profile is `workstream`.
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
    <Box component="span" data-tq-workstream={slug || ""} title={`Profile: ${shown}`}
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
  if (xs.length < 2) return null;
  const pick = async (slug) => {
    setBusy(true); setErr("");
    try { await api.put(`/api/tasks/${taskId}/workstream`, { workstream: slug }); onDone?.(slug); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not move it"); }
    setBusy(false);
  };
  return (
    <Box data-tq-workstream-picker="" sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mt: 0.5 }}>
      <LayersIcon sx={{ fontSize: 15, color: DIM }} />
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>profile</Typography>
      <select aria-label="which profile" value={value?.slug || ""} disabled={busy} onChange={(e) => pick(e.target.value)}
        style={{ fontSize: 12.5, padding: "3px 6px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "var(--tq-panel, #fff)", color: INK, minWidth: 180 }}>
        {!value?.slug && <option value="">not placed yet…</option>}
        {xs.map((w) => <option key={w.slug} value={w.slug}>{w.name}{w.personal ? " (personal)" : ""}</option>)}
      </select>
      {err && <Typography variant="caption" sx={{ color: "var(--tq-danger, #6b2733)" }}>{err}</Typography>}
    </Box>
  );
};

// WHOSE ACCOUNT A CONNECTION IS (the owner, 2026-11-26): one profile's, or every profile's - a task's agent uses its own profile's
// accounts and the ones left to all. Saved as it is picked, like everything on a connection card; not drawn while there is one profile.
export const AccountProfile = ({ conn, reload }) => {
  const xs = useWorkstreams();
  const [err, setErr] = useState("");
  if (xs.length < 2 || !conn?.ConnectorId) return null;
  const pick = async (slug) => {
    setErr("");
    try { await api.put(`/api/connectors/${conn.ConnectorId}/workstream`, { workstream: slug }); reload?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not save it"); }
  };
  return (
    <Box data-tq-account-profile="" sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
      <Typography component="label" htmlFor={`tq-profile-${conn.ConnectorId}`} variant="caption" sx={{ color: DIM }}>Profile</Typography>
      <select id={`tq-profile-${conn.ConnectorId}`} value={conn.Workstream || ""} onChange={(e) => pick(e.target.value)}
        style={{ fontSize: 12.5, padding: "2px 6px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "var(--tq-panel, #fff)", color: INK }}>
        <option value="">All profiles</option>
        {xs.map((w) => <option key={w.slug} value={w.slug}>{w.name}</option>)}
      </select>
      {err && <Typography variant="caption" sx={{ color: "var(--tq-danger, #6b2733)" }}>{err}</Typography>}
    </Box>
  );
};
