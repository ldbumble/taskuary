// Settings, Stripe-style: a landing page of grouped category cards (icon + indigo title +
// description) that drill into detail pages - breadcrumb on top, big title, underline tabs,
// then generous divider-separated rows. Search on the landing reaches EVERYTHING (knobs,
// rules, memory, help text) and jumps straight to the right page + tab.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, InputAdornment, MenuItem, Select, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import VerifiedIcon from "@mui/icons-material/Verified";
import TuneIcon from "@mui/icons-material/Tune";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import PsychologyIcon from "@mui/icons-material/Psychology";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { AgentsPage } from "./AgentsPanel.jsx";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, mono, ACTION_COLORS } from "./theme.jsx";
import { Empty, Crumb as CrumbBase, UnderTabs, LandingCard } from "./ui.jsx";

const Crumb = (props) => <CrumbBase section="Settings" {...props} />;

const KINDS = ["keyword", "sender", "sender_domain", "noreply", "first_time_sender"];
// skip = never shows on the timeline at all (flood senders); ignore = shows, no task
const ACTIONS = ["skip", "ignore", "escalate", "auto_answer", "draft", "task_only"];
const NEW_POLICY = { Name: "", Kind: "keyword", Pattern: "", Action: "draft", Reason: "", SortOrder: 100, Active: true };
const SCOPES = ["global", "sender", "sender_domain", "source"];

const KNOB_META = {
  // ── Triage & routing: what happens to a message the moment it arrives ──
  intent_classify_enabled: { group: "Triage & routing", label: "Intent triage", type: "switch",
    desc: "Classify every new message: a task to DO, a question to ANSWER, or FYI to file.",
    help: "The heart of the funnel. Every inbound message is read (by the triage brain below, guided by SOUL.md) and classified: task = something must be done, so an agent can be dispatched; reply_only = answering IS the work, so a reply is drafted for your approval; fyi = informational, filed with no task and no draft.\n\nOff: every message becomes a task, which turns newsletters into work items. Leave this on unless you are debugging triage itself." },
  triage_ai: { group: "Triage & routing", label: "Triage brain", type: "brain",
    desc: "Which AI reads and classifies inbound messages.",
    help: "TWO BRAINS: a small, fast cloud model (Anthropic / OpenAI / Azure OpenAI) classifies each message in under a second for a fraction of a cent, while your CLI agent — the expensive, capable one — is saved for actually working tasks.\n\nONE BRAIN, TWO GEARS also works well: pick a CLI agent here and set its 'light model' (Connectors → AI CLI agents → Edit) — triage, drafts, summaries and the digest then run on the cheap fast tier (haiku, gemini-flash…) while coding sessions keep the agent's main model. No second API key, one bill.\n\nauto = the first active AI connector holding a key. Obvious automated noise is filtered by cheap heuristics before any AI is called either way." },
  default_action: { group: "Triage & routing", label: "When no rule matches", type: "select", options: ["draft", "task_only", "escalate"],
    desc: "The fallback when no routing policy claims a message.",
    help: "draft = reply-only questions get an AI draft waiting in Review; task_only = file a task, draft nothing; escalate = always put it in front of you undecided.\n\nThis is only the FALLBACK: your routing policies (Settings → Routing policies) always win, and messages triaged as real tasks go to the coder regardless." },
  attach_threshold: { group: "Triage & routing", label: "Attach threshold", type: "number",
    desc: "How similar a message must be (0–1) to join an existing task instead of opening a new one.",
    help: "Lower = more messages glued onto existing tasks (risk: unrelated asks pile onto one task). Higher = more new tasks (risk: one conversation splinters). 0.42 is a sane default.\n\nTrue thread continuations — same email conversation, RE: replies — attach regardless of this number, so this only decides the borderline cases." },
  learn_enabled: { group: "Triage & routing", label: "Learn from your verdicts", type: "switch",
    desc: "Your corrections teach LEARNED.md — style, responsibilities, what deserves a task.",
    help: "Every correction you make — editing a draft before sending, rejecting one, reclassifying a task as a question, promoting something triage filed, 'Not a task' / 'Not our task' — is distilled into LEARNED.md (Docs tab): first as a hypothesis with a strength counter and the evidence behind it, promoted into the active profile only once it keeps holding across separate episodes. The active sections ride into every triage call, draft and agent run; SOUL.md always outranks them.\n\nRules that would HIDE mail (treat as fyi, never a task) never activate themselves — they wait in the doc's 'Proposed rules' for you to adopt or delete. Off: nothing new is learned; the doc stays as it is and is still injected." },

  // ── Replies: the drafts you approve ──
  auto_draft_enabled: { group: "Replies", label: "Draft replies automatically", type: "switch",
    desc: "Questions get their AI draft the moment they arrive, waiting in Review.",
    help: "On: a message triaged as a question lands in Review with the reply already written — you edit or just Approve & send. Off: questions still queue in Review, but empty; you click 'Draft with AI' per item.\n\nNothing sends itself either way — approving is always yours. Turning this off is also the cheapest way to pause AI spending." },
  outlook_drafts_enabled: { group: "Replies", label: "Outlook drafts on approve", type: "switch",
    desc: "Approved Outlook replies are also saved as reply-all DRAFTS in the mailbox.",
    help: "For the belt-and-braces workflow: on approval, the reply is additionally created as a reply-all draft inside the source mailbox via Graph (needs the Mail.ReadWrite consent), so you can give it one last look in Outlook and hit Send there. Failures land in the audit log, never block the approval." },
  send_enabled: { group: "Replies", label: "(legacy, unused)", type: "switch",
    desc: "Kept only for old databases — has no effect. Leave off.",
    help: "An earlier design had a separate send gate. Sending is now simply what Approve & send does, so this switch controls nothing." },

  // ── Coder agent: who works the tasks, and how eagerly ──
  default_agent: { group: "Coder agent", label: "Default agent", type: "agent",
    desc: "The CLI agent that works tasks when nothing names one.",
    help: "Start session, Send to coding agent and auto-dispatch all use this agent unless you pick another in the moment; every agent picker lists it first. The roster itself lives under Connectors → AI CLI agents, where the default row wears the star.\n\nGitHub-specific permissions (may agents open issues? push?) are on the GitHub connector card, because they are decisions about how your team uses GitHub, not about Taskuary." },
  answer_to_agent: { group: "Coder agent", label: "Hand answers to the working agent", type: "select",
    options: ["ask", "auto", "off"],
    desc: "When someone answers a question on a task an agent is sitting on, their answer can go straight into the live session.",
    help: "The classic round trip: the agent asks something mid-task, the hub asks the person, the person replies by mail or chat — and the reply attaches to the same task.\n\nask (default) = the review panel offers one click: 'Type this into the agent's session'. auto = the answer is typed into the live session the moment it arrives, as if you relayed it. off = it just lands on the task; you paste it yourself.\n\nOnly a LIVE session is ever typed into — if the agent already exited, nothing happens and the thread simply waits on the task." },
  ci_watch: { group: "Coder agent", label: "Watch CI on the task's pull request", type: "select",
    options: ["off", "feedback", "watch"],
    desc: "A red build goes back to the agent that wrote the code, with the failing check named.",
    help: "Once a task has a draft pull request (open it from the task, or let the agent propose one), every sync refreshes its checks.\n\nfeedback = a failing build is typed into the live session — 'these checks failed, fix the cause and push again, do not merge' — and recorded on the task; if no session is live the task returns to 'open' so it lands on you. watch = the state is shown on the proof card but nothing is handed back. off (default) = no polling at all.\n\nEach distinct failure reaches the agent ONCE per commit, never on every poll. Taskuary opens drafts and never merges." },
  proposals_enabled: { group: "Coder agent", label: "Agents may propose actions", type: "switch",
    desc: "An agent can ASK to open a PR, comment publicly, close an issue or run a tool — each waits for your approval.",
    help: "High-impact actions come off the auto-approve road entirely. Instead of doing them, the agent writes a typed proposal in its transcript (TASKUARY-PROPOSE {\"action\": \"open_pr\", …}); when the session wraps up, each valid one becomes a pending review saying what it wants and why. Approving RUNS it; rejecting does nothing.\n\nEvery proposal is re-validated at execution, so approving never grants a permission you have switched off — an open_pr proposal still needs 'Agents may push / deploy', a public comment still needs the GitHub card's reply switch. Malformed or unpermitted proposals are refused and recorded on the task rather than dropped silently." },
  coder_auto_enabled: { group: "Coder agent", label: "Auto-dispatch new tasks", type: "switch",
    desc: "Every new real task immediately opens a live agent session in its repo.",
    help: "On: the moment triage says 'this is work', your CLI opens in the task's repository (picked from the SOUL.md repo map) with the full ask seeded — visible on the Board, watchable, interruptible. Off: tasks queue as 'needs you' and you press Start session yourself.\n\nRequires the CLI installed and signed in on this machine. Nothing ships or sends without your approval either way." },

  // ── Notifications: the timeline pushed to you ──
  notify_level: { group: "Notifications", label: "Push to your chat", type: "select", options: ["needs_me", "all", "off"],
    desc: "Ping a Telegram / WhatsApp / Teams chat instead of you watching the tab.",
    help: "Give a chat connector the NOTIFY role (its Role step) and name the chat in its config; this decides what gets pushed there.\n\nneeds_me (default) = only what is genuinely waiting on YOU: a question to answer, a task nobody was dispatched at, and — the one that matters — 'the work is done, the reply is drafted and waiting in Review'. all = every new timeline item. off = never push.\n\nEvents that happened in the notify chat itself are never echoed back into it, so one channel can safely be both input and output." },

  phone_approvals: { group: "Notifications", label: "Approve from your phone", type: "switch",
    desc: "Reply to a ping in the notify chat to decide the review — approve, reject, or type the reply yourself.",
    help: "On: every ping about a pending reply carries the DRAFT and an [rvN] tag. Reply in that same chat: 'approve' sends the draft, 'reject' / 'no reply' land those verdicts, and ANY OTHER TEXT is sent instead of the draft — exactly like editing in Review. A confirmation comes back into the chat, including when a send fails (the review returns to the queue wearing the error).\n\nNeeds a Telegram or WhatsApp connector with the NOTIFY role and its notify chat set — and the connector polled (trigger or feed role on). Verdicts typed in the notify chat are intercepted before triage: they never become work, and the chat needs no source row flipped on.\n\nOff (default): pings stay read-only." },

  // ── Attachments & images ──
  vision_enabled: { group: "Attachments & images", label: "AI reads attached images", type: "switch",
    desc: "Screenshots go to the triage AI — \"see below\" mail is read, not guessed at.",
    help: "Half of \"see below\" mail says nothing in its body: the screenshot IS the request. On: attached images (PNG/JPEG/GIF/WebP, up to 4 per message, 5MB each) ride along into triage when the model has vision, and coding sessions get the local file paths to open themselves.\n\nOff: only text is ever sent to the AI — the setting to use if your model lacks vision or images must never leave the machine. The panel still displays attachments either way." },
  report_images_enabled: { group: "Attachments & images", label: "Charts on reports", type: "switch",
    desc: "Reports hand back a bar chart alongside the spreadsheet.",
    help: "A report's rows always come back as an .xlsx; with this on they also become an .svg bar chart drawn in the panel — and the summarizing model, which just read every row, picks which column to plot (better than a heuristic grabbing the id column). Off: spreadsheet only." },

  // ── Sync & startup ──
  startup_sync_days: { group: "Sync & startup", label: "Catch-up window (days)", type: "number",
    desc: "How far back the app reaches when it opens, for what arrived while it was closed.",
    help: "Taskuary is a window you open, not a service — at 5:30am it is closed, so 'anything since I last polled' misses the weekend. On startup every trigger connection is asked for this many days; the window only ever WIDENS (a source last polled a month ago is not pulled forward), and duplicates are never re-ingested.\n\nThe Timeline shows the catch-up running and refreshes when it lands. The daily DIGEST.md synthesis runs right after it. 0 = plain incremental poll on startup." },

  // ── Display ──
  timezone: { group: "Display", label: "Timezone", type: "timezone",
    desc: "The zone the app's clock speaks. Blank = this machine's local time.",
    help: "Timestamps are stored in the server machine's local time. Name that zone here and every displayed time wears its label (2:44 PM EDT) — and a browser opened from another timezone still reads the stamps correctly instead of silently reinterpreting them in its own zone.\n\nUse an IANA name (America/New_York, Europe/London, Asia/Jerusalem). Takes effect on the next page load." },
  feed_days: { group: "Display", label: "Timeline lookback (days)", type: "number",
    desc: "How many days the Timeline shows. Display only — nothing is deleted.",
    help: "Purely the Timeline's window. Older messages stay in the database, in task histories, and in search." },
};
const GROUPS = ["Triage & routing", "Replies", "Coder agent", "Notifications", "Attachments & images", "Sync & startup", "Display", "Other"];
// internal state and settings that moved onto their connector - never shown as knobs
const HIDDEN = new Set(["ingest_status", "agent_issues_enabled", "agent_push_enabled",
                        "owner_name", "owner_email",     // the owner lives on the Docs page
                        "last_pinged_review"]);          // phone-approvals bookkeeping, not a knob
const meta = (name) => KNOB_META[name] || { group: "Other", label: name, type: "auto" };

const SECTION_HELP = {
  policies: { title: "Routing policies — the deterministic layer",
    body: "Rules evaluated BEFORE any AI touches a message; no model confidence can override them. Precedence: ignore > escalate > auto_answer > draft > task_only — within one action, lowest order number wins.\n\nKINDS: keyword (pipe-separated substrings matched against subject+body), sender (exact addresses), sender_domain (domains), noreply (built-in matcher for automated addresses), first_time_sender (fires when the address has never been seen).\n\nACTIONS: ignore (no task, message stays visible in the feed), escalate (a human always decides), auto_answer (the draft is auto-approved — still never sent), draft (targeted default), task_only (file it, no reply).\n\nWhen you hit 'Not a task', a sender ignore rule is added here automatically — the learning loop writes into this table." },
  memory: { title: "Agent memory — the specific layer",
    body: "Standing notes tied to a sender, domain, or everyone: written when you say 'Not a task' or 'Not our task' (editable before saving), plus anything you add manually. Active notes are injected into triage and every draft, and they outrank the AI's own reading.\n\nThis is the SPECIFIC memory — verdicts about senders and kinds of mail. The GENERAL lessons (your style, your responsibilities, what deserves a task) are distilled from the same verdicts into LEARNED.md on the Docs tab, and the daily DIGEST.md is the working memory. Toggle off anything learned wrong — deactivated notes stay for the record but are never injected." },
  audit: { title: "Audit integrity",
    body: "Every action (routing, verdicts, agent runs, deletions, config changes) is appended to a hash-chained audit log: each row's hash covers the previous row's hash, so editing history breaks every hash after it. Verify recomputes the whole chain." },
};

const PAGES = {
  config: { title: "Configuration", icon: TuneIcon, desc: "Triage, drafting, coder and display knobs — how the funnel behaves." },
  policies: { title: "Routing policies", icon: AltRouteIcon, desc: "Deterministic rules the AI can never override — ignores, escalations, auto-answers." },
  memory: { title: "Agent memory", icon: PsychologyIcon, desc: "Standing notes learned from your verdicts, injected into every draft." },
  agents: { title: "Agents", icon: SmartToyIcon, desc: "Bring your own AI CLI — cmd, args, resumable sessions, repo → checkout map." },
  audit: { title: "Audit integrity", icon: VerifiedIcon, desc: "Tamper-evident hash chain over every action the hub takes." },
};

export default function SettingsView() {
  const [policies, setPolicies] = useState(null);
  const [settings, setSettings] = useState([]);
  const [memory, setMemory] = useState([]);
  const [newNote, setNewNote] = useState(null);
  const [draft, setDraft] = useState(null);
  const [verify, setVerify] = useState(null);
  const [help, setHelp] = useState(null);
  const [page, setPage] = useState(null);          // null = landing
  const [cfgTab, setCfgTab] = useState("Triage & routing");
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

  const [brains, setBrains] = useState([{ value: "", label: "auto — first active AI connector", ready: true }]);
  const [agentNames, setAgentNames] = useState([]);

  const load = useCallback(async () => {
    try {
      const [p, s, m] = await Promise.all([api.get("/api/policies"), api.get("/api/settings"), api.get("/api/memory")]);
      setPolicies(p.data.data || []); setSettings(s.data.data || []); setMemory(m.data.data || []);
      api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {});
      api.get("/api/agents").then(({ data }) => setAgentNames((data.data || []).map((a) => a.Name))).catch(() => {});
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load settings"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const savePolicy = async (p) => { await api.post("/api/policies", p); setDraft(null); load(); };
  const togglePolicy = async (p) => { await api.post("/api/policies", { PolicyId: p.PolicyId, Active: !p.Active }); load(); };
  const saveSetting = async (name, value) => { await api.patch("/api/settings", { name, value }); load(); };
  const toggleMemory = async (m) => { await api.patch(`/api/memory/${m.MemoryId}`, { active: !m.Active }); load(); };
  const addNote = async () => { await api.post("/api/memory", newNote); setNewNote(null); load(); };
  const runVerify = async () => setVerify((await api.get("/api/audit/verify")).data);

  // Deep search: every hit knows which page (and tab) it lives on and jumps there.
  const hit = (...parts) => parts.join(" ").toLowerCase().includes(q.toLowerCase());
  const results = !q ? [] : [
    ...settings.filter((s) => { if (HIDDEN.has(s.Name)) return false; const m = meta(s.Name); return hit(s.Name, s.Description, m.label, m.desc, m.help, m.group); })
      .map((s) => ({ key: `k${s.Name}`, label: meta(s.Name).label, crumb: `Configuration → ${meta(s.Name).group}`,
        go: () => { setPage("config"); setCfgTab(meta(s.Name).group); setQ(""); } })),
    ...(policies || []).filter((p) => hit(p.Name, p.Kind, p.Pattern, p.Action, p.Reason))
      .map((p) => ({ key: `p${p.PolicyId}`, label: p.Name, crumb: "Routing policies", go: () => { setPage("policies"); setQ(""); } })),
    ...memory.filter((m) => hit(m.Note, m.Scope, m.ScopeKey, m.Source))
      .map((m) => ({ key: `m${m.MemoryId}`, label: m.Note.slice(0, 70), crumb: "Agent memory", go: () => { setPage("memory"); setQ(""); } })),
  ];

  const control = (s) => {
    const m = meta(s.Name);
    // the agent roster is user-config, so the default-agent knob is a real dropdown of it
    if (m.type === "agent") return (
      <Select size="small" value={agentNames.includes(s.Value) ? s.Value : (agentNames[0] || "")}
        onChange={(e) => saveSetting(s.Name, e.target.value)} sx={{ minWidth: 140, fontSize: 12.5, bgcolor: "#fff" }}>
        {agentNames.map((n) => <MenuItem key={n} value={n} sx={{ fontSize: 12.5 }}>{n}</MenuItem>)}
        {!agentNames.length && <MenuItem value="" disabled sx={{ fontSize: 12.5 }}>no agents yet — add one under Connectors</MenuItem>}
      </Select>
    );
    // the brains list is dynamic: AI connectors that actually hold a key + your CLI agents
    if (m.type === "brain") return (
      <Select size="small" displayEmpty value={brains.some((b) => b.value === s.Value) ? s.Value : ""}
        sx={{ minWidth: 250, fontSize: 12.5, bgcolor: "#fff" }}
        onChange={(e) => saveSetting(s.Name, e.target.value)}>
        {brains.map((b) => (
          <MenuItem key={b.value} value={b.value} disabled={!b.ready} sx={{ fontSize: 12.5 }}>
            {b.label}{b.ready ? "" : " — no key saved"}
          </MenuItem>
        ))}
      </Select>
    );
    if (m.type === "select") return (
      <Select size="small" value={s.Value} onChange={(e) => saveSetting(s.Name, e.target.value)} sx={{ minWidth: 140, fontSize: 12.5, bgcolor: "#fff" }}>
        {m.options.map((o) => <MenuItem key={o} value={o} sx={{ fontSize: 12.5 }}>{o.replace("_", " ")}</MenuItem>)}
      </Select>
    );
    // the browser knows every IANA zone - a dropdown, not a spelling test
    if (m.type === "timezone") {
      const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
      return (
        <Select size="small" displayEmpty value={zones.includes(s.Value) ? s.Value : ""}
          MenuProps={{ PaperProps: { sx: { maxHeight: 380 } } }}
          sx={{ minWidth: 240, fontSize: 12.5, bgcolor: "#fff" }}
          onChange={(e) => saveSetting(s.Name, e.target.value)}>
          <MenuItem value="" sx={{ fontSize: 12.5 }}>this machine's local time</MenuItem>
          {zones.map((z) => <MenuItem key={z} value={z} sx={{ fontSize: 12.5 }}>{z}</MenuItem>)}
        </Select>
      );
    }
    if (m.type === "number") return (
      <TextField type="number" defaultValue={s.Value} sx={{ width: 100, bgcolor: "#fff" }}
        inputProps={{ style: { fontSize: 12.5, padding: "6px 10px" } }}
        onBlur={(e) => e.target.value !== s.Value && saveSetting(s.Name, e.target.value)} />
    );
    if (m.type === "switch" || ["0", "1"].includes(String(s.Value))) return (
      <Switch checked={s.Value === "1"} onChange={() => saveSetting(s.Name, s.Value === "1" ? "0" : "1")} />
    );
    return (
      <TextField defaultValue={s.Value} sx={{ width: 150, bgcolor: "#fff" }} inputProps={{ style: { fontSize: 12.5, padding: "6px 10px" } }}
        onBlur={(e) => e.target.value !== s.Value && saveSetting(s.Name, e.target.value)} />
    );
  };

  if (!policies) return <CircularProgress size={22} sx={{ m: 4 }} />;

  /* ── detail pages ─────────────────────────────────────────────────────── */
  if (page === "config") {
    const rows = settings.filter((s) => !HIDDEN.has(s.Name) && meta(s.Name).group === cfgTab);
    const tabs = GROUPS.filter((g) => settings.some((s) => meta(s.Name).group === g));
    return (
      <Box sx={{ maxWidth: 980 }}>
        <Crumb onBack={() => setPage(null)} title="Configuration" />
        <UnderTabs tabs={tabs} value={cfgTab} onChange={setCfgTab} />
        {rows.map((s) => {
          const m = meta(s.Name);
          return (
            <Box key={s.Name} sx={{ display: "flex", alignItems: "center", gap: 3, py: 2.5, borderBottom: `1px solid ${BORDER}` }}>
              <Box sx={{ flex: 1, minWidth: 0, cursor: m.help ? "pointer" : "default" }}
                onClick={() => m.help && setHelp({ title: m.label, body: m.help })}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                  {m.label}
                  {m.help && <HelpOutlineIcon sx={{ fontSize: 15, color: "#c2c9d6" }} />}
                </Typography>
                <Typography variant="body2" sx={{ color: DIM, mt: 0.25 }}>{m.desc || s.Description}</Typography>
              </Box>
              <Box sx={{ flexShrink: 0 }}>{control(s)}</Box>
            </Box>
          );
        })}
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  if (page === "policies") {
    return (
      <Box sx={{ maxWidth: 980 }}>
        <Crumb onBack={() => setPage(null)} title="Routing policies" />
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Typography variant="body2" sx={{ color: DIM }}>
            Deterministic gates the AI can never override.
            <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.policies)}
              sx={{ color: "#4f46e5", cursor: "pointer", ml: 0.75, "&:hover": { textDecoration: "underline" } }}>
              How precedence works →
            </Typography>
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="contained" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => setDraft({ ...NEW_POLICY })}>Add rule</Button>
        </Box>
        {!(policies || []).length && <Empty>No rules yet.</Empty>}
        {(policies || []).map((p) => (
          <Box key={p.PolicyId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.75, borderBottom: `1px solid ${BORDER}`, opacity: p.Active ? 1 : 0.55 }}>
            <Chip size="small" label={p.Action.replace("_", " ")}
              sx={{ bgcolor: ACTION_COLORS[p.Action]?.bg, color: ACTION_COLORS[p.Action]?.fg, height: 21, fontSize: 10.5, width: 100, justifyContent: "center" }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }} noWrap>{p.Name}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT }} noWrap>{p.Kind}{p.Pattern ? `: ${p.Pattern}` : ""}</Typography>
            </Box>
            <Typography variant="caption" sx={{ ...mono, color: FAINT }}>#{p.SortOrder}</Typography>
            <Button size="small" onClick={() => setDraft({ ...p, Active: !!p.Active })}>Edit</Button>
            <Switch checked={!!p.Active} onChange={() => togglePolicy(p)} />
          </Box>
        ))}
        {draft && (
          <Box sx={{ ...card, bgcolor: PANEL2, p: 2, mt: 2, display: "flex", flexDirection: "column", gap: 1.25 }}>
            <Typography variant="body2" sx={{ color: "#4f46e5", fontWeight: 700 }}>{draft.PolicyId ? `Edit rule · ${draft.Name}` : "New rule"}</Typography>
            <TextField label="Name" value={draft.Name} onChange={(e) => setDraft({ ...draft, Name: e.target.value })} />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Select fullWidth value={draft.Kind} onChange={(e) => setDraft({ ...draft, Kind: e.target.value })}>
                {KINDS.map((k) => <MenuItem key={k} value={k}>{k}</MenuItem>)}
              </Select>
              <Select fullWidth value={draft.Action} onChange={(e) => setDraft({ ...draft, Action: e.target.value })}>
                {ACTIONS.map((a) => <MenuItem key={a} value={a}>{a.replace("_", " ")}</MenuItem>)}
              </Select>
              <TextField label="Order" type="number" sx={{ width: 100 }} value={draft.SortOrder}
                onChange={(e) => setDraft({ ...draft, SortOrder: Number(e.target.value) })} />
            </Box>
            {!["noreply", "first_time_sender"].includes(draft.Kind) && (
              <TextField label="Pattern (pipe-separated terms / addresses / domains)"
                value={draft.Pattern || ""} onChange={(e) => setDraft({ ...draft, Pattern: e.target.value })} />
            )}
            <TextField label="Reason (shown to the reviewer)" value={draft.Reason} onChange={(e) => setDraft({ ...draft, Reason: e.target.value })} />
            <Box sx={{ display: "flex", gap: 0.75 }}>
              <Button size="small" variant="contained" disabled={!draft.Name || !draft.Reason} onClick={() => savePolicy(draft)}>Save</Button>
              <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
            </Box>
          </Box>
        )}
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  if (page === "memory") {
    return (
      <Box sx={{ maxWidth: 980 }}>
        <Crumb onBack={() => setPage(null)} title="Agent memory" />
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Typography variant="body2" sx={{ color: DIM }}>
            Standing notes learned from your verdicts, injected into every draft.
            <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.memory)}
              sx={{ color: "#4f46e5", cursor: "pointer", ml: 0.75, "&:hover": { textDecoration: "underline" } }}>
              How memory works →
            </Typography>
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="contained" startIcon={<AddIcon sx={{ fontSize: 14 }} />}
            onClick={() => setNewNote({ note: "", scope: "global", scope_key: "" })}>Add note</Button>
        </Box>
        {!memory.length && <Empty>Nothing learned yet — every review verdict teaches it.</Empty>}
        {memory.map((m) => (
          <Box key={m.MemoryId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.75, borderBottom: `1px solid ${BORDER}`, opacity: m.Active ? 1 : 0.5 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: INK, fontSize: 13.5, lineHeight: 1.4 }}>{m.Note}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT }}>{m.Scope}{m.ScopeKey ? `: ${m.ScopeKey}` : ""} · {m.Source}</Typography>
            </Box>
            <Switch checked={!!m.Active} onChange={() => toggleMemory(m)} />
          </Box>
        ))}
        {newNote && (
          <Box sx={{ ...card, bgcolor: PANEL2, p: 2, mt: 2, display: "flex", flexDirection: "column", gap: 1.25 }}>
            <TextField label="Standing note (imperative, e.g. 'Never draft replies to daily cash reports')"
              multiline value={newNote.note} onChange={(e) => setNewNote({ ...newNote, note: e.target.value })} />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Select fullWidth value={newNote.scope} onChange={(e) => setNewNote({ ...newNote, scope: e.target.value })}>
                {SCOPES.map((s) => <MenuItem key={s} value={s}>{s.replace("_", " ")}</MenuItem>)}
              </Select>
              {newNote.scope !== "global" && (
                <TextField fullWidth label="address / domain / source" value={newNote.scope_key}
                  onChange={(e) => setNewNote({ ...newNote, scope_key: e.target.value })} />
              )}
            </Box>
            <Box sx={{ display: "flex", gap: 0.75 }}>
              <Button size="small" variant="contained" disabled={!newNote.note.trim()} onClick={addNote}>Save</Button>
              <Button size="small" onClick={() => setNewNote(null)}>Cancel</Button>
            </Box>
          </Box>
        )}
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  if (page === "agents") {
    return <AgentsPage onBack={() => setPage(null)} />;
  }

  if (page === "audit") {
    return (
      <Box sx={{ maxWidth: 980 }}>
        <Crumb onBack={() => setPage(null)} title="Audit integrity" />
        <Typography variant="body2" sx={{ color: DIM, mb: 2 }}>
          Every action lands in a hash-chained, tamper-evident log — verification recomputes the whole chain.
        </Typography>
        <Button variant="contained" startIcon={<VerifiedIcon sx={{ fontSize: 16 }} />} onClick={runVerify}>Verify chain</Button>
        {verify && (
          <Typography sx={{ mt: 2, fontWeight: 700, fontSize: 13.5, color: verify.ok ? "#15803d" : "#b91c1c" }}>
            {verify.ok ? `✓ Intact — ${verify.rows} rows verified` : `✗ BROKEN at ids ${verify.broken_ids.join(", ")}`}
          </Typography>
        )}
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  /* ── landing ──────────────────────────────────────────────────────────── */
  return (
    <Box sx={{ maxWidth: 1160 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <TextField fullWidth placeholder="Search settings, rules, memory — matches help text too…" value={q}
        onChange={(e) => setQ(e.target.value)} sx={{ mb: 3, bgcolor: "#fff", borderRadius: 2, maxWidth: 520 }}
        InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: FAINT }} /></InputAdornment> }} />

      {q ? (
        <Box>
          {!results.length && <Empty>Nothing matches.</Empty>}
          {results.map((r) => (
            <Box key={r.key} onClick={r.go} sx={{ py: 1.25, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
              "&:hover": { bgcolor: "#fafbfd" } }}>
              <Typography sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 13.5 }}>{r.label}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{r.crumb}</Typography>
            </Box>
          ))}
        </Box>
      ) : (
        <>
          <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>Agent behavior</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3, mb: 4 }}>
            {["config", "policies", "memory", "agents"].map((k) => <PageCard key={k} k={k} onOpen={() => setPage(k)} />)}
          </Box>
          <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>System</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3 }}>
            <PageCard k="audit" onOpen={() => setPage("audit")} />
          </Box>
        </>
      )}
    </Box>
  );
}

const PageCard = ({ k, onOpen }) => {
  const p = PAGES[k]; const Icon = p.icon;
  return <LandingCard icon={<Icon sx={{ fontSize: 19, color: "#4f46e5" }} />} title={p.title} desc={p.desc} onOpen={onOpen} />;
};

const HelpDialog = ({ help, onClose }) => (
  <Dialog open={!!help} onClose={onClose} fullWidth maxWidth="sm">
    {help && (
      <>
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <HelpOutlineIcon sx={{ fontSize: 18, color: ACCENT2 }} />{help.title}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, lineHeight: 1.6 }}>{help.body}</Typography>
        </DialogContent>
        <DialogActions><Button variant="contained" onClick={onClose}>Got it</Button></DialogActions>
      </>
    )}
  </Dialog>
);
