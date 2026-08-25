// Scheduled reports - the pipeline builder: pick a source (a connection from the
// Connectors tab, or an inline one), write the query, optionally an AI summary prompt,
// preview the whole pipeline, schedule it - results land on the Timeline. Connectors
// stay pure connections; this tab is where reports are built and managed.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, CircularProgress, Dialog, DialogContent, DialogTitle,
  MenuItem, Select, Step, StepButton, StepContent, Stepper, Switch, TextField, Typography,
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
  database: [["query", "query", "multiline", "SELECT ... (any SQL the connected engine speaks)"], AI_FIELD],
  // service and operation are PICKED, not typed - see AwsPicker. botocore ships both lists
  // locally, so getting a name wrong no longer waits until a scheduled run fails to tell you.
  aws: [["service", "service", "aws_service", "s3 · logs · ec2 · athena · dynamodb ..."],
    ["operation", "operation", "aws_operation", "list_buckets · describe_instances ..."],
    ["params (JSON)", "params", "multiline", '{"Bucket": "my-bucket"}'],
    ["path into the response", "path", "text", "Contents"], AI_FIELD],
  s3_object: [["bucket", "bucket", "text", "my-bucket"],
    ["key — read this object (blank = list instead)", "key", "text", "reports/latest.csv"],
    ["prefix — list under this", "prefix", "text", "reports/"], AI_FIELD],
  cloudwatch_logs: [["log group", "log_group", "text", "/aws/lambda/my-fn"],
    ["filter pattern (optional)", "pattern", "text", "?ERROR ?Exception"],
    ["hours back", "hours", "text", "24"], AI_FIELD],
  azure: [["ARM path (or full URL)", "path", "multiline", "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Web/sites"],
    ["api-version", "api_version", "text", "2022-12-01"], AI_FIELD],
  azure_blob: [["storage account", "account", "text", "mystorageacct"],
    ["container", "container", "text", "reports"],
    ["blob — read this one (blank = list instead)", "blob", "text", "latest.csv"],
    ["prefix — list under this", "prefix", "text", ""], AI_FIELD],
  azure_logs: [["workspace id", "workspace_id", "text", "the Log Analytics workspace GUID"],
    ["KQL query", "query", "multiline", "AppExceptions | where TimeGenerated > ago(1d) | take 50"],
    ["hours back", "hours", "text", "24"], AI_FIELD],
  entra_users: [["OData filter (optional)", "filter", "text", "accountEnabled eq false"],
    ["properties to select (optional)", "select", "text", "displayName,userPrincipalName,accountEnabled,department"], AI_FIELD],
  entra_groups: [["group name or id (blank = list every group)", "group", "text", "All Staff"], AI_FIELD],
  entra_signins: [["hours back", "hours", "text", "24"],
    ["failed only (1 = just the failures)", "failed_only", "text", "1"], AI_FIELD],
  entra_licenses: [AI_FIELD],
  automate: [["days back", "days", "text", "30"], AI_FIELD],
  prometheus: [["PromQL query", "query", "multiline", 'up == 0   ·   sum(rate(http_requests_total[5m])) by (service)'], AI_FIELD],
  datadog: [["monitor name filter (blank = all monitors, trouble first)", "name", "text", "prod"], AI_FIELD],
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
  database: "Any database", aws: "AWS (any call)", s3_object: "S3 object", cloudwatch_logs: "CloudWatch logs",
  azure: "Azure (ARM)", azure_blob: "Azure blob", azure_logs: "Azure Log Analytics",
  entra_users: "Entra ID — people", entra_groups: "Entra ID — group members",
  entra_signins: "Entra ID — sign-ins", entra_licenses: "Entra ID — licence seats",
  prometheus: "Prometheus", datadog: "Datadog monitors",
  digest: "Taskuary digest", automate: "Automation ideas (own data)",
};
// which connector CARD a type's credentials live on (mirrors reports.card_of server-side)
const CARD_OF = { s3_object: "aws", cloudwatch_logs: "aws", azure_blob: "azure", azure_logs: "azure",
  entra_users: "azure", entra_groups: "azure", entra_signins: "azure", entra_licenses: "azure" };
const CARD_LABELS = { mssql: "SQL Server", winrm: "Remote Windows", database: "Any database", aws: "AWS", azure: "Azure",
  prometheus: "Prometheus", datadog: "Datadog" };
const BLANK = { type: "mssql", title: "", every_minutes: "", daily_at: "" };
const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const NL = String.fromCharCode(10);
// Everything that belongs to ONE source card; the rest (title, prompt, schedule) is the
// report itself. Splitting here is what lets old single-source configs load unchanged.
const SOURCE_KEYS = ["type", "label", "query", "script", "cmd", "args", "tool", "tool_args",
  "db", "url", "headers", "path", "max_rows", "server", "database", "auth", "username", "driver",
  "service", "operation", "params", "bucket", "key", "prefix", "log_group", "pattern", "hours",
  "api_version", "path_expr", "account", "container", "blob", "workspace_id",
  "filter", "select", "group", "failed_only", "days"];

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
        const sched = c.on_startup ? "on startup" : c.cron ? `cron ${c.cron}`
          : c.every_minutes ? `every ${c.every_minutes}m` : c.daily_at ? `daily ${c.daily_at}` : "daily";
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
    if (typeof c.params === "string" && c.params.trim()) { try { c.params = JSON.parse(c.params); } catch { /* preview will complain */ } }
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
                    {/* only brains that can actually answer: a connector with no key saved is
                        not a choice, it is a trap. A saved pick that lost its key stays
                        visible - disabled - instead of silently vanishing. Labels are worded
                        for THIS context: picking a CLI here runs it for this report only. */}
                    {brains.filter((b) => b.value && b.ready).map((b) => (
                      <MenuItem key={b.value} value={b.value} sx={{ fontSize: 12 }}>{b.label}</MenuItem>
                    ))}
                    {cfg.ai_brain && !brains.some((b) => b.value === cfg.ai_brain && b.ready) && (
                      <MenuItem value={cfg.ai_brain} disabled sx={{ fontSize: 12 }}>
                        {cfg.ai_brain.startsWith("cli:") ? cfg.ai_brain.slice(4)
                          : (brains.find((b) => b.value === cfg.ai_brain) || {}).label || cfg.ai_brain} — not connected
                      </MenuItem>
                    )}
                  </Select>
                  {/* the chosen brain knows its models - a dropdown, free typing for the rest */}
                  <Autocomplete freeSolo size="small" sx={{ width: 230 }}
                    options={(brains.find((b) => b.value === (cfg.ai_brain || "")) || {}).models || []}
                    value={cfg.ai_model || ""}
                    onChange={(_e, v) => setCfg({ ...cfg, ai_model: v || "" })}
                    onInputChange={(_e, v, why) => { if (why === "input") setCfg({ ...cfg, ai_model: v }); }}
                    renderInput={(params) => (
                      <TextField {...params} label="model (optional — the brain's default)" sx={{ bgcolor: "#fff" }} />
                    )} />
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
              <TextField label="every N minutes" type="number" value={cfg.every_minutes || ""} sx={{ bgcolor: "#fff", width: 140 }}
                onChange={(e) => setCfg({ ...cfg, every_minutes: e.target.value, daily_at: "", cron: "", on_startup: false })} />
              <TextField label="daily at HH:MM" value={cfg.daily_at || ""} sx={{ bgcolor: "#fff", width: 140 }}
                onChange={(e) => setCfg({ ...cfg, daily_at: e.target.value, every_minutes: "", cron: "", on_startup: false })} />
              <TextField label="cron (min hr dom mon dow)" value={cfg.cron || ""} sx={{ bgcolor: "#fff", width: 190 }}
                placeholder="0 8 * * 1-5"
                title="Standard 5-field cron. A slot missed while the app was closed fires once on reopen."
                onChange={(e) => setCfg({ ...cfg, cron: e.target.value, every_minutes: "", daily_at: "", on_startup: false })} />
              <Box sx={{ display: "flex", alignItems: "center" }}
                title="It's local — opening the app IS a schedule. Runs once per launch, after the startup catch-up.">
                <Switch checked={!!cfg.on_startup}
                  onChange={(e) => setCfg({ ...cfg, on_startup: e.target.checked,
                    ...(e.target.checked ? { every_minutes: "", daily_at: "", cron: "" } : {}) })} />
                <Typography variant="caption" sx={{ color: DIM }}>or on app startup</Typography>
              </Box>
              <Button variant="contained" disableElevation onClick={save}>Save report</Button>
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
              Pick one. Everything blank = once a day, whenever the app is open.
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

/* AWS service and operation, picked from botocore's own models - fetched once per card, and
   again per service for its operations. No AWS call is made to build either list.

   `seen` are the services discovery actually found objects for in THIS account, and they are
   pinned to the top of a 430-name alphabetical list, because the list is otherwise a haystack.
   freeSolo stays on: a service too new for the installed botocore must still be typeable. */
function AwsPicker({ label, which, value, placeholder, service, onChange }) {
  const [cat, setCat] = useState(null);
  useEffect(() => {
    const q = which === "aws_operation" ? (service ? `?service=${encodeURIComponent(service)}` : null) : "";
    if (q === null) { setCat({ options: [], seen: [] }); return; }
    api.get(`/api/aws/catalog${q}`)
      .then(({ data }) => setCat({
        options: which === "aws_operation" ? (data.operations || []) : (data.services || []),
        seen: which === "aws_operation" ? (data.read || []) : (data.seen || []),
        error: data.error,
      }))
      .catch(() => setCat({ options: [], seen: [] }));
  }, [which, service]);
  const opts = cat?.options || [];
  const seen = new Set(cat?.seen || []);
  // the ones this account demonstrably uses (or the read-only operations) sort first
  const sorted = [...opts].sort((a, b) => (seen.has(b) ? 1 : 0) - (seen.has(a) ? 1 : 0));
  return (
    <Autocomplete freeSolo autoHighlight options={sorted} value={value ?? ""} size="small"
      onChange={(_e, v) => onChange(v ?? "")} onInputChange={(_e, v, reason) => reason === "input" && onChange(v)}
      groupBy={(o) => (seen.has(o)
        ? (which === "aws_operation" ? "reads only — safe for a report" : "your keys already see these")
        : (which === "aws_operation" ? "everything else this service does" : "everything botocore knows"))}
      renderInput={(params) => (
        <TextField {...params} label={label} placeholder={placeholder} sx={{ bgcolor: "#fff" }}
          helperText={which === "aws_operation" && !service ? "pick a service first"
            : cat?.error ? cat.error : undefined} />
      )} />
  );
}

/* "What does this actually return?" - answerable on the card now, before the whole pipeline is
   assembled and without the AI pass in the way. The wizard's own Test showed the HEADLINE only
   ("12 items"), which is the one thing you can already guess; the rows are the question. */
function SourceTest({ src }) {
  const [out, setOut] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    const c = { ...src, title: "test" };
    if (typeof c.params === "string" && c.params.trim()) { try { c.params = JSON.parse(c.params); } catch { /* the server says so */ } }
    if (c.max_rows) c.max_rows = Number(c.max_rows);
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null) delete c[k];
    try {
      const { data } = await api.post("/api/reports/preview", { ...c, ai_prompt: undefined });
      setOut(data);
    } catch (e) { setOut({ ok: false, error: e?.response?.data?.detail || "the call failed" }); }
    setBusy(false);
  };
  return (
    <>
      <Button size="small" onClick={run} disabled={busy} startIcon={busy ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}
        sx={{ fontSize: 11.5, alignSelf: "flex-start" }}>{busy ? "calling…" : "Test — show me the data"}</Button>
      <Dialog open={!!out} onClose={() => setOut(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          {out?.ok ? out.headline || "it returned nothing" : "that call did not work"}
        </DialogTitle>
        <DialogContent>
          {out?.ok ? (
            <>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.75 }}>
                exactly what a scheduled run would hand the prompt{out.rows ? ` — ${out.rows} rows` : ""}
              </Typography>
              <Box component="pre" sx={{ ...mono, fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-word",
                bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1, p: 1, m: 0, maxHeight: 460, overflow: "auto" }}>
                {out.summary || "(the call succeeded and returned no rows)"}
              </Box>
            </>
          ) : <Alert severity="error" sx={{ fontSize: 12.5 }}>{out?.error}</Alert>}
        </DialogContent>
      </Dialog>
    </>
  );
}

/* One input to the funnel: what it is, what to ask it, and (optionally) a label so the
   AI can tell two queries against the same database apart. Drag to reorder. */
function SourceCard({ src, index, count, typeOptions, connectors, dragging, onDragStart, onDragEnd,
                      onDropHere, onChange, onRetype, onCopy, onRemove }) {
  const fields = (FIELDS[src.type] || []).filter(([, key]) => key !== "ai_prompt");
  const cardType = CARD_OF[src.type] || src.type;
  const conn = connectors.find((c) => c.Type === cardType);
  const needsConn = ["mssql", "winrm", "database", "aws", "azure", "prometheus", "datadog"].includes(cardType);
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
          {connOk ? `✓ uses the ${CARD_LABELS[cardType] || cardType} connection from Connectors`
            : `⚠ set up Connectors → ${CARD_LABELS[cardType] || cardType} first`}
        </Typography>
      )}
      {count > 1 && (
        <TextField size="small" label="label" value={src.label || ""} sx={{ bgcolor: "#fff" }}
          placeholder="cash balances" onChange={(e) => onChange({ label: e.target.value })} />
      )}
      {fields.map(([label, key, kind, ph]) => {
        const v = src[key];
        const shown = Array.isArray(v) ? v.join(NL) : typeof v === "object" && v ? JSON.stringify(v) : (v ?? "");
        if (kind === "aws_service" || kind === "aws_operation") {
          return <AwsPicker key={key} label={label} which={kind} value={shown} placeholder={ph}
            service={src.service} onChange={(x) => onChange({ [key]: x })} />;
        }
        return <TextField key={key} size="small" label={label} placeholder={ph} value={shown} sx={{ bgcolor: "#fff" }}
          multiline={kind === "multiline"} minRows={kind === "multiline" ? 3 : undefined}
          inputProps={kind === "multiline" ? { style: { fontFamily: "Consolas, monospace", fontSize: 11.5 } } : undefined}
          onChange={(e) => onChange({ [key]: e.target.value })} />;
      })}
      {/* blank is not "no cap" - it is the 200-row default, and the field has to say so or
          the timeline's "capped at 200" points at a setting you never made */}
      {/* blank is not "no cap" - it is the 200-row default, and the field has to say so or
          the timeline's "capped at 200" points at a setting you never made. It applies whenever
          the call comes back as a LIST (list_buckets, describe_instances, a SQL result) and does
          nothing at all when it comes back as one object - which the Test below makes obvious. */}
      <TextField size="small" label="max rows" type="number" placeholder="200" value={src.max_rows ?? ""}
        helperText="blank = 200. Only bites when the result is a list — Test shows which you have."
        sx={{ bgcolor: "#fff", width: 300 }} onChange={(e) => onChange({ max_rows: e.target.value })} />
      <SourceTest src={src} />
    </Box>
  );
}
