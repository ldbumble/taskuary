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
  intent_classify_enabled: { group: "Triage & routing", label: "Intent triage", type: "switch",
    desc: "Classify every new message: task / reply-only question / FYI (filed, no draft).",
    help: "The heart of the funnel: every new message is classified task (a requirement to DO something), reply_only (just needs an answer), or fyi (informational - filed with no task and no draft), guided by SOUL.md. Off = every message becomes a task, like v1 did." },
  triage_ai: { group: "Triage & routing", label: "Triage brain", type: "brain",
    desc: "Which AI classifies inbound messages — a cloud model, or your coding CLI itself.",
    help: "auto = the first active AI connector with a key wins. Pick a specific connector to pin it. Pick a CLI agent (claude, codex…) and the SAME brain that writes your code also triages your inbox — one model, one bill, no second API key. The trade-off is speed and cost per message: a CLI run takes seconds to a minute and spends agent tokens, while an API key answers in well under a second. Obvious automated noise is filtered by heuristics before any AI is called either way." },
  default_action: { group: "Triage & routing", label: "Default action", type: "select", options: ["draft", "task_only", "escalate"],
    desc: "What happens when no policy rule matches a message.",
    help: "draft = the AI drafts a reply for your review (reply-only questions); task_only = just file a task, no draft; escalate = always send it to you. Note: messages triaged as REAL tasks skip the responder regardless - they queue for the coder." },
  attach_threshold: { group: "Triage & routing", label: "Attach threshold", type: "number",
    desc: "Similarity floor (0–1) for joining an existing task instead of opening a new one.",
    help: "Lower = more messages glued onto old tasks; higher = more new tasks. True thread continuations (same conversation / RE:) attach regardless of this number." },
  auto_draft_enabled: { group: "Drafting & replies", label: "Auto-draft during ingest", type: "switch",
    desc: "Draft replies as messages arrive (reply-only questions and auto-answer rules).",
    help: "On: the responder drafts replies as messages arrive. Off: nothing drafts by itself - you click 'Draft with AI' per item. Turning this off is the cheapest way to pause the LLM entirely." },
  outlook_drafts_enabled: { group: "Drafting & replies", label: "Outlook drafts on approve", type: "switch",
    desc: "Approved replies become reply-all DRAFTS in the mailbox — the hub never sends.",
    help: "When you approve (or approve-with-edit) an email reply, the hub creates it as a reply-all DRAFT in the source mailbox via Graph (Mail.ReadWrite - a permission that cannot send). Requires that consent on the Graph app; failures are recorded in the audit log." },
  send_enabled: { group: "Drafting & replies", label: "Send (legacy)", type: "switch",
    desc: "Kept for compatibility only — there is no send path in the hub. Leave off.",
    help: "The hub has NO send path by design. Approved replies become Outlook DRAFTS instead and you hit Send in Outlook yourself." },
  coder_auto_enabled: { group: "Coder agent", label: "Auto-dispatch the coder", type: "switch",
    desc: "Run the full coder lifecycle (issue → CLI → report → close) on every new real task.",
    help: "On: every new REAL task automatically runs the coder at ingest - GitHub issue opened, claude CLI works it, report + reply, auto-close or escalation. Requires the claude CLI installed and authenticated on the server. Off: you click 'Send to coder' on the task." },
  feed_days: { group: "Display", label: "Timeline lookback (days)", type: "number",
    desc: "How many days of messages the Timeline shows. Display only — nothing is deleted.",
    help: "Purely a display window for the Timeline tab. Older messages remain in the database and in task histories." },
};
const GROUPS = ["Triage & routing", "Drafting & replies", "Coder agent", "Display", "Other"];
const meta = (name) => KNOB_META[name] || { group: "Other", label: name, type: "auto" };

const SECTION_HELP = {
  policies: { title: "Routing policies — the deterministic layer",
    body: "Rules evaluated BEFORE any AI touches a message; no model confidence can override them. Precedence: ignore > escalate > auto_answer > draft > task_only — within one action, lowest order number wins.\n\nKINDS: keyword (pipe-separated substrings matched against subject+body), sender (exact addresses), sender_domain (domains), noreply (built-in matcher for automated addresses), first_time_sender (fires when the address has never been seen).\n\nACTIONS: ignore (no task, message stays visible in the feed), escalate (a human always decides), auto_answer (the draft is auto-approved — still never sent), draft (targeted default), task_only (file it, no reply).\n\nWhen you hit 'Not a task', a sender ignore rule is added here automatically — the learning loop writes into this table." },
  memory: { title: "Agent memory — the learned layer",
    body: "Standing notes distilled from your review verdicts (No reply needed, Not a task, Reject, and your edits) plus anything you add manually. Scopes: global (always injected), sender, sender_domain, source. Active notes are injected into every draft the agents write.\n\nThis is the durable memory; the nightly DIGEST.md (Docs tab) is the daily working memory. Toggle off anything learned wrong — deactivated notes stay for the record but are never injected." },
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

  const load = useCallback(async () => {
    try {
      const [p, s, m] = await Promise.all([api.get("/api/policies"), api.get("/api/settings"), api.get("/api/memory")]);
      setPolicies(p.data.data || []); setSettings(s.data.data || []); setMemory(m.data.data || []);
      api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {});
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
    ...settings.filter((s) => { const m = meta(s.Name); return hit(s.Name, s.Description, m.label, m.desc, m.help, m.group); })
      .map((s) => ({ key: `k${s.Name}`, label: meta(s.Name).label, crumb: `Configuration → ${meta(s.Name).group}`,
        go: () => { setPage("config"); setCfgTab(meta(s.Name).group); setQ(""); } })),
    ...(policies || []).filter((p) => hit(p.Name, p.Kind, p.Pattern, p.Action, p.Reason))
      .map((p) => ({ key: `p${p.PolicyId}`, label: p.Name, crumb: "Routing policies", go: () => { setPage("policies"); setQ(""); } })),
    ...memory.filter((m) => hit(m.Note, m.Scope, m.ScopeKey, m.Source))
      .map((m) => ({ key: `m${m.MemoryId}`, label: m.Note.slice(0, 70), crumb: "Agent memory", go: () => { setPage("memory"); setQ(""); } })),
  ];

  const control = (s) => {
    const m = meta(s.Name);
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
    const rows = settings.filter((s) => meta(s.Name).group === cfgTab);
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
