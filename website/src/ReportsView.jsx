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

  const runNow = async (sid) => {
    try { const { data } = await api.post(`/api/sources/${sid}/run`); setNote({ ok: !String(data.subject).includes("FAILED"), detail: `filed on the Timeline: ${data.subject}` }); }
    catch (e) { setNote({ ok: false, detail: e?.response?.data?.detail || "run failed" }); }
    load();
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
        const sched = c.every_minutes ? `every ${c.every_minutes}m` : c.daily_at ? `daily ${c.daily_at}` : "daily";
        return (
          <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.5, borderBottom: `1px solid ${BORDER}` }}>
            <StatusDot ok={!!s.Active} />
            <ChannelIcon channel="report" />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }} noWrap>{c.title || s.Address}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT }}>
                {TYPE_LABELS[c.type] || c.type || "rest"} · {sched}{s.LastPolledAt ? ` · ran ${timeAgo(s.LastPolledAt)}` : " · never ran"}
              </Typography>
            </Box>
            {c.ai_prompt && <Box sx={{ display: "flex", alignItems: "center", gap: 0.4, px: 1, py: 0.25, borderRadius: 99,
              bgcolor: "#fef4e6", border: "1px solid #f3ddb8" }}>
              <AutoAwesomeIcon sx={{ fontSize: 12, color: "#b45309" }} />
              <Typography variant="caption" sx={{ color: "#b45309", fontWeight: 700, fontSize: 10 }}>AI summary</Typography>
            </Box>}
            <Button size="small" startIcon={<PlayArrowIcon sx={{ fontSize: 14 }} />} onClick={() => runNow(s.SourceId)}>Run now</Button>
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
  const [cfg, setCfg] = useState(cur ? { ...BLANK, ...parse(cur.ConfigJson) } : { ...BLANK });
  const [step, setStep] = useState(cur ? 1 : 0);
  const [test, setTest] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const mssqlConn = connectors.find((c) => c.Type === "mssql");
  const mssqlOk = mssqlConn?.LastSyncAt && !mssqlConn?.LastError;
  const winrmConn = connectors.find((c) => c.Type === "winrm");
  const winrmOk = winrmConn?.LastSyncAt && !winrmConn?.LastError;
  const aiActive = connectors.some((c) => ["anthropic", "openai", "azure_openai"].includes(c.Type) && c.Active && c.HasSecret);

  const bodyCfg = () => {
    const c = { ...cfg };
    if (typeof c.args === "string") c.args = c.args.split(NL).map((x) => x.trim()).filter(Boolean);
    if (typeof c.headers === "string" && c.headers.trim()) { try { c.headers = JSON.parse(c.headers); } catch { /* preview will complain */ } }
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null) delete c[k];
    if (c.every_minutes) c.every_minutes = Number(c.every_minutes);
    return c;
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

  const fields = FIELDS[cfg.type] || [];
  const typeOptions = types.filter((t) => t.status === "builtin");
  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section="Reports" onBack={onBack} title={cur ? (parse(cur.ConfigJson).title || "Edit report") : "New report"} />
      <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
        <Step completed={!!cfg.type}>
          <StepButton onClick={() => setStep(0)}>Source</StepButton>
          <StepContent>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1 }}>Where the data comes from.</Typography>
            <FilterPills options={typeOptions.map((t) => ({ key: t.type, label: TYPE_LABELS[t.type] || t.type }))}
              value={cfg.type} onChange={(t) => { setCfg({ ...BLANK, title: cfg.title, type: t }); setTest(null); setPreview(null); }} />
            {cfg.type === "mssql" && (
              <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: mssqlOk ? "#15803d" : "#b45309" }}>
                {mssqlOk ? "✓ uses the SQL Server connection from the Connectors tab"
                  : "⚠ no tested SQL Server connection yet — set it up under Connectors → Microsoft SQL Server first"}
              </Typography>
            )}
            {cfg.type === "winrm" && (
              <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: winrmOk ? "#15803d" : "#b45309" }}>
                {winrmOk ? `✓ runs on ${parse(winrmConn?.ConfigJson).host || "the remote host"} via the Connectors-tab connection`
                  : "⚠ no tested remote machine yet — set the host under Connectors → Remote Windows (WinRM) first"}
              </Typography>
            )}
            <Box sx={{ mt: 1.5 }}><Button variant="contained" disableElevation onClick={() => setStep(1)}>Continue</Button></Box>
          </StepContent>
        </Step>
        <Step completed={!!cfg.title}>
          <StepButton onClick={() => setStep(1)}>Configure</StepButton>
          <StepContent>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 560, mt: 1 }}>
              <TextField label="title — becomes the Timeline headline" value={cfg.title || ""} sx={{ bgcolor: "#fff" }}
                onChange={(e) => setCfg({ ...cfg, title: e.target.value })} />
              {fields.map(([label, key, kind, ph]) => {
                const v = cfg[key]; const shown = Array.isArray(v) ? v.join(NL) : typeof v === "object" && v ? JSON.stringify(v) : (v ?? "");
                return <TextField key={key} label={label} placeholder={ph} value={shown} sx={{ bgcolor: "#fff" }}
                  multiline={kind === "multiline"} minRows={kind === "multiline" ? 2 : undefined}
                  inputProps={kind === "multiline" && key !== "ai_prompt" ? { style: { fontFamily: "Consolas, monospace", fontSize: 12 } } : undefined}
                  onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />;
              })}
              {cfg.ai_prompt && !aiActive && (
                <Typography variant="body2" sx={{ fontWeight: 600, color: "#b45309" }}>
                  ⚠ AI prompt set, but no active AI connector — the raw data will file until you enable one (Connectors → AI).
                </Typography>
              )}
              <Box><Button variant="contained" disableElevation onClick={() => setStep(2)}>Continue</Button></Box>
            </Box>
          </StepContent>
        </Step>
        <Step completed={!!test?.ok || !!preview?.ok}>
          <StepButton onClick={() => setStep(2)}>Test & preview</StepButton>
          <StepContent>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1 }}>
              Test checks the source; Preview runs the whole pipeline — query + AI — exactly like a scheduled run, without filing anything.
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
                startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test source</Button>
              <Button variant="outlined" disabled={busy === "preview"} onClick={runPreview}
                startIcon={busy === "preview" ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 15 }} />}>Preview pipeline</Button>
              <Button onClick={() => setStep(3)}>Continue</Button>
            </Box>
            {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>{test.ok ? "✓" : "✗"} {test.detail}</Typography>}
            {preview && (preview.ok ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: "#15803d" }}>✓ {preview.headline}</Typography>
                <Box component="pre" sx={{ ...mono, whiteSpace: "pre-wrap", bgcolor: PANEL2, border: `1px solid ${BORDER}`,
                  borderRadius: 1.5, p: 1.25, fontSize: 11, maxHeight: 260, overflow: "auto", color: INK }}>{preview.summary}</Box>
              </Box>
            ) : <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "#b91c1c" }}>✗ {preview.error}</Typography>)}
          </StepContent>
        </Step>
        <Step completed={!!cur}>
          <StepButton onClick={() => setStep(3)}>Schedule & save</StepButton>
          <StepContent>
            <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
              <TextField label="every N minutes" type="number" value={cfg.every_minutes || ""} sx={{ bgcolor: "#fff", width: 160 }}
                onChange={(e) => setCfg({ ...cfg, every_minutes: e.target.value, daily_at: "" })} />
              <TextField label="or daily at HH:MM" value={cfg.daily_at || ""} sx={{ bgcolor: "#fff", width: 160 }}
                onChange={(e) => setCfg({ ...cfg, daily_at: e.target.value, every_minutes: "" })} />
              <Button variant="contained" disableElevation onClick={save}>Save report</Button>
            </Box>
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
