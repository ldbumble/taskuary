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
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { SOUNDS, playSound } from "./handraise.js";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SearchIcon from "@mui/icons-material/Search";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import VerifiedIcon from "@mui/icons-material/Verified";
import TuneIcon from "@mui/icons-material/Tune";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import PsychologyIcon from "@mui/icons-material/Psychology";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import { AgentsPage } from "./AgentsPanel.jsx";
import AboutYou from "./AboutYou.jsx";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, mono, ACTION_COLORS } from "./theme.jsx";
import { ChannelIcon, Empty, FilterPills } from "./ui.jsx";
import { notifyState } from "./notify.js";


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
  reply_channels: { group: "Replies", label: "Draft replies on", type: "channels",
    options: ["email", "teams", "slack", "telegram", "whatsapp", "imessage", "discord", "github"],
    desc: "Which channels get a drafted reply at all. Switch one off and its questions just file.",
    help: "A question arriving somewhere you never answer from should not open a reply task whose draft has nowhere to go. Turn a channel off and messages from it still land on the Timeline and can still become real tasks — they simply never get a draft, and the funnel says so in the row's reason ('replies are off for slack').\n\nOne answer for the whole app: triage uses it to decide whether a question becomes a reply task, the coder wrap-up uses it to decide whether to draft at all, and the Review buttons use it to decide whether Approve can actually send. They cannot disagree.\n\nTwo rules are not yours to change here: GitHub also needs 'Reply to issue/PR authors' on its own card (a reply there is a PUBLIC comment), and the read-only trackers — Jira, Linear, Sentry, PagerDuty and friends — can never carry a reply because Taskuary only reads them." },
  calendar_enabled: { group: "Replies", label: "Check your calendar when a reply is about time", type: "switch",
    desc: "\"Tuesday at 1 works for me\" is only drafted if Tuesday at 1 is free. Reads the Outlook card's calendars (needs the Calendars.Read application permission) and a Google calendar if its OAuth fields are on the Gmail card.",
    help: "When the thread mentions a day, a time, a meeting or availability, the responder fetches your busy slots for the next 14 days and is told: never offer a busy time; if the asked time is busy, say so and offer the nearest free one; if the calendar could not be read, say you will confirm. The task gets a note that the calendar was checked.\n\nAgents can read the same thing: POST /api/tools/run with type \"calendar\"." },
  counsel_enabled: { group: "Replies", label: "Assistant brief on every judged message", type: "switch",
    desc: "After triage, the assistant reads the message against what it already knows — this sender's recent mail, what you last wrote them, the topic elsewhere, open tasks, your calendar — and leaves a short opinionated brief on the panel. Invites get a prep note. Voice and rules: COUNSEL.md on the Docs tab.",
    help: "One extra AI call per message a model judged (never for automated noise the keyword pass filed). The brief is private and never sent anywhere; when it names something to get ahead of, or a task you may not see, it is also pushed to your notify channel. A suggested task is one click away on the panel and never opens itself. Replies read the same history, so a draft no longer forgets what the same person asked last week. Off: no briefs, drafts still read the history." },
  auto_draft_enabled: { group: "Replies", label: "Draft replies automatically", type: "switch",
    desc: "Questions get their AI draft the moment they arrive, waiting in Review.",
    help: "On: a message triaged as a question lands in Review with the reply already written — you edit or just Approve & send. Off: questions still queue in Review, but empty; you click 'Draft with AI' per item.\n\nNothing sends itself either way — approving is always yours. Turning this off is also the cheapest way to pause AI spending." },
  outlook_drafts_enabled: { group: "Replies", label: "Outlook drafts on approve", type: "switch",
    desc: "Approved Outlook replies are also saved as reply-all DRAFTS in the mailbox.",
    help: "For the belt-and-braces workflow: on approval, the reply is additionally created as a reply-all draft inside the source mailbox via Graph (needs the Mail.ReadWrite consent), so you can give it one last look in Outlook and hit Send there. Failures land in the audit log, never block the approval." },
  send_enabled: { group: "Replies", label: "(legacy, unused)", type: "switch",
    desc: "Kept only for old databases — has no effect. Leave off.",
    help: "An earlier design had a separate send gate. Sending is now simply what Approve & send does, so this switch controls nothing." },

  // ── Assistant: the voice on the Timeline (assistant.py) ──
  assistant_enabled: { group: "Assistant", label: "The assistant posts on the Timeline", type: "switch",
    desc: "On its own clock it says what it noticed: the reply you sent and never heard back on, the meeting coming up and what came before it, the task gone quiet, its own ideas from the day's mail — one row, each line with its buttons.",
    help: "One AI call per post, and none when there is nothing new. Every line has a key and a state, so it never says the same thing twice: dismissed stays dismissed until the facts change, snoozed sleeps. 'Follow up' drafts the chase in your voice into Review — nothing is sent by itself; 'Make it a task' starts the agent; 'Not this' teaches LEARNED.md which nudges you never want. Voice and rules: COUNSEL.md → The post (Docs tab). Without an AI connector the facts still post, in the hub's own words." },
  assistant_every_minutes: { group: "Assistant", label: "Minutes between posts", type: "number",
    desc: "How often it looks — it posts only when something is new. 60 by default.",
    help: "The clock rides the background sync (Sync & startup → poll interval), so a value under that interval means 'every sync'. 'Ask now' on the status card posts regardless of the clock." },
  assistant_followup_hours: { group: "Assistant", label: "Silence before a follow-up", type: "number",
    desc: "Hours after your last reply on a thread — one that asked for or promised something — before 'no answer yet, follow up?' appears. 24 by default.",
    help: "Only your own last word counts, and only when it asked or promised something ('could you send', 'by Friday', a question mark). A plain thanks that goes unanswered is not a follow-up. The chase itself is drafted only when you click." },
  assistant_cold_days: { group: "Assistant", label: "Quiet days before a task has 'gone cold'", type: "number",
    desc: "Open work with no comment, message or run for this many days gets a line. 3 by default.",
    help: "A task with a live agent on it is never cold. One with a draft waiting in Review is named as waiting on you." },
  assistant_card: { group: "Assistant", label: "Status card at the top of the Timeline", type: "switch",
    desc: "One quiet line: agents working, tasks waiting on you, drafts to review, the next meeting — and 'ask now'. Status, not advice: the recommendations are the rows.",
    help: "Off hides the card; the posts keep coming. The card refreshes every minute while the tab is visible." },
  assistant_producers: { group: "Assistant", label: "What it looks for", type: "channels", options: ["followup", "prep", "cold", "ahead", "idea"],
    desc: "followup = your unanswered asks · prep = meetings in the next two days, with what came before them · cold = tasks gone quiet · ahead = what a brief said would bite later · idea = the model's own thoughts from the day's mail.",
    help: "Switch a kind off and it never appears in a post again; lines already posted keep their buttons. 'idea' is the only one that needs an AI connector — the others are read straight off the hub's own tables and your calendar. With 'idea' off no model is called at all: the facts post in the hub's own words." },

  // ── Coder agent: who works the tasks, and how eagerly ──
  default_agent: { group: "Coder agent", label: "Default agent", type: "agent",
    desc: "The CLI agent that works tasks when nothing names one.",
    help: "Start session, Send to coding agent and auto-dispatch all use this agent unless you pick another in the moment; every agent picker lists it first. The roster itself lives under Connectors → AI CLI agents, where the default row wears the star.\n\nGitHub-specific permissions (may agents open issues? push?) are on the GitHub connector card, because they are decisions about how your team uses GitHub, not about Taskuary." },
  answer_to_agent: { group: "Coder agent", label: "Hand answers to the working agent", type: "select",
    options: ["ask", "auto", "off"],
    desc: "When someone answers a question on a task an agent is sitting on, their answer can go straight into the live session.",
    help: "The classic round trip: the agent asks something mid-task, the hub asks the person, the person replies by mail or chat — and the reply attaches to the same task.\n\nask (default) = the review panel offers one click: 'Type this into the agent's session'. auto = the answer is typed into the live session the moment it arrives, as if you relayed it. off = it just lands on the task; you paste it yourself.\n\nOnly a LIVE session is ever typed into — if the agent already exited, nothing happens and the thread simply waits on the task." },
  git_flow: { group: "Coder agent", label: "How finished work lands", type: "select", options: ["pr", "direct"],
    desc: "A draft pull request, or the commits pushed straight onto the default branch.",
    help: "pr (default) = a DRAFT pull request from the task's branch; you review and merge it yourself, and Taskuary never merges. direct = the commits already in the checkout are pushed straight onto the default branch — no PR, no review ceremony, which is usually what you want on your own repository.\n\nDirect mode is deliberately narrow: it pushes commits that ALREADY EXIST. A dirty checkout is refused rather than committed for you (Taskuary will not write a commit message over work nobody has read), nothing ahead of the remote is simply 'nothing to do', and a rejected push is reported for you to pull and rebase — it never force-pushes.\n\nEither way 'Agents may push / deploy' on the GitHub card is what allows anything to leave the machine at all, and CI watching follows the work to wherever it landed." },
  ci_watch: { group: "Coder agent", label: "Watch CI on the task's pull request", type: "select",
    options: ["off", "feedback", "watch"],
    desc: "A red build goes back to the agent that wrote the code, with the failing check named.",
    help: "Once a task has a draft pull request (open it from the task, or let the agent propose one), every sync refreshes its checks.\n\nfeedback = a failing build is typed into the live session — 'these checks failed, fix the cause and push again, do not merge' — and recorded on the task; if no session is live the task returns to 'open' so it lands on you. watch = the state is shown on the proof card but nothing is handed back. off (default) = no polling at all.\n\nEach distinct failure reaches the agent ONCE per commit, never on every poll. Taskuary opens drafts and never merges." },
  proposals_enabled: { group: "Coder agent", label: "Agents may propose actions", type: "switch",
    desc: "An agent can ASK to open a PR, comment publicly, close an issue or run a tool — each waits for your approval.",
    help: "High-impact actions come off the auto-approve road entirely. Instead of doing them, the agent writes a typed proposal in its transcript (TASKUARY-PROPOSE {\"action\": \"open_pr\", …}); when the session wraps up, each valid one becomes a pending review saying what it wants and why. Approving RUNS it; rejecting does nothing.\n\nEvery proposal is re-validated at execution, so approving never grants a permission you have switched off — an open_pr proposal still needs 'Agents may push / deploy', a public comment still needs the GitHub card's reply switch. Malformed or unpermitted proposals are refused and recorded on the task rather than dropped silently." },
  waitroom_drip: { group: "Coder agent", label: "Tell-the-agent notes land one per stop", type: "switch",
    desc: "On: a queue of prompts drips in - each time the agent stops, the next one is typed in, the rest wait their turn. Off: everything queued goes in as one batch.",
    help: "The waiting room is a funnel: paste twenty prompts and each becomes its own note, in order. With the drip on, the agent gets one at a time with its full attention - it is told how many wait behind it and that the next comes when it stops again, so it never goes looking. Turn it off to hand over the whole list in one message instead." },
  coder_auto_enabled: { group: "Coder agent", label: "Auto-dispatch new tasks", type: "switch",
    desc: "Every new task immediately opens a live agent session - coding or not. The agent does what a keyboard can do, or says 'nothing to do here'.",
    help: "On: the moment triage says 'this is work' your CLI opens in the task's repository (picked from the SOUL.md repo map) with the full ask seeded: visible on the Board, watchable, interruptible. That includes work with no code in it - chase a vendor, add a user, produce a document - because an agent that looks and stops is cheap and a job sitting on a list is not. Only plain questions (a reply is drafted instead) and notices (filed) stay out of it. Off: tasks queue as 'needs you' and you press Start session yourself.\n\nA first-time sender from outside your domains never starts an agent by itself - the task lands, you press the button. Requires the CLI installed and signed in on this machine. Nothing ships or sends without your approval either way." },
  agent_hooks: { group: "Coder agent", label: "Let Claude Code tell the Board what it is doing", type: "switch",
    desc: "A Claude Code hook in each checkout a session opens reports every tool call and stop to Taskuary - the Board card reads 'Edit server.py · 4s' and the agent's own list instead of a scrollback.",
    help: "How: Taskuary adds PostToolUse, Stop and UserPromptSubmit entries to the checkout's .claude/settings.local.json (the project-local file Claude Code itself keeps out of git). Each entry pipes the event's JSON to this server on localhost with curl; nothing leaves the machine and nothing changes what the agent does. Existing hooks in that file are kept.\n\nCodex needs no hook: Taskuary follows the session log Codex writes as it works. Other CLIs show the last screen line and the files git says they touched.\n\nOff: no file is written; cards fall back to files only." },
  auto_sessions: { group: "Coder agent", label: "Agents at once", type: "number",
    desc: "How many unattended agent sessions may run together. The rest queue.",
    help: "The one number that decides how much work this machine takes on at once. Four is the default because four live CLI sessions in four checkouts is about what a laptop stays responsive under — each one is a real process with a real model behind it.\n\nPast the limit nothing is dropped: a dispatched task joins the queue and starts the moment a session ends, and the Board shows it waiting with the reason. The Board's floor view is drawn to this number, so raising it widens the room instead of crowding it.\n\nRaise it if the machine has headroom and your tasks rarely touch the same files; lower it to one if you would rather watch a single agent at a time. Sessions you start yourself are never blocked by this." },
  notify_level: { group: "Notifications", label: "Push to your chat", type: "select", options: ["needs_me", "all", "off"],
    optionLabels: { needs_me: "needs me", all: "everything", off: "off" },
    desc: "Ping a Telegram / WhatsApp / Teams chat instead of you watching the tab.",
    help: "Give a chat connector the Notifications role (its Role step) and name the chat in its config; this decides what gets pushed there.\n\nneeds me (default) = only what is genuinely waiting on YOU: a question to answer, a task nobody was dispatched at, and — the one that matters — 'the work is done, the reply is drafted and waiting in Review'. everything = every new timeline item. off = never push.\n\nEvents that happened in the notify chat itself are never echoed back into it, so one channel can safely be both input and output." },

  hand_sound: { group: "Notifications", label: "Sound when an agent raises its hand", type: "sound",
    desc: "A session that stops at its prompt, or asks you a question, plays this - from any tab. Off silences it.",
    help: "The moment worth a sound: the thing you delegated is now waiting on you. It fires once, on the transition from working to waiting, never while you already have the task open in front of you. Sounds are synthesised in the browser - nothing to download.\n\nThe desktop notification below is separate: it is the browser's own, so it reaches you when Taskuary is behind other windows, and the first time it asks for permission." },
  hand_desktop: { group: "Notifications", label: "Desktop notification when an agent raises its hand", type: "switch",
    desc: "The browser's notification, so it reaches you when Taskuary is behind other windows. Click it to jump to the task." },
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
  poll_minutes: { group: "Sync & startup", label: "Background sync (minutes)", type: "number",
    desc: "How often the app checks your connections while it is open. 0 turns it off.",
    help: "The server keeps this clock, so it runs whichever tab you are on and whether or not you are looking at the app - it is also what makes a SCHEDULED REPORT fire on time, since reports are checked on the same pass.\n\nIt used to live in the Timeline tab instead: the countdown died the moment you opened Board or Tasks, restarted itself every time you changed a filter, and with the window closed nothing polled at all - so a report set for 8am Monday only ran if somebody happened to be sitting on the Timeline at 8am on Monday.\n\n10 is the default. Lower it if you want mail sooner and do not mind the API calls; 0 turns background polling off entirely and leaves Sync now as the only road." },
  startup_sync_days: { group: "Sync & startup", label: "Catch-up window (days)", type: "number",
    desc: "How far back the app reaches when it opens, for what arrived while it was closed.",
    help: "Taskuary is a window you open, not a service — at 5:30am it is closed, so 'anything since I last polled' misses the weekend. On startup every trigger connection is asked for this many days; the window only ever WIDENS (a source last polled a month ago is not pulled forward), and duplicates are never re-ingested.\n\nThe Timeline shows the catch-up running and refreshes when it lands. The daily DIGEST.md synthesis runs right after it. 0 = plain incremental poll on startup." },

  mark_read_enabled: { group: "Sync & startup", label: "Mark items read at the source", type: "switch",
    desc: "Once the funnel has taken a message in, mark it read where it came from — the mail seen, the chat read.",
    help: "Off (default): Taskuary is a pure reader — your inbox still shows every message bold, so nothing about your mailbox changes because you connected it. On: anything the funnel ingests is marked read at the source, so the bold rows left over are exactly the ones the hub never saw.\n\nWHERE IT APPLIES: Outlook mail (needs the Mail.ReadWrite consent), Gmail/IMAP mailboxes (the \\Seen flag), Slack channels (the read cursor moves to the newest line taken), Teams (Graph marks the whole CHAT read — there is no per-message read state there) and WhatsApp (blue ticks, via the bridge).\n\nWHERE IT CANNOT: Telegram and Discord bots have no read state to set, and the trackers — Jira, Linear, GitHub, Sentry and friends — have nothing to mark. The switch is simply a no-op for them.\n\nMarking always runs AFTER the message is safely stored and is best-effort: a refused permission is logged and never costs you the ingest." },

  // ── Display ──
  timezone: { group: "Display", label: "Timezone", type: "timezone",
    desc: "The zone the app's clock speaks. Blank = this machine's local time.",
    help: "Timestamps are stored in the server machine's local time. Name that zone here and every displayed time wears its label (2:44 PM EDT) — and a browser opened from another timezone still reads the stamps correctly instead of silently reinterpreting them in its own zone.\n\nUse an IANA name (America/New_York, Europe/London, Asia/Jerusalem). Takes effect on the next page load." },
  feed_days: { group: "Display", label: "Timeline lookback (days)", type: "number",
    desc: "How many days the Timeline shows. Display only — nothing is deleted.",
    help: "Purely the Timeline's window. Older messages stay in the database, in task histories, and in search." },
};
const GROUPS = ["Triage & routing", "Replies", "Assistant", "Coder agent", "Notifications", "Attachments & images", "Sync & startup", "Display", "Other"];
// Internal state, and settings that live on another page - never shown as knobs. The "Other" tab
// used to catch every bookkeeping value the server ever wrote (digest_report_seeded, task_id_mark,
// learn_pending, owner_bio...), each with a switch that did something nobody could predict.
const HIDDEN = new Set(["ingest_status", "agent_issues_enabled", "agent_push_enabled",   // github card decisions
                        "last_pinged_review", "triage_last_error",                          // bookkeeping
                        "setup_dismissed", "task_id_mark", "learn_pending", "learn_last_reflect"]);
const hidden = (name) => HIDDEN.has(name) || name.startsWith("owner_") || name.endsWith("_seeded");   // owner_* = About you
const meta = (name) => KNOB_META[name] || { group: "Other", label: name, type: "auto" };

const SECTION_HELP = {
  policies: { title: "Routing policies — the deterministic layer",
    body: "Rules evaluated BEFORE any AI touches a message; no model confidence can override them. Precedence: ignore > escalate > auto_answer > draft > task_only — within one action, lowest order number wins.\n\nKINDS: keyword (pipe-separated substrings matched against subject+body), sender (exact addresses), sender_domain (domains), noreply (built-in matcher for automated addresses), first_time_sender (fires when the address has never been seen).\n\nACTIONS: ignore (no task, message stays visible in the feed), escalate (a human always decides, and the task is marked urgent - this is the ONLY thing that marks one urgent, so name the senders whose mail jumps your queue), auto_answer (the draft is auto-approved — still never sent), draft (targeted default), task_only (file it, no reply).\n\nWhen you hit 'Not a task', a sender ignore rule is added here automatically — the learning loop writes into this table." },
  memory: { title: "Verdicts & notes — the evidence behind LEARNED.md",
    body: "Two layers, one loop. LEARNED.md (Docs tab) is the GENERAL profile — your style, your responsibilities, what deserves a task — and it is written by a nightly pass. This page is the EVIDENCE that pass reads: one dated line per verdict you gave ('Not our task' on this subject from this sender, 'Not a task' on that one) plus notes you type yourself, each tied to a sender, a domain, a subject, or everyone.\n\nWhen a new message arrives, the lines that bear on it (same sender, same topic) ride into triage and into the reply draft, and the model judges how alike the new message really is — the same sender asking the same thing is binding, a shared word is not. The general lessons in LEARNED.md are distilled from these same lines under a stricter rule (LEARNED.md → Verdicts lists which ones fed which lesson).\n\nSo nothing was removed: LEARNED.md is what it concluded, this is what it concluded it from. Toggle off a line learned wrong — it stays for the record and is never injected again; the next distillation drops it too." },
  audit: { title: "Audit integrity — what the log is, and how to read it",
    body: "Every consequential thing Taskuary does is one row in an append-only log: a message routed or filed and why, a verdict you gave, a reply sent, an agent session opened or wrapped, a connector saved or signed in, a setting changed, a task deleted. Each row stores a hash of its own contents PLUS the hash of the row before it, so the rows form a chain: change any row after the fact — even one character in the database — and its hash no longer matches, and every row after it points at a parent that no longer exists.\n\nVerify recomputes the whole chain from the first row. Intact means the record you see is the record that was written. 'Contents altered' names the exact rows that were changed after writing — the thing this log exists to catch. 'Out of order' means two writers raced at the same instant once; nothing was changed, and it cannot recur.\n\nThe history below is that log, newest first: when, who (you, the router, an agent, a scheduled report), what was done, to what. It is the answer to 'why did this happen' and 'who did this' for anything on the Timeline or the Board." },
};

const PAGES = {
  about: { title: "About you", icon: AccountCircleIcon, desc: "Who the system knows you are — your identities per channel, the facts only you can add, your avatar." },
  config: { title: "Configuration", icon: TuneIcon, desc: "Triage, drafting, coder and display knobs — how the funnel behaves." },
  policies: { title: "Routing policies", icon: AltRouteIcon, desc: "Deterministic rules the AI can never override — ignores, escalations, auto-answers." },
  memory: { title: "Verdicts & notes", icon: PsychologyIcon, desc: "The evidence behind LEARNED.md — every verdict you gave, one line each, plus notes you write. Toggle off what it learned wrong." },
  agents: { title: "Agents", icon: SmartToyIcon, desc: "Bring your own AI CLI — cmd, args, resumable sessions, repo → checkout map." },
  audit: { title: "Audit integrity", icon: VerifiedIcon, desc: "Who did what, when — a tamper-evident record of every action, and a button that proves nobody edited it." },
};

function SettingsPages({ page, setPage, q, setQ }) {
  const [policies, setPolicies] = useState(null);
  const [settings, setSettings] = useState([]);
  const [memory, setMemory] = useState([]);
  const [newNote, setNewNote] = useState(null);
  const [draft, setDraft] = useState(null);
  const [verify, setVerify] = useState(null);
  const [help, setHelp] = useState(null);
  const [cfgTab, setCfgTab] = useState("Triage & routing");
  const [err, setErr] = useState("");

  const [brains, setBrains] = useState([{ value: "", label: "auto — first active AI connector", ready: true }]);
  const [agentNames, setAgentNames] = useState([]);
  const [connectors, setConnectors] = useState([]);

  const load = useCallback(async () => {
    try {
      const [p, s, m] = await Promise.all([api.get("/api/policies"), api.get("/api/settings"), api.get("/api/memory")]);
      setPolicies(p.data.data || []); setSettings(s.data.data || []); setMemory(m.data.data || []);
      api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {});
      api.get("/api/agents").then(({ data }) => setAgentNames((data.data || []).map((a) => a.Name))).catch(() => {});
      api.get("/api/connectors").then(({ data }) => setConnectors(data.data || [])).catch(() => {});
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load settings"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const savePolicy = async (p) => { await api.post("/api/policies", p); setDraft(null); load(); };
  const togglePolicy = async (p) => { await api.post("/api/policies", { PolicyId: p.PolicyId, Active: !p.Active }); load(); };
  const deletePolicy = async (p) => { await api.delete(`/api/policies/${p.PolicyId}`); load(); };
  const saveSetting = async (name, value) => { await api.patch("/api/settings", { name, value }); load(); };
  const toggleMemory = async (m) => { await api.patch(`/api/memory/${m.MemoryId}`, { active: !m.Active }); load(); };
  const addNote = async () => { await api.post("/api/memory", newNote); setNewNote(null); load(); };
  const runVerify = async () => setVerify((await api.get("/api/audit/verify")).data);

  // Deep search: every hit knows which page (and tab) it lives on and jumps there.
  const hit = (...parts) => parts.join(" ").toLowerCase().includes(q.toLowerCase());
  const results = !q ? [] : [
    ...settings.filter((s) => { if (hidden(s.Name)) return false; const m = meta(s.Name); return hit(s.Name, s.Description, m.label, m.desc, m.help, m.group); })
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
    // a csv of channels: chips you toggle, which is what "which of these" actually is -
    // a comma-separated text field asked the owner to spell channel names correctly
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

  if (!policies) return <CircularProgress size={22} sx={{ m: 4 }} />;

  /* ── detail pages ─────────────────────────────────────────────────────── */
  if (page === "config") {
    const rows = settings.filter((s) => !hidden(s.Name) && meta(s.Name).group === cfgTab);
    const tabs = GROUPS.filter((g) => settings.some((s) => meta(s.Name).group === g));
    return (
      <Box>
        {/* the segmented pill bar, same as Reports and the Timeline - the old underlined tab
            strip was the one place in the app still wearing a different header */}
        <Box sx={{ mb: 2 }}><FilterPills options={tabs} value={cfgTab} onChange={setCfgTab} /></Box>
        {cfgTab === "Notifications" && <NotifyStatus connectors={connectors} settings={settings} />}
        {rows.map((s) => {
          const m = meta(s.Name);
          return (
            <Box key={s.Name} sx={{ display: "flex", alignItems: "center", gap: 3, py: 2.5, borderBottom: `1px solid ${BORDER}`,
              opacity: s.Name === "phone_approvals" && (settings.find((x) => x.Name === "notify_level") || {}).Value === "off" ? 0.5 : 1 }}>
              <Box sx={{ flex: 1, minWidth: 0, cursor: m.help ? "pointer" : "default" }}
                onClick={() => m.help && setHelp({ title: m.label, body: m.help })}>
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                  {m.label}
                  {m.help && <HelpOutlineIcon sx={{ fontSize: 15, color: "#cfc9bf" }} />}
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
      <Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Typography variant="body2" sx={{ color: DIM }}>
            Deterministic gates the AI can never override.
            <Typography component="span" variant="body2" onClick={() => setHelp(SECTION_HELP.policies)}
              sx={{ color: "#55697a", cursor: "pointer", ml: 0.75, "&:hover": { textDecoration: "underline" } }}>
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
            <IconButton size="small" title="Delete this rule" onClick={() => deletePolicy(p)}><DeleteOutlineIcon sx={{ fontSize: 16 }} /></IconButton>
          </Box>
        ))}
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
        <HelpDialog help={help} onClose={() => setHelp(null)} />
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
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  if (page === "about") return <AboutYou />;

  if (page === "agents") {
    return <AgentsPage onBack={() => setPage(null)} />;
  }

  if (page === "audit") {
    return (
      <Box>
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
        <AuditHistory />
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
        <HelpDialog help={help} onClose={() => setHelp(null)} />
      </Box>
    );
  }

  /* ── search results, or nothing: the rail is always on screen now ────── */
  return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      {!results.length && <Empty>Nothing matches.</Empty>}
      {results.map((r) => (
        <Box key={r.key} onClick={r.go} sx={{ py: 1.25, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
          "&:hover": { bgcolor: "#f4f1ec" } }}>
          <Typography sx={{ color: "#55697a", fontWeight: 600, fontSize: 13.5 }}>{r.label}</Typography>
          <Typography variant="caption" sx={{ color: FAINT }}>{r.crumb}</Typography>
        </Box>
      ))}
    </Box>
  );
}

// One page, a rail, and a search box that is always reachable. The landing grid meant every
// trip between two settings went section → back → section; these five are edited together.
const NAV = ["about", "config", "policies", "memory", "agents", "audit"];

export default function SettingsView() {
  const [page, setPage] = useState(NAV[0]);      // the rail's first entry is where Settings opens - About you
  const [q, setQ] = useState("");
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "236px minmax(0,1fr)" },
      gap: 3, alignItems: "start", maxWidth: 1320, mx: "auto" }}>
      <Box sx={{ position: { md: "sticky" }, top: { md: 62 } }}>
        <Typography sx={{ color: INK, fontWeight: 700, fontSize: 16, mb: 1.5 }}>Settings</Typography>
        <TextField fullWidth placeholder="Search settings, rules, memory…" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ mb: 1.5, bgcolor: "#fff", borderRadius: 2 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 17, color: FAINT }} /></InputAdornment> }} />
        {NAV.map((k) => {
          const on = !q && page === k;
          return (
            <Box key={k} onClick={() => { setQ(""); setPage(k); }}
              sx={{ display: "flex", alignItems: "center", gap: 1.1, px: 1.25, height: 34, borderRadius: 1.75,
                cursor: "pointer", fontSize: 12.5, fontWeight: on ? 600 : 400,
                color: on ? "#41525f" : DIM, bgcolor: on ? "#eae4d8" : "transparent",
                "&:hover": { bgcolor: on ? "#eae4d8" : "#f4f1ec" } }}>
              {React.createElement(PAGES[k].icon, { sx: { fontSize: 16 } })}
              {PAGES[k].title}
            </Box>
          );
        })}
        <Typography variant="caption" sx={{ color: FAINT, display: "block", pt: 2, px: 1.25, lineHeight: 1.6 }}>
          Everything here is stored locally, in the same SQLite file as your tasks.
        </Typography>
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <SettingsPages page={q ? null : page} setPage={setPage} q={q} setQ={setQ} />
      </Box>
    </Box>
  );
}


// The log itself, newest first - the page used to be one button and a sentence, and nobody could
// tell what it was a log OF. Who is said in words: you, the router, an agent, a scheduled report.
const ACTOR_LABEL = { owner: "you", router: "the router", triage: "triage", report: "a report", system: "the app", startup: "startup", "connector-test": "a Test", msauth: "sign-in" };
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
        <Typography sx={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT }}>HISTORY · LAST {rows.length} ACTIONS</Typography>
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
  const st = notifyState(connectors, val("notify_level", "needs_me"), val("phone_approvals") === "1");
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
