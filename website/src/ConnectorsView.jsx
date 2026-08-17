// Connectors, Stripe-style like Settings: a landing of report-connection cards with live
// status, drilling into a detail page (Connectors breadcrumb + title) with horizontal
// tabs: Overview (enable/test/run), Configuration (typed form + preview), Setup guide.
// Standalone Taskuary pulls FROM systems on a schedule - SQL Server, MCP servers,
// SQLite, REST, RSS - and files results on the Timeline as informational rows.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, MenuItem, Select, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import BoltIcon from "@mui/icons-material/Bolt";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, UnderTabs, LandingCard, Empty } from "./ui.jsx";

// field spec per type: [label, key, kind(text|password|multiline|select-auth|select-driver), placeholder]
const FIELDS = {
  mssql: [["server", "server", "text", "localhost  or  HOST\\INSTANCE"], ["database", "database", "text", "master"],
    ["auth", "auth", "select-auth", ""], ["username", "username", "text", "(sql auth only)"],
    ["password", "password", "password", ""], ["driver", "driver", "select-driver", ""],
    ["query", "query", "multiline", "SELECT TOP 20 * FROM ..."]],
  mcp: [["command", "cmd", "text", "npx / uvx / path to the MCP server"], ["args (one per line)", "args", "multiline", "-y\n@modelcontextprotocol/server-postgres\npostgresql://localhost/db"],
    ["tool", "tool", "text", "query  (Test lists the server's tools)"], ["tool args (JSON)", "tool_args", "multiline", '{"sql": "SELECT ..."}']],
  sqlite: [["db path", "db", "text", "C:/data/app.db"], ["query", "query", "multiline", "SELECT ..."]],
  rest: [["url", "url", "text", "https://api.example.com/items"], ["headers (JSON)", "headers", "multiline", '{"Authorization": "Bearer ..."}'], ["json path", "path", "text", "data.items"]],
  rss: [["feed url", "url", "text", "https://example.com/feed.xml"]],
};

const HOWTO = {
  mssql: ["Local SQL Server works out of the box: leave auth on Windows (trusted) - server + database + query is all the config.",
    "Driver auto-picks the newest installed 'ODBC Driver NN for SQL Server'; override only if you need a specific one.",
    "For a remote server or SQL logins, switch auth to SQL login and fill username/password.",
    "Hit Test connection - it connects for real and reports the server version, or exactly what failed.",
    "Preview runs the query without filing anything; Save + Run now files the first row on the Timeline."],
  mcp: ["Any MCP server is a connector: give the command that starts it over stdio (npx, uvx, an exe).",
    "Args go one per line. Test connection starts the server and lists the tools it exposes.",
    "Pick the tool to call and give its arguments as JSON - the tool's text output lands on the Timeline.",
    "Schedule it like any other connection (every N minutes or daily at HH:MM)."],
  sqlite: ["Point at any .db file on this machine and write the query.", "Preview to sanity-check, then Save."],
  rest: ["GET any JSON endpoint; optional headers as JSON (auth tokens etc.).", "json path dot-walks into the response (data.items) so the Timeline row shows the part you care about."],
  rss: ["Paste the feed url - the newest titles land on the Timeline."],
};

const BLANK = { type: "mssql", title: "", every_minutes: "", daily_at: "" };
const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };

export default function ConnectorsView() {
  const [sources, setSources] = useState(null);
  const [types, setTypes] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [open, setOpen] = useState(null);            // null = landing; {SourceId?} = detail
  const [tab, setTab] = useState("Overview");
  const [cfg, setCfg] = useState(BLANK);
  const [test, setTest] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([api.get("/api/sources"), api.get("/api/connectors")]);
      setSources((s.data.data || []).filter((x) => x.Channel === "report"));
      setTypes(c.data.data || []);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load connectors"); }
  }, []);
  useEffect(() => { load(); api.get("/api/mssql/drivers").then(({ data }) => setDrivers(data.data || [])).catch(() => {}); }, [load]);

  const openSrc = (s) => {
    setOpen(s || { SourceId: null }); setTab(s ? "Overview" : "Configuration");
    setCfg(s ? { ...BLANK, ...parse(s.ConfigJson) } : { ...BLANK });
    setTest(null); setPreview(null);
  };

  const bodyCfg = () => {
    const c = { ...cfg, type: cfg.type, title: cfg.title };
    if (typeof c.args === "string") c.args = c.args.split("\n").map((x) => x.trim()).filter(Boolean);
    if (typeof c.headers === "string" && c.headers.trim()) { try { c.headers = JSON.parse(c.headers); } catch { /* send as-is; preview will complain */ } }
    for (const k of ["every_minutes", "daily_at", "username", "password", "database", "server", "driver"]) if (c[k] === "" || c[k] == null) delete c[k];
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
        setTest(data.ok ? { ok: true, detail: `server ok · tools: ${(data.data || []).map((t) => t.name).join(", ") || "(none)"}` }
          : { ok: false, detail: data.error });
      } else {
        const { data } = await api.post("/api/reports/preview", c);
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
    if (!c.title) { setErr("title is required"); return; }
    const body = { Channel: "report", Address: c.title, ConfigJson: JSON.stringify(c), Active: true };
    if (open?.SourceId) body.SourceId = open.SourceId;
    const { data } = await api.post("/api/sources", body);
    await load();
    setOpen((cur) => ({ ...(cur || {}), SourceId: data.sourceId }));
    setTab("Overview");
  };

  const toggle = async (s) => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); load(); };
  const runNow = async (sid) => {
    setBusy("run");
    try { const { data } = await api.post(`/api/sources/${sid}/run`); setTest({ ok: !String(data.subject).includes("FAILED"), detail: data.subject }); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "run failed" }); }
    setBusy(""); load();
  };
  const del = async (sid) => { await api.delete(`/api/sources/${sid}`); setOpen(null); load(); };
  const syncNow = async () => {
    setSyncing(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSyncing(false); load(); }, 2500); }
    catch { setSyncing(false); }
  };

  if (!sources) return <CircularProgress size={22} sx={{ m: 4 }} />;

  /* ── detail page ──────────────────────────────────────────────────────── */
  if (open) {
    const cur = sources.find((s) => s.SourceId === open.SourceId);
    const fields = FIELDS[cfg.type] || [];
    const sqlAuth = (cfg.auth || "windows") === "sql";
    return (
      <Box sx={{ maxWidth: 980 }}>
        <Crumb section="Connectors" onBack={() => setOpen(null)} title={cfg.title || "New connection"} />
        <UnderTabs tabs={["Overview", "Configuration", "Setup guide"]} value={tab} onChange={setTab} />

        {tab === "Overview" && (cur ? (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2, borderBottom: `1px solid ${BORDER}` }}>
              <StatusDot ok={!!cur.Active} />
              <Box sx={{ flex: 1 }}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 15 }}>Enabled</Typography>
                <Typography variant="body2" sx={{ color: DIM }}>
                  {cur.Active ? "Runs on its schedule and via Sync now." : "Off — this connection is not pulled."}
                  {cur.LastPolledAt ? ` Last ran ${timeAgo(cur.LastPolledAt)}.` : " Never ran yet."}
                </Typography>
              </Box>
              <Switch checked={!!cur.Active} onChange={() => toggle(cur)} />
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2, borderBottom: `1px solid ${BORDER}` }}>
              <Box sx={{ flex: 1 }}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 15 }}>Health check</Typography>
                <Typography variant="body2" sx={{ color: DIM }}>Live probe — connects / lists tools / runs the pull for real.</Typography>
                {test && <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>{test.ok ? "✓" : "✗"} {test.detail}</Typography>}
              </Box>
              <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
                startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
              <Button variant="outlined" disabled={busy === "run"} onClick={() => runNow(cur.SourceId)}
                startIcon={<PlayArrowIcon sx={{ fontSize: 15 }} />}>Run now</Button>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 15 }}>Delete</Typography>
                <Typography variant="body2" sx={{ color: DIM }}>Removes the connection — rows it already filed stay on the Timeline.</Typography>
              </Box>
              <Button color="error" variant="outlined" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />}
                onClick={() => del(cur.SourceId)}>Delete</Button>
            </Box>
          </>
        ) : <Empty>Save the configuration first — then enable, test and run it here.</Empty>)}

        {tab === "Configuration" && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 560 }}>
            <Box sx={{ display: "flex", gap: 1 }}>
              <TextField fullWidth label="title" value={cfg.title || ""} sx={{ bgcolor: "#fff" }}
                onChange={(e) => setCfg({ ...cfg, title: e.target.value })} />
              <Select value={cfg.type} sx={{ minWidth: 130, bgcolor: "#fff" }}
                onChange={(e) => { setCfg({ ...BLANK, title: cfg.title, type: e.target.value }); setPreview(null); setTest(null); }}>
                {types.map((t) => <MenuItem key={t.type} value={t.type} disabled={t.status === "planned"} sx={{ fontSize: 12.5 }}>
                  {t.type}{t.status === "planned" ? " (planned)" : ""}</MenuItem>)}
              </Select>
            </Box>
            <Box sx={{ display: "flex", gap: 1 }}>
              <TextField label="every N minutes" type="number" value={cfg.every_minutes || ""} sx={{ bgcolor: "#fff", width: 160 }}
                onChange={(e) => setCfg({ ...cfg, every_minutes: e.target.value, daily_at: "" })} />
              <TextField label="or daily at HH:MM" value={cfg.daily_at || ""} sx={{ bgcolor: "#fff", width: 160 }}
                onChange={(e) => setCfg({ ...cfg, daily_at: e.target.value, every_minutes: "" })} />
            </Box>
            {fields.map(([label, key, kind, ph]) => {
              if (kind === "select-auth") return (
                <Select key={key} value={cfg.auth || "windows"} sx={{ bgcolor: "#fff" }}
                  onChange={(e) => setCfg({ ...cfg, auth: e.target.value })}>
                  <MenuItem value="windows" sx={{ fontSize: 12.5 }}>Windows auth (local, trusted)</MenuItem>
                  <MenuItem value="sql" sx={{ fontSize: 12.5 }}>SQL login</MenuItem>
                </Select>
              );
              if (kind === "select-driver") return (
                <Select key={key} value={cfg.driver || ""} displayEmpty sx={{ bgcolor: "#fff" }}
                  onChange={(e) => setCfg({ ...cfg, driver: e.target.value })}>
                  <MenuItem value="" sx={{ fontSize: 12.5 }}>(auto — newest installed driver)</MenuItem>
                  {drivers.map((d) => <MenuItem key={d} value={d} sx={{ fontSize: 12.5 }}>{d}</MenuItem>)}
                </Select>
              );
              if (["username", "password"].includes(key) && !sqlAuth) return null;
              const v = cfg[key]; const shown = Array.isArray(v) ? v.join("\n") : typeof v === "object" && v ? JSON.stringify(v) : (v ?? "");
              return <TextField key={key} label={label} placeholder={ph} value={shown} sx={{ bgcolor: "#fff" }}
                type={kind === "password" ? "password" : "text"} multiline={kind === "multiline"} minRows={kind === "multiline" ? 2 : undefined}
                inputProps={kind === "multiline" ? { style: { fontFamily: "Consolas, monospace", fontSize: 12 } } : undefined}
                onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />;
            })}
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Button variant="contained" disableElevation onClick={save}>Save connection</Button>
              <Button variant="outlined" disabled={busy === "preview"} onClick={runPreview}
                startIcon={busy === "preview" ? <CircularProgress size={12} /> : null}>Preview</Button>
              <Button disabled={busy === "test"} onClick={runTest}>Test connection</Button>
            </Box>
            {test && <Typography variant="body2" sx={{ fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>{test.ok ? "✓" : "✗"} {test.detail}</Typography>}
            {preview && (preview.ok ? (
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, color: "#15803d" }}>✓ {preview.headline}</Typography>
                <Box component="pre" sx={{ ...mono, whiteSpace: "pre-wrap", bgcolor: PANEL2, border: `1px solid ${BORDER}`,
                  borderRadius: 1.5, p: 1.25, fontSize: 11, maxHeight: 260, overflow: "auto", color: INK }}>{preview.summary}</Box>
              </Box>
            ) : <Typography variant="body2" sx={{ fontWeight: 600, color: "#b91c1c" }}>✗ {preview.error}</Typography>)}
          </Box>
        )}

        {tab === "Setup guide" && (
          <Box sx={{ maxWidth: 720 }}>
            {(HOWTO[cfg.type] || []).map((step, i) => (
              <Box key={i} sx={{ display: "flex", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
                <Box sx={{ ...mono, width: 24, height: 24, borderRadius: "50%", bgcolor: "#eef0ff", color: "#4f46e5",
                  fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</Box>
                <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{step}</Typography>
              </Box>
            ))}
          </Box>
        )}
      </Box>
    );
  }

  /* ── landing ──────────────────────────────────────────────────────────── */
  return (
    <Box sx={{ maxWidth: 1160 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 17, flex: 1 }}>Report connections</Typography>
        <Button size="small" variant="outlined" disableElevation onClick={syncNow} disabled={syncing} sx={{ mr: 1 }}
          startIcon={syncing ? <CircularProgress size={12} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Running…" : "Run due now"}
        </Button>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => openSrc(null)}>Add connection</Button>
      </Box>
      {!sources.length && <Empty>No connections yet — add SQL Server, an MCP server, SQLite, REST or RSS and results land on the Timeline.</Empty>}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3 }}>
        {sources.map((s) => {
          const c = parse(s.ConfigJson);
          const sched = c.every_minutes ? `every ${c.every_minutes}m` : c.daily_at ? `daily ${c.daily_at}` : "daily";
          const status = `${c.type || "rest"} · ${s.Active ? "on" : "off"} · ${sched}` + (s.LastPolledAt ? ` · ran ${timeAgo(s.LastPolledAt)}` : " · never ran");
          return <LandingCard key={s.SourceId} title={c.title || s.Address} desc={status}
            icon={<ChannelIcon channel="report" sx={{ fontSize: 19 }} />} onOpen={() => openSrc(s)} />;
        })}
      </Box>
    </Box>
  );
}
