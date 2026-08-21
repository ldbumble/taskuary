// Scheduled reports - the pipeline builder: pick a source (a connection from the
// Connectors tab, or an inline one), write the query, optionally an AI summary prompt,
// preview the whole pipeline, schedule it - results land on the Timeline. Connectors
// stay pure connections; this tab is where reports are built and managed.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, MenuItem, Select, Step, StepButton, StepContent,
  Stepper, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import BoltIcon from "@mui/icons-material/Bolt";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, card, mono, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, Empty, FilterPills } from "./ui.jsx";

const AI_FIELD = ["AI summary prompt (optional)", "ai_prompt", "multiline",
  "e.g. Summarize the census by facility. Flag anything under 70 and any day-over-day drop."];
const FIELDS = {
  mssql: [["query", "query", "multiline", "SELECT TOP 20 * FROM ..."], AI_FIELD],
  winrm: [["PowerShell to run on the remote box", "script", "multiline",
    "Get-Content C:/logs/latest.csv -Tail 20"], AI_FIELD],
  mcp: [["command", "cmd", "text", "npx / uvx / path to the MCP server"], ["args (one per line)", "args", "multiline", ""],
    ["tool", "tool", "text", "query"], ["tool args (JSON)", "tool_args", "multiline", '{"sql": "SELECT ..."}'], AI_FIELD],
  sqlite: [["db path", "db", "text", "C:/data/app.db"], ["query", "query", "multiline", "SELECT ..."], AI_FIELD],
  rest: [["url", "url", "text", "https://api.example.com/items"], ["headers (JSON)", "headers", "multiline", '{"Authorization": "Bearer ..."}'], ["json path", "path", "text", "data.items"], AI_FIELD],
  rss: [["feed url", "url", "text", "https://example.com/feed.xml"], AI_FIELD],
};
const TYPE_LABELS = {
  mssql: "SQL Server", winrm: "Remote Windows", mcp: "MCP server", sqlite: "SQLite", rest: "REST / JSON", rss: "RSS / Atom",
};
const BLANK = { type: "mssql", title: "", every_minutes: "", daily_at: "" };
const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const NL = String.fromCharCode(10);
// Everything that belongs to ONE source card; the rest (title, prompt, schedule) is the
// report itself. Splitting here is what lets old single-source configs load unchanged.
const SOURCE_KEYS = ["type", "label", "query", "script", "cmd", "args", "tool", "tool_args",
  "db", "url", "headers", "path", "max_rows", "server", "database", "auth", "username", "driver"];

const toSources = (cfg) => {
  if (Array.isArray(cfg.sources) && cfg.sources.length) return cfg.sources;
  const one = {};
  for (const k of SOURCE_KEYS) if (cfg[k] !== undefined && cfg[k] !== "") one[k] = cfg[k];
  return [{ type: cfg.type || "mssql", ...one }];
};

export default function ReportsView() {
  const [sources, setSources] = useState(null);
  const [types, setTypes] = useState([]);
  const [connectors, setConnectors] = useState([]);
  const [editing, setEditing] = useState(null);   // null = landing; {SourceId|null}
  const [syncing, setSyncing] = useState(false);
  const [note, setNote] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, t, c] = await Promise.all([api.get("/api/sources"), api.get("/api/report-types"), api.get("/api/connectors")]);
      setSources((s.data.data || []).filter((x) => x.Channel === "report"));
      setTypes(t.data.data || []); setConnectors(c.data.data || []);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load reports"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // a report run is synchronous and can take a while (a slow query, an AI pass) - say so
  // on the row that's working instead of leaving a dead button
  const [running, setRunning] = useState(null);
  const runNow = async (sid) => {
    setRunning(sid); setNote(null);
    try {
      const { data } = await api.post(`/api/sources/${sid}/run`);
      setNote({ ok: !String(data.subject).includes("FAILED"), detail: `filed on the Timeline: ${data.subject}` });
    } catch (e) { setNote({ ok: false, detail: e?.response?.data?.detail || "run failed" }); }
    setRunning(null); load();
  };
  const syncNow = async () => {
    setSyncing(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSyncing(false); load(); }, 3000); }
    catch { setSyncing(false); }
  };

  if (!sources) return <CircularProgress size={22} sx={{ m: 4 }} />;

  if (editing) {
    return <ReportWizard sourceId={editing.SourceId} sources={sources} types={types} connectors={connectors}
      reload={load} onBack={() => { setEditing(null); load(); }}
      onSaved={(sid) => setEditing({ SourceId: sid })} />;
  }

  return (
    <Box sx={{ maxWidth: 980 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", mb: 0.5 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, flex: 1 }}>Scheduled reports</Typography>
        <Button size="small" variant="outlined" disableElevation onClick={syncNow} disabled={syncing} sx={{ mr: 1 }}
          startIcon={syncing ? <CircularProgress size={12} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Running…" : "Run due now"}
        </Button>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => setEditing({ SourceId: null })}>New report</Button>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mb: 2 }}>
        A report is a pipeline: source → query → optional AI summary → your Timeline. Connections live on the Connectors tab.
      </Typography>
      {note && <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 600, color: note.ok ? "#15803d" : "#b91c1c" }}>{note.ok ? "✓" : "✗"} {note.detail}</Typography>}
      {!sources.length && <Empty>No reports yet — "New report" walks you through source, query, AI summary and schedule.</Empty>}
      {sources.map((s) => {
        const c = parse(s.ConfigJson);
        const sched = c.on_startup ? "on startup" : c.every_minutes ? `every ${c.every_minutes}m` : c.daily_at ? `daily ${c.daily_at}` : "daily";
        return (
          <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.5, borderBottom: `1px solid ${BORDER}` }}>
            <StatusDot ok={!!s.Active} />
            <ChannelIcon channel="report" />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }} noWrap>{c.title || s.Address}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT }}>
                {(c.sources || []).length > 1 ? `${c.sources.length} sources` : (TYPE_LABELS[c.type] || c.type || "rest")} · {sched}{s.LastPolledAt ? ` · ran ${timeAgo(s.LastPolledAt)}` : " · never ran"}
              </Typography>
            </Box>
            {c.ai_prompt && <Box sx={{ display: "flex", alignItems: "center", gap: 0.4, px: 1, py: 0.25, borderRadius: 99,
              bgcolor: "#fef4e6", border: "1px solid #f3ddb8" }}>
              <AutoAwesomeIcon sx={{ fontSize: 12, color: "#b45309" }} />
              <Typography variant="caption" sx={{ color: "#b45309", fontWeight: 700, fontSize: 10 }}>AI summary</Typography>
            </Box>}
            <Button size="small" disabled={running === s.SourceId}
              startIcon={running === s.SourceId ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}
              onClick={() => runNow(s.SourceId)}>{running === s.SourceId ? "Running…" : "Run now"}</Button>
            <Button size="small" onClick={() => setEditing({ SourceId: s.SourceId })}>Edit</Button>
            <Switch checked={!!s.Active} onChange={async () => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); load(); }} />
          </Box>
        );
      })}
    </Box>
  );
}

/* ── the pipeline wizard: source → configure → test & preview → schedule ── */
function ReportWizard({ sourceId, sources, types, connectors, reload, onBack, onSaved }) {
  const cur = sources.find((s) => s.SourceId === sourceId);
  const saved = cur ? { ...BLANK, ...parse(cur.ConfigJson) } : { ...BLANK };
  const [cfg, setCfg] = useState(saved);
  const [srcs, setSrcs] = useState(toSources(saved));   // the funnel's inputs, in order
  const [drag, setDrag] = useState(null);
  const [step, setStep] = useState(0);
  const [test, setTest] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [brains, setBrains] = useState([]);   // which AI writes THIS summary - same roster as triage
  useEffect(() => { api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {}); }, []);
  const mssqlConn = connectors.find((c) => c.Type === "mssql");
  const mssqlOk = mssqlConn?.LastSyncAt && !mssqlConn?.LastError;
  const winrmConn = connectors.find((c) => c.Type === "winrm");
  const winrmOk = winrmConn?.LastSyncAt && !winrmConn?.LastError;
  const aiActive = connectors.some((c) => ["anthropic", "openai", "azure_openai"].includes(c.Type) && c.Active && c.HasSecret);

  // one source card -> the shape an executor expects
  const cleanSource = (src) => {
    const c = { ...src };
    if (typeof c.args === "string") c.args = c.args.split(NL).map((x) => x.trim()).filter(Boolean);
    if (typeof c.headers === "string" && c.headers.trim()) { try { c.headers = JSON.parse(c.headers); } catch { /* preview will complain */ } }
    if (c.max_rows) c.max_rows = Number(c.max_rows);
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null) delete c[k];
    return c;
  };
  const bodyCfg = () => {
    const c = { ...cfg };
    for (const k of SOURCE_KEYS) delete c[k];            // sources live in sources[] now
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null) delete c[k];
    if (c.every_minutes) c.every_minutes = Number(c.every_minutes);
    const list = srcs.map(cleanSource).filter((x) => x.type);
    // a single source still writes the flat shape too, so a config saved here stays
    // readable by anything (and by an older Taskuary) that expects one source
    return list.length === 1 ? { ...c, ...list[0] } : { ...c, sources: list };
  };
  const runTest = async () => {
    setBusy("test"); setTest(null);
    try {
      const c = bodyCfg();
      if (c.type === "mssql") {
        const { data } = await api.post("/api/mssql/test", c);
        setTest(data.ok ? { ok: true, detail: `connected · ${data.version} · db ${data.database}` } : { ok: false, detail: data.error });
      } else if (c.type === "mcp") {
        const { data } = await api.post("/api/mcp/tools", c);
        setTest(data.ok ? { ok: true, detail: `server ok · tools: ${(data.data || []).map((t) => t.name).join(", ") || "(none)"}` } : { ok: false, detail: data.error });
      } else {
        const { data } = await api.post("/api/reports/preview", { ...c, ai_prompt: undefined });
        setTest(data.ok ? { ok: true, detail: data.headline } : { ok: false, detail: data.error });
      }
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy("");
  };
  const runPreview = async () => {
    setBusy("preview"); setPreview(null);
    try { setPreview((await api.post("/api/reports/preview", bodyCfg())).data); }
    catch (e) { setPreview({ ok: false, error: e?.response?.data?.detail || "preview failed" }); }
    setBusy("");
  };
  const save = async () => {
    const c = bodyCfg();
    if (!c.title) { setTest({ ok: false, detail: "title is required" }); return; }
    const body = { Channel: "report", Address: c.title, ConfigJson: JSON.stringify(c), Active: true };
    if (cur) body.SourceId = cur.SourceId;
    const { data } = await api.post("/api/sources", body);
    await reload(); onSaved(data.sourceId);
    setTest({ ok: true, detail: "saved ✓ — enabled and scheduled" });
  };

  const typeOptions = types.filter((t) => t.status === "builtin");
  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section="Reports" onBack={onBack} title={cur ? (parse(cur.ConfigJson).title || "Edit report") : "New report"} />
      <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
        <Step completed={srcs.some((x) => x.type)}>
          <StepButton onClick={() => setStep(0)}>Pipeline</StepButton>
          <StepContent>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1.5 }}>
              Sources at the top feed one prompt at the bottom. Add as many as you want — the same
              connection twice with different queries is fine, and every source's rows reach the
              summary together.
            </Typography>
            <TextField label="title — becomes the Timeline headline" value={cfg.title || ""} sx={{ bgcolor: "#fff", maxWidth: 560, mb: 2 }}
              fullWidth onChange={(e) => setCfg({ ...cfg, title: e.target.value })} />

            {/* ── the funnel: source cards, draggable, converging on the prompt ── */}
            <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "stretch" }}>
              {srcs.map((src, i) => (
                <SourceCard key={i} src={src} index={i} count={srcs.length}
                  typeOptions={typeOptions} connectors={connectors}
                  dragging={drag === i}
                  onDragStart={() => setDrag(i)} onDragEnd={() => setDrag(null)}
                  onDropHere={() => { if (drag === null || drag === i) return;
                    setSrcs((cur) => { const n = [...cur]; const [m] = n.splice(drag, 1); n.splice(i, 0, m); return n; }); setDrag(null); }}
                  onChange={(patch) => setSrcs((cur) => cur.map((x, k) => (k === i ? { ...x, ...patch } : x)))}
                  onRetype={(t) => setSrcs((cur) => cur.map((x, k) => (k === i ? { type: t, label: x.label } : x)))}
                  onCopy={() => setSrcs((cur) => [...cur.slice(0, i + 1), { ...src, label: `${src.label || src.type} copy` }, ...cur.slice(i + 1)])}
                  onRemove={() => setSrcs((cur) => cur.filter((_, k) => k !== i))} />
              ))}
              <Box onClick={() => setSrcs((cur) => [...cur, { type: "mssql" }])}
                sx={{ ...card, width: 300, minHeight: 120, display: "flex", flexDirection: "column", alignItems: "center",
                  justifyContent: "center", gap: 0.5, cursor: "pointer", borderStyle: "dashed",
                  color: DIM, "&:hover": { borderColor: "#c9cff0", color: "#4f46e5" } }}>
                <AddIcon sx={{ fontSize: 20 }} />
                <Typography variant="body2" sx={{ fontWeight: 600 }}>add a source</Typography>
              </Box>
            </Box>

            {/* everything above narrows into one prompt */}
            <Box sx={{ display: "flex", justifyContent: "center", py: 0.5 }}>
              <Box sx={{ width: 0, height: 0, borderLeft: "12px solid transparent", borderRight: "12px solid transparent",
                borderTop: `14px solid ${BORDER}` }} />
            </Box>
            <Box sx={{ ...card, p: 1.5, maxWidth: 720, bgcolor: "#fffdf7", borderColor: "#f3ddb8" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
                <AutoAwesomeIcon sx={{ fontSize: 15, color: "#b45309" }} />
                <Typography variant="caption" sx={{ color: "#b45309", fontWeight: 700 }}>
                  ONE PROMPT OVER ALL {srcs.length > 1 ? `${srcs.length} SOURCES` : "THE ROWS"}
                </Typography>
              </Box>
              <TextField fullWidth multiline minRows={3} value={cfg.ai_prompt || ""} sx={{ bgcolor: "#fff" }}
                placeholder={AI_FIELD[3]} onChange={(e) => setCfg({ ...cfg, ai_prompt: e.target.value })} />
              {cfg.ai_prompt && (
                <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Select size="small" displayEmpty value={cfg.ai_brain || ""} sx={{ bgcolor: "#fff", fontSize: 12.5, minWidth: 230 }}
                    onChange={(e) => setCfg({ ...cfg, ai_brain: e.target.value })}>
                    <MenuItem value="" sx={{ fontSize: 12 }}>the triage brain (default)</MenuItem>
                    {brains.filter((b) => b.value).map((b) => (
                      <MenuItem key={b.value} value={b.value} sx={{ fontSize: 12 }}>{b.label}</MenuItem>
                    ))}
                  </Select>
                  <TextField size="small" label="model override (optional)" value={cfg.ai_model || ""}
                    sx={{ bgcolor: "#fff", width: 210 }}
                    onChange={(e) => setCfg({ ...cfg, ai_model: e.target.value })} />
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    which AI writes this summary — a heavier model for the weekly review, the cheap tier for pings
                  </Typography>
                </Box>
              )}
              {cfg.ai_prompt && !aiActive && !cfg.ai_brain && (
                <Typography variant="body2" sx={{ mt: 0.75, fontWeight: 600, color: "#b45309" }}>
                  ⚠ AI prompt set, but no active AI connector — the raw data will file until you enable one (Connectors → AI).
                </Typography>
              )}
              {!cfg.ai_prompt && (
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                  Leave it empty to file the raw rows with no AI pass.
                </Typography>
              )}
            </Box>
            <Box sx={{ mt: 1.5 }}><Button variant="contained" disableElevation onClick={() => setStep(1)}>Continue</Button></Box>
          </StepContent>
        </Step>
        <Step completed={!!test?.ok || !!preview?.ok}>
          <StepButton onClick={() => setStep(1)}>Test & preview</StepButton>
          <StepContent>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1 }}>
              Test checks the source; Preview runs the whole pipeline — query + AI — exactly like a scheduled run, without filing anything.
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
                startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test source</Button>
              <Button variant="outlined" disabled={busy === "preview"} onClick={runPreview}
                startIcon={busy === "preview" ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 15 }} />}>Preview pipeline</Button>
              <Button onClick={() => setStep(2)}>Continue</Button>
            </Box>
            {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>{test.ok ? "✓" : "✗"} {test.detail}</Typography>}
            {preview && (preview.ok ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: "#15803d" }}>✓ {preview.headline}</Typography>
                <Box component="pre" sx={{ ...mono, whiteSpace: "pre-wrap", bgcolor: PANEL2, border: `1px solid ${BORDER}`,
                  borderRadius: 1.5, p: 1.25, fontSize: 11, maxHeight: 260, overflow: "auto", color: INK }}>{preview.summary}</Box>
                {/* the chart is half of what a scheduled run hands back, so the dry run shows it too -
                    rendered in memory server-side, since a preview files no message to attach it to */}
                {preview.chart && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
                      The chart this report will hand back, from {preview.rows} row{preview.rows === 1 ? "" : "s"}:
                    </Typography>
                    <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "auto", bgcolor: "#fff" }}
                      dangerouslySetInnerHTML={{ __html: preview.chart }} />
                  </Box>
                )}
              </Box>
            ) : <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "#b91c1c" }}>✗ {preview.error}</Typography>)}
          </StepContent>
        </Step>
        <Step completed={!!cur}>
          <StepButton onClick={() => setStep(2)}>Schedule & save</StepButton>
          <StepContent>
            <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center", flexWrap: "wrap" }}>
              <TextField label="every N minutes" type="number" value={cfg.every_minutes || ""} sx={{ bgcolor: "#fff", width: 150 }}
                onChange={(e) => setCfg({ ...cfg, every_minutes: e.target.value, daily_at: "", on_startup: false })} />
              <TextField label="or daily at HH:MM" value={cfg.daily_at || ""} sx={{ bgcolor: "#fff", width: 150 }}
                onChange={(e) => setCfg({ ...cfg, daily_at: e.target.value, every_minutes: "", on_startup: false })} />
              <Box sx={{ display: "flex", alignItems: "center" }}
                title="It's local — opening the app IS a schedule. Runs once per launch, after the startup catch-up.">
                <Switch checked={!!cfg.on_startup}
                  onChange={(e) => setCfg({ ...cfg, on_startup: e.target.checked,
                    ...(e.target.checked ? { every_minutes: "", daily_at: "" } : {}) })} />
                <Typography variant="caption" sx={{ color: DIM }}>or on app startup</Typography>
              </Box>
              <Button variant="contained" disableElevation onClick={save}>Save report</Button>
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
              All three blank = once a day, whenever the app is open.
            </Typography>
            {test?.detail?.includes("saved") && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "#15803d" }}>✓ {test.detail}</Typography>}
            {cur && (
              <Box sx={{ display: "flex", gap: 1, mt: 1.5, alignItems: "center" }}>
                <Button size="small" color="error" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />}
                  onClick={async () => { await api.delete(`/api/sources/${cur.SourceId}`); reload(); onBack(); }}>Delete report</Button>
              </Box>
            )}
          </StepContent>
        </Step>
      </Stepper>
    </Box>
  );
}

/* One input to the funnel: what it is, what to ask it, and (optionally) a label so the
   AI can tell two queries against the same database apart. Drag to reorder. */
function SourceCard({ src, index, count, typeOptions, connectors, dragging, onDragStart, onDragEnd,
                      onDropHere, onChange, onRetype, onCopy, onRemove }) {
  const fields = (FIELDS[src.type] || []).filter(([, key]) => key !== "ai_prompt");
  const conn = connectors.find((c) => c.Type === src.type);
  const needsConn = ["mssql", "winrm"].includes(src.type);
  const connOk = conn?.LastSyncAt && !conn?.LastError;
  return (
    <Box draggable onDragStart={onDragStart} onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()} onDrop={onDropHere}
      sx={{ ...card, width: 300, p: 1.25, display: "flex", flexDirection: "column", gap: 1,
        opacity: dragging ? 0.45 : 1, cursor: "grab", "&:active": { cursor: "grabbing" } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <DragIndicatorIcon sx={{ fontSize: 16, color: "#c2c9d6" }} />
        <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1 }}>source {index + 1} of {count}</Typography>
        <ContentCopyIcon onClick={onCopy} titleAccess="Duplicate — same connection, different query"
          sx={{ fontSize: 14, color: FAINT, cursor: "pointer", "&:hover": { color: "#4f46e5" } }} />
        {count > 1 && <CloseIcon onClick={onRemove} titleAccess="Remove this source"
          sx={{ fontSize: 15, color: FAINT, cursor: "pointer", "&:hover": { color: "#b91c1c" } }} />}
      </Box>
      <Select size="small" value={src.type || "mssql"} onChange={(e) => onRetype(e.target.value)}
        sx={{ fontSize: 12.5, bgcolor: "#fff" }}>
        {typeOptions.map((t) => (
          <MenuItem key={t.type} value={t.type} sx={{ fontSize: 12.5 }}>{TYPE_LABELS[t.type] || t.type}</MenuItem>
        ))}
      </Select>
      {needsConn && (
        <Typography variant="caption" sx={{ fontWeight: 600, color: connOk ? "#15803d" : "#b45309" }}>
          {connOk ? `✓ uses the ${TYPE_LABELS[src.type]} connection from Connectors`
            : `⚠ set up Connectors → ${TYPE_LABELS[src.type]} first`}
        </Typography>
      )}
      {count > 1 && (
        <TextField size="small" label="label" value={src.label || ""} sx={{ bgcolor: "#fff" }}
          placeholder="cash balances" onChange={(e) => onChange({ label: e.target.value })} />
      )}
      {fields.map(([label, key, kind, ph]) => {
        const v = src[key];
        const shown = Array.isArray(v) ? v.join(NL) : typeof v === "object" && v ? JSON.stringify(v) : (v ?? "");
        return <TextField key={key} size="small" label={label} placeholder={ph} value={shown} sx={{ bgcolor: "#fff" }}
          multiline={kind === "multiline"} minRows={kind === "multiline" ? 3 : undefined}
          inputProps={kind === "multiline" ? { style: { fontFamily: "Consolas, monospace", fontSize: 11.5 } } : undefined}
          onChange={(e) => onChange({ [key]: e.target.value })} />;
      })}
      {/* blank is not "no cap" - it is the 200-row default, and the field has to say so or
          the timeline's "capped at 200" points at a setting you never made */}
      <TextField size="small" label="max rows" type="number" placeholder="200" value={src.max_rows ?? ""}
        helperText="blank = 200 (the default). Raise it to send more rows to the prompt."
        sx={{ bgcolor: "#fff", width: 300 }} onChange={(e) => onChange({ max_rows: e.target.value })} />
    </Box>
  );
}
