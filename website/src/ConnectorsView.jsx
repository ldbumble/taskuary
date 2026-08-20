// Connectors, Stripe-style like Settings: a searchable landing of grouped category cards
// (AI · Messaging · Developer · Local & data), each drilling into a detail page with a
// setup WIZARD (stepper) plus Sources/management. All connectors live here - channel
// connectors (Outlook, Teams, Slack, GitHub), cloud AI APIs (Anthropic, OpenAI, Azure
// OpenAI - wired into intent triage), AI CLI agents, and scheduled report connections.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, InputAdornment, MenuItem, Select, Step, StepButton,
  StepContent, Stepper, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import BoltIcon from "@mui/icons-material/Bolt";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, UnderTabs, LandingCard, Empty } from "./ui.jsx";
import { AgentsPage } from "./AgentsPanel.jsx";

/* ── connector metadata: channel + AI connectors (rows in the connector table) ── */
const META = {
  outlook: { group: "Messaging", channel: "email", srcLabel: "Mailboxes", srcPh: "someone@yourdomain.com",
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"]], secretLabel: "client secret",
    desc: "Ingest mailboxes through a Microsoft Graph app - mail lands on the Timeline through triage.",
    howto: ["Register (or reuse) an Azure app: Azure Portal → App registrations → New registration.",
      "API permissions → add the APPLICATION permission Mail.Read (Microsoft Graph) → Grant admin consent.",
      "Enter tenant_id + client_id and paste the app's client secret (write-only). Blank = the server's AZURE_* env vars.",
      "Add each mailbox to read as a UPN under Sources and flip it on.",
      "Test acquires a real Graph token and reports exactly what failed if anything. Enable, and mail flows through the same triage funnel as everything else."] },
  teams: { group: "Messaging", channel: "teams", srcLabel: "Users / chat ids", srcPh: "user UPN, e.g. jsmith@yourcompany.com",
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"]], secretLabel: "client secret",
    desc: "Ingest Teams chats via Graph. Leave credentials blank to reuse the Outlook connector's app.",
    howto: ["Credentials: leave everything blank and Teams automatically reuses the Outlook connector's saved Graph app (or the server's AZURE_* env vars). Only fill these to use a different app registration.",
      "App-only chat reading is a Microsoft PROTECTED API: the tenant needs Microsoft-approved Chat.Read.All - until that approval is granted, Test shows the 403 telling you so.",
      "Add the user whose chats to ingest as a UPN under Sources. Your UPN (User Principal Name) is your Microsoft 365 sign-in address - usually just your work email. Find it in Teams: click your profile picture, it's the address under your name. Or run `whoami /upn` in a terminal on a work Windows machine, or check Azure Portal → Users → your account → User principal name.",
      "A specific chat id works too (Teams web: open the chat, the 19:...@thread.v2 part of the URL).",
      "Test probes an actual chat read for the first Teams source, not just the token."] },
  slack: { group: "Messaging", channel: "slack", srcLabel: "Channel IDs", srcPh: "C0123456789",
    fields: [], secretLabel: "bot token (xoxb-…)",
    desc: "Ingest Slack channels with a bot token - messages land on the Timeline through triage.",
    howto: ["Create a Slack app (api.slack.com/apps) → OAuth & Permissions → bot token scopes: channels:history, channels:read.",
      "Install the app to your workspace and invite the bot to the channels to ingest (/invite @yourbot).",
      "Paste the xoxb- bot token under Credentials (write-only).",
      "Add each channel ID under Sources (channel → View details → ID at the bottom).",
      "Test authenticates and probes a real channel read."] },
  telegram: { group: "Messaging", channel: "telegram", srcLabel: "Chat IDs (optional — blank takes every chat)", srcPh: "-1001234567890",
    fields: [], secretLabel: "bot token (from @BotFather)",
    desc: "A Telegram bot as an inbound channel - message it (or add it to a group) and the chats flow through triage; approved replies go back into the same chat.",
    howto: ["Message @BotFather in Telegram → /newbot → copy the token.",
      "Paste the token under Credentials (write-only).",
      "Test authenticates and adds a catch-all source; message your bot and Sync.",
      "For a group: add the bot to it and disable its privacy mode (@BotFather → /setprivacy) so it sees messages.",
      "Add specific chat IDs under Sources only if you want to LIMIT which chats come in."] },
  whatsapp: { group: "Messaging", channel: "whatsapp", srcLabel: "Chat JIDs (optional — blank takes every chat)", srcPh: "15551234567@s.whatsapp.net",
    fields: [["bridge URL (blank = http://127.0.0.1:8977)", "bridge_url"]], secretLabel: null,
    desc: "Your own WhatsApp, via a small bridge that runs beside Taskuary (Baileys, installed separately) - chats flow through triage, approved replies go back into the chat.",
    howto: ["The heavy dependency is deliberately NOT bundled: in the Taskuary folder run `cd taskuary/whatsapp && npm install && node bridge.mjs` (Node 18+).",
      "Pair once: scan the QR the bridge prints (WhatsApp → Linked devices), or run it with --phone 1555… and enter the code it gives you.",
      "Leave the bridge running; Test here confirms the pairing and adds a catch-all source.",
      "Add specific chat JIDs under Sources only if you want to LIMIT which chats come in.",
      "Unofficial protocol (WhatsApp Web) - use a number you would risk; business-critical numbers belong on the official API."] },
  github: { group: "Developer", channel: "github", srcLabel: "Repositories", srcPh: "org/repo",
    fields: [], secretLabel: "fine-grained PAT",
    desc: "Paste a PAT - repos are auto-discovered, feed the Board's repo picker and the coder's issue loop.",
    howto: ["Create a fine-grained PAT: GitHub → Settings → Developer settings → Fine-grained tokens.",
      "Repository access: the repos the agent may touch. Permissions: Issues Read+Write, Pull requests Read+Write, Metadata Read.",
      "Paste the token under Credentials - that's ALL the config: on save Taskuary discovers every repo the token reaches, adds them under Sources, and writes the repository map into SOUL.md.",
      "Test re-runs discovery and reports who it's authenticated as.",
      "Coding tasks then open an issue first, the agent works it, and closing the task closes the issue."] },
  anthropic: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default claude-opus-5)", "model"]], secretLabel: "API key",
    desc: "Claude via the Anthropic API - powers intent triage (task / reply-only / FYI) once enabled.",
    howto: ["Create an API key at console.anthropic.com → API keys.",
      "Paste it under Credentials (write-only). Optionally set a model - default is claude-opus-5.",
      "Test runs a real round trip through the model.",
      "Enable it and every new inbound message is classified by the model, guided by SOUL.md - the first active AI connector wins."] },
  openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default gpt-4o-mini)", "model"]], secretLabel: "API key",
    desc: "OpenAI models for intent triage - alternative to the Anthropic connector.",
    howto: ["Create an API key at platform.openai.com.",
      "Paste it under Credentials; optionally set a model.",
      "Test runs a real round trip. Enable to wire it into triage - the first active AI connector wins."] },
  azure_openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["endpoint", "endpoint"], ["deployment", "deployment"], ["api_version", "api_version"]], secretLabel: "API key",
    desc: "Your Azure OpenAI deployment for intent triage - endpoint + deployment + key.",
    howto: ["Azure Portal → your Azure OpenAI resource → Keys and Endpoint.",
      "Enter the endpoint (https://YOUR-RESOURCE.openai.azure.com), the deployment name, and optionally an api_version.",
      "Paste a key under Credentials. Test runs a real round trip through the deployment."] },
};

const PLANNED_AI = [
  { name: "AWS Bedrock", desc: "planned - Claude & friends through your AWS account" },
  { name: "Google Vertex AI", desc: "planned - Gemini / Claude through your GCP project" },
];

const MSSQL_HOWTO = [
  "This card is the CONNECTION only - set it up once, Test it, and every SQL report inherits it.",
  "Local SQL Server: keep auth on Windows (trusted) - server + database is all the config. Named instance? Use HOST\INSTANCE, e.g. localhost\SQLEXPRESS.",
  "Driver auto-picks the newest installed 'ODBC Driver NN for SQL Server'; SQL logins go under auth.",
  "Build the actual reports (query + AI summary + schedule) on the REPORTS tab.",
];

const WINRM_HOWTO = [
  "This card is the CONNECTION only - the machine name. Build the actual reports (script + AI summary + schedule) on the REPORTS tab.",
  "A box you can RDP into (like AZWEB01) is usually domain-joined and already reachable over WinRM with your Windows login - just enter the machine name and Test.",
  "If Test fails with 'WinRM unreachable', enable PS remoting on the remote box once: open an elevated PowerShell THERE and run Enable-PSRemoting -Force.",
  "Reports then run any PowerShell you write ON that machine (read a log, query a service, export a CSV) and the output - optionally AI-summarized - lands on the Timeline.",
];

const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const NL = String.fromCharCode(10);

export default function ConnectorsView() {
  const [connectors, setConnectors] = useState(null);
  const [sources, setSources] = useState([]);
  const [types, setTypes] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);   // {kind:'channel',id} | {kind:'rtype',rtype,SourceId?} | {kind:'agents'}
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, s, t] = await Promise.all([api.get("/api/connectors"), api.get("/api/sources"), api.get("/api/report-types")]);
      setConnectors(c.data.data || []); setSources(s.data.data || []); setTypes(t.data.data || []);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load connectors"); }
  }, []);
  useEffect(() => { load(); api.get("/api/mssql/drivers").then(({ data }) => setDrivers(data.data || [])).catch(() => {}); }, [load]);

  const reports = sources.filter((x) => x.Channel === "report");
  const syncNow = async () => {
    setSyncing(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSyncing(false); load(); }, 3000); }
    catch { setSyncing(false); }
  };

  const byType = Object.fromEntries((connectors || []).map((c) => [c.Type, c]));

  if (!connectors) return <CircularProgress size={22} sx={{ m: 4 }} />;

  if (open?.kind === "agents") return <AgentsPage section="Connectors" title="AI CLI agents" onBack={() => setOpen(null)} />;
  if (open?.kind === "channel") {
    const conn = connectors.find((c) => c.ConnectorId === open.id);
    return <ChannelDetail conn={conn} sources={sources} reload={load} onBack={() => setOpen(null)} />;
  }
  if (open?.kind === "mssql") {
    return <MssqlDetail conn={byType.mssql} drivers={drivers} reload={load} onBack={() => setOpen(null)} />;
  }
  if (open?.kind === "winrm") {
    return <WinrmDetail conn={byType.winrm} reload={load} onBack={() => setOpen(null)} />;
  }

  /* ── landing: searchable grouped catalog ── */
  const chanCard = (c) => {
    const m = META[c.Type] || {};
    const srcs = m.channel && m.channel !== "ai"
      ? sources.filter((s) => s.ConnectorId === c.ConnectorId || (!s.ConnectorId && m.channel === s.Channel)) : null;
    const roles = String(c.Roles || "").split(",").filter(Boolean);
    const status = `${c.Active ? "on" : "off"}`
      + (roles.length ? ` · ${roles.join(" + ")}` : "")
      + (srcs ? ` · ${srcs.filter((s) => s.Active).length}/${srcs.length} ${(m.srcLabel || "sources").toLowerCase()}` : c.HasSecret ? " · key saved" : " · no key yet")
      + (c.LastError ? " · last test failed" : c.LastSyncAt ? ` · ok ${timeAgo(c.LastSyncAt)}` : "");
    return { key: `c${c.ConnectorId}`, title: c.Name, desc: status, channel: m.channel || c.Type,
      haystack: `${c.Name} ${c.Type} ${m.desc || ""} ${(m.howto || []).join(" ")}`,
      go: () => setOpen({ kind: "channel", id: c.ConnectorId }) };
  };
  const groups = [
    { title: "AI — agents & models", cards: [
      { key: "agents", title: "AI CLI agents", desc: "claude / codex / gemini — bring your own coding CLI, resumable sessions",
        channel: "cli", haystack: "ai cli agents claude codex gemini command args resume", go: () => setOpen({ kind: "agents" }) },
      ...["anthropic", "openai", "azure_openai"].filter((t) => byType[t]).map((t) => chanCard(byType[t])),
      ...PLANNED_AI.map((p) => ({ key: p.name, title: p.name, desc: p.desc, channel: "ai", haystack: `${p.name} ${p.desc}`, planned: true })),
    ]},
    { title: "Messaging", cards: ["outlook", "teams", "slack", "telegram", "whatsapp"].filter((t) => byType[t]).map((t) => chanCard(byType[t])) },
    { title: "Developer", cards: ["github"].filter((t) => byType[t]).map((t) => chanCard(byType[t])) },
    { title: "Data connections", cards: [
      {
        key: "mssql", title: "Microsoft SQL Server", channel: "report",
        desc: (byType.mssql?.LastError ? "connection failing" : byType.mssql?.LastSyncAt ? "connection ✓" : "not set up")
          + ` · ${reports.filter((s2) => (parse(s2.ConfigJson).type || "rest") === "mssql").length} reports (built on the Reports tab)`,
        haystack: "microsoft sql server mssql connection windows auth " + MSSQL_HOWTO.join(" "),
        go: () => setOpen({ kind: "mssql" }),
      },
      ...(byType.winrm ? [{
        key: "winrm", title: "Remote Windows (WinRM)", channel: "winrm",
        desc: (byType.winrm.LastError ? "connection failing" : byType.winrm.LastSyncAt ? "connection ✓" : "not set up")
          + ` · ${reports.filter((s2) => (parse(s2.ConfigJson).type || "rest") === "winrm").length} reports (built on the Reports tab)`,
        haystack: "remote windows winrm rdp powershell remoting azweb01 " + WINRM_HOWTO.join(" "),
        go: () => setOpen({ kind: "winrm" }),
      }] : []),
      ...types.filter((t) => t.status === "planned").map((t) => ({
        key: `p${t.type}`, title: t.type, desc: "planned", channel: "report", haystack: `${t.type} planned`, planned: true })),
    ]},
  ];
  const hits = q ? groups.flatMap((g) => g.cards.filter((c) => !c.planned && c.haystack.toLowerCase().includes(q.toLowerCase()))
    .map((c) => ({ ...c, crumb: g.title }))) : [];

  return (
    <Box sx={{ maxWidth: 1160 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 3 }}>
        <TextField fullWidth placeholder="Search connectors — Slack, SQL Server, Anthropic… matches setup guides too" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ bgcolor: "#fff", borderRadius: 2, maxWidth: 520 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: FAINT }} /></InputAdornment> }} />
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" disableElevation onClick={syncNow} disabled={syncing}
          startIcon={syncing ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </Box>

      {q ? (
        <Box>
          {!hits.length && <Empty>Nothing matches.</Empty>}
          {hits.map((r) => (
            <Box key={r.key} onClick={r.go} sx={{ py: 1.25, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
              "&:hover": { bgcolor: "#fafbfd" } }}>
              <Typography sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 13.5 }}>{r.title}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{r.crumb} · {r.desc}</Typography>
            </Box>
          ))}
        </Box>
      ) : groups.map((g) => (
        <Box key={g.title} sx={{ mb: 4 }}>
          <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>{g.title}</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3 }}>
            {g.cards.map((c) => (
              <Box key={c.key} sx={{ opacity: c.planned ? 0.45 : 1 }}>
                <LandingCard title={c.title} desc={c.desc} onOpen={c.planned ? () => {} : c.go}
                  icon={c.channel === "cli" ? <TerminalIcon sx={{ fontSize: 19, color: "#4f46e5" }} />
                    : <ChannelIcon channel={c.channel} sx={{ fontSize: 19 }} />} />
              </Box>
            ))}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/* ── "Remove connection" on every detail page: wipes creds/config, turns sources off ── */
function RemoveConnection({ conn, reload, onBack }) {
  const [confirm, setConfirm] = useState(false);
  const remove = async () => {
    await api.post(`/api/connectors/${conn.ConnectorId}/reset`);
    reload(); onBack();
  };
  return (
    <Box sx={{ mt: 3, pt: 1.5, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1, alignItems: "center", maxWidth: 720 }}>
      {confirm ? (
        <>
          <Typography variant="body2" sx={{ color: "#b91c1c", flex: 1 }}>
            Wipes the saved credentials & settings and turns its sources off. The card stays in the catalog. Sure?
          </Typography>
          <Button size="small" color="error" variant="contained" disableElevation onClick={remove}>Remove</Button>
          <Button size="small" onClick={() => setConfirm(false)}>Cancel</Button>
        </>
      ) : (
        <Button size="small" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />} sx={{ color: "#8a94a6" }}
          onClick={() => setConfirm(true)}>Remove connection</Button>
      )}
    </Box>
  );
}

/* ── channel / AI connector detail: setup wizard + sources ─────────────── */
function ChannelDetail({ conn, sources, reload, onBack }) {
  const m = META[conn.Type] || { fields: [], howto: [] };
  const isAI = m.channel === "ai";
  const [tab, setTab] = useState("Setup");
  const [step, setStep] = useState(conn.HasSecret ? (conn.LastSyncAt ? 2 : 1) : 0);
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [newSrc, setNewSrc] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const mine = sources.filter((s) => s.ConnectorId === conn.ConnectorId || (!s.ConnectorId && m.channel === s.Channel));

  const saveCreds = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg) };
      if (secret) body.Secret = secret;
      const { data } = await api.post("/api/connectors", body);
      setMsg("saved ✓");
      if (data.discovery) {
        const d = data.discovery;
        setTest(d.error ? { ok: false, detail: d.error }
          : { ok: true, detail: `authenticated as ${d.login} · ${d.repos} repos discovered · ${d.added} sources added · repo map written to SOUL.md` });
      }
      setSecret(""); setStep(1); reload();
    } catch (e) { setMsg(""); setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try {
      const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/test`);
      setTest(data);
      if (data.ok) setStep(m.srcLabel ? 2 : 3);
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };
  const addSource = async () => {
    if (!newSrc.trim()) return;
    await api.post("/api/sources", { Channel: m.channel, Address: newSrc.trim(), ConnectorId: conn.ConnectorId, Active: true });
    setNewSrc(""); reload();
  };
  const toggleSource = async (s) => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); reload(); };
  const setActive = async (on) => { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Active: on }); reload(); };

  const steps = [
    { label: "Credentials", done: !!conn.HasSecret || !m.secretLabel, body: (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
        {m.fields.map(([label, key]) => (
          <TextField key={key} label={label} value={cfg[key] || ""} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />
        ))}
        {/* WhatsApp has no secret at all - the bridge holds the pairing, not us */}
        {m.secretLabel && (
          <TextField label={conn.HasSecret ? `${m.secretLabel} (saved — type to replace)` : m.secretLabel} type="password"
            value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }}
            helperText="Write-only: stored server-side, never returned to the browser." />
        )}
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Button variant="contained" disableElevation disabled={busy === "save"} onClick={saveCreds}>
            {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
          {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
        </Box>
      </Box>
    )},
    { label: "Test", done: !!conn.LastSyncAt && !conn.LastError, body: (
      <Box sx={{ mt: 1 }}>
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>Live probe — token / model / channel read, for real.</Typography>
        <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
          startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
        {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
          {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
        {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
      </Box>
    )},
    ...(m.srcLabel ? [{ label: m.srcLabel, done: mine.some((s) => s.Active), body: (
      <Box sx={{ mt: 1 }}>
        {mine.map((s) => (
          <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
            <StatusDot ok={!!s.Active} />
            <Typography sx={{ ...mono, color: INK, flex: 1, fontSize: 13 }} noWrap>{s.Address}</Typography>
            {s.LastPolledAt && <Typography variant="caption" sx={{ color: FAINT }}>polled {timeAgo(s.LastPolledAt)}</Typography>}
            <Switch checked={!!s.Active} onChange={() => toggleSource(s)} />
          </Box>
        ))}
        <Box sx={{ display: "flex", gap: 1, mt: 1.5, maxWidth: 460 }}>
          <TextField fullWidth placeholder={m.srcPh} value={newSrc} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setNewSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addSource()} />
          <Button variant="contained" disableElevation onClick={addSource}>Add</Button>
        </Box>
      </Box>
    )}] : []),
    ...(isAI ? [] : [{ label: "Role", done: !!(conn.Roles || "").length, body: <RoleStep conn={conn} reload={reload} /> }]),
    { label: "Enable", done: !!conn.Active, body: (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 1 }}>
        <Switch checked={!!conn.Active} onChange={(e) => setActive(e.target.checked)} />
        <Typography variant="body2" sx={{ color: DIM }}>
          {conn.Active
            ? (isAI ? "On — wired into intent triage (the first active AI connector wins)." : "On — polling on schedule and via Sync now.")
            : "Off — flip on once Test passes."}
        </Typography>
      </Box>
    )},
  ];

  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section="Connectors" onBack={onBack} title={conn.Name} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>{m.desc}</Typography>
      <UnderTabs tabs={["Setup", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Setup" && (
        <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
          {steps.map((s, i) => (
            <Step key={s.label} completed={s.done}>
              <StepButton onClick={() => setStep(i)}>{s.label}{s.done ? " ✓" : ""}</StepButton>
              <StepContent>{s.body}</StepContent>
            </Step>
          ))}
        </Stepper>
      )}
      {tab === "Guide" && <Steps steps={m.howto || []} />}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── SQL Server detail: connection wizard + guide (reports live on the Reports tab) ── */
function MssqlDetail({ conn, drivers, reload, onBack }) {
  const [tab, setTab] = useState("Connection");
  if (!conn) return null;
  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section="Connectors" onBack={onBack} title="Microsoft SQL Server" />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        The connection only — build the scheduled reports (query + AI summary) on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Connection" && <MssqlConnection conn={conn} drivers={drivers} reload={reload} />}
      {tab === "Guide" && <Steps steps={MSSQL_HOWTO} />}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── the SQL Server CONNECTION (set up once; reports inherit it) ────────── */
function MssqlConnection({ conn, drivers, reload }) {
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [step, setStep] = useState(conn.LastSyncAt && !conn.LastError ? 1 : 0);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const sqlAuth = (cfg.auth || "windows") === "sql";

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true };
      if (secret) body.Secret = secret;
      await api.post("/api/connectors", body);
      setMsg("saved ✓"); setSecret(""); setStep(1); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
      <Step completed={!!(cfg.server || conn.LastSyncAt)}>
        <StepButton onClick={() => setStep(0)}>Connection</StepButton>
        <StepContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
            <TextField label="server" placeholder="localhost  ·  localhost\SQLEXPRESS  ·  HOST\INSTANCE" value={cfg.server || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, server: e.target.value })} />
            <TextField label="database" placeholder="master" value={cfg.database || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, database: e.target.value })} />
            <Select value={cfg.auth || "windows"} sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, auth: e.target.value })}>
              <MenuItem value="windows" sx={{ fontSize: 12.5 }}>Windows auth (local, trusted)</MenuItem>
              <MenuItem value="sql" sx={{ fontSize: 12.5 }}>SQL login</MenuItem>
            </Select>
            {sqlAuth && <TextField label="username" value={cfg.username || ""} sx={{ bgcolor: "#fff" }}
              onChange={(e) => setCfg({ ...cfg, username: e.target.value })} />}
            {sqlAuth && <TextField label={conn.HasSecret ? "password (saved — type to replace)" : "password"} type="password"
              value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }} />}
            <Select value={cfg.driver || ""} displayEmpty sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, driver: e.target.value })}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>(auto — newest installed driver)</MenuItem>
              {drivers.map((d) => <MenuItem key={d} value={d} sx={{ fontSize: 12.5 }}>{d}</MenuItem>)}
            </Select>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
                {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
              {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
            </Box>
          </Box>
        </StepContent>
      </Step>
      <Step completed={!!(conn.LastSyncAt && !conn.LastError)}>
        <StepButton onClick={() => setStep(1)}>Test connection</StepButton>
        <StepContent>
          <Typography variant="body2" sx={{ color: DIM, mb: 1, mt: 0.5 }}>Connects for real and reports the server version — every scheduled report inherits this connection.</Typography>
          <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
            startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
          {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
            {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
          {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
        </StepContent>
      </Step>
    </Stepper>
  );
}

/* ── Remote Windows (WinRM) detail: machine name + live probe; reports live on Reports ── */
function WinrmDetail({ conn, reload, onBack }) {
  const [tab, setTab] = useState("Connection");
  const [cfg, setCfg] = useState(parse(conn?.ConfigJson));
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!conn) return null;

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true });
      setMsg("saved ✓"); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section="Connectors" onBack={onBack} title="Remote Windows (WinRM)" />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Run PowerShell ON a machine you can RDP into (your Windows credentials) — the connection only;
        build the scheduled reports on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Guide" && <Steps steps={WINRM_HOWTO} />}
      {tab === "Connection" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
          <TextField label="machine name" placeholder="AZWEB01" value={cfg.host || ""} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setCfg({ ...cfg, host: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
              {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
            <Button variant="outlined" disabled={busy === "test" || !cfg.host} onClick={runTest}
              startIcon={busy === "test" ? <CircularProgress size={12} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
            {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
          </Box>
          {test && <Typography variant="body2" sx={{ fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
            {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
          {!test && conn.LastError && <Typography variant="body2" sx={{ color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
        </Box>
      )}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* What a connection IS to the hub. Three independent jobs - a system can do all three,
   or just be something the agents are allowed to touch. */
const ROLE_META = {
  trigger: ["Inbound trigger — creates work", "Poll it for new items, run them through triage, open tasks and draft replies. This is what turns a connection into work (mail, chats, GitHub issues…)."],
  feed: ["Timeline feed — shows, never assigns", "Poll it and show every new item on the Timeline, but stop there: no triage, no AI call, no task. Good for GitHub issues or a chatty channel you want to SEE without being handed."],
  report: ["Report source", "Selectable on the Reports tab: query it on a schedule and put the (optionally AI-summarized) result on the Timeline."],
  tool: ["Agent tool", "Named for the agents in SOUL.md as a system they may use — pull data from it, create and update things in it while working a task."],
};

const RoleStep = ({ conn, reload }) => {
  const roles = new Set(String(conn.Roles || "").split(",").filter(Boolean));
  const toggle = async (r) => {
    const next = new Set(roles);
    if (next.has(r)) next.delete(r); else next.add(r);
    // a trigger already puts its items on the timeline; holding both would just be a
    // contradiction the poller has to resolve
    if (r === "trigger" && next.has("trigger")) next.delete("feed");
    if (r === "feed" && next.has("feed")) next.delete("trigger");
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Roles: [...next].join(",") });
    reload();
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 620 }}>
      {Object.entries(ROLE_META).map(([key, [label, desc]]) => (
        <Box key={key} sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
          <Switch checked={roles.has(key)} onChange={() => toggle(key)} sx={{ mt: -0.5 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{label}</Typography>
            <Typography variant="body2" sx={{ color: DIM }}>{desc}</Typography>
          </Box>
        </Box>
      ))}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        {roles.has("trigger") ? "Trigger is on: new items become tasks, replies and reviews."
          : roles.has("feed") ? "Feed only: new items appear on the Timeline as information — nothing becomes work."
            : "Neither: nothing here is polled at all — it stays available to the agents and to reports."}
      </Typography>
    </Box>
  );
};

const Steps = ({ steps }) => (
  <Box sx={{ maxWidth: 720 }}>
    {steps.map((step, i) => (
      <Box key={i} sx={{ display: "flex", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
        <Box sx={{ ...mono, width: 24, height: 24, borderRadius: "50%", bgcolor: "#eef0ff", color: "#4f46e5",
          fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</Box>
        <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{step}</Typography>
      </Box>
    ))}
  </Box>
);
