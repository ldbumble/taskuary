// Scheduled reports - the pipeline builder: pick a source (a connection from the
// Connections tab, or an inline one), write the query, optionally an AI summary prompt,
// preview the whole pipeline, schedule it - results land on the Timeline. Connections
// stay pure connections; this tab is where reports are built and managed.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, CircularProgress, Dialog, DialogContent, DialogTitle,
  ListSubheader, MenuItem, Select, Step, StepButton, StepContent, Stepper, Switch, TextField,
  Typography,
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
import { NL, SOURCE_KEYS, addField, showValue, toShape, toSources } from "./sourceShape.js";
import { ASSISTANT, GRADIENT, PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, mono, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, Empty, FilterPills, SideRail, ConfirmDelete } from "./ui.jsx";

const AI_FIELD = ["AI summary prompt (optional)", "ai_prompt", "multiline",
  "e.g. Summarize headcount by site. Flag anything under 70 and any day-over-day drop."];
const FIELDS = {
  mssql: [["query", "query", "multiline", "SELECT TOP 20 * FROM ..."], AI_FIELD],
  database: [["query", "query", "multiline", "SELECT ... (any SQL the connected engine speaks)"], AI_FIELD],
  // service and operation are PICKED, not typed - see AwsPicker. botocore ships both lists
  // locally, so getting a name wrong no longer waits until a scheduled run fails to tell you.
  aws: [["service", "service", "aws_service", "s3 · logs · ec2 · athena · dynamodb ..."],
    ["operation", "operation", "aws_operation", "list_buckets · describe_instances ..."],
    ["params (JSON)", "params", "multiline", '{"Bucket": "my-bucket"}'],
    ["path into the response", "path", "text", "Contents"], AI_FIELD],
  s3_object: [["bucket", "bucket", "aws_bucket", "pick a discovered bucket"],
    ["region", "region", "text", "us-east-1"],
    ["key — read this object (blank = list instead)", "key", "text", "reports/latest.csv"],
    ["prefix — list under this", "prefix", "text", "reports/"], AI_FIELD],
  cloudwatch_logs: [["log group", "log_group", "aws_log_group", "pick a discovered log group"],
    // a log group is (name, region). Picking one fills this in; it is here so a hand-typed name
    // can still be pointed at the right region instead of failing with "does not exist".
    ["region", "region", "text", "us-east-1"],
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
  // The Assistant silently pulls selected saved report pipelines; its prompt judges all of
  // those current views together. The selector itself lives in ReportWizard below.
  assistant: [],
  // the window starts at MIDNIGHT that many days back: 1 = all of yesterday plus today so far
  digest: [["days back (1 = all of yesterday + today so far; counted from midnight)", "days", "text", "1"], AI_FIELD],
  prometheus: [["PromQL query", "query", "multiline", 'up == 0   ·   sum(rate(http_requests_total[5m])) by (service)'], AI_FIELD],
  datadog: [["monitor name filter (blank = all monitors, trouble first)", "name", "text", "prod"], AI_FIELD],
  winrm: [["PowerShell to run on the remote box", "script", "multiline",
    "Get-Content C:/logs/latest.csv -Tail 20"], AI_FIELD],
  mcp: [["command", "cmd", "text", "npx / uvx / path to the MCP server"], ["args (one per line)", "args", "multiline", ""],
    ["tool", "tool", "text", "query"], ["tool args (JSON)", "tool_args", "multiline", '{"sql": "SELECT ..."}'], AI_FIELD],
  sqlite: [["db path", "db", "text", "C:/data/app.db"], ["query", "query", "multiline", "SELECT ..."], AI_FIELD],
  google_sheets: [["spreadsheet (URL or id)", "spreadsheet", "text", "https://docs.google.com/spreadsheets/d/…"],
    ["range (blank = the first sheet)", "range", "text", "Sheet1!A:F"], AI_FIELD],
  sharepoint_list: [["site", "site", "text", "contoso.sharepoint.com/sites/Ops"],
    ["list (its title in SharePoint)", "list", "text", "Requests"],
    ["max items", "top", "text", "200"], AI_FIELD],
  sharepoint_file: [["site", "site", "text", "contoso.sharepoint.com/sites/Ops"],
    ["path in the library (end with / to list a folder)", "path", "text", "Shared Documents/Reports/latest.xlsx"],
    ["sheet name (xlsx only, blank = the first)", "sheet", "text", ""],
    ["last N lines (text files only)", "tail", "text", "50"], AI_FIELD],
  local_file: [["file, folder, or a pattern", "path", "text", "C:/exports/sales-*.csv"],
    ["which one, when the pattern matches several", "pick", "pick_file", ""],
    ["last N lines (text and log files only)", "tail", "text", "50"],
    ["sheet name (xlsx only, blank = the first)", "sheet", "text", ""],
    ["path into the JSON (json only)", "path_expr", "text", "items"], AI_FIELD],
  intacct: [["object", "object", "text", "GLENTRY \u00b7 APBILL \u00b7 VENDOR \u00b7 GLACCOUNT \u00b7 LOCATION \u00b7 GLBUDGETITEM"],
    ["fields (comma separated \u2014 blank = every field on the object)", "fields", "csv_list",
      "RECORDNO, VENDORID, TOTALDUE, WHENDUE"],
    ["filters, one per line: FIELD op value", "filters", "filter_lines",
      "WHENDUE <= 08/31/2026\nSTATE = Posted"], AI_FIELD],
  intacct_fields: [["object", "object", "text", "APBILL \u2014 what does this object actually carry?"], AI_FIELD],
  // the semantic layer (Assistant \u2192 Numbers): a number that was PROVED against numbers the owner
  // already knew, and the scheduled check that demotes it the day it stops reconciling
  metric: [["metric name", "name", "text", "the certified metric to read"],
    ["scope \u2014 whatever names one row of the grain", "scope", "text", "a site, a division, an entity"],
    ["period", "period", "text", "2026-07 \u00b7 2026 \u00b7 2026-07-01..2026-07-31"], AI_FIELD],
  metric_check: [["metric name (blank = check every one)", "name", "text", ""], AI_FIELD],
  // the AI itself as the source: a coding CLI agent runs a saved skill (a slash command) and/or a
  // prompt on the schedule, and what it answers IS the report - "run my weekly user-management
  // review every Monday". The summary pass is optional: the agent already wrote prose.
  agent: [["skill — the slash command the agent should run (optional)", "skill", "text", "/weekly-user-review"],
    ["prompt — what to do, or what the skill needs to know", "prompt", "multiline", "Review this week's user-management changes and list anything unusual."],
    ["agent (blank = coder)", "agent", "text", "coder · codex · gemini"],
    ["repository folder — for a skill that lives in a repo (optional)", "cwd", "text", "C:/work/fanapp"],
    ["model (optional — the agent's default otherwise)", "model", "text", ""], AI_FIELD],
  rest: [["url", "url", "text", "https://api.example.com/items"], ["headers (JSON)", "headers", "multiline", '{"Authorization": "Bearer ..."}'], ["json path", "path", "text", "data.items"], AI_FIELD],
  rss: [["feed url", "url", "text", "https://example.com/feed.xml"], AI_FIELD],
  // Research: the web as a source. Each is one REST call with a key on its card - what is NOT
  // here is anything that drives a browser (logging in, clicking), which needs CDP and a client
  // library rather than an API.
  exa: [["what to search for", "query", "multiline", "companies shipping local-first AI tools, last 30 days"],
    ["how many results", "num", "text", "8"],
    ["only these domains (optional, comma separated)", "domains", "text", "news.ycombinator.com, lobste.rs"],
    ["published since (optional)", "since", "text", "2026-01-01"], AI_FIELD],
  tavily: [["what to search for", "query", "multiline", "what changed in the EU AI Act this month"],
    ["depth", "depth", "text", "basic — or advanced for a harder question"],
    ["how many results", "num", "text", "8"],
    ["news window (optional)", "time_range", "text", "day · week · month · year"], AI_FIELD],
  firecrawl: [["page to read", "url", "text", "https://example.com/pricing"], AI_FIELD],
  reader: [["page to read", "url", "text", "https://example.com/pricing"], AI_FIELD],
};
// A cron line, said in words when it is one of the shapes people actually write; the raw
// expression stays for anything cleverer, because a wrong paraphrase is worse than none.
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const cronText = (expr) => {
  const f = String(expr || "").trim().split(/\s+/);
  if (f.length !== 5) return `cron ${expr}`;
  const [mi, h, dom, mon, dow] = f;
  const hhmm = /^\d+$/.test(mi) && /^\d+$/.test(h) ? `${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}` : null;
  const every = (x, unit) => { const m = /^\*\/(\d+)$/.exec(x); return m ? `every ${m[1]}${unit}` : null; };
  if (h === "*" && dom === "*" && mon === "*" && dow === "*") return every(mi, "m") || (mi === "*" ? "every minute" : `cron ${expr}`);
  if (mi !== "*" && dom === "*" && mon === "*" && dow === "*") return every(h, "h") ? `${every(h, "h")} at :${String(mi).padStart(2, "0")}` : hhmm ? `daily ${hhmm}` : `cron ${expr}`;
  if (hhmm && dom === "*" && mon === "*") {
    if (dow === "1-5") return `weekdays ${hhmm}`;
    if (dow === "0,6" || dow === "6,0") return `weekends ${hhmm}`;
    const days = dow.split(",").map((d) => DOW[Number(d) % 7]).filter(Boolean);
    if (days.length && days.length === dow.split(",").length) return `${days.join(", ")} ${hhmm}`;
  }
  if (hhmm && mon === "*" && dow === "*" && /^\d+$/.test(dom)) return `the ${dom}${["th", "st", "nd", "rd"][(dom % 10 > 3 || [11, 12, 13].includes(dom % 100)) ? 0 : dom % 10]} of the month ${hhmm}`;
  return `cron ${expr}`;
};

const TYPE_LABELS = {
  mssql: "SQL Server", winrm: "Remote Windows", mcp: "MCP server", sqlite: "SQLite", rest: "REST / JSON", rss: "RSS / Atom",
  database: "Any database", aws: "AWS (any call)", s3_object: "S3 object", cloudwatch_logs: "CloudWatch logs",
  azure: "Azure (ARM)", azure_blob: "Azure blob", azure_logs: "Azure Log Analytics",
  entra_users: "Entra ID — people", entra_groups: "Entra ID — group members",
  entra_signins: "Entra ID — sign-ins", entra_licenses: "Entra ID — licence seats",
  prometheus: "Prometheus", datadog: "Datadog monitors",
  intacct: "Sage Intacct", intacct_fields: "Intacct \u2014 what fields exist",
  metric: "A certified number (Assistant \u2192 Numbers)", metric_check: "Re-prove the certified numbers",
  digest: "Taskuary digest", automate: "Automation ideas (own data)", assistant: "Assistant — its post on the Timeline (its voice: COUNSEL.md, Docs tab)",
  agent: "AI agent — run a skill or a prompt",
  local_file: "File on this computer",
  google_sheets: "Google Sheet", sharepoint_list: "SharePoint list", sharepoint_file: "SharePoint file",
  exa: "Exa — search the web", tavily: "Tavily — search + answer",
  firecrawl: "Firecrawl — read a page", reader: "Jina Reader — read a page (no key)",
};

/* The picker was 21 flat entries in the order the registry happens to list them, which is not a
   list anybody reads - it is a list you scroll while hoping. Grouped by where the data LIVES,
   because that is what you know when you arrive: on this machine, in a database, at AWS, in
   Microsoft, somewhere on the web. Anything new falls into "Other" rather than vanishing. */
/* An example ask per type. "AP bills due in the next 30 days" tells you what kind of sentence
   the box wants far better than an empty field does, and the types not listed here fall back to
   a generic line rather than needing one written for them. */
const PLACEHOLDER_FOR = {
  intacct: "AP bills due in the next 30 days — the vendor, the amount and the site",
  intacct_fields: "what a vendor bill carries in our company",
  metric: "occupancy for each site, last month",
  mssql: "yesterday's census by facility",
  database: "open orders by customer, newest first",
  sqlite: "the last 50 rows of the events table",
  local_file: "the newest census export in C:/exports, totalled by site",
  google_sheets: "the headcount tab of our staffing sheet",
  sharepoint_list: "open requests in the Ops site's Requests list",
  rest: "the open incidents from our status API",
  entra_users: "accounts that are disabled but still licensed",
  cloudwatch_logs: "errors in the api log group over the last 24 hours",
  s3_object: "the newest file under reports/ in our exports bucket",
  agent: "run my weekly user-management review",
  tavily: "what changed in nursing-home staffing rules this week",
};

const TYPE_GROUPS = [
  ["This computer", ["local_file", "sqlite", "mcp"]],
  ["Files & sheets", ["google_sheets", "sharepoint_list", "sharepoint_file"]],
  ["Databases", ["mssql", "database"]],
  ["AWS", ["aws", "s3_object", "cloudwatch_logs"]],
  ["Azure", ["azure", "azure_blob", "azure_logs"]],
  ["Microsoft 365 — Entra ID", ["entra_users", "entra_groups", "entra_signins", "entra_licenses"]],
  ["Monitoring", ["prometheus", "datadog"]],
  ["Corporate systems", ["intacct", "intacct_fields", "metric", "metric_check"]],
  ["The AI itself", ["agent"]],
  ["Research the web", ["tavily", "exa", "reader", "firecrawl"]],
  ["The web", ["rest", "rss"]],
  ["Windows", ["winrm"]],
  ["Taskuary's own data", ["digest", "automate", "assistant"]],
];
// which connector CARD a type's credentials live on (mirrors reports.card_of server-side)
const CARD_OF = { s3_object: "aws", cloudwatch_logs: "aws", azure_blob: "azure", azure_logs: "azure",
  entra_users: "azure", entra_groups: "azure", entra_signins: "azure", entra_licenses: "azure",
  intacct_fields: "intacct", sharepoint_list: "sharepoint", sharepoint_file: "sharepoint" };
const CARD_LABELS = { mssql: "SQL Server", winrm: "Remote Windows", database: "Any database", aws: "AWS", azure: "Azure",
  sharepoint: "SharePoint", google_sheets: "Google Sheets",
  prometheus: "Prometheus", datadog: "Datadog", exa: "Exa", tavily: "Tavily", firecrawl: "Firecrawl",
  intacct: "Sage Intacct" };
const BLANK = { type: "mssql", title: "", every_minutes: "", daily_at: "" };
const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };

export default function ReportsView() {
  const [sources, setSources] = useState(null);
  const [types, setTypes] = useState([]);
  const [connectors, setConnectors] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [note, setNote] = useState(null);
  const [err, setErr] = useState("");
  const [bucket, setBucket] = useState(() => {
    const found = /report=(\d+)/.exec(window.location.hash || "");
    return found ? Number(found[1]) : "all";
  });   // which rail section is open (a newly promoted discussion links straight to its editor)
  const [q, setQ] = useState("");

  const [lastRuns, setLastRuns] = useState({});   // per source: what its last run read and did
  const load = useCallback(async () => {
    try {
      const [s, t, c, r] = await Promise.all([api.get("/api/sources"), api.get("/api/report-types"), api.get("/api/connectors"),
        api.get("/api/reports/last-runs").catch(() => ({ data: { data: {} } }))]);
      setSources((s.data.data || []).filter((x) => x.Channel === "report"));
      setTypes(t.data.data || []); setConnectors(c.data.data || []); setLastRuns(r.data.data || {});
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load reports"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // a report run is synchronous and can take a while (a slow query, an AI pass) - say so
  // on the row that's working instead of leaving a dead button
  const [draft, setDraft] = useState(null);   // a composed config waiting in the builder
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

  /* The rail lists the REPORTS, not categories of them, and picking one opens its fields
     right there - no second click through an Edit button, which is the whole point of a
     master-detail layout. "All reports" keeps the overview with the per-row Run/Edit
     controls; a title selects that report and the pipeline appears beside it. */
  const titleOf = (s) => parse(s.ConfigJson).title || s.Address || `report ${s.SourceId}`;
  const railItems = [
    { key: "all", label: "All reports", n: sources.length || null },
    ...sources.map((s) => ({ key: s.SourceId, label: titleOf(s) })),
    { key: "new", label: "+ New report" },
  ];
  const list = sources.filter((s) => !q || titleOf(s).toLowerCase().includes(q.toLowerCase()));
  const openId = bucket === "new" ? null : bucket;
  const open = bucket !== "all" && !q;

  return (
    <SideRail title="Reports" q={q} setQ={setQ} placeholder="Search reports…"
      items={railItems} value={bucket} onChange={setBucket}
      note="A report is a pipeline: source → query → optional AI summary → your Timeline. The connections themselves live on the Connections tab.">
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      {open ? (
        <ReportWizard key={String(bucket) + (draft ? "-draft" : "")} sourceId={openId} sources={sources}
          types={types} connectors={connectors} draft={draft}
          reload={load} onBack={() => { setBucket("all"); setDraft(null); load(); }}
          onSaved={(sid) => { setDraft(null); setBucket(sid); }} />
      ) : (<>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, flex: 1, minWidth: 0 }} noWrap>
          {q ? `Matches for “${q}”` : "Scheduled reports"}
        </Typography>
        <Button size="small" variant="outlined" disableElevation onClick={syncNow} disabled={syncing} sx={{ mr: 1 }}
          startIcon={syncing ? <CircularProgress size={12} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Running…" : "Run due now"}
        </Button>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => { setQ(""); setBucket("new"); }} sx={{ background: GRADIENT }}>New report</Button>
      </Box>
      {note && <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 600, color: note.ok ? "#47654a" : "#6b2733" }}>{note.ok ? "✓" : "✗"} {note.detail}</Typography>}
      <Composer onDraft={(config, meta) => {
        setDraft(config);
        setNote({ ok: true, detail: `${meta.explain || "Drafted."} Check it below and preview before saving.`
          + (meta.confidence === "low" ? " It is not confident about this one." : "") });
        setBucket("new");
      }} />
      {!sources.length ? <Empty>No reports yet — "New report" walks you through source, query, AI summary and schedule.</Empty>
        : !list.length && <Empty>Nothing here.</Empty>}
      {list.map((s) => {
        const c = parse(s.ConfigJson);
        // both halves, not the first one: "on startup" alone hid the Monday cron behind it
        const sched = [c.on_startup && "on startup", c.cron && cronText(c.cron),
          c.every_minutes && `every ${c.every_minutes}m`, c.daily_at && `daily ${c.daily_at}`]
          .filter(Boolean).join(" + ") || "daily";
        return (
          <Box key={s.SourceId} sx={{ borderBottom: `1px solid ${BORDER}` }}>
          <Box onClick={() => { setQ(""); setBucket(s.SourceId); }}
            sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.5, cursor: "pointer",
              "&:hover": { bgcolor: "#faf8f4" } }}>
            <StatusDot ok={!!s.Active} />
            <ChannelIcon channel="report" />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }} noWrap>{c.title || s.Address}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT }}>
                {(c.sources || []).length > 1 ? `${c.sources.length} sources` : (TYPE_LABELS[c.type] || c.type || "rest")} · {sched}{s.LastPolledAt ? ` · ran ${timeAgo(s.LastPolledAt)}` : " · never ran"}
              </Typography>
            </Box>
            {c.ai_prompt && <Box sx={{ display: "flex", alignItems: "center", gap: 0.4, px: 1, py: 0.25, borderRadius: 99,
              bgcolor: "#eae4d8", border: "1px solid #d8cfbe" }}>
              <AutoAwesomeIcon sx={{ fontSize: 12, color: "#55697a" }} />
              <Typography variant="caption" sx={{ color: "#55697a", fontWeight: 700, fontSize: 10 }}>AI summary</Typography>
            </Box>}
            <Button size="small" disabled={running === s.SourceId}
              startIcon={running === s.SourceId ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}
              onClick={(e) => { e.stopPropagation(); runNow(s.SourceId); }}>{running === s.SourceId ? "Running…" : "Run now"}</Button>
            <Button size="small" onClick={() => { setQ(""); setBucket(s.SourceId); }}>Edit</Button>
            <Switch checked={!!s.Active} onClick={(e) => e.stopPropagation()}
              onChange={async () => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); load(); }} />
          </Box>
          {lastRuns[s.SourceId] && <LastRun r={lastRuns[s.SourceId]} sid={s.SourceId} />}
          </Box>
        );
      })}
      </>)}
    </SideRail>
  );
}

/* ── the pipeline wizard: source → configure → test & preview → schedule ── */
/* WHERE a report goes. A chat id is a Graph id, a WhatsApp JID, a Discord channel number -
   nothing anyone types from memory, and a typo is a report that quietly goes nowhere at 6am.
   So both halves are PICKED out of what Taskuary can actually reach today (/api/send-targets:
   the channels with a live connector and replies switched on, and the destinations already seen
   on each). Email is the one exception - an address you have never had mail from is still a real
   address - so there, and only there, you may type one as well. */
function Destination({ dest, onChange, targets }) {
  const chans = targets.map((t) => t.channel);
  const ch = dest.channel || chans[0] || "";
  const opts = targets.find((t) => t.channel === ch)?.to || [];
  const picked = String(dest.to || "").split(",").map((x) => x.trim()).filter(Boolean);
  const named = (to) => opts.find((o) => o.to === to)?.name || to;
  const empty = ch ? `no ${ch} chat seen yet` : "connect a channel first";
  return (
    <>
      <Select size="small" value={ch} sx={{ bgcolor: "#fff", fontSize: 12.5, minWidth: 130 }} displayEmpty
        onChange={(e) => onChange({ channel: e.target.value, to: "" })}>
        {(!ch || chans.includes(ch) ? chans : [...chans, ch]).map((c) => (
          <MenuItem key={c} value={c} sx={{ fontSize: 12 }}>{c}{chans.includes(c) ? "" : " — not set up"}</MenuItem>
        ))}
        {!chans.length && <MenuItem value="" sx={{ fontSize: 12, color: FAINT }}>nothing can send yet</MenuItem>}
      </Select>
      {ch === "email" ? (
        <Autocomplete multiple freeSolo size="small" sx={{ flex: 1, minWidth: 240 }} options={opts.map((o) => o.to)}
          value={picked} onChange={(_e, v) => onChange({ to: v.map((x) => String(x).trim()).filter(Boolean).join(", ") })}
          renderOption={(props, o) => (
            <li {...props} style={{ fontSize: 12.5 }}>{named(o)}{named(o) !== o && <span style={{ color: FAINT }}>&nbsp;&middot; {o}</span>}</li>
          )}
          renderInput={(params) => <TextField {...params} sx={{ bgcolor: "#fff" }} label="to — who gets it"
            placeholder={picked.length ? "" : "pick, or type an address"} />} />
      ) : (
        <Select size="small" displayEmpty value={picked[0] || ""} sx={{ bgcolor: "#fff", flex: 1, minWidth: 240, fontSize: 12.5 }}
          onChange={(e) => onChange({ to: e.target.value })}
          renderValue={(v) => (v ? named(v) : <span style={{ color: FAINT }}>{opts.length ? "to — the chat it lands in" : empty}</span>)}>
          {opts.map((o) => (
            <MenuItem key={o.to} value={o.to} sx={{ fontSize: 12, display: "block", py: 0.5 }}>
              <Typography variant="body2" sx={{ fontSize: 12.5, color: INK, fontWeight: 600 }}>{o.name}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10 }}>
                {[o.name === o.to ? "" : o.to, o.hint].filter(Boolean).join(" · ")}
              </Typography>
            </MenuItem>
          ))}
          {picked.filter((t) => !opts.some((o) => o.to === t)).map((t) => (
            <MenuItem key={t} value={t} sx={{ fontSize: 12 }}>{t} &mdash; saved, not seen lately</MenuItem>
          ))}
          {!opts.length && (
            <MenuItem value="" disabled sx={{ fontSize: 11.5, color: FAINT }}>
              {empty} &mdash; write something in the chat you want and it appears here
            </MenuItem>
          )}
        </Select>
      )}
    </>
  );
}

function ReportWizard({ sourceId, sources, types, connectors, reload, onBack, onSaved, draft }) {
  const cur = sources.find((s) => s.SourceId === sourceId);
  // a composed draft is a STARTING POINT, not a saved report: it lands in the same boxes the
  // owner would have filled in, and nothing exists until they preview it and press save
  const saved = cur ? { ...BLANK, ...parse(cur.ConfigJson) } : { ...BLANK, ...(draft || {}) };
  const [cfg, setCfg] = useState(saved);
  const [srcs, setSrcs] = useState(toSources(saved));   // the funnel's inputs, in order
  // the Assistant's OWN data sources: a system it checks without a saved report standing behind it
  const [watchSrcs, setWatchSrcs] = useState(() => (Array.isArray(saved.watch_sources) ? saved.watch_sources : []));
  const [drag, setDrag] = useState(null);
  const [step, setStep] = useState(0);
  const [test, setTest] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [brains, setBrains] = useState([]);   // which AI writes THIS summary - same roster as triage
  useEffect(() => { api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {}); }, []);
  // where it may be SENT: only live channels, only destinations Taskuary knows (see Destination)
  const [targets, setTargets] = useState([]);
  useEffect(() => { api.get("/api/send-targets").then(({ data }) => setTargets(data.data || [])).catch(() => {}); }, []);
  // switching one of these blocks on should leave a config that works: the first live channel,
  // addressed to your own notify chat - not an empty box beside a channel you never connected
  const firstDest = () => ({ channel: targets[0]?.channel || "email", to: targets[0]?.to?.[0]?.to || "" });
  const mssqlConn = connectors.find((c) => c.Type === "mssql");
  const mssqlOk = mssqlConn?.LastSyncAt && !mssqlConn?.LastError;
  const winrmConn = connectors.find((c) => c.Type === "winrm");
  const winrmOk = winrmConn?.LastSyncAt && !winrmConn?.LastError;
  const aiActive = connectors.some((c) => ["anthropic", "openai", "azure_openai"].includes(c.Type) && c.Active && c.HasSecret);

  const bodyCfg = () => {
    const c = { ...cfg };
    // an empty recipient means it was switched on and never filled in - saving that would make
    // a report that tries to send to nobody on every run
    if (c.deliver && !String(c.deliver.to || "").trim()) delete c.deliver;
    // same for the alert: switched on with nowhere to send is a rule that can only fail at 3am
    if (c.alert && !String(c.alert.to || "").trim()) delete c.alert;
    if (c.alert?.count != null && c.alert.count !== "") c.alert = { ...c.alert, count: Number(c.alert.count) };
    for (const k of SOURCE_KEYS) delete c[k];            // sources live in sources[] now
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null) delete c[k];
    if (c.every_minutes) c.every_minutes = Number(c.every_minutes);
    const list = srcs.map(toShape).filter((x) => x.type);
    // the Assistant's own sources ride alongside, never in sources[] - that array IS the report's
    // pipeline, and the Assistant's pipeline is itself; these are systems it reads before it thinks
    const watch = watchSrcs.map(toShape).filter((x) => x.type);
    if (watch.length) c.watch_sources = watch; else delete c.watch_sources;
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
  /* "Save report is not working" - it was refusing, correctly, and saying so into a state that
     is only rendered on step TWO. The button is on step three. So an empty title produced a
     click that did nothing, explained nothing, and never reached the server. Three things wrong
     at once: the message had nowhere to appear, the button did not know it could not work, and a
     POST that failed for any other reason threw into a void with no catch anywhere. */
  const [saveErr, setSaveErr] = useState("");
  const [savedMsg, setSavedMsg] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  const save = async () => {
    setSaveErr(""); setSavedMsg("");
    const c = bodyCfg();
    if (!c.title) { setSaveErr("Give the report a title first — it is the headline on the Timeline (step 1)."); return; }
    const body = { Channel: "report", Address: c.title, ConfigJson: JSON.stringify(c), Active: true };
    if (cur) body.SourceId = cur.SourceId;
    try {
      const { data } = await api.post("/api/sources", body);
      await reload();
      setSavedMsg("saved — enabled and scheduled");
      onSaved?.(data.sourceId);
    } catch (e) {
      setSaveErr(e?.response?.data?.detail || e?.message || "the server refused to save it");
    }
  };

  const typeOptions = types.filter((t) => t.status === "builtin");
  const isAssistant = cfg.type === "assistant" || (srcs.length === 1 && srcs[0].type === "assistant");
  const watchChoices = sources.filter((s) => s.SourceId !== cur?.SourceId && parse(s.ConfigJson).type !== "assistant")
    .map((s) => { const c = parse(s.ConfigJson); return { id: s.SourceId, title: c.title || s.Address,
      type: (c.sources || []).length > 1 ? `${c.sources.length} sources` : (TYPE_LABELS[c.type] || c.type || "report"), active: !!s.Active }; });
  const watchedIds = (Array.isArray(cfg.watch_source_ids) ? cfg.watch_source_ids : []).map(Number);
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Reports" onBack={onBack} title={cur ? (parse(cur.ConfigJson).title || "Edit report") : "New report"} />
      <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
        <Step completed={!!String(cfg.title || "").trim() && srcs.some((x) => x.type)}>
          <StepButton onClick={() => setStep(0)}>Pipeline</StepButton>
          <StepContent>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1.5 }}>
              {isAssistant
                ? "Point it at the systems it should read on every check — write the query here, or reuse a data view you already saved — then tell it what deserves your attention across all of them."
                : "Sources at the top feed one prompt at the bottom. Add as many as you want — the same connection twice with different queries is fine, and every source's rows reach the summary together."}
            </Typography>
            <TextField required label="title — becomes the Timeline headline" value={cfg.title || ""} sx={{ bgcolor: "#fff", maxWidth: 720, mb: 2 }}
              fullWidth onChange={(e) => setCfg({ ...cfg, title: e.target.value })} />

            {isAssistant && (
              <Box sx={{ ...card, p: 1.5, mb: 1.5, maxWidth: 720, bgcolor: PANEL2 }}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13, mb: 0.4 }}>Systems and data views to check</Typography>
                <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>
                  Anything a report can read — Intacct queries, databases, REST or MCP tools, cloud systems, files, agent skills. Add it here and nothing else needs to exist: the Assistant pulls it silently on its own schedule and files no intermediate report.
                </Typography>
                {/* "I don't know what fields off hand Intacct has set up" - so this step cannot be a
                    form. Describe what the Assistant should keep an eye on and the composer adds
                    the cards for it: only systems that are actually connected, field names read off
                    the real schema, and a question back rather than a guessed filter. */}
                <SourceComposer hint="Describe what the Assistant should keep an eye on"
                  placeholder={"AP bills from Intacct due in the next 30 days, and the cash balance by entity."
                    + NL + "Anything unpaid over 10k, this week's failed sign-ins, and yesterday's census by site."}
                  onSources={(list, prompt) => {
                    setWatchSrcs((cur) => [...cur, ...list]);
                    // its own prompt is the owner's to write; a composed one only fills a blank
                    if (prompt) setCfg((c) => (c.ai_prompt ? c : { ...c, ai_prompt: prompt }));
                  }} />
                {/* "we don't have to choose a pre-existing report to ask the Assistant about other
                    data" - right, and the picker below made that a lie. A source card here IS a
                    source: the same types, the same Test button, owned by this check alone. */}
                <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "stretch", mb: 1.25 }}>
                  {watchSrcs.map((src, i) => (
                    <SourceCard key={i} src={src} index={i} count={watchSrcs.length} removable
                      typeOptions={typeOptions.filter((t) => t.type !== "assistant")} connectors={connectors}
                      onChange={(patch) => setWatchSrcs((cur) => cur.map((x, k) => (k === i ? { ...x, ...patch } : x)))}
                      onRetype={(t) => setWatchSrcs((cur) => cur.map((x, k) => (k === i ? { type: t, label: x.label } : x)))}
                      onFill={(one) => setWatchSrcs((cur) => cur.map((x, k) => (k === i ? { ...one, label: one.label || x.label } : x)))}
                      onCopy={() => setWatchSrcs((cur) => [...cur.slice(0, i + 1), { ...src, label: `${src.label || src.type} copy` }, ...cur.slice(i + 1)])}
                      onRemove={() => setWatchSrcs((cur) => cur.filter((_, k) => k !== i))} />
                  ))}
                  <Box onClick={() => setWatchSrcs((cur) => [...cur, { type: "mssql" }])}
                    sx={{ ...card, width: 354, minHeight: 108, display: "flex", flexDirection: "column", alignItems: "center",
                      justifyContent: "center", gap: 0.5, cursor: "pointer", borderStyle: "dashed", bgcolor: "#fff",
                      color: DIM, "&:hover": { borderColor: "#d8cfbe", color: "#55697a" } }}>
                    <AddIcon sx={{ fontSize: 20 }} />
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>add a data source</Typography>
                    <Typography variant="caption" sx={{ color: FAINT }}>no saved report needed</Typography>
                  </Box>
                </Box>
                <Typography variant="caption" sx={{ color: INK, fontWeight: 700, display: "block", mb: 0.5 }}>
                  …and pull these saved data views too (optional)
                </Typography>
                <Autocomplete multiple options={watchChoices} value={watchChoices.filter((o) => watchedIds.includes(o.id))}
                  getOptionLabel={(o) => o.title || ""} isOptionEqualToValue={(o, v) => o.id === v.id}
                  onChange={(_e, values) => setCfg({ ...cfg, watch_source_ids: values.map((o) => o.id) })}
                  renderOption={(props, o) => (
                    <Box component="li" {...props} key={o.id} sx={{ display: "flex", gap: 1 }}>
                      <Typography sx={{ fontSize: 12.5, flex: 1 }}>{o.title}</Typography>
                      <Typography variant="caption" sx={{ color: FAINT }}>{o.type}{o.active ? "" : " · report schedule off"}</Typography>
                    </Box>
                  )}
                  renderInput={(params) => <TextField {...params} size="small" sx={{ bgcolor: "#fff" }}
                    placeholder={watchChoices.length ? "Choose views…" : "Create another report/data view first"} />} />
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
                  A view may stay disabled as a standalone report and still be pulled here. Its query and credentials remain owned by that view and its connector.
                </Typography>
              </Box>
            )}

            {/* ── the funnel: source cards, draggable, converging on the prompt ── */}
            {/* two cards and a gap make exactly the 720 the prompt and the two cards below it are, so
                the column has one right edge instead of three */}
            <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "stretch", maxWidth: 720 }}>
              {srcs.map((src, i) => (
                <SourceCard key={i} src={src} index={i} count={srcs.length}
                  typeOptions={typeOptions} connectors={connectors}
                  dragging={drag === i}
                  onDragStart={() => setDrag(i)} onDragEnd={() => setDrag(null)}
                  onDropHere={() => { if (drag === null || drag === i) return;
                    setSrcs((cur) => { const n = [...cur]; const [m] = n.splice(drag, 1); n.splice(i, 0, m); return n; }); setDrag(null); }}
                  onChange={(patch) => setSrcs((cur) => cur.map((x, k) => (k === i ? { ...x, ...patch } : x)))}
                  onRetype={(t) => setSrcs((cur) => cur.map((x, k) => (k === i ? { type: t, label: x.label } : x)))}
                  onFill={(one) => setSrcs((cur) => cur.map((x, k) => (k === i ? { ...one, label: one.label || x.label } : x)))}
                  onCopy={() => setSrcs((cur) => [...cur.slice(0, i + 1), { ...src, label: `${src.label || src.type} copy` }, ...cur.slice(i + 1)])}
                  onRemove={() => setSrcs((cur) => cur.filter((_, k) => k !== i))} />
              ))}
              {!isAssistant && <Box onClick={() => setSrcs((cur) => [...cur, { type: "mssql" }])}
                sx={{ ...card, width: 354, minHeight: 120, display: "flex", flexDirection: "column", alignItems: "center",
                  justifyContent: "center", gap: 0.5, cursor: "pointer", borderStyle: "dashed",
                  color: DIM, "&:hover": { borderColor: "#d8cfbe", color: "#55697a" } }}>
                <AddIcon sx={{ fontSize: 20 }} />
                <Typography variant="body2" sx={{ fontWeight: 600 }}>add a source</Typography>
              </Box>}
            </Box>

            {/* everything above narrows into one prompt */}
            <Box sx={{ display: "flex", justifyContent: "center", py: 0.5 }}>
              <Box sx={{ width: 0, height: 0, borderLeft: "12px solid transparent", borderRight: "12px solid transparent",
                borderTop: `14px solid ${BORDER}` }} />
            </Box>
            <Box sx={{ ...card, p: 1.5, maxWidth: 720, bgcolor: "#fffdf7", borderColor: "#d8cfbe" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
                <AutoAwesomeIcon sx={{ fontSize: 15, color: "#55697a" }} />
                <Typography variant="caption" sx={{ color: "#55697a", fontWeight: 700 }}>
                  {isAssistant ? "WHAT SHOULD THE ASSISTANT SURFACE?" : `ONE PROMPT OVER ALL ${srcs.length > 1 ? `${srcs.length} SOURCES` : "THE ROWS"}`}
                </Typography>
              </Box>
              <TextField fullWidth multiline minRows={3} value={cfg.ai_prompt || ""} sx={{ bgcolor: "#fff" }}
                placeholder={isAssistant
                  ? "Tell me only what needs attention now. Across finance and operations, flag unusual totals or changes, thresholds crossed, missing expected activity, failures, and contradictions. Give the number, comparison, and source."
                  : AI_FIELD[3]} onChange={(e) => setCfg({ ...cfg, ai_prompt: e.target.value })} />
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
                    {isAssistant ? "which AI performs the proactive cross-system check" : "which AI writes this summary — a heavier model for the weekly review, the cheap tier for pings"}
                  </Typography>
                </Box>
              )}
              {cfg.ai_prompt && !aiActive && !cfg.ai_brain && (
                <Typography variant="body2" sx={{ mt: 0.75, fontWeight: 600, color: "#55697a" }}>
                  ⚠ AI prompt set, but no active AI connector — the raw data will file until you enable one (Connections → AI).
                </Typography>
              )}
              {!cfg.ai_prompt && (
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                  {isAssistant ? "Add a general instruction so it knows what is worth interrupting you about." : "Leave it empty to file the raw rows with no AI pass."}
                </Typography>
              )}
            </Box>

            {/* WHERE IT GOES. A report has always landed on the Timeline and stopped there; this
                is the same run turning around. Off by default: a report that quietly emailed
                somebody the first time you saved it would be the worst kind of surprise. */}
            <Box sx={{ mt: 2, ...card, p: 1.5, maxWidth: 720 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10, flex: 1 }}>
                  SEND IT SOMEWHERE (OPTIONAL)
                </Typography>
                <Switch size="small" checked={!!cfg.deliver}
                  onChange={(e) => setCfg({ ...cfg, deliver: e.target.checked ? { ...firstDest(), gate: "review" } : undefined })} />
              </Box>
              {!cfg.deliver ? (
                <Typography variant="caption" sx={{ color: FAINT }}>
                  Off — the report lands on your Timeline and goes nowhere else.
                </Typography>
              ) : (
                <>
                  <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
                    <Destination dest={cfg.deliver} targets={targets}
                      onChange={(d) => setCfg({ ...cfg, deliver: { ...cfg.deliver, ...d } })} />
                    <TextField size="small" sx={{ bgcolor: "#fff", flex: 1, minWidth: 180 }}
                      label="subject (blank = the report's headline)" value={cfg.deliver.subject || ""}
                      onChange={(e) => setCfg({ ...cfg, deliver: { ...cfg.deliver, subject: e.target.value } })} />
                  </Box>
                  <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center", flexWrap: "wrap" }}>
                    <Select size="small" value={cfg.deliver.gate || "review"} sx={{ bgcolor: "#fff", fontSize: 12.5, minWidth: 260 }}
                      onChange={(e) => setCfg({ ...cfg, deliver: { ...cfg.deliver, gate: e.target.value } })}>
                      <MenuItem value="review" sx={{ fontSize: 12 }}>wait for me to approve it (Review)</MenuItem>
                      <MenuItem value="auto" sx={{ fontSize: 12 }}>send it without asking</MenuItem>
                    </Select>
                    <Typography variant="caption" sx={{ color: (cfg.deliver.gate === "auto") ? "#55697a" : FAINT, flex: 1, minWidth: 200 }}>
                      {cfg.deliver.gate === "auto"
                        ? "This report will send on its schedule with nobody reading it first. Everything else in Taskuary waits for you — this is the one place you can turn that off, deliberately."
                        : "Each run lands in Review as a draft. Approving it sends; editing first is fine."}
                    </Typography>
                  </Box>
                </>
              )}
            </Box>
            {/* The opposite of "send it somewhere": say NOTHING unless the result trips a rule.
                A message that arrives whether or not anything is wrong is one you stop reading,
                so silence is the normal outcome here and an alert means go and look. */}
            <Box sx={{ mt: 2, ...card, p: 1.5, maxWidth: 720 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10, flex: 1 }}>
                  TELL ME WHEN IT LOOKS WRONG (OPTIONAL)
                </Typography>
                <Switch size="small" checked={!!cfg.alert}
                  onChange={(e) => setCfg({ ...cfg, alert: e.target.checked ? { when: "nothing_came_back", ...firstDest() } : undefined })} />
              </Box>
              {!cfg.alert ? (
                <Typography variant="caption" sx={{ color: FAINT }}>
                  Off — the report never messages you, however its result looks.
                </Typography>
              ) : (
                <>
                  <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap", alignItems: "center" }}>
                    <Select size="small" value={cfg.alert.when || "nothing_came_back"} sx={{ bgcolor: "#fff", fontSize: 12.5, minWidth: 250 }}
                      onChange={(e) => setCfg({ ...cfg, alert: { ...cfg.alert, when: e.target.value } })}>
                      <MenuItem value="nothing_came_back" sx={{ fontSize: 12 }}>nothing came back</MenuItem>
                      <MenuItem value="something_came_back" sx={{ fontSize: 12 }}>anything came back</MenuItem>
                      <MenuItem value="fewer_than" sx={{ fontSize: 12 }}>fewer rows than…</MenuItem>
                      <MenuItem value="more_than" sx={{ fontSize: 12 }}>more rows than…</MenuItem>
                      <MenuItem value="contains" sx={{ fontSize: 12 }}>the result mentions…</MenuItem>
                      <MenuItem value="missing" sx={{ fontSize: 12 }}>the result never mentions…</MenuItem>
                      <MenuItem value="failed" sx={{ fontSize: 12 }}>the report failed to run</MenuItem>
                    </Select>
                    {["fewer_than", "more_than"].includes(cfg.alert.when) && (
                      <TextField size="small" type="number" sx={{ bgcolor: "#fff", width: 120 }} label="how many"
                        value={cfg.alert.count ?? ""}
                        onChange={(e) => setCfg({ ...cfg, alert: { ...cfg.alert, count: e.target.value } })} />
                    )}
                    {["contains", "missing"].includes(cfg.alert.when) && (
                      <TextField size="small" sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} label="the words to look for"
                        value={cfg.alert.text || ""}
                        onChange={(e) => setCfg({ ...cfg, alert: { ...cfg.alert, text: e.target.value } })} />
                    )}
                  </Box>
                  <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
                    <Destination dest={cfg.alert} targets={targets}
                      onChange={(d) => setCfg({ ...cfg, alert: { ...cfg.alert, ...d } })} />
                    <TextField size="small" sx={{ bgcolor: "#fff", flex: 1, minWidth: 200 }}
                      label="what to say (optional)" value={cfg.alert.note || ""}
                      onChange={(e) => setCfg({ ...cfg, alert: { ...cfg.alert, note: e.target.value } })} />
                  </Box>
                  <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
                    Sent the moment the rule trips — no Review step, because an alert waiting for approval is not an alert.
                    Only channels with a live connection and replies on (Settings → Replies) are offered, and only chats Taskuary has already seen.
                  </Typography>
                </>
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
            {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#47654a" : "#6b2733" }}>{test.ok ? "✓" : "✗"} {test.detail}</Typography>}
            {preview && (preview.ok ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: "#47654a" }}>✓ {preview.headline}</Typography>
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
            ) : <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "#6b2733" }}>✗ {preview.error}</Typography>)}
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
              <TextField label="cron" value={cfg.cron || ""} sx={{ bgcolor: "#fff", width: 190 }}
                helperText={cfg.cron ? cronText(cfg.cron) : ""}
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
              {/* a report is informational by default. On, each run goes through triage like an inbound
                  message and TRIAGE.md decides whether it is work - an agent's research can then be handed
                  to the coding agent. A failed run is never triaged. */}
              <Box sx={{ display: "flex", alignItems: "center", ml: { sm: 1 } }}
                title="Send each run through triage like an inbound message. TRIAGE.md decides whether it becomes a task - so a report one agent researched can be handed to the coding agent. Off: informational, never a task.">
                <Switch checked={!!cfg.triage} onChange={(e) => setCfg({ ...cfg, triage: e.target.checked })} />
                <Typography variant="caption" sx={{ color: DIM }}>can become work (triage decides)</Typography>
              </Box>
              <Button variant="contained" disableElevation onClick={save} disabled={!cfg.title}
                title={cfg.title ? "" : "the report needs a title - step 1"}>Save report</Button>
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
              Pick one. Everything blank = once a day, whenever the app is open.
            </Typography>
            {/* WHAT WOULD BE WRONG. Without it the classifier reads a table of numbers with no idea
                which numbers would be bad, so every run came out informational and the switch above
                did nothing - see triage.classify_intent(watch=). */}
            {!!cfg.triage && (
              <Box sx={{ mt: 1.25 }}>
                <TextField fullWidth multiline minRows={2} size="small" value={cfg.watch_for || ""}
                  onChange={(e) => setCfg({ ...cfg, watch_for: e.target.value })}
                  label="Why you run this, and what would be off"
                  placeholder="flag a vendor we have not paid before, or a bill over $10k from a location we do not normally pay"
                  sx={{ "& .MuiInputBase-root": { fontSize: 13 } }} />
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                  Triage judges each run against this. Something matching becomes a task and an agent
                  looks into it; nothing matching stays informational. What it finds comes back to the
                  Timeline — it is never sent to anyone unless you name a destination below.
                </Typography>
                <Box sx={{ display: "flex", gap: 1, mt: 1.25, flexWrap: "wrap", alignItems: "center" }}>
                  <TextField size="small" value={(cfg.deliver_findings || {}).to || ""}
                    onChange={(e) => setCfg({ ...cfg, deliver_findings: { ...(cfg.deliver_findings || { channel: "email" }), to: e.target.value } })}
                    label="Send the findings to (optional)" placeholder="nobody — findings stay on the Timeline"
                    sx={{ minWidth: 280, "& .MuiInputBase-root": { fontSize: 13 } }} />
                  <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 200 }}>
                    Still drafted for your approval first — nothing about a report makes a send automatic.
                  </Typography>
                </Box>
              </Box>
            )}
            {!cfg.title && (
              <Typography variant="caption" sx={{ mt: 0.5, display: "block", color: "#55697a", fontWeight: 600 }}>
                No title yet — <Box component="span" sx={{ textDecoration: "underline", cursor: "pointer" }}
                  onClick={() => setStep(0)}>add one in step 1</Box> and this button wakes up.
              </Typography>
            )}
            {saveErr && <Alert severity="error" sx={{ mt: 1, fontSize: 12.5 }}>{saveErr}</Alert>}
            {savedMsg && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "#47654a" }}>✓ {savedMsg}</Typography>}
            {cur && (
              <Box sx={{ display: "flex", gap: 1, mt: 1.5, alignItems: "center" }}>
                <Button size="small" color="error" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />}
                  onClick={() => setConfirmDel(true)}>Delete report</Button>
              </Box>
            )}
          </StepContent>
        </Step>
      </Stepper>
      <ConfirmDelete open={confirmDel} what={`the report "${cfg.title || cur?.Address || "untitled"}"`}
        consequence="It stops running on its schedule and disappears from the Reports tab. Briefs it already filed stay on the Timeline."
        onClose={() => setConfirmDel(false)}
        onConfirm={async () => { await api.delete(`/api/sources/${cur.SourceId}`); await reload(); onBack(); }} />
    </Box>
  );
}

/* AWS service and operation, picked from botocore's own models - fetched once per card, and
   again per service for its operations. No AWS call is made to build either list.

   `seen` are the services discovery actually found objects for in THIS account, and they are
   pinned to the top of a 430-name alphabetical list, because the list is otherwise a haystack.
   freeSolo stays on: a service too new for the installed botocore must still be typeable. */
/* `objects: true` means the options are {name, region} rather than bare strings, and choosing
   one sets the REGION as well as the name. That is not a nicety: a log group belongs to ONE
   region, so a name picked from a list and run against the card's first region answers "The
   specified log group does not exist" - true, and completely misleading. */
const PICKS = {
  aws_service: { list: (d) => d.services, top: (d) => d.seen, label: "your keys already see these", rest: "everything botocore knows" },
  aws_operation: { list: (d) => d.operations, top: (d) => d.read, label: "reads only — safe for a report", rest: "everything else this service does" },
  aws_log_group: { list: (d) => d.log_groups, objects: true, group: (o) => `in ${o.region || "the default region"}` },
  aws_bucket: { list: (d) => d.buckets, objects: true, group: (o) => `in ${o.region || "the default region"}` },
};

function AwsPicker({ label, which, value, placeholder, service, onChange }) {
  const [cat, setCat] = useState(null);
  const spec = PICKS[which];
  useEffect(() => {
    // operations depend on the service; everything else is one fetch
    if (which === "aws_operation" && !service) { setCat({ options: [], top: [] }); return; }
    const q = which === "aws_operation" ? `?service=${encodeURIComponent(service)}` : "";
    api.get(`/api/aws/catalog${q}`)
      .then(({ data }) => setCat({ options: spec.list(data) || [], top: (spec.top?.(data)) || [], error: data.error }))
      .catch(() => setCat({ options: [], top: [] }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [which, service]);
  const top = new Set(cat?.top || []);
  const opts = cat?.options || [];
  const sorted = spec.objects ? opts : [...opts].sort((a, b) => (top.has(b) ? 1 : 0) - (top.has(a) ? 1 : 0));
  const empty = cat && !sorted.length;
  // the region of whatever is currently typed in, when we can recognise it
  const hit = spec.objects ? opts.find((o) => o.name === value) : null;
  return (
    <Autocomplete freeSolo autoHighlight options={sorted} size="small" fullWidth
      value={value ?? ""}
      getOptionLabel={(o) => (typeof o === "string" ? o : o?.name ?? "")}
      isOptionEqualToValue={(o, v) => (typeof o === "string" ? o : o.name) === (typeof v === "string" ? v : v?.name)}
      onChange={(_e, v) => onChange(typeof v === "string" || !v ? { value: v ?? "" } : { value: v.name, region: v.region })}
      onInputChange={(_e, v, reason) => reason === "input" && onChange({ value: v })}
      groupBy={spec.objects ? spec.group : (spec.rest ? (o) => (top.has(o) ? spec.label : spec.rest) : undefined)}
      renderInput={(params) => (
        <TextField {...params} label={label} sx={{ bgcolor: "#fff" }}
          // the placeholder used to show s3 examples whatever the service was, which reads as a
          // suggestion rather than as an example and is wrong for every other service
          placeholder={which === "aws_operation" ? (service ? `an operation on ${service}` : "") : placeholder}
          helperText={which === "aws_operation" && !service ? "pick a service first"
            : cat?.error ? cat.error
              : empty ? "nothing discovered yet — run Discover on the AWS card"
                : hit ? `in ${hit.region || "the default region"}`
                  : value && spec.objects ? "typed by hand — set the region below if it is not the card's first"
                    : undefined} />
      )} />
  );
}

/* Say what you want; the model writes the configuration.

   The Reports tab is a builder, and a builder asks you to know things first - which of
   twenty-odd source types your data is behind, what its config keys are called, what query
   language is on the other end. This asks for the sentence instead. What comes back is a
   DRAFT in the ordinary boxes: it is not saved, it has not run, and the next thing the owner
   does is preview it against the real system. Questions come back as questions rather than a
   guess, because a wrong filter on a finance report is silently wrong forever. */
function Composer({ onDraft }) {
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [answers, setAnswers] = useState({});

  const go = async (withAnswers) => {
    setBusy(true);
    try {
      const { data } = await api.post("/api/reports/compose", { ask, answers: withAnswers || undefined });
      setOut(data);
      if (data.config) { onDraft(data.config, data); setAsk(""); setAnswers({}); setOut(null); }
    } catch (e) { setOut({ error: e?.response?.data?.detail || "the composer could not be reached" }); }
    setBusy(false);
  };

  const answered = out?.questions?.length && out.questions.every((q) => String(answers[q] || "").trim());
  return (
    <Box sx={{ ...card, p: 1.5, mb: 2, bgcolor: PANEL2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mb: 0.9 }}>
        <AutoAwesomeIcon sx={{ fontSize: 15, color: ACCENT2 }} />
        <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: INK }}>Describe the report you want</Typography>
      </Box>
      <TextField fullWidth size="small" multiline minRows={2} value={ask} disabled={busy}
        sx={{ bgcolor: "#fff" }}
        placeholder={"Read C:/exports/daily-*.csv every morning, total the units by site and flag anything under 70."
          + NL + "Every Monday, list the AP bills from Intacct due in the next 30 days and call out anything over 10k."}
        onChange={(e) => setAsk(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && ask.trim()) go(); }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.9 }}>
        <Button size="small" variant="contained" disableElevation disabled={busy || !ask.trim()}
          onClick={() => go()} startIcon={busy ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />}>
          {busy ? "Working it out…" : "Build it"}
        </Button>
        <Typography sx={{ fontSize: 11, color: FAINT }}>
          It can only use connections you have set up — and it will ask rather than guess.
        </Typography>
      </Box>

      {out?.error && <Alert severity="warning" sx={{ mt: 1.25, fontSize: 12.5 }}>{out.error}</Alert>}

      {/* it did not know something. Better here than as a silently wrong WHERE clause. */}
      {out?.questions?.length > 0 && (
        <Box sx={{ mt: 1.25, display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ fontSize: 11.5, color: DIM, fontWeight: 600 }}>
            A couple of things it will not guess at:
          </Typography>
          {out.questions.map((qq) => (
            <TextField key={qq} size="small" fullWidth label={qq} sx={{ bgcolor: "#fff" }}
              value={answers[qq] || ""} onChange={(e) => setAnswers({ ...answers, [qq]: e.target.value })} />
          ))}
          <Button size="small" variant="contained" disableElevation disabled={busy || !answered}
            onClick={() => go(answers)} sx={{ alignSelf: "flex-start" }}>Answer & build</Button>
        </Box>
      )}
    </Box>
  );
}

/* "I don't know what fields off hand Intacct has set up." Right - so a source card is not a form
   to fill in from memory. Say what you want out of the system and this writes the card: it may
   only choose a connection that exists, and it goes and READS the schema first (an object's real
   field list, a table's columns) so the names are this company's own rather than plausible.

   One component for both callers, because they differ only in how many cards come back: a single
   card fills itself in, and the Assistant's Pipeline step gets the whole set of systems the ask
   needs plus the instruction to judge them by. */
function SourceComposer({ typeHint, one, hint, placeholder, onSources }) {
  const [open, setOpen] = useState(!one);
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [answers, setAnswers] = useState({});

  const go = async (withAnswers) => {
    setBusy(true); setOut(null);
    try {
      const { data } = await api.post("/api/reports/compose-sources",
        { ask, type: typeHint || undefined, answers: withAnswers || undefined });
      if (data.sources?.length) {
        onSources(data.sources, data.ai_prompt || "");
        setAsk(""); setAnswers({});
        setOut({ done: (data.explain || (one ? "Filled it in." : "Added them."))
          + (data.confidence === "low" ? " It is not confident about this one — check it before you save." : "") });
      } else setOut(data);
    } catch (e) { setOut({ error: e?.response?.data?.detail || "the composer could not be reached" }); }
    setBusy(false);
  };
  const answered = out?.questions?.length && out.questions.every((qq) => String(answers[qq] || "").trim());

  if (!open) {
    return (
      <Button size="small" onClick={() => setOpen(true)} startIcon={<AutoAwesomeIcon sx={{ fontSize: 14 }} />}
        sx={{ fontSize: 11.5, alignSelf: "flex-start" }}>let AI fill this in</Button>
    );
  }
  return (
    <Box sx={one ? { bgcolor: "#fffdf7", border: "1px solid #d8cfbe", borderRadius: 1, p: 1 }
      : { ...card, p: 1.5, mb: 1.25, bgcolor: "#fffdf7", borderColor: "#d8cfbe" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mb: 0.7 }}>
        <AutoAwesomeIcon sx={{ fontSize: 14, color: ACCENT2 }} />
        <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: INK, flex: 1 }}>{hint}</Typography>
        {one && <CloseIcon onClick={() => { setOpen(false); setOut(null); }} titleAccess="Fill it in by hand instead"
          sx={{ fontSize: 14, color: FAINT, cursor: "pointer" }} />}
      </Box>
      <TextField fullWidth size="small" multiline minRows={2} value={ask} disabled={busy} sx={{ bgcolor: "#fff" }}
        inputProps={{ style: { fontSize: 12 } }} placeholder={placeholder}
        onChange={(e) => setAsk(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && ask.trim()) go(); }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.7, flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation disabled={busy || !ask.trim()} onClick={() => go()}
          startIcon={busy ? <CircularProgress size={12} /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />}>
          {busy ? "Reading the schema…" : one ? "Write this card" : "Point it at them"}
        </Button>
        <Typography sx={{ fontSize: 10.5, color: FAINT }}>
          It reads the real schema first, and asks rather than guessing a field name.
        </Typography>
      </Box>
      {out?.error && <Alert severity="warning" sx={{ mt: 1, fontSize: 12 }}>{out.error}</Alert>}
      {out?.done && <Typography sx={{ mt: 0.9, fontSize: 11.5, color: "#47654a", fontWeight: 600 }}>✓ {out.done}</Typography>}

      {/* it did not know something. Better here than as a silently wrong filter. */}
      {out?.questions?.length > 0 && (
        <Box sx={{ mt: 1, display: "flex", flexDirection: "column", gap: 0.9 }}>
          <Typography sx={{ fontSize: 11, color: DIM, fontWeight: 600 }}>A couple of things it will not guess at:</Typography>
          {out.questions.map((qq) => (
            <TextField key={qq} size="small" fullWidth label={qq} sx={{ bgcolor: "#fff" }}
              value={answers[qq] || ""} onChange={(e) => setAnswers({ ...answers, [qq]: e.target.value })} />
          ))}
          <Button size="small" variant="contained" disableElevation disabled={busy || !answered}
            onClick={() => go(answers)} sx={{ alignSelf: "flex-start" }}>Answer &amp; write it</Button>
        </Box>
      )}
    </Box>
  );
}

/* What does APBILL actually carry? Asked of Intacct itself - lookup, custom fields and all -
   because the alternative is a list in our heads that is wrong the day somebody adds a field.
   Click one and it lands in the card's "fields" box. */
function IntacctFields({ object, connectorId, onPick }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const obj = String(object || "").trim();
  const load = async () => {
    setOpen(true); setRows(null); setErr(""); setQ("");
    try {
      const { data } = await api.get("/api/intacct/fields", { params: { obj, connector_id: connectorId } });
      if (data.ok) setRows(data.data || []); else setErr(data.error);
    } catch (e) { setErr(e?.response?.data?.detail || "the lookup failed"); }
  };
  const shown = (rows || []).filter((f) => !q || (f.ID + " " + f.LABEL).toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <Button size="small" onClick={load} disabled={!obj} sx={{ fontSize: 11.5, alignSelf: "flex-start" }}>
        {obj ? "What fields does " + obj + " have?" : "Name an object to see its fields"}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          {obj}{rows ? " — " + rows.length + " fields in this company" : ""}
        </DialogTitle>
        <DialogContent>
          {err && <Alert severity="error" sx={{ fontSize: 12.5 }}>{err}</Alert>}
          {!rows && !err && <CircularProgress size={20} sx={{ m: 2 }} />}
          {rows && (
            <>
              <TextField size="small" fullWidth autoFocus placeholder="filter…" value={q}
                onChange={(e) => setQ(e.target.value)} sx={{ bgcolor: "#fff", mb: 1 }} />
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.75 }}>
                straight from Sage, custom fields included{onPick ? " — click one to add it to this card" : ""}
              </Typography>
              <Box sx={{ maxHeight: 420, overflow: "auto" }}>
                {shown.map((f) => (
                  <Box key={f.ID} onClick={() => onPick?.(f.ID)}
                    sx={{ display: "flex", gap: 1, alignItems: "baseline", py: 0.4, borderBottom: "1px solid " + BORDER,
                      cursor: onPick ? "pointer" : "default", "&:hover": onPick ? { bgcolor: "#faf8f4" } : {} }}>
                    <Typography sx={{ ...mono, fontSize: 11.5, color: INK, fontWeight: 700, minWidth: 170 }}>{f.ID}</Typography>
                    <Typography sx={{ fontSize: 11.5, color: DIM, flex: 1 }} noWrap>{f.LABEL}</Typography>
                    <Typography variant="caption" sx={{ ...mono, color: FAINT }}>{f.DATATYPE}</Typography>
                  </Box>
                ))}
                {!shown.length && <Typography sx={{ fontSize: 12, color: FAINT, py: 1 }}>nothing matches that.</Typography>}
              </Box>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
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
    const c = toShape({ ...src, title: "test" });
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
/* Five fields where four never apply: a csv has no sheet, a log has no JSON path, and a plain
   path matches one file so there is nothing to pick between. The suffix already says which. */
const FILE_FIELD_FOR = { tail: ['', '.log', '.txt', '.md', '.out', '.err'], sheet: ['.xlsx'],
  path_expr: ['.json'] };

/* `removable` is the Assistant's case: every one of its own sources can go, including the last,
   because zero of them is a valid Assistant - a report with zero sources is not a report. */
function SourceCard({ src, index, count, typeOptions, connectors, dragging, onDragStart, onDragEnd,
                      onDropHere, onChange, onRetype, onCopy, onRemove, onFill, removable = count > 1 }) {
  const fields = (FIELDS[src.type] || []).filter(([, key]) => {
    if (key === "ai_prompt") return false;
    if (src.type !== "local_file") return true;
    const path = String(src.path || "");
    if (key === "pick") return /[*?[]/.test(path);
    const only = FILE_FIELD_FOR[key];
    if (!only) return true;
    const dot = path.lastIndexOf(".");
    const suffix = dot > path.lastIndexOf("/") && dot > path.lastIndexOf("\\") ? path.slice(dot).toLowerCase() : "";
    return only.includes(suffix);
  });
  const cardType = CARD_OF[src.type] || src.type;
  const matching = connectors.filter((c) => c.Type === cardType);
  const conn = matching.find((c) => c.ConnectorId === Number(src.connector_id))
    || matching.find((c) => c.Active) || matching[0];
  const needsConn = ["mssql", "winrm", "database", "aws", "azure", "prometheus", "datadog",
    "exa", "tavily", "firecrawl"].includes(cardType);   // reader works with no key at all
  const connOk = conn?.LastSyncAt && !conn?.LastError;
  return (
    <Box draggable={!!onDragStart} onDragStart={onDragStart} onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()} onDrop={onDropHere}
      sx={{ ...card, width: 354, p: 1.25, display: "flex", flexDirection: "column", gap: 1,
        opacity: dragging ? 0.45 : 1, ...(onDragStart ? { cursor: "grab", "&:active": { cursor: "grabbing" } } : {}) }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        {onDragStart && <DragIndicatorIcon sx={{ fontSize: 16, color: "#cfc9bf" }} />}
        <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1 }}>source {index + 1} of {count}</Typography>
        <ContentCopyIcon onClick={onCopy} titleAccess="Duplicate — same connection, different query"
          sx={{ fontSize: 14, color: FAINT, cursor: "pointer", "&:hover": { color: "#55697a" } }} />
        {removable && <CloseIcon onClick={onRemove} titleAccess="Remove this source"
          sx={{ fontSize: 15, color: FAINT, cursor: "pointer", "&:hover": { color: "#6b2733" } }} />}
      </Box>
      <Select size="small" value={src.type || "mssql"} onChange={(e) => onRetype(e.target.value)}
        sx={{ fontSize: 12.5, bgcolor: "#fff" }}>
        {(() => {
          const have = new Set(typeOptions.map((t) => t.type));
          const grouped = TYPE_GROUPS.map(([g, ts]) => [g, ts.filter((t) => have.has(t))]).filter(([, ts]) => ts.length);
          const spoken = new Set(grouped.flatMap(([, ts]) => ts));
          const rest = [...have].filter((t) => !spoken.has(t));
          return [...grouped, ...(rest.length ? [["Other", rest]] : [])].flatMap(([g, ts]) => [
            <ListSubheader key={`h-${g}`} sx={{ fontSize: 10, lineHeight: 2.2, letterSpacing: 0.8,
              textTransform: "uppercase", color: FAINT, bgcolor: "#fff" }}>{g}</ListSubheader>,
            ...ts.map((t) => (
              <MenuItem key={t} value={t} sx={{ fontSize: 12.5, pl: 2.5 }}>{TYPE_LABELS[t] || t}</MenuItem>
            )),
          ]);
        })()}
      </Select>
      {needsConn && (
        <>
          {matching.length > 1 && (
            <Select size="small" value={conn?.ConnectorId || ""}
              onChange={(e) => onChange({ connector_id: Number(e.target.value) })}
              displayEmpty sx={{ fontSize: 12, bgcolor: "#fff" }}>
              {matching.map((c) => (
                <MenuItem key={c.ConnectorId} value={c.ConnectorId} sx={{ fontSize: 12 }}>{c.Name}</MenuItem>
              ))}
            </Select>
          )}
          <Typography variant="caption" sx={{ fontWeight: 600, color: connOk ? "#47654a" : "#55697a" }}>
            {connOk ? `✓ uses ${conn.Name} from Connections`
              : `⚠ set up ${conn?.Name || CARD_LABELS[cardType] || cardType} in Connections first`}
          </Typography>
        </>
      )}
      {onFill && src.type !== "assistant" && <SourceComposer one typeHint={src.type} hint="say what you want out of it"
        placeholder={PLACEHOLDER_FOR[src.type] || "the rows this card should return"}
        onSources={(list) => onFill(list[0])} />}
      {(count > 1 || removable) && (
        <TextField size="small" label="label" value={src.label || ""} sx={{ bgcolor: "#fff" }}
          placeholder="cash balances" onChange={(e) => onChange({ label: e.target.value })} />
      )}
      {/* "I just want log history" should not require knowing a boto3 operation name. The generic
          AWS call is the escape hatch for anything unusual; there is a purpose-built type for the
          two things people actually ask AWS for, and it takes a log group and a number of hours. */}
      {src.type === "aws" && ["logs", "s3"].includes(src.service) && (
        <Alert severity="info" sx={{ fontSize: 11.5, py: 0, "& .MuiAlert-message": { py: 0.75 } }}
          action={<Button size="small" sx={{ fontSize: 11 }}
            onClick={() => onRetype(src.service === "logs" ? "cloudwatch_logs" : "s3_object")}>switch</Button>}>
          {src.service === "logs" ? "For log history there is a simpler source: pick a log group and hours back."
            : "For reading or listing a bucket there is a simpler source: pick the bucket."}
        </Alert>
      )}
      {fields.map(([label, key, kind, ph]) => {
        const v = src[key];
        const shown = showValue(v, kind);
        if (kind === "pick_file") {
          return (
            <Select key={key} size="small" value={src.pick || "newest"} sx={{ fontSize: 12.5, bgcolor: "#fff" }}
              onChange={(e) => onChange({ pick: e.target.value })}>
              <MenuItem value="newest" sx={{ fontSize: 12 }}>the one that changed most recently</MenuItem>
              <MenuItem value="name" sx={{ fontSize: 12 }}>the highest name (sales-2026-08-25 beats -08-01)</MenuItem>
            </Select>
          );
        }
        if (PICKS[kind]) {
          return <AwsPicker key={key} label={label} which={kind} value={shown} placeholder={ph}
            service={src.service}
            onChange={(x) => onChange({ [key]: x.value, ...(x.region !== undefined ? { region: x.region } : {}) })} />;
        }
        return <TextField key={key} size="small" label={label} placeholder={ph} value={shown} sx={{ bgcolor: "#fff" }}
          multiline={kind === "multiline" || kind === "filter_lines"}
          minRows={kind === "multiline" ? 3 : kind === "filter_lines" ? 2 : undefined}
          inputProps={["multiline", "filter_lines", "csv_list"].includes(kind)
            ? { style: { fontFamily: "Consolas, monospace", fontSize: 11.5 } } : undefined}
          onChange={(e) => onChange({ [key]: e.target.value })} />;
      })}
      {["intacct", "intacct_fields"].includes(src.type) && (
        <IntacctFields object={src.object} connectorId={src.connector_id}
          onPick={src.type === "intacct" ? (id) => onChange({ fields: addField(src.fields, id) }) : undefined} />
      )}
      {/* blank is not "no cap" - it is the 200-row default, and the field has to say so or
          the timeline's "capped at 200" points at a setting you never made */}
      {/* blank is not "no cap" - it is the 200-row default, and the field has to say so or
          the timeline's "capped at 200" points at a setting you never made. It applies whenever
          the call comes back as a LIST (list_buckets, describe_instances, a SQL result) and does
          nothing at all when it comes back as one object - which the Test below makes obvious. */}
      {/* width:300 on a 300-wide card with padding on both sides: it hung out over the edge.
          Full width of whatever the card gives it, and a one-line hint instead of three. */}
      <TextField size="small" label="max rows" type="number" placeholder="200" value={src.max_rows ?? ""}
        helperText="blank = 200, and only for list results"
        FormHelperTextProps={{ sx: { fontSize: 10.5, mx: 0 } }}
        sx={{ bgcolor: "#fff", width: "100%" }} onChange={(e) => onChange({ max_rows: e.target.value })} />
      <SourceTest src={src} />
    </Box>
  );
}

/* What the report's last run DID, under its row. A quiet assistant check posts nothing, so this is
   the only place its work shows: what it read (the exact text the model saw), what it reviewed and let
   go, its note to the next check, and what came out - or the error, when it failed. */
const IDEA_KINDS = { followup: "follow up", promise: "promise", prep: "prep", cold: "gone quiet", idea: "idea" };
function LastRun({ r, sid, embedded }) {
  // embedded: one run inside the History dialog - starts open, no "last run" header of its own
  const [open, setOpen] = useState(!!embedded);
  const [showInputs, setShowInputs] = useState(false);
  const [hist, setHist] = useState(false);
  const rv = r.reviewed || null;
  const outcome = r.failed ? `failed${r.error ? ` — ${r.error}` : ""}`
    : r.type === "assistant" ? (r.said ? `posted ${r.said} line${r.said === 1 ? "" : "s"}` : "nothing to say — no post")
    : r.subject ? `filed: ${r.subject}` : "ran";
  const read = rv ? [`${rv.recent ?? rv.today ?? 0} sender/subject lines from the last two days`, `${rv.week ?? 0} tasks closed this week`,
    `${rv.open ?? 0} open`, `${rv.said ?? 0} already said`, Object.entries(rv.candidates || {}).map(([k, v]) => `${v} ${IDEA_KINDS[k] || k}`).join(", ") || "no candidates"] : [];
  return (
    <Box sx={{ pl: embedded ? 0 : 5.5, pr: embedded ? 0 : 1, pb: embedded ? 0 : 1.25, mt: embedded ? 0 : -0.5 }}>
      {!embedded && (
      <Typography variant="caption" sx={{ color: r.failed ? "#8a3646" : FAINT, display: "block", lineHeight: 1.5 }}>
        <Box component="span" sx={{ fontWeight: 700, color: r.failed ? "#8a3646" : DIM }}>last run</Box>
        {` · ${timeAgo(r.at)}${r.ms != null ? ` · ${(r.ms / 1000).toFixed(1)}s` : ""} · ${outcome}`}
        {rv && ` · read ${read[0]}, ${read[1]}`}
        <Box component="span" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
          sx={{ ml: 1, color: "#55697a", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>
          {open ? "hide ↑" : "details ↓"}
        </Box>
        {/* every run, not only the last: what each one read and why it said what it said (the owner, 2026-08-30) */}
        {sid != null && (
          <Box component="span" onClick={(e) => { e.stopPropagation(); setHist(true); }}
            sx={{ ml: 1, color: "#55697a", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>history ↗</Box>
        )}
      </Typography>
      )}
      {hist && <RunHistory sid={sid} title={r.title} onClose={() => setHist(false)} />}
      {open && !!r.lines?.length && (
        <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.5 }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: ASSISTANT.ink }}>what it said, and why</Typography>
          {r.lines.map((l) => (
            <Box key={l.id ?? l.key} sx={{ mt: 0.35, px: 1, py: 0.5, borderRadius: 1, border: `1px solid ${ASSISTANT.bd}`, bgcolor: ASSISTANT.tint }}>
              <Typography variant="caption" sx={{ display: "block", color: INK, lineHeight: 1.45 }}>
                <Box component="span" sx={{ fontWeight: 700, color: ASSISTANT.ink }}>{IDEA_KINDS[l.kind] || l.kind} · </Box>{l.text}
              </Typography>
              {l.why && <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.4, whiteSpace: "pre-wrap" }}>
                <Box component="span" sx={{ fontWeight: 700, color: ASSISTANT.ink }}>why · </Box>{l.why}</Typography>}
            </Box>
          ))}
        </Box>
      )}
      {open && (
        <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.5, p: 1.25, borderRadius: 1.5, border: `1px dashed ${BORDER}`, bgcolor: "#faf8f4" }}>
          {rv && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.5 }}>
              <Box component="span" sx={{ fontWeight: 700, color: "#6b5f45" }}>what it reviewed · </Box>{read.join(" · ")}
              {rv.model === false ? " · no model — the facts in the hub's own words" : ""}
            </Typography>
          )}
          {rv?.notes && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.5, mt: 0.4 }}>
              <Box component="span" sx={{ fontWeight: 700, color: "#6b5f45" }}>note to its next check · </Box>{rv.notes}
            </Typography>
          )}
          {!!rv?.skipped?.length && (
            <Box sx={{ mt: 0.4 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, color: "#6b5f45" }}>looked at and let go · {rv.skipped.length}</Typography>
              {rv.skipped.map((c) => (
                <Typography key={c.key} variant="caption" sx={{ display: "block", color: FAINT, pl: 1, borderLeft: `2px solid ${BORDER}`, mt: 0.3, whiteSpace: "pre-wrap" }}>
                  <Box component="span" sx={{ fontWeight: 700 }}>{IDEA_KINDS[c.kind] || c.kind} · </Box>{c.facts}
                </Typography>
              ))}
            </Box>
          )}
          {r.summary && r.type !== "assistant" && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", whiteSpace: "pre-wrap", mt: 0.4, maxHeight: 220, overflowY: "auto" }}>
              <Box component="span" sx={{ fontWeight: 700, color: "#6b5f45" }}>what it filed · </Box>{r.summary}
            </Typography>
          )}
          {r.inputs && (
            <Box sx={{ mt: 0.6 }}>
              <Typography variant="caption" onClick={() => setShowInputs((v) => !v)}
                sx={{ color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                {showInputs ? "hide" : "show"} exactly what it read — {r.inputs.length.toLocaleString()} chars {showInputs ? "↑" : "↓"}
              </Typography>
              {showInputs && (
                <Box component="pre" sx={{ ...mono, fontSize: 11, lineHeight: 1.45, color: INK, whiteSpace: "pre-wrap", m: 0, mt: 0.5, p: 1,
                  bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 1, maxHeight: 360, overflowY: "auto" }}>{r.inputs}</Box>
              )}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

/* The History dialog: every run of one report (store.report_run, newest first) down the left - when,
   how long, what came out - and the chosen run whole on the right: what it read, what it reviewed and
   let go, what it said and WHY. The assistant's quiet checks post nothing, so this is where "why did it
   bring that up / why did it stay quiet at 14:30" gets answered (the owner, 2026-08-30). */
function RunHistory({ sid, title, onClose }) {
  const [runs, setRuns] = useState(null);
  const [pick, setPick] = useState(null);      // the run id chosen
  const [full, setFull] = useState({});        // run id -> the whole record, inputs and all
  useEffect(() => {
    api.get(`/api/reports/${sid}/runs`).then(({ data }) => { const rs = data.data || []; setRuns(rs); if (rs.length) setPick(rs[0].runId); })
      .catch(() => setRuns([]));
  }, [sid]);
  useEffect(() => {
    if (pick == null || full[pick]) return;
    api.get(`/api/reports/runs/${pick}`).then(({ data }) => setFull((f) => ({ ...f, [pick]: data }))).catch(() => {});
  }, [pick, full]);
  const outcome = (r) => r.failed ? "failed" : r.type === "assistant" ? (r.said ? `posted ${r.said} line${r.said === 1 ? "" : "s"}` : "quiet") : (r.subject ? "filed" : "ran");
  const cur = pick != null ? (full[pick] || runs?.find((r) => r.runId === pick)) : null;
  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth onClick={(e) => e.stopPropagation()}>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, fontSize: 15 }}>
        {title || "Report"} — run history
        <Typography variant="caption" sx={{ color: FAINT }}>{runs ? `${runs.length} run${runs.length === 1 ? "" : "s"} kept` : "loading…"}</Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={onClose} startIcon={<CloseIcon sx={{ fontSize: 14 }} />}>Close</Button>
      </DialogTitle>
      <DialogContent sx={{ display: "flex", gap: 1.5, minHeight: 420 }}>
        <Box sx={{ width: 260, flexShrink: 0, borderRight: `1px solid ${BORDER}`, pr: 1, overflowY: "auto", maxHeight: "70vh" }}>
          {runs && !runs.length && <Empty>No runs kept yet — the history starts with the next run.</Empty>}
          {(runs || []).map((r) => (
            <Box key={r.runId} onClick={() => setPick(r.runId)}
              sx={{ px: 1, py: 0.6, mb: 0.4, borderRadius: 1, cursor: "pointer", bgcolor: pick === r.runId ? "#eef3ea" : "transparent",
                border: `1px solid ${pick === r.runId ? "#cfd8c8" : "transparent"}`, "&:hover": { bgcolor: "#f4f3ef" } }}>
              <Typography variant="caption" sx={{ display: "block", color: INK, fontWeight: 600, lineHeight: 1.4 }}>{(r.at || "").slice(0, 16)}</Typography>
              <Typography variant="caption" sx={{ display: "block", color: r.failed ? "#8a3646" : DIM, lineHeight: 1.4 }}>
                {outcome(r)}{r.ms != null ? ` · ${(r.ms / 1000).toFixed(1)}s` : ""}{r.inputChars ? ` · read ${r.inputChars.toLocaleString()} chars` : ""}
              </Typography>
            </Box>
          ))}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, overflowY: "auto", maxHeight: "70vh" }}>
          {cur ? (
            <>
              <Typography variant="body2" sx={{ color: INK, fontWeight: 600, mb: 0.5 }}>
                {cur.at} · {outcome(cur)}{cur.error ? ` — ${cur.error}` : ""}{cur.subject && cur.type !== "assistant" ? ` · ${cur.subject}` : ""}
              </Typography>
              {full[pick] ? <LastRun r={{ ...cur, inputs: cur.inputs || "" }} embedded /> : <CircularProgress size={16} />}
            </>
          ) : <Typography variant="caption" sx={{ color: FAINT }}>Pick a run on the left.</Typography>}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
