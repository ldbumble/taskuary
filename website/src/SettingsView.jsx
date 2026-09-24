// Settings: a rail on the left that is the whole map - every page, and under it the sections
// that page stacks - beside one scrolling page. Picking a section scrolls to it; it does not
// swap the page out, so a knob two sections down is one scroll away rather than a tab hunt.
// Search reaches EVERYTHING (knobs, rules, memory, help text, the section names themselves)
// and lands you on the same anchor, under the same path the rail shows.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, InputAdornment, MenuItem, Select, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { SOUNDS, playSound } from "./handraise.js";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SearchIcon from "@mui/icons-material/Search";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import VerifiedIcon from "@mui/icons-material/Verified";
import TuneIcon from "@mui/icons-material/Tune";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import PsychologyIcon from "@mui/icons-material/Psychology";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import AiDefaults from "./AiDefaults.jsx";
import AboutYou from "./AboutYou.jsx";
import UpdateCard from "./UpdateCard.jsx";
import SystemUpdateAltIcon from "@mui/icons-material/SystemUpdateAlt";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, mono, ACTION_COLORS } from "./theme.jsx";
import { ChannelIcon, ConfirmDelete, Empty } from "./ui.jsx";
import { notifyState } from "./notify.js";
import { normalizeBrainOptions } from "./brainOptions.js";
import { ABOUT_SECTIONS, AUDIT_SECTIONS, secId, pageId, scrollToSection, sectionOffset, SCROLL_TOP } from "./settingsMap.js";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import DocsView, { OPERATOR_DOCS } from "./DocsView.jsx";


const KINDS = ["keyword", "sender", "sender_domain", "noreply", "first_time_sender"];
// skip = never shows on the timeline at all (flood senders); ignore = shows, no task
const ACTIONS = ["skip", "ignore", "escalate", "auto_answer", "draft", "task_only"];
const NEW_POLICY = { Name: "", Kind: "keyword", Pattern: "", Action: "draft", Reason: "", SortOrder: 100, Active: true };
// what a note can be ABOUT. "subject" leads because most verdicts are about a kind of work
// rather than a person - and it was missing here, so a topic rule could only be created by
// pressing "Not our task" on a message, never written by hand.
const SCOPES = ["subject", "sender", "sender_domain", "source", "global"];
const SCOPE_LABEL = { subject: "any mail about a topic", sender: "one sender",
  sender_domain: "everyone at a domain", source: "one connection (mailbox, repo)",
  global: "every message" };
const SCOPE_KEY_LABEL = { subject: "the topic, e.g. resident refund request", sender: "their address",
  sender_domain: "the domain, e.g. vendor.com", source: "the mailbox or repo it arrives on" };

import schema from "../../taskuary/settings_schema.json";
// ONE VOCABULARY for the knobs, in taskuary/settings_schema.json - the assistant reads the same file
// (settings_schema.py, appfacts.py), so a knob is called the same thing on this page and in the chat.
const KNOB_META = schema.knobs;
// "Assistant on your phone" is its own tab, not a row inside Assistant: the rest of that tab is
// how the assistant BEHAVES (how many lines, how long a follow-up waits), and this is where you
// can reach it at all - a different question, asked once, for every channel (the owner,
// 2026-09-17: "make the assistant -> whatsapp/telegram section separate").
/* ── WHERE YOU CAN TALK TO THE ASSISTANT ────────────────────────────────────────────────
   One question - "where can I reach it, and when may it listen" - that used to be three places:
   a bare text box asking for a chat id on the WhatsApp card, another on the Telegram card, and the
   standing permission over here under Notifications, whose own help text had to end with "name the
   Assistant chat on the WhatsApp or Telegram card under Connections first". A setting that tells
   you to go somewhere else to finish is the split this replaces (the owner, 2026-09-17).

   Only chats you are ALONE in are offered, and that is enforced again on the way in
   (remote_assistant.use_chat) - the picker is a convenience, not the guard. */
const PhoneDoorways = ({ onLoaded }) => {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");     // could not READ the channels
  const [wErr, setWErr] = useState("");   // could not WRITE a choice
  // A REQUEST THAT FAILED IS NOT AN EMPTY ANSWER. Catching the error into an empty list made a
  // 404 - the app still running the Python from before this shipped - read as "you have no WhatsApp
  // or Telegram connection", which is a lie about the owner's own setup, and the one thing a
  // settings page must never tell you (2026-09-17: "don't see anything there just one setting?").
  const load = useCallback(async () => {
    try { setRows((await api.get("/api/assistant/doorways")).data.data || []); setErr(""); onLoaded?.(true); }
    catch (e) {
      setRows(null);
      setErr(e?.response?.status === 404
        ? "This page needs a newer Taskuary than the one running — restart the app and it appears."
        : (e?.response?.data?.detail || "could not read your channels just now"));
      onLoaded?.(false);
    }
  }, [onLoaded]);
  useEffect(() => { load(); }, [load]);
  const choose = async (channel, chat) => {
    setBusy(channel); setWErr("");
    try { await api.post("/api/assistant/doorways", { channel, chat }); await load(); }
    catch (e) { setWErr(e?.response?.data?.detail || "could not set that chat"); }
    setBusy("");
  };
  const listen = async (channel, how) => {
    setBusy(channel); setWErr("");
    try { await api.post("/api/assistant/doorways/listens", { channel, listens: how }); await load(); }
    catch (e) { setWErr(e?.response?.data?.detail || "could not change that"); }
    setBusy("");
  };
  return (
    <Box sx={{ mb: 2 }}>
      {(rows || []).map((r) => {
        const picked = r.options.find((o) => o.to === r.chat)
          || (r.chat ? { to: r.chat, name: r.chat, mine: true } : null);
        return (
          <Box key={`${r.channel}-${r.connectorId}`} sx={{ py: 2, borderBottom: `1px solid ${BORDER}` }}>
            <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap" }}>
              <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, minWidth: 92, textTransform: "capitalize" }}>
                {r.channel}
              </Typography>
              {!r.live ? (
                <Typography variant="body2" sx={{ color: DIM }}>
                  not switched on — turn it on under Connections first
                </Typography>
              ) : (
                <>
                  <Autocomplete size="small" sx={{ flex: 1, minWidth: 260 }} autoHighlight disabled={busy === r.channel}
                    options={r.options} value={picked}
                    getOptionLabel={(o) => o?.name || o?.to || ""}
                    isOptionEqualToValue={(o, v) => o.to === v.to}
                    onChange={(_e, v) => choose(r.channel, v?.to || "")}
                    noOptionsText={r.channel === "whatsapp"
                      ? "no private chat seen yet — message yourself on WhatsApp, then reopen this page"
                      : "no private chat seen yet — send your bot a direct message, then reopen this page"}
                    renderOption={(props, o) => (
                      <li {...props} key={o.to} style={{ display: "block", paddingTop: 4, paddingBottom: 4 }}>
                        <Typography variant="body2" sx={{ fontSize: 12.5, color: INK, fontWeight: 600 }}>{o.name}</Typography>
                        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10, fontFamily: "monospace" }}>{o.to}</Typography>
                      </li>
                    )}
                    renderInput={(params) => <TextField {...params} sx={{ bgcolor: "#fff" }}
                      placeholder="not connected — pick the chat that is only you" />} />
                  {r.chat && <Button size="small" disabled={busy === r.channel}
                    onClick={() => choose(r.channel, "")} sx={{ fontSize: 11.5 }}>disconnect</Button>}
                </>
              )}
            </Box>
            {/* WHEN, asked of this channel. The answer differs by channel - your own phone is not
                your bot - so a single switch under both rows was answering for both at once. */}
            {r.live && r.chat && (
              <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", mt: 1, ml: { sm: 12.5 }, flexWrap: "wrap" }}>
                <Select size="small" value={r.listens || "walk"} disabled={busy === r.channel}
                  sx={{ bgcolor: "#fff", fontSize: 12.5, minWidth: 260 }}
                  onChange={(e) => listen(r.channel, e.target.value)}>
                  <MenuItem value="always" sx={{ fontSize: 12 }}>listens any time you message it</MenuItem>
                  <MenuItem value="walk" sx={{ fontSize: 12 }}>listens only while a walk is handed over</MenuItem>
                </Select>
                <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 200 }}>
                  {r.listens === "always"
                    ? "Anything you type there runs the same walk the Assistant tab runs — and may include private mail, tasks, reviews and agent output."
                    : "Quiet until you hand a walk over from the Assistant tab. The hand-over works either way."}
                </Typography>
              </Box>
            )}
          </Box>
        );
      })}
      {err && (
        <Typography variant="body2" sx={{ color: "#6b2733", py: 2 }}>{err}</Typography>
      )}
      {rows && !rows.length && (
        <Typography variant="body2" sx={{ color: DIM, py: 2 }}>
          No WhatsApp or Telegram connection yet. Add one under Connections and it appears here.
        </Typography>
      )}
      {rows === null && !err && <Typography variant="body2" sx={{ color: FAINT, py: 2 }}>reading your channels…</Typography>}
      <Typography variant="body2" sx={{ color: FAINT, mt: 2 }}>
        Only chats you are alone in are offered. A group can never command the assistant, and an answer
        about your mail must not land where other people are reading. This is separate from the
        Notifications role — the assistant chat is not subscribed to ordinary Taskuary alerts.
      </Typography>
      {wErr && <Typography variant="body2" sx={{ color: "#6b2733", mt: 1 }}>✗ {wErr}</Typography>}
    </Box>
  );
};

const GROUPS = schema.groups;
// Internal state, and settings that live on another page - never shown as knobs. The "Other" tab
// used to catch every bookkeeping value the server ever wrote (digest_report_seeded, task_id_mark,
// learn_pending, owner_bio...), each with a switch that did something nobody could predict.
const HIDDEN = new Set(["ingest_status", "agent_issues_enabled", "agent_push_enabled",   // github card decisions
                        "funnel_hours", "funnel_max", // retained values; All and Unread now share history without an item cap
                        "auto_draft_enabled",   // replies are always drafted (PW-043); the old switch no longer gates anything
                        // A KNOB NOBODY READS IS NOT A KNOB. Four rows on this page changed
                        // nothing at all - verified by reading every Python module for the key,
                        // not by trusting the label (the owner, 2026-09-16: "make sure they change
                        // things"). Two of them were the dangerous kind, a switch about sending and
                        // a failover chain, both of which you would reasonably believe you had set:
                        //   send_enabled, outlook_drafts_enabled - no reader anywhere, ever
                        //   attach_threshold        - routing.route() takes it as a default ARGUMENT
                        //                             and nobody passes the setting (docstring fixed)
                        //   backup_agents           - superseded by backup_brains in the 2026-09-16
                        //                             brain split; store.py says so in as many words
                        // The rows stay in the table (deleting a stored value is a migration, and
                        // `backup_agents` is still the pre-split value an old install may want to
                        // read back); they are simply not offered as something you can set.
                        "send_enabled", "outlook_drafts_enabled", "attach_threshold", "backup_agents",
                        "last_pinged_review", "triage_last_error",                          // bookkeeping
                        // ...and the one step that records having been LOOKED at (setup.SEEN_MODELS,
                        // written by the AI-defaults panel's own mount). A switch for it would
                        // un-tick a setup step you had already done.
                        "setup_dismissed", "setup_seen_models",
                        "task_id_mark", "learn_pending", "learn_last_reflect"]);
// The AI defaults the panel at the top of this section draws as cards - each would otherwise also
// appear as a bare dropdown in the knob list. THE LIST IS NOT KEPT HERE: aidefaults.py grew a
// fifth slot (`judge_ai`, "Where runs go") and this hand-written set did not, so a real setting
// the owner is meant to pick showed up as an unlabelled text box in "Other" - exactly what
// `assistant_ai` did in d3bde8bd. It lives in the schema now, and a Python test fails if a slot
// is missing from it (the owner, 2026-09-18: "what is the other settings in configuration").
const PANEL_OWNED = new Set(schema.panel_owned);
// MACHINE STATE IS NOT CONFIGURATION. The settings table is also where the app keeps its own
// bookkeeping - which CLI session a chat is on, where a per-task cursor got to, when a sweep last
// ran - and every row without a KNOB_META entry fell through to the "Other" tab as an editable
// text box. On a real install that was 185 of 249 rows, 162 of them per-entity ids and
// timestamps: a page of machine state you can type over (the owner, 2026-09-16: "does not feel
// useful"). A per-entity key is `name:<id>` and is state by construction; the scalars are named.
// Nothing here is deleted or stopped being written - it just is not offered as a knob.
// Two more that READ like settings and are not: `handbook_on_by_default` is a one-shot marker
// ("flip it once and remember that we did", store.py) and `processing_membership_rules` is a
// stamp of the grouping-rule version that triggers one reconcile when it changes. Typing in
// either does nothing useful and re-running a migration is the best case.
// `voice_vocabulary` is real, but it is a list of up to 100 terms that /api/voice/vocabulary
// sanitises with voice.normalize_vocabulary on save - a raw text box here writes straight past
// that validation, which is worse than not offering it.
// `assistant_card` and `counsel_enabled` have NO reader anywhere: two more dead knobs found the
// same way as the other four (grep every module for the key, do not trust the label).
// ...and the two the combined "who may start a worker" row now owns: they are still the
// settings senders.py reads, they just are not their own rows any more. Plus two one-shot
// migration sentinels that end in _fixed and _dropped rather than _seeded and so slipped the
// suffix rule - the second of which was the only thing keeping "Other" on the page at all.
const STATE = new Set(["trust_sent_history", "trust_non_email", "triage_pr_rule_fixed",
  "whatsapp_star_dropped",
  "handbook_on_by_default", "processing_membership_rules", "voice_vocabulary",
  "assistant_card", "counsel_enabled",
  "app_sessions", "assistant_dock_task_id", "assistant_handoff", "assistant_last_run",
  "assistant_notes", "auto_start_upgraded", "github_login",
  "learn_reflect_log", "problems_dismissed", "wall_rolled_on"]);
// A KEY ENDING `_at` IS A STAMP, NOT A KNOB. Six of them exist and every one is the app writing
// down when it last did something - the morning line, a cleanup sweep, an ingest fetch, where the
// setup walk stopped. Two of those (`setup_walk_at`, `phone_morning_line_at`) were newer than the
// hand-written list and so were being offered as text boxes under "Other"; naming each one as it
// appears is how that keeps happening. No knob in the schema ends in `_at`, and a stamp you can
// type over is at best a re-run and at worst a lie about what already went out.
const isState = (name) => name.includes(":") || name.endsWith("_at") || STATE.has(name);
// WHAT IT WAS BEFORE YOU TOUCHED IT. No description carried its own default, so a page of knobs
// could not tell you which ones you had actually changed, or what the shipped answer had been -
// and a default written into 55 strings is 55 places to drift. The server sends `Default` straight
// from store.DEFAULT_SETTINGS; this only decides how to say it.
const showValue = (v, type) => {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (type === "switch") return s === "1" ? "on" : "off";
  return s === "" ? "blank" : s;
};
const defaultNote = (s, type) => {
  const d = showValue(s.Default, type);
  if (!d) return "";
  const now = showValue(s.Value, type);
  return now === d ? `Default: ${d} \u2014 unchanged.` : `Default: ${d}. Yours: ${now}.`;
};

const hidden = (name) => HIDDEN.has(name) || isState(name)
  || name.startsWith("owner_") || name.endsWith("_seeded");   // owner_* = About you
const meta = (name) => KNOB_META[name] || { group: "Other", label: name, type: "auto" };

const SECTION_HELP = {
  policies: { title: "Routing policies — the deterministic layer",
    body: "Rules evaluated BEFORE any AI touches a message; no model confidence can override them. Precedence: ignore > escalate > auto_answer > draft > task_only — within one action, lowest order number wins.\n\nKINDS: keyword (pipe-separated substrings matched against subject+body), sender (exact addresses), sender_domain (domains), noreply (built-in matcher for automated addresses), first_time_sender (fires when the address has never been seen).\n\nACTIONS: ignore (no task, message stays visible in the feed), escalate (a human always decides, and the task is marked urgent - this is the ONLY thing that marks one urgent, so name the senders whose mail jumps your queue), auto_answer (the draft is auto-approved — still never sent), draft (targeted default), task_only (file it, no reply).\n\nNothing writes into this table by itself: 'Not a task' teaches a verdict in Memory, not a rule here, and muting a sender is 'Skip this sender'." },
  memory: { title: "Verdicts & notes — the evidence behind LEARNED.md",
    body: "Two layers, one loop. LEARNED.md (Settings → Docs) is the GENERAL profile — your style, your responsibilities, what deserves a task — and it is written by a nightly pass. This page is the EVIDENCE that pass reads: one dated line per verdict you gave ('Not our task' on this subject from this sender, 'Not a task' on that one) plus notes you type yourself, each tied to a sender, a domain, a subject, or everyone.\n\nWhen a new message arrives, the lines that bear on it (same sender, same topic) ride into triage and into the reply draft, and the model judges how alike the new message really is — the same sender asking the same thing is binding, a shared word is not. The general lessons in LEARNED.md are distilled from these same lines under a stricter rule (LEARNED.md → Verdicts lists which ones fed which lesson).\n\nSo nothing was removed: LEARNED.md is what it concluded, this is what it concluded it from. Toggle off a line learned wrong — it stays for the record and is never injected again; the next distillation drops it too." },
  audit: { title: "Audit integrity — what the log is, and how to read it",
    body: "Every consequential thing Taskuary does is one row in an append-only log: a message routed or filed and why, a verdict you gave, a reply sent, an agent session opened or wrapped, a connector saved or signed in, a setting changed, a task deleted. Each row stores a hash of its own contents PLUS the hash of the row before it, so the rows form a chain: change any row after the fact — even one character in the database — and its hash no longer matches, and every row after it points at a parent that no longer exists.\n\nVerify recomputes the whole chain from the first row. Intact means the record you see is the record that was written. 'Contents altered' names the exact rows that were changed after writing — the thing this log exists to catch. 'Out of order' means two writers raced at the same instant once; nothing was changed, and it cannot recur.\n\nThe history below is that log, newest first: when, who (you, the router, an agent, a scheduled report), what was done, to what. It is the answer to 'why did this happen' and 'who did this' for anything on the Timeline or the Board." },
};

// ONE WIDTH FOR ALL SIX PAGES, and it is Configuration's. Giving each page the width its own
// content wanted (a form narrow, a table the whole column) meant the block around it changed size
// as you moved down the rail - and because the block is centred, the RAIL slid sideways with it:
// you clicked Routing policies and the menu you had just clicked moved (the owner, 2026-09-18:
// "keep it the same as above"). A settings menu that does not hold still is worse than a table
// with less room, so the tables give up the room. Change this one number, not six.
const PAGE = 980;

const PAGES = {
  about: { title: "About you", icon: AccountCircleIcon, desc: "Who the system knows you are — your identities per channel, the facts only you can add, your avatar." },
  docs: { title: "Docs", icon: MenuBookIcon, desc: "The documents the system writes from and writes to — how you sound, what triage is told, what it has learned, and the playbooks your agents follow." },
  config: { title: "Configuration", icon: TuneIcon, desc: "Triage, drafting, coder and display knobs — how the funnel behaves." },
  policies: { title: "Routing policies", icon: AltRouteIcon, desc: "Deterministic rules the AI can never override — ignores, escalations, auto-answers." },
  memory: { title: "Verdicts & notes", icon: PsychologyIcon, desc: "The evidence behind LEARNED.md — every verdict you gave, one line each, plus notes you write. Toggle off what it learned wrong." },
  audit: { title: "Audit integrity", icon: VerifiedIcon, desc: "Who did what, when — a tamper-evident record of every action, and a button that proves nobody edited it." },
  updates: { title: "Updates", icon: SystemUpdateAltIcon, desc: "Which build is running, which is the latest release, and one button that installs it and reopens — connections and settings untouched." },
};

// WHAT EACH PAGE STACKS. The rail draws these under the page as sub-entries, the page stamps the
// same id on the matching heading, and search says the same path back to you. Configuration's are
// the schema's groups - add a group there and it appears in all three at once. A page with no
// entry here is one section long and simply has no sub-entries.
const SECTIONS = { about: ABOUT_SECTIONS, config: GROUPS, audit: AUDIT_SECTIONS };

// The heading a rail entry scrolls to. scrollMarginTop is the belt to the offset's braces: a
// keyboard "find in page" or a browser restoring the anchor does not go through scrollToSection.
const SectionHead = ({ page, name }) => (
  <Typography id={secId(page, name)} sx={{ color: INK, fontWeight: 800, fontSize: 14.5, pt: 0.5, pb: 0.75, mb: 1.75,
    borderBottom: `1px solid ${BORDER}`, scrollMarginTop: `${SCROLL_TOP}px` }}>{name}</Typography>
);

// THE HEADING THAT STARTS A PAGE, and the reason the document reads as a document rather than as
// seven of them joined end to end: you always know which one you have scrolled into. Four pages
// used to get this line and three did not, because it was drawn outside SettingsPages and only
// for the pages whose own first row was a knob. It belongs to the page.
const PageHead = ({ page, first }) => (
  // the rule above it is the seam: without one, seven pages end to end read as one page that
  // keeps changing its mind about what it is about
  <Box sx={{ mt: first ? 0 : 7, pt: first ? 0 : 5, borderTop: first ? "none" : `1px solid ${BORDER}` }}>
    <Box id={pageId(page)} sx={{ display: "flex", alignItems: "center", gap: 1, scrollMarginTop: `${SCROLL_TOP}px` }}>
      {React.createElement(PAGES[page].icon, { sx: { fontSize: 17, color: FAINT } })}
      <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15 }}>{PAGES[page].title}</Typography>
    </Box>
    <Typography variant="body2" sx={{ color: DIM, mt: 0.25, mb: 2 }}>{PAGES[page].desc}</Typography>
  </Box>
);

// onNavigate is threaded through: goFromPanel below calls it, and it was declared on
// SettingsView instead - two components apart, so the panel's "go to Connections" was a
// ReferenceError waiting for a click. The scope test only tracks set* setters, so eslint's
// no-undef is what caught it before it shipped.
function SettingsPages({ q, setQ, onNavigate, onJump, onSections, docSel, setDocSel, onCatalog }) {
  const [policies, setPolicies] = useState(null);
  const [settings, setSettings] = useState([]);
  const [memory, setMemory] = useState([]);
  const [newNote, setNewNote] = useState(null);
  const [draft, setDraft] = useState(null);
  const [verify, setVerify] = useState(null);
  const [help, setHelp] = useState(null);
  const [panelOk, setPanelOk] = useState(false);   // the AI defaults panel is standing up; until it is, the plain rows stay
  const [err, setErr] = useState("");

  const [brains, setBrains] = useState([]);
  const [agentNames, setAgentNames] = useState([]);
  const [agentOptions, setAgentOptions] = useState([]);
  const [agentModels, setAgentModels] = useState({});
  const [connectors, setConnectors] = useState([]);

  const load = useCallback(async () => {
    try {
      const [p, s, m] = await Promise.all([api.get("/api/policies"), api.get("/api/settings"), api.get("/api/memory")]);
      setPolicies(p.data.data || []); setSettings(s.data.data || []); setMemory(m.data.data || []);
      api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {});
      api.get("/api/agents").then(({ data }) => {
        const rows = data.data || [], models = data.models || {}, seen = new Set();
        setAgentNames(rows.map((a) => a.Name));
        setAgentModels(models);
        // Settings asks which coding CLI runs, not which instruction profile it wears.
        // The endpoint puts the saved default first; keep that order and collapse profiles
        // backed by the same executable into one provider choice.
        setAgentOptions(rows.filter((a) => ["coding", "cli"].includes(String(a.Kind || "").toLowerCase()))
          .map((a) => ({ value: a.Name, label: models[a.Name]?.cli || models[a.Name]?.cmd || a.Name }))
          .filter((a) => !seen.has(a.label) && seen.add(a.label)));
      }).catch(() => {});
      api.get("/api/connectors").then(({ data }) => setConnectors(data.data || [])).catch(() => {});
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load settings"); }
  }, []);

  const selectedBrains = useMemo(() => {
    const value = (name) => settings.find((s) => s.Name === name)?.Value || "";
    return [value("triage_ai"), ...String(value("triage_backup_ai")).split(",").map((v) => v.trim())];
  }, [settings]);
  const brainOptions = useMemo(
    () => normalizeBrainOptions(brains, agentModels, selectedBrains),
    [brains, agentModels, selectedBrains]);
  useEffect(() => { load(); }, [load]);

  const savePolicy = async (p) => { await api.post("/api/policies", p); setDraft(null); load(); };
  const togglePolicy = async (p) => { await api.post("/api/policies", { PolicyId: p.PolicyId, Active: !p.Active }); load(); };
  const [delPolicy, setDelPolicy] = useState(null);      // the rule awaiting its confirm
  const deletePolicy = async (p) => { await api.delete(`/api/policies/${p.PolicyId}`); load(); };
  const saveSetting = async (name, value) => { await api.patch("/api/settings", { name, value }); load(); };
  const toggleMemory = async (m) => { await api.patch(`/api/memory/${m.MemoryId}`, { active: !m.Active }); load(); };
  const addNote = async () => { await api.post("/api/memory", newNote); setNewNote(null); load(); };
  const runVerify = async () => setVerify((await api.get("/api/audit/verify")).data);

  // Where a model is really saved. The AI defaults panel names the owning screen and this
  // opens it: the CLI roster is a Settings page, a connector card lives on Connections (whose
  // own hash router picks up connector=<id>), so the tab has to move for the second kind.
  const goFromPanel = (where) => {
    if (where === "agents") {
      window.location.hash = "profiles";
      onNavigate?.("Docs");
      return;
    }
    if (where && where.startsWith("connector:")) window.location.hash = `connector=${where.slice(10)}`;
    onNavigate?.("Connections");
  };

  // Deep search: every hit knows the page and the section it lives in, and scrolls there.
  // Sections lead - they are the rail's own entries, and a search for a place should offer the place.
  const hit = (...parts) => parts.join(" ").toLowerCase().includes(q.toLowerCase());
  const results = !q ? [] : [
    // the sections themselves, under the same path the rail draws - typing "display" should offer
    // the section, not only the three knobs that happen to sit in it (the owner, 2026-09-18)
    ...Object.entries(SECTIONS).flatMap(([pg, names]) => names.filter((n) => hit(n, PAGES[pg].title))
      .map((n) => ({ key: `s${pg}${n}`, label: n, crumb: `${PAGES[pg].title} → ${n}`, section: true,
        go: () => { setQ(""); onJump(pg, n); } }))),
    ...settings.filter((s) => { if (hidden(s.Name)) return false; const m = meta(s.Name); return hit(s.Name, s.Description, m.label, m.desc, m.help, m.group); })
      .map((s) => ({ key: `k${s.Name}`, label: meta(s.Name).label, crumb: `Configuration → ${meta(s.Name).group}`,
        go: () => { setQ(""); onJump("config", meta(s.Name).group); } })),
    ...(policies || []).filter((p) => hit(p.Name, p.Kind, p.Pattern, p.Action, p.Reason))
      .map((p) => ({ key: `p${p.PolicyId}`, label: p.Name, crumb: PAGES.policies.title, go: () => { setQ(""); onJump("policies"); } })),
    ...memory.filter((m) => hit(m.Note, m.Scope, m.ScopeKey, m.Source))
      .map((m) => ({ key: `m${m.MemoryId}`, label: m.Note.slice(0, 70), crumb: PAGES.memory.title, go: () => { setQ(""); onJump("memory"); } })),
  ];

  const control = (s) => {
    const m = meta(s.Name);
    const codingOptions = agentOptions.length ? agentOptions : agentNames.map((n) => ({ value: n, label: n }));
    // Coding defaults choose an executable. The stored value remains its representative worker
    // so existing task/session APIs keep their profile-specific model and repository mappings.
    if (m.type === "agent") return (
      <Select size="small" value={codingOptions.some((o) => o.value === s.Value) ? s.Value : (codingOptions[0]?.value || "")}
        onChange={(e) => saveSetting(s.Name, e.target.value)} sx={{ minWidth: 140, fontSize: 12.5, bgcolor: "#fff" }}>
        {codingOptions.map((o) => <MenuItem key={o.value} value={o.value} sx={{ fontSize: 12.5 }}>{o.label}</MenuItem>)}
        {!codingOptions.length && <MenuItem value="" disabled sx={{ fontSize: 12.5 }}>no coding CLI yet — add one under Connections</MenuItem>}
      </Select>
    );
    if (m.type === "agents") {
      const values = s.Value === "*" ? ["*"] : String(s.Value || "").split(",").filter((v) => codingOptions.some((o) => o.value === v));
      return (
        <Select size="small" multiple displayEmpty value={values}
          renderValue={(picked) => picked.includes("*") ? "automatic — any other coding CLI"
            : picked.length ? picked.map((v) => codingOptions.find((o) => o.value === v)?.label || v).join(" → ") : "none"}
          onChange={(e) => {
            const picked = typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value;
            saveSetting(s.Name, picked.includes("*") ? "*" : picked.join(","));
          }} sx={{ minWidth: 250, maxWidth: 380, fontSize: 12.5, bgcolor: "#fff" }}>
          <MenuItem value="*" sx={{ fontSize: 12.5 }}>automatic — any other configured coding CLI</MenuItem>
          {codingOptions.map((o) => <MenuItem key={o.value} value={o.value} sx={{ fontSize: 12.5 }}>{o.label}</MenuItem>)}
        </Select>
      );
    }
    // the brains list is dynamic: AI connectors that actually hold a key + your CLI agents
    if (m.type === "brain") return (
      <Select size="small" displayEmpty value={brainOptions.some((b) => b.value === s.Value) ? s.Value : ""}
        sx={{ minWidth: 250, fontSize: 12.5, bgcolor: "#fff" }}
        onChange={(e) => saveSetting(s.Name, e.target.value)}>
        {brainOptions.map((b) => (
          <MenuItem key={b.value} value={b.value} disabled={!b.ready} sx={{ fontSize: 12.5 }}>
            {b.label}{b.ready ? "" : " — no key saved"}
          </MenuItem>
        ))}
      </Select>
    );
    if (m.type === "brains") {
      const options = brainOptions.filter((b) => b.value);
      const values = String(s.Value || "").split(",").filter((v) => options.some((b) => b.value === v));
      return (
        <Select size="small" multiple displayEmpty value={values}
          renderValue={(picked) => picked.length
            ? picked.map((v) => options.find((b) => b.value === v)?.label || v).join(" → ") : "none"}
          onChange={(e) => saveSetting(s.Name, (typeof e.target.value === "string"
            ? e.target.value.split(",") : e.target.value).join(","))}
          sx={{ minWidth: 250, maxWidth: 420, fontSize: 12.5, bgcolor: "#fff" }}>
          {options.map((b) => <MenuItem key={b.value} value={b.value} disabled={!b.ready} sx={{ fontSize: 12.5 }}>
            {b.label}{b.ready ? "" : " — unavailable"}
          </MenuItem>)}
        </Select>
      );
    }
    // a csv of channels: chips you toggle, which is what "which of these" actually is -
    // a comma-separated text field asked the owner to spell channel names correctly
    // ONE QUESTION, ONE ROW. Three switches asked one thing - who may start a worker without
    // you - and a reader had to hold all three in their head to know the answer (the owner,
    // 2026-09-16). This draws them as one set of pills over the SAME three settings: no new key,
    // no migration, and senders.py still reads exactly what it always read.
    if (m.type === "flags") {
      const keys = Object.keys(m.flags);
      const val = (k) => (settings.find((x) => x.Name === k)?.Value ?? "1") === "1";
      const none = keys.every((k) => !val(k));
      return (
        <Box sx={{ display: "flex", gap: 0.6, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: 360 }}>
          {keys.map((k) => (
            <Box key={k} title={m.flags[k].help} onClick={() => saveSetting(k, val(k) ? "0" : "1")}
              sx={{ display: "inline-flex", alignItems: "center", px: 0.9, py: 0.35, borderRadius: 99,
                cursor: "pointer", fontSize: 11.5, fontWeight: val(k) ? 700 : 500, userSelect: "none",
                bgcolor: val(k) ? "#eae4d8" : "#e9e3d8", color: val(k) ? "#55697a" : DIM,
                border: `1px solid ${val(k) ? "#d8cfbe" : BORDER}`, "&:hover": { borderColor: "#d8cfbe" } }}>
              {m.flags[k].label}
            </Box>
          ))}
          {/* all three off is a real choice, not a broken row - say what it means */}
          {none && <Typography variant="caption" sx={{ color: FAINT, alignSelf: "center", ml: 0.5 }}>
            nobody — every task waits for your click
          </Typography>}
        </Box>
      );
    }
    if (m.type === "channels") {
      const on = new Set(String(s.Value || "").split(",").map((x) => x.trim()).filter(Boolean));
      const toggle = (ch) => {
        on.has(ch) ? on.delete(ch) : on.add(ch);
        saveSetting(s.Name, m.options.filter((o) => on.has(o)).join(","));
      };
      return (
        <Box sx={{ display: "flex", gap: 0.6, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: 340 }}>
          {m.options.map((ch) => (
            <Box key={ch} onClick={() => toggle(ch)}
              sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, px: 0.9, py: 0.35, borderRadius: 99,
                cursor: "pointer", fontSize: 11.5, fontWeight: on.has(ch) ? 700 : 500, userSelect: "none",
                bgcolor: on.has(ch) ? "#eae4d8" : "#e9e3d8", color: on.has(ch) ? "#55697a" : DIM,
                border: `1px solid ${on.has(ch) ? "#d8cfbe" : BORDER}`, "&:hover": { borderColor: "#d8cfbe" } }}>
              <ChannelIcon channel={ch} sx={{ fontSize: 12 }} />{ch}
            </Box>
          ))}
        </Box>
      );
    }
    if (m.type === "sound") {
      return (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Select size="small" value={s.Value || "chime"} sx={{ width: 130, bgcolor: "#fff", fontSize: 12.5 }}
            onChange={(e) => { saveSetting(s.Name, e.target.value); playSound(e.target.value); }}>
            {SOUNDS.map((o) => <MenuItem key={o} value={o} sx={{ fontSize: 12.5 }}>{o}</MenuItem>)}
          </Select>
          <IconButton size="small" title="Preview" disabled={(s.Value || "chime") === "off"} onClick={() => playSound(s.Value || "chime")}>
            <PlayArrowIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Box>
      );
    }
    if (m.type === "select") return (
      <Select size="small" value={s.Value} onChange={(e) => saveSetting(s.Name, e.target.value)} sx={{ minWidth: 140, fontSize: 12.5, bgcolor: "#fff" }}>
        {m.options.map((o) => <MenuItem key={o} value={o} sx={{ fontSize: 12.5 }}>
          {(m.optionLabels && m.optionLabels[o]) || o.replaceAll("_", " ")}
        </MenuItem>)}
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

  // WHAT CONFIGURATION ACTUALLY DRAWS, decided once and told to the rail. A group with nothing in
  // it ("Other", on an install where no stray key fell there) must not be a rail entry: it would
  // scroll nowhere and highlight nothing. The rail cannot work this out - the rows are here.
  const rowsOf = (g) => settings.filter((s) => !hidden(s.Name) && meta(s.Name).group === g
    && !(panelOk && PANEL_OWNED.has(s.Name)));
  const panels = {
    "Triage & agents": <AiDefaults brains={brainOptions} agents={agentOptions} onGo={goFromPanel} onLoaded={setPanelOk} />,
    "Notifications": <NotifyStatus connectors={connectors} settings={settings} />,
    "Assistant on your phone": <PhoneDoorways onLoaded={setPanelOk} />,
  };
  const cfgGroups = GROUPS.filter((g) => panels[g] || rowsOf(g).length);
  const cfgKey = cfgGroups.join("|");
  useEffect(() => { onSections(cfgKey ? cfgKey.split("|") : []); }, [cfgKey, onSections]);

  // A spinner that never stops is the worst thing this page can show: on the install where
  // /api/settings answered 500, Settings span for ever and said nothing (2026-09-22).
  if (!policies) return err
    ? <Alert severity="error" sx={{ m: 1 }}>{err}</Alert>
    : <CircularProgress size={22} sx={{ m: 4 }} />;

  // WHAT ONE PAGE OF THE DOCUMENT DRAWS. Every one of them is drawn, every time: Settings is
  // one long page you scroll from About you to Updates, so a page is a place in it rather than
  // something that replaces what was there before (the owner, 2026-09-22: "we should have header
  // for each new section and then continue scrolling"). The loads above are shared, so seven
  // pages cost the same requests one page did.
  const body = (page) => {
    if (page === "config") {
      // ...and the panel's own keys are suppressed wherever they would otherwise land. Scoping this
      // to the panel's tab was fine while every owned key had a KNOB_META entry in that group -
      // then `assistant_ai` lost its entry when it became a card, fell to "Other" by default, and
      // came back as a bare unlabelled text box (d3bde8bd). `panelOk` still puts the plain rows
      // back if the panel fails to load, which is why they keep their KNOB_META entries.
      // A FUNCTION, NOT A COMPONENT: a component declared in here is a new type on every render,
      // so React would remount every row and the box you are typing in would lose the caret.
      const knobRow = (s) => {
        const m = meta(s.Name);
        return (
          <Box key={s.Name} sx={{ display: "flex", alignItems: { xs: "stretch", sm: "center" }, flexDirection: { xs: "column", sm: "row" },
            gap: { xs: 1, sm: 3 }, py: 2.5, borderBottom: `1px solid ${BORDER}`,
            opacity: s.Name === "phone_approvals" && (settings.find((x) => x.Name === "notify_level") || {}).Value === "off" ? 0.5 : 1 }}>
            <Box sx={{ flex: 1, minWidth: 0, cursor: m.help ? "pointer" : "default" }}
              onClick={() => m.help && setHelp({ title: m.label, body: m.help })}>
              <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                {m.label}
                {m.help && <HelpOutlineIcon sx={{ fontSize: 15, color: "#cfc9bf" }} />}
              </Typography>
              <Typography variant="body2" sx={{ color: DIM, mt: 0.25 }}>{m.desc || s.Description}</Typography>
              {/* the line every description was missing: what shipped, and whether this is
                  still it. Quiet on purpose - it is a fact you check, not a thing to read. */}
              {defaultNote(s, m.type) && (
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.3 }}>
                  {defaultNote(s, m.type)}
                </Typography>
              )}
            </Box>
            <Box sx={{ flexShrink: 0 }}>{control(s)}</Box>
          </Box>
        );
      };
      // ONE PAGE, NOT ELEVEN TABS. Every group is a section you scroll past and the rail holds the
      // same eleven names, so nothing runs off the right edge and a knob you half remember is found
      // by reading rather than by guessing which tab it was hiding on (the owner, 2026-09-18).
      return (
        <Box>
          <AssistantChanges />
          {cfgGroups.map((g) => (
            <Box key={g} sx={{ mb: 4.5 }}>
              <SectionHead page="config" name={g} />
              {panels[g]}
              {rowsOf(g).map(knobRow)}
            </Box>
          ))}
        </Box>
      );
    }

    if (page === "policies") {
      return (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <Typography variant="body2" sx={{ color: DIM }}>
              {/* the page title above already says what these are; this line is the door to the rules of the rules */}
              <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.policies)}
                sx={{ color: "#55697a", cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                How precedence works →
              </Typography>
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Button size="small" variant="contained" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => setDraft({ ...NEW_POLICY })}>Add rule</Button>
          </Box>
          {!(policies || []).length && !draft && (
            <Box sx={{ ...card, bgcolor: PANEL2, p: 2.25, mt: 2, maxWidth: 680 }}>
              <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5 }}>No routing rules yet</Typography>
              <Typography variant="body2" sx={{ color: DIM, mt: 0.5, mb: 1.5, maxWidth: 560 }}>
                Rules are optional. Add one when a sender, domain, or message type should always be drafted,
                filed, made into a task, or sent to you for a decision.
              </Typography>
              <Button size="small" variant="outlined" startIcon={<AddIcon sx={{ fontSize: 14 }} />}
                onClick={() => setDraft({ ...NEW_POLICY })}>Add your first rule</Button>
            </Box>
          )}
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
              <IconButton size="small" title="Delete this rule" onClick={() => setDelPolicy(p)}><DeleteOutlineIcon sx={{ fontSize: 16 }} /></IconButton>
            </Box>
          ))}
          <ConfirmDelete open={!!delPolicy} what={delPolicy ? `the rule “${delPolicy.Name}”` : "this rule"}
            consequence="Messages it matched go back to being judged by triage alone."
            onClose={() => setDelPolicy(null)} onConfirm={() => deletePolicy(delPolicy)} />
          {draft && (
            <Box sx={{ ...card, bgcolor: PANEL2, p: 2, mt: 2, display: "flex", flexDirection: "column", gap: 1.25 }}>
              <Typography variant="body2" sx={{ color: "#55697a", fontWeight: 700 }}>{draft.PolicyId ? `Edit rule · ${draft.Name}` : "New rule"}</Typography>
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
        </Box>
      );
    }

    if (page === "memory") {
      return (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <Typography variant="body2" sx={{ color: DIM }}>
              One dated line per verdict you gave, plus notes you write — the evidence LEARNED.md (Docs) distils its general lessons from.
              Lines that bear on a new message ride into its triage and draft.
              <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.memory)}
                sx={{ color: "#55697a", cursor: "pointer", ml: 0.75, "&:hover": { textDecoration: "underline" } }}>
                How this relates to LEARNED.md →
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
                  {SCOPES.map((s) => <MenuItem key={s} value={s}>{SCOPE_LABEL[s] || s.replace("_", " ")}</MenuItem>)}
                </Select>
                {newNote.scope !== "global" && (
                  // a keyed scope with no key matches nothing, ever - the server refuses it now,
                  // so the button does too rather than posting a note that could never fire
                  <TextField fullWidth label={SCOPE_KEY_LABEL[newNote.scope] || "what to match on"}
                    value={newNote.scope_key}
                    onChange={(e) => setNewNote({ ...newNote, scope_key: e.target.value })} />
                )}
              </Box>
              <Box sx={{ display: "flex", gap: 0.75 }}>
                <Button size="small" variant="contained" onClick={addNote}
                  disabled={!newNote.note.trim() || (newNote.scope !== "global" && !(newNote.scope_key || "").trim())}>Save</Button>
                <Button size="small" onClick={() => setNewNote(null)}>Cancel</Button>
              </Box>
            </Box>
          )}
        </Box>
      );
    }

    if (page === "about") return <AboutYou />;
    if (page === "docs") return <DocsView sel={docSel} onSel={setDocSel} onCatalog={onCatalog} />;
    if (page === "updates") return <UpdateCard />;

    if (page === "audit") {
      return (
        <Box>
          <SectionHead page="audit" name={AUDIT_SECTIONS[0]} />
          <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
            Every consequential action — a message routed, a verdict given, a reply sent, an agent started, a connector or setting changed —
            is one row in an append-only log. Each row carries a hash of its own contents and of the row before it, so changing history
            after the fact breaks every hash from that point on. <b>Verify</b> recomputes the chain and says whether the record you see is
            the record that was written.
            <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.audit)}
              sx={{ color: "#55697a", cursor: "pointer", ml: 0.75, "&:hover": { textDecoration: "underline" } }}>
              How to read it →
            </Typography>
          </Typography>
          <Button variant="contained" startIcon={<VerifiedIcon sx={{ fontSize: 16 }} />} onClick={runVerify}>Verify chain</Button>
          {verify && (
            <Box sx={{ mt: 2 }}>
              {verify.ok && <Typography sx={{ fontWeight: 700, fontSize: 13.5, color: "#47654a" }}>
                ✓ Intact — {verify.rows} rows verified
              </Typography>}
              {/* two different findings, and calling both "BROKEN" cried wolf about a bug in
                  store.py: a row whose CONTENTS were edited is the thing this log exists to catch,
                  and a row that two concurrent writers linked to the same parent is not. */}
              {!!verify.altered_ids?.length && (
                <Alert severity="error" sx={{ fontSize: 12.5, mb: 1 }}>
                  <b>Contents altered</b> at {verify.altered_ids.join(", ")} — {verify.altered_ids.length === 1 ? "this row does" : "these rows do"} not
                  match {verify.altered_ids.length === 1 ? "its" : "their"} own hash. This is what the log is for: something changed the record after it was written.
                </Alert>
              )}
              {!!verify.forked_ids?.length && (
                <Alert severity="warning" sx={{ fontSize: 12.5 }}>
                  <b>Out of order</b> at {verify.forked_ids.join(", ")} — nothing was altered.
                  Two writers linked to the same previous row at the same moment, which was a bug in
                  Taskuary's own writer (fixed — it cannot happen to rows written from here on).
                  The contents of every row are intact.
                </Alert>
              )}
              {!verify.ok && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
                {verify.rows} rows checked.
              </Typography>}
            </Box>
          )}
          <Box sx={{ mt: 4 }}><SectionHead page="audit" name={AUDIT_SECTIONS[1]} /></Box>
          <AuditHistory />
        </Box>
      );
    }
    return null;
  };

  /* ── searching replaces the document; the rail is always on screen either way ────── */
  if (q) return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      {!results.length ? <Empty>Nothing matches “{q}”. Try a setting, rule, or memory keyword.</Empty> : (
        <>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1 }}>
            {results.length} {results.length === 1 ? "result" : "results"}
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(2, minmax(0, 1fr))" }, gap: 1 }}>
            {results.map((r) => (
              <Box key={r.key} onClick={r.go}
                sx={{ ...card, p: 1.5, cursor: "pointer", transition: "border-color .15s, box-shadow .15s",
                  "&:hover": { borderColor: "#c8c0b3", boxShadow: "0 2px 8px rgba(47,56,64,.08)" } }}>
                <Typography sx={{ color: "#55697a", fontWeight: 650, fontSize: 13.5 }}>{r.label}</Typography>
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.35 }}>{r.crumb}</Typography>
              </Box>
            ))}
          </Box>
        </>
      )}
    </Box>
  );

  // THE DOCUMENT. Seven pages end to end, each under its own heading, and the scroll carries you
  // from one into the next - which is the whole point: scrolling off the bottom of Configuration
  // used to stop dead, with Routing policies reachable only by clicking the rail.
  return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      {NAV.map((k, i) => (
        <React.Fragment key={k}>
          <PageHead page={k} first={!i} />
          {body(k)}
        </React.Fragment>
      ))}
      <HelpDialog help={help} onClose={() => setHelp(null)} />
    </Box>
  );
}

// One page, a rail, and a search box that is always reachable. The landing grid meant every
// trip between two settings went section -> back -> section; these six are edited together.
// Docs is a SECTION here rather than a tab of its own: it is configuration you read, it sits
// where About you leaves off, and moving it in keeps the top strip symmetric about the
// Assistant now that Review is gone (the owner, 2026-09-22).
const NAV = ["about", "docs", "config", "policies", "memory", "audit", "updates"];

// DOCS IS A TREE, not a list of scroll anchors: its rail entries SWITCH the document rather than
// scrolling to a heading, because a document is not a heading you scroll past. Groups are headers
// with their files under them, and the buttons that used to sit on a shelf inside the page - New
// playbook, Manage profiles - are entries here too. Nothing about this page lives in a header any
// more (the owner, 2026-09-22: "everything moves to sidebar").
const docsTree = ({ profiles = [], playbooks = [] }) => [
  { key: "g:documents", label: "Operator documents", head: true, sel: { group: "documents" } },
  ...OPERATOR_DOCS.map((d) => ({ key: `d:${d.name}`, label: d.label, sel: { group: "documents", doc: d.name } })),
  { key: "g:profiles", label: "Profiles", head: true, sel: { group: "profiles" } },
  // by WORKER NAME, not by filename. A profile's rules document can BE an operator document -
  // the coder profile's is CODER.md - so filenames here put the same label in the rail twice,
  // under two groups, and a click landed on whichever came first.
  ...profiles.map((r) => ({ key: `p:${r.name}`, label: r.name, sel: { group: "profiles", doc: r.name } })),
  { key: "a:new-profile", label: "+ New profile", sel: { action: "new-profile" } },
  { key: "a:manage-profiles", label: "Manage profiles", sel: { action: "manage-profiles" } },
  { key: "g:playbooks", label: "Playbooks", head: true, sel: { group: "playbooks" } },
  ...playbooks.map((b) => ({ key: `b:${b.slug}`, label: b.title || b.slug, sel: { group: "playbooks", doc: b.slug } })),
  { key: "a:new-playbook", label: "+ New playbook", sel: { action: "new-playbook" } },
  // no "Import skills" entry: that road was deliberately consolidated onto the Agents panel,
  // which holds both ways in - a second door from here is the thing that was removed.
  { key: "g:how", label: "How it works", head: true, sel: { group: "how" } },
];
const sameSel = (a, b) => !!a && !!b && (a.action || "") === (b.action || "")
  && (a.group || "") === (b.group || "") && (a.doc || "") === (b.doc || "");
const RAIL = 236, GUTTER = 24;   // the rail's own width, and the grid gap beside it

export default function SettingsView({ onNavigate }) {
  const [page, setPage] = useState(NAV[0]);      // the rail's first entry is where Settings opens - About you
  // Docs' rail entries switch the document, so the selection belongs here beside `page` - and the
  // catalog they draw comes from DocsView, which already fetches and derives both lists.
  const [docSel, setDocSel] = useState({ group: "documents", doc: OPERATOR_DOCS[0].name });
  const [docCat, setDocCat] = useState({ profiles: [], playbooks: [] });
  const onCatalog = useCallback((c) => setDocCat((cur) =>
    (cur.profiles === c.profiles && cur.playbooks === c.playbooks ? cur : c)), []);
  // WHICH RAIL ENTRIES SHOW THEIR SECTIONS. The page you are in shows its own - it has to, or the
  // rail would highlight a section folded away under a title - and the rest stay shut. Scrolling
  // the whole document would otherwise leave all seven open behind you, with eleven Configuration
  // groups and the whole Docs tree among them. A chevron overrides that for its entry, and keeps
  // the override: open{} holds only what you asked for by hand.
  const [open, setOpen] = useState({});
  const [jump, setJump] = useState("");          // a section id waiting for its page to be on screen
  const [here, setHere] = useState("");          // the section the page is actually scrolled to
  const [cfgSecs, setCfgSecs] = useState(null);  // Configuration's sections, as the page reports them
  const [q, setQ] = useState("");
  // The rail draws what the page draws. Configuration's list is the page's own - a group with no
  // rows on this install is not an entry - and every other page's is fixed.
  const sectionsOf = useCallback((k) => (k === "config" && cfgSecs)
    || (k === "docs" ? docsTree(docCat) : null) || SECTIONS[k] || [], [cfgSecs, docCat]);

  // Go to a page, and to a section inside it. NOTHING SWAPS OUT, for either one: a page is a
  // place in the document exactly as a section is, so both are a scroll to an anchor. The anchor
  // may not have settled yet - the page below it is still fetching its rows - so the scroll is
  // retried until it lands or two seconds pass.
  // Picking a document DOES swap what Docs shows, and it also scrolls you to Docs, so a rail
  // click always lands on the thing you clicked. An ACTION entry (New playbook, Manage profiles)
  // carries a nonce: it is a one-shot, and without it a second click on the same entry would be
  // the same selection and nothing would reopen.
  const pickDoc = useCallback((sel) => {
    setQ(""); setPage("docs");
    setDocSel(sel.action ? { ...sel, n: Date.now() } : sel);
    setJump(pageId("docs"));
  }, []);
  const goTo = useCallback((pg, section) => {
    setQ(""); setPage(pg);
    setHere(section || "");
    setJump(section ? secId(pg, section) : pageId(pg));
  }, []);
  // LANDING ONCE IS NOT LANDING. The heading exists long before the page has stopped growing under
  // it - the AI panel fetches its brains, the rows arrive, the audit log paints - and every one of
  // those pushes the anchor back down past the top bar. So it is nudged until the heading sits
  // still where it belongs, or two seconds have gone by: smooth for the move you asked for, then
  // instant corrections, which read as the page settling rather than as a second scroll.
  useEffect(() => {
    if (!jump) return;
    let tries = 0, settled = 0, t;
    const land = () => {
      const at = sectionOffset(jump);
      if (at?.landed) settled += 1;
      else if (at && (tries === 0 || tries > 8)) { settled = 0; scrollToSection(jump, tries ? "auto" : "smooth"); }
      if (settled > 2 || ++tries > 40) { setJump(""); return; }
      t = setTimeout(land, 50);
    };
    land();
    return () => clearTimeout(t);
  }, [jump]);

  // WHERE YOU ACTUALLY ARE: the last heading that has passed under the top bar, and that heading
  // names BOTH the page and the section. The rail cannot follow the click any more - you scroll
  // out of Configuration and into Routing policies without clicking anything - so it follows the
  // document instead, and the page you are reading is the one it highlights.
  // NOT WHILE A CLICK IS STILL FLYING. The smooth scroll to Docs passes every heading between here
  // and there, and the spy named each one as it went by - so the rail folded Docs shut, opened the
  // pages in between and only opened Docs again on landing: two paints for one click (the owner,
  // 2026-09-24: "it repaints twice ... it should open the sub menu items right away"). The click
  // already said where you are going; the spy takes over again, and measures once, when it lands.
  useEffect(() => {
    if (q) { setHere(""); return; }
    if (jump) return;
    let queued = false;
    const measure = () => {
      queued = false;
      // Docs contributes its page heading and nothing else: its rail entries SWITCH the document
      // rather than scrolling to a heading, and they are objects, not heading names.
      const marks = NAV.flatMap((k) => [{ page: k, section: "", id: pageId(k) },
        ...(k === "docs" ? [] : sectionsOf(k).map((n) => ({ page: k, section: n, id: secId(k, n) })))]);
      let cur = marks[0];
      for (const m of marks) {
        const el = document.getElementById(m.id);
        if (el && el.getBoundingClientRect().top <= SCROLL_TOP + 8) cur = m;
      }
      // the last heading is too short to scroll under the bar: at the foot of the document it is
      // what you are looking at, whatever the arithmetic says about the one above it
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) cur = marks[marks.length - 1];
      setPage(cur.page); setHere(cur.section);
    };
    const onScroll = () => { if (queued) return; queued = true; requestAnimationFrame(measure); };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [q, jump, sectionsOf]);

  // #settings=<page> lands on one of the rail's pages, and &group=<section> scrolls to a section
  // inside it. The section names contain a `&` ("Triage & agents"), so a link carries them encoded
  // and they are decoded exactly once, here. The hash is read and consumed in this one place: it
  // used to be two effects in two components, and React runs the child's first, so the child
  // blanked the hash before the parent ever read it.
  useEffect(() => {
    const hash = window.location.hash || "";
    // #playbook=<slug> / #profiles come from a connector card and name no settings page. They are
    // left in place for DocsView to read; this only has to open the page that renders it.
    if (/^#(?:playbook=|profiles(?:$|=))/.test(hash)) { goTo("docs", ""); return; }
    if (!/settings=/.test(hash)) return;
    const m = /settings=([\w-]+)/.exec(hash);
    const g = /group=([^&]+)/.exec(hash);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (!m || !NAV.includes(m[1])) return;
    const want = g ? decodeURIComponent(g[1]) : "";
    goTo(m[1], (SECTIONS[m[1]] || []).includes(want) ? want : "");
  }, [goTo]);

  return (
    // THE BLOCK IS CENTRED, NOT THE PAGE INSIDE IT. Capping the page's width while the grid around
    // it stayed 1560 wide left the rail and the page glued to the left of the window with half a
    // screen of nothing beside them (the owner, 2026-09-18: "it's not centered??"). So the grid is
    // exactly rail + gutter + page and mx:auto centres the lot - and since PAGE is one number,
    // that sum never changes, which is what stops the rail drifting from page to page.
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: `${RAIL}px minmax(0,1fr)` },
      gap: 3, alignItems: "start", mx: "auto", maxWidth: RAIL + GUTTER + PAGE }}>
      <Box sx={{ position: { md: "sticky" }, top: { md: 62 }, maxHeight: { md: "calc(100vh - 74px)" }, overflowY: { md: "auto" } }}>
        <Typography id="tqSettingsRail" sx={{ color: INK, fontWeight: 700, fontSize: 16, mb: 1.5 }}>Settings</Typography>
        <TextField fullWidth placeholder="Search settings…" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ mb: 1.5, bgcolor: "#fff", borderRadius: 2 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 17, color: FAINT }} /></InputAdornment> }} />
        {/* THE RAIL IS THE MAP: a page, and under it the sections that page stacks. Eleven
            Configuration groups were a pill strip that ran off the right edge of the page, and a
            strip can only ever hold what fits across - a rail grows downward (the owner, 2026-09-18). */}
        {NAV.map((k) => {
          // the page you are in shows its sections unless you shut them yourself; the rest are
          // closed unless you opened them
          const on = !q && page === k, secs = q ? [] : sectionsOf(k), shown = k in open ? open[k] : on;
          return (
            <Box key={k}>
              <Box onClick={() => goTo(k)}
                sx={{ display: "flex", alignItems: "center", gap: 1.1, px: 1.25, height: 34, borderRadius: 1.75,
                  cursor: "pointer", fontSize: 12.5, fontWeight: on ? 600 : 400,
                  color: on ? "#41525f" : DIM, bgcolor: on ? "#eae4d8" : "transparent",
                  "&:hover": { bgcolor: on ? "#eae4d8" : "#f4f1ec" } }}>
                {React.createElement(PAGES[k].icon, { sx: { fontSize: 16 } })}
                <Box component="span" sx={{ flex: 1, minWidth: 0 }}>{PAGES[k].title}</Box>
                {!!secs.length && (
                  <ExpandMoreIcon titleAccess={`${shown ? "hide" : "show"} ${PAGES[k].title}'s sections`}
                    onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [k]: !shown })); }}
                    sx={{ fontSize: 17, color: FAINT, transition: "transform .15s", transform: shown ? "none" : "rotate(-90deg)",
                      "&:hover": { color: INK } }} />
                )}
              </Box>
              {shown && secs.map((raw) => {
                // a string is a SECTION (a place on one long page); an object is a docs entry,
                // which switches what the page shows instead of scrolling it
                const e = typeof raw === "string" ? { key: raw, label: raw, section: raw } : raw;
                const at = on && (e.section ? here === e.section : sameSel(docSel, e.sel));
                return (
                  <Box key={e.key} onClick={() => (e.section ? goTo(k, e.section) : pickDoc(e.sel))}
                    sx={{ ml: e.head ? 1.5 : 2.5, pl: 1.25, pr: 0.75, py: e.head ? 0.6 : 0.45, cursor: "pointer",
                      fontSize: 12, lineHeight: 1.35, mt: e.head ? 0.75 : 0,
                      borderLeft: e.head ? "none" : `2px solid ${at ? ACCENT2 : BORDER}`,
                      color: at ? "#41525f" : e.head ? "#55697a" : DIM,
                      fontWeight: at ? 650 : e.head ? 700 : 400,
                      letterSpacing: e.head ? ".02em" : 0,
                      "&:hover": { color: "#41525f", borderLeftColor: at ? ACCENT2 : "#c8c0b3" } }}>
                    {e.label}
                  </Box>
                );
              })}
            </Box>
          );
        })}
        <Typography variant="caption" sx={{ color: FAINT, display: "block", pt: 2, px: 1.25, lineHeight: 1.6 }}>
          Everything here is stored locally, in the same SQLite file as your tasks.
        </Typography>
        {/* the one link out to the docs, and it is here because this is where someone already is
            when they are looking a setting up (taskuary.com/docs/settings is generated from the
            same settings_schema.json this page draws from, so it can never describe another app) */}
        <Typography variant="caption" sx={{ color: FAINT, display: "block", pt: 1, px: 1.25 }}>
          <Box component="a" href="https://taskuary.com/docs/settings" target="_blank" rel="noreferrer"
            sx={{ color: "#55697a", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>
            Full documentation →
          </Box>
        </Typography>
      </Box>
      {/* every page carries its own heading now (PageHead), because there is no longer a
          "current page" for one heading up here to name - there is a document, and you are
          somewhere in it */}
      <Box sx={{ minWidth: 0 }}>
        <SettingsPages q={q} setQ={setQ} onNavigate={onNavigate} onJump={goTo} onSections={setCfgSecs}
          docSel={docSel} setDocSel={setDocSel} onCatalog={onCatalog} />
      </Box>
    </Box>
  );
}


// The log itself, newest first - the page used to be one button and a sentence, and nobody could
// tell what it was a log OF. Who is said in words: you, the router, an agent, a scheduled report.
const ACTOR_LABEL = { owner: "you", router: "the router", triage: "triage", report: "a report", system: "the app", startup: "startup", "connector-test": "a Test", msauth: "sign-in" };
// WHAT THE ASSISTANT CHANGED. An instant write from the chat (a setting, a report's clock, a
// connection switched off) is always visible here and, while it still applies, reversible with one
// click - the tiers' promise, kept on the page that owns the knobs (2026-09-18). Hidden when empty.
const AssistantChanges = () => {
  const [rows, setRows] = useState([]);
  const [undo, setUndo] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/api/audit/assistant", { params: { limit: 8 } }); setRows(data.data || []); setUndo(data.undo || null); }
    catch { /* the list is a nicety */ }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!rows.length) return null;
  const said = (r) => {
    const d = r.detail || {};
    if (r.entity === "setting") return `${d.key}: ${d.from ?? "(blank)"} → ${d.to}`;
    if (r.entity === "source") return `${r.action} · ${d.title || `report ${r.id}`}${d.to ? ` → ${d.to}` : ""}${d.changed ? ` (${d.changed.join(", ")})` : ""}`;
    if (r.entity === "connector") return `${r.action.replace("_", " ")} · ${d.name || `connection ${r.id}`}`;
    return `${r.entity} ${r.action}`;
  };
  const revert = async () => {
    setBusy(true);
    try { await api.post(`/api/operations/${undo.id}/execute`, { version: undo.version }); await load(); }
    catch { /* the receipt in the chat says why */ } finally { setBusy(false); }
  };
  return (
    <Box sx={{ ...card, mb: 2, px: 1.5, py: 1.1, borderLeft: "4px solid #6f8a6e" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ ...mono, fontSize: 10, fontWeight: 750, letterSpacing: 1.2, color: ACCENT2, flex: 1, textTransform: "uppercase" }}>What the assistant changed</Typography>
        {undo && <Button size="small" variant="outlined" disabled={busy} onClick={revert} sx={{ fontSize: 11, minHeight: 26, py: 0 }}>{busy ? "Undoing…" : "Undo the last change"}</Button>}
      </Box>
      {rows.map((r, i) => (
        <Typography key={i} variant="body2" sx={{ fontSize: 12, color: INK, mt: 0.4 }}>
          <Box component="span" sx={{ color: FAINT, mr: 1 }}>{String(r.when || "").slice(0, 16)}</Box>{said(r)}
        </Typography>
      ))}
    </Box>
  );
};

const AuditHistory = () => {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/api/audit/recent", { params: { limit: 300 } }).then(({ data }) => setRows(data.data || [])).catch(() => setRows([])); }, []);
  if (rows === null) return <CircularProgress size={16} sx={{ display: "block", mt: 3 }} />;
  const hit = (r) => !q || `${r.Actor} ${r.Action} ${r.EntityType} ${r.EntityId} ${r.Detail || ""}`.toLowerCase().includes(q.toLowerCase());
  const shown = rows.filter(hit);
  const who = (r) => ACTOR_LABEL[r.Actor] || r.Actor || r.ActorType || "?";
  return (
    <Box sx={{ mt: 3 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, mb: 1 }}>
        <Typography sx={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT }}>LAST {rows.length} ACTIONS</Typography>
        <Box sx={{ flex: 1 }} />
        <TextField size="small" placeholder="filter — a task id, an action, a word" value={q} onChange={(e) => setQ(e.target.value)}
          sx={{ width: 280, bgcolor: "#fff" }} inputProps={{ style: { fontSize: 12, padding: "5px 9px" } }} />
      </Box>
      {!shown.length && <Empty>Nothing matches.</Empty>}
      {shown.map((r) => (
        <Box key={r.Id} sx={{ display: "grid", gridTemplateColumns: "150px 110px 150px minmax(0, 1fr) 70px", gap: 1.5, alignItems: "baseline", py: 0.75, borderBottom: `1px solid ${BORDER}` }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10.5 }}>{String(r.CreatedAt || "").slice(0, 16)}</Typography>
          <Typography variant="caption" sx={{ color: r.ActorType === "human" ? "#47654a" : DIM, fontWeight: 600 }}>{who(r)}</Typography>
          <Typography variant="caption" sx={{ color: INK, fontWeight: 700 }}>{String(r.Action || "").replace(/_/g, " ")}</Typography>
          <Typography variant="caption" sx={{ color: DIM, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.Detail || ""}>
            {r.EntityType}{r.EntityId ? ` ${r.EntityType === "task" ? `TQ-${String(r.EntityId).padStart(4, "0")}` : `#${r.EntityId}`}` : ""}
            {r.Detail ? ` — ${typeof r.Detail === "string" ? r.Detail : JSON.stringify(r.Detail)}` : ""}
          </Typography>
          <Typography variant="caption" sx={{ ...mono, color: "#cfc9bf", fontSize: 9.5 }} title={`row hash ${r.RowHash || ""}`}>{String(r.RowHash || "").slice(0, 8)}</Typography>
        </Box>
      ))}
    </Box>
  );
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

// The two knobs above are mute until a chat is actually named. Say so here, rather
// than leaving the page looking like a finished setup that silently goes nowhere.
const NotifyStatus = ({ connectors, settings }) => {
  const val = (n, d) => (settings.find((s) => s.Name === n) || {}).Value ?? d;
  const st = notifyState(connectors, val("notify_level", "needs_me"), val("phone_approvals") === "1",
    val("phone_assistant") === "1");
  const good = st.kind === "pinging", warn = st.kind === "none" || st.kind === "unnamed" || st.kind === "inactive";
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, mb: 1.5, mt: -0.5, px: 1.25, py: 0.85,
      bgcolor: good ? "#dfeade" : warn ? "#eae4d8" : "#f4f1ec",
      border: `1px solid ${good ? "#c8d9c7" : warn ? "#d8cfbe" : BORDER}`, borderRadius: 1.5 }}>
      {st.targets[0] && <ChannelIcon channel={st.targets[0].Type} sx={{ fontSize: 15, mt: 0.15 }} />}
      <Typography variant="caption" sx={{ color: good ? "#47654a" : warn ? "#55697a" : DIM, lineHeight: 1.45 }}>{st.text}</Typography>
    </Box>
  );
};
