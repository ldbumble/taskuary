// A DASHBOARD ON THE REPORTS PAGE: set up with AI like a report (describe it, the composer proposes sources and presets, the owner
// sees it drawn over REAL rows and saves it), then its name, its refresh and its buttons. Nothing runs an AI after the save - each
// refresh re-reads the sources (dashboards.py). The composer's words land here; the buttons do the talking.
// ...and every one is CONFIGURABLE (the owner, 2026-10-24: "it should be configurable ... with sources layout like reports"): its
// sources are a report's source cards, its components are cards beside them, and the built-in one is edited like any other.
import React, { useEffect, useRef, useState } from "react";
import { Alert, Autocomplete, Box, Button, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import api from "./api";
import Composer from "./Composer.jsx";
import Dashboard from "./dashboard/Dashboard.jsx";
import { RANGES } from "./dashboard/slice.js";
import { BINDS, MAX_COMPONENTS, MAX_SOURCES, OWN_KEYS, runCfg, freshKey, orphans, sigOf, whereOf, whereText, windowOf, withField, withKind, withWindow } from "./dashboard/setup.js";
import { SourceCard, SourceTest } from "./ReportsView.jsx";
import { WORKFLOW_TYPES } from "./sourceShape.js";
import { SchedulePicker, scheduleOf, withSchedule } from "./WorkflowEditor.jsx";
import { removeNow } from "./Removed.jsx";
import { DASH } from "./words.js";
import { BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { dayLabel } from "./dates.js";
import { fmtTime12 } from "./ui.jsx";

const errOf = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

const COLUMN = new Set(["x", "y", "series", "label", "meta", "sort"]), NUMBER = new Set(["target", "limit"]);
const NOT_ROWS = new Set(["assistant", "dashboard", ...WORKFLOW_TYPES]);   // compose.NOT_A_SOURCE: a dashboard reads data views only

// THE READY ONES (dashboards.TEMPLATES): what the End of day checkup is to reports - one press draws it over this install's own rows,
// and it is saved like any draft. Taskuary at a glance needs nothing connected, so it is the way in for anybody (the owner, 2026-10-23).
export function Templates({ onUse }) {
  const [list, setList] = useState(null), [busy, setBusy] = useState(""), [err, setErr] = useState("");
  useEffect(() => { api.get("/api/dashboards/templates").then(({ data }) => setList(data.templates || [])).catch(() => setList([])); }, []);
  const use = async (key) => {
    setBusy(key); setErr("");
    try { const { data } = await api.get(`/api/dashboards/templates/${encodeURIComponent(key)}`); onUse(data); }
    catch (e) { setErr(errOf(e, "It could not be drawn.")); }
    setBusy("");
  };
  if (!list?.length) return null;
  return (
    <Box data-tq-dashboard-templates="" sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography sx={{ fontSize: 12, color: FAINT }}>{DASH.or_start}</Typography>
      {list.map((t) => (
        <Box key={t.key} sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fffdfb" }}>
          <Box sx={{ flex: "1 1 240px", minWidth: 0 }}>
            <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: INK }}>{t.title}</Typography>
            <Typography sx={{ fontSize: 12.5, color: FAINT, mt: 0.25 }}>{t.explain}</Typography>
          </Box>
          <Button size="small" variant="outlined" disableElevation disabled={!!busy} onClick={() => use(t.key)} data-tq-dashboard-template={t.key}
            startIcon={busy === t.key ? <CircularProgress size={12} /> : null} sx={{ flex: "none" }}>{busy === t.key ? DASH.using : DASH.use}</Button>
        </Box>
      ))}
      {err && <Alert severity="error">{err}</Alert>}
    </Box>
  );
}

// a column: picked from what its source returned last, or typed (a source that has not run yet has no columns to offer)
function ColumnField({ label, value, cols, onChange, multiple = false, placeholder }) {
  const input = (p) => <TextField {...p} label={label || undefined} placeholder={placeholder} sx={{ bgcolor: "#fff" }}
    inputProps={{ ...p.inputProps, "aria-label": label || placeholder }} />;
  return multiple
    ? <Autocomplete multiple freeSolo size="small" options={cols} value={value || []} onChange={(_e, v) => onChange(v)} renderInput={input} />
    : <Autocomplete freeSolo size="small" options={cols} value={value ?? ""} inputValue={value ?? ""}
        onInputChange={(_e, v) => { if (v !== (value ?? "")) onChange(v); }} renderInput={input} />;
}

// ONE COMPONENT, SET UP: a source card's frame (its place, Duplicate, Remove, drag to move), the preset and what it binds
export function ComponentCard({ c, index, count, sources, columns, dragging, onDragStart, onDragEnd, onDropHere, onChange, onCopy, onRemove }) {
  const F = DASH.fields, cols = columns[c.source] || [];
  const [w, setW] = useState(whereText(c.where));
  useEffect(() => { if (JSON.stringify(whereOf(w)) !== JSON.stringify(c.where)) setW(whereText(c.where)); }, [JSON.stringify(c.where)]);   // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k, v) => onChange(withField(c, k, k === "w" && v !== "" ? Number(v) : v));
  const sel = (k, value, opts, sx = {}) => (
    <Select size="small" value={value} onChange={(e) => set(k, e.target.value)} sx={{ fontSize: 12.5, bgcolor: "#fff", ...sx }}
      inputProps={{ "aria-label": F[k] }}>{opts.map(([v, l]) => <MenuItem key={v} value={v} sx={{ fontSize: 12.5 }}>{l}</MenuItem>)}</Select>
  );
  const field = (k) => {
    if (k === "agg") return <Box key={k}>{sel(k, c.agg || "count", Object.entries(DASH.aggs), { width: "100%" })}</Box>;
    if (k === "y" && (c.agg || "count") === "count") return null;
    if (k === "good") return <Box key={k} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Typography variant="caption" sx={{ color: DIM, flex: "none" }}>{F.good}</Typography>
      {sel(k, c.good || "up", Object.entries(DASH.goods), { flex: 1 })}</Box>;
    if (k === "columns") return <ColumnField key={k} multiple label={F.columns} value={c.columns} cols={cols} onChange={(v) => set(k, v)} />;
    if (COLUMN.has(k)) return <ColumnField key={k} label={F[k]} value={c[k]} cols={cols} onChange={(v) => set(k, v)} />;
    return <TextField key={k} size="small" label={F[k]} type={NUMBER.has(k) ? "number" : "text"} value={c[k] ?? ""} sx={{ bgcolor: "#fff" }}
      onChange={(e) => set(k, NUMBER.has(k) && e.target.value !== "" ? Number(e.target.value) : e.target.value)} />;
  };
  return (
    <Box data-tq-dash-component={index} draggable onDragStart={onDragStart} onDragEnd={onDragEnd} onDragOver={(e) => e.preventDefault()} onDrop={onDropHere}
      sx={{ ...card, width: { xs: "100%", sm: 354 }, p: 1.25, display: "flex", flexDirection: "column", gap: 1, opacity: dragging ? 0.45 : 1,
        cursor: "grab", "&:active": { cursor: "grabbing" } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <DragIndicatorIcon sx={{ fontSize: 16, color: "#cfc9bf" }} />
        <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1, minWidth: 0 }} noWrap>component {index + 1} of {count}</Typography>
        <ContentCopyIcon onClick={onCopy} titleAccess="Duplicate" sx={{ fontSize: 14, color: FAINT, cursor: "pointer", "&:hover": { color: "#55697a" } }} />
        <CloseIcon onClick={onRemove} titleAccess="Remove this component" sx={{ fontSize: 15, color: FAINT, cursor: "pointer", "&:hover": { color: "#6b2733" } }} />
      </Box>
      {/* the preset: a kind changed keeps what both read (title, source, where, window) and drops the bindings the old one had */}
      <Select size="small" value={c.kind} inputProps={{ "aria-label": "preset" }} sx={{ fontSize: 12.5, bgcolor: "#fff" }}
        onChange={(e) => onChange(withKind(c, e.target.value))}>
        {Object.entries(DASH.kinds).map(([k, l]) => <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{l}</MenuItem>)}
      </Select>
      <TextField size="small" label={F.title} value={c.title || ""} sx={{ bgcolor: "#fff" }} onChange={(e) => set("title", e.target.value)} />
      {sel("source", sources.some((s) => s.key === c.source) ? c.source : "", [["", "-"], ...sources.map((s) => [s.key, s.label || s.key])])}
      {(BINDS[c.kind] || []).map(field)}
      <TextField size="small" label={F.where} value={w} sx={{ bgcolor: "#fff" }} placeholder="state=open"
        onChange={(e) => { setW(e.target.value); set("where", whereOf(e.target.value)); }} />
      <Box sx={{ display: "flex", gap: 1 }}>
        <Select size="small" value={windowOf(c)} displayEmpty onChange={(e) => onChange(withWindow(c, e.target.value))} inputProps={{ "aria-label": F.range }}
          sx={{ fontSize: 12.5, bgcolor: "#fff", flex: 1, minWidth: 0 }}>
          {Object.entries(DASH.windows).map(([v, l]) => <MenuItem key={v} value={v} sx={{ fontSize: 12.5 }}>{l}</MenuItem>)}
        </Select>
        {sel("w", String(c.w || ""), [["", `${F.w}: as its kind`], ...Object.entries(DASH.widths)], { flex: "0 0 128px" })}
      </Box>
    </Box>
  );
}

// a section of the page: its name and one line on what it is, then its cards in rows, the add card last
const Section = ({ title, hint, children }) => (
  <Box sx={{ mt: 1 }}>
    <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }}>{title}</Typography>
    <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>{hint}</Typography>
    <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "stretch" }}>{children}</Box>
  </Box>
);
const AddCard = ({ label, onClick, ...rest }) => (
  <Box onClick={onClick} {...rest} sx={{ ...card, width: { xs: "100%", sm: 354 }, minHeight: 120, display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", gap: 0.5, cursor: "pointer", borderStyle: "dashed", color: DIM, "&:hover": { borderColor: "#d8cfbe", color: "#55697a" } }}>
    <AddIcon sx={{ fontSize: 20 }} /><Typography variant="body2" sx={{ fontWeight: 600 }}>{label}</Typography>
  </Box>
);

export default function DashboardEditor({ sourceId = null, draft = null, types = [], connectors = [], reload, onBack, onSaved }) {
  const [spec, setSpec] = useState(draft?.config || null);
  const [note, setNote] = useState(draft ? { severity: draft.meta?.error || draft.meta?.confidence === "low" ? "warning" : "info",
    text: draft.meta?.error ? `${draft.meta.error}.` : draft.meta?.explain || "" } : null);
  const [data, setData] = useState(null), [problems, setProblems] = useState([]), [active, setActive] = useState(true);
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [said, setSaid] = useState("");
  const [title, setTitle] = useState(draft?.config?.title || ""), [sched, setSched] = useState(() => scheduleOf(draft?.config || {}));
  const [drag, setDrag] = useState(null);       // {what: "sources"|"components", i}
  // the sources the rows on screen were read from, and the ones saved: a component edit redraws those rows in place, a source edit
  // reads them again (a ready one came drawn already - the demo refuses /preview, and it would be the same rows)
  const read = useRef(null), kept = useRef(null);
  const takeTemplate = (t) => {
    read.current = sigOf(t.config);
    setSpec(t.config); setData(t.data); setProblems(t.problems || []); setTitle(t.config.title || ""); setSched(scheduleOf(t.config));
    setNote({ severity: "info", text: t.explain || "" });
  };

  const fetchSaved = async () => {
    const { data: d } = await api.get(`/api/dashboards/${sourceId}`);
    read.current = kept.current = sigOf(d.config);
    setSpec(d.config); setData(d.data); setProblems(d.problems || []); setActive(d.active);
    return d;
  };
  useEffect(() => {
    if (sourceId == null) return;
    fetchSaved().then((d) => { setTitle(d.config.title || ""); setSched(scheduleOf(d.config)); })
      .catch((e) => setErr(errOf(e, "The dashboard could not be read.")));
  }, [sourceId]);   // eslint-disable-line react-hooks/exhaustive-deps
  // its sources are read over real rows before they are kept: they run now, nothing is saved. A draft's run at once; an edited
  // source's once the typing stops, so a half-written query is not run on every key
  const sig = sigOf(spec);
  useEffect(() => {
    if (!spec || sig === read.current || (sourceId != null && kept.current == null)) return;
    let live = true;
    const t = setTimeout(() => {
      setBusy("preview"); setErr("");
      api.post("/api/dashboards/preview", { config: spec })
        .then(({ data: d }) => { if (live) { read.current = sig; setData(d.data); setProblems(d.problems || []); } })
        .catch((e) => { if (live) setErr(errOf(e, "Its sources could not be read.")); })
        .finally(() => setBusy((b) => (b === "preview" ? "" : b)));
    }, read.current == null ? 0 : 1200);
    return () => { live = false; clearTimeout(t); };
  }, [sig, sourceId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const config = () => withSchedule({ ...spec, title: title.trim() || spec.title }, sched);
  const save = async () => {
    setBusy("save"); setErr(""); setSaid("");
    try {
      const c = config();
      const body = { Channel: "report", Address: c.title, ConfigJson: JSON.stringify(c), Active: sourceId == null ? true : active };
      if (sourceId != null) body.SourceId = sourceId;
      const { data: d } = await api.post("/api/sources", body);
      const sid = d.sourceId ?? sourceId;
      // a new one fills now, not at its first slot - and so does a saved one whose sources changed, so its rows are the ones it reads
      if (sourceId == null || sigOf(c) !== kept.current) await api.post(`/api/reports/${sid}/rerun`).catch(() => null);
      kept.current = sigOf(c);
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
      {sourceId == null ? <>
        <Composer kind="dashboard" onDraft={(config, meta) => {
          setSpec(config); setTitle(config.title || ""); setSched(scheduleOf(config));
          setNote({ severity: meta?.error || meta?.confidence === "low" ? "warning" : "info", text: meta?.error ? `${meta.error}.` : meta?.explain || "" });
        }} />
        <Templates onUse={takeTemplate} />
      </> : !err && <CircularProgress size={20} />}
    </Box>
  );

  const srcs = spec.sources || [], comps = spec.components || [];
  const setSrcs = (f) => setSpec((s) => ({ ...s, sources: f(s.sources || []) }));
  const setComps = (f) => setSpec((s) => ({ ...s, components: f(s.components || []) }));
  const setFilter = (k, v) => setSpec((s) => ({ ...s, filters: withField(s.filters || {}, k, v) }));
  const columns = Object.fromEntries(Object.entries(data?.sources || {}).map(([k, d]) => [k, d.columns || []]));
  const allCols = [...new Set(Object.values(columns).flat())].sort();
  const typeOptions = types.filter((t) => t.status === "builtin" && !NOT_ROWS.has(t.type));
  const move = (what, set, to) => { if (!drag || drag.what !== what || drag.i === to) return;
    set((cur) => { const n = [...cur]; const [m] = n.splice(drag.i, 1); n.splice(to, 0, m); return n; }); setDrag(null); };
  const shown = [...problems, ...orphans(spec).map((c) => `${c.title || DASH.kinds[c.kind]}: ${DASH.orphan}`)];
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
        {sourceId == null && <Button size="small" disabled={!!busy} onClick={() => { read.current = null; setSpec(null); setData(null); setNote(null); setProblems([]); }}>{DASH.again}</Button>}
        {sourceId != null && <Button size="small" disabled={!!busy} onClick={run}
          startIcon={busy === "run" ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}>{busy === "run" ? DASH.running : DASH.run}</Button>}
        {sourceId != null && <Button size="small" color="inherit" disabled={!!busy} onClick={remove} sx={{ color: FAINT }}>{DASH.remove}</Button>}
        {said && <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "#47654a" }}>{said}</Typography>}
        {busy === "preview" && data && <Typography sx={{ fontSize: 11.5, color: FAINT }}>{DASH.rereading}</Typography>}
        {data?.at && <Typography sx={{ fontSize: 11.5, color: FAINT, ml: "auto" }}>{DASH.updated} {dayLabel(data.at)} {fmtTime12(data.at)}</Typography>}
      </Box>
      {err && <Alert severity="error">{err}</Alert>}
      {shown.length > 0 && <Alert severity="warning" sx={{ fontSize: 12.5 }}>{shown.map((p) => <div key={p}>{p}</div>)}</Alert>}
      {busy === "preview" && !data ? <CircularProgress size={20} />
        // ...drawn afresh when what it opens on changes: the page's range and segment are its own state from then on
        : data ? <Dashboard key={`${spec.filters?.range}-${spec.filters?.segment}`} spec={spec} data={data} stale={busy === "run" || busy === "preview"} />
          : sourceId != null && <Typography sx={{ fontSize: 12.5, color: INK }}>{DASH.never}</Typography>}

      {/* ── what it reads: a report's own source cards, laid out as a report lays them (ReportsView.SourceCard) ── */}
      <Section title={DASH.sources} hint={DASH.sources_hint}>
        {srcs.map((s, i) => (
          <SourceCard key={s.key || i} src={s} index={i} count={srcs.length} typeOptions={typeOptions} connectors={connectors}
            dragging={drag?.what === "sources" && drag.i === i} onDragStart={() => setDrag({ what: "sources", i })} onDragEnd={() => setDrag(null)}
            onDropHere={() => move("sources", setSrcs, i)}
            onChange={(patch) => setSrcs((cur) => cur.map((x, k) => (k === i ? { ...x, ...patch } : x)))}
            onRetype={(t) => setSrcs((cur) => cur.map((x, k) => (k === i ? { type: t, key: x.key, label: x.label } : x)))}
            onFill={(one) => setSrcs((cur) => cur.map((x, k) => (k === i ? { ...one, ...(OWN_KEYS[one.type] && one.key ? { [OWN_KEYS[one.type].key]: one.key } : {}),
              key: x.key, label: one.label || x.label, date: one.date || x.date } : x)))}
            onCopy={srcs.length < MAX_SOURCES ? () => setSrcs((cur) => [...cur.slice(0, i + 1), { ...s, key: freshKey(cur), label: `${s.label || s.type} copy` }, ...cur.slice(i + 1)]) : undefined}
            onRemove={() => setSrcs((cur) => cur.filter((_, k) => k !== i))}
            renames={OWN_KEYS[s.type] || {}} test={<SourceTest src={runCfg(s)} />}
            extra={<ColumnField label={DASH.date} value={s.date} cols={columns[s.key] || []}
              onChange={(v) => setSrcs((cur) => cur.map((x, k) => (k === i ? withField(x, "date", v) : x)))} />} />
        ))}
        {srcs.length < MAX_SOURCES && <AddCard label={DASH.add_source} data-tq-dashboard-add-source=""
          onClick={() => setSrcs((cur) => [...cur, { key: freshKey(cur), label: DASH.datasets.tasks[0], type: "taskuary_data", dataset: "tasks", days: 90, date: "arrived" }])} />}
      </Section>

      {/* ── what it shows: one card per component, in the order the grid draws them ── */}
      <Section title={DASH.shows} hint={DASH.shows_hint}>
        <Box sx={{ width: "100%", display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.25 }}>
          <Typography variant="caption" sx={{ color: DIM }}>{DASH.opens_on}</Typography>
          <Select size="small" value={String(spec.filters?.range ?? 30)} onChange={(e) => setFilter("range", Number(e.target.value))}
            inputProps={{ "aria-label": DASH.opens_on }} sx={{ fontSize: 12.5, bgcolor: "#fff" }}>
            {RANGES.map((d) => <MenuItem key={d} value={String(d)} sx={{ fontSize: 12.5 }}>{DASH.ranges[String(d)]}</MenuItem>)}
          </Select>
          <Typography variant="caption" sx={{ color: DIM, ml: 1 }}>{DASH.slice_by}</Typography>
          <Box sx={{ width: 200 }}><ColumnField label="" placeholder={DASH.nothing} value={spec.filters?.segment} cols={allCols} onChange={(v) => setFilter("segment", v)} /></Box>
        </Box>
        {comps.map((c, i) => (
          <ComponentCard key={i} c={c} index={i} count={comps.length} sources={srcs} columns={columns}
            dragging={drag?.what === "components" && drag.i === i} onDragStart={() => setDrag({ what: "components", i })} onDragEnd={() => setDrag(null)}
            onDropHere={() => move("components", setComps, i)}
            onChange={(n) => setComps((cur) => cur.map((x, k) => (k === i ? n : x)))}
            onCopy={() => comps.length < MAX_COMPONENTS && setComps((cur) => [...cur.slice(0, i + 1), { ...c }, ...cur.slice(i + 1)])}
            onRemove={() => setComps((cur) => cur.filter((_, k) => k !== i))} />
        ))}
        {comps.length < MAX_COMPONENTS && <AddCard label={DASH.add} data-tq-dashboard-add-component=""
          onClick={() => setComps((cur) => [...cur, { kind: "stat", title: DASH.kinds.stat, source: srcs[0]?.key || "", agg: "count" }])} />}
      </Section>
    </Box>
  );
}
