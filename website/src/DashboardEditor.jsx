// A DASHBOARD ON THE REPORTS PAGE: set up with AI like a report (describe it, the composer proposes sources and presets, the owner
// sees it drawn over REAL rows and saves it), then its name, its refresh and its buttons. Nothing runs an AI after the save - each
// refresh re-reads the sources (dashboards.py). The composer's words land here; the buttons do the talking.
// ...and every one is CONFIGURABLE (the owner, 2026-10-24: "it should be configurable ... with sources layout like reports"): its
// sources are a report's source cards, its components are cards beside them, and the built-in one is edited like any other.
// ...and A TILE IS ONE SENTENCE (the owner, 2026-11-06, of the field grid each component had: "it's useless ... it's not generalized ...
// maybe we should just use text to say what it shows"): the owner writes what a tile shows, the AI binds it to the sources once
// (POST /api/dashboards/tile) and it draws in place. The page set up is the page drawn - each tile under its own sentence.
import React, { useEffect, useRef, useState } from "react";
import { Alert, Autocomplete, Box, Button, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import api from "./api";
import SetupWithAi from "./SetupWithAi.jsx";
import Dashboard from "./dashboard/Dashboard.jsx";
import { RANGES } from "./dashboard/slice.js";
import { MAX_COMPONENTS, MAX_SOURCES, OWN_KEYS, copyTile, runCfg, freshKey, orphans, saidOf, sigOf, swapTile, tileAsk, wantsDrawing, withField } from "./dashboard/setup.js";
import { useCapabilities } from "./capabilities.js";
import { SourceCard, SourceTest } from "./ReportsView.jsx";
import { WORKFLOW_TYPES } from "./sourceShape.js";
import { SchedulePicker, scheduleOf, withSchedule } from "./WorkflowEditor.jsx";
import { removeNow } from "./Removed.jsx";
import { DASH } from "./words.js";
import { BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { dayLabel } from "./dates.js";
import { fmtTime12 } from "./ui.jsx";

const errOf = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

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
        <Box key={t.key} sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "var(--tq-panel, #fffdfb)" }}>
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
  const input = (p) => <TextField {...p} label={label || undefined} placeholder={placeholder} sx={{ bgcolor: "var(--tq-panel, #fff)" }}
    inputProps={{ ...p.inputProps, "aria-label": label || placeholder }} />;
  return multiple
    ? <Autocomplete multiple freeSolo size="small" options={cols} value={value || []} onChange={(_e, v) => onChange(v)} renderInput={input} />
    : <Autocomplete freeSolo size="small" options={cols} value={value ?? ""} inputValue={value ?? ""}
        onInputChange={(_e, v) => { if (v !== (value ?? "")) onChange(v); }} renderInput={input} />;
}

// ONE TILE'S SENTENCE: the owner's words, drawn into a tile on Enter or on leaving the line ("drawing…" while the AI binds it), and the
// AI's no said under it in plain words. The words stay as typed when it fails, to be said another way. No AI: the line only reads.
export function SaidLine({ c = null, canAsk, ask, onDrawn, placeholder, clearOnDraw = false }) {
  const [text, setText] = useState(saidOf(c)), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  useEffect(() => { setText(saidOf(c)); setErr(""); }, [c]);     // drawn, or another tile dragged into this place
  const draw = async () => {
    if (!canAsk || busy || !wantsDrawing(text, c)) return;
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/api/dashboards/tile", ask(text.trim()));
      if (data?.component) { onDrawn(data.component); if (clearOnDraw) setText(""); }
      else setErr(data?.error || "It could not be drawn.");
    } catch (e) { setErr(errOf(e, "It could not be drawn.")); }
    setBusy(false);
  };
  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <TextField variant="standard" fullWidth multiline maxRows={3} value={text} placeholder={placeholder} disabled={busy}
        onChange={(e) => setText(e.target.value)} onBlur={draw}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); draw(); } }}
        InputProps={{ readOnly: !canAsk, sx: { fontSize: 13, color: INK, lineHeight: 1.4 } }} inputProps={{ "aria-label": placeholder || DASH.said }} />
      {busy && <Typography sx={{ fontSize: 11.5, color: FAINT, mt: 0.25 }}>{DASH.drawing}</Typography>}
      {err && <Typography role="alert" sx={{ fontSize: 12, color: "var(--tq-danger, #8a3b2f)", mt: 0.25 }}>{err}</Typography>}
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
    justifyContent: "center", gap: 0.5, cursor: "pointer", borderStyle: "dashed", color: DIM, "&:hover": { borderColor: "var(--tq-border, #d8cfbe)", color: "var(--tq-link, #55697a)" } }}>
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
  const canAsk = useCapabilities().ai !== false;  // no AI: a tile is moved, copied or removed, never added or changed
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
        {/* the describe box is the chat's now (2026-10-30): its door, and the Assistant's draft lands here as New's did (ReportsView compose) */}
        <SetupWithAi kind="dashboard" sx={{ mb: 2 }} />
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
  const shown = [...problems, ...orphans(spec).map((c) => `${c.title || saidOf(c)}: ${DASH.orphan}`)];
  const icon = { fontSize: 14, color: FAINT, cursor: "pointer", flex: "none", mt: 0.5 };
  // each tile drawn under its sentence, with its move, Copy and Remove; the answer lands on the tile asked about wherever it went since
  const frame = (c, i, node, w) => (
    <div className={`tq-dash-frame w${w}${drag?.what === "components" && drag.i === i ? " dragging" : ""}`} data-tq-dash-tile={i}
      onDragOver={(e) => e.preventDefault()} onDrop={() => move("components", setComps, i)}>
      {/* two lines held for every sentence, so the tiles of one row start level whatever their words' length */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.5, minHeight: 44 }}>
        <Box draggable onDragStart={() => setDrag({ what: "components", i })} onDragEnd={() => setDrag(null)} title={DASH.move}
          sx={{ cursor: "grab", flex: "none", mt: 0.5, "&:active": { cursor: "grabbing" } }}><DragIndicatorIcon sx={{ fontSize: 16, color: "var(--tq-muted, #cfc9bf)" }} /></Box>
        <SaidLine c={c} canAsk={canAsk} ask={(t) => tileAsk(spec, t, c)} onDrawn={(n) => setComps((cur) => swapTile(cur, c, n))} />
        {comps.length < MAX_COMPONENTS && <ContentCopyIcon onClick={() => setComps((cur) => copyTile(cur, i))} titleAccess={DASH.copy}
          sx={{ ...icon, "&:hover": { color: "var(--tq-link, #55697a)" } }} />}
        <CloseIcon onClick={() => setComps((cur) => cur.filter((_, k) => k !== i))} titleAccess={DASH.remove_tile}
          sx={{ ...icon, fontSize: 15, "&:hover": { color: "var(--tq-danger, #6b2733)" } }} />
      </Box>
      {node}
    </div>
  );
  const addTile = canAsk && comps.length < MAX_COMPONENTS && (
    <div className="tq-dash-add" data-tq-dashboard-add-tile="">
      <SaidLine canAsk ask={(t) => tileAsk(spec, t)} onDrawn={(n) => setComps((cur) => [...cur, n])} placeholder={DASH.add_tile} clearOnDraw />
    </div>
  );
  return (
    <Box data-tq-dashboard-editor="" sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
      {note?.text && <Alert severity={note.severity} onClose={() => setNote(null)} sx={{ fontSize: 12.5 }}>{note.text}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
        <TextField size="small" value={title} onChange={(e) => setTitle(e.target.value)} sx={{ bgcolor: "var(--tq-panel, #fff)", minWidth: 220, flex: "1 1 220px" }}
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
        {said && <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "var(--tq-success, #47654a)" }}>{said}</Typography>}
        {busy === "preview" && data && <Typography sx={{ fontSize: 11.5, color: FAINT }}>{DASH.rereading}</Typography>}
        {data?.at && <Typography sx={{ fontSize: 11.5, color: FAINT, ml: "auto" }}>{DASH.updated} {dayLabel(data.at)} {fmtTime12(data.at)}</Typography>}
      </Box>
      {err && <Alert severity="error">{err}</Alert>}
      {shown.length > 0 && <Alert severity="warning" sx={{ fontSize: 12.5 }}>{shown.map((p) => <div key={p}>{p}</div>)}</Alert>}

      {/* THE SETTINGS GO ABOVE THE DASHBOARD (the owner, 2026-10-25): what it reads first, then what it shows - the page itself, set up in place */}
      {/* ── what it reads: a report's own source cards, laid out as a report lays them (ReportsView.SourceCard) ── */}
      <Section title={DASH.sources} hint={DASH.sources_hint}>
        {srcs.map((s, i) => (
          <SourceCard key={s.key || i} src={s} index={i} count={srcs.length} typeOptions={typeOptions} connectors={connectors} ownSwitch
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

      {/* ── what it shows: the dashboard drawn, each tile under its sentence, the add box closing its grid ── */}
      <Section title={DASH.shows} hint={DASH.shows_hint}>
        <Box sx={{ width: "100%", display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.25 }}>
          <Typography variant="caption" sx={{ color: DIM }}>{DASH.opens_on}</Typography>
          <Select size="small" value={String(spec.filters?.range ?? 30)} onChange={(e) => setFilter("range", Number(e.target.value))}
            inputProps={{ "aria-label": DASH.opens_on }} sx={{ fontSize: 12.5, bgcolor: "var(--tq-panel, #fff)" }}>
            {RANGES.map((d) => <MenuItem key={d} value={String(d)} sx={{ fontSize: 12.5 }}>{DASH.ranges[String(d)]}</MenuItem>)}
          </Select>
          <Typography variant="caption" sx={{ color: DIM, ml: 1 }}>{DASH.slice_by}</Typography>
          <Box sx={{ width: 200 }}><ColumnField label="" placeholder={DASH.nothing} value={spec.filters?.segment} cols={allCols} onChange={(v) => setFilter("segment", v)} /></Box>
        </Box>
        {!canAsk && <Typography data-tq-dashboard-no-ai="" sx={{ width: "100%", fontSize: 12, color: FAINT }}>{DASH.no_ai_tiles}</Typography>}
        {!data && sourceId != null && busy !== "preview" && <Typography sx={{ width: "100%", fontSize: 12.5, color: INK }}>{DASH.never}</Typography>}
        {/* ...drawn afresh when what it opens on changes: the page's range and segment are its own state from then on */}
        <Box data-tq-dashboard-preview="" sx={{ width: "100%", minWidth: 0 }}>
          <Dashboard key={`${spec.filters?.range}-${spec.filters?.segment}`} spec={spec} data={data} stale={busy === "run" || busy === "preview"}
            frame={frame} after={addTile} />
        </Box>
      </Section>
    </Box>
  );
}
