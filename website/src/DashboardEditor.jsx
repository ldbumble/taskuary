// A DASHBOARD ON THE REPORTS PAGE: set up with AI like a report (describe it, the composer proposes sources and presets, the owner
// sees it drawn over REAL rows and saves it), then its name, its refresh and its buttons. Nothing runs an AI after the save - each
// refresh re-reads the sources (dashboards.py). The composer's words land here; the buttons do the talking.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import api from "./api";
import Composer from "./Composer.jsx";
import Dashboard from "./dashboard/Dashboard.jsx";
import { SchedulePicker, scheduleOf, withSchedule } from "./WorkflowEditor.jsx";
import { removeNow } from "./Removed.jsx";
import { DASH } from "./words.js";
import { FAINT, INK } from "./theme.jsx";
import { dayLabel } from "./dates.js";
import { fmtTime12 } from "./ui.jsx";

const errOf = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

export default function DashboardEditor({ sourceId = null, draft = null, reload, onBack, onSaved }) {
  const [spec, setSpec] = useState(draft?.config || null);
  const [note, setNote] = useState(draft ? { severity: draft.meta?.error || draft.meta?.confidence === "low" ? "warning" : "info",
    text: draft.meta?.error ? `${draft.meta.error}.` : draft.meta?.explain || "" } : null);
  const [data, setData] = useState(null), [problems, setProblems] = useState([]), [active, setActive] = useState(true);
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [said, setSaid] = useState("");
  const [title, setTitle] = useState(draft?.config?.title || ""), [sched, setSched] = useState(() => scheduleOf(draft?.config || {}));

  const fetchSaved = async () => {
    const { data: d } = await api.get(`/api/dashboards/${sourceId}`);
    setSpec(d.config); setData(d.data); setProblems(d.problems || []); setActive(d.active);
    return d;
  };
  useEffect(() => {
    if (sourceId == null) return;
    fetchSaved().then((d) => { setTitle(d.config.title || ""); setSched(scheduleOf(d.config)); })
      .catch((e) => setErr(errOf(e, "The dashboard could not be read.")));
  }, [sourceId]);   // eslint-disable-line react-hooks/exhaustive-deps
  // a draft is drawn over real rows before it is kept: its sources run now, nothing is saved
  useEffect(() => {
    if (sourceId != null || !spec) return;
    let live = true;
    setBusy("preview"); setErr("");
    api.post("/api/dashboards/preview", { config: spec })
      .then(({ data: d }) => { if (live) { setData(d.data); setProblems(d.problems || []); } })
      .catch((e) => { if (live) setErr(errOf(e, "Its sources could not be read.")); })
      .finally(() => { if (live) setBusy(""); });
    return () => { live = false; };
  }, [spec, sourceId]);

  const config = () => withSchedule({ ...spec, title: title.trim() || spec.title }, sched);
  const save = async () => {
    setBusy("save"); setErr(""); setSaid("");
    try {
      const c = config();
      const body = { Channel: "report", Address: c.title, ConfigJson: JSON.stringify(c), Active: sourceId == null ? true : active };
      if (sourceId != null) body.SourceId = sourceId;
      const { data: d } = await api.post("/api/sources", body);
      const sid = d.sourceId ?? sourceId;
      if (sourceId == null) await api.post(`/api/reports/${sid}/rerun`).catch(() => null);   // a new one fills now, not at its first slot
      await reload?.();
      onSaved?.(sid);
      if (sourceId != null) setSaid("✓");
    } catch (e) { setErr(errOf(e, "The dashboard was not saved.")); }
    setBusy("");
  };
  // a run is in the background (the one road, reports.run_one): its rows are read back as it lands
  const run = async () => {
    setBusy("run"); setErr("");
    try {
      await api.post(`/api/reports/${sourceId}/rerun`);
      for (const ms of [1200, 2500, 5000]) {
        await new Promise((r) => setTimeout(r, ms));
        const d = await fetchSaved();
        if (d.data?.at && (!data?.at || d.data.at > data.at)) break;
      }
    } catch (e) { setErr(errOf(e, "It did not run.")); }
    setBusy("");
  };
  const remove = async () => {
    setBusy("remove");
    try { await removeNow(() => api.delete(`/api/sources/${sourceId}`), "dashboard", title); await reload?.(); onBack?.(); }
    catch (e) { setErr(errOf(e, "It was not removed.")); setBusy(""); }
  };

  if (!spec) return (
    <Box data-tq-dashboard-setup="">
      {err && <Alert severity="error" sx={{ mb: 1.5 }}>{err}</Alert>}
      {sourceId == null ? <Composer kind="dashboard" onDraft={(config, meta) => {
        setSpec(config); setTitle(config.title || ""); setSched(scheduleOf(config));
        setNote({ severity: meta?.error || meta?.confidence === "low" ? "warning" : "info", text: meta?.error ? `${meta.error}.` : meta?.explain || "" });
      }} /> : !err && <CircularProgress size={20} />}
    </Box>
  );
  return (
    <Box data-tq-dashboard-editor="" sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
      {note?.text && <Alert severity={note.severity} onClose={() => setNote(null)} sx={{ fontSize: 12.5 }}>{note.text}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
        <TextField size="small" value={title} onChange={(e) => setTitle(e.target.value)} sx={{ bgcolor: "#fff", minWidth: 220, flex: "1 1 220px" }}
          inputProps={{ "aria-label": "Title" }} />
        <Typography sx={{ fontSize: 12, color: FAINT }}>{DASH.schedule}</Typography>
        <SchedulePicker sched={sched} setSched={setSched} cron={spec.cron} />
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation disabled={!!busy || !title.trim()} onClick={save} data-tq-dashboard-save=""
          startIcon={busy === "save" ? <CircularProgress size={12} /> : null}>{busy === "save" ? DASH.saving : DASH.save}</Button>
        {sourceId == null && <Button size="small" disabled={!!busy} onClick={() => { setSpec(null); setData(null); setNote(null); setProblems([]); }}>{DASH.again}</Button>}
        {sourceId != null && <Button size="small" disabled={!!busy} onClick={run}
          startIcon={busy === "run" ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}>{busy === "run" ? DASH.running : DASH.run}</Button>}
        {sourceId != null && <Button size="small" color="inherit" disabled={!!busy} onClick={remove} sx={{ color: FAINT }}>{DASH.remove}</Button>}
        {said && <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "#47654a" }}>{said}</Typography>}
        {data?.at && <Typography sx={{ fontSize: 11.5, color: FAINT, ml: "auto" }}>{DASH.updated} {dayLabel(data.at)} {fmtTime12(data.at)}</Typography>}
      </Box>
      {err && <Alert severity="error">{err}</Alert>}
      {problems.length > 0 && <Alert severity="warning" sx={{ fontSize: 12.5 }}>{problems.map((p) => <div key={p}>{p}</div>)}</Alert>}
      {busy === "preview" && !data ? <CircularProgress size={20} />
        : data ? <Dashboard spec={spec} data={data} stale={busy === "run" || busy === "preview"} />
          : sourceId != null && <Typography sx={{ fontSize: 12.5, color: INK }}>{DASH.never}</Typography>}
    </Box>
  );
}
