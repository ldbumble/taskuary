// Timeline: left time rail, messages slide in as compact blurbs - who/where, the subject,
// and one plain sentence saying what the hub DID with it (routed where, drafted, filed,
// ignored) plus its current status. Hover or click a blurb for the whole story. Refreshes
// itself every 30s so new mail animates in while the tab is open.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Drawer, IconButton, ListSubheader, MenuItem, Select, TextField, Typography, useMediaQuery,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import CheckIcon from "@mui/icons-material/Check";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import api from "./api";
import { fadeBand } from "./timelineFade.js";
import { syncStatusDelay } from "./syncTiming.js";
import { availablePickerChannels, channelsForCategory } from "./feedFilters.js";
import { timelineDayLabel } from "./timelineDay.js";
import { splitTimelineMeetings } from "./timelineMeetings.js";
import { groupThreads, loudest, spanText } from "./threadGroups.js";
import EventIcon from "@mui/icons-material/Event";
import { pollWhileVisible } from "./visible.js";
import { feedHeaders, feedOk, takeFeed } from "./feedLoad.js";
import { ALERT, ALERT_BD, ALERT_INK, ASSISTANT, ROLES, PILL_COLORS, BG, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, GRADIENT, card, mono, fadeIn } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { Attachments } from "./Attachments.jsx";
import { AgentPicker, ChannelIcon, RefChip, ChoiceRow, CoderReport, Confirm, DiffBlock, Empty, FilterPills, ProofCard, SendToAgent, NotMine, fmtTime12, fmtDateTime, localDay, tsMs, cleanText, splitQuoted, IDLE_WAITING, TellAgent, TellAgentButton, LiveConsole, useAgents, useVoiceReady, TaskuaryMark } from "./ui.jsx";
import MicIcon from "@mui/icons-material/Mic";
import MicOffIcon from "@mui/icons-material/MicOff";
import { Md, looksMd } from "./md.jsx";
import { subjectOf, sourceOf } from "./feedText.js";
import { HOLD_TAG, hasTag, stateMeta, stateOf, subline } from "./timelineState.js";
import StateMark, { edgeOf } from "./StateMark.jsx";
import NewSheet from "./NewSheet.jsx";
import AddIcon from "@mui/icons-material/Add";
import { isVoicePlaceholder, voiceNoteBody } from "./voiceNote.js";
import { TerminalPane } from "./TerminalView.jsx";

const GeneralWorkspace = React.lazy(() => import("./GeneralWorkspace.jsx").then((m) => ({ default: m.GeneralWorkspace })));

// Two different dimensions, two controls: WHAT STATE it's in (everything vs needs me) and WHICH
// KIND / SOURCE it came from - they combine (e.g. "needs me" + "email"). STATE gets semantic
// colour: "needs me" is the one filter on this screen that names something being on you.
const VIEW_FILTERS = [
  { key: "", label: "everything", c: PILL_COLORS.pick },
  { key: "pending", label: "needs me", c: PILL_COLORS.you },
];
// ...and on a PHONE the segmented control becomes one toggle pill with its count: the housing
// scrolled there so only "everythin" showed, and the row had no room for two words twice (the
// owner, 2026-09-01). The desktop keeps the segmented control exactly as it was.
const NeedsMe = ({ on, n, onClick }) => (
  <Box onClick={onClick} role="switch" aria-checked={on} title={on ? "showing only what is waiting on you — click for everything" : "show only what is waiting on you"}
    sx={{ display: "inline-flex", alignItems: "center", gap: 0.65, height: 34, px: 1.35, borderRadius: 2, cursor: "pointer",
      fontSize: 11.5, fontWeight: 700, whiteSpace: "nowrap", userSelect: "none", transition: "all .15s",
      bgcolor: on ? PILL_COLORS.you.bg : PANEL2, color: on ? PILL_COLORS.you.fg : DIM,
      border: `1px solid ${on ? PILL_COLORS.you.bd : BORDER}`,
      "&:hover": { color: on ? PILL_COLORS.you.fg : INK, borderColor: on ? PILL_COLORS.you.bd : "#d8cfbe" } }}>
    needs me
    {n > 0 && (
      <Box component="span" sx={{ px: 0.6, py: 0.05, borderRadius: 99, fontSize: 10, fontWeight: 700, lineHeight: 1.5,
        fontVariantNumeric: "tabular-nums", bgcolor: on ? "rgba(255,255,255,.7)" : ALERT, color: on ? PILL_COLORS.you.fg : "#fffdfb" }}>{n}</Box>
    )}
  </Box>
);
// The pill row is a fixed set of CATEGORIES - it must not grow as connections do (a
// pill per mailbox, repo, channel and report would be unreadable by connection five).
// Everything narrower lives in one grouped picker: category -> channel -> connection.
const CATEGORIES = [
  { key: "", label: "all kinds", c: PILL_COLORS.pick },
  { key: "email", label: "email", c: PILL_COLORS.pick },
  { key: "messages", label: "messages", c: PILL_COLORS.pick },
  { key: "code", label: "code", c: PILL_COLORS.pick },
  { key: "reports", label: "reports", c: PILL_COLORS.pick },
  { key: "other", label: "other", c: PILL_COLORS.pick },
];
const CHANNEL_LABELS = { email: "Mailboxes", teams: "Teams chats", slack: "Slack channels",
  telegram: "Telegram chats", whatsapp: "WhatsApp chats", imessage: "Apple Messages chats", discord: "Discord channels",
  github: "Repositories", gitlab: "GitLab instances", report: "Reports", assistant: "Assistant posts", own: "Your own notes",
  jira: "Jira issues", asana: "Asana tasks", monday: "Monday items", linear: "Linear issues",
  clickup: "ClickUp tasks", todoist: "Todoist tasks",
  trello: "Trello cards", notion: "Notion pages", azdo: "Azure DevOps items",
  sentry: "Sentry errors", pagerduty: "PagerDuty incidents",
  aws: "AWS buckets & log groups", azure: "Azure containers & workspaces" };

const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;

// What the row is, for the chip. A scheduled report or a feed-only connection's item was
// never judged - it is information. Only a policy 'ignore' is a verdict.
const actionOf = (r) => (r.Channel === "report" ? "report"
  : r.MsgStatus === "feed" ? "feed"
    : r.MsgStatus === "triaging" ? "triaging"
    : r.MsgStatus === "ignored" ? "ignore"
      : r.MsgStatus === "filed" ? "filed"
        : r.ReviewKind === "auto" ? "auto"
          : r.ReviewId ? "draft" : "task_only");

// NeedsYou comes from the server and means one thing: nobody else is moving this. It
// outranks the verdict chip, because "what happened to it" matters less than "is it mine".
const needsYou = (r) => !!r.NeedsYou && r.TaskStatus !== "done";

// One plain-English sentence: what the hub did + where it stands.
const blurb = (r) => {
  if ((r.RouteReason || "").includes("your reply") || (r.RouteReason || "").includes("your sent reply"))
    return r.TaskId ? `Your reply — kept on ${ref(r.TaskId)} so the thread shows both sides` : "Your reply — kept for context, never a task";
  if (r.Channel === "assistant") return "The assistant's post — open it to talk back or act on a suggestion";
  if (r.Channel === "report") return "Scheduled report — hover to read the summary";
  if (r.MsgStatus === "feed") return "Shown for information — this connection is a feed, not a task trigger";
  if (r.MsgStatus === "triaging") return "On the timeline first — triage is deciding what it is";
  // WHAT happened, never the classifier's sentence about why: that lives on the Triage tab, where
  // it is asked for (owner, 2026-09-02: "hate the why - just tell me what")
  if (r.MsgStatus === "ignored") return "Ignored by policy — no task created";
  if (r.Category === "info") return "Info from a person — nothing to do";
  if (r.Category === "promo") return "Promotional — nothing to do";
  if (r.Category === "automated") return "Automated notice — nothing to do";
  if (r.MsgStatus === "filed") return "Filed — nothing to do";
  const routed = r.Decision === "attach" ? `Added to ${ref(r.TaskId)} (existing thread)` : `New task ${ref(r.TaskId)} created`;
  const state = r.ReviewStatus === "pending" ? "a reply is drafted — waiting on your review"
      : r.ReviewStatus === "auto" ? "AI answered automatically"
        : r.TaskStatus === "done" ? `completed${r.ReviewStatus ? ` · you said ${r.ReviewStatus.replace("_", " ")}` : ""}`
          : r.Working ? `an agent is working it right now (${r.Working})`
          : needsYou(r) ? "needs you — no agent is working it right now"
            : r.ReviewStatus ? `reviewed (${r.ReviewStatus})` : "an agent is working it";
  return `${routed} · ${state}`;
};

// The time gutter. 58px broke "12:40 PM" onto two lines, which is what made the column look
// unkempt - the number and its meridiem have to live on one line.
const GUTTER = 70;
// The rail dot says WHAT STATE it is in. Channel identity is already on the icon beside the
// sender, and the old row said it three times over (stripe, dot, tinted tile).
const dotOf = (r) => (needsYou(r) || r.ReviewStatus === "pending" ? ACCENT
  : r.Channel === "assistant" ? ASSISTANT.solid             // the assistant speaking up
  : r.Category === "info" ? "#6f8a6e"                      // a person told you something: worth the eye
  : ["ignored", "filed", "triaging", "withdrawn"].includes(r.MsgStatus) ? "#cfc9bf"
    : r.ReviewStatus === "auto" || r.TaskStatus === "done" ? "#b8b2a9"
      : r.TaskId ? ACCENT2 : "#a7b0a8");

// How much each state DEMANDS of you, most first - which is what a fold has to sort by to pick
// the face it wears. Deliberately NOT stateOf's evaluation order: that reads withdrawn first,
// because a message that no longer exists cannot be what you act on, and for one row that is
// right. For a fold it is backwards - a withdrawn line must never speak for four others, one of
// which is a reply waiting on you.
const LOUDNESS = ["reply", "waving", "working", "held", "answered", "todo", "mine", "done", "withdrawn", "fyi"];

const PAGE = 100;

// The funnel bar (rank mode): what is being worked and what waits, in value order. One line
// folded - "In the funnel 3/4 · Next up 7" - so the Timeline is never stuffed with the tail of
// the queue; unfold it for the ranks, the reasons, and the two overrides.
const FunnelBar = ({ onOpenTask }) => {
  const [f, setF] = useState(null);
  const [open, setOpen] = useState(false);
  const load = useCallback(async () => { try { setF((await api.get("/api/funnel")).data); } catch { setF(null); } }, []);
  useEffect(() => { load(); return pollWhileVisible(load, 10000); }, [load]);
  if (!f || f.mode !== "rank") return null;
  const act = async (tid, what) => { await api.post(`/api/funnel/${tid}/${what}`); load(); };
  return (
    <Box sx={{ gridColumn: "1 / -1", justifySelf: "center", width: "100%", maxWidth: 900, mt: 0.5 }}>
      <Box onClick={() => setOpen((o) => !o)} sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 0.6, cursor: "pointer",
        bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: open ? "10px 10px 0 0" : 99 }}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "#47654a", fontSize: 11 }}>
          In the funnel {f.working.length}/{f.width}
        </Typography>
        <Box sx={{ width: "1px", height: 14, bgcolor: BORDER }} />
        <Typography variant="caption" sx={{ fontWeight: 700, color: ROLES.working.ink, fontSize: 11 }}>
          Next up {f.queued.length} {open ? "▾" : "▸"}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
          {f.working.slice(0, 4).map((w) => (
            <Box key={w.tid} sx={{ display: "inline-flex", alignItems: "center", gap: 0.4 }}>
              <Typography variant="caption" onClick={() => onOpenTask && onOpenTask(w.tid)} sx={{ ...mono, color: "#47654a", fontSize: 10.5, fontWeight: 700, cursor: "pointer" }} title={w.title}>{w.ref}</Typography>
              <TellAgentButton taskId={w.tid} taskRef={w.ref} small />
            </Box>
          ))}
        </Box>
      </Box>
      {open && (
        <Box sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderTop: "none", borderRadius: "0 0 10px 10px", px: 1.5, py: 0.5 }}>
          {f.queued.length === 0 && <Typography variant="caption" sx={{ color: FAINT, display: "block", py: 1 }}>Nothing waiting — every task from a rank-mode connector is being worked.</Typography>}
          {f.queued.map((q, i) => (
            <Box key={q.tid} sx={{ display: "flex", alignItems: "center", gap: 1.25, py: 0.6, borderTop: i ? `1px solid ${BORDER}` : "none" }}>
              <Typography variant="caption" sx={{ ...mono, color: ROLES.working.ink, fontWeight: 700, width: 18, fontSize: 11 }}>{i + 1}</Typography>
              <Typography variant="body2" onClick={() => onOpenTask && onOpenTask(q.tid)} sx={{ fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={q.title}>{q.title}</Typography>
              <Typography variant="caption" sx={{ color: DIM, fontSize: 10.5, whiteSpace: "nowrap", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}
                title={q.why}>{q.behind ? `waiting on ${q.behind} · ` : ""}{q.why}</Typography>
              <Button size="small" onClick={() => act(q.tid, "pin")} sx={{ fontSize: 10.5, py: 0, minWidth: 0 }}>Start now</Button>
              <Button size="small" onClick={() => act(q.tid, "later")} sx={{ fontSize: 10.5, py: 0, minWidth: 0, color: DIM }}>Later</Button>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};

// What is coming up on your calendar, at the top of today: each meeting a row in the
// Timeline's own shape, tinted so it reads as a different kind of thing, with how long until
// it starts. Events come cached from the server; the countdown ticks here every 30 s.
const untilText = (start, end) => {
  const now = Date.now(), s = new Date(String(start).replace(" ", "T")).getTime(), e = end ? new Date(String(end).replace(" ", "T")).getTime() : s;
  if (now >= s && now <= e) return { text: "now", hot: true };
  const m = Math.round((s - now) / 60000);
  if (m < 0) return { text: now - e < 15 * 60000 ? "just ended" : "ended", hot: false };
  if (m < 60) return { text: `in ${m} min`, hot: m <= 15 };
  if (m < 60 * 24) return { text: `in ${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`, hot: false };
  return { text: `in ${Math.round(m / 1440)} day${Math.round(m / 1440) === 1 ? "" : "s"}`, hot: false };
};
// Today's meetings, fetched once for the whole Timeline and re-rendered every 30 s so countdowns
// move. Upcoming ones go in the band above the newest message (the list is newest-first, so the
// future belongs on top); at its start time a meeting takes its chronological place in the stream.
const useCalToday = () => {
  const [cal, setCal] = useState(null);
  const [tick, setTick] = useState(0);          // only read to force the 30 s re-render (the scope test needs it named)
  useEffect(() => {
    let alive = true;
    const load = async () => { try { const { data } = await api.get("/api/calendar/today"); if (alive) setCal(data); } catch { /* no calendar */ } };
    load();
    const a = setInterval(load, 300000), b = setInterval(() => setTick((t) => t + 1), 30000);
    return () => { alive = false; clearInterval(a); clearInterval(b); };
  }, []);
  return tick >= 0 ? (cal?.events || []) : [];
};
// One meeting as a Timeline row - tinted so it reads as a different kind of thing. Hover opens it
// after the same beat a message takes, click opens it now; the panel shows who is in it and why.
// What ties a prep row to the invite it is about. server.prep_key builds the same string when
// the prep is created; if the two drift, the prep goes back to floating an hour down the rail.
export const evKey = (e) => `calendar:${e?.start || ""}:${String(e?.subject || "the meeting").trim().slice(0, 120)}`;

const MeetingRow = ({ e, onPick, picked, preps = [], onOpenRow }) => {
  const hover = useRef(null);
  useEffect(() => () => clearTimeout(hover.current), []);
  const u = untilText(e.start, e.end), open = picked && picked.start === e.start && picked.subject === e.subject;
  // A meeting is a Timeline row like any other, and it did not look like one: no left margin off
  // the rail, so it sat 8px closer than every message; a heavier tint; and everything it knows -
  // who, where, tentative, the countdown - crammed onto the collapsed line. Same geometry as a
  // message row now, subject only until it is the row you are on.
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: `${GUTTER}px 14px minmax(0,1fr)`, alignItems: "stretch", mb: "3px" }}>
      <Typography sx={{ ...mono, fontSize: 10, color: FAINT, textAlign: "right",
        pt: "6px", pl: "8px", pr: "12px", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
        {e.all_day ? "all day" : fmtTime12(e.start)}
      </Typography>
      <Box sx={{ position: "relative" }}>
        <Box sx={{ position: "absolute", left: "6px", top: "-5px", bottom: "-5px", width: "1px", bgcolor: BORDER }} />
        <Box sx={{ position: "absolute", left: "2.5px", top: "9px", width: 8, height: 8, borderRadius: "50%",
          bgcolor: u.hot ? ALERT : ROLES.info.solid, boxShadow: `0 0 0 3px ${PANEL}` }} />
      </Box>
      <Box onClick={() => { clearTimeout(hover.current); onPick?.({ ...e, pinned: true }); }}
        onMouseEnter={() => { clearTimeout(hover.current); hover.current = setTimeout(() => onPick?.({ ...e, pinned: false }), 140); }}
        onMouseLeave={() => clearTimeout(hover.current)}
        sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderLeft: `2px solid ${u.hot ? ALERT : ROLES.info.solid}`,
          borderRadius: "8px", px: "10px", pt: "3px", pb: "4px", ml: "8px", minWidth: 0, overflow: "hidden",
          cursor: "pointer",
          transition: "box-shadow .18s, border-color .18s",
          ...(open ? { borderColor: ACCENT, boxShadow: `inset 0 0 0 1px ${ACCENT}, 0 1px 3px rgba(30,50,38,.08)` } : {}),
          "&:hover": { borderColor: "#d8cfbe", boxShadow: "0 2px 8px rgba(47,107,79,.10)" } }}>
        <Box sx={{ display: "flex", gap: 0.85, alignItems: "center", minWidth: 0, minHeight: 22 }}>
          <EventIcon sx={{ fontSize: 16, color: ROLES.info.solid, flexShrink: 0 }} />
          <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: INK, fontSize: 12, flex: 1, minWidth: 0 }}>{e.subject}</Typography>
          {/* the countdown is the one thing that is only true right now, so it stays on the
              collapsed line - but quietly, unless the meeting is imminent */}
          <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, fontWeight: u.hot ? 700 : 400, whiteSpace: "nowrap",
            color: u.hot ? ALERT : FAINT, flexShrink: 0 }}>{u.text}</Typography>
        </Box>
        <Box sx={{ display: "grid", gridTemplateRows: open ? "1fr" : "0fr", transition: "grid-template-rows .2s ease" }}>
          <Box sx={{ overflow: "hidden" }}>
            <Typography noWrap sx={{ fontSize: 10.5, lineHeight: 1.5, pt: "2px", pl: "24px", color: FAINT }}>
              {[(e.who || []).length ? `with ${e.who.slice(0, 4).map((w) => w.split(" ")[0]).join(", ")}${e.who.length > 4 ? ` +${e.who.length - 4}` : ""}` : "",
                e.where || "", e.status === "tentative" ? "tentative" : ""].filter(Boolean).join(" · ") || "no attendees listed"}
            </Typography>
          </Box>
        </Box>
        {/* What you asked for ABOUT THIS MEETING, on the meeting. It used to be a row of its own,
            stamped whenever the session happened to open, so the invite and the prep for it sat
            an hour apart on a rail that is meant to read as a day. */}
        {preps.map((p) => (
          <Box key={p.MessageId} onClick={(ev) => { ev.stopPropagation(); onOpenRow?.(p); }}
            sx={{ display: "flex", alignItems: "center", gap: 0.7, mt: 0.4, pt: 0.4, minWidth: 0,
              borderTop: `1px dashed ${BORDER}`, cursor: "pointer",
              "&:hover .tqPrepTitle": { color: INK } }}>
            <Box component="span" aria-hidden sx={{ fontSize: 10.5, lineHeight: 1, flexShrink: 0 }}>💡</Box>
            <Typography className="tqPrepTitle" variant="caption" noWrap
              sx={{ color: DIM, fontWeight: 600, fontSize: 11, flex: 1, minWidth: 0, transition: "color .15s" }}>
              {String(p.Subject || "").replace(/^Prep:\s*/i, "") || "prep"}
            </Typography>
            <StateMark row={p} size="sm" />
          </Box>
        ))}
      </Box>
    </Box>
  );
};

// The band above today's newest message: what is still ahead (and all-day items). Ended meetings
// are not here - they are rendered in the stream by the Timeline itself, at their time.
const ComingUp = ({ events, onPick, picked }) => {
  if (!events.length) return null;
  return <Box sx={{ mb: 0.5 }}>{events.map((e, i) => <MeetingRow key={`${e.start}-${i}`} e={e} onPick={onPick} picked={picked} />)}</Box>;
};

// "Get me ready for this one." The panel says who is in it and what it is about; this is where
// you say what to DO about that - pull the numbers, find the last thread, draft the questions.
// The invite goes down with your prompt as the task's context, so the agent opens already
// knowing which meeting it is; the task carries repo:none, because preparing for a meeting is
// not a change to a codebase.
const MeetingPrep = ({ e, onOpenTask }) => {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { setSent(null); setErr(""); setPrompt(""); }, [e.start, e.subject]);
  const send = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/api/calendar/prep", {
        subject: e.subject, start: e.start, end: e.end, where: e.where, organizer: e.organizer,
        who: e.who || [], about: e.about, link: e.link, status: e.status, all_day: !!e.all_day,
        instruction: prompt.trim() || null });
      setSent(data); setPrompt("");
      onOpenTask?.(data.taskId);
    } catch (x) { setErr(x?.response?.data?.detail || "Could not reach the agent"); }
    setBusy(false);
  };
  if (sent) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      <TaskuaryMark size={15} />
      <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>
        Your assistant is prepping it — {sent.ref}
      </Typography>
      <Button size="small" sx={{ fontSize: 11 }} onClick={() => onOpenTask?.(sent.taskId)}>open the chat →</Button>
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setSent(null)}>ask something else</Button>
    </Box>
  );
  return (
    <Box>
      {/* no agent picker: preparing for a meeting is reading and thinking, so it opens the
          ASSISTANT'S CHAT rather than a CLI in a checkout, and the chat picks its own provider */}
      <PanelLabel>Prepare me for it</PanelLabel>
      <TextField fullWidth multiline minRows={2} maxRows={8} size="small" value={prompt}
        onChange={(x) => setPrompt(x.target.value)}
        placeholder={`What should it get ready? e.g. "Pull last month's numbers for these facilities and give me three questions to ask."`}
        sx={{ bgcolor: "#fffdfb" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75 }}>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 0 }}>
          it gets the invite — when, where, who is in it and what it says
        </Typography>
        <Button size="small" variant="contained" disableElevation disabled={busy || !prompt.trim()} onClick={send}
          startIcon={busy ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <TaskuaryMark size={14} />}
          sx={{ fontSize: 11.5, bgcolor: "#6f8a6e", "&:hover": { bgcolor: "#5b7259" } }}>
          {busy ? "opening…" : "Ask the assistant"}
        </Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#6b2733", display: "block", mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
};

// A meeting, opened: the right panel's answer to "who is in it and what is it about" - the
// invite's own words when it has any, the people (never you), where, and the way in.
const EventPanel = ({ e, onClose, onOpenTask }) => {
  const u = untilText(e.start, e.end);
  const when = e.all_day ? "all day" : `${fmtTime12(e.start)} – ${fmtTime12(e.end)}`;
  return (
    <Box sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 3, overflow: "hidden", display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 80px)" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.25, borderBottom: `1px solid ${BORDER}`, bgcolor: "#f5f0e4" }}>
        <EventIcon sx={{ fontSize: 18, color: "#8a7a5c" }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, color: INK, fontSize: 14.5, lineHeight: 1.25 }} noWrap>{e.subject}</Typography>
          <Typography variant="caption" sx={{ color: DIM }}>{when}{e.where ? ` · ${e.where}` : ""}{e.status === "tentative" ? " · tentative" : ""}</Typography>
        </Box>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10.5, fontWeight: 700, whiteSpace: "nowrap",
          color: u.hot ? "#fffdfb" : "#6b5f45", bgcolor: u.hot ? "#8a3646" : "#eee7d6", px: 0.8, py: 0.15, borderRadius: 99 }}>{u.text}</Typography>
        <IconButton size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
      </Box>
      <Box sx={{ px: 2, py: 1.5, overflowY: "auto", display: "flex", flexDirection: "column", gap: 1.5 }}>
        <Box>
          <PanelLabel>What it’s about</PanelLabel>
          {e.about ? <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{e.about}</Typography>
            : <Typography variant="body2" sx={{ color: FAINT }}>The invite says nothing beyond its title{e.subject ? ` — “${e.subject}”` : ""}.</Typography>}
        </Box>
        <Box>
          <PanelLabel>Who’s in it</PanelLabel>
          {(e.who || []).length ? (
            <Box sx={{ display: "flex", gap: 0.6, flexWrap: "wrap" }}>
              {e.who.map((w) => (
                <Box key={w} sx={{ display: "inline-flex", alignItems: "center", gap: 0.6, px: 1, py: 0.35, borderRadius: 99, bgcolor: "#eee7d6", border: "1px solid #ddd2b9", fontSize: 12, color: INK }}>
                  <Box sx={{ width: 18, height: 18, borderRadius: "50%", bgcolor: "#8a7a5c", color: "#fffdfb", fontSize: 9.5, fontWeight: 800, display: "grid", placeItems: "center" }}>
                    {w.split(" ").map((p) => p[0]).filter(Boolean).slice(0, 2).join("").toUpperCase()}
                  </Box>
                  {w}{e.organizer === w ? <Typography component="span" variant="caption" sx={{ color: FAINT }}>· organizer</Typography> : null}
                </Box>
              ))}
            </Box>
          ) : <Typography variant="body2" sx={{ color: FAINT }}>{e.organizer ? `organized by ${e.organizer} — no other attendees listed` : "no attendees listed — just you"}</Typography>}
        </Box>
        {(e.join || e.link) && (
          <Box sx={{ display: "flex", gap: 1 }}>
            {e.join && <Button size="small" variant="contained" disableElevation component="a" href={e.join} target="_blank" rel="noreferrer"
              sx={{ bgcolor: "#55697a", "&:hover": { bgcolor: "#41525f" } }}>Join the meeting</Button>}
            {e.link && <Button size="small" variant="outlined" component="a" href={e.link} target="_blank" rel="noreferrer">Open in calendar</Button>}
          </Box>
        )}
        <Box sx={{ pt: 1.25, borderTop: `1px dashed ${BORDER}` }}>
          <MeetingPrep e={e} onOpenTask={onOpenTask} />
        </Box>
      </Box>
    </Box>
  );
};

// The day's meetings as one strip above the Morning digest: a track from 7 to 7, each meeting a
// block at its hour, sliding into place; a pulsing mark for now. The digest's words are below it;
// this is the shape of the day at a glance.
const TodayStrip = () => {
  const [t, setT] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    api.get("/api/calendar/today").then(({ data }) => alive && setT(data)).catch(() => alive && setT({ events: [] }));
    const id = setInterval(() => setTick((x) => x + 1), 60000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  if (!t) return null;
  const evs = (t.events || []).filter((e) => !e.all_day);
  const allDay = (t.events || []).filter((e) => e.all_day);
  if (!t.events?.length) return null;
  const H0 = 7, H1 = 19, span = H1 - H0;
  const hourOf = (s) => { const d = new Date(String(s).replace(" ", "T")); return d.getHours() + d.getMinutes() / 60; };
  const now = new Date(); const nowH = now.getHours() + now.getMinutes() / 60;
  const pct = (h) => `${Math.max(0, Math.min(100, ((h - H0) / span) * 100))}%`;
  return (
    <Box data-tick={tick} sx={{ mb: 1.5, p: 1.25, bgcolor: "#f5f0e4", border: "1px solid #e3d9c2", borderRadius: 2,
      "@keyframes tqSlide": { from: { opacity: 0, transform: "translateY(6px) scaleX(.6)" }, to: { opacity: 1, transform: "none" } },
      "@keyframes tqPulse": { "0%": { boxShadow: "0 0 0 0 rgba(138,54,70,.45)" }, "100%": { boxShadow: "0 0 0 8px rgba(138,54,70,0)" } } }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.75 }}>
        <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: "#6b5f45", fontWeight: 700 }}>📅 TODAY’S MEETINGS · {t.events.length}</Typography>
        {allDay.map((e) => <Typography key={e.subject} variant="caption" sx={{ color: FAINT }}>· all day: {e.subject}</Typography>)}
      </Box>
      {/* the track */}
      <Box sx={{ position: "relative", height: 44, borderTop: "1px solid #ddd2b9", borderBottom: "1px solid #ddd2b9" }}>
        {Array.from({ length: span + 1 }, (_, i) => H0 + i).map((h) => (
          <Box key={h} sx={{ position: "absolute", left: pct(h), top: 0, bottom: 0, borderLeft: `1px dotted ${h % 3 === 0 ? "#c9b98f" : "#e6dcc3"}` }}>
            {h % 3 === 0 && <Typography sx={{ ...mono, fontSize: 8.5, color: FAINT, position: "absolute", top: 46, left: -8 }}>{h > 12 ? `${h - 12}p` : h === 12 ? "12p" : `${h}a`}</Typography>}
          </Box>
        ))}
        {evs.map((e, i) => {
          const s = hourOf(e.start), en = e.end ? hourOf(e.end) : s + 0.5;
          const live = nowH >= s && nowH <= en, past = nowH > en;
          // a title only fits a block that is wide enough (~75 min on this track); shorter meetings
          // carry their number and the list below carries the name - long or short, it always fits
          const wide = en - s >= 1.25;
          return (
            <Box key={`${e.start}-${i}`} title={`${e.subject}${e.who?.length ? ` · with ${e.who.join(", ")}` : ""}${e.about ? `\n${e.about}` : ""}`}
              sx={{ position: "absolute", left: pct(s), width: `calc(${pct(Math.max(en, s + 0.35))} - ${pct(s)})`, top: 8, height: 28, borderRadius: 1,
                bgcolor: live ? "#8a3646" : past ? "#d9cfb6" : "#8a7a5c", color: live || !past ? "#fffdfb" : "#6b5f45",
                px: wide ? 0.75 : 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
                fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", textOverflow: "ellipsis",
                transformOrigin: "left center", animation: `tqSlide .5s ease ${i * 0.08}s both`, cursor: "default" }}>
              <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{wide ? e.subject : i + 1}</Box>
            </Box>
          );
        })}
        {nowH >= H0 && nowH <= H1 && (
          <Box sx={{ position: "absolute", left: pct(nowH), top: -4, bottom: -4, width: 2, bgcolor: "#8a3646", borderRadius: 1 }}>
            <Box sx={{ position: "absolute", top: -5, left: -4, width: 10, height: 10, borderRadius: "50%", bgcolor: "#8a3646", animation: "tqPulse 1.6s ease-out infinite" }} />
          </Box>
        )}
      </Box>
      <Box sx={{ mt: 2.25, display: "flex", flexDirection: "column", gap: 0.35 }}>
        {evs.map((e, i) => (
          <Typography key={`${e.start}-l${i}`} variant="caption" sx={{ color: INK, display: "flex", gap: 0.75, alignItems: "baseline", flexWrap: "wrap", animation: `tqSlide .4s ease ${0.3 + i * 0.06}s both` }}>
            {/* the number is the block on the track: a short meeting cannot hold its own name up there */}
            <Box component="span" sx={{ ...mono, color: "#6b5f45", fontSize: 10, minWidth: 16, textAlign: "right" }}>{i + 1}.</Box>
            <Box component="span" sx={{ ...mono, color: "#6b5f45", fontSize: 10.5, minWidth: 62 }}>{fmtTime12(e.start)}</Box>
            <Box component="span" sx={{ fontWeight: 600, overflowWrap: "anywhere" }}>{e.subject}</Box>
            {!!(e.who || []).length && <Box component="span" sx={{ color: DIM }}>with {e.who.slice(0, 4).map((w) => w.split(" ")[0]).join(", ")}{e.who.length > 4 ? ` +${e.who.length - 4}` : ""}</Box>}
            {e.about && <Box component="span" sx={{ color: FAINT }}>— {e.about.length > 90 ? `${e.about.slice(0, 90)}…` : e.about}</Box>}
          </Typography>
        ))}
      </Box>
    </Box>
  );
};

export default function FeedView({ onOpenTask, onChanged, active = true }) {
  // below md there is no stage beside the rail; whatever is opened slides over it instead, so a
  // tap on a row is never a tap that did nothing
  const narrow = useMediaQuery("(max-width:899.95px)");
  const [calSel, setCalSel] = useState(null);        // a meeting opened from the coming-up band
  const calEvents = useCalToday();
  // The filter dock is a fixed flex sibling of the scroller. Rows never fade at its top edge;
  // the only visual fade belongs to the true bottom edge of the rail.
  // the rail's own scroller. The Timeline used to BE the page: it scrolled the window, its
  // filters were a sticky dock floating over the whole width, and the review panel was a sticky
  // column beside it. That made the list the subject of the screen when the TASK is the subject
  // - so the list is a container now, with its own header and its own scrollbar, and everything
  // below reads scroll off this element instead of off the window.
  const railRef = useRef(null);
  // the rail pins BELOW the app's top bar and fills the rest of the window; height measured by id
  const [navH, setNavH] = useState(49);
  useEffect(() => {
    const el = document.getElementById("tqTopNav");
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setNavH(el.offsetHeight));
    ro.observe(el); setNavH(el.offsetHeight);
    return () => ro.disconnect();
  }, []);
  // ONE date line, in the rail's header: everything from the date up stays exactly the same
  // regardless of scroll. The rows slide into the date's underside and only the LABEL updates -
  // a scroll spy reads which day group currently crosses the header's bottom edge.
  const dayRefs = useRef({});                        // day (YYYY-MM-DD) -> group element
  const dayLayout = useRef([]);                      // cached content offsets; scrolling must not force layout
  const dayLayoutDirty = useRef(true);
  const dayLayoutAt = useRef(0);                     // the rail's scrollHeight when last measured
  const dateJump = useRef("");                       // picker owns the label during its smooth glide
  const dateJumpTimer = useRef(null);
  const [curDay, setCurDay] = useState("");
  const spy = useCallback(() => {
    const rail = railRef.current; if (!rail) return;
    if (dateJump.current) { setCurDay(dateJump.current); return; }
    // ...and re-measure whenever the rail has grown since the last look: rows arriving after the
    // first measurement left every group at top 0, and the last of those ties is the wrong day
    if (dayLayoutDirty.current || rail.scrollHeight !== dayLayoutAt.current) {
      // Measure once after the rows/layout change. Reading every group's bounding box on every
      // wheel frame made Chromium synchronously lay out the whole rail while it was scrolling.
      const railTop = rail.getBoundingClientRect().top;
      dayLayout.current = Object.entries(dayRefs.current).flatMap(([day, el]) => el
        ? [{ day, top: el.getBoundingClientRect().top - railTop + rail.scrollTop }]
        : []).sort((a, b) => a.top - b.top);
      dayLayoutDirty.current = false; dayLayoutAt.current = rail.scrollHeight;
    }
    const edge = rail.scrollTop + 1;
    // the current day is the last group whose cached content edge has crossed the dock
    let cur = "", lastTop = -1;
    for (const entry of dayLayout.current) {
      if (entry.top > edge) break;
      if (entry.top === lastTop) continue;             // two groups at one top: nothing is laid out yet
      cur = entry.day; lastTop = entry.top;
    }
    setCurDay((was) => cur || was);
  }, []);
  useEffect(() => {
    const rail = railRef.current; if (!rail) return undefined;
    let raf = 0;
    const onScroll = () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; spy(); }); };
    rail.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
    return () => { rail.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, [spy]);
  useEffect(() => () => clearTimeout(dateJumpTimer.current), []);
  const [newOpen, setNewOpen] = useState(false);     // the ＋ New sheet (NewSheet.jsx)
  const [rows, setRows] = useState(null);
  const [view, setView] = useState("");              // "" everything | "pending" needs me
  const [openFolds, setOpenFolds] = useState(() => new Set());   // conversations unfolded by hand
  const [cat, setCat] = useState("");                // broad content family; exact choices live in the source picker
  const [pick, setPick] = useState("");              // "" all in category | "channel:x" | "src:channel:name"
  const [srcByChannel, setSrcByChannel] = useState({});   // channel -> connection names
  const [srcQ, setSrcQ] = useState("");                    // the picker's own search box
  const [noMore, setNoMore] = useState(false);
  const [detail, setDetail] = useState(null);
  const [editText, setEditText] = useState(null);    // null = untouched; "" = deliberately cleared
  const [err, setErr] = useState("");
  const seen = useRef(new Set());               // MessageIds already animated in
  const rowsLen = useRef(0);
  const etagRef = useRef("");
  const busyMore = useRef(false);
  const endRef = useRef(null);

  // one place turns (category, pick) into query params: a category is a channel csv, a
  // pick narrows to one channel or one named connection inside it
  const fparams = useCallback(() => {
    const chans = channelsForCategory(cat, Object.keys(srcByChannel));
    const p = { ...(view === "pending" ? { pending_only: true } : {}) };
    if (pick.startsWith("src:")) {
      const [, ch, ...rest] = pick.split(":");
      p.channel = ch; p.source = rest.join(":");
    } else if (pick.startsWith("channel:")) {
      p.channel = pick.slice(8);
    } else if (chans) {
      p.channel = chans.join(",");
    }
    return p;
  }, [view, cat, pick, srcByChannel]);

  // Every channel is a CATEGORY; the picker next to it narrows to one actual connection —
  // this mailbox, this repo, this Slack channel, this report.
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => {
      const by = {};
      for (const s of data.data || []) {
        if (!s.Active) continue;
        let sourceConfig = {};
        try { sourceConfig = JSON.parse(s.ConfigJson || "{}"); } catch { /* the address remains usable */ }
        // The scheduled Assistant is configured as a report source, but its Timeline posts are
        // channel=assistant. Put it under that exact picker option so filtering reaches the rows.
        const ch = s.Channel === "report" && sourceConfig.type === "assistant" ? "assistant" : s.Channel;
        const name = s.Channel === "report" ? (sourceConfig.title || s.Address) : s.Address;
        (by[ch] = by[ch] || []).push(name);
      }
      setSrcByChannel(by);
    }).catch(() => {});
  }, []);
  useEffect(() => { setPick(""); }, [cat]);          // switching category clears the narrower pick

  // (Re)fetch from the top - span covers everything already on screen so the 30s
  // refresh never shrinks the list under the user.
  const load = useCallback(async (span) => {
    try {
      const limit = Math.max(span || 0, PAGE);
      const res = await api.get("/api/feed", {
        params: { limit, ...fparams() },
        headers: feedHeaders(etagRef.current),
        validateStatus: feedOk,
      });
      const batch = takeFeed(res, etagRef);
      if (batch == null) return;                 // 304: the list on screen is still the truth
      setRows(batch); rowsLen.current = batch.length;
      setNoMore(batch.length < limit);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load the feed"); }
  }, [fparams]);

  // Infinite scroll: append the next page when the bottom sentinel shows.
  const loadMore = useCallback(async () => {
    if (busyMore.current || noMore || !rowsLen.current) return;
    busyMore.current = true;
    try {
      const { data } = await api.get("/api/feed", { params: { limit: PAGE, offset: rowsLen.current, ...fparams() } });
      const batch = data.data || [];
      setNoMore(batch.length < PAGE);
      if (batch.length) setRows((cur) => { const next = [...(cur || []), ...batch]; rowsLen.current = next.length; return next; });
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load more"); }
    busyMore.current = false;
  }, [fparams, noMore]);

  // Sync = trigger a real mailbox/Teams ingest server-side, then TRACK its actual state
  // (/ingest/status) instead of guessing with a fixed wait - the button stays "Updating"
  // and the list shows loading until the server says the poll finished.
  const [syncing, setSyncing] = useState(false);   // a sync YOU started - the list dims for it
  const [bgSync, setBgSync] = useState(false);     // the startup catch-up - rows stay readable
  const [syncWhat, setSyncWhat] = useState("");
  const [lastSync, setLastSync] = useState(null);
  const [every, setEvery] = useState(10);            // the server's cadence, not a guess
  // the server's clock, as an offset from OUR clock: nextPollAt is its time, so the countdown
  // uses (next - serverNow) and never trusts the two machines to agree on the hour
  const [nextIn, setNextIn] = useState(null);        // seconds until the next background sync, from the server
  const [triageErr, setTriageErr] = useState("");    // the brain's last failure, until it answers again
  const [fade, setFade] = useState("normal");        // Settings > Display; height of the viewport's bottom fade
  const bottomFade = fadeBand(fade);
  const [tick, setTick] = useState(0);
  useEffect(() => { if (!active) return undefined; const id = setInterval(() => setTick((t) => t + 1), 1000); return () => clearInterval(id); }, [active]);
  const nextAtRef = useRef(null);                     // Date.now() when the server's next poll is due
  useEffect(() => {
    // gated on `active`: this loop re-reads the whole list when a sync lands, and the Timeline
    // now stays MOUNTED behind another tab (so a live session keeps its socket) - ungated it
    // would poll and refetch for a screen nobody is looking at. Coming back re-asks at once.
    if (!active) return undefined;
    let alive = true, timer = null, completionTimer = null, wasRunning = false, seenPollAt = null;
    const ask = async () => {
      if (!alive) return;
      let running = false;
      try {
        const { data } = await api.get("/api/ingest/status");
        if (!alive) return;
        if (data.everyMinutes != null) setEvery(data.everyMinutes);
        const pollAt = Number(data.lastPollAt) || null;
        const completedBetweenChecks = seenPollAt != null && pollAt != null && pollAt > seenPollAt;
        if (pollAt) setLastSync(new Date(Date.now() - (data.now - pollAt) * 1000));
        seenPollAt = pollAt;
        nextAtRef.current = data.nextPollAt ? Date.now() + (data.nextPollAt - data.now) * 1000 : null;
        setTriageErr(data.triageError || "");
        if (data.timelineFade) setFade(data.timelineFade);
        // the server's OWN ten-minute sync wears the same face as pressing the button: the
        // button says Syncing…, the caption says what it is reading, rows land as they arrive
        running = data.status?.state === "running";
        if (running) {
          clearTimeout(completionTimer);
          setBgSync(true); setSyncWhat(data.status.what || ""); load(rowsLen.current);
        }
        else if (wasRunning) { setBgSync(false); setSyncWhat(""); load(rowsLen.current); }
        else if (completedBetweenChecks) {
          // Even a sub-second automatic poll gets a visible receipt. The clock changing proves
          // a real refresh ran, even if it completed between the two status requests.
          setBgSync(true); setSyncWhat("timeline refreshed"); load(rowsLen.current);
          clearTimeout(completionTimer);
          completionTimer = setTimeout(() => {
            if (alive) { setBgSync(false); setSyncWhat(""); }
          }, 900);
        }
        wasRunning = running;
      } catch { /* the caption just stops counting */ }
      timer = setTimeout(ask, syncStatusDelay({ running, nextAt: nextAtRef.current }));
    };
    ask();
    return () => { alive = false; clearTimeout(timer); clearTimeout(completionTimer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
  useEffect(() => { setNextIn(nextAtRef.current ? Math.max(0, Math.round((nextAtRef.current - Date.now()) / 1000)) : null); }, [tick]);
  const syncNow = useCallback(async (silent) => {
    if (!silent) setSyncing(true);
    try { await api.post("/api/ingest/poll"); } catch { /* poll failures surface in Connections */ }
    const t0 = Date.now();
    const settle = async () => { await load(rowsLen.current); setSyncing(false); setLastSync(new Date()); };
    const check = async () => {
      try {
        const { data } = await api.get("/api/ingest/status");
        if (data.status?.state === "running" && Date.now() - t0 < 180000) {
          setSyncWhat(data.status.what || "");
          // stop DIMMING the moment there is something real to look at: rows land oldest
          // first, one at a time, and a half-faded list behind a spinner hides exactly the
          // thing you pressed the button to watch
          setSyncing(false); setBgSync(true);
          await load(rowsLen.current);
          setTimeout(check, 2000); return;
        }
      } catch { /* fall through and settle */ }
      setSyncWhat(""); setBgSync(false); settle();
    };
    setTimeout(check, 1500);
  }, [load]);

  // The startup catch-up runs before this tab is even open - if it is still going when the
  // page mounts, say so and refresh the list the moment it finishes. It used to run silently,
  // and a timeline that had not refreshed read as "it did not sync".
  useEffect(() => {
    let alive = true, sawRunning = false;    // local, not state: the closure would freeze state
    const watch = async () => {
      try {
        const { data } = await api.get("/api/ingest/status");
        if (!alive) return;
        if (data.everyMinutes != null) setEvery(data.everyMinutes);
        if (data.status?.state === "running") {
          sawRunning = true;
          // background catch-up: say so and keep polling, but never dim rows that are already
          // real - a readable timeline behind a working banner, not a page that looks loading
          setBgSync(true); setSyncWhat(data.status.what || "");
          // ...and SHOW what has landed so far. Ingest writes each message the moment it has
          // it, oldest first, so the rows were already arriving one at a time - the timeline
          // just was not asking until the whole poll finished. A three-day catch-up sat behind
          // a spinner for minutes with a database filling up behind it.
          load(rowsLen.current);
          setTimeout(watch, 2000);
        } else if (sawRunning) {
          setBgSync(false); setSyncWhat(""); setLastSync(new Date()); load(rowsLen.current);
        }
      } catch { if (alive) { setBgSync(false); setSyncWhat(""); } }
    };
    watch();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setRows(null); rowsLen.current = 0; setNoMore(false);
    etagRef.current = "";                        // a new filter is not the same page
    setSel(null); setEditText("");   // filter switch: never leave a stale review panel up
    load();
    // Rows only. The INGEST clock moved to the server (server.poll_forever): living here it
    // died the moment you opened another tab, and restarted its ten minutes every time a
    // filter changed this effect's dependencies - so "auto-syncs every 10 min" was a promise
    // kept only by someone sitting on the Timeline, and never when the window was closed.
    return active ? pollWhileVisible(() => load(rowsLen.current), 30000) : undefined;
  }, [load, active]);
  useEffect(() => {
    // root: the RAIL. A viewport-rooted observer never fires for a sentinel inside a scroll
    // container that is already fully on screen - the list would simply stop at 100 rows.
    const obs = new IntersectionObserver(([e]) => e.isIntersecting && loadMore(), { root: railRef.current });
    if (endRef.current) obs.observe(endRef.current);
    return () => obs.disconnect();
  }, [loadMore]);
  useEffect(() => { (rows || []).forEach((r) => seen.current.add(r.MessageId)); }, [rows]);

  // Hovering a line opens it in the review panel after a SHORT rest (120ms: 260 read as lag, 0
  // made the panel flicker through every row you scrolled past); click pins it. A draft mid-edit
  // locks the panel in place. Rows sliding under a STILL cursor fire mouseenter too - that is
  // scrolling, not hovering, so nothing opens until the mouse itself moves again.
  const lastScroll = useRef(0);
  const hoverArmed = useRef(true);
  useEffect(() => {
    const rail = railRef.current; if (!rail) return undefined;
    let stopped = null;
    const h = () => {
      lastScroll.current = Date.now(); clearTimeout(hoverTimer.current);
      // Scrolling moves rows under a stationary pointer. Keep hover locked even after the wheel
      // settles; only an intentional pointer move should make a newly arrived email react.
      hoverArmed.current = false;
      rail.dataset.tqScrolling = "true";
      rail.dataset.tqHoverLocked = "true";
      clearTimeout(stopped);
      stopped = setTimeout(() => { delete rail.dataset.tqScrolling; }, 120);
    };
    rail.addEventListener("scroll", h, { passive: true });
    return () => { rail.removeEventListener("scroll", h); clearTimeout(stopped);
      delete rail.dataset.tqScrolling; delete rail.dataset.tqHoverLocked; };
  }, []);
  const [sel, setSel] = useState(null);
  const [sendErr, setSendErr] = useState("");     // approved, but the channel refused it
  const hoverTimer = useRef(null);
  const want = useRef(null);                    // newest selection wins if fetches land out of order
  // `quiet` is the hover path: the panel keeps showing the row you were on until the next one's
  // detail has ARRIVED, then header and body swap in one render. Clearing the detail first
  // meant every hover flashed a spinner in the panel before filling it - sweeping down a list
  // of tasks read as the page labouring (the owner, 2026-08-30). A click still switches at once.
  // Details are fetched the moment the cursor ENTERS a row and kept for a minute, so by the time
  // the short rest is over the body is usually already here - hover felt slow when the fetch only
  // started after the rest. (no task = report / filed / ignored: the message itself, whole - the
  // feed row only carries a truncated preview.)
  const cache = useRef(new Map());
  const fetchDetail = (row) => {
    const hit = cache.current.get(row.MessageId);
    if (hit && Date.now() - hit.at < 60000) return hit.p;
    // ...and a row with no task gets its whole CONVERSATION, not just itself. A chat is a
    // conversation by nature: showing one line of it hid every reply the owner sent from Teams
    // or Outlook, which is ingested as a `context` row and which the assistant has been reading
    // all along. The panel was the only place the history looked incomplete.
    const p = (row.TaskId ? api.get(`/api/tasks/${row.TaskId}`).then((r) => r.data)
      : api.get(`/api/messages/${row.MessageId}/thread`).then((r) => ({ messages: r.data.messages || [],
          routes: r.data.routes || [] })))
      .catch(() => ({ messages: [] }));                                  // panel falls back to the preview
    cache.current.set(row.MessageId, { at: Date.now(), p });
    return p;
  };
  // pinned = you CLICKED it: it stays until you click something else or the page ground. A hover
  // selection is transient - it closes when the cursor leaves the list and the panel.
  const pinned = useRef(false);
  const [pinnedOn, setPinnedOn] = useState(false);
  const setPinned = (v) => { pinned.current = v; setPinnedOn(v); };
  const drill = async (row, quiet = false) => {
    if (quiet && pinned.current && sel?.MessageId === row.MessageId) return;   // pinned outranks hover
    if (!quiet) clearTimeout(hoverTimer.current);
    setCalSel(null);   // a message row takes the panel back from an opened meeting
    want.current = row.MessageId; setPinned(!quiet);
    const p = fetchDetail(row);
    if (!quiet) { setSel(row); setDetail(null); setEditText(null); setSendErr(""); setPanelLock(false); }
    const d = await p;
    if (want.current !== row.MessageId) return;                          // a newer hover won
    if (quiet) { setSel(row); setEditText(null); setSendErr(""); setPanelLock(false); }
    setDetail(d);
  };
  // Transcription replaces the message body in place. Reflect the returned body immediately,
  // and invalidate the minute-long detail cache so reopening cannot resurrect the placeholder.
  const messageBodyChanged = useCallback((mid, body) => {
    cache.current.delete(mid);
    setRows((cur) => (cur || []).map((r) => r.MessageId === mid ? { ...r, Preview: body } : r));
    setSel((cur) => cur?.MessageId === mid ? { ...cur, Preview: body } : cur);
    setDetail((cur) => cur ? { ...cur, messages: (cur.messages || []).map((m) =>
      m.MessageId === mid ? { ...m, BodyText: body } : m) } : cur);
    load(rowsLen.current);
  }, [load]);
  // leaving: a hover-opened row and its panel close 400ms after the cursor has left both the list
  // and the panel (the gap between them is crossed in well under that); a clicked one stays
  const leaveTimer = useRef(null);
  const disarmClose = () => clearTimeout(leaveTimer.current);
  const armClose = () => {
    clearTimeout(leaveTimer.current);
    if (pinned.current || narrow) return;
    leaveTimer.current = setTimeout(() => {
      if (!pinned.current && !panelLock && !(editText ?? "").trim()) { clearTimeout(hoverTimer.current); setSel(null); }
    }, 400);
  };
  // A verdict being TYPED locks the panel the same way a draft does. It did not, and a sync
  // is when it hurts: rows arrive at the top every two seconds, the list slides under a
  // stationary cursor, hover selects whatever moved into place, and the panel - keyed on the
  // selected message - took the half-written "not our task" note down with it.
  const [panelLock, setPanelLock] = useState(false);
  const hoverSelect = (row) => {
    clearTimeout(hoverTimer.current);
    if (narrow) return;                                 // a phone taps; the drawer opens on the tap
    if (!hoverArmed.current) return;
    if (sel?.MessageId === row.MessageId) return;
    if (sel && ((editText ?? "").trim() || panelLock)) return;   // don't yank an OPEN panel mid-edit
    // a meeting you CLICKED stays until you click something else; one that opened on hover gives
    // way to the next hover like any row - otherwise the panel stuck on the first meeting
    if (calSel?.pinned) return;
    if (Date.now() - lastScroll.current < 250) return;
    disarmClose(); fetchDetail(row);                                      // start the fetch now, commit after the rest
    hoverTimer.current = setTimeout(() => drill(row, true), 70);
  };
  const hoverCancel = () => clearTimeout(hoverTimer.current);
  // Clicking the page ground closes the panel AND collapses the selected row. Whatever was
  // last opened used to stay up until you opened something else - there was no way to just
  // put it down. Rows, the panel, the dock and any popover/dialog are exempt (they handle
  // their own clicks); a draft or verdict mid-edit holds the panel like it holds against hover.
  useEffect(() => {
    if (!sel && !calSel) return undefined;
    const h = (e) => {
      if (e.target.closest?.("[data-tq-keep], .MuiPopover-root, .MuiModal-root, #tqTopNav")) return;
      if (panelLock || (editText ?? "").trim()) return;
      clearTimeout(hoverTimer.current); setPinned(false); setSel(null); setCalSel(null);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [sel, calSel, panelLock, editText]);

  // Approving IS sending, so a refusal has to land in front of you now - not as a NOT SENT line
  // in the task history that you find tomorrow. The panel stays open when the send failed.
  const decide = async (reviewId, verb, finalText) => {
    const { data } = await api.post(`/api/reviews/${reviewId}/decide`, { verb, final_text: finalText || null });
    if (data?.send_error) { setSendErr(data.send_error); load(); onChanged?.(); return; }
    setSendErr(""); setSel(null); setEditText(null);   // stale edits must never block hover
    load(); onChanged?.();
  };

  // Strict newest-first by sent time (UTC strings compare correctly), then group by local day.
  // The category is enforced here too: whatever the request returned, a row outside the
  // picked category never renders under its pill (mail was showing under "code").
  const catChans = channelsForCategory(cat, Object.keys(srcByChannel));
  // a prep row is drawn BY its meeting (MeetingRow), so it must not also be drawn as a line of
  // its own - keyed on the conversation id server.prep_key gave it
  const prepFor = {};
  for (const r of rows || []) {
    const cid = String(r.ConversationId || "");
    if (cid.startsWith("calendar:")) (prepFor[cid] = prepFor[cid] || []).push(r);
  }
  const sorted = [...(rows || [])]
    .filter((r) => !String(r.ConversationId || "").startsWith("calendar:"))
    .filter((r) => !catChans || catChans.includes(r.Channel))
    .sort((a, b) => (b.SentAt || "").localeCompare(a.SentAt || ""));
  const days = sorted.reduce((acc, r) => {
    const d = localDay(r.SentAt) || "undated";
    (acc[d] = acc[d] || []).push(r);
    return acc;
  }, {});
  // Once its start time arrives, a meeting becomes normal Timeline history at that timestamp.
  // Give it a day even when no messages arrived that day; otherwise the calendar row would vanish
  // from both the upcoming band and the stream.
  const { upcoming, started: timelineMeetings } = splitTimelineMeetings(calEvents, Date.now(), tsMs);
  timelineMeetings.forEach((e) => {
    const day = localDay(e.start);
    if (day && !days[day]) days[day] = [];
  });
  // With no messages yet, a calendar-only day still needs a group in which to render its upcoming
  // band. `/calendar/today` only returns this day, so the first event is the correct heading.
  if (!Object.keys(days).length && calEvents.length) {
    const day = localDay(calEvents[0].start);
    if (day) days[day] = [];
  }
  const dayEntries = Object.entries(days).sort(([a], [b]) => b.localeCompare(a));
  // ONE TASK, ONE ROW. Not one conversation: on a report, on the assistant's posts and in a
  // WhatsApp chat the conversation id is the CHANNEL, so grouping on it collapsed five runs of
  // one report, twelve assistant posts and a day of one person into single lines - and hid a
  // photo the owner was hunting for. A task is the honest unit: triage or a thread put those
  // messages together. Rows nothing has judged to be one thing never fold.
  const foldOf = new Map(), memberOf = new Map();
  for (const [, dayRows] of dayEntries) {
    for (const e of groupThreads(dayRows)) {
      if (e.kind !== "fold") continue;
      foldOf.set(e.row.MessageId, e);                 // the newest member is where the fold sits
      for (const m of e.rows) memberOf.set(m.MessageId, e.tid);
    }
  }
  const shownDay = dayEntries.some(([day]) => day === curDay) ? curDay : (dayEntries[0]?.[0] || "");
  const jumpToDay = (day) => {
    dateJump.current = day;
    clearTimeout(dateJumpTimer.current);
    setCurDay(day);
    requestAnimationFrame(() => {
      const rail = railRef.current, group = dayRefs.current[day];
      if (!rail || !group) return;
      const top = rail.scrollTop + group.getBoundingClientRect().top - rail.getBoundingClientRect().top;
      rail.scrollTo({ top: Math.max(0, top - 4), behavior: "smooth" });
    });
    // Browser smooth scrolling is normally ~500ms. Keep the explicit choice authoritative
    // through that motion; the next manual wheel/drag uses the regular day spy again.
    dateJumpTimer.current = setTimeout(() => { dateJump.current = ""; }, 850);
  };
  // the started meetings that belong between message i-1 and message i of a day (newest-first), or
  // after the oldest message of the day when i === items.length
  const meetingsAt = (day, items, i) => {
    const hi = i === 0 ? Infinity : tsMs(items[i - 1].SentAt), lo = i >= items.length ? -Infinity : tsMs(items[i].SentAt);
    return timelineMeetings.filter((e) => localDay(e.start) === day && tsMs(e.start) < hi && tsMs(e.start) >= lo);
  };

  // only offer channels that actually have a connection behind them. With no category
  // picked, EVERY connected channel is offered - a hardcoded five-channel list here
  // silently hid telegram/whatsapp/jira/... sources from the picker as connectors grew
  const availableChannels = [...new Set([...Object.keys(srcByChannel), ...(rows || []).map((r) => r.Channel)])];
  const pickerChannels = availablePickerChannels(cat, availableChannels);

  const today = new Date().toLocaleDateString("sv-SE");
  const todays = (rows || []).filter((r) => localDay(r.SentAt) === today);
  // meetings are rows too. Counting only messages meant the rail showed three lines under a
  // heading that said two - the invite was on screen and in no total.
  const todayMeetings = timelineMeetings.filter((e) => localDay(e.start) === today).length;
  const stats = [{ label: "in today", n: todays.length + todayMeetings, f: "" }, ...[
    { label: "auto", n: todays.filter((r) => r.ReviewStatus === "auto").length, f: "" },
    ...(narrow ? [] : [{ label: "needs me", n: (rows || []).filter(needsYou).length, f: "pending", hot: true }]),
    { label: "info", n: todays.filter((r) => r.Category === "info").length, f: "" },
    { label: "promo", n: todays.filter((r) => r.Category === "promo").length, f: "" },
    { label: "ignored", n: todays.filter((r) => r.MsgStatus === "ignored").length, f: "" },
  ].filter((s) => s.n > 0)];

  return (
    // THE RAIL AND THE STAGE. The Timeline used to be the page - the window scrolled it, its
    // filters floated over the whole width, and the task sat in a sticky column beside it. But
    // the list is not the subject of this screen: the task is. So the list becomes a rail with
    // its own header and its own scrollbar, and the rest of the window belongs to whatever is
    // open. Both columns are full height and neither one scrolls the page.
    <Box sx={{ display: "grid", columnGap: 1.75, alignItems: "stretch", width: "100%",
      height: `calc(100vh - ${navH}px - 22px)`, minHeight: 420,
      // 500px of rail: enough that a real subject line is readable before you open anything,
      // which is the whole job of a one-line row. Everything else goes to the stage, which holds
      // a whole message, the agent's work and the draft.
      gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 500px) minmax(0, 1fr)" },
      mt: { xs: -1.5, md: -2.25 }, pt: { xs: 1.5, md: 2 } }}>

      {/* ── the rail ────────────────────────────────────────────────────────────── */}
      <Box data-tq-keep onMouseEnter={disarmClose} onMouseLeave={armClose}
        sx={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden", position: "relative",
          bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>

        {/* the header. Frozen by construction now rather than by position:sticky - it is a
            flex sibling of the scroller, so nothing can slide over it and nothing has to be
            measured to keep it out of the way. */}
        <Box sx={{ flexShrink: 0, bgcolor: "transparent",
          px: 1.5, py: 1.25, display: "flex", flexDirection: "column", gap: 1 }}>

          {/* filters: one segmented control for STATE, one quiet picker for WHERE FROM. Two
              rows of loose pills of two different kinds read as a settings panel, not a filter. */}
          {/* wraps: on a phone the pickers and New drop to a second row as one group, under the
              pill, instead of the whole row scrolling sideways */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: "wrap" }}>
            {narrow
              ? <NeedsMe on={view === "pending"} n={(rows || []).filter(needsYou).length}
                  onClick={() => setView(view === "pending" ? "" : "pending")} />
              : <FilterPills options={VIEW_FILTERS} value={view} onChange={setView} />}
            {/* on a phone the pickers take a full second line and New sits beside the pill; from md
                up the three share one line, right-aligned */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, ml: { md: "auto" }, minWidth: 0,
              order: { xs: 3, md: 2 }, flex: { xs: "1 1 100%", md: "0 0 auto" },
              "& > .MuiInputBase-root": { flex: { xs: 1, md: "0 0 auto" } } }}>
            <Select size="small" value={cat} displayEmpty onChange={(e) => setCat(e.target.value)}
              inputProps={{ "aria-label": "Timeline category" }}
              renderValue={(v) => CATEGORIES.find((o) => o.key === v)?.label || "all kinds"}
              sx={{ height: 34, fontSize: 11.5, fontWeight: 600, borderRadius: 2, bgcolor: PANEL2,
                color: cat ? INK : DIM, flexShrink: 0,
                "& .MuiSelect-select": { py: 0.25, px: 1.15 },
                "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER } }}>
              {CATEGORIES.map((o) => <MenuItem key={o.key} value={o.key} sx={{ fontSize: 12 }}>{o.label}</MenuItem>)}
            </Select>
            <Select size="small" value={pickerChannels.length ? pick : ""} displayEmpty onChange={(e) => setPick(e.target.value)}
              onClose={() => setSrcQ("")}
              inputProps={{ "aria-label": "Timeline source" }}
              MenuProps={{ PaperProps: { sx: { maxHeight: 440, maxWidth: 420 } } }}
              renderValue={(v) => (!v ? "all sources"
                : v.startsWith("channel:") ? `all ${CHANNEL_LABELS[v.slice(8)] || v.slice(8)}`.toLowerCase()
                  : String(v.split(":").slice(2).join(":")).split("@")[0])}
              sx={{ height: 34, fontSize: 11.5, fontWeight: 600, borderRadius: 2, bgcolor: PANEL2,
                color: pick ? INK : DIM, flex: { xs: 1, md: "0 0 104px" }, width: { md: 104 }, minWidth: 104, maxWidth: { md: 104 },
                "& .MuiSelect-select": { py: 0.25, px: 1.15 },
                "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER } }}>
              {/* 96 discovered buckets turned this into a page-long wall. It is a bounded,
                  searchable list: type to narrow, and each channel shows a few with a count
                  for the rest rather than every object it has ever seen. */}
              <Box sx={{ px: 1, pt: 0.5, pb: 0.75, position: "sticky", top: 0, bgcolor: PANEL, zIndex: 2 }}
                onKeyDown={(e) => e.stopPropagation()}>
                <TextField autoFocus fullWidth placeholder="search sources…" value={srcQ}
                  onChange={(e) => setSrcQ(e.target.value)} sx={{ bgcolor: "#fff" }}
                  inputProps={{ style: { fontSize: 12, padding: "5px 8px" } }} />
              </Box>
              <MenuItem value="" sx={{ fontSize: 12 }}>all sources</MenuItem>
              {pickerChannels.flatMap((ch) => {
                const q = srcQ.trim().toLowerCase();
                const all = (srcByChannel[ch] || []).filter((n) => !q || String(n).toLowerCase().includes(q));
                const label = CHANNEL_LABELS[ch] || ch;
                if (q && !all.length && !label.toLowerCase().includes(q)) return [];
                const shown = q ? all.slice(0, 12) : all.slice(0, 6);
                return [
                  <ListSubheader key={`h${ch}`} sx={{ fontSize: 9.5, lineHeight: 1.9, color: FAINT, letterSpacing: 1,
                    textTransform: "uppercase", bgcolor: PANEL }}>
                    {label}{all.length > shown.length ? ` · ${all.length}` : ""}
                  </ListSubheader>,
                  <MenuItem key={`c${ch}`} value={`channel:${ch}`} sx={{ fontSize: 12 }}>
                    all {label.toLowerCase()}
                  </MenuItem>,
                  ...shown.map((n) => (
                    <MenuItem key={`${ch}:${n}`} value={`src:${ch}:${n}`} sx={{ fontSize: 11.5, pl: 2.5, maxWidth: 400 }}>
                      <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n}</Box>
                    </MenuItem>
                  )),
                  ...(all.length > shown.length ? [
                    <MenuItem key={`m${ch}`} disabled sx={{ fontSize: 10.5, pl: 2.5, color: FAINT, opacity: 1 }}>
                      +{all.length - shown.length} more — type to find one
                    </MenuItem>] : []),
                ];
              })}
            </Select>
            {/* New starts work, so it stays visually distinct, but it belongs on this toolbar —
                not alone on a wasteful row above it. */}
            </Box>
            <Button size="small" variant="contained" disableElevation onClick={() => setNewOpen(true)}
              startIcon={<AddIcon sx={{ fontSize: 15 }} />}
              sx={{ flexShrink: 0, height: 34, minWidth: 68, py: 0.25, px: 1.1, borderRadius: 2,
                fontSize: 11.5, background: GRADIENT, order: { xs: 2, md: 3 }, ml: { xs: "auto", md: 0 } }}>New</Button>
          </Box>

          {/* The counts describe what is in the rail. The date and sync clock belong together
              below them: date first, centered over the quieter sync status/action. */}
          {rows && (
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap", justifyContent: "center" }}>
              {stats.map((s) => (
                <Box key={s.label} onClick={() => s.f && setView(s.f)}
                  sx={{ display: "flex", alignItems: "baseline", gap: 0.4, cursor: s.f ? "pointer" : "default",
                    ...(s.f ? { "&:hover .thubStatLbl": { color: ALERT_INK } } : {}) }}>
                  <Typography sx={{ fontWeight: 700, fontSize: 11.5,
                    color: s.hot && s.n ? ALERT_INK : INK }}>{s.n}</Typography>
                  <Typography className="thubStatLbl" variant="caption" sx={{ color: FAINT, fontSize: 10.5, transition: "color .15s" }}>{s.label}</Typography>
                </Box>
              ))}
            </Box>
          )}
          {/* a brain that errors on every call used to look like slow triage: rows parked on
              "triaging…" and nothing saying why. The last error stays until it answers again. */}
          {triageErr && !syncing && !bgSync && (
            <Typography variant="caption" noWrap title={triageErr} sx={{ color: ALERT_INK, fontWeight: 700, fontSize: 10.5 }}>
              triage brain failing — {triageErr}
            </Typography>
          )}
          {err && (
            <Alert severity="error" variant="outlined" onClose={() => setErr("")}
              action={<Button size="small" color="error" onClick={() => { setErr(""); setRows(null); load(rowsLen.current); }}
                sx={{ fontSize: 11 }}>Retry</Button>}
              sx={{ py: 0, borderRadius: 2, bgcolor: PANEL, alignItems: "center",
                "& .MuiAlert-message": { fontSize: 11.5, py: 0.5 }, "& .MuiAlert-action": { pt: 0, alignItems: "center" } }}>
              {err}
            </Alert>
          )}
          {/* Sync belongs to the controls above. The moving date is the label for the rows, so it
              must be the final thing in the dock — otherwise scrolling changes a heading that
              appears to describe the sync line beneath it. */}
          <Box sx={{ minHeight: 20, display: "flex", justifyContent: "center", alignItems: "center", gap: 0.25 }}>
            <Typography variant="caption" noWrap sx={{ color: syncing || bgSync ? ACCENT : FAINT, fontSize: 10.5 }}>
              {syncing || bgSync ? (syncWhat || "syncing…")
                : !every ? "background sync off"
                : `synced ${lastSync ? lastSync.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "—"}`
                  + (nextIn == null ? "" : nextIn <= 0 ? " · next sync due now" : ` · next in ${Math.floor(nextIn / 60)}:${String(nextIn % 60).padStart(2, "0")}`)}
            </Typography>
            <Button size="small" variant="text" disabled={syncing || bgSync} onClick={() => syncNow(false)}
              title={syncing || bgSync ? syncWhat : "read the mailboxes, chats and repos now"}
              startIcon={<SyncIcon data-tq-sync-icon sx={{ fontSize: 12,
                color: syncing || bgSync ? ACCENT : "inherit",
                ...(syncing || bgSync ? { animation: "tqSyncSpin .8s linear infinite" } : {}) }} />}
              sx={{ minWidth: 0, minHeight: 20, py: 0, px: 0.6, ml: 0.35, fontSize: 10.5,
                lineHeight: 1.2, whiteSpace: "nowrap", color: DIM,
                "@keyframes tqSyncSpin": { to: { transform: "rotate(360deg)" } },
                "&.Mui-disabled": { color: DIM, opacity: 1 },
                "& .MuiButton-startIcon": { mr: 0.35 }, "&:hover": { bgcolor: PANEL2 } }}>
              {syncing || bgSync ? "Syncing" : "Sync now"}
            </Button>
          </Box>
          {/* The heading is also navigation: choose any day already in this Timeline and the
              rail glides to its first item. It stays typographically a date, not another pill. */}
          <Select value={shownDay} onChange={(e) => jumpToDay(e.target.value)} variant="standard" disableUnderline
            displayEmpty inputProps={{ "aria-label": "Timeline date" }}
            IconComponent={(props) => <ChevronRightIcon {...props} sx={{ ...props.sx, fontSize: 14,
              transform: "rotate(90deg)", color: `${FAINT} !important`, right: 1 }} />}
            renderValue={(day) => fmtDay(day)}
            sx={{ ...mono, color: INK, fontWeight: 700, fontSize: 11.5, letterSpacing: 0.3,
              minWidth: 0, maxWidth: "100%", height: 22, textAlign: "center", cursor: "pointer",
              "& .MuiSelect-select": { py: 0, pl: 2, pr: "22px !important", textAlign: "center" },
              "&:hover": { color: ACCENT } }}>
            {dayEntries.map(([day]) => (
              <MenuItem key={day} value={day} sx={{ ...mono, fontSize: 11.5 }}>{fmtDay(day)}</MenuItem>
            ))}
          </Select>
        </Box>

        {/* ── the scroller ── */}
        <Box ref={railRef}
          onPointerMoveCapture={() => {
            // Capture runs before the row's mousemove. The first real pointer move after the rail
            // settles arms that row; wheel movement by itself never does.
            if (!hoverArmed.current && Date.now() - lastScroll.current >= 120) {
              hoverArmed.current = true;
              delete railRef.current?.dataset.tqHoverLocked;
            }
          }}
          onPointerLeave={() => {
            hoverArmed.current = true;
            delete railRef.current?.dataset.tqHoverLocked;
          }}
          sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden",
          position: "relative", px: 1, pt: 1, pb: 3,
          "&[data-tq-scrolling='true'] .tqRow [data-tq-keep]": {
            transition: "none !important",
          },
          "&[data-tq-hover-locked='true'] .tqRow [data-tq-open='false'], &[data-tq-hover-locked='true'] .tqRow [data-tq-open='false']:hover": {
            borderColor: `${BORDER} !important`, borderLeftColor: "var(--tq-row-edge) !important",
            boxShadow: "none !important", transition: "none !important", cursor: "default",
          } }}>
          <FunnelBar onOpenTask={onOpenTask} />
          <Box sx={{ position: "relative", opacity: syncing ? 0.55 : 1, transition: "opacity .25s" }}>
            {syncing && (
              <Box sx={{ position: "absolute", inset: 0, zIndex: 4, display: "flex",
                alignItems: "flex-start", justifyContent: "center", pointerEvents: "none" }}>
                <CircularProgress size={22} sx={{ mt: 8 }} />
              </Box>
            )}
            {!rows ? (err ? null : <CircularProgress size={20} sx={{ m: 4 }} />) : !sorted.length && !calEvents.length ? (
              <Empty>{view || cat || pick
                ? "Nothing here matches this filter — try “everything”, or widen the Timeline lookback in Settings."
                : "Nothing in the feed yet — connect a source in Connections (a mailbox, a chat, a repo, a board…) and hit Sync now."}</Empty>
            ) : dayEntries.map(([day, items], di) => (
              // the group's top edge is what the date spy watches - no header row of its own
              <Box key={day} sx={{ mt: di ? 1.25 : 0.5 }} ref={(el) => {
                if (el) dayRefs.current[day] = el; else delete dayRefs.current[day];
                dayLayoutDirty.current = true;
              }}>
                {di === 0 && !view && !cat && !pick && <ComingUp events={upcoming} picked={calSel} onPick={(e) => { setSel(null); setCalSel(e); }} />}
                <Box>
                  {items.map((r, i) => {
                    // ONE state per row, from one table (timelineState.js). It renders as a small
                    // mark, its word in quiet type, and the card's LEFT EDGE in the state's colour -
                    // a coloured pill on every row makes the whole column loud, which is the same
                    // as making none of it loud.
                    const st = stateOf(r);
                    const fold = foldOf.get(r.MessageId);
                    const inFold = memberOf.get(r.MessageId);
                    // A member is never drawn HERE, open or shut - the fold draws its own, in one
                    // block. Revealing them in place looked right until a fold opened: its members
                    // are not contiguous, so an unrelated row landing between two of them (a CI
                    // email in the same minute as two chat lines) appeared inside the group.
                    // display:none rather than skipping the entry, because the meeting slots are
                    // placed by INDEX into this day's rows and dropping one would move them.
                    const showRow = !inFold;
                    const open = sel?.MessageId === r.MessageId;
                    // hovering PREVIEWS (a soft edge, the stage follows the cursor); clicking
                    // PINS (a ring in the brand colour, the stage holds). Both used to draw the
                    // same border, so there was no way to know which one you were in.
                    const held = open && pinnedOn;
                    return (
                      <React.Fragment key={r.MessageId}>
                        {/* the calendar is filtered like everything else. "needs me" means work waiting on
                            you, and a meeting is never that - it sat in the list regardless, so a
                            filter that should have shown three rows showed four. */}
                        {!view && !cat && !pick && meetingsAt(day, items, i).map((e, j) => (
                          <MeetingRow key={`m-${e.start}-${j}`} e={e} picked={calSel}
                            preps={prepFor[evKey(e)] || []} onOpenRow={(p) => { setCalSel(null); drill(p); }}
                            onPick={(ev) => { setSel(null); setCalSel(ev); }} />
                        ))}
                        {fold && (
                          <ThreadFold entry={fold} open={openFolds.has(fold.tid)} onOpenRow={drill} sel={sel}
                            onToggle={() => setOpenFolds((cur) => {
                              const next = new Set(cur);
                              if (next.has(fold.tid)) next.delete(fold.tid); else next.add(fold.tid);
                              return next;
                            })} />
                        )}
                        <Box className="tqRow" sx={{ display: showRow ? "grid" : "none", gridTemplateColumns: `${GUTTER}px 14px minmax(0,1fr)`,
                          alignItems: "stretch", mb: "3px",
                          ...(seen.current.has(r.MessageId) ? {} : { ...fadeIn, animationDelay: `${Math.min(i * 35, 320)}ms`, animationFillMode: "backwards" }) }}>
                          {/* the clock sits in its own gutter with air on BOTH sides - 8px off the
                              container edge, 12px off the rail - so it never reads as crushed
                              against the frame the way a flush-left column does */}
                          <Typography sx={{ ...mono, fontSize: 10, color: FAINT, textAlign: "right",
                            pt: "6px", pl: "8px", pr: "12px", whiteSpace: "nowrap", letterSpacing: "-.2px",
                            fontVariantNumeric: "tabular-nums" }}>
                            {fmtTime12(r.SentAt)}
                          </Typography>
                          {/* rail + dot: the dot repeats the state's colour at scanning size */}
                          <Box sx={{ position: "relative" }}>
                            <Box sx={{ position: "absolute", left: "6px", top: "-5px", bottom: "-5px", width: "1px", bgcolor: BORDER }} />
                            <Box sx={{ position: "absolute", left: "2.5px", top: "9px", width: 8, height: 8, borderRadius: "50%",
                              bgcolor: edgeOf(st), boxShadow: `0 0 0 3px ${PANEL}` }} />
                          </Box>
                          {/* ONE LINE until this is the row you are on. Hover selects it after a
                              short rest and unfolds a second line; click pins it. It used to
                              unfold on hover alone, and a cursor sweeping the list heaved every
                              row below it. */}
                          <Box data-tq-keep data-tq-open={open ? "true" : "false"} onClick={() => drill(r)}
                            onMouseMove={() => hoverSelect(r)} onMouseLeave={hoverCancel}
                            sx={{ "--tq-row-edge": edgeOf(st), bgcolor: ["ignored", "filed", "withdrawn"].includes(r.MsgStatus) ? "#faf8f4" : PANEL,
                              border: `1px solid ${BORDER}`, borderLeft: `2px solid ${edgeOf(st)}`,
                              borderRadius: "8px", px: "10px", pt: "3px", pb: "4px", ml: "8px",
                              minWidth: 0, overflow: "hidden",
                              transition: "box-shadow .18s, border-color .18s",
                              ...(open ? { borderColor: held ? ACCENT : "#d8cfbe", borderLeftColor: edgeOf(st),
                                boxShadow: held ? `inset 0 0 0 1px ${ACCENT}, 0 2px 10px rgba(47,107,79,.14)`
                                                : "0 1px 3px rgba(30,50,38,.08)" } : {}),
                              "&:hover": { borderColor: held ? ACCENT : "#d8cfbe", borderLeftColor: edgeOf(st),
                                boxShadow: held ? `inset 0 0 0 1px ${ACCENT}, 0 2px 10px rgba(47,107,79,.14)`
                                                : "0 2px 8px rgba(47,107,79,.10)", cursor: "pointer" } }}>
                            <Box sx={{ display: "flex", gap: 0.85, alignItems: "center", minWidth: 0, minHeight: 22 }}>
                              {/* where it came from stays a LOGO, not a glyph - the channel is an
                                  identity and the app already draws it everywhere else */}
                              <Box sx={{ display: "flex", flexShrink: 0 }}>
                                <ChannelIcon channel={r.Channel} sx={{ fontSize: 16 }} />
                              </Box>
                              <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: ["ignored", "filed", "withdrawn"].includes(r.MsgStatus) ? DIM : INK,
                                fontSize: 12, letterSpacing: "-.1px", maxWidth: 118, minWidth: 0, flexShrink: 0 }}>
                                {r.FromName || r.FromEmail || "unknown"}
                              </Typography>
                              <Typography variant="body2" noWrap sx={{ color: DIM, fontSize: 11.5, flex: 1, minWidth: 0 }}>
                                {subjectOf(r) || ""}
                              </Typography>
                              {r.Attachments > 0 && (
                                <AttachFileIcon titleAccess={`${r.Attachments} attached`} sx={{ fontSize: 13, color: FAINT, flexShrink: 0 }} />
                              )}
                              {r.Direction === "out" && (
                                <Typography variant="caption" title="Taskuary sent this"
                                  sx={{ ...mono, fontSize: 9.5, color: ACCENT, flexShrink: 0 }}>out</Typography>
                              )}
                              <StateMark row={r} state={st} />
                            </Box>
                            {/* the second line, only on the row you are on: who has it and what
                                it is waiting for, every clause from a field the server sent */}
                            <Box sx={{ display: "grid", gridTemplateRows: open ? "1fr" : "0fr", transition: "grid-template-rows .2s ease" }}>
                              <Box sx={{ overflow: "hidden" }}>
                                <Typography noWrap sx={{ fontSize: 10.5, lineHeight: 1.5, pt: "2px", pl: "24px",
                                  color: FAINT }}>{subline(r, ref)}</Typography>
                                {r.Preview && (
                                  <Typography noWrap sx={{ fontSize: 10.5, lineHeight: 1.5, pl: "24px", color: DIM }}>
                                    “{r.Preview}”
                                  </Typography>
                                )}
                              </Box>
                            </Box>
                          </Box>
                        </Box>
                      </React.Fragment>
                    );
                  })}
                  {/* meetings that started before the oldest message of the day shown so far */}
                  {!view && !cat && !pick && meetingsAt(day, items, items.length).map((e, j) => (
                    <MeetingRow key={`m-${e.start}-${j}`} e={e} picked={calSel}
                            preps={prepFor[evKey(e)] || []} onOpenRow={(p) => { setCalSel(null); drill(p); }}
                            onPick={(ev) => { setSel(null); setCalSel(ev); }} />
                  ))}
                </Box>
              </Box>
            ))}
            {/* infinite-scroll sentinel: crossing it loads the next page */}
            <Box ref={endRef} sx={{ height: 8 }} />
            {!!sorted.length && !noMore && <CircularProgress size={16} sx={{ display: "block", mx: "auto", my: 1 }} />}
          </Box>
        </Box>
        {bottomFade && (
          <Box data-tq-bottom-fade={fade} aria-hidden sx={{
            position: "absolute", left: "1px", right: "1px", bottom: "1px", zIndex: 6,
            height: bottomFade.height, pointerEvents: "none",
            background: `linear-gradient(transparent, ${PANEL} ${bottomFade.solidAt}%)`,
          }} />
        )}
      </Box>

      {/* ── the stage: the task, which is what this screen is actually for ────────── */}
      <Box data-tq-keep onMouseEnter={disarmClose} onMouseLeave={armClose}
        sx={{ minWidth: 0, minHeight: 0, display: { xs: "none", md: "block" } }}>
        {calSel && !sel ? <EventPanel e={calSel} onClose={() => setCalSel(null)} onOpenTask={onOpenTask} />
          : sel ? (
            <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText}
              decide={decide} onOpenTask={onOpenTask} onClose={() => setSel(null)}
              onSkipped={() => { setSel(null); load(); onChanged?.(); }} onRefresh={() => load()}
              onMessageChanged={messageBodyChanged}
              sendErr={sendErr} clearSendErr={() => setSendErr("")} onLock={setPanelLock} />
          ) : (
            // an empty stage is not a broken one. It says what the rail is for and what the
            // one button on it does, which is the only thing a new install has to be told.
            <Box sx={{ height: "100%", border: `1px dashed ${BORDER}`, borderRadius: 2,
              display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
              gap: 1, px: 4, textAlign: "center" }}>
              <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: DIM }}>
                Pick anything on the left
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, maxWidth: 380, lineHeight: 1.6 }}>
                Hovering a row opens it here; clicking pins it. You get the message that arrived,
                why triage sent it where it did, what the agent is doing about it, and the reply
                waiting to go — each on its own tab.
              </Typography>
              <Button size="small" variant="outlined" startIcon={<AddIcon sx={{ fontSize: 15 }} />}
                onClick={() => setNewOpen(true)}
                sx={{ mt: 1, fontSize: 12, borderColor: BORDER, color: DIM }}>Start something instead</Button>
            </Box>
          )}
      </Box>

      {/* the same stage, over the rail, on a phone */}
      {narrow && (
        <Drawer anchor="right" open={!!(sel || calSel)} data-tq-keep
          onClose={() => { setPinned(false); setSel(null); setCalSel(null); }}
          PaperProps={{ sx: { width: "100%", p: 1, bgcolor: BG, borderRadius: 0 } }}>
          {calSel && !sel ? <EventPanel e={calSel} onClose={() => setCalSel(null)} onOpenTask={onOpenTask} />
            : sel ? (
              <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText}
                decide={decide} onOpenTask={onOpenTask} onClose={() => { setPinned(false); setSel(null); }}
                onSkipped={() => { setSel(null); load(); onChanged?.(); }} onRefresh={() => load()}
                onMessageChanged={messageBodyChanged}
                sendErr={sendErr} clearSendErr={() => setSendErr("")} onLock={setPanelLock} />
            ) : null}
        </Drawer>
      )}

      <NewSheet open={newOpen} onClose={() => setNewOpen(false)} onOpenTask={onOpenTask}
        onDone={() => { load(); onChanged?.(); }} />
    </Box>
  );
}

// Day rail label: "Today · Friday, Aug 14" / "Yesterday · ..." / "Thursday, Aug 13".
const fmtDay = (d) => {
  return timelineDayLabel(d);
};

// Compact what-happened rail: opened -> routed -> agent runs -> decisions -> closed,
// oldest first, with consecutive duplicates collapsed into one row with a ×N count.
const historyOf = (sel, detail) => {
  const ev = [];
  if (detail?.task) ev.push({ at: detail.task.CreatedAt, label: `Task ${detail.ref} opened`, sub: detail.task.Kind, c: "#55697a" });
  // An `ignore` route is the OWNER overruling triage - "not ours" - and it is the judgement
  // most worth reading back, because it is the one that taught the funnel something. It used to
  // vanish from the panel entirely: the verdict deletes the task, the history was read off the
  // task, so the record of the correction died with the thing it corrected.
  (detail?.routes || []).forEach((r) => ev.push({
    at: r.CreatedAt || detail?.task?.CreatedAt,
    c: r.Decision === "ignore" ? "#8a3646" : "#6f8a6e",
    label: r.Decision === "ignore" ? "You said: not ours"
      : r.Decision === "attach" ? "Routed — attached to this thread"
      : r.Decision === "create" ? "Routed — new task created" : `Routed — ${r.Decision}`,
    sub: r.Decision === "ignore"
      ? cleanText(String(r.Reason || "")).replace(/^not ours\s*[-—]\s*/i, "").slice(0, 70)
      : undefined,
  }));
  (detail?.runs || []).forEach((r) => ev.push({ at: r.StartedAt, label: `${r.AgentName} run`, sub: r.Status,
    c: r.Status === "error" ? "#6b2733" : "#6f8a6e" }));
  (detail?.comments || []).filter((c) => c.ActorType === "human").forEach((c) =>
    ev.push({ at: c.CreatedAt, label: c.Actor, sub: cleanText(c.Body).slice(0, 70), c: "#5e685f" }));
  if (sel.ReviewStatus && sel.ReviewStatus !== "pending") ev.push({ at: null, label: "You decided", sub: sel.ReviewStatus.replace("_", " "), c: "#47654a" });
  if (["done", "dropped"].includes(detail?.task?.Status)) ev.push({ at: detail.task.UpdatedAt, label: `Task ${detail.task.Status}`, c: "#47654a" });
  ev.sort((a, b) => String(a.at || "9").localeCompare(String(b.at || "9")));
  const out = [];
  for (const e of ev) {
    const last = out[out.length - 1];
    if (last && last.label === e.label && last.sub === e.sub) { last.n = (last.n || 1) + 1; last.at = e.at || last.at; }
    else out.push({ ...e });
  }
  return out;
};

// ONE button shape for the whole tray. It was four: a MUI contained, a MUI outlined, a
// ChoiceRow (a full-width tinted strip with an icon and a hint), and a bare Button - so the
// same row of controls had four heights, three corner radii and two type sizes, and nothing
// about the look told you which of them was the important one. These do: primary is the thing
// you came here to do, plain is the rest, quiet is the harmless exit, and teach is the one that
// changes what happens NEXT TIME - which is the distinction the tray never made.
const TRAY_BTN = {
  base: { textTransform: "none", fontWeight: 600, fontSize: 12, borderRadius: 2, height: 34,
    width: 190, px: 1.5, whiteSpace: "nowrap", boxShadow: "none", justifyContent: "flex-start" },
  primary: { color: "#fffdfb", background: GRADIENT, "&:hover": { filter: "brightness(1.06)", boxShadow: "none" } },
  plain: { color: DIM, bgcolor: PANEL, border: `1px solid ${BORDER}`, "&:hover": { borderColor: "#d8cfbe", bgcolor: PANEL } },
  quiet: { color: FAINT, bgcolor: "transparent", border: `1px dashed ${BORDER}`, fontWeight: 500,
    "&:hover": { borderColor: "#d8cfbe", bgcolor: PANEL } },
  teach: { color: "#5a3e83", bgcolor: "#f8f5fc", border: "1px solid #d9cbea",
    "&:hover": { bgcolor: "#f1eafa", borderColor: "#bca3d8" } },
};
const TrayBtn = ({ tone = "plain", icon, children, teaches, ...rest }) => (
  <Button size="small" disableElevation startIcon={icon} {...rest}
    sx={{ ...TRAY_BTN.base, ...TRAY_BTN[tone], ...(rest.sx || {}) }}>
    {children}
    {/* Spell the consequence out. A tiny dot was technically a legend, but nobody could infer
        that it meant this verdict changes later routing. */}
    {teaches && <Box component="span" aria-hidden
      sx={{ ml: 1, px: 0.65, py: 0.08, borderRadius: 0.8, bgcolor: "rgba(90,62,131,.1)",
        fontSize: 8.5, fontWeight: 800, letterSpacing: 0.7, lineHeight: 1.5 }}>MEMORY</Box>}
  </Button>
);

const TrayGroupLabel = ({ children, note }) => (
  <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, mb: 0.7 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.35, fontSize: 9.5,
      fontWeight: 800, lineHeight: 1 }}>{children}</Typography>
    {note && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5, lineHeight: 1 }}>{note}</Typography>}
  </Box>
);

const PanelLabel = ({ children }) => (
  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.8, fontSize: 10, fontWeight: 700,
    display: "block", mt: 1.75, mb: 0.25 }}>
    {children}
  </Typography>
);

// One quiet progress rail. Detail belongs in the four tabs, not repeated in a stack of cards.
// The whole stop is clickable so the summary remains a fast way into any stage.
const StoryTimelineStep = ({ title, status, summary, onOpen, first, last, state = "idle" }) => {
  const dot = state === "current" ? "#c7a258" : state === "done" ? "#718f74" : "#cfc8bc";
  return (
    <Box component="button" type="button" onClick={onOpen} aria-label={`Open ${title} details`}
      sx={{ appearance: "none", border: 0, bgcolor: "transparent", p: 0, width: "100%", minWidth: 0,
        display: "grid", gridTemplateColumns: "22px minmax(0, 1fr) 18px", alignItems: "stretch",
        minHeight: 58, textAlign: "left", cursor: "pointer", font: "inherit", color: "inherit",
        borderRadius: 1, "&:hover": { bgcolor: "#f7f4ef" },
        "&:hover .tq-story-title": { color: ACCENT },
        "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } }}>
      <Box sx={{ alignSelf: "stretch", position: "relative" }}>
        <Box sx={{ position: "absolute", left: 10.5, top: first ? "50%" : 0, bottom: last ? "50%" : 0,
          width: "1px", bgcolor: "#d8d2c8" }} />
        <Box sx={{ position: "absolute", zIndex: 1, top: "50%", left: 6.5, transform: "translateY(-50%)",
          width: 9, height: 9, borderRadius: "50%", bgcolor: dot, border: `2px solid ${PANEL}`,
          boxShadow: `0 0 0 1px ${dot}` }} />
      </Box>
      <Box sx={{ minWidth: 0, py: 0.65, pr: 1 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, mb: 0.15 }}>
          <Typography className="tq-story-title" sx={{ color: INK, fontWeight: 700, fontSize: 11.5,
            transition: "color .15s", whiteSpace: "nowrap" }}>{title}</Typography>
          <Typography sx={{ ...mono, color: state === "idle" ? FAINT : dot, fontSize: 9.5,
            fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{status}</Typography>
        </Box>
        <Typography sx={{ color: DIM, fontSize: 11.5, lineHeight: 1.38, overflow: "hidden",
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{summary}</Typography>
      </Box>
      <Box sx={{ display: "grid", placeItems: "center" }}>
        <ChevronRightIcon sx={{ color: FAINT, fontSize: 13 }} />
      </Box>
    </Box>
  );
};

// The pop-out review panel: everything about the selected line, editable and decidable
// without leaving the page. All text hard-left-aligned.
const ReviewCanvas = ({ sel, detail, editText, setEditText, decide, onOpenTask, onClose, onSkipped, onRefresh,
                        onMessageChanged, sendErr, clearSendErr, onLock }) => {
  // one click turns a flood sender (100s of automated mails) into a skip policy - their
  // mail is deduped but never shows on the timeline again, and their HISTORY goes with it
  const [skipped, setSkipped] = useState(null);
  const [skipConfirm, setSkipConfirm] = useState(false);
  const [tab, setTab] = useState("summary");      // overview first; four detailed stages remain one click away
  const [filing, setFiling] = useState("");       // "once" teaches nothing; "learn" writes one Memory verdict
  const [fileErr, setFileErr] = useState("");
  // a reply opened from THIS panel on a message with no pending review
  const [opened, setOpened] = useState(null);
  const [opening, setOpening] = useState(false);
  const openReply = async () => {
    setOpening(true);
    try {
      const { data } = await api.post(`/api/messages/${sel.MessageId}/reply`, {});
      setOpened({ reviewId: data.reviewId, draft: data.draft || "" });
      onRefresh?.();
    } catch (e) { /* the row's hint stays; nothing sent */ }
    setOpening(false);
  };
  // the same realisation - "this is not one job" - usually arrives while reading the mail,
  // so the fix is offered here too; the form itself is a drawer, since this panel is narrow
  const [reshape, setReshape] = useState(false);
  // Handing work to another person is occasional, not another permanent form in the action tray.
  // Keep one clear action visible and put the recipient/message fields in their own focused sheet.
  const [handoff, setHandoff] = useState(false);
  // "type their answer into the working session" - the round trip's last leg (answer_to_agent=ask)
  const [handed, setHanded] = useState(false);
  const handToAgent = async () => {
    try { await api.post(`/api/tasks/${sel.TaskId}/answer`, { message_id: sel.MessageId }); setHanded(true); }
    catch { /* session gone between render and click: the row's hint still points at the task */ }
  };
  useEffect(() => { setReshape(false); setHandoff(false); setOpened(null); setOpening(false); setHanded(false);
    setTab("summary"); setFiling(""); setFileErr(""); setNotCoding(false); setRouteErr(""); setSkipConfirm(false); }, [sel.MessageId]);
  const fileMessage = async (learn) => {
    setFiling(learn ? "learn" : "once"); setFileErr("");
    try {
      // /file historically learned by default, so the one-off road must send false explicitly.
      await api.post(`/api/messages/${sel.MessageId}/file`, { learn });
      onSkipped?.();
    } catch (e) {
      setFileErr(e?.response?.data?.detail || e?.message || "Could not file this message");
      setFiling("");
    }
  };
  const skipSender = async () => {
    const { data } = await api.post("/api/policies", { Name: `skip:${sel.FromEmail}`, Kind: "sender", Pattern: sel.FromEmail,
      Action: "skip", Reason: "flood sender — skipped from the timeline", SortOrder: 10, Active: true });
    setSkipped(data.affected || 0);
    setTimeout(() => onSkipped?.(), 1400);          // let the count land, then drop the rows
  };
  const rep = [...(detail?.comments || [])].reverse().find((c) => String(c.Body || "").trimStart().startsWith("CODER REPORT"));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  // an ACTION is a proposal, not a reply - it has its own card and must never fill this tab
  const livePending = (detail?.reviews || []).find((r) => r.Status === "pending" && r.Kind !== "action");
  const pending = detail ? !!livePending : !!(sel.ReviewId && sel.ReviewStatus === "pending");
  const pendingId = livePending?.ReviewId || sel.ReviewId;
  // is somebody already on this? a live pty session or a running headless run both count,
  // and a session gone quiet is a question waiting for an answer, not work in progress
  const ses = detail?.session;
  const run = (detail?.runs || []).find((r) => r.Status === "running");
  const onIt = ses ? { agent: ses.agent || ses.label, waiting: ses.waiting ?? (ses.idle >= IDLE_WAITING) }
    : run ? { agent: run.AgentName, waiting: false } : null;
  // the live console: while an agent is on this task, the panel polls its last lines every 3 s
  const [liveRow, setLiveRow] = useState(null);
  useEffect(() => {
    if (!onIt || !sel?.TaskId) { setLiveRow(null); return; }
    let alive = true;
    const poll = async () => { try { const { data } = await api.get("/api/runs/live", { params: { lines: 120 } }); if (alive) setLiveRow((data.data || []).find((r) => r.TaskId === sel.TaskId) || null); } catch { /* keep the last */ } };
    poll(); const id = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!onIt, sel?.TaskId]);
  const loading = sel.TaskId && !detail;
  // triage's OWN verdict, read off the route line it already wrote. reply_only and fyi both
  // mean "no work to do here" - so a coding agent is not the answer, and offering it first
  // made the panel argue with the reason printed at the top of the very same panel.
  const codeless = /triage:\s*(reply_only|fyi)/.test(String(sel.RouteReason || "")) && !sel.TaskId;
  const history = historyOf(sel, detail);
  const st = stateOf(sel);
  const held = hasTag(sel, HOLD_TAG);
  // A decided draft is the completed Reply stage, not an absent draft. Approval is the send
  // door, and FinalText is the exact response that left; keep it visible after Review closes.
  const sentReview = (detail?.reviews || []).find((r) =>
    ["approved", "edited", "sent"].includes(r.Status) && r.Kind !== "action" &&
    String(r.FinalText || r.DraftText || "").trim());
  const sentReply = String(sentReview?.FinalText || sentReview?.DraftText || "").trim();
  const replied = !!sentReply;
  const replyOpen = pending || !!opened;
  const chatTask = !!sel.TaskId && ["general", "research", "marketing", "triage", "assistant"]
    .includes(String(detail?.task?.Kind || sel.TaskKind || "").toLowerCase());
  const tabs = [
    { key: "summary", label: "Summary" },
    { key: "msg", label: "Message" },
    { key: "why", label: "Triage" },
    { key: "agent", label: "Agent", mark: onIt ? "live" : chatTask ? "chat" : rep ? "done" : "" },
    { key: "reply", label: "Reply", mark: replied ? "replied" : pending ? "waiting" : opened ? "open" : "" },
  ];
  // The drawer just read the live session list; the row's chip is whatever the last feed poll
  // saw. When they disagree the drawer is the newer fact, so ask the list to refresh rather than
  // leaving "agent working" on a task nothing is working. Once per message: the refreshed row
  // clears Working, so this cannot chase itself.
  const correctedRef = useRef(null);
  useEffect(() => {
    if (!detail || !sel?.MessageId) return;
    const staleAgent = sel.Working && !detail.session;
    const staleReply = (sel.ReviewStatus === "pending") !== !!livePending;
    if (!staleAgent && !staleReply) return;
    if (correctedRef.current === sel.MessageId) return;
    correctedRef.current = sel.MessageId;
    onRefresh?.();
  }, [detail, sel?.MessageId, sel?.Working, sel?.ReviewStatus, livePending, onRefresh]);
  const replyDraft = pending
    ? (livePending?.DraftText || pendingDraft(detail || { runs: [] }, sel))
    : (opened?.draft || "");
  // the road, in words - the why sentence is one tab over, for when it is asked for
  const roadMeta = ROADS.find((r) => r.key === roadOf(sel));
  const roadLine = roadMeta ? `${roadMeta.label} — ${roadMeta.hint}` : (sel.RouteReason ? "Routed; open for the verdict." : "Not routed.");
  const reportText = String(rep?.Body || "").replace(/^(CODER REPORT|HANDOVER NOTE)\s*/i, "").trim();
  const reportResult = ((/(?:^|\n)Summary:[ \t]*([^\n]+)/im.exec(reportText) ||
    /(?:^|\n)Result:[ \t]*([^\n]+)/im.exec(reportText) || [])[1] || cleanText(reportText)).trim();
  const messageSummary = cleanText(sel.Preview || sel.Subject || "No message preview available.");
  const triageStatus = ["assistant", "report", "calendar"].includes(sel.Channel)
    ? "fyi" : (roadOf(sel) || "not routed");

  const [mined, setMined] = useState(null);          // "Mine to do" made a task, and its ref
  const [notCoding, setNotCoding] = useState(false); // "Mine, not agent" landed - the button says so
  const [routeErr, setRouteErr] = useState("");      // ...or was refused, and the reason is shown here
  const [closed, setClosed] = useState(null);        // ...and closing one from the panel
  const [releasing, setReleasing] = useState(false);
  const release = async () => {
    setReleasing(true);
    try { const { data } = await api.post(`/api/tasks/${sel.TaskId}/release`, {}); onRefresh?.(); if (data?.session) onOpenTask?.(sel.TaskId); }
    catch { /* the row keeps its hold; the reason is on the task */ }
    setReleasing(false);
  };

  return (
    <Box key={sel.MessageId} sx={{ height: "100%", minHeight: 0, textAlign: "left",
      // grows out of the row you clicked: slides rightward and scales up
      "@keyframes thubGrow": { from: { opacity: 0, transform: "translateX(-24px) scale(.975)" },
        to: { opacity: 1, transform: "none" } },
      animation: "thubGrow .26s cubic-bezier(.2,.8,.3,1) both", transformOrigin: "left center" }}>
      <Box sx={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column",
        bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden" }}>

        {/* header */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 2, pt: 1.5, pb: 1.25, flexShrink: 0 }}>
          <ChannelIcon channel={sel.Channel} sx={{ fontSize: 19 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 15, lineHeight: 1.3, letterSpacing: "-.25px" }} noWrap>
              {sel.Subject || `${sel.FromName || sel.FromEmail} in ${sel.SourceName || "chat"}`}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
              {sel.FromName || sel.FromEmail}{sel.SourceName && String(sel.SourceName).toLowerCase() !== String(sel.FromName || "").toLowerCase() ? ` · ${sel.SourceName}` : ""} · {fmtDateTime(sel.SentAt)}
            </Typography>
          </Box>
          <RefChip taskId={sel.TaskId} onClick={() => onOpenTask(sel.TaskId)} />
          <StateMark row={sel} state={st} size="md" />
          <IconButton size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
        </Box>

        {/* a stranger's first message is the one state that needs answering before anything else
            can happen, so it sits above the tabs rather than inside one of them */}
        {held && sel.TaskId && (
          <Box sx={{ mx: 2, mb: 1.5, px: 1.5, py: 1.25, borderRadius: 2,
            border: `1px solid ${ROLES.muted.bd}`, borderLeft: `2px solid ${ROLES.muted.solid}`, bgcolor: "#fcfaf7" }}>
            <Typography sx={{ fontSize: 12.5, color: INK, lineHeight: 1.6, mb: 1 }}>
              <b>Nothing was started.</b> This is the first message from {sel.FromEmail || "this address"},
              and an unvetted message is not allowed to open a session on this machine by itself.
            </Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              <Button size="small" variant="contained" disableElevation disabled={releasing} onClick={release}
                startIcon={releasing ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <TaskuaryMark size={15} />}
                sx={{ fontSize: 12, background: GRADIENT }}>Release to the agent</Button>
              <Typography variant="caption" sx={{ color: FAINT, alignSelf: "center" }}>
                they are never held again after this
              </Typography>
            </Box>
          </Box>
        )}

        {/* Summary is the fifth, default view. The original four stages remain full detail views. */}
        <Box role="tablist" aria-label="Message workflow views"
          sx={{ display: "flex", gap: 0.25, px: 2, borderBottom: `1px solid ${BORDER}`, flexShrink: 0,
            overflowX: "auto", scrollbarWidth: "none", "&::-webkit-scrollbar": { display: "none" } }}>
          {tabs.map((item) => (
            <Box key={item.key} role="tab" aria-selected={tab === item.key} tabIndex={tab === item.key ? 0 : -1}
              onClick={() => setTab(item.key)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setTab(item.key); }}
              sx={{ display: "flex", alignItems: "center", gap: 0.55, px: 1.35, py: 1, mb: "-1px",
                cursor: "pointer", color: tab === item.key ? INK : FAINT, fontSize: 12.5, fontWeight: 650,
                whiteSpace: "nowrap", borderBottom: `2px solid ${tab === item.key ? ACCENT : "transparent"}`,
                transition: "color .15s", "&:hover": { color: INK } }}>
              {item.label}
              {item.mark && (
                <Box component="span" sx={{ ...mono, px: 0.55, py: 0.12, borderRadius: 2, bgcolor: PANEL2,
                  color: item.key === "agent" && onIt ? ACCENT2 : FAINT, fontSize: 8.5, fontWeight: 700 }}>
                  {item.mark}
                </Box>
              )}
            </Box>
          ))}
        </Box>

        <Box sx={{ px: 2, py: 1.1, overflowY: "auto", flex: 1, minHeight: 0 }}>
          {loading ? <CircularProgress size={20} sx={{ m: 2 }} /> : (
            <>
              {tab === "summary" && (
                <Box aria-label="Workflow summary" sx={{ width: "100%",
                  px: 0.75, pt: 0.45, pb: 0.75 }}>
                  <StoryTimelineStep title="Message" first state="done"
                    status={(detail?.messages || []).length > 1 ? `${detail.messages.length} messages` : "received"}
                    summary={messageSummary}
                    onOpen={() => setTab("msg")} />
                  <StoryTimelineStep title="Triage" status={triageStatus} summary={roadLine}
                    state={triageStatus !== "not routed" ? "done" : "idle"} onOpen={() => setTab("why")} />
                  <StoryTimelineStep title="Agent"
                    status={onIt ? (onIt.waiting ? "waiting" : "working") : chatTask ? "assistant chat" : rep ? "finished" : "not started"}
                    summary={onIt ? (onIt.waiting ? `${onIt.agent} needs your answer.` : `${onIt.agent} is working in the live terminal.`)
                      : chatTask ? "The assistant conversation is available here."
                      : rep ? (reportResult || "The agent finished; open for the result.")
                      : held ? "Held until you release it."
                      : codeless ? "Triage decided an agent was not needed."
                      : "No agent work has started."}
                    state={onIt ? "current" : (chatTask || rep || diffRun) ? "done" : "idle"}
                    onOpen={() => setTab("agent")} />
                  <StoryTimelineStep title="Reply" last
                    status={replied ? "replied" : pending ? "waiting on you" : opened ? "draft open" : "not drafted"}
                    summary={replied ? cleanText(sentReply) : replyDraft ? cleanText(replyDraft) : (["report", "assistant"].includes(sel.Channel)
                      ? "This item has nobody to reply to." : "No reply has been drafted yet.")}
                    state={replied ? "done" : replyOpen ? "current" : "idle"} onOpen={() => setTab("reply")} />
                </Box>
              )}

              {tab === "msg" && (
                <Box>
                  {sel.Channel === "assistant" && <AssistantPost sel={sel} onOpenTask={onOpenTask} onChanged={() => onRefresh?.()} />}
                  {sel.Channel === "report" && /morning digest/i.test(`${sel.SourceName || ""} ${sel.Subject || ""}`) && <TodayStrip />}
                  {sel.Channel !== "assistant" && (
                    <MessageBlock key={sel.MessageId} messages={detail?.messages} focusId={sel.MessageId} fallback={sel.Preview} />
                  )}
                  {history.length > 0 && (
                    <>
                      <PanelLabel>What happened to it</PanelLabel>
                      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                        {history.map((h, i) => (
                          <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 0.45 }}>
                            <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: h.c }} />
                            <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{h.label}{h.n > 1 ? ` ×${h.n}` : ""}</Typography>
                          </Box>
                        ))}
                      </Box>
                    </>
                  )}
                </Box>
              )}

              {tab === "why" && (
                <Box>
                  <TriagePane sel={sel} detail={detail} onRefresh={onRefresh} />
                </Box>
              )}

              {tab === "agent" && (
                <Box>
                  {chatTask ? (
                    <Box sx={{ height: 480 }}>
                      <React.Suspense fallback={<Box sx={{ height: "100%", display: "grid", placeItems: "center" }}><CircularProgress size={20} /></Box>}>
                        <GeneralWorkspace task={detail.task} compact />
                      </React.Suspense>
                    </Box>
                  ) : onIt && (
                    <>
                      <PanelLabel>{onIt.waiting ? `${onIt.agent} is waiting on you` : `${onIt.agent} is working now`}</PanelLabel>
                      {ses?.sid ? (
                        <>
                          <Box sx={{ height: 440, display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                            <TerminalPane sid={ses.sid} height="100%" onExit={() => onRefresh?.()} />
                          </Box>
                          {ses.alive !== false && (
                            <Box sx={{ mt: 0.75 }}>
                              <TellAgent taskId={sel.TaskId} taskRef={detail?.ref} compact onQueued={() => onRefresh?.()} />
                            </Box>
                          )}
                          <Typography variant="caption" onClick={() => onOpenTask(sel.TaskId)}
                            sx={{ color: FAINT, display: "block", mt: 0.5, cursor: "pointer", "&:hover": { color: INK } }}>
                            open the task page ↗
                          </Typography>
                        </>
                      ) : <LiveConsole run={liveRow} agent={onIt.agent} lines={14} onOpen={() => onOpenTask(sel.TaskId)} />}
                    </>
                  )}
                  {rep && (
                    <>
                      <PanelLabel>Agent result</PanelLabel>
                      <Box sx={{ bgcolor: "#fcfaf7", border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden" }}>
                        <CoderReport body={rep.Body} />
                      </Box>
                      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                        Finished by {rep.Actor || "the coding agent"}{rep.CreatedAt ? ` · ${fmtDateTime(rep.CreatedAt)}` : ""}
                      </Typography>
                    </>
                  )}
                  {diffRun && <Box sx={{ mt: 1 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                  {sel.TaskId && (rep || diffRun) && <Box sx={{ mt: 1 }}><ProofCard taskId={sel.TaskId} onOpenTask={onOpenTask} /></Box>}
                  {/* a session RAN and is gone: say that, rather than that none ever started */}
                  {!chatTask && !onIt && !rep && !diffRun && detail?.transcript && (
                    <>
                      <PanelLabel>The session that was working this has ended</PanelLabel>
                      <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
                        {detail.transcript.agent || "an agent"} worked here
                        {detail.transcript.cwd ? ` in ${detail.transcript.cwd}` : ""}
                        {detail.transcript.at ? ` · ${fmtDateTime(detail.transcript.at)}` : ""}, and its terminal is gone.
                        Nothing is working it now — the transcript it left is what closes it out.
                      </Typography>
                      <Typography variant="caption" onClick={() => onOpenTask(sel.TaskId)}
                        sx={{ color: "#55697a", display: "block", mt: 0.75, cursor: "pointer", fontWeight: 600 }}>
                        open the task page to close it out ↗
                      </Typography>
                    </>
                  )}
                  {!chatTask && !onIt && !rep && !diffRun && !detail?.transcript && (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
                      {held ? "Nothing is working this — it is held until you release it."
                        : codeless ? "No agent was sent: triage read this as something a reply settles."
                        : sel.TaskId ? "No agent has started on this yet." : "No agent work was created for this item."}
                    </Typography>
                  )}
                </Box>
              )}

              {tab === "reply" && (
                <Box>
                  {/* YOU answered it, somewhere else. Not the same fact as "Sent reply", which
                      means Taskuary drafted it and something here sent it - and the panel said
                      that about both, so a message handled in Teams read as one we had answered
                      for you. The reply itself is on the Message tab, in the thread. */}
                  {sel.AnsweredAt && !replied && !pending && (
                    <Box sx={{ mb: 1.25 }}>
                      <PanelLabel>You answered this</PanelLabel>
                      <Typography variant="caption" sx={{ color: DIM, display: "block" }}>
                        in {sel.Channel === "email" ? "your mailbox" : sel.Channel} · {fmtDateTime(sel.AnsweredAt)}
                        {" "}— nothing here sent it, and nothing is waiting on you.
                      </Typography>
                    </Box>
                  )}
                  {replied && (
                    <Box>
                      <PanelLabel>Sent reply</PanelLabel>
                      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.65 }}>
                        To {sel.FromName || sel.FromEmail || "the conversation"}
                      </Typography>
                      <Box sx={{ bgcolor: "#fcfaf7", border: `1px solid ${BORDER}`, borderRadius: 1.5,
                        px: 1.25, py: 1, color: INK, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                        {sentReply}
                      </Box>
                    </Box>
                  )}
                  {pending && (
                    <ReviewActions reviewId={pendingId} draft={replyDraft}
                      editText={editText} setEditText={setEditText} decide={decide}
                      sendErr={sendErr} clearSendErr={clearSendErr} canSend={sel.CanSend} />
                  )}
                  {!pending && opened && (
                    <ReviewActions reviewId={opened.reviewId} draft={replyDraft}
                      editText={editText} setEditText={setEditText} decide={decide}
                      sendErr={sendErr} clearSendErr={clearSendErr} canSend={sel.CanSend} />
                  )}
                  {!replied && !replyOpen && (["report", "assistant"].includes(sel.Channel) ? (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
                      Nobody sent this, so there is nobody to answer. Findings stay with the Timeline item.
                    </Typography>
                  ) : (
                    <ChoiceRow tint={PANEL2} busy={opening} onClick={openReply}
                      icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: ACCENT }} />}
                      label="Write a reply" first
                      hint="the AI drafts it from the thread and the agent result; approving sends it" />
                  ))}
                </Box>
              )}
            </>
          )}
        </Box>

        {/* Actions stay visible while details change. Every row uses the same button geometry;
            the bucket copy explains the consequence and MEMORY marks the choices that teach. */}
        {!loading && sel.Channel !== "assistant" && (
          <Box sx={{ flexShrink: 0, borderTop: `1px solid ${BORDER}`, bgcolor: "#fcfaf7", px: 2, py: 1.35 }}>
            <TrayGroupLabel note="open existing work, or choose who should handle it">WORK ON IT</TrayGroupLabel>
            <Box sx={{ display: "flex", gap: 0.8, flexWrap: "wrap", alignItems: "center" }}>
              {sel.TaskId ? (
                <TrayBtn tone="primary" onClick={() => onOpenTask(sel.TaskId)} icon={<OpenInFullIcon sx={{ fontSize: 15 }} />}>
                  {onIt ? "Open the live session" : `Open ${ref(sel.TaskId)}`}</TrayBtn>
              ) : (
                <TrayBtn disabled={!!mined} icon={<AssignmentIndIcon sx={{ fontSize: 15 }} />}
                  title="adds a task with your name on it; no coding agent is dispatched"
                  onClick={async () => {
                    try { const { data } = await api.post(`/api/messages/${sel.MessageId}/mine`, {});
                      setMined(data.ref); onRefresh?.(); } catch { /* the row keeps its state */ }
                  }}>{mined || "Add to my tasks"}</TrayBtn>
              )}
              {/* Closing it needed the Tasks tab, which is a trip away from the row you are
                  reading - so a finished piece of work kept saying "on your list" because marking
                  it done was somewhere else. */}
              {sel.TaskId && !["done", "dropped"].includes(sel.TaskStatus) && (
                <TrayBtn disabled={!!closed} icon={<CheckIcon sx={{ fontSize: 16 }} />}
                  title="closes the task from here - the agent's report and the thread stay"
                  onClick={async () => {
                    try {
                      await api.patch(`/api/tasks/${sel.TaskId}`, { Status: "done" });
                      setClosed("Closed"); onRefresh?.();
                    } catch { /* the row keeps its state */ }
                  }}>{closed || "Mark done"}</TrayBtn>
              )}
              {onIt && sel.MessageId && (
                <TrayBtn disabled={handed} onClick={handToAgent} icon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                  title="their message is typed into the live session, as if you relayed it">
                  {handed ? "Typed into the session" : `Tell ${onIt.agent} this`}</TrayBtn>
              )}
              {onIt && sel.TaskId && <TellAgentButton taskId={sel.TaskId} />}
              {!onIt && !codeless && !held && (
                <SendToAgent messageId={sel.MessageId} subject={sel.Subject} onOpenTask={onOpenTask} />
              )}
              {!onIt && <TalkItThrough messageId={sel.MessageId} onOpenTask={onOpenTask} />}
              {sel.TaskId && (
                <TrayBtn onClick={() => setHandoff(true)} icon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                  title="send the full task and its context to another person">
                  Hand off</TrayBtn>
              )}
            </Box>

            <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
              <TrayGroupLabel note="choose whether this should change future routing">CLEAR FROM TIMELINE</TrayGroupLabel>
              <Box sx={{ display: "flex", gap: 0.8, flexWrap: "wrap", alignItems: "center" }}>
                <TrayBtn tone="quiet" disabled={!!filing} icon={<ArchiveOutlinedIcon sx={{ fontSize: 15 }} />}
                  title="files this message only; nothing is added to Memory" onClick={() => fileMessage(false)}>
                  {filing === "once" ? "Dismissing…" : "Dismiss once"}</TrayBtn>
                <TrayBtn tone="teach" teaches disabled={!!filing} icon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}
                  title="files this message and adds one verdict to Memory for later triage" onClick={() => fileMessage(true)}>
                  {filing === "learn" ? "Teaching triage…" : "Nothing to do"}</TrayBtn>
              </Box>
              {fileErr && <Typography variant="caption" sx={{ display: "block", color: ROLES.bad.ink,
                fontWeight: 600, mt: 0.75 }}>{fileErr} — nothing changed.</Typography>}
            </Box>

            <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
              <TrayGroupLabel note="correct who owns it; MEMORY choices teach future triage">ROUTING</TrayGroupLabel>
              <Box sx={{ display: "flex", gap: 0.8, flexWrap: "wrap", alignItems: "center" }}>
                {sel.TaskId && (
                  <TrayBtn tone="teach" teaches disabled={notCoding} icon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}
                    title="make this your task instead of agent work, and remember that choice"
                    onClick={async () => {
                      setRouteErr("");
                      try { await api.post(`/api/tasks/${sel.TaskId}/not-coding`); setNotCoding(true); onRefresh?.(); }
                      catch (e) { setRouteErr(e?.response?.data?.detail || "that did not work"); }
                    }}>{notCoding ? "Now yours" : "Mine, not agent"}</TrayBtn>
                )}
                {sel.TaskId && (
                  <TrayBtn icon={<CallSplitIcon sx={{ fontSize: 15 }} />}
                    title="separate two jobs, or mark this as a duplicate"
                    onClick={() => setReshape(true)}>Split / merge</TrayBtn>
                )}
                <NotMine compact messageId={sel.MessageId} onDone={onSkipped} onLock={onLock} />
                <SplitTask compact row={sel} onSplit={() => onRefresh?.()} />
              </Box>
              {routeErr && <Typography variant="caption" sx={{ display: "block", color: ROLES.bad.ink, fontWeight: 600, mt: 0.75 }}>{routeErr} — nothing changed.</Typography>}

              {sel.Channel === "email" && sel.FromEmail && (
                <Box sx={{ mt: 1.1 }}>
                  <TrayGroupLabel note="hide this address now and remember that rule">SENDER RULES</TrayGroupLabel>
                  <TrayBtn tone="teach" teaches disabled={skipped !== null} onClick={() => setSkipConfirm(true)}
                    icon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}
                    title={`hide ${sel.FromEmail} and their past mail — undo in Settings`}>
                    {skipped !== null ? `Skipped${skipped ? ` · ${skipped} hidden` : ""}` : "Skip sender"}</TrayBtn>
                  <Confirm open={skipConfirm} onClose={() => setSkipConfirm(false)} confirmLabel="Skip this sender"
                    title={`Skip everything from ${sel.FromEmail}?`}
                    text={"Their mail leaves the Timeline now - what they already sent, and everything after it. "
                      + "It is still received and kept; it just never shows here again. The rule lives under Settings → Routing policies, where it can be switched off."}
                    onConfirm={skipSender} />
                </Box>
              )}
            </Box>
            <VoiceNoteRow sel={sel}
              body={voiceNoteBody(sel, (detail?.messages || []).find((m) => m.MessageId === sel.MessageId))}
              onRefresh={onRefresh} onMessageChanged={onMessageChanged} />

            <Drawer anchor="right" open={handoff && !!sel.TaskId} onClose={() => setHandoff(false)}
              PaperProps={{ sx: { width: { xs: "100%", sm: 460 }, p: 2, bgcolor: PANEL } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <ForwardToInboxIcon sx={{ fontSize: 18, color: ACCENT }} />
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>Hand this to a person</Typography>
                <IconButton size="small" onClick={() => setHandoff(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
              </Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
                {sel.TaskId ? ref(sel.TaskId) : ""} · {sel.Subject}
              </Typography>
              {handoff && sel.TaskId && <Handoff taskId={sel.TaskId} onSent={() => onRefresh?.()} />}
            </Drawer>

            <Drawer anchor="right" open={!!reshape && !!sel.TaskId} onClose={() => setReshape(false)}
              PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <CallSplitIcon sx={{ fontSize: 18, color: ACCENT2 }} />
                <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>Is this one job?</Typography>
                <IconButton size="small" onClick={() => setReshape(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
              </Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
                {sel.TaskId ? ref(sel.TaskId) : ""} · {sel.Subject}
              </Typography>
              {reshape && sel.TaskId && (
                <Reshape taskId={sel.TaskId} taskRef={ref(sel.TaskId)}
                  onDone={(r) => { onRefresh?.(); if (r?.merged) onOpenTask?.(r.merged); }} />
              )}
            </Drawer>
          </Box>
        )}
      </Box>
    </Box>
  );
};

// ── Triage, as a decision you can see and argue with ──────────────────────────────────────
// The verdict used to be one grey caption at the top of the panel ("Why it's here: triage:
// coding - …"), which said what happened without ever showing that there were four answers it
// could have given. Four roads, the one it took lit, and its own sentence underneath: that is
// the difference between a system you can correct and a system you have to trust.
// FIVE roads, because there are five places a message can go and there were only ever four
// words for them. `general` used to read "only you can do it" - triage's old meaning - while the
// Board, + New and GeneralWorkspace all treated the same Kind as the assistant's chat. One value,
// two meanings, and the road nobody could act on. general IS chat now, everywhere, and the work
// a person genuinely has to do in the world is its own road.
const ROADS = [
  { key: "fyi", label: "fyi", hint: "nothing to do" },
  { key: "reply", label: "reply", hint: "a sentence settles it" },
  { key: "coding", label: "coding", hint: "an agent on a keyboard" },
  { key: "general", label: "chat", hint: "talk it through with the assistant" },
  { key: "task", label: "task", hint: "yours - nothing works it" },
];
// which road the route line says it took. `kind` decides coding vs general and rides on the
// task, so the two are read from different places on purpose.
const roadOf = (sel) => {
  const r = String(sel.RouteReason || "");
  if (/triage:\s*fyi/.test(r)) return "fyi";
  if (/triage:\s*reply_only/.test(r) || sel.TaskKind === "reply") return "reply";
  if (sel.TaskKind === "coding") return "coding";
  if (sel.TaskKind === "note") return null;                 // you wrote it; nothing judged it
  if (sel.TaskKind === "task") return "task";               // a person has to do it in the world
  return sel.TaskId ? "general" : null;
};

const TriageSummary = ({ sel, detail }) => {
  const road = roadOf(sel);
  const meta = ROADS.find((r) => r.key === road);
  const why = String(sel.RouteReason || "").replace(/^triage:\s*\w+\s*-\s*/, "").split(" · ")[0];
  const watch = (detail?.task || {}).Kind === "note";
  return (
    <Box sx={{ bgcolor: "#fcfaf7", border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.2, py: 0.85 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
        <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: INK, flexShrink: 0 }}>
          {meta?.label || (watch ? "your note" : "not routed")}
        </Typography>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{meta?.hint || ""}</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, fontSize: 12, lineHeight: 1.5, mt: 0.2 }}>
        {why || (watch ? "You created this directly; triage did not judge it." : "Nothing classified this message.")}
      </Typography>
    </Box>
  );
};

// "Talk it through" - the chat door for a Timeline row. Distinct from SendToAgent (a CLI in a
// checkout) and from "this one is mine" (a plain task nothing works): this one opens the
// assistant's own thread with the message as the question.
const TalkItThrough = ({ messageId, onOpenTask }) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/chat`, {});
      onOpenTask?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not open the chat"); }
    setBusy(false);
  };
  return (
    <>
      <TrayBtn disabled={busy} onClick={go} icon={<ForumOutlinedIcon sx={{ fontSize: 15 }} />}
        title="opens the assistant's chat on this, with the message as the question">
        {busy ? "Opening…" : "Talk it through"}</TrayBtn>
      {err && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </>
  );
};

// A conversation, folded. Nine rows reading "Teams chat with Priya Shah" is not a day you can
// read - so the rail carries ONE line for the thread, with the count, the span it covers and the
// loudest thing inside it. Expanding reveals the real rows, unchanged, underneath.
//
// The state is the LOUDEST member's, never the newest: a reply waiting two messages down must not
// be hidden by a fold whose top line happens to be fyi. Folding is not a way to lose work.
const ThreadFold = ({ entry, open, onToggle, onOpenRow, sel }) => {
  const rows = entry.rows;
  const st = loudest(rows, stateOf, LOUDNESS);
  const head = rows[0];
  const who = [...new Set(rows.map((r) => r.FromName || r.SourceName).filter(Boolean))];
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: `${GUTTER}px 14px minmax(0,1fr)`,
      alignItems: "stretch", mb: "3px" }}>
      <Typography sx={{ ...mono, fontSize: 10, color: FAINT, textAlign: "right",
        pt: "6px", pl: "8px", pr: "12px", whiteSpace: "nowrap", letterSpacing: "-.2px",
        fontVariantNumeric: "tabular-nums" }}>
        {fmtTime12(head.SentAt)}
      </Typography>
      <Box sx={{ position: "relative" }}>
        <Box sx={{ position: "absolute", left: "6px", top: "-5px", bottom: "-5px", width: "1px", bgcolor: BORDER }} />
        <Box sx={{ position: "absolute", left: "2.5px", top: "9px", width: 8, height: 8, borderRadius: "50%",
          bgcolor: edgeOf(st), boxShadow: `0 0 0 3px ${PANEL}` }} />
      </Box>
      <Box onClick={onToggle} data-tq-keep
        title={open ? "fold this conversation back up" : `${rows.length} messages on one conversation - open it`}
        sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderLeft: `2px solid ${edgeOf(st)}`,
          borderRadius: "8px", px: "10px", pt: "3px", pb: "4px", ml: "8px", minWidth: 0, overflow: "hidden",
          cursor: "pointer", transition: "box-shadow .18s, border-color .18s",
          "&:hover": { borderColor: "#d8cfbe", boxShadow: "0 2px 8px rgba(47,107,79,.10)" } }}>
        <Box sx={{ display: "flex", gap: 0.85, alignItems: "center", minWidth: 0, minHeight: 22 }}>
          <Box component="span" aria-hidden sx={{ display: "flex", flexShrink: 0, color: FAINT,
            transform: open ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform .15s" }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
              strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6l4 4 4-4" /></svg>
          </Box>
          <Box sx={{ display: "flex", flexShrink: 0 }}><ChannelIcon channel={head.Channel} sx={{ fontSize: 16 }} /></Box>
          <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: INK, fontSize: 12, flexShrink: 1, minWidth: 56, maxWidth: 150 }}>
            {who.slice(0, 2).join(", ")}{who.length > 2 ? ` +${who.length - 2}` : ""}
          </Typography>
          <Typography variant="body2" noWrap sx={{ color: DIM, fontSize: 11.5, flex: 1, minWidth: 0 }}>
            {cleanText(String(head.Subject || "")) || "conversation"}
          </Typography>
          <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, fontWeight: 600, color: ROLES.info.ink,
            bgcolor: ROLES.info.tint, border: `1px solid ${ROLES.info.bd}`, borderRadius: 99, px: 0.75,
            lineHeight: "15px", flexShrink: 0 }}>{rows.length}</Typography>
          <StateMark row={head} state={st} />
        </Box>
        <Box sx={{ display: "grid", gridTemplateRows: open ? "0fr" : "1fr", transition: "grid-template-rows .2s ease" }}>
          <Box sx={{ overflow: "hidden" }}>
            <Typography noWrap sx={{ fontSize: 10.5, lineHeight: 1.5, pt: "2px", pl: "20px", color: FAINT }}>
              {spanText(rows, fmtTime12)}
            </Typography>
          </Box>
        </Box>
        {/* the members, INSIDE the card and indented under the caret - so the group is one block
            and nothing that merely shares a minute with it can land in the middle */}
        {open && rows.map((m) => (
          <Box key={m.MessageId} onClick={(ev) => { ev.stopPropagation(); onOpenRow?.(m); }}
            sx={{ display: "flex", alignItems: "center", gap: 0.85, minWidth: 0, py: 0.5, pl: "20px",
              borderTop: `1px solid ${BORDER}`, cursor: "pointer",
              bgcolor: sel?.MessageId === m.MessageId ? PANEL2 : "transparent",
              "&:hover .tqKid": { color: INK } }}>
            <Typography sx={{ ...mono, fontSize: 9.5, color: FAINT, flexShrink: 0,
              fontVariantNumeric: "tabular-nums" }}>{fmtTime12(m.SentAt)}</Typography>
            <Box sx={{ display: "flex", flexShrink: 0 }}><ChannelIcon channel={m.Channel} sx={{ fontSize: 14 }} /></Box>
            <Typography noWrap className="tqKid" sx={{ fontSize: 11.5, fontWeight: 600, color: DIM,
              flexShrink: 0, maxWidth: 120, transition: "color .15s" }}>
              {m.FromName || m.SourceName || "—"}
            </Typography>
            <Typography noWrap sx={{ fontSize: 11, color: FAINT, flex: 1, minWidth: 0 }}>
              {cleanText(String(m.Preview || m.Subject || ""))}
            </Typography>
            <StateMark row={m} showWord={stateMeta(st).loud && stateOf(m) === st} />
          </Box>
        ))}
      </Box>
    </Box>
  );
};

const TriagePane = ({ sel, detail, onRefresh }) => {
  const road = roadOf(sel);
  // every judgement made about this message, oldest first. "And why" below is only the LATEST
  // one, which is why a correction was invisible here: the owner clicks "not ours", the verdict
  // changes, and the panel showed the new sentence with no sign that anyone had overruled
  // anything. Routes are keyed on the message, so they survive the task the verdict deletes.
  // ...about THIS message. On a task row detail.routes covers every message on the task, and a
  // thread's other rows were judged separately - their reasons are not this row's history.
  const trail = (detail?.routes || []).filter((r) => !r.MessageId || r.MessageId === sel.MessageId);
  // the sentence the classifier wrote, without the routing bookkeeping after it
  const why = String(sel.RouteReason || "").replace(/^triage:\s*\w+\s*-\s*/, "").split(" · ")[0];
  const rest = String(sel.RouteReason || "").split(" · ").slice(1);
  const watch = (detail?.task || {}).Kind === "note";
  if (!sel.RouteReason && !road) return (
    <Typography variant="caption" sx={{ color: FAINT, lineHeight: 1.7 }}>
      Nothing judged this. {watch ? "You wrote it." : "It is here to be read."}
    </Typography>
  );
  return (
    <>
      <PanelLabel>Which road it took</PanelLabel>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.65, flexWrap: "wrap", mb: 1.5 }}>
        {ROADS.map((r) => (
          <Box key={r.key} title={r.hint} aria-current={road === r.key ? "true" : undefined}
            sx={{ display: "flex", alignItems: "center", gap: 0.55, border: `1px solid ${road === r.key ? "#aebcaf" : BORDER}`,
              borderRadius: 10, px: 1.15, height: 30, bgcolor: road === r.key ? "#edf1eb" : "transparent" }}>
            {road === r.key && <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: ACCENT2 }} />}
            <Typography sx={{ fontSize: 11.5, fontWeight: road === r.key ? 700 : 500,
              color: road === r.key ? INK : FAINT }}>{r.label}</Typography>
          </Box>
        ))}
        {road && <Typography variant="caption" sx={{ color: FAINT, ml: 0.35 }}>
          {ROADS.find((r) => r.key === road)?.hint}
        </Typography>}
      </Box>
      <PanelLabel>And why</PanelLabel>
      <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.5, py: 1.25, bgcolor: "#fcfaf7" }}>
        <Typography sx={{ fontSize: 13, color: INK, lineHeight: 1.65 }}>{why || sel.RouteReason}</Typography>
        {!!rest.length && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.85, lineHeight: 1.6 }}>
            {rest.join(" · ")}
          </Typography>
        )}
      </Box>
      {trail.length > 1 && (
        <>
          <PanelLabel>How it got here</PanelLabel>
          <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.5, py: 0.25, bgcolor: "#fcfaf7" }}>
            {trail.map((r, i) => {
              const mine = r.Decision === "ignore";
              return (
                <Box key={r.RouteId || i} sx={{ display: "flex", alignItems: "baseline", gap: 1, py: 0.65,
                  borderTop: i ? `1px solid ${BORDER}` : "none" }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, flexShrink: 0,
                    color: mine ? ALERT_INK : DIM }}>
                    {mine ? "You said: not ours" : `triage · ${r.Decision}`}
                  </Typography>
                  <Typography variant="caption" noWrap sx={{ color: FAINT, flex: 1, minWidth: 0 }}>
                    {cleanText(String(r.Reason || "")).replace(/^(not ours|triage:)\s*[-\u2014:]?\s*/i, "").split(" \u00b7 ")[0]}
                  </Typography>
                  {r.CreatedAt && (
                    <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: FAINT, flexShrink: 0 }}>
                      {fmtDateTime(r.CreatedAt)}
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
        </>
      )}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.25, lineHeight: 1.6 }}>
        Correcting this teaches it: the verdict you give lands in TRIAGE.md and applies to the next
        message like this one, not as a rule about this sender.
      </Typography>
    </>
  );
};

// A report that writes in sections (the Morning digest's prompt asks for emoji headers)
// renders AS sections: the emoji-led line becomes a real header, its bullets hang under it.
// Report bodies only - an email that happens to start a line with 🎉 is not a document.
const HDR = /^\s*\p{Extended_Pictographic}/u;
// URLs in a report become links - the digest writes one per task (#task=<id>, which the page
// opens in place), so the brief is a set of doors, not a reading.
const URL_RE = /(https?:\/\/[^\s<>"')\]]+)/g;
const Linkify = ({ text }) => {
  const parts = String(text).split(URL_RE);
  return parts.map((p, i) => (URL_RE.test(p) && (URL_RE.lastIndex = 0, true)
    ? <a key={i} href={p} style={{ color: "#55697a", fontWeight: 600, textDecoration: "none" }}
        onClick={(e) => { const m = /#task=(\d+)/.exec(p); if (m) { e.preventDefault(); window.location.hash = `task=${m[1]}`; } }}>
        {/#task=(\d+)/.test(p) ? `open TQ-${String(/#task=(\d+)/.exec(p)[1]).padStart(4, "0")} →` : p}</a>
    : <React.Fragment key={i}>{p}</React.Fragment>));
};
const SectionedText = ({ text }) => (
  <Box sx={{ textAlign: "left" }}>
    {text.split("\n").map((l, i) => (HDR.test(l)
      ? <Typography key={i} variant="body2" sx={{ fontWeight: 700, color: INK, mt: i ? 1.1 : 0,
          pb: 0.35, mb: 0.35, borderBottom: `1px solid ${BORDER}` }}>{l.trim()}</Typography>
      : l.trim()
        ? <Typography key={i} variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, lineHeight: 1.55 }}><Linkify text={l} /></Typography>
        : null))}
  </Box>
);

// A voice note that landed with nothing to transcribe it: the body is the placeholder voice.py
// writes and the audio is attached. With a voice connector now present, one click transcribes it
// here; without one the row says exactly what is missing, in the place the owner is looking.
const VoiceNoteRow = ({ sel, body, onRefresh, onMessageChanged }) => {
  const voice = useVoiceReady();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!isVoicePlaceholder(body)) return null;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${sel.MessageId}/transcribe`);
      if (onMessageChanged) onMessageChanged(sel.MessageId, data.body);
      else onRefresh?.();
    }
    catch (e) { setErr(e?.response?.data?.detail || "transcription failed"); }
    setBusy(false);
  };
  if (!voice) return (
    <ChoiceRow tint="#e3e6e1" busy icon={<MicIcon sx={{ fontSize: 14, color: "#6f8a6e" }} />}
      label="Checking voice provider…" hint="the saved audio is ready to transcribe" />
  );
  return voice?.ready ? (
    <ChoiceRow tint="#e3e6e1" busy={busy} onClick={go} icon={<MicIcon sx={{ fontSize: 14, color: "#6f8a6e" }} />}
      label={err ? `Transcription failed — ${err}` : "Transcribe this voice note"}
      hint={`the audio is attached — ${voice.label || voice.provider} turns it into text right here`} />
  ) : (
    <ChoiceRow tint="#eee7d6" icon={<MicOffIcon sx={{ fontSize: 14, color: "#8a7a5c" }} />}
      label="Voice note — not transcribed: no AI voice connector"
      hint="add one under Connections → AI — voice (Groq has a free tier; Local Whisper needs no key), then come back and click Transcribe" />
  );
};

// A chain can hold several emails (the inbound thread + your replies). One clean strip
// of pills above the body flips between them - the clicked timeline row is preselected,
// "↩ you" marks your own replies. Keyed by focusId so a new selection resets the pick.
const MessageBlock = ({ messages, focusId, fallback }) => {
  const msgs = messages || [];
  const [mid, setMid] = useState(null);
  const [showQuoted, setShowQuoted] = useState(false);
  const cur = msgs.find((m) => m.MessageId === mid) || msgs.find((m) => m.MessageId === focusId) || msgs[msgs.length - 1];
  // what just arrived, separated from the thread quoted underneath it
  const { latest, quoted } = splitQuoted(cleanText(cur?.BodyText) || fallback || "…");
  const whole = latest || quoted;
  // a report's raw rows are receipts, not reading: the summary is the message, the rows fold
  // away behind one click - same treatment the quoted thread below a reply gets
  const RAW = "\n--- raw data ---";
  const [showRaw, setShowRaw] = useState(false);
  const cut = whole.indexOf(RAW);
  const text = cut >= 0 ? whole.slice(0, cut).trimEnd() : whole;
  const raw = cut >= 0 ? whole.slice(cut + RAW.length).trim() : "";
  const you = cur?.Status === "context";
  const own = !you && cur?.Channel === "own";        // a note you left yourself: nothing arrived
  // an excerpt first. A PR body or a forwarded chain ran the panel into its own scrollbar
  // and pushed the choices under the fold; the first screen of a message is what the
  // decision needs, and the rest is one click, not a scroll, away
  const [full, setFull] = useState(false);
  useEffect(() => setFull(false), [cur?.MessageId]);
  const LINES = 8, CHARS = 700;
  const rows = text.split("\n");
  const long = rows.length > LINES || text.length > CHARS;
  const excerpt = long ? rows.slice(0, LINES).join("\n").slice(0, CHARS).trimEnd() + " …" : text;
  const shown = full || !long ? text : excerpt;
  const today = new Date().toLocaleDateString("sv-SE");
  const pt = (s) => (localDay(s) === today ? fmtTime12(s) : `${(localDay(s) || "").slice(5)} · ${fmtTime12(s)}`);
  // The strip is for PICKING a message. It drew one chip per message in the thread, which was
  // fine while a task-less row fetched only itself - then /thread started handing over the whole
  // conversation and a WhatsApp group chat filled six rows with a month of "Sam · 08-30". The
  // recent ones, and a way back to the rest.
  const CHIPS = 10;
  const [allChips, setAllChips] = useState(false);
  useEffect(() => setAllChips(false), [focusId]);
  const earlier = Math.max(0, msgs.length - CHIPS);
  let chips = allChips || !earlier ? msgs : msgs.slice(-CHIPS);
  // ...and never hide the one being read: an old message opened from the rail must show as picked
  if (cur && !chips.some((m) => m.MessageId === cur.MessageId)) chips = [cur, ...chips];
  return (
    <>
      {msgs.length > 1 && (
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 0.75 }}>
          {!!earlier && !allChips && (
            <Box onClick={() => setAllChips(true)}
              title={`show the other ${earlier} on this thread`}
              sx={{ px: 1.1, py: 0.35, borderRadius: 99, cursor: "pointer", fontSize: 11, fontWeight: 600,
                border: `1px dashed ${BORDER}`, color: FAINT, bgcolor: "transparent", whiteSpace: "nowrap",
                "&:hover": { borderColor: "#d8cfbe", color: "#55697a" } }}>
              +{earlier} earlier
            </Box>
          )}
          {chips.map((m) => {
            const on = cur && m.MessageId === cur.MessageId;
            const you = m.Status === "context";
            return (
              <Box key={m.MessageId} onClick={() => setMid(m.MessageId)}
                sx={{ px: 1.1, py: 0.35, borderRadius: 99, cursor: "pointer", fontSize: 11, fontWeight: 600,
                  border: `1px solid ${on ? "#d8cfbe" : BORDER}`, color: on ? "#55697a" : you ? FAINT : DIM,
                  bgcolor: on ? "#eae4d8" : "#fff", whiteSpace: "nowrap", transition: "all .15s",
                  "&:hover": { borderColor: "#d8cfbe", color: "#55697a" } }}>
                {you ? "↩ you" : (m.FromName || m.FromEmail || "?").split(" ")[0]} · {pt(m.SentAt)}
              </Box>
            );
          })}
        </Box>
      )}
      <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.25,
        borderLeft: `3px solid ${you ? "#d8cfbe" : "#6f8a6e"}` }}>
        {/* who / which way / when - so "new inbound" is never confused with "your reply" */}
        {cur && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.6, flexWrap: "wrap" }}>
            <Chip size="small" label={you ? "↩ your reply" : own ? "your note" : "inbound"}
              sx={{ height: 17, fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                bgcolor: you || own ? ROLES.working.tint : ROLES.muted.tint,
                color: you || own ? ROLES.working.ink : ROLES.muted.ink }} />
            <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>
              {you ? "you" : cur.FromName || cur.FromEmail || "unknown"}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>· {fmtDateTime(cur.SentAt)}</Typography>
            {quoted && <Typography variant="caption" sx={{ color: FAINT }}>· replying on this thread</Typography>}
          </Box>
        )}
        {cur?.Channel === "report" ? (looksMd(text) ? <Md text={text} /> : <SectionedText text={text} />)
          : own && (!text.trim() || text === "…")
            ? <Typography variant="body2" sx={{ color: FAINT, fontStyle: "italic" }}>You started this yourself — there is no incoming message behind it.</Typography>
          : <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, textAlign: "left" }}>
              {shown}
            </Typography>}
        {long && cur?.Channel !== "report" && (
          <Typography variant="caption" onClick={() => setFull(!full)}
            sx={{ display: "block", mt: 0.5, color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
            {full ? "show less ↑" : `show the whole message — ${rows.length} lines ↓`}
          </Typography>
        )}
        {raw && (
          <Box sx={{ mt: 1, borderTop: `1px dashed ${BORDER}`, pt: 0.75 }}>
            <Typography variant="caption" onClick={() => setShowRaw(!showRaw)}
              sx={{ color: DIM, fontWeight: 600, cursor: "pointer", "&:hover": { color: "#55697a" } }}>
              {showRaw ? "hide" : "show"} raw data — {raw.length.toLocaleString()} chars {showRaw ? "↑" : "↓"}
            </Typography>
            {showRaw && (
              <Typography variant="body2" sx={{ ...mono, whiteSpace: "pre-wrap", color: DIM, mt: 0.5,
                fontSize: 11, textAlign: "left", wordBreak: "break-word" }}>
                {raw}
              </Typography>
            )}
          </Box>
        )}
        {/* the thread quoted underneath: folded away by default, one click to read */}
        {latest && quoted && (
          <Box sx={{ mt: 1, borderTop: `1px dashed ${BORDER}`, pt: 0.75 }}>
            <Typography variant="caption" onClick={() => setShowQuoted(!showQuoted)}
              sx={{ color: DIM, fontWeight: 600, cursor: "pointer", "&:hover": { color: "#55697a" } }}>
              {showQuoted ? "hide" : "show"} quoted thread below it — {quoted.length.toLocaleString()} chars {showQuoted ? "↑" : "↓"}
            </Typography>
            {showQuoted && (
              <Typography variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap", color: FAINT, mt: 0.5,
                borderLeft: `2px solid ${BORDER}`, pl: 1 }}>
                {quoted}
              </Typography>
            )}
          </Box>
        )}
        {/* "See below." - and below was a screenshot. Drawn here, not listed as a filename. */}
        {cur && <Attachments messageId={cur.MessageId} canFetch={cur.Channel === "email"} />}
      </Box>
    </>
  );
};

// An action proposal's DraftText is its JSON envelope. For most actions that IS the thing to read
// (a bill: vendor, amount, account); a proposed playbook is a page of markdown, so show the page.
const proposalText = (t) => {
  try { const j = JSON.parse(t); if (j?.action === "write_playbook" && j.text) return j.text; } catch { /* a plain draft */ }
  return t;
};

// The pending draft text for this message's review - stored on the review row; a
// responder run's result is the fallback for drafts written before that column existed.
const pendingDraft = (detail, open) => {
  const rv = (detail.reviews || []).find((r) => r.ReviewId === open.ReviewId);
  if (rv?.DraftText) return proposalText(rv.DraftText);
  const run = (detail.runs || []).find((r) => r.AgentName === "responder" && r.Status === "done");
  return run?.Result || "";
};

// Two asks arriving in one chat thread are one conversation but two jobs - and an agent
// sent at the task only ever receives the first one's prompt.
// Not everything a person has to do is an agent's job: approve the workflow in ADP, click the
// thing in the portal. That is still work, and filing it as "nothing to do" is a lie - so it
// becomes a task with YOUR name on it and no agent sent at it. (A computer-use connector would
// take its queue from exactly here.)
// ── the assistant's private read (counsel.py) ──────────────────────────────────────────
const briefOf = (b) => { if (!b) return null; if (typeof b === "object") return b; try { return JSON.parse(b); } catch { return null; } };

// ── the assistant on the Timeline (assistant.py) ────────────────────────────────────────────
// The assistant is its ROWS: a post lands on the Timeline only when it has something specific
// to say (a reply never answered, a promise unkept, a meeting ahead, a task gone quiet, an
// idea of its own). Nothing is pinned above the feed - the owner (2026-08-30): "don't like the
// 2 open tab on top of the timeline and ask now button". What is open, in flight and waiting on
// you is the Morning digest's job, on its own clock (Reports tab).
// The why, folded: the line says WHAT; the facts it rests on open on a click (owner, 2026-09-02:
// "hate the why - hide it unless it's asked for").
const Why = ({ text }) => {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return open ? (
    <Typography variant="caption" onClick={() => setOpen(false)}
      sx={{ display: "block", color: DIM, mt: 0.35, whiteSpace: "pre-wrap", lineHeight: 1.4, cursor: "pointer" }}>
      <Box component="span" sx={{ fontWeight: 700, color: ASSISTANT.ink }}>why · </Box>{text}
    </Typography>
  ) : (
    <Typography variant="caption" onClick={() => setOpen(true)}
      sx={{ display: "inline-block", color: FAINT, mt: 0.3, cursor: "pointer", "&:hover": { color: INK } }}>why?</Typography>
  );
};

// One post, opened: each line with its buttons AND its why - the facts it rests on (the mail, the
// date, the silence; the model's own reason for an idea) - and under them what the post was built
// from: candidates by kind, the ones it looked at and let go, how much of the day it read (the
// owner, 2026-08-30: "we need more context like what it reviewed, why it brings up something").
// State comes from the server (a line acted on from another tab shows as done here too); the
// buttons are the ones the line's action allows.
const IDEA_KIND = { followup: "follow up", prep: "prep", cold: "gone quiet", ahead: "coming up", idea: "idea" };

// THE POST HAS SECTIONS. It used to be a flat list of lines, which is fine at two lines and
// unreadable at six - the owner (2026-09-01): "it should summarize into sections... what the
// info emails said, then open tasks and what they are working on, then things you forgot to
// follow up, then some stats". The lines themselves are unchanged: each still carries its own
// buttons and its own state, they are just sorted into what KIND of thing they are.
// Mirrors assistant.SECTIONS - the server decides which section a line is in.
const SECTIONS = [
  { key: "people",  mark: "📥", label: "What people said" },
  { key: "loose",   mark: "🧵", label: "Loose ends" },
  { key: "systems", mark: "🛠️", label: "From the systems" },
  { key: "ideas",   mark: "💡", label: "Worth a thought" },
];
const SectionHead = ({ mark, label, n }) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 0.85, mt: 1.75, mb: 0.85 }}>
    <Box component="span" aria-hidden sx={{ fontSize: 14, lineHeight: 1 }}>{mark}</Box>
    <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: INK, letterSpacing: "-.1px" }}>{label}</Typography>
    <Box sx={{ flex: 1, height: "1px", bgcolor: BORDER }} />
    {n != null && <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10 }}>{n}</Typography>}
  </Box>
);

// what is being worked, straight off the tasks - the assistant never writes this, because a
// model asked to restate the open list is a model that eventually invents a task (assistant.in_flight)
const InFlight = ({ rows, onOpenTask }) => !rows?.length ? null : (
  <>
    <SectionHead mark="🚀" label="In flight" n={rows.length} />
    <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden" }}>
      {rows.map((r, i) => (
        <Box key={r.tid} onClick={() => onOpenTask?.(r.tid)}
          sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.75, cursor: "pointer",
            borderTop: i ? `1px solid ${BORDER}` : "none", bgcolor: r.hot ? PANEL : "#fcfaf7",
            "&:hover": { bgcolor: PANEL2 } }}>
          <Box sx={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
            bgcolor: r.agent ? ROLES.working.solid : r.state.startsWith("a reply") ? ALERT : ROLES.muted.solid }} />
          <Typography variant="caption" sx={{ ...mono, color: ACCENT, fontWeight: 600, flexShrink: 0 }}>{r.ref}</Typography>
          <Typography variant="caption" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>{r.title}</Typography>
          <Typography variant="caption" sx={{ color: r.hot ? DIM : FAINT, flexShrink: 0, fontSize: 10.5 }}>{r.state}</Typography>
        </Box>
      ))}
    </Box>
  </>
);

// the day in four numbers, counted rather than asked for
const DayStats = ({ rows }) => !rows?.length ? null : (
  <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", px: 1.5, py: 1.25, mb: 0.5,
    border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fcfaf7" }}>
    {rows.map((s) => (
      <Box key={s.label} sx={{ display: "flex", alignItems: "baseline", gap: 0.6 }}>
        <Typography sx={{ fontSize: 17, fontWeight: 700, lineHeight: 1,
          color: s.hot && s.n ? ALERT : s.n ? INK : FAINT }}>{s.n}</Typography>
        <Typography variant="caption" sx={{ color: FAINT }}>{s.label}</Typography>
      </Box>
    ))}
  </Box>
);
const AssistantPost = ({ sel, onOpenTask, onChanged }) => {
  const [ideas, setIdeas] = useState(() => briefOf(sel.Brief)?.ideas || []);
  const brief = briefOf(sel.Brief) || {};
  const rv = brief.reviewed;
  const [showSkipped, setShowSkipped] = useState(false);
  const [busy, setBusy] = useState(null);
  const [notes, setNotes] = useState({});
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { const { data } = await api.get(`/api/assistant/ideas?mid=${sel.MessageId}`); if (data.data?.length) setIdeas(data.data); } catch { /* keep the post's own copy */ }
  }, [sel.MessageId]);
  useEffect(() => { load(); }, [load]);
  const act = async (i, verb) => {
    setBusy(`${i.id}:${verb}`); setErr("");
    try {
      const { data } = await api.post(`/api/assistant/ideas/${i.id}/${verb}`, { days: 1 });
      if (verb === "followup") setNotes((n) => ({ ...n, [i.id]: `drafted — the chase waits in Review on ${data.ref}` }));
      if (verb === "task" && data.taskId) onOpenTask?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "That did not work"); }
    setBusy(null); load(); onChanged?.();
  };
  const discuss = async (i) => {
    setBusy(`${i.id}:discuss`); setErr("");
    try {
      const { data } = await api.post(`/api/assistant/ideas/${i.id}/discuss`, {});
      await load();
      if (data.taskId) onOpenTask?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "The Assistant workspace could not open"); }
    setBusy(null);
  };
  const btn = { textTransform: "none", fontSize: 11.5, minWidth: 0, minHeight: 27, px: 1.1, lineHeight: 1.2 };
  const primary = { color: "#fff", background: ASSISTANT.gradient,
    "&:hover": { background: "linear-gradient(90deg, #465866, #698368)" } };
  const quiet = { color: DIM, borderColor: BORDER, bgcolor: PANEL,
    "&:hover": { borderColor: ASSISTANT.solid, bgcolor: "#f7f8f4" } };
  // ONE renderer for a line, called from inside whichever section it belongs to.
  const line = (i) => {
        const a = i.action || {}, open = i.status === "open", ev = a.event;
        return (
          <Box key={i.id} sx={{ px: 1.25, py: 0.85, mb: 0.6, borderRadius: 1.5, border: `1px solid ${ASSISTANT.bd}`, bgcolor: open ? ASSISTANT.tint : "#f4f3ef", opacity: open ? 1 : 0.72 }}>
            <Box sx={{ display: "flex", gap: 0.75, alignItems: "baseline" }}>
              <Typography variant="caption" sx={{ color: ASSISTANT.ink, fontWeight: 700, flexShrink: 0 }}>{IDEA_KIND[i.kind] || i.kind}</Typography>
              <Typography variant="body2" sx={{ color: INK, lineHeight: 1.45, flex: 1 }}>{i.text}</Typography>
            </Box>
            <Why text={i.why} />
            {ev && (
              <Typography variant="caption" sx={{ display: "block", color: DIM, mt: 0.3 }}>
                {ev.who?.length ? `with ${ev.who.join(", ")}` : ""}{ev.where ? ` · ${ev.where}` : ""}{ev.about ? ` · ${ev.about}` : ""}
              </Typography>
            )}
            {open ? (
              <>
                {(a.chat || []).map((turn, n) => (
                  <Box key={`${i.id}:chat:${n}`} sx={{ mt: 0.55, ml: turn.role === "owner" ? 3 : 0,
                    px: 1, py: 0.55, borderRadius: 1.25,
                    bgcolor: turn.role === "owner" ? "#e9e3d8" : PANEL,
                    border: `1px solid ${turn.role === "owner" ? "#d8d0c4" : BORDER}` }}>
                    <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.4 }}>
                      <Box component="span" sx={{ fontWeight: 700, color: turn.role === "owner" ? INK : ASSISTANT.ink }}>
                        {turn.role === "owner" ? "you" : "assistant"} · </Box>{turn.text}
                    </Typography>
                  </Box>
                ))}
                <Box sx={{ mt: 0.75, display: "flex", gap: 0.6, flexWrap: "wrap", alignItems: "center" }}>
                  {a.type === "followup" && (
                    <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={() => act(i, "followup")} sx={{ ...btn, ...primary }}>
                      {busy === `${i.id}:followup` ? "drafting…" : "Draft follow-up"}</Button>
                  )}
                  {a.mid && (
                    <Button size="small" variant={a.type === "task" ? "contained" : "outlined"} disableElevation disabled={!!busy} onClick={() => act(i, "task")}
                      title={a.title ? `Make it a task: ${a.title}` : "Make it a task"}
                      sx={{ ...btn, ...(a.type === "task" ? primary : quiet) }}>
                      {busy === `${i.id}:task` ? "starting…" : "Make it a task"}</Button>
                  )}
                  {a.tid && <Button size="small" variant="outlined" onClick={() => onOpenTask?.(a.tid)} sx={{ ...btn, ...quiet }}>Open {ref(a.tid)}</Button>}
                  <Button size="small" variant="contained" disableElevation disabled={!!busy}
                    onClick={() => discuss(i)} sx={{ ...btn, ...primary }}>
                    {busy === `${i.id}:discuss` ? "opening…" : a.discussion_tid ? `Continue in ${ref(a.discussion_tid)}` : "Discuss in Assistant"}
                  </Button>
                </Box>
                <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.35 }}>
                  Opens the full Assistant chat with this idea and its context carried over.
                </Typography>
              </>
            ) : (
              <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.4 }}>
                {notes[i.id] || (i.status === "done" ? "done" : i.status === "dismissed" ? "not this — noted" : i.status === "snoozed" ? "snoozed" : i.status)}
              </Typography>
            )}
          </Box>
        );
  };

  // the sections, in the order the day reads. An empty one is not drawn - a header over nothing
  // is worse than no header, because it says the assistant looked and found something.
  const bySection = (k) => ideas.filter((i) => (i.section || "ideas") === k);
  return (
    <Box sx={{ mb: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
        <TaskuaryMark size={15} />
        <Typography sx={{ color: ASSISTANT.ink, fontWeight: 700, fontSize: 13 }}>Your assistant</Typography>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>{fmtDateTime(sel.SentAt)}</Typography>
        {err && <Typography variant="caption" sx={{ color: ALERT_INK }}>{err}</Typography>}
      </Box>
      <DayStats rows={brief.stats} />
      {SECTIONS.map((sec) => {
        const rows = bySection(sec.key);
        if (!rows.length) return null;
        // In flight is FACT, not the model's work, so it sits between the sections that are -
        // after what people said, before what is still hanging.
        return (
          <React.Fragment key={sec.key}>
            {sec.key === "loose" && <InFlight rows={brief.flight} onOpenTask={onOpenTask} />}
            <SectionHead mark={sec.mark} label={sec.label} n={rows.length} />
            {rows.map(line)}
          </React.Fragment>
        );
      })}
      {/* ...and when nothing is hanging, In flight still belongs on the post */}
      {!bySection("loose").length && <InFlight rows={brief.flight} onOpenTask={onOpenTask} />}
      {!ideas.length && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1, lineHeight: 1.7 }}>
          Nothing worth saying this time — which is most checks. What it read is below.
        </Typography>
      )}
      {rv && (
        <Box sx={{ mt: 1.5, px: 1.25, py: 0.7, borderRadius: 1.5, border: `1px dashed ${BORDER}`, bgcolor: "#faf8f4" }}>
          <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.45 }}>
            <Box component="span" sx={{ fontWeight: 700, color: "#6b5f45" }}>what it reviewed · </Box>
            {Object.entries(rv.candidates || {}).map(([k, v]) => `${v} ${IDEA_KIND[k] || k}`).join(", ") || "no candidates"}
            {rv.people != null ? ` · ${rv.people} thread${rv.people === 1 ? "" : "s"} of what people said` : ""}
            {rv.recent != null ? ` · ${rv.recent} sender/subject line${rv.recent === 1 ? "" : "s"} from the last two days · ${rv.week} task${rv.week === 1 ? "" : "s"} closed this week`
              : ` · ${rv.today} message${rv.today === 1 ? "" : "s"} from today`}
            {` · ${rv.open} open task${rv.open === 1 ? "" : "s"} · ${rv.said} line${rv.said === 1 ? "" : "s"} already said`}
            {rv.model ? " · the model chose the lines" : " · no model — the hub's facts in its own words"}
          </Typography>
          {/* what it left for its next check - so you can see what it will NOT research again */}
          {rv.notes && (
            <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.45, mt: 0.3 }}>
              <Box component="span" sx={{ fontWeight: 700, color: "#6b5f45" }}>note to its next check · </Box>{rv.notes}
            </Typography>
          )}
          {!!rv.skipped?.length && (
            <>
              <Typography variant="caption" onClick={() => setShowSkipped((v) => !v)}
                sx={{ display: "block", mt: 0.3, color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                {showSkipped ? "hide" : "show"} what it looked at and let go — {rv.skipped.length} {showSkipped ? "↑" : "↓"}</Typography>
              {showSkipped && rv.skipped.map((c) => (
                <Typography key={c.key} variant="caption" sx={{ display: "block", color: FAINT, mt: 0.3, pl: 1, borderLeft: `2px solid ${BORDER}`, whiteSpace: "pre-wrap" }}>
                  <Box component="span" sx={{ fontWeight: 700 }}>{IDEA_KIND[c.kind] || c.kind} · </Box>{c.facts}</Typography>
              ))}
            </>
          )}
        </Box>
      )}
    </Box>
  );
};

const MineToDo = ({ messageId, onMade }) => {
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState(null);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/mine`, {});
      setMade(data.ref); onMade?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not make the task"); }
    setBusy(false);
  };
  return (
    <ChoiceRow tint="#eae4d8" busy={busy || !!made} onClick={go}
      icon={<AssignmentIndIcon sx={{ fontSize: 14, color: "#55697a" }} />}
      label={made ? `${made} — on your list` : "Mine to do"}
      hint={err || (made ? "a task with your name on it, no agent" : "a task on your own list — nobody is dispatched")} />
  );
};

const SplitTask = ({ row, onSplit, compact = false }) => {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");
  if (!row.TaskId || (row.ChainSize || 1) < 2) return null;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${row.MessageId}/split`, {});
      setDone(data.taskId); onSplit?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not split it out"); }
    setBusy(false);
  };
  return compact ? (
    <TrayBtn disabled={busy || !!done} onClick={go} icon={<CallSplitIcon sx={{ fontSize: 15 }} />}
      title={done ? "This message now has its own task" : `separate this message from ${ref(row.TaskId)}`}>
      {done ? `Opened ${ref(done)}` : "Separate task"}
    </TrayBtn>
  ) : (
    <ChoiceRow tint="#e3e6e1" busy={busy || !!done} onClick={go}
      icon={<CallSplitIcon sx={{ fontSize: 14, color: "#6f8a6e" }} />}
      label={done ? `Now its own task ${ref(done)}` : "Give this message its own task"}
      hint={err || (done ? "send it to an agent above" : `a separate ask from the rest of ${ref(row.TaskId)}`)} />
  );
};

const ReviewActions = ({ reviewId, draft, editText, setEditText, decide, sendErr, clearSendErr, canSend }) => (
  <Box>
    <TextField fullWidth multiline minRows={3} size="small" placeholder="Edit the draft (or approve as-is)"
      value={editText ?? draft ?? ""} onChange={(e) => setEditText(e.target.value)} sx={{ mb: 1 }} />
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      {/* ONE approve: it sends what is in the box, edited or not - two buttons asked you to
          declare something the text already shows. A channel that cannot CARRY the reply
          (github with replies off) offers closing instead of a send that bounces. */}
      {canSend === false ? (
        <Button size="small" variant="contained" disableElevation
          sx={{ bgcolor: "#8a8276", "&:hover": { bgcolor: "#6b6459" } }}
          title="GitHub replies are off (GitHub card → Reply to issue/PR authors) — close this without sending"
          onClick={() => decide(reviewId, "no_reply")}>No response required</Button>
      ) : (
        <>
          <Button size="small" variant="contained" disabled={!(editText ?? draft ?? "").trim()}
            onClick={() => decide(reviewId, "approve", editText ?? draft)}
            title="Sends the text above on the channel it arrived on">Approve &amp; send</Button>
          <Button size="small" sx={{ color: "#867f74" }} onClick={() => decide(reviewId, "no_reply")}>No reply needed</Button>
        </>
      )}
      <Button size="small" color="error" onClick={() => decide(reviewId, "reject")}>Reject</Button>
    </Box>
    {sendErr && (
      <Alert severity="error" sx={{ mt: 1 }} onClose={clearSendErr}>
        <b>Approved, but it did not send.</b> {sendErr}
        <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
          The text is kept on the task marked NOT SENT, so nothing is lost — send it by hand, or hand
          the task to a person on a channel that works.
        </Box>
      </Alert>
    )}
  </Box>
);
