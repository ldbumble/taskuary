// The Assistant page's sidebar and stage: the buttons, the filter and the sync line over the Work rail (the
// ranked pipe AssistantView draws), and beside it the stage where a row opens whole - the message, why triage
// sent it where it did, the agent's work and the reply. A live socket pushes new rows in; the list is not on a
// timer. (The Timeline - every message in date order, a tab beside Work - was removed 2026-10-15.)
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Drawer, IconButton, ListSubheader, MenuItem, Popover, TextField, Tooltip, Typography, useMediaQuery,
} from "@mui/material";
import ApprovalInterrupt from "./ApprovalInterrupt.jsx";
import { interruptOf, captureInterruptedReply, interruptedReplyTarget, restoreInterruptedReply } from "./approvalInterrupt.js";
import CloseIcon from "@mui/icons-material/Close";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import CheckIcon from "@mui/icons-material/Check";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import api from "./api";
import { placeName } from "./words.js";
import { hint as bHint, label as bLabel } from "./buttons.js";   // `btn` is this file's button style
import { ideaCounted, ideaWord } from "./lanes.js";
import SearchEverything, { OPEN_SEARCH, searchPicked } from "./SearchEverything.jsx";
import { fadeBand } from "./timelineFade.js";
import { syncFace, syncPhaseLabel } from "./syncTiming.js";
import { observeSync } from "./syncObserver.js";
import { lazyGeneral } from "./lazyGeneral.js";
import { availablePickerChannels, channelsForCategory } from "./feedFilters.js";
import { splitTimelineMeetings } from "./timelineMeetings.js";
import { RemindPicker } from "./RemindMe.jsx";
import { onLive } from "./live.js";
import { detailPhase, feedHeaders, feedOk, takeFeed, threadDetail } from "./feedLoad.js";
import { ALERT, ALERT_BD, ALERT_INK, ASSISTANT, ROLES, PILL_COLORS, BG, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, GRADIENT, card, mono } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import BarChartIcon from "@mui/icons-material/BarChart";
import PowerOutlinedIcon from "@mui/icons-material/PowerOutlined";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import TuneIcon from "@mui/icons-material/Tune";
import { SIDE_NAV } from "./sideNav.js";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { Attachments } from "./Attachments.jsx";
import { AgentPicker, ChannelIcon, RefChip, CcRow, ChoiceRow, AgentReport, Confirm, DiffBlock, ProofCard, SendToAgent, NotMine, fmtDateTime, localDay, tsMs, cleanText, splitQuoted, IDLE_WAITING, TellAgent, TellAgentButton, LiveConsole, useAgents, useVoiceReady, TaskuaryMark } from "./ui.jsx";
import MicIcon from "@mui/icons-material/Mic";
import MicOffIcon from "@mui/icons-material/MicOff";
import { Md, looksMd } from "./md.jsx";
import DigestText from "./DigestText.jsx";
import TodayMeetingsStrip from "./TodayMeetingsStrip.jsx";
import { sourceOf, structured } from "./feedText.js";
import { HOLD_TAG, ROADS, hasTag, roadOf, stateOf, triageSummary, verdictOf } from "./timelineState.js";
import { sendBlockLine, draftState, replyEnvelope, replySendFailure } from "./sendState.js";
import { extraTriageFields, intentLabel, kindLabel, latestTriageVerdict, legacyTriageVerdict, relationshipLabel, routeIntent, routeWhy } from "./triageVerdict.js";
import ReplyFiles from "./ReplyFiles.jsx";
import { AGENT } from "./taskLifecycle.js";
import StateMark from "./StateMark.jsx";


import NewSheet from "./NewSheet.jsx";
import { channelCanSend, useCapabilities } from "./capabilities.js";
import AddIcon from "@mui/icons-material/Add";
import { isVoicePlaceholder, voiceNoteBody } from "./voiceNote.js";
import { TerminalPane } from "./TerminalView.jsx";
import {
  fullProcessingRow, processingDetailPath, processingErrorCode, processingErrorMessage, processingMessageDetail, processingRefreshCandidate,
  processingRowId, processingSelectionKey, processingTarget, processingTransportLimit, rowOwnsMessage, unreadProcessingRows,
} from "./processingAll.js";
import { plural } from "./timeWords.js";

const GeneralWorkspace = React.lazy(lazyGeneral("GeneralWorkspace"));   // guarded: a stale chunk reloads once (lazyGeneral.js)

// All and Unread are the only Timeline views. Kind and source remain independent filters.
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
  github: "Repositories", gitlab: "GitLab instances", report: "Reports", assistant: "Advisor posts", own: "Your own notes",
  jira: "Jira issues", asana: "Asana tasks", monday: "Monday items", linear: "Linear issues",
  clickup: "ClickUp tasks", todoist: "Todoist tasks",
  trello: "Trello cards", notion: "Notion pages", azdo: "Azure DevOps items",
  sentry: "Sentry errors", pagerduty: "PagerDuty incidents",
  aws: "AWS buckets & log groups", azure: "Azure containers & workspaces" };


// ONE control for BOTH filters. A switch and two pickers of identical shape sat in a row, so four
// controls read as one undifferentiated strip and none of them said what it was for (the owner,
// 2026-09-16: "the work/timeline vs all kinds/all sources filters look weird"). This one says what
// it is filtering TO - "All items", "Email", "Email - rrdbreports" - and opens on both lists at once.
export const filterLabel = (cat, pick, cats = CATEGORIES, labels = CHANNEL_LABELS) => {
  const kind = cat ? (cats.find((o) => o.key === cat)?.label || cat) : "";
  const src = !pick ? ""
    : pick.startsWith("channel:") ? `all ${labels[pick.slice(8)] || pick.slice(8)}`.toLowerCase()
      : String(pick.split(":").slice(2).join(":")).split("@")[0];
  return [kind, src].filter(Boolean).join(" \u00b7 ") || "All items";
};

// the sidebar buttons' marks, one per SIDE_NAV key
const NAV_ICONS = { new: AddIcon, reports: BarChartIcon, connections: PowerOutlinedIcon, hub: TravelExploreIcon, settings: TuneIcon };

function FilterButton({ cat, pick, channels, srcByChannel, srcQ, setSrcQ, onChange }) {
  const [el, setEl] = useState(null);
  const close = () => { setEl(null); setSrcQ(""); };
  const narrowed = !!cat || !!pick;
  const q = srcQ.trim().toLowerCase();
  const label = filterLabel(cat, pick);
  return (
    <>
      {/* THE ROW'S ONE CONTROL since the Timeline tab went (the owner, 2026-10-15: "replace it with the filter being a little
          larger"): full width, and it says on its face what the rail is narrowed to - it was an icon beside Work | Timeline
          that left that to its tooltip. It fills in when the rail is narrowed. */}
      <Box component="button" type="button" onClick={(e) => setEl(e.currentTarget)}
        data-tq-filter="true" aria-label={`Filter the rail - ${label}`}
        sx={{ flex: 1, minWidth: 0, height: 30, display: "flex", alignItems: "center", gap: 0.75, px: 1.25,
          borderRadius: "8px", border: `1px solid ${narrowed ? "#b9c3cb" : BORDER}`, bgcolor: narrowed ? "#e4e9ee" : PANEL,
          cursor: "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 600, color: narrowed ? INK : DIM, textAlign: "left",
          "&:hover": { borderColor: "#b9c3cb", bgcolor: narrowed ? "#e4e9ee" : PANEL } }}>
        <FilterAltIcon sx={{ fontSize: 15, color: narrowed ? ACCENT : DIM, flexShrink: 0 }} />
        <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</Box>
        <ChevronRightIcon sx={{ fontSize: 14, color: FAINT, transform: "rotate(90deg)", flexShrink: 0 }} />
      </Box>
      <Popover open={!!el} anchorEl={el} onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{ paper: { sx: { width: 320, maxHeight: 560, p: 1.25 } } }}>
        <Typography sx={{ fontSize: 9.5, fontWeight: 600, letterSpacing: ".1em", textTransform: "uppercase", color: FAINT, mb: 0.75 }}>Kind</Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6, mb: 1.25 }}>
          {CATEGORIES.map((o) => (
            <Chip key={o.key} size="small" label={o.label} data-tq-kind={o.key || "all"}
              onClick={() => onChange(o.key, pick)}
              sx={{ height: 24, fontSize: 11, fontWeight: 600, borderRadius: 99,
                bgcolor: cat === o.key ? "#e4e9ee" : PANEL2, color: cat === o.key ? "#41525f" : DIM,
                border: `1px solid ${cat === o.key ? "#cbd4dc" : BORDER}` }} />
          ))}
        </Box>
        <Typography sx={{ fontSize: 9.5, fontWeight: 600, letterSpacing: ".1em", textTransform: "uppercase", color: FAINT, mb: 0.75 }}>Source</Typography>
        <TextField fullWidth placeholder="search sources…" value={srcQ} onChange={(e) => setSrcQ(e.target.value)}
          sx={{ bgcolor: "#fff", mb: 0.5 }} inputProps={{ style: { fontSize: 12, padding: "5px 8px" } }} />
        <Box sx={{ maxHeight: 220, overflowY: "auto", mx: -0.5 }}>
          <MenuItem selected={!pick} onClick={() => onChange(cat, "")} sx={{ fontSize: 12, borderRadius: 1 }}>all sources</MenuItem>
          {/* 96 discovered buckets turned this into a page-long wall. It is a bounded, searchable
              list: type to narrow, and each channel shows a few with a count for the rest. */}
          {channels.flatMap((ch) => {
            const all = (srcByChannel[ch] || []).filter((n) => !q || String(n).toLowerCase().includes(q));
            const label = CHANNEL_LABELS[ch] || ch;
            if (q && !all.length && !label.toLowerCase().includes(q)) return [];
            const shown = q ? all.slice(0, 12) : all.slice(0, 6);
            return [
              <ListSubheader key={`h${ch}`} sx={{ fontSize: 9.5, lineHeight: 1.9, color: FAINT, letterSpacing: 1,
                textTransform: "uppercase", bgcolor: PANEL, px: 1 }}>
                {label}{all.length > shown.length ? ` \u00b7 ${all.length}` : ""}
              </ListSubheader>,
              <MenuItem key={`c${ch}`} selected={pick === `channel:${ch}`} onClick={() => onChange(cat, `channel:${ch}`)}
                sx={{ fontSize: 12, borderRadius: 1 }}>all {label.toLowerCase()}</MenuItem>,
              ...shown.map((n) => (
                <MenuItem key={`${ch}:${n}`} selected={pick === `src:${ch}:${n}`} onClick={() => onChange(cat, `src:${ch}:${n}`)}
                  sx={{ fontSize: 11.5, pl: 2.5, borderRadius: 1 }}>
                  <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n}</Box>
                </MenuItem>
              )),
              ...(all.length > shown.length ? [
                <MenuItem key={`m${ch}`} disabled sx={{ fontSize: 10.5, pl: 2.5, color: FAINT, opacity: 1 }}>
                  +{all.length - shown.length} more — type to find one
                </MenuItem>] : []),
            ];
          })}
        </Box>
        {narrowed && (
          <Button size="small" onClick={() => { onChange("", ""); close(); }}
            sx={{ mt: 0.75, fontSize: 11, textTransform: "none", color: ACCENT }}>Show everything</Button>
        )}
      </Popover>
    </>
  );
}

const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;

// What the row is, for the chip. A scheduled report or a feed-only connection's item was
// never judged - it is information. Only a policy 'ignore' is a verdict.
const actionOf = (r) => (r.Channel === "report" ? "report"
  : r.MsgStatus === "feed" ? "feed"
    : r.MsgStatus === "triaging" ? "triaging"
    : r.MsgStatus === "error" ? "error"
    : r.MsgStatus === "ignored" ? "ignore"
      : r.MsgStatus === "filed" ? "filed"
        : r.ReviewKind === "auto" ? "auto"
          : r.ReviewId ? "draft" : "task_only");

// the error state is the durable answer (PW-036); the reason regex still recognises failures
// recorded as filed before that state existed
const triageFailed = (r) => r?.MsgStatus === "error" || /(?:AI )?triage (?:failed|returned an answer it could not read)/i
  .test(String(r?.RouteReason || ""));

// Which rows get the PLAIN pane instead of the four stages. An idea does not belong here: it is
// triaged like anything else and its verdict now rides on the row, so it has a Triage step to show
// and a Message step to fill - it only ever fell to the bare pane because its open target is not a
// message (the owner, 2026-09-15: "why does idea show this screen and not the regular all other on
// the timelines"). A standalone task or review still has no story to tell, so they keep it.
const bareDetail = (sel) => !!sel?.ProcessingItemId && !["message", "idea"].includes(sel.OpenTarget?.kind);

// NeedsYou comes from the server and means one thing: nobody else is moving this. It
// outranks the verdict chip, because "what happened to it" matters less than "is it mine".
const needsYou = (r) => !!r.NeedsYou && r.TaskStatus !== "done";

// One plain-English sentence: what the hub did + where it stands.
const blurb = (r) => {
  // the row's own DIRECTION, as the server sends it - never the classifier's sentence searched for "your reply" (2026-10-11)
  if (r.Direction === "out" || r.Category === "yours")
    return r.TaskId ? `Your reply — kept on ${ref(r.TaskId)} so the thread shows both sides` : "Your reply — kept for context, never a task";
  if (r.Channel === "assistant") return "The assistant's post — open it to talk back or act on a suggestion";
  if (r.Channel === "report") return "Scheduled report — hover to read the summary";
  if (r.MsgStatus === "feed") return "Shown for information — this connection is a feed, not a task trigger";
  if (r.MsgStatus === "triaging") return "On the timeline first — triage is deciding what it is";
  if (r.MsgStatus === "error") return `Triage failed — ${String(r.RouteReason || "").split(" - ")[0] || "no verdict"}; retry, or choose what it is`;
  if (triageFailed(r)) return "Triage could not classify this — filed safely; choose what it is";
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

const PAGE = 100;

// Today's meetings, fetched once for the rail and re-read every 30 s: a meeting that has started counts in
// "in today" beside the mail that arrived (a meeting is a row too).
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

// The rail is the Assistant page's rail (AssistantView.jsx): `top` is its ranked Work pipe and `stage`
// is the conversation. A card's "open on the Timeline" (#msg=) opens its message on the stage.
// On a phone the chat and the rail take turns: `railOnNarrow` says which one is up.
// The countdown ticks on its own. As a 1 s state change on FeedView it re-rendered every row of the rail
// every second for as long as the tab was open.
function NextIn({ atRef, render }) {
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((t) => t + 1), 1000); return () => clearInterval(id); }, []);
  return render(atRef.current ? Math.max(0, Math.round((atRef.current - Date.now()) / 1000)) : null);
}

export default function FeedView({ onOpenTask, onChanged, active = true, top = null, stage = null, rowMode = "task", onPull = null, railOnNarrow = false, onInventoryFilter = null, unreadInventory = null, onGo = null, navOn = "", openNew = 0, setupMode = false, setupRail = null }) {
  // below md there is no stage beside the rail; whatever is opened slides over it instead, so a
  // tap on a row is never a tap that did nothing
  const narrow = useMediaQuery("(max-width:899.95px)");
  // WORK IS THE ONLY VIEW. The Timeline - every message in date order, a second tab beside Work - is gone (the owner,
  // 2026-10-15: "removing the timeline tab ... replace it with the filter being a little larger"); the rail is the pipe.
  const visibleStage = stage;
  const chatMode = rowMode === "chat" && !!onPull;       // a row click pulls it into the chat, or opens it on the stage
  const railShown = !narrow || !visibleStage || railOnNarrow;
  const stageShown = !narrow || (!!visibleStage && !railOnNarrow);
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
  // WORK is ranked and its categories are headings inside the rail that freeze as you scroll, so the only thing the
  // scroll is watched for is whether anything is still BELOW the fold (the bottom fade).
  const measureMore = useCallback(() => {
    const rail = railRef.current; if (!rail) return;
    setMore(rail.scrollTop + rail.clientHeight < rail.scrollHeight - 4);
  }, []);
  useEffect(() => {
    const rail = railRef.current; if (!rail) return undefined;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; measureMore(); });
    };
    rail.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
    return () => { rail.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, [measureMore]);
  // A new pile is a new layout, and the pile admits its rows a batch per animation frame - so the
  // rail keeps changing under the fade. Watch for rows ARRIVING or LEAVING, and measure once more
  // after the .55s a landing row takes to slide into place.
  //
  // childList only, deliberately: an attribute watch over the rail's subtree also fired on every
  // inline `top` React wrote and on every re-render the composer caused, which cost 600ms of
  // keystroke latency in the phase-zero budget (2130ms against a 1500ms limit).
  useEffect(() => {
    const rail = railRef.current; if (!rail) return undefined;
    let settle = 0, frame = 0;
    const remeasure = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; measureMore(); });
    };
    if (typeof MutationObserver === "undefined") { remeasure(); return undefined; }
    const observer = new MutationObserver(() => {
      remeasure();
      clearTimeout(settle);
      settle = setTimeout(remeasure, 600);          // the landing transition, then the resting tops
    });
    observer.observe(rail, { childList: true, subtree: true });
    remeasure();
    return () => { observer.disconnect(); clearTimeout(settle); if (frame) cancelAnimationFrame(frame); };
  }, [unreadInventory, measureMore]);
  const [newOpen, setNewOpen] = useState(false);     // the ＋ New sheet (NewSheet.jsx)
  useEffect(() => { if (openNew) setNewOpen(true); }, [openNew]);   // ...or a link asked for it (#new-task)
  const [rows, setRows] = useState(null);
  const loadRequest = useRef(0);                     // the newest load wins if responses land out of order
  const [cat, setCat] = useState("");                // broad content family; exact choices live in the source picker
  const [pick, setPick] = useState("");              // "" all in category | "channel:x" | "src:channel:name"
  const [srcByChannel, setSrcByChannel] = useState({});   // channel -> connection names
  const [srcQ, setSrcQ] = useState("");                    // the picker's own search box
  const [detail, setDetail] = useState(null);
  const [editText, setEditText] = useState(null);    // null = untouched; "" = deliberately cleared
  const [err, setErr] = useState("");
  const rowsLen = useRef(0);
  const etagRef = useRef("");

  // one place turns (category, pick) into query params: a category is a channel csv, a
  // pick narrows to one channel or one named connection inside it
  const fparams = useCallback(() => {
    const chans = channelsForCategory(cat, Object.keys(srcByChannel));
    const p = {};
    if (pick.startsWith("src:")) {
      const [, ch, ...rest] = pick.split(":");
      p.channel = ch; p.source = rest.join(":");
    } else if (pick.startsWith("channel:")) {
      p.channel = pick.slice(8);
    } else if (chans) {
      p.channel = chans.join(",");
    }
    return p;
  }, [cat, pick, srcByChannel]);

  const canonicalUnread = Boolean(unreadInventory?.canonical);
  const inventoryFilter = JSON.stringify(fparams());
  useEffect(() => { onInventoryFilter?.(inventoryFilter); }, [inventoryFilter, onInventoryFilter]);

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
  const pendingPick = useRef("");
  useEffect(() => { loadRequest.current += 1; setPick(pendingPick.current); pendingPick.current = ""; }, [cat]); // switching category clears the narrower pick
  // SEARCH OVER EVERYTHING (SearchEverything.jsx): the bar on the rail, or Ctrl+K while this view is on screen
  const [searchOpen, setSearchOpen] = useState(false);
  useEffect(() => {
    if (!active) return undefined;
    const k = (e) => { if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [active]);
  // ...and the bar on the top line opens it from ANY view: the dialog floats over the Board or the Game, and only a pick
  // brings Chat up (searchPicked). It used to switch to Chat first, so searching from the Board left it (2026-10-15)
  useEffect(() => {
    const o = () => setSearchOpen(true);
    window.addEventListener(OPEN_SEARCH, o);
    return () => window.removeEventListener(OPEN_SEARCH, o);
  }, []);

  // (Re)fetch from the top - span covers everything already on screen so the 30s
  // refresh never shrinks the list under the user.
  const load = useCallback(async (span) => {
    const request = ++loadRequest.current;
    try {
      const limit = processingTransportLimit(Math.max(span || 0, PAGE));
      // Assistant owns Work and supplies its canonical pile. On the first render that prop is
      // still null while /api/funnel/pile is in flight; fetching the legacy feed here starts a
      // second, obsolete database walk (and source discovery can start it again). Wait for the
      // one authoritative response instead of competing with it under the store lock.
      if (top && !unreadInventory) return;
      if (canonicalUnread) {
        const batch = unreadProcessingRows(unreadInventory) || [];
        setRows(batch); rowsLen.current = batch.length; setErr("");
        return;
      }
      const res = await api.get("/api/feed", {
        params: { limit, ...fparams() },
        headers: feedHeaders(etagRef.current),
        validateStatus: feedOk,
      });
      if (request !== loadRequest.current) return;
      const batch = takeFeed(res, etagRef);
      if (batch == null) return;                 // 304: the list on screen is still the truth
      setRows(batch); rowsLen.current = batch.length; setErr("");
    } catch (e) {
      if (request === loadRequest.current) setErr(processingErrorMessage(e, "Failed to load the feed"));
    }
  }, [fparams, canonicalUnread, unreadInventory, top]);

  // Sync tracks the server's actual stage. Rows remain readable throughout;
  // elapsed time and lost live events cannot manufacture completion.
  const [syncing, setSyncing] = useState(false);   // an owner-started check awaiting status
  const [bgSync, setBgSync] = useState(false);     // the startup catch-up - rows stay readable
  const [syncWhat, setSyncWhat] = useState("");
  const [syncPhase, setSyncPhase] = useState("");
  const [syncUnknown, setSyncUnknown] = useState(false);
  const syncObserver = useRef(null);
  const [lastSync, setLastSync] = useState(null);
  const [syncStarted, setSyncStarted] = useState(false);
  const [every, setEvery] = useState(10);            // the server's cadence, not a guess
  // the server's clock, as an offset from OUR clock: nextPollAt is its time, so the countdown
  // uses (next - serverNow) and never trusts the two machines to agree on the hour
  const [triageErr, setTriageErr] = useState("");    // the brain's last failure, until it answers again
  const [thinking, setThinking] = useState("");      // ...and the line she reads about it, while anything is held
  const [fade, setFade] = useState("normal");        // Settings > Display; height of the viewport's bottom fade
  // ...drawn only while something is actually BELOW it. The band means "rows are passing behind the
  // bottom edge" (timelineFade.js): true of the Timeline's endless history, and true of work only
  // when a band has been opened wide enough to overflow. Painted unconditionally it dimmed the
  // agents-working band at the foot of a list that fits, which is the one thing nothing was hiding
  // (the owner, 2026-09-16: "if fyi overlaps past the bottom and there is a scroll then fade is
  // okay. but if bottom is agent working then we want to see them").
  const [more, setMore] = useState(false);
  const bottomFade = fadeBand(fade);
  const nextAtRef = useRef(null);                     // Date.now() when the server's next poll is due
  const seenPollAt = useRef(null);
  const wasRunning = useRef(false);
  const completionTimer = useRef(null);
  const applyStatus = useCallback((data) => {
    if (!data) return;
    if (data.everyMinutes != null) setEvery(data.everyMinutes);
    const pollAt = Number(data.lastPollAt) || null;
    const completedBetweenChecks = seenPollAt.current != null && pollAt != null && pollAt > seenPollAt.current;
    const finishedAt = Number(data.lastFetchCompletedAt) || null;
    const clockAt = finishedAt || pollAt;
    if (clockAt) setLastSync(new Date(Date.now() - (data.now - clockAt) * 1000));
    setSyncStarted(!finishedAt && !!pollAt);
    if (pollAt) seenPollAt.current = pollAt;
    nextAtRef.current = data.nextPollAt ? Date.now() + (data.nextPollAt - data.now) * 1000 : null;
    setTriageErr(data.triageError || "");
    setThinking(data.thinking || "");
    if (data.timelineFade) setFade(data.timelineFade);
    // a coalesced feed-changed can fold running+idle into one idle payload, so lastPollAt
    // advancing is how a sub-second automatic poll still gets a visible receipt
    const running = data.status?.state === "running" || data.ingest?.state === "running";
    const what = data.status?.what || data.ingest?.what || "";
    setSyncUnknown(false);
    setSyncPhase(data.status?.phase || "");
    if (running) {
      clearTimeout(completionTimer.current);
      setBgSync(true); setSyncWhat(what);
    } else if (wasRunning.current) {
      setBgSync(false); setSyncWhat(""); load(rowsLen.current);
    } else if (completedBetweenChecks) {
      setBgSync(true); setSyncWhat("check finished"); load(rowsLen.current);
      clearTimeout(completionTimer.current);
      completionTimer.current = setTimeout(() => { setBgSync(false); setSyncWhat(""); }, 900);
    }
    wasRunning.current = running;
    if (!running) setSyncing(false);
  }, [load]);
  useEffect(() => {
    // gated on `active`: the Timeline stays mounted behind another tab, and coming back
    // re-asks at once. Hidden windows stay subscribed via onLive but do not refetch.
    if (!active) return undefined;
    const observer = observeSync({
      read: () => api.get("/api/ingest/status", { timeout: 10000 }).then(({ data }) => data),
      changed: applyStatus,
      failed: () => setSyncUnknown(true),
      subscribe: refresh => onLive(["feed-changed", "ingest-status"], refresh),
    });
    syncObserver.current = observer;
    return () => { observer.stop(); syncObserver.current = null; clearTimeout(completionTimer.current); };
  }, [applyStatus, active]);
  const syncNow = useCallback(async (silent) => {
    if (syncUnknown) { await syncObserver.current?.refresh(); return; }
    if (!silent) setSyncing(true);
    try { await api.post("/api/ingest/poll"); }
    catch { setSyncUnknown(true); }
    await syncObserver.current?.refresh();
  }, [syncUnknown]);

  const loadLatest = useRef(load);
  loadLatest.current = load;
  useEffect(() => {
    // Only a real filter change closes detail. `load` also changes whenever the Assistant supplies
    // a newer Work inventory; coupling this reset to that callback made every background sync
    // close an open detail panel.
    etagRef.current = "";                        // a new filter is not the same page
    detailEpoch.current += 1; want.current = null;
    setSel(null); setEditText("");   // filter switch: never leave a stale review panel up
    loadLatest.current();
  }, [inventoryFilter]);                    // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!active) return undefined;
    // Rows only. The INGEST clock lives on the server; this socket is how the list learns
    // a row landed. Coming back to the page also asks for the newest snapshot.
    loadLatest.current(rowsLen.current);
    return onLive("feed-changed", () => loadLatest.current(rowsLen.current));
  }, [active]);
  useEffect(() => {
    // Work is supplied by AssistantView rather than fetched here. A newer pile replaces its
    // rows, but it is a data refresh - not a scope change and never a reason to close detail.
    if (active && unreadInventory) loadLatest.current(rowsLen.current);
  }, [active, unreadInventory]);

  const [sel, setSel] = useState(null);
  const [sendErr, setSendErr] = useState("");     // approved, but the channel refused it
  const editOwner = useRef("");                  // canonical item + exact review whose draft is being edited
  const [interrupt, setInterrupt] = useState(null);   // PW-239: the click that did not send
  const [compare, setCompare] = useState(null);       // the refreshed draft, shown beside the owner's edit
  const [savedReplies, setSavedReplies] = useState({});
  const [recoveringReply, setRecoveringReply] = useState(false);
  const recoveryFlight = useRef(null);
  const hoverTimer = useRef(null);
  const want = useRef(null);                    // newest selection wins if fetches land out of order
  const detailEpoch = useRef(0);                // request ownership across filters, views and closes
  // `quiet` is the hover path: the panel keeps showing the row you were on until the next one's
  // detail has ARRIVED, then header and body swap in one render. Clearing the detail first
  // meant every hover flashed a spinner in the panel before filling it - sweeping down a list
  // of tasks read as the page labouring (the owner, 2026-08-30). A click still switches at once.
  // Details are fetched the moment the cursor ENTERS a row and kept for a minute, so by the time
  // the short rest is over the body is usually already here - hover felt slow when the fetch only
  // started after the rest. (no task = report / filed / ignored: the message itself, whole - the
  // feed row only carries a truncated preview.)
  const cache = useRef(new Map());
  const fetchDetail = (row, targetOverride = null) => {
    const key = processingSelectionKey(row, targetOverride);
    const hit = cache.current.get(key);
    if (hit && Date.now() - hit.at < 60000) return hit.p;
    const canonicalPath = processingDetailPath(row, targetOverride);
    // ...and a row with no task gets its whole CONVERSATION, not just itself. A chat is a
    // conversation by nature: showing one line of it hid every reply the owner sent from Teams
    // or Outlook, which is ingested as a `context` row and which the assistant has been reading
    // all along. The panel was the only place the history looked incomplete.
    const request = canonicalPath
      ? api.get(canonicalPath).then(({ data }) => {
          const requested = targetOverride ? { ...row, OpenTarget: targetOverride } : row;
          const full = fullProcessingRow(requested, data);
          if (data.view_changed) cache.current.delete(key);
          return { canonical: true, row: full, detail: processingMessageDetail(full, data.detail || {}) };
        })
      : (row.TaskId ? api.get(`/api/tasks/${row.TaskId}`).then((r) => ({ canonical: false, detail: r.data }))
        : api.get(`/api/messages/${row.MessageId}/thread`).then((r) => ({ canonical: false, detail: threadDetail(r.data) })))
        .catch(() => ({ canonical: false, detail: { messages: [] } }));   // legacy panel falls back to the preview
    let p;
    p = request.catch((error) => {
      // A failed speculative hover must not poison this target for a minute. Promise identity
      // keeps an older failure from evicting a newer request for the same semantic selection.
      if (cache.current.get(key)?.p === p) cache.current.delete(key);
      throw error;
    });
    cache.current.set(key, { at: Date.now(), p });
    return p;
  };
  // pinned = you CLICKED it: it stays until you click something else or the page ground. A hover
  // selection is transient - it closes when the cursor leaves the list and the panel.
  const pinned = useRef(false);
  const [pinnedOn, setPinnedOn] = useState(false);
  const setPinned = (v) => { pinned.current = v; setPinnedOn(v); };
  const closeSelection = () => {
    clearTimeout(hoverTimer.current); detailEpoch.current += 1; want.current = null;
    setPinned(false); setSel(null); setDetail(null);
  };
  const drill = async (row, quiet = false, targetOverride = null) => {
    const semanticKey = processingSelectionKey(row, targetOverride);
    const requestKey = `${++detailEpoch.current}:${semanticKey}`;
    const requestedTarget = processingTarget(row, targetOverride);
    const selectedTarget = processingTarget(sel);
    const sameSubject = processingRowId(sel) === processingRowId(row)
      && (!requestedTarget || !selectedTarget
        || (requestedTarget.kind === selectedTarget.kind && String(requestedTarget.id) === String(selectedTarget.id)));
    if (quiet && pinned.current && sameSubject) return;                 // pinned outranks hover
    if (!quiet) clearTimeout(hoverTimer.current);
    want.current = requestKey; setPinned(!quiet);
    const requested = targetOverride && row.ProcessingItemId ? { ...row, OpenTarget: targetOverride } : row;
    const p = fetchDetail(row, targetOverride);
    if (!quiet) { editOwner.current = ""; setSel(requested); setDetail(null); setEditText(null); setSendErr(""); setPanelLock(false); }
    try {
      const loaded = await p;
      if (want.current !== requestKey) return;                           // a newer hover won
      const selected = loaded.canonical ? loaded.row : requested;
      if (quiet) { editOwner.current = ""; setEditText(null); setSendErr(""); setPanelLock(false); }
      setSel(selected); setDetail(loaded.detail);
    } catch (e) {
      if (want.current !== requestKey) return;
      // through the helpers: the structured refusal is on the error, and the copy in
      // response.data.detail is flattened to a string for rendering (apiError.js). Reading the
      // flattened one is what showed a reconcile lag as "Request failed with status code 409".
      if (processingErrorCode(e) === "processing_target_moved") {
        setErr(e.detail?.message || "That item changed. Refreshing the Timeline.");
        closeSelection(); load(rowsLen.current);
      } else {
        setErr(processingErrorMessage(e, "Failed to load item detail"));
      }
    }
  };
  // The unread rail is the PIPE, drawn by whoever passed `top` in - so in task mode a click there
  // has no way to reach this stage, and did nothing at all. `top` may be a function, and this is
  // what it is handed (the owner, 2026-09-04: "task instead of chat not working on the unread tab").
  // False means there is nothing here to open, so the caller can fall back to its chat.
  const openByMid = (mid) => {
    if (!mid) return false;
    const row = (rows || []).find((r) => r.MessageId === mid || rowOwnsMessage(r, mid));
    drill(row || { MessageId: mid }, false, row?.ProcessingItemId ? { kind: "message", id: mid } : null);
    return true;
  };
  // ...and the same door for a canonical item that has no message to open. An assistant idea that
  // became a task is presented on the work rail as the TASK - its post is a container, not a row of
  // its own (processing_all, the duplicate-Assistant regression of 2026-09-04) - so there was no mid
  // to hand `openByMid` and a click in task mode fell through to the chat, while the Timeline showed
  // the same thing perfectly well (the owner, 2026-09-16: "on the timeline assistant ideas still get
  // a right side blurb no? why would on the work tab it would be different?").
  // The canonical detail endpoint describes a task as readily as a message; this asks it for one.
  const openByItem = (itemId, target) => {
    if (!itemId || !processingTarget(null, target)) return false;   // the same kinds the endpoint serves
    const row = (rows || []).find((r) => r.ProcessingItemId === itemId);
    drill(row || { ProcessingItemId: itemId, OpenTarget: target }, false, target);
    return true;
  };
  // what a click on a row does: pull it into the chat (rowMode chat) or open it on the stage
  const openRow = (row) => (chatMode ? onPull(row) : drill(row));
  // #msg=<id> - a card in the chat pointing here. Opened once the rows are here, and again whenever the
  // hash changes; the hash is cleared so a reload does not reopen it. A message no Work row holds opens
  // by itself, as openByMid does - it used to be left to the Timeline, which is gone (2026-10-15). It
  // pins the row in EVERY mode: over the chat, this is how a card says "read it whole".
  const drillRef = useRef(drill); drillRef.current = drill;
  const rowsRef = useRef(null); rowsRef.current = rows;
  const openHash = useCallback(() => {
    const m = /^#msg=(\d+)/.exec(window.location.hash || "");
    const cur = rowsRef.current;
    if (!m || !cur) return;
    const mid = Number(m[1]);
    const row = cur.find((r) => r.MessageId === mid || rowOwnsMessage(r, mid));
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    drillRef.current(row || { MessageId: mid }, false, row?.ProcessingItemId ? { kind: "message", id: mid } : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { openHash(); }, [rows, openHash]);
  useEffect(() => { window.addEventListener("hashchange", openHash); return () => window.removeEventListener("hashchange", openHash); }, [openHash]);
  // A selected message is a LIVE row, not a frozen copy of what it looked like at click time.
  // During ingest it moves from taskless/triaging to routed (often gaining a TaskId). Refresh
  // both the row and the kind of detail endpoint at that boundary, or the open panel circles
  // forever on yesterday's object while the rail beside it already shows the verdict.
  useEffect(() => {
    if (!sel || !rows || recoveryFlight.current) return;
    const fresh = sel.ProcessingItemId
      ? rows.find((r) => r.ProcessingItemId === sel.ProcessingItemId)
      : rows.find((r) => r.MessageId === sel.MessageId);
    if (sel.ProcessingItemId) {
      const candidate = processingRefreshCandidate(sel, rows);
      if (fresh && fresh.ViewRevision === sel.ViewRevision) return;
      const target = processingTarget(sel);
      // Exact-member deep links stay exact. If reconciliation moved that member away, the
      // authoritative detail endpoint returns processing_target_moved instead of substituting.
      const base = target ? { ...candidate, OpenTarget: target } : candidate;
      const requestKey = `${++detailEpoch.current}:${processingSelectionKey(base)}`;
      want.current = requestKey;
      for (const key of cache.current.keys()) if (key.startsWith(`${sel.ProcessingItemId}|`)) cache.current.delete(key);
      fetchDetail(base).then((loaded) => {
        if (want.current !== requestKey) return;
        setSel(loaded.row); setDetail(loaded.detail);
      }).catch((e) => {
        if (want.current !== requestKey) return;
        setErr(processingErrorMessage(e, "Failed to refresh item detail"));
        if (processingErrorCode(e) === "processing_target_moved" || e?.response?.status === 404) closeSelection();
      });
      return;
    }
    if (!fresh) return;
    const finishedTriage = sel.MsgStatus === "triaging" && fresh.MsgStatus !== "triaging";
    const changedTask = fresh.TaskId !== sel.TaskId;
    setSel(fresh);
    if (!finishedTriage && !changedTask) return;
    const requestKey = `${++detailEpoch.current}:${processingSelectionKey(fresh)}`;
    want.current = requestKey;
    cache.current.delete(processingSelectionKey(fresh));
    setDetail(null);
    fetchDetail(fresh).then((loaded) => {
      if (want.current === requestKey) setDetail(loaded.detail);
    });
    // rows is the event: sel is intentionally the previous snapshot used to detect the boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);
  // Transcription replaces the message body in place. Reflect the returned body immediately,
  // and invalidate the minute-long detail cache so reopening cannot resurrect the placeholder.
  const messageBodyChanged = useCallback((mid, body) => {
    for (const key of cache.current.keys()) if (key === `legacy-message:${mid}` || key.includes(`|message:${mid}|`)) cache.current.delete(key);
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
      if (!pinned.current && !panelLock && !(editText ?? "").trim()) {
        clearTimeout(hoverTimer.current); detailEpoch.current += 1; want.current = null; setSel(null);
      }
    }, 400);
  };
  // A verdict being TYPED locks the panel the same way a draft does. It did not, and a sync
  // is when it hurts: rows arrive at the top every two seconds, the list slides under a
  // stationary cursor, hover selects whatever moved into place, and the panel - keyed on the
  // selected message - took the half-written "not our task" note down with it.
  const [panelLock, setPanelLock] = useState(false);
  // Clicking the page ground closes the panel AND collapses the selected row. Whatever was
  // last opened used to stay up until you opened something else - there was no way to just
  // put it down. Rows, the panel, the dock and any popover/dialog are exempt (they handle
  // their own clicks); a draft or verdict mid-edit holds the panel like it holds against hover.
  useEffect(() => {
    if (!sel) return undefined;
    const h = (e) => {
      if (e.target.closest?.("[data-tq-keep], .MuiPopover-root, .MuiModal-root, #tqTopNav")) return;
      if (panelLock || (editText ?? "").trim()) return;
      clearTimeout(hoverTimer.current); detailEpoch.current += 1; want.current = null;
      setPinned(false); setSel(null);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [sel, panelLock, editText]);

  // Approving IS sending, so a refusal has to land in front of you now - not as a NOT SENT line
  // in the task history that you find tomorrow. The panel stays open when the send failed.
  const decide = async (reviewId, verb, finalText, cc) => {
    const attemptedRow = sel;
    // cc only on the send: rejecting or "no reply needed" copies nobody on nothing
    const { data } = await api.post(`/api/reviews/${reviewId}/decide`,
      { verb, final_text: finalText || null, cc: verb === "approve" ? (cc || []) : null });
    const it = interruptOf(data, reviewId);
    if (it) {
      const saved = captureInterruptedReply(it, attemptedRow, finalText);
      setSavedReplies((previous) => ({ ...previous, [reviewId]: saved }));
      setInterrupt(saved); setCompare(null); load(); onChanged?.(); return;
    }
    if (data?.send_error) { setSendErr(replySendFailure(data)); load(); onChanged?.(); return; }
    setSendErr(""); closeSelection(); setEditText(null); setCompare(null); // stale edits must never block hover
    setSavedReplies((previous) => { const next = { ...previous }; delete next[reviewId]; return next; });
    load(); onChanged?.();
  };

  const reviewInterrupted = async (saved) => {
    if (!saved || recoveryFlight.current) return;
    setInterrupt(null);
    const key = `${++detailEpoch.current}:interrupted:${saved.reviewId}`;
    recoveryFlight.current = key; want.current = key; setRecoveringReply(true);
    clearTimeout(hoverTimer.current);
    try {
      const target = interruptedReplyTarget(saved, rowsRef.current);
      cache.current.delete(processingSelectionKey(target));
      const loaded = await fetchDetail(target);
      if (want.current !== key) return;
      const restored = restoreInterruptedReply(saved, { ...loaded, row: loaded.row || target });
      editOwner.current = restored.owner;
      setPinned(true); setPanelLock(false);
      setSel(restored.row); setDetail(restored.detail); setEditText(restored.yours);
      setCompare(restored.compare); setSendErr("");
    } catch (error) {
      if (want.current === key) setErr(processingErrorMessage(error, "Could not load the updated reply. Your edit is saved."));
    } finally {
      if (recoveryFlight.current === key) { recoveryFlight.current = null; setRecoveringReply(false); }
    }
  };

  // only offer channels that actually have a connection behind them. With no category
  // picked, EVERY connected channel is offered - a hardcoded five-channel list here
  // silently hid telegram/whatsapp/jira/... sources from the picker as connectors grew
  const availableChannels = [...new Set([...Object.keys(srcByChannel), ...(rows || []).map((r) => r.Channel)])];
  const pickerChannels = availablePickerChannels(cat, availableChannels);

  const today = new Date().toLocaleDateString("sv-SE");
  const todays = (unreadInventory?.canonical
    ? (unreadInventory.items || []).map(i => ({ SentAt: i.when, Category: i.category, MsgStatus: i.status }))
    : (rows || [])).filter((r) => localDay(r.SentAt) === today);
  // meetings are rows too. Counting only messages meant the rail showed three lines under a
  // heading that said two - the invite was on screen and in no total.
  const todayMeetings = splitTimelineMeetings(calEvents, Date.now(), tsMs).started.filter((e) => localDay(e.start) === today).length;
  const stats = [{ label: "in today", n: todays.length + (canonicalUnread ? 0 : todayMeetings) }, ...[
    { label: "auto", n: todays.filter((r) => r.ReviewStatus === "auto").length },
    { label: "info", n: todays.filter((r) => r.Category === "info").length },
    { label: "promo", n: todays.filter((r) => r.Category === "promo").length },
    { label: "ignored", n: todays.filter((r) => r.MsgStatus === "ignored").length },
  ].filter((s) => s.n > 0)];

  return (
    // THE RAIL AND THE STAGE. The Timeline used to be the page - the window scrolled it, its
    // filters floated over the whole width, and the task sat in a sticky column beside it. But
    // the list is not the subject of this screen: the task is. So the list becomes a rail with
    // its own header and its own scrollbar, and the rest of the window belongs to whatever is
    // open. Both columns are full height and neither one scrolls the page.
    <Box sx={{ display: "grid", columnGap: 1.75, alignItems: "stretch", width: "100%",
      height: `calc(100vh - ${navH}px - 22px)`, minHeight: 420,
      // THE RAIL IS 25% OF THE WINDOW, NOT A NUMBER OF PIXELS. 470px was a third of a laptop and
      // a quarter of a desktop monitor - the same rail reading as two different shapes depending
      // on where you opened it. 25vw is the quarter the owner reads on his own desktop, held on
      // every screen (2026-09-22: "so do 25 percent if that's my size").
      // The canvas redesign (2d1f48a7, 2026-09-29) narrowed it to the sidebar's 340px at 1440, 320px at
      // the floor: the row gives the subject that room by carrying nothing else that can be read on the
      // card - no ref, a lane's mark only. A ref back on the row cut every subject at a laptop to ~14
      // characters (the walk click-through, 2026-10-17), so a narrower floor means a leaner row, not a wider rail.
      // Everything else goes to the stage, which holds a whole message, the agent's work and the draft.
      gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, clamp(320px, 23.6vw, 380px)) minmax(0, 1fr)" },
      mt: { xs: -1.5, md: -2.25 }, pt: { xs: 1.5, md: 2 } }}>
      <ApprovalInterrupt it={interrupt} onResolve={(choice) => {
        if (choice === "review") reviewInterrupted(interrupt);
        else setInterrupt(null);  // The independent saved-reply entry remains available after Cancel.
      }} />

      {/* ── the rail ────────────────────────────────────────────────────────────── */}
      <Box data-tq-keep onMouseEnter={disarmClose} onMouseLeave={armClose}
        sx={{ display: railShown ? "flex" : "none", flexDirection: "column", minHeight: 0, overflow: "hidden", position: "relative",
          bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>

        {/* the header. Frozen by construction now rather than by position:sticky - it is a
            flex sibling of the scroller, so nothing can slide over it and nothing has to be
            measured to keep it out of the way. */}
        {/* THE SIDEBAR'S BUTTONS (the canvas redesign, 2026-09-29): New, then the parts of the app you browse, one line
            each. They stay put - only the rows under them scroll. */}
        <Box data-tq-sidenav="" sx={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "1px", px: 1, pt: 1, pb: 0.75,
          borderBottom: `1px solid ${BORDER}` }}>
          {SIDE_NAV.map((n) => {
            const Icon = NAV_ICONS[n.key];
            return (
              <Tooltip key={n.key} title={n.hint} placement="right">
                <Box component="button" type="button" data-tq-nav={n.key} aria-current={navOn === n.key ? "page" : undefined}
                  onClick={() => (n.key === "new" && !onGo ? setNewOpen(true) : onGo?.(n.go, n.key))}
                  sx={{ display: "flex", alignItems: "center", gap: 1.25, width: "100%", height: 30, px: 1.25, border: 0,
                    borderRadius: "8px", cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600, textAlign: "left",
                    color: navOn === n.key ? INK : "#4d4a43", bgcolor: navOn === n.key ? "#e4e9ee" : "transparent",
                    "& svg": { fontSize: 16, color: "#6e685f" }, "&:hover": { bgcolor: navOn === n.key ? "#e4e9ee" : PANEL2 } }}>
                  <Icon />{n.label}
                </Box>
              </Tooltip>
            );
          })}
        </Box>
        <Box sx={{ flexShrink: 0, bgcolor: "transparent",
          px: 1.5, pt: 1.1, pb: 0.75, display: "flex", flexDirection: "column", gap: 0.75 }}>
          {Object.values(savedReplies).map((saved) => (
            <Box key={saved.reviewId} data-interrupted-reply={saved.reviewId} sx={{ fontSize: 11, color: DIM }}>
              <Box component="details">
                <Box component="summary">Your unsent edit is saved · {saved.row?.Subject || "Reply"}</Box>
                <Typography variant="caption" sx={{ whiteSpace: "pre-wrap" }}>{saved.yours}</Typography>
              </Box>
              <Button size="small" disabled={recoveringReply} onClick={() => reviewInterrupted(saved)}>Review the update</Button>
            </Box>
          ))}

          {/* A HIT OPENS ON THE ASSISTANT CANVAS, whatever the mode, through the same pull a rail click takes (pull switches the
              stage to chat) - it opened the task-mode panel, titled "undefined in chat" (the owner, 2026-10-14: "searched task
              should show up on assistant canvas regardless not on the task view") */}
          {/* ...and QUIET: a pick is not something the owner said, so no "Tell me about ..." bubble rides in above the task
              (the owner, 2026-10-15: "why does the gray thing show up when clicking on searched task. Just show the task") */}
          <SearchEverything open={searchOpen} onClose={() => setSearchOpen(false)}
            onOpenTask={(tid, h) => { searchPicked(); return onPull ? onPull({ TaskId: tid, Title: h?.title }, { quiet: true }) : onOpenTask?.(tid); }}
            onOpenMessage={(mid, h) => { searchPicked(); return onPull ? (onPull({ MessageId: mid, TaskId: h?.tid, Subject: h?.title }, { quiet: true }), true) : openByMid(mid); }}
            onPickSource={(next) => {
              searchPicked();
              loadRequest.current += 1; detailEpoch.current += 1; want.current = null;
              if (cat) { pendingPick.current = next; setCat(""); } else setPick(next);
            }} />

          {/* THE FILTER TAKES THE ROW. Work | Timeline sat here; with the Timeline gone (the owner, 2026-10-15) the filter
              is the row's one control and says on its face what the rail is narrowed to. */}
          <Box sx={{ display: setupMode ? "none" : "flex", alignItems: "center", minWidth: 0 }}>
            <FilterButton cat={cat} pick={pickerChannels.length ? pick : ""} channels={pickerChannels}
              srcByChannel={srcByChannel} srcQ={srcQ} setSrcQ={setSrcQ}
              onChange={(nextCat, nextPick) => {
                loadRequest.current += 1; detailEpoch.current += 1; want.current = null;
                if (nextCat !== cat) setCat(nextCat);
                if (nextPick !== pick) setPick(nextPick);
              }} />
          </Box>

          {/* ONE line, and it never wraps. It used to wrap whenever the clock ran long - "running the reports
              that were due", "· linkedin failed" - so Sync now dropped to a second line and the whole list
              under it jumped with every sync (the owner, 2026-09-23: "it should stay in same place at all
              times"). The counts keep their size, the clock takes what is left and ellipses, and the button
              has one width whatever its label says, flush right under + New. */}
          <Box sx={{ display: setupMode ? "none" : "flex", alignItems: "center", gap: 1.25, flexWrap: "nowrap", minHeight: 20 }}>
            {/* THE NARROWED SIDEBAR (the owner, 2026-09-29: "make the full time fit ... might have to hide the 8 in today while
                refreshing ... when it's not refreshing it should not have a ..."): at rest, the day's one count and the whole
                time - the other counts ride its tooltip; while a sync runs, no counts, and the line says what it is reading */}
            {rows && !(syncing || bgSync) && stats.slice(0, 1).map((s2) => (
              <Box key={s2.label} title={stats.map((x) => `${x.n} ${x.label}`).join(" · ")}
                sx={{ display: "flex", alignItems: "baseline", gap: 0.4, flexShrink: 0 }}>
                <Typography sx={{ fontWeight: 600, fontSize: 11.5, color: INK }}>{s2.n}</Typography>
                <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{s2.label}</Typography>
              </Box>
            ))}
            {!rows && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>Loading item counts…</Typography>}
            <Typography variant="caption" noWrap sx={{ color: syncing || bgSync ? ACCENT : FAINT, fontSize: 10.5, flex: 1, minWidth: 0, textAlign: "right" }}>
              {syncUnknown ? "Sync status unavailable — rechecking"
                : <NextIn atRef={nextAtRef} render={(nextIn) => syncFace({ busy: syncing || bgSync, what: syncWhat, every, lastAt: lastSync, nextIn, checked: true, started: syncStarted,
                    terse: !(syncing || bgSync) })} />}
            </Typography>
            <Button size="small" variant="text" disabled={!syncUnknown && (syncing || bgSync)} onClick={() => syncNow(false)}
              title={syncing || bgSync ? syncWhat : "read the mailboxes, chats and repos now"}
              startIcon={<SyncIcon data-tq-sync-icon sx={{ fontSize: 12,
                color: syncing || bgSync ? ACCENT : "inherit",
                ...(!syncUnknown && (syncing && !bgSync || bgSync && (!syncPhase || syncPhase === "fetching"))
                  ? { animation: "tqSyncSpin .8s linear infinite" } : {}) }} />}
              sx={{ width: 112, flexShrink: 0, justifyContent: "flex-end", minHeight: { xs: 30, md: 20 }, py: 0, pl: { xs: 1, md: 0.6 }, pr: 0, fontSize: 10.5,
                lineHeight: 1.2, whiteSpace: "nowrap", color: DIM,
                // paint containment keeps the spin's compositor layer inside the button: without it Chrome
                // assumes the rotating icon may overlap everything painted after it, promotes the rail to
                // layers and re-renders every row's text (LCD -> greyscale) as each sync starts and stops -
                // the whole list visibly flickered every 10-30 s with nothing changed (the owner, 2026-09-23)
                contain: "paint",
                "@keyframes tqSyncSpin": { to: { transform: "rotate(360deg)" } },
                "&.Mui-disabled": { color: DIM, opacity: 1 },
                "& .MuiButton-startIcon": { mr: 0.35 }, "&:hover": { bgcolor: PANEL2 } }}>
              {syncUnknown ? "Check status" : syncing || bgSync ? syncPhaseLabel(syncPhase) : "Sync now"}
            </Button>
          </Box>
          {/* a brain that errors on every call used to look like slow triage: rows parked on
              "triaging…" and nothing saying why. The last error stays until it answers again. */}
          {/* ...said the way the owner should hear it (problems.thinking), with the raw cause on hover only - and it stays
              while mail is still held, after the first good answer, saying "I'm catching up" in a quieter colour */}
          {!setupMode && (thinking || triageErr) && (
            <Typography variant="caption" noWrap title={triageErr || thinking} sx={{ color: triageErr ? ALERT_INK : DIM, fontWeight: 600, fontSize: 10.5 }}>
              {thinking || "I'm having trouble thinking for a few minutes. Mail is still coming in and I'm holding all of it."}
            </Typography>
          )}
          {err && (
            <Alert severity="error" variant="outlined" onClose={() => setErr("")}
              action={<Button size="small" color="error" onClick={() => { setErr(""); setRows(null); load(rowsLen.current); }}
                sx={{ fontSize: 11 }}>{bLabel("try_again")}</Button>}
              sx={{ py: 0, borderRadius: 2, bgcolor: PANEL, alignItems: "center",
                "& .MuiAlert-message": { fontSize: 11.5, py: 0.5 }, "& .MuiAlert-action": { pt: 0, alignItems: "center" } }}>
              {err}
            </Alert>
          )}
        </Box>

        {/* ── the scroller ── */}
        <Box ref={railRef} data-tq-rail="true"
          sx={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden",
          // no top padding under the pipe: a sticky heading sticks at the padding edge, and rows showed through above it
          position: "relative", pl: "2px", pr: 1, pt: 0, pb: 3 }}>
          {setupRail}
          {setupRail ? null : <>{typeof top === "function" ? top({ openByMid, openByItem }) : top}</>}
        </Box>
        {bottomFade && more && (
          <Box data-tq-bottom-fade={fade} aria-hidden sx={{
            position: "absolute", left: "1px", right: "1px", bottom: "1px", zIndex: 6,
            height: bottomFade.height, pointerEvents: "none",
            background: `linear-gradient(transparent, ${PANEL} ${bottomFade.solidAt}%)`,
          }} />
        )}
      </Box>

      {/* ── the stage: the task, which is what this screen is actually for ────────── */}
      {/* a flex column so the chat can fill it; the canvas and the event panel size themselves to 100% */}
      <Box data-tq-keep data-tq-timeline-stage onMouseEnter={disarmClose} onMouseLeave={armClose}
        sx={{ minWidth: 0, minHeight: 0, display: stageShown ? "flex" : "none", flexDirection: "column", "& > *": { minHeight: 0 } }}>
        {sel ? (
            bareDetail(sel) ? (
              <CanonicalDetail sel={sel} detail={detail} onOpenTask={onOpenTask}
                onOpenMessage={(mid) => openByMid(mid)}
                onClose={closeSelection} />
            ) : <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText} editOwner={editOwner}
              decide={decide} onOpenTask={onOpenTask} onClose={closeSelection}
              onSkipped={() => { closeSelection(); load(); onChanged?.(); }}
              onRefresh={() => { for (const key of cache.current.keys()) if (key.startsWith(`${sel.ProcessingItemId || `legacy-message:${sel.MessageId}`}|`) || key === `legacy-message:${sel.MessageId}`) cache.current.delete(key); load(); }}
              onMessageChanged={messageBodyChanged}
              sendErr={sendErr} clearSendErr={() => setSendErr("")} onLock={setPanelLock} active={active}
              compare={compare} clearCompare={() => setCompare(null)} />
          ) : visibleStage || (
            // an empty stage is not a broken one. It says what the rail is for and what the
            // one button on it does, which is the only thing a new install has to be told.
            <Box sx={{ height: "100%", border: `1px dashed ${BORDER}`, borderRadius: 2,
              display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
              gap: 1, px: 4, textAlign: "center" }}>
              <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: DIM }}>
                Pick anything on the left
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, maxWidth: 380, lineHeight: 1.6 }}>
                Clicking a row opens it here. You get the message that arrived,
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
        <Drawer anchor="right" open={!!sel} data-tq-keep
          onClose={closeSelection}
          PaperProps={{ sx: { width: "100%", p: 1, bgcolor: BG, borderRadius: 0 } }}>
          {sel ? (
              bareDetail(sel) ? (
                <CanonicalDetail sel={sel} detail={detail} onOpenTask={onOpenTask}
                  onOpenMessage={(mid) => openByMid(mid)}
                  onClose={closeSelection} />
              ) : <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText} editOwner={editOwner}
                decide={decide} onOpenTask={onOpenTask} onClose={closeSelection}
                onSkipped={() => { closeSelection(); load(); onChanged?.(); }}
                onRefresh={() => { for (const key of cache.current.keys()) if (key.startsWith(`${sel.ProcessingItemId || `legacy-message:${sel.MessageId}`}|`) || key === `legacy-message:${sel.MessageId}`) cache.current.delete(key); load(); }}
                onMessageChanged={messageBodyChanged}
                sendErr={sendErr} clearSendErr={() => setSendErr("")} onLock={setPanelLock} active={active}
                compare={compare} clearCompare={() => setCompare(null)} />
            ) : null}
        </Drawer>
      )}

      <NewSheet open={newOpen} onClose={() => setNewOpen(false)} onOpenTask={onOpenTask}
        onDone={() => { load(); onChanged?.(); }} />
    </Box>
  );
}

// Day rail label: "Today · Friday, Aug 14" / "Yesterday · ..." / "Thursday, Aug 13".
// Standalone canonical roots have no message envelope, so the message workflow canvas would
// invent reply/task semantics for them. This stage is deliberately read-only; opening a real
// task or an explicitly linked message remains a named owner action.
const CanonicalDetail = ({ sel, detail, onOpenTask, onOpenMessage, onClose }) => {
  if (!detail) return <Box data-processing-generic-detail sx={{ ...card, p: 2 }}><CircularProgress size={20} /></Box>;
  const target = sel.OpenTarget || {};
  const history = Array.isArray(detail.history) ? detail.history : [];
  const links = Array.isArray(detail.links) ? detail.links : [];
  const actionLinks = links.filter((link) => ["task", "message"].includes(link.kind)
    && !(target.kind === link.kind && String(target.id) === String(link.id)));
  const checklist = Array.isArray(detail.checklist) ? detail.checklist
    : detail.checklist ? String(detail.checklist).split("\n").filter(Boolean) : [];
  return (
    <Box data-processing-generic-detail data-processing-detail-kind={target.kind || ""}
      sx={{ ...card, p: 0, height: "100%", overflow: "auto" }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, p: 1.5, borderBottom: `1px solid ${BORDER}` }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, textTransform: "uppercase" }}>{target.kind || "item"}</Typography>
          <Typography sx={{ color: INK, fontWeight: 600, fontSize: 16 }}>{detail.title || sel.Subject || "Untitled item"}</Typography>
          {(detail.status || sel.MsgStatus) && <Typography variant="caption" sx={{ color: DIM }}>{detail.status || sel.MsgStatus}</Typography>}
        </Box>
        <IconButton aria-label="Close detail" size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      <Box sx={{ p: 1.5 }}>
        {detail.body ? (
          looksMd(detail.body) ? <Md>{detail.body}</Md>
            : <Typography sx={{ whiteSpace: "pre-wrap", color: INK, fontSize: 13, lineHeight: 1.6 }}>{detail.body}</Typography>
        ) : <Typography variant="caption" sx={{ color: FAINT }}>No body was recorded for this item.</Typography>}
        {!!checklist.length && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" sx={{ ...mono, color: FAINT, textTransform: "uppercase" }}>Checklist</Typography>
            {checklist.map((entry, i) => {
              const words = typeof entry === "string" ? entry : entry.text || entry.label || JSON.stringify(entry);
              const done = typeof entry === "object" && !!(entry.done ?? entry.Done ?? entry.checked);
              return <Typography key={i} sx={{ color: done ? FAINT : DIM, fontSize: 12.5, mt: 0.4,
                textDecoration: done ? "line-through" : "none" }}>{done ? "✓" : "○"} {words}</Typography>;
            })}
          </Box>
        )}
        {!!history.length && (
          <Box data-processing-detail-history sx={{ mt: 2 }}>
            <Typography variant="caption" sx={{ ...mono, color: FAINT, textTransform: "uppercase" }}>History</Typography>
            {history.map((entry, i) => (
              <Box key={`${entry.at || ""}-${i}`} sx={{ mt: 0.75 }}>
                <Typography variant="caption" sx={{ color: FAINT }}>{entry.at || ""}{entry.actor ? ` · ${entry.actor}` : ""}</Typography>
                <Typography sx={{ color: DIM, fontSize: 12.5, whiteSpace: "pre-wrap" }}>{entry.text || ""}</Typography>
              </Box>
            ))}
          </Box>
        )}
        {(target.kind === "task" || actionLinks.length > 0) && (
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 2 }}>
            {target.kind === "task" && <Button size="small" variant="contained" disableElevation
              onClick={() => onOpenTask?.(target.id)}>Open {ref(target.id)}</Button>}
            {actionLinks.map((link, i) => (
              <Button key={`${link.kind}:${link.id}:${i}`} size="small" variant="outlined"
                onClick={() => link.kind === "task" ? onOpenTask?.(link.id) : onOpenMessage?.(link.id)}>
                {link.label || (link.kind === "task" ? `Open ${ref(link.id)}` : "Open message")}
              </Button>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
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
      : r.Decision === "create" ? "Routed — new task created"
      // the automatic tries stopped on it, so it went on your list (ingest.give_up)
      : r.Decision === "held" ? "Put on your list to be safe" : `Routed — ${r.Decision}`,
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
        fontSize: 8.5, fontWeight: 600, letterSpacing: 0.7, lineHeight: 1.5 }}>MEMORY</Box>}
  </Button>
);

const TrayGroupLabel = ({ children, note }) => (
  <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, mb: 0.7 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.35, fontSize: 9.5,
      fontWeight: 600, lineHeight: 1 }}>{children}</Typography>
    {note && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5, lineHeight: 1 }}>{note}</Typography>}
  </Box>
);

const PanelLabel = ({ children }) => (
  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.8, fontSize: 10, fontWeight: 600,
    display: "block", mt: 1.75, mb: 0.25 }}>
    {children}
  </Typography>
);

// One quiet progress rail. Detail belongs in the four tabs, not repeated in a stack of cards.
// The whole stop is clickable so the summary remains a fast way into any stage.
// `children` turns a step from a signpost into the thing itself - which the Reply step needs and
// Triage and Agent deliberately do not. Those two are whole workspaces (five roads and a verdict;
// a live terminal, a diff, a report), and flattening them onto this list would bury the one line
// that matters under two screens that do not. Reply is the opposite: a box and two buttons, and
// the only thing on this panel the owner ACTS on, so travelling to it was travelling for nothing.
//
// A step with children cannot be a <button>: a button may not contain a textbox or another
// button. So it becomes a row whose HEADER is the button and whose body is yours.
const StoryTimelineStep = ({ title, status, summary, bullets, lines = 2, onOpen, first, last, state = "idle", children }) => {
  const dot = state === "current" ? "#c7a258" : state === "done" ? "#718f74" : "#cfc8bc";
  const rail = (
    <Box sx={{ alignSelf: "stretch", position: "relative" }}>
      <Box sx={{ position: "absolute", left: 10.5, top: first ? 22 : 0, bottom: last ? "auto" : 0,
        height: last ? 8 : "auto", width: "1px", bgcolor: "#d8d2c8" }} />
      <Box sx={{ position: "absolute", zIndex: 1, top: 22, left: 6.5, transform: "translateY(-50%)",
        width: 9, height: 9, borderRadius: "50%", bgcolor: dot, border: `2px solid ${PANEL}`,
        boxShadow: `0 0 0 1px ${dot}` }} />
    </Box>
  );
  const head = (
    <Box component="button" type="button" onClick={onOpen} aria-label={`Open ${title} details`}
      sx={{ appearance: "none", border: 0, bgcolor: "transparent", p: 0, width: "100%", minWidth: 0,
        display: "grid", gridTemplateColumns: "minmax(0, 1fr) 18px", alignItems: "center",
        textAlign: "left", cursor: "pointer", font: "inherit", color: "inherit", borderRadius: 1,
        "&:hover .tq-story-title": { color: ACCENT },
        "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } }}>
      <Box sx={{ minWidth: 0, py: 0.65, pr: 1 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, mb: 0.15 }}>
          <Typography className="tq-story-title" sx={{ color: INK, fontWeight: 600, fontSize: 11.5,
            transition: "color .15s", whiteSpace: "nowrap" }}>{title}</Typography>
          <Typography sx={{ ...mono, color: state === "idle" ? FAINT : dot, fontSize: 9.5,
            fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{status}</Typography>
        </Box>
        {/* two lines is right for a step that only has a verdict to report. The MESSAGE step is the
            one you actually read - at two lines it showed a sentence and a half of a mail and stopped,
            with the rest of the pane empty below it (the owner, 2026-09-15: "just make the message
            section bigger no?"), so it asks for room and the others do not. */}
        {summary && <Typography sx={{ color: DIM, fontSize: 11.5, lineHeight: 1.45, overflow: "hidden",
          whiteSpace: "pre-wrap", display: "-webkit-box", WebkitLineClamp: lines, WebkitBoxOrient: "vertical" }}>{summary}</Typography>}
        {/* what the body listed, still a list. A few lines only - the step is a summary, and the
            whole of it is one click away on the tab this row opens. */}
        {!!bullets?.length && (
          <Box sx={{ mt: 0.3 }}>
            {bullets.slice(0, 6).map((line, i) => (
              <Box key={i} sx={{ display: "flex", gap: 0.6, color: DIM, fontSize: 11, lineHeight: 1.45 }}>
                <Box component="span" sx={{ color: FAINT, flexShrink: 0 }}>·</Box>
                <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line}</Box>
              </Box>
            ))}
            {bullets.length > 6 && (
              <Box sx={{ color: FAINT, fontSize: 10.5, mt: 0.15 }}>+{bullets.length - 6} more</Box>
            )}
          </Box>
        )}
      </Box>
      <Box sx={{ display: "grid", placeItems: "center" }}>
        <ChevronRightIcon sx={{ color: FAINT, fontSize: 13 }} />
      </Box>
    </Box>
  );
  if (children) return (
    <Box sx={{ display: "grid", gridTemplateColumns: "22px minmax(0, 1fr)", alignItems: "stretch", minWidth: 0 }}>
      {rail}
      <Box sx={{ minWidth: 0, pr: 0.5, pb: 1 }}>
        {head}
        <Box sx={{ mt: 0.25 }}>{children}</Box>
      </Box>
    </Box>
  );
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
          <Typography className="tq-story-title" sx={{ color: INK, fontWeight: 600, fontSize: 11.5,
            transition: "color .15s", whiteSpace: "nowrap" }}>{title}</Typography>
          <Typography sx={{ ...mono, color: state === "idle" ? FAINT : dot, fontSize: 9.5,
            fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{status}</Typography>
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
const ReviewCanvas = ({ sel, detail, editText, setEditText, editOwner, decide, onOpenTask, onClose, onSkipped, onRefresh,
                        onMessageChanged, sendErr, clearSendErr, onLock, active = true, compare = null, clearCompare = null }) => {
  // one click turns a flood sender (100s of automated mails) into a skip policy - their
  // mail is deduped but never shows on the timeline again, and their HISTORY goes with it
  const [skipped, setSkipped] = useState(null);
  const [skipConfirm, setSkipConfirm] = useState(false);
  // can a reply leave on this row's channel: asked of capabilities.js, the one answer - the row's own CanSend until it is in
  const sendable = channelCanSend(useCapabilities(), sel.Channel, sel.CanSend);
  const [tab, setTab] = useState("summary");      // overview first; the deeper stages stay one click away
  const [filing, setFiling] = useState("");       // "once" teaches nothing; "learn" writes one Memory verdict
  const [fileErr, setFileErr] = useState("");
  // a reply opened from THIS panel on a message with no pending review
  const [opened, setOpened] = useState(null);
  const [opening, setOpening] = useState(false);
  const openReply = async () => {
    setOpening(true);
    try {
      // Open the editor first. Writing by hand is a first-class path; AI generation is the
      // adjacent button, not a gate the owner must pass before a text box exists.
      const { data } = await api.post(`/api/messages/${sel.MessageId}/reply`, { draft: false });
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
  const rep = [...(detail?.comments || [])].reverse().find((c) => /^(?:AGENT|CODER) REPORT/.test(String(c.Body || "").trimStart()));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  // an ACTION is a proposal, not a reply - it has its own card and must never fill this tab
  const livePending = (detail?.reviews || []).find((r) => r.Status === "pending" && r.Kind !== "action");
  const pending = detail ? !!livePending : !!(sel.ReviewId && sel.ReviewStatus === "pending");
  const pendingId = livePending?.ReviewId || sel.ReviewId;
  const draftOwner = `${sel.ProcessingItemId || `message:${sel.MessageId}`}|review:${pendingId || opened?.reviewId || ""}`;
  useEffect(() => {
    if (editText == null || !editOwner?.current || editOwner.current === draftOwner) return;
    setEditText(null);
  }, [draftOwner, editText, editOwner, setEditText]);
  const writeEditText = (value) => { if (editOwner) editOwner.current = draftOwner; setEditText(value); };
  // is somebody already on this? a live pty session or a running headless run both count,
  // and a session gone quiet is a question waiting for an answer, not work in progress
  const ses = detail?.session;
  const run = (detail?.runs || []).find((r) => r.Status === "running");
  const onIt = ses ? { agent: ses.agent || ses.label, waiting: ses.waiting ?? (ses.idle >= IDLE_WAITING) }
    : run ? { agent: run.AgentName, waiting: false } : null;
  // This small text summary polls calmly. Fetching it for every PTY frame starved the real terminal.
  const [liveRow, setLiveRow] = useState(null);
  useEffect(() => {
    if (!active || !onIt || !sel?.TaskId) { setLiveRow(null); return; }
    let alive = true;
    const poll = async () => { try { const { data } = await api.get("/api/runs/live", { params: { lines: 120 } }); if (alive) setLiveRow((data.data || []).find((r) => r.TaskId === sel.TaskId) || null); } catch { /* keep the last */ } };
    poll(); const id = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, !!onIt, sel?.TaskId]);
  const phase = detailPhase(sel, detail);
  const loading = phase === "loading";
  const triaging = phase === "triaging";
  // triage's OWN verdict, read off the route line it already wrote. reply_only and fyi both
  // mean "no work to do here" - so a coding agent is not the answer, and offering it first
  // made the panel argue with the reason printed at the top of the very same panel.
  const codeless = ["reply_only", "fyi"].includes(routeIntent(sel.RouteReason)) && !sel.TaskId;
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
  // A reply written in Outlook/Teams/iMessage is a context/outbound message, not a Taskuary
  // review. The thread is still proof that this was answered; calling it "not drafted" beside
  // the visible reply made the summary contradict the Message tab.
  const threadReply = [...(detail?.messages || [])].reverse().find((m) =>
    isOwnMessage(m) && tsMs(m.SentAt) > tsMs(sel.SentAt));
  const outsideReply = String(threadReply?.BodyText || "").trim();
  const answeredOutside = !replied && (!!sel.AnsweredAt || !!threadReply);
  const answered = replied || answeredOutside;
  const replyOpen = pending || !!opened;
  const chatTask = !!sel.TaskId && ["general", "research", "marketing", "triage", "assistant"]
    .includes(String(detail?.task?.Kind || sel.TaskKind || "").toLowerCase());
  const assistantDiscussion = (detail?.comments || []).filter((c) =>
    ["concierge_user", "concierge_assistant", "assistant_user", "assistant_agent"].includes(c.ActorType));
  const tabs = [
    { key: "summary", label: "Summary" },
    { key: "msg", label: "Message" },
    { key: "why", label: "Triage" },
    { key: "agent", label: "Agent", mark: onIt ? "live" : chatTask ? "chat" : rep ? "done" : "" },
    ...(assistantDiscussion.length ? [{ key: "discussion", label: "Assistant discussion", mark: assistantDiscussion.length }] : []),
    // no Reply tab: everything it held - the draft, its verdicts, what was sent, what you answered
    // elsewhere - is on the Summary timeline, in the step that already told you about it. A tab
    // whose whole content fits under the line describing it was a trip for nothing.
  ];
  // The drawer just read the live session list; the row's chip is whatever the last feed poll
  // saw. When they disagree the drawer is the newer fact, so ask the list to refresh rather than
  // leaving "agent working" on a task nothing is working. Once per message: the refreshed row
  // clears Working, so this cannot chase itself.
  const correctedRef = useRef(null);
  useEffect(() => {
    if (!detail || !sel?.MessageId) return;
    const staleAgent = sel.Working && detail.session_available !== false && !detail.session;
    const staleReply = (sel.ReviewStatus === "pending") !== !!livePending;
    if (!staleAgent && !staleReply) return;
    if (correctedRef.current === sel.MessageId) return;
    correctedRef.current = sel.MessageId;
    onRefresh?.();
  }, [detail, sel?.MessageId, sel?.Working, sel?.ReviewStatus, livePending, onRefresh]);
  const replyDraft = pending
    ? (livePending?.DraftText || pendingDraft(detail || { runs: [] }, sel))
    : (opened?.draft || "");
  // The reply's ACTIONS, in one place: the Reply tab shows them, and the Summary timeline inlines
  // them under its Reply step. Written once so the two cannot drift into disagreeing about what
  // you may do with a draft.
  const replyControls = (
    <>
      {/* YOU answered it, somewhere else. Not the same fact as "Sent reply", which means Taskuary
          drafted it and something here sent it - and the panel said that about both, so a message
          handled in Teams read as one we had answered for you. The reply itself is on the Message
          tab, in the thread. */}
      {answeredOutside && !pending && (
        <Box sx={{ mb: 1.25 }}>
          <Typography variant="caption" sx={{ color: DIM, display: "block" }}>
            You answered this in {sel.Channel === "email" ? "your mailbox" : sel.Channel} · {fmtDateTime(sel.AnsweredAt || threadReply?.SentAt)}
            {" "}— nothing here sent it, and nothing is waiting on you.
          </Typography>
          {/* your own words, quoted under the line that says where you said them. This used to be
              pushed right like a chat bubble, which on a left-aligned summary left a bald gutter
              beside it and read as a stray (the owner, 2026-09-07). It fills the column now, in the
              tint the chat already gives your own messages, and the top-left corner is squared off
              so it hangs from the line above instead of floating. */}
          {outsideReply && (
            <Box sx={{ mt: 0.65, bgcolor: "#f1eee8", border: "1px solid #dfdbd3",
              borderRadius: "4px 14px 14px 14px",
              px: 1.25, py: 0.9, color: INK, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
              {cleanText(outsideReply)}
            </Box>
          )}
        </Box>
      )}
      {replied && (
        <Box sx={{ mb: 1.25 }}>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.65 }}>
            Sent to {sel.FromName || sel.FromEmail || "the conversation"}
          </Typography>
          <Box sx={{ bgcolor: "#fcfaf7", border: `1px solid ${BORDER}`, borderRadius: 1.5,
            px: 1.25, py: 1, color: INK, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
            {sentReply}
          </Box>
        </Box>
      )}
      {pending && (
        <ReviewActions key={`${sel.MessageId}:${pendingId}`} reviewId={pendingId} draft={replyDraft} review={livePending}
          editText={editText} setEditText={writeEditText} decide={decide}
          sendErr={sendErr} clearSendErr={clearSendErr} canSend={sendable}
          onChanged={onRefresh} channel={sel.Channel} compare={compare} clearCompare={clearCompare} />
      )}
      {!pending && opened && (
        <ReviewActions key={`${sel.MessageId}:${opened.reviewId}`} reviewId={opened.reviewId} draft={replyDraft}
          review={(detail?.reviews || []).find((r) => r.ReviewId === opened.reviewId)}
          editText={editText} setEditText={writeEditText} decide={decide}
          sendErr={sendErr} clearSendErr={clearSendErr} canSend={sendable}
          onChanged={onRefresh} channel={sel.Channel} compare={compare} clearCompare={clearCompare} />
      )}
      {!answered && !replyOpen && (["report", "assistant"].includes(sel.Channel) ? (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
          Nobody sent this, so there is nobody to answer. Findings stay with the Timeline item.
        </Typography>
      ) : (
        <ChoiceRow tint={PANEL2} busy={opening} onClick={openReply}
          icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: ACCENT }} />}
          label="Write a reply" first
          hint="the AI drafts it from the thread and the agent result; approving sends it" />
      ))}
    </>
  );
  // the road, in words - the why sentence is one tab over, for when it is asked for
  const roadMeta = ROADS.find((r) => r.key === roadOf(sel));
  const failedTriage = triageFailed(sel);
  // ONE verdict behind the chip and the step. Assembled from roadOf alone, this said "No
  // classification - choose what should happen below" about a message the owner's own rule had
  // already turned away (timelineState.triageSummary).
  const triage = triageSummary(sel);
  const roadLine = failedTriage && triage.choose
    ? "Triage could not classify it, so no task was created. Choose what should happen below."
    : triage.line;
  const reportText = String(rep?.Body || "").replace(/^((?:AGENT|CODER) REPORT|HANDOVER NOTE)\s*/i, "").trim();
  const reportResult = ((/(?:^|\n)Summary:[ \t]*([^\n]+)/im.exec(reportText) ||
    /(?:^|\n)Result:[ \t]*([^\n]+)/im.exec(reportText) || [])[1] || cleanText(reportText)).trim();
  // a generated body carries its own structure (a lead, then a list); flattening the whole thing
  // into one clamp turned a report's error summary into a wall of run-on text (2026-09-15)
  const messageBody = structured(cleanText(detail?.body || sel.Preview || sel.Subject || "No message preview available."));
  const triageStatus = triage.status;
  // 255 is Graph's bodyPreview cap, so a body of exactly that length on a rule-ignored mail is the
  // preview itself - the body was never fetched. A short ignored mail is whole and says nothing.
  const envelopeOnly = verdictOf(sel) === "ignored"
    && String((detail?.messages || []).find((m) => m.MessageId === sel.MessageId)?.BodyText || "").length === 255;

  const [mined, setMined] = useState(null);          // "Mine to do" made a task, and its ref
  const [notCoding, setNotCoding] = useState(false); // "Mine, not agent" landed - the button says so
  const [mineAsk, setMineAsk] = useState(false);     // ...and where the work actually lives, asked first
  const [mineWhere, setMineWhere] = useState("");
  const [mining, setMining] = useState(false);
  const takeItMine = async () => {
    if (mining) return;
    setMining(true); setRouteErr("");
    try {
      await api.post(`/api/tasks/${sel.TaskId}/not-coding`, { learn: true, belongs_to: mineWhere.trim() || null });
      setNotCoding(true); setMineAsk(false); setMineWhere(""); onRefresh?.();
    } catch (e) { setRouteErr(e?.response?.data?.detail || "that did not work"); }
    finally { setMining(false); }
  };
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
            <Typography sx={{ color: INK, fontWeight: 600, fontSize: 15, lineHeight: 1.3, letterSpacing: "-.25px" }} noWrap>
              {sel.Subject || `${sel.FromName || sel.FromEmail} in ${sel.SourceName || "chat"}`}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
              {sel.FromName || sel.FromEmail}{sel.SourceName && String(sel.SourceName).toLowerCase() !== String(sel.FromName || "").toLowerCase() ? ` · ${sel.SourceName}` : ""} · {fmtDateTime(sel.SentAt)}
            </Typography>
          </Box>
          <RefChip taskId={sel.TaskId} onClick={() => onOpenTask(sel.TaskId)} />
          <StateMark row={sel} state={st} size="md" />
          <IconButton aria-label="Close item" size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
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
                cursor: "pointer", color: tab === item.key ? INK : FAINT, fontSize: 12.5, fontWeight: 600,
                whiteSpace: "nowrap", borderBottom: `2px solid ${tab === item.key ? ACCENT : "transparent"}`,
                transition: "color .15s", "&:hover": { color: INK } }}>
              {item.label}
              {item.mark && (
                <Box component="span" sx={{ ...mono, px: 0.55, py: 0.12, borderRadius: 2, bgcolor: PANEL2,
                  color: item.key === "agent" && onIt ? ACCENT2 : FAINT, fontSize: 8.5, fontWeight: 600 }}>
                  {item.mark}
                </Box>
              )}
            </Box>
          ))}
        </Box>

        <Box sx={{ px: 2, py: 1.1, overflowY: "auto", flex: 1, minHeight: 0 }}>
          {loading ? (
            <Box role="status" aria-live="polite" sx={{ minHeight: 180, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 1 }}>
              <CircularProgress size={22} />
              <Typography variant="caption" sx={{ color: DIM }}>
                {sel.MsgStatus === "triaging" ? "Loading this message while triage works…" : "Loading message…"}
              </Typography>
            </Box>
          ) : triaging ? (
            <Box role="status" aria-live="polite" sx={{ py: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 1,
                bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, mb: 1.25 }}>
                <CircularProgress size={18} thickness={5} />
                <Box>
                  <Typography sx={{ color: INK, fontWeight: 600, fontSize: 12.5 }}>Triaging this message…</Typography>
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    It is safely on the Timeline. The task, agent, and reply steps will appear when the decision lands.
                  </Typography>
                </Box>
              </Box>
              <MessageBlock messages={detail?.messages} focusId={sel.MessageId} fallback={detail?.body || sel.Preview} threadTotal={detail?.thread_total} askIds={detail?.ask_ids} />
            </Box>
          ) : (
            <>
              {tab === "summary" && (
                <Box aria-label="Workflow summary" sx={{ width: "100%",
                  px: 0.75, pt: 0.45, pb: 0.75 }}>
                  <StoryTimelineStep title="Message" first state="done"
                    status={(detail?.messages || []).length > 1 ? `${detail.messages.length} messages` : "received"}
                    summary={messageBody.lead} bullets={messageBody.bullets} lines={10}
                    onOpen={() => setTab("msg")} />
                  <StoryTimelineStep title="Triage" status={triageStatus} summary={roadLine}
                    state={failedTriage ? "current" : triageStatus !== "not routed" ? "done" : "idle"}
                    onOpen={() => setTab("why")} />
                  <StoryTimelineStep title="Agent"
                    status={onIt ? (onIt.waiting ? AGENT.waiting : AGENT.working) : chatTask ? "assistant chat" : rep ? AGENT.saved : AGENT.idle}
                    summary={onIt ? (onIt.waiting ? `${onIt.agent} needs your answer.` : `${onIt.agent} is working in the live terminal.`)
                      : chatTask ? "The assistant conversation is available here."
                      : rep ? (reportResult || "The agent finished; open for the result.")
                      : held ? "Held until you release it."
                      : codeless ? "Triage decided an agent was not needed."
                      : "No agent work has started."}
                    state={onIt ? "current" : (chatTask || rep || diffRun) ? "done" : "idle"}
                    onOpen={() => setTab("agent")} />
                  {/* the draft is IN the step now, so repeating it as a two-line summary above the
                      box it is already in was saying the same words twice */}
                  <StoryTimelineStep title="Reply" last
                    status={pending ? "waiting on you" : replied ? "sent from Taskuary" : answeredOutside ? "you replied" : opened ? "draft open" : "not drafted"}
                    summary={replied ? cleanText(sentReply)
                      : answeredOutside ? (cleanText(outsideReply) || `Answered in ${sel.Channel}.`) : ""}
                    state={replyOpen ? "current" : answered ? "done" : "idle"}>
                    {replyControls}
                  </StoryTimelineStep>
                </Box>
              )}

              {tab === "msg" && (
                <Box>
                  {/* A standing rule that ignores a sender also stops Taskuary paying for the body:
                      the mail keeps Graph's free 255-character preview and no request is made
                      (channels._hydrate). That is a saving, not a truncation - but the tab showed
                      the stub with nothing to explain it and read as a bug (the owner, 2026-09-15:
                      "where is the rest of the email of this one?? seems like you are cutting them
                      off?"). 255 exactly is the cap, and so the signal that there IS more. */}
                  {envelopeOnly && (
                    <Box sx={{ mb: 1, px: 1.25, py: 0.9, borderRadius: 1.5, bgcolor: PANEL2,
                      border: `1px solid ${BORDER}`, fontSize: 12, color: DIM, lineHeight: 1.6 }}>
                      Only the first 255 characters were downloaded. A standing rule ignores this sender,
                      so Taskuary never fetched the rest of the body.
                      {sel.SourceLink && <> <Box component="a" href={sel.SourceLink} target="_blank" rel="noreferrer"
                        sx={{ color: ACCENT }}>Open it in Outlook</Box> for the whole message.</>}
                    </Box>
                  )}
                  {sel.Channel === "assistant" && <AssistantPost sel={sel} onOpenTask={onOpenTask} onChanged={() => onRefresh?.()} />}
                  {sel.Channel === "report" && /morning digest/i.test(`${sel.SourceName || ""} ${sel.Subject || ""}`) && <TodayMeetingsStrip />}
                  {sel.Channel !== "assistant" && (
                    <MessageBlock key={sel.MessageId} messages={detail?.messages} focusId={sel.MessageId} fallback={detail?.body || sel.Preview} threadTotal={detail?.thread_total} askIds={detail?.ask_ids} />
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
                        <AgentReport body={rep.Body} />
                      </Box>
                      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                        Finished by {rep.Actor || "the coding agent"}{rep.CreatedAt ? ` · ${fmtDateTime(rep.CreatedAt)}` : ""}
                      </Typography>
                    </>
                  )}
                  {diffRun && <Box sx={{ mt: 1 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                  {sel.TaskId && (rep || diffRun) && <Box sx={{ mt: 1 }}><ProofCard taskId={sel.TaskId} onOpenTask={onOpenTask} /></Box>}
                  {/* a session RAN and is gone: say that, rather than that none ever started */}
                  {!chatTask && !onIt && !rep && !diffRun && detail?.session_available === false && (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
                      Live session status is unavailable. Open the task page for its persisted history.
                    </Typography>
                  )}
                  {!chatTask && !onIt && !rep && !diffRun && detail?.session_available !== false && detail?.transcript && (
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
                  {!chatTask && !onIt && !rep && !diffRun && detail?.session_available !== false && !detail?.transcript && (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.7 }}>
                      {held ? "Nothing is working this — it is held until you release it."
                        : codeless ? "No agent was sent: triage read this as something a reply settles."
                        : sel.TaskId ? "No agent has started on this yet." : "No agent work was created for this item."}
                    </Typography>
                  )}
                </Box>
              )}

              {tab === "discussion" && (
                <Box aria-label="Assistant discussion" sx={{ display: "flex", flexDirection: "column", gap: 0.9, py: 0.5 }}>
                  {assistantDiscussion.map((c) => {
                    const owner = ["concierge_user", "assistant_user"].includes(c.ActorType);
                    const body = cleanText(c.Body || "").replace(/\nOPTIONS:\s*.*$/s, "").trim();
                    return (
                      <Box key={c.CommentId} sx={{ alignSelf: owner ? "flex-end" : "flex-start", maxWidth: "88%" }}>
                        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.25,
                          textAlign: owner ? "right" : "left", fontSize: 10 }}>
                          {owner ? "You" : "Taskuary"}{c.CreatedAt ? ` · ${fmtDateTime(c.CreatedAt)}` : ""}
                        </Typography>
                        <Box sx={{ bgcolor: owner ? "#e9e3d8" : "#f8f6f2", border: `1px solid ${BORDER}`,
                          borderRadius: owner ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                          px: 1.2, py: 0.85, color: INK, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                          {body}
                        </Box>
                      </Box>
                    );
                  })}
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
                <TrayBtn tone={sel.MsgStatus === "filed" ? "teach" : "plain"}
                  teaches={sel.MsgStatus === "filed"} disabled={!!mined} icon={<AssignmentIndIcon sx={{ fontSize: 15 }} />}
                  title={sel.MsgStatus === "filed"
                    ? "adds a task with your name on it and teaches triage that filing it was a miss"
                    : "adds a task with your name on it; no coding agent is dispatched"}
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
                  }}>{closed || bLabel("close")}</TrayBtn>
              )}
              {onIt && sel.MessageId && (
                <TrayBtn disabled={handed} onClick={handToAgent} icon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                  title="their message is typed into the live session, as if you relayed it">
                  {handed ? "Typed into the session" : `Tell ${onIt.agent} this`}</TrayBtn>
              )}
              {onIt && sel.TaskId && <TellAgentButton taskId={sel.TaskId} />}
              {/* fyi/reply rows can still be sent to an agent by hand, as the chat cards allow (PW-211); triage's
                  reading stays printed above as the reason it was not sent automatically */}
              {!onIt && !held && (
                <SendToAgent messageId={sel.MessageId} subject={sel.Subject} taskKind={sel.TaskKind}
                  onOpenTask={onOpenTask} />
              )}
              {!onIt && <TalkItThrough messageId={sel.MessageId} onOpenTask={onOpenTask}
                teaches={!sel.TaskId && sel.MsgStatus === "filed"} />}
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
              {/* Saying it is yours only says where the work does NOT go. The one thing triage
                  cannot work out for itself is where it DOES - it only knows the repositories it
                  has code for, so a job that lives in ADP had no answer it could give. Asked here
                  inline rather than in a modal: this is a quiet drawer, not a decision to dramatise. */}
              {mineAsk && sel.TaskId && (
                <Box sx={{ display: "flex", gap: 0.8, alignItems: "center", flexWrap: "wrap", mb: 0.9 }}>
                  <TextField size="small" autoFocus value={mineWhere} onChange={(e) => setMineWhere(e.target.value)}
                    placeholder="Where does this really live? e.g. ADP (optional)"
                    onKeyDown={(e) => { if (e.key === "Enter") takeItMine(); }}
                    sx={{ flex: 1, minWidth: 210, "& .MuiInputBase-input": { fontSize: 12.5, py: 0.7 } }} />
                  <TrayBtn tone="teach" teaches disabled={mining} onClick={takeItMine}
                    icon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}>
                    {mining ? "Teaching triage…" : bLabel("mine")}</TrayBtn>
                  <TrayBtn tone="quiet" disabled={mining} onClick={() => { setMineAsk(false); setMineWhere(""); }}>Cancel</TrayBtn>
                </Box>
              )}
              <Box sx={{ display: "flex", gap: 0.8, flexWrap: "wrap", alignItems: "center" }}>
                {sel.TaskId && (
                  <TrayBtn tone="teach" teaches disabled={notCoding} icon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}
                    title="make this your task instead of agent work, and remember that choice"
                    onClick={() => { setRouteErr(""); setMineAsk(true); }}>
                    {notCoding ? "Now yours" : "Mine, not agent"}</TrayBtn>
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
                      + `It is still received and kept; it just never shows here again. The rule lives under ${placeName("rules")}, where it can be switched off.`}
                    onConfirm={skipSender} />
                </Box>
              )}
            </Box>
            <VoiceNoteRow sel={sel}
              body={voiceNoteBody(sel, (detail?.messages || []).find((m) => m.MessageId === sel.MessageId))}
              onRefresh={onRefresh} onMessageChanged={onMessageChanged} />

            {/* put down at the press like every close (2026-10-01): the drawer goes while it sends, the form kept behind it for a
                send that fails; once it is sent the task is closed and the panel goes too */}
            <Drawer anchor="right" open={handoff === true && !!sel.TaskId} onClose={() => setHandoff(false)} ModalProps={{ keepMounted: !!handoff }}
              PaperProps={{ sx: { width: { xs: "100%", sm: 460 }, p: 2, bgcolor: PANEL } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <ForwardToInboxIcon sx={{ fontSize: 18, color: ACCENT }} />
                <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14.5, flex: 1 }}>Hand this to a person</Typography>
                <IconButton aria-label="Close handoff" size="small" onClick={() => setHandoff(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
              </Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
                {sel.TaskId ? ref(sel.TaskId) : ""} · {sel.Subject}
              </Typography>
              {handoff && sel.TaskId && <Handoff taskId={sel.TaskId} onLeave={() => setHandoff("sending")} onStay={() => setHandoff(true)}
                onSent={() => { setHandoff(false); onSkipped?.(); }} />}
            </Drawer>

            <Drawer anchor="right" open={reshape === true && !!sel.TaskId} onClose={() => setReshape(false)} ModalProps={{ keepMounted: !!reshape }}
              PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <CallSplitIcon sx={{ fontSize: 18, color: ACCENT2 }} />
                <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14.5, flex: 1 }}>Is this one job?</Typography>
                <IconButton aria-label="Close split or merge" size="small" onClick={() => setReshape(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
              </Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
                {sel.TaskId ? ref(sel.TaskId) : ""} · {sel.Subject}
              </Typography>
              {reshape && sel.TaskId && (
                <Reshape taskId={sel.TaskId} taskRef={ref(sel.TaskId)}
                  // folded away, it goes at the press like every close; a fold that fails reopens the drawer with the reason
                  onLeave={(tid) => tid === sel.TaskId && setReshape("merging")} onStay={(tid) => tid === sel.TaskId && setReshape(true)}
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
const TriageSummary = ({ sel, detail }) => {
  const road = roadOf(sel);
  const meta = ROADS.find((r) => r.key === road);
  const failed = triageFailed(sel);
  const why = routeWhy(sel.RouteReason).split(" · ")[0];
  const watch = (detail?.task || {}).Kind === "note";
  return (
    <Box sx={{ bgcolor: "#fcfaf7", border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.2, py: 0.85 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
        <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: INK, flexShrink: 0 }}>
          {meta?.label || (watch ? "your note" : failed ? "needs your choice" : "not routed")}
        </Typography>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>
          {meta?.hint || (failed ? "the AI answer was not a usable verdict" : "")}
        </Typography>
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
const TalkItThrough = ({ messageId, onOpenTask, teaches = false }) => {
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
      <TrayBtn tone={teaches ? "teach" : "plain"} teaches={teaches} disabled={busy} onClick={go}
        icon={<ForumOutlinedIcon sx={{ fontSize: 15 }} />}
        title={teaches
          ? "opens the assistant's chat and teaches triage that filing this was a miss"
          : "opens the assistant's chat on this, with the message as the question"}>
        {busy ? "Opening…" : "Talk it through"}</TrayBtn>
      {err && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </>
  );
};

const TRIAGE_FACT_TONES = {
  intent: { dot: "#6f8a6e", bg: "#f4f7f2", bd: "#d8e1d5" },
  kind: { dot: "#65798b", bg: "#f3f6f8", bd: "#d8e0e6" },
  profile: { dot: "#8a7355", bg: "#f8f5ef", bd: "#e5ddcf" },
  repo: { dot: "#725f88", bg: "#f6f3f8", bd: "#dfd7e5" },
  relation: { dot: "#8a6d69", bg: "#f8f4f3", bd: "#e5d9d7" },
};

const TriageFact = ({ label, value, tone = "intent" }) => {
  if (!value) return null;
  const c = TRIAGE_FACT_TONES[tone] || TRIAGE_FACT_TONES.intent;
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.7, minHeight: 31,
      border: `1px solid ${c.bd}`, borderRadius: 99, bgcolor: c.bg, px: 1.05, py: 0.35 }}>
      <Box aria-hidden sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: c.dot, flexShrink: 0 }} />
      <Typography component="span" sx={{ fontSize: 9, fontWeight: 600, letterSpacing: ".09em",
        textTransform: "uppercase", color: FAINT }}>{label}</Typography>
      <Typography component="span" sx={{ fontSize: 11.5, fontWeight: 600, color: INK }}>{value}</Typography>
    </Box>
  );
};

const TriageVerdictCard = ({ verdict, exact = true }) => {
  if (!verdict) return null;
  const checklist = Array.isArray(verdict.checklist)
    ? verdict.checklist.filter((x) => typeof x === "string" && x.trim()) : [];
  const isFyi = verdict.intent === "fyi";
  const isReply = verdict.intent === "reply_only";
  const destination = kindLabel(verdict.kind) || (isFyi ? "Filed" : isReply ? "Reply review" : "");
  const worker = verdict.profile || (isFyi || isReply ? "No agent" : "");
  const repo = verdict.repository || (verdict.needs_repo_choice ? "Repository choice needed"
    : isFyi || isReply || (verdict.kind && verdict.kind !== "coding") ? "Not applicable"
      : verdict.kind === "coding" ? "No repository recorded" : "");
  const extras = extraTriageFields(verdict);
  const noteCount = Array.isArray(verdict.notes) ? verdict.notes.length : 0;
  return (
    <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fcfaf7", overflow: "hidden" }}>
      <Box sx={{ px: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}`,
        background: "linear-gradient(135deg, #fbfaf6 0%, #f4f6f2 100%)" }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 0.85 }}>
          <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>
            {exact ? "Triage's structured response" : "Saved triage result"}
          </Typography>
          {!exact && <Typography variant="caption" sx={{ fontSize: 9.5, color: FAINT }}>limited saved response · reconstructed</Typography>}
        </Box>
        <Box sx={{ display: "flex", gap: 0.65, flexWrap: "wrap" }}>
          <TriageFact label="Item" value={intentLabel(verdict.intent)} tone="intent" />
          <TriageFact label="Goes to" value={destination} tone="kind" />
          <TriageFact label="Worker" value={worker} tone="profile" />
          <TriageFact label="Playbook" value={verdict.playbook} tone="profile" />
          <TriageFact label="Thread" value={relationshipLabel(verdict.relationship)} tone="relation" />
        </Box>
      </Box>

      <Box sx={{ px: 1.5, py: 1.35, display: "grid", gap: 1.25 }}>
        {(verdict.title || verdict.summary) && (
          <Box>
            <Typography sx={{ ...mono, fontSize: 9.5, color: FAINT, letterSpacing: ".08em", textTransform: "uppercase" }}>
              Work it pulled out
            </Typography>
            {verdict.title && <Typography sx={{ mt: 0.35, fontSize: 14, fontWeight: 600, color: INK, lineHeight: 1.35 }}>
              {verdict.title}
            </Typography>}
            {verdict.summary && <Typography sx={{ mt: 0.35, fontSize: 12.25, color: DIM, lineHeight: 1.6 }}>
              {verdict.summary}
            </Typography>}
          </Box>
        )}

        {(repo || verdict.repo_reason) && (
          <Box sx={{ border: `1px solid ${TRIAGE_FACT_TONES.repo.bd}`, borderRadius: 1.5,
            bgcolor: TRIAGE_FACT_TONES.repo.bg, px: 1.15, py: 0.9 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
              <Box aria-hidden sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: TRIAGE_FACT_TONES.repo.dot }} />
              <Typography sx={{ ...mono, fontSize: 9.5, color: FAINT, letterSpacing: ".07em", textTransform: "uppercase" }}>
                Repository
              </Typography>
              <Typography sx={{ fontSize: 12, fontWeight: 600, color: INK }}>{repo || "None selected"}</Typography>
            </Box>
            {(verdict.repo_reason || repo === "Not applicable") && <Typography sx={{ mt: 0.45, ml: 1.7, fontSize: 11.5, color: DIM, lineHeight: 1.5 }}>
              {verdict.repo_reason || (isFyi ? "No task was created from this item." : "This route does not use a code repository.")}
            </Typography>}
          </Box>
        )}

        {!!verdict.intent && (
          <Box>
            <Typography sx={{ ...mono, fontSize: 9.5, color: FAINT, letterSpacing: ".08em", textTransform: "uppercase" }}>
              Task list
            </Typography>
            {checklist.length ? (
              <Box component="ol" sx={{ listStyle: "none", p: 0, m: "7px 0 0", display: "grid", gap: 0.6 }}>
                {checklist.map((item, i) => (
                  <Box component="li" key={`${i}-${item}`} sx={{ display: "grid", gridTemplateColumns: "23px minmax(0, 1fr)",
                    gap: 0.8, alignItems: "start" }}>
                    <Box aria-hidden sx={{ width: 21, height: 21, borderRadius: "50%", border: "1px solid #c9d2c8",
                      bgcolor: "#f4f7f2", color: "#536b58", display: "grid", placeItems: "center",
                      ...mono, fontSize: 9.5, fontWeight: 600 }}>{i + 1}</Box>
                    <Typography sx={{ pt: 0.15, fontSize: 12.25, color: INK, lineHeight: 1.55 }}>{item}</Typography>
                  </Box>
                ))}
              </Box>
            ) : <Typography sx={{ mt: 0.35, fontSize: 11.5, color: FAINT }}>
              {isFyi ? "None — triage found no requested action."
                : isReply ? "None — this was routed to a reply instead of a task."
                  : "No separate checklist was returned."}
            </Typography>}
          </Box>
        )}

        {!exact && (
          <Typography variant="caption" sx={{ color: FAINT, lineHeight: 1.55 }}>
            This route was saved without structured triage details. These fields come from its saved route and resulting task; details that were never stored are not invented.
          </Typography>
        )}

        {verdict.why && (
          <Box sx={{ borderTop: `1px solid ${BORDER}`, pt: 1.05 }}>
            <Typography sx={{ ...mono, fontSize: 9.5, color: FAINT, letterSpacing: ".08em", textTransform: "uppercase" }}>
              Why
            </Typography>
            <Typography sx={{ mt: 0.3, fontSize: 12.25, color: DIM, lineHeight: 1.6 }}>{verdict.why}</Typography>
          </Box>
        )}

        {/* !! - an empty list is 0, and React draws a 0 (it sat under "Why" on every plain verdict, 2026-09-25) */}
        {!!(verdict.existing_task_id || (verdict.related_message_ids || []).length) && (
          <Typography variant="caption" sx={{ color: FAINT, lineHeight: 1.55 }}>
            {verdict.existing_task_id ? `Linked to ${ref(verdict.existing_task_id)}` : ""}
            {verdict.existing_task_id && (verdict.related_message_ids || []).length ? " · " : ""}
            {(verdict.related_message_ids || []).length ? `Related timeline items ${verdict.related_message_ids.join(", ")}` : ""}
          </Typography>
        )}
        {(noteCount > 0 || verdict.notes_left > 0) && (
          <Typography variant="caption" sx={{ color: FAINT }}>
            Memory evidence considered: {noteCount}{verdict.notes_left ? ` shown, ${verdict.notes_left} more did not fit` : ""}
          </Typography>
        )}
        {extras.length > 0 && (
          <Box sx={{ display: "flex", gap: 0.6, flexWrap: "wrap" }}>
            {extras.map(([key, value]) => (
              <TriageFact key={key} label={key.replaceAll("_", " ")}
                value={typeof value === "object" ? JSON.stringify(value) : String(value)} tone="relation" />
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
};

const TriagePane = ({ sel, detail, onRefresh }) => {
  const road = roadOf(sel);
  const failed = triageFailed(sel);
  const [retrying, setRetrying] = useState(false);
  const [retryNote, setRetryNote] = useState("");
  const [retryError, setRetryError] = useState(false);
  // Correcting the road. The panel has always PROMISED this ("correcting this teaches it") and
  // offered nothing to click; a pill is now the click. It does the road's real action as well as
  // recording the verdict - saying it without doing it would leave the funnel and the record
  // disagreeing, which is the failure this panel exists to prevent.
  const [fixing, setFixing] = useState("");
  const [fixNote, setFixNote] = useState("");
  const [fixError, setFixError] = useState(false);
  const reclassify = async (key) => {
    if (fixing || key === road) return;
    setFixing(key); setFixNote(""); setFixError(false);
    try {
      const { data } = await api.post(`/api/messages/${sel.MessageId}/reclassify`, { road: key });
      const meta = ROADS.find((r) => r.key === key);
      setFixNote(data.changed
        ? `Now ${meta?.label || key} — ${meta?.hint || ""}. Remembered for the next message like this one.`
        : `It was already ${meta?.label || key}.`);
      onRefresh?.();
    } catch (e) {
      setFixError(true);
      setFixNote(e?.response?.data?.detail || "That did not work.");
    }
    setFixing("");
  };
  const retryTriage = async () => {
    if (retrying) return;
    setRetrying(true); setRetryNote(""); setRetryError(false);
    try {
      const { data } = await api.post(`/api/messages/${sel.MessageId}/retriage`, {});
      setRetryNote(data.ref ? `Routed to ${data.ref}.` : data.status === "filed"
        ? "Triage still could not classify it. The new response is shown above."
        : "Triage completed.");
      onRefresh?.();
    } catch (e) {
      setRetryError(true);
      setRetryNote(e?.response?.data?.detail || "Triage retry failed.");
    }
    setRetrying(false);
  };
  // every judgement made about this message, oldest first. "And why" below is only the LATEST
  // one, which is why a correction was invisible here: the owner clicks "not ours", the verdict
  // changes, and the panel showed the new sentence with no sign that anyone had overruled
  // anything. Routes are keyed on the message, so they survive the task the verdict deletes.
  // ...about THIS message. On a task row detail.routes covers every message on the task, and a
  // thread's other rows were judged separately - their reasons are not this row's history.
  const trail = (detail?.routes || []).filter((r) => !r.MessageId || r.MessageId === sel.MessageId);
  const diagnostic = [...trail].reverse().find((r) => r.RawOutput != null || r.ParseError);
  // the sentence the classifier wrote, without the routing bookkeeping after it
  const why = routeWhy(sel.RouteReason).split(" · ")[0];
  const rest = String(sel.RouteReason || "").split(" · ").slice(1);
  const watch = (detail?.task || {}).Kind === "note";
  const savedVerdict = latestTriageVerdict(trail);
  const shownVerdict = savedVerdict || legacyTriageVerdict({
    routeReason: sel.RouteReason, routes: trail, task: detail?.task, checklist: detail?.checklist,
  });
  if (!sel.RouteReason && !road) return (
    <Typography variant="caption" sx={{ color: FAINT, lineHeight: 1.7 }}>
      Nothing judged this. {watch ? "You wrote it." : "It is here to be read."}
    </Typography>
  );
  return (
    <>
      <PanelLabel>Which road it took</PanelLabel>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.65, flexWrap: "wrap", mb: 1.5 }}>
        {ROADS.map((r) => {
          const on = road === r.key;
          return (
            <Box key={r.key} component="button" type="button" disabled={!!fixing || on}
              onClick={() => reclassify(r.key)}
              title={on ? r.hint : `Should have been ${r.label} — ${r.hint}. Sets it right and remembers it.`}
              aria-current={on ? "true" : undefined}
              sx={{ appearance: "none", font: "inherit", display: "flex", alignItems: "center", gap: 0.55,
                border: `1px solid ${on ? "#aebcaf" : BORDER}`, borderRadius: 10, px: 1.15, height: 30,
                bgcolor: on ? "#edf1eb" : "transparent", cursor: on ? "default" : "pointer",
                opacity: fixing && fixing !== r.key ? 0.5 : 1,
                "&:hover": on ? {} : { bgcolor: "#f7f4ef", borderColor: "#d8cfbe" },
                "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } }}>
              {on && <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: ACCENT2 }} />}
              <Typography sx={{ fontSize: 11.5, fontWeight: on ? 700 : 500, color: on ? INK : FAINT }}>
                {fixing === r.key ? "…" : r.label}
              </Typography>
            </Box>
          );
        })}
        {road && <Typography variant="caption" sx={{ color: FAINT, ml: 0.35 }}>
          {ROADS.find((r) => r.key === road)?.hint}
        </Typography>}
      </Box>
      <PanelLabel>Full triage response</PanelLabel>
      {shownVerdict ? <TriageVerdictCard verdict={shownVerdict} exact={!!savedVerdict} /> : (
        <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.5, py: 1.25, bgcolor: "#fcfaf7" }}>
          <Typography sx={{ fontSize: 13, color: INK, lineHeight: 1.65 }}>{why || sel.RouteReason}</Typography>
          {!!rest.length && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.85, lineHeight: 1.6 }}>
              {rest.join(" · ")}
            </Typography>
          )}
        </Box>
      )}
      {diagnostic && (
        <>
          <PanelLabel>What the triage AI returned</PanelLabel>
          <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.5, py: 1.25,
            bgcolor: "#f7f5f1", maxHeight: 300, overflowY: "auto", overflowX: "hidden" }}>
            {diagnostic.ParseError && (
              <Typography variant="caption" sx={{ color: ALERT_INK, display: "block", mb: 0.75,
                overflowWrap: "anywhere" }}>
                Parser: {diagnostic.ParseError}
              </Typography>
            )}
            <Typography component="pre" sx={{ m: 0, ...mono, color: DIM, fontSize: 11,
              lineHeight: 1.55, whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word" }}>
              {diagnostic.RawOutput || "(No response was returned.)"}
            </Typography>
          </Box>
        </>
      )}
      {failed && (!sel.TaskId || sel.MsgStatus === "error") && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1.25 }}>
          <Button size="small" variant="outlined" disabled={retrying} onClick={retryTriage}
            startIcon={retrying ? <CircularProgress size={13} /> : <SyncIcon sx={{ fontSize: 16 }} />}>
            {retrying ? "Retrying triage…" : "Retry triage"}
          </Button>
          {retryNote && (
            <Typography variant="caption" sx={{ color: retryError ? ALERT_INK : DIM,
              overflowWrap: "anywhere" }}>
              {retryNote}
            </Typography>
          )}
        </Box>
      )}
      {trail.length > 1 && (
        <>
          <PanelLabel>How it got here</PanelLabel>
          <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.5, py: 0.25, bgcolor: "#fcfaf7" }}>
            {trail.map((r, i) => {
              const mine = r.Decision === "ignore";
              return (
                <Box key={r.RouteId || i} sx={{ display: "flex", alignItems: "baseline", gap: 1, py: 0.65,
                  borderTop: i ? `1px solid ${BORDER}` : "none" }}>
                  <Typography variant="caption" sx={{ fontWeight: 600, flexShrink: 0,
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
        Pick another road to correct it: the message goes down that road for real, and the verdict
        lands in memory for the next message like this one, not as a rule about this sender.
      </Typography>
      {fixNote && (
        <Typography variant="caption" sx={{ display: "block", mt: 0.5, lineHeight: 1.6,
          color: fixError ? ALERT_INK : "#47654a" }}>{fixNote}</Typography>
      )}
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
      ? <Typography key={i} variant="body2" sx={{ fontWeight: 600, color: INK, mt: i ? 1.1 : 0,
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
      hint={`add one under ${placeName("voice")} (Groq has a free tier; Local Whisper needs no key), then come back and click Transcribe`} />
  );
};

// A chain can hold several messages (the inbound thread plus your replies), and a chat room hands
// over its whole history. So it reads AS a chat: the last few in order, newest at the bottom, your
// own lines on the right, and one click walks back through what came before. A strip of picker
// pills came first and it flipped the panel between messages one at a time - at 131 lines in a
// WhatsApp group that was a row of dates, and a conversation you have to click through is not a
// conversation. (The room is the thread there: whatsapp:<jid> is a relationship, not a topic, so
// "131 messages" is the whole group chat, not 131 messages about one thing.)
const isOwnMessage = (m) => m?.Status === "context" || m?.Direction === "out";

const Bubble = ({ m, fallback, context }) => {
  const [showQuoted, setShowQuoted] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [full, setFull] = useState(false);
  // what just arrived, separated from the thread quoted underneath it
  const { latest: said, quoted } = splitQuoted(cleanText(m?.BodyText) || fallback || "…");
  // what they WROTE, cleaned of signature, legal footer and banner by the server (ReadText) - the quoted
  // thread still folds below it, and the original is a click away
  const latest = m?.ReadText != null && m?.Direction !== "out" ? cleanText(m.ReadText) : said;
  const whole = latest || quoted;
  // a report's raw rows are receipts, not reading: the summary is the message, the rows fold
  // away behind one click - same treatment the quoted thread below a reply gets
  const RAW = "\n--- raw data ---";
  const cut = whole.indexOf(RAW);
  const text = cut >= 0 ? whole.slice(0, cut).trimEnd() : whole;
  const raw = cut >= 0 ? whole.slice(cut + RAW.length).trim() : "";
  const you = isOwnMessage(m);
  const own = !you && m?.Channel === "own";        // a note you left yourself: nothing arrived
  // an excerpt first. A PR body or a forwarded chain ran the panel into its own scrollbar
  // and pushed the choices under the fold; the first screen of a message is what the
  // decision needs, and the rest is one click, not a scroll, away
  // An ordinary mail should arrive WHOLE. At 8 lines / 700 chars the fold landed inside the first
  // screen of most of them - a signature, and the address the owner actually needed, sat behind
  // "show the whole message" on a nine-line note (2026-09-15). The fold is for a forwarded chain
  // or a PR body, not for a paragraph and a sign-off.
  const LINES = 20, CHARS = 2000;
  const rows = text.split("\n");
  const long = rows.length > LINES || text.length > CHARS;
  const excerpt = long ? rows.slice(0, LINES).join("\n").slice(0, CHARS).trimEnd() + " …" : text;
  const shown = full || !long ? text : excerpt;
  return (
    <Box sx={{ bgcolor: you || own ? "#e9e3d8" : PANEL2, border: `1px solid ${you || own ? "#d8d0c4" : BORDER}`,
      borderRadius: you || own ? "14px 14px 4px 14px" : "14px 14px 14px 4px", p: 1.25,
      borderLeft: `3px solid ${you ? "#8a7a5c" : "#6f8a6e"}`,
      // context recedes; it is there to be read past, not acted on - but only a step back. At 0.58
      // it was not receded, it was unreadable, which defeats the point of carrying it in at all
      // (the owner, 2026-09-15: "why does this look so faded?").
      opacity: context ? 0.75 : 1,
      maxWidth: you || own ? "88%" : "100%", ml: you || own ? "auto" : 0 }}>
      {/* who / which way / when - so "new inbound" is never confused with "your reply" */}
      {m && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.6, flexWrap: "wrap" }}>
          <Chip size="small" label={you ? "↩ your reply" : own ? "your note" : "inbound"}
            sx={{ height: 17, fontSize: 9.5, fontWeight: 600, letterSpacing: 0.3,
              bgcolor: you || own ? ROLES.working.tint : ROLES.muted.tint,
              color: you || own ? ROLES.working.ink : ROLES.muted.ink }} />
          <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>
            {you ? "you" : m.FromName || m.FromEmail || "unknown"}
          </Typography>
          <Typography variant="caption" sx={{ color: FAINT }}>· {fmtDateTime(m.SentAt)}</Typography>
          {quoted && <Typography variant="caption" sx={{ color: FAINT }}>· replying on this thread</Typography>}
        </Box>
      )}
      {m?.Channel === "report" ? ((m?.SourceName === "Morning digest" || /^Morning digest\b/i.test(m?.Subject || ""))
          ? <DigestText text={text} /> : looksMd(text) ? <Md text={text} /> : <SectionedText text={text} />)
        : own && (!text.trim() || text === "…")
          ? <Typography variant="body2" sx={{ color: FAINT, fontStyle: "italic" }}>You started this yourself — there is no incoming message behind it.</Typography>
        : <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, textAlign: "left" }}>
            {shown}
          </Typography>}
      {long && m?.Channel !== "report" && (
        <Typography variant="caption" component="button" type="button" aria-expanded={full}
          onClick={() => setFull(!full)} sx={{ appearance: "none", border: 0, bgcolor: "transparent", p: 0,
            display: "block", mt: 0.5, color: "#55697a", font: "inherit", fontWeight: 600,
            textAlign: "left", cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
          {full ? "show less ↑" : `show the whole message — ${rows.length} lines ↓`}
        </Typography>
      )}
      {raw && (
        <Box sx={{ mt: 1, borderTop: `1px dashed ${BORDER}`, pt: 0.75 }}>
          <Typography variant="caption" component="button" type="button" aria-expanded={showRaw}
            onClick={() => setShowRaw(!showRaw)} sx={{ appearance: "none", border: 0, bgcolor: "transparent", p: 0,
              color: DIM, font: "inherit", fontWeight: 600, textAlign: "left", cursor: "pointer",
              "&:hover": { color: "#55697a" } }}>
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
          <Typography variant="caption" component="button" type="button" aria-expanded={showQuoted}
            onClick={() => setShowQuoted(!showQuoted)} sx={{ appearance: "none", border: 0, bgcolor: "transparent", p: 0,
              color: DIM, font: "inherit", fontWeight: 600, textAlign: "left", cursor: "pointer",
              "&:hover": { color: "#55697a" } }}>
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
      {m && <Attachments messageId={m.MessageId} canFetch={m.Channel === "email"} />}
    </Box>
  );
};

const SHOWN = 5, STEP = 10;   // the last five read as the conversation; each click walks ten back

// THE ASK IS WHAT OPENS, not the room it was typed in. The panel used to draw every message
// sharing a ConversationId - and on a chat that id names a ROOM, so one "Budgeting" line came
// with 131 lines of a WhatsApp group behind it. It now opens on the messages the item actually
// holds (what triage ruled is THIS ask), and the rest of the room is one click below the fold,
// fetched only if it is asked for. Order is the conversation's own: oldest at the top, newest
// at the bottom, so walking back goes UP.
const MessageBlock = ({ messages, focusId, fallback, threadTotal, askIds }) => {
  const scoped = messages || [];
  const [room, setRoom] = useState(null);       // the rest of the conversation, once asked for
  const [shown, setShown] = useState(SHOWN);
  const [loading, setLoading] = useState(false);
  useEffect(() => { setRoom(null); setShown(SHOWN); setLoading(false); }, [focusId]);
  const msgs = room || scoped;
  // never cut off the message the clicked row is about, however far back on the thread it is
  const back = msgs.findIndex((m) => m.MessageId === focusId);
  const n = Math.min(msgs.length, Math.max(shown, back < 0 ? 0 : msgs.length - back));
  const list = msgs.slice(-n), earlier = msgs.length - n;
  const ask = askIds || [];
  const rest = room || !focusId ? 0 : Math.max(0, (threadTotal || 0) - scoped.length);
  const loadRoom = () => {
    setLoading(true);
    api.get(`/api/messages/${focusId}/thread?limit=500`)
      .then(({ data }) => { setRoom(data.messages || scoped); setShown(scoped.length + STEP); })
      .catch(() => setRoom(scoped))
      .finally(() => setLoading(false));
  };
  const label = loading ? "loading the conversation…"
    : earlier ? `↑ show ${Math.min(STEP, earlier)} older${earlier > STEP ? ` · ${earlier} before this` : ""}`
    // NOT "earlier". What is missing is whatever the item does not own, and on a thread the owner
    // has already answered that is the reply that came back AFTER it - which then arrives at the
    // bottom of the list while the pill that promised it sits at the top (2026-09-15: "the rest of
    // the convo is nothing more when you click on it??").
    : `↑ the rest of this conversation — ${plural(rest, "more line")} in the same chat`;
  return (
    <>
      {!!(earlier || rest || loading) && (
        <Box onClick={loading ? undefined : earlier ? () => setShown(n + STEP) : loadRoom}
          title={earlier ? `${earlier} more already loaded` : "these were said in the same chat, about other things"}
          sx={{ width: "fit-content", mx: "auto", mb: 0.75, px: 1.2, py: 0.4, borderRadius: 99,
            cursor: loading ? "default" : "pointer", fontSize: 11, fontWeight: 600, whiteSpace: "nowrap",
            border: `1px dashed ${BORDER}`, color: FAINT,
            "&:hover": { borderColor: "#d8cfbe", color: loading ? FAINT : "#55697a" } }}>
          {label}
        </Box>
      )}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
        {(list.length ? list : [null]).map((m, i) => (
          <Bubble key={m?.MessageId ?? "none"} m={m} context={m && ask.length > 0 && !ask.includes(m.MessageId)}
            fallback={i === (list.length || 1) - 1 ? fallback : undefined} />
        ))}
      </Box>
    </>
  );
};

// An action proposal's DraftText is its JSON envelope. For most actions that IS the thing to read
// (a bill: vendor, amount, account); a proposed playbook is a page of markdown, so show the page.
const proposalText = (t) => {
  try { const j = JSON.parse(t); if ((j?.action === "write_playbook" || j?.action === "amend_playbook") && j.text) return j.text; } catch { /* a plain draft */ }
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
// One post, opened: each line keeps its actions and conversation. The supporting facts remain in
// report run history for auditing, but the Timeline card does not put a little "why?" under every
// sentence; that label turned a readable brief into a stack of footnotes.
// State comes from the server (a line acted on from another tab shows as done here too); the
// buttons are the ones the line's action allows.
// A line's kind wears the word its card wears, a candidate the word a run's review counts it in (lanes.json `idea_kinds`).

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
    <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK, letterSpacing: "-.1px" }}>{label}</Typography>
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
        <Typography sx={{ fontSize: 17, fontWeight: 600, lineHeight: 1,
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
  const [remindAt, setRemindAt] = useState(null);     // { idea, anchor }: Remind me's day picker
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { const { data } = await api.get(`/api/assistant/ideas?mid=${sel.MessageId}`); if (data.data?.length) setIdeas(data.data); } catch { /* keep the post's own copy */ }
  }, [sel.MessageId]);
  useEffect(() => { load(); }, [load]);
  // THE SAME FIVE WORDS AS EVERY OTHER SURFACE (the owner, 2026-09-27): Make a task, Send to agent, Remind me, Not
  // ours - and Next, which is the walk's. Draft follow-up and Discuss are gone: a task's agent drafts the chase.
  const act = async (i, verb) => {
    setBusy(`${i.id}:${verb}`); setErr("");
    try {
      const { data } = await api.post(`/api/assistant/ideas/${i.id}/${verb}`, {});
      if ((verb === "task" || verb === "agent") && data.taskId) onOpenTask?.(data.taskId);
    } catch (e) { setErr(e?.response?.data?.detail || "That did not work"); }
    setBusy(null); load(); onChanged?.();
  };
  const btn = { textTransform: "none", fontSize: 11.5, minWidth: 0, minHeight: 27, px: 1.1, lineHeight: 1.2 };
  const primary = { color: "#fff", background: ASSISTANT.gradient,
    "&:hover": { background: "linear-gradient(90deg, #465866, #698368)" } };
  const quiet = { color: DIM, borderColor: BORDER, bgcolor: PANEL,
    "&:hover": { borderColor: ASSISTANT.solid, bgcolor: "#f7f8f4" } };
  // ONE renderer for a line, called from inside whichever section it belongs to.
  const line = (i) => {
        const a = i.action || {}, answered = i.answered, open = i.status === "open" && !answered, ev = a.event;
        return (
          <Box key={i.id} sx={{ px: 1.25, py: 0.85, mb: 0.6, borderRadius: 1.5, border: `1px solid ${ASSISTANT.bd}`, bgcolor: open ? ASSISTANT.tint : "#f4f3ef", opacity: open ? 1 : 0.72 }}>
            <Box sx={{ display: "flex", gap: 0.75, alignItems: "baseline" }}>
              <Typography variant="caption" sx={{ color: ASSISTANT.ink, fontWeight: 600, flexShrink: 0 }}>{answered ? "answered" : ideaWord(i.kind)}</Typography>
              <Typography variant="body2" sx={{ color: INK, lineHeight: 1.45, flex: 1 }}>
                {answered ? "You had already replied to this." : i.text}
              </Typography>
            </Box>
            {answered?.text && (
              <Box sx={{ mt: 0.55, ml: "auto", maxWidth: "88%", px: 1, py: 0.65,
                bgcolor: "#e9e3d8", border: "1px solid #d8d0c4", borderRadius: "12px 12px 4px 12px" }}>
                <Typography variant="caption" sx={{ color: INK, display: "block", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>
                  {cleanText(answered.text)}
                </Typography>
              </Box>
            )}
            {ev && (
              <Typography variant="caption" sx={{ display: "block", color: DIM, mt: 0.3 }}>
                {ev.who?.length ? `with ${ev.who.join(", ")}` : ""}{ev.where ? ` · ${ev.where}` : ""}{ev.about ? ` · ${ev.about}` : ""}
              </Typography>
            )}
            {/* WHICH QUERY PUT THIS IN FRONT OF IT. Looked up from the block that supplied the
                message, never asked of the model - a line with no source says nothing rather than
                guessing, which is the only reason this is worth reading at all. */}
            {a.source && (
              <Typography variant="caption" sx={{ ...mono, display: "block", color: FAINT, mt: 0.35, fontSize: 10.5 }}>
                from: {a.source.label || a.source.block}{a.source.window ? ` (${a.source.window})` : ""}
                {a.source.rows?.length ? ` · ${plural(a.source.rows.length, "message")}` : ""}
              </Typography>
            )}
            {open ? (
              <Box sx={{ mt: 0.75, display: "flex", gap: 0.6, flexWrap: "wrap", alignItems: "center" }}>
                <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={() => act(i, "task")}
                  title={bHint("mine")} sx={{ ...btn, ...primary }}>
                  {busy === `${i.id}:task` ? "making…" : bLabel("mine")}</Button>
                <Button size="small" variant="outlined" disabled={!!busy} onClick={() => act(i, "agent")}
                  title={bHint("regular_agent")} sx={{ ...btn, ...quiet }}>
                  {busy === `${i.id}:agent` ? "sending…" : bLabel("regular_agent")}</Button>
                <Button size="small" variant="outlined" disabled={!!busy} onClick={(e) => setRemindAt({ idea: i, anchor: e.currentTarget })}
                  title={bHint("defer")} sx={{ ...btn, ...quiet }}>{bLabel("defer")}</Button>
                <Button size="small" variant="outlined" disabled={!!busy} onClick={() => act(i, "dismiss")}
                  title={bHint("not_ours")} sx={{ ...btn, ...quiet }}>
                  {busy === `${i.id}:dismiss` ? "…" : bLabel("not_ours")}</Button>
                {a.tid && <Button size="small" variant="outlined" onClick={() => onOpenTask?.(a.tid)} sx={{ ...btn, ...quiet }}>Open {ref(a.tid)}</Button>}
              </Box>
            ) : (
              // a settled idea still leads to the task it became, says which day a put-away one comes back, and never
              // shows a status's raw name
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.4, flexWrap: "wrap" }}>
                <Typography variant="caption" sx={{ color: FAINT }}>
                  {answered ? `reply sent${answered.at ? ` · ${fmtDateTime(answered.at)}` : ""}`
                    : i.status === "done" ? "done" : i.status === "dismissed" ? "not ours"
                      : i.status === "snoozed" ? (i.until ? `put away until ${fmtDateTime(i.until)}` : "put away until its day") : "no longer open"}
                </Typography>
                {a.tid && <Button size="small" variant="outlined" onClick={() => onOpenTask?.(a.tid)} sx={{ ...btn, ...quiet }}>Open {ref(a.tid)}</Button>}
              </Box>
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
        <Typography sx={{ color: ASSISTANT.ink, fontWeight: 600, fontSize: 13 }}>Your assistant</Typography>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>{fmtDateTime(sel.SentAt)}</Typography>
        {err && <Typography variant="caption" sx={{ color: ALERT_INK }}>{err}</Typography>}
      </Box>
      <DayStats rows={brief.stats} />
      {remindAt && <RemindPicker task={{ TaskId: `idea-${remindAt.idea.id}` }} path={`/api/assistant/ideas/${remindAt.idea.id}/snooze`}
        anchor={remindAt.anchor} onClose={() => setRemindAt(null)} onDone={() => { load(); onChanged?.(); }} />}
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
      {/* THE ASSISTANT'S OWN WORDS, when the structured post cannot show them. Every line here is
          drawn from `brief.ideas`, so a post whose brief did not reach the page rendered as an
          empty card - while the very sentence it wrote sat in the message all along, unused
          (the owner, 2026-09-16: "it should show the message underneath it that the assistant
          says"). The ideas are richer when they are there (they carry the actions); this is what
          it SAID, which is never nothing. */}
      {!ideas.length && cleanText(sel.Preview) && (
        <Typography variant="body2" sx={{ color: INK, mt: 1, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
          {cleanText(sel.Preview)}
        </Typography>
      )}
      {/* ...and only when it truly said nothing. "What it read is below" is a PROMISE, and the
          block it points at is the `rv` one; said unconditionally it ended the post pointing at
          nothing at all. Promise only what is actually there. */}
      {!ideas.length && !cleanText(sel.Preview) && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1, lineHeight: 1.7 }}>
          Nothing worth saying this time — which is most checks.{rv ? " What it read is below." : ""}
        </Typography>
      )}
      {rv && (
        <Box sx={{ mt: 1.5, px: 1.25, py: 0.7, borderRadius: 1.5, border: `1px dashed ${BORDER}`, bgcolor: "#faf8f4" }}>
          <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.45 }}>
            <Box component="span" sx={{ fontWeight: 600, color: "#6b5f45" }}>what it reviewed · </Box>
            {rv.scope === "sources" ? `${plural(rv.systems ?? 0, "configured data source")} only` : <>
              {Object.entries(rv.candidates || {}).map(([k, v]) => `${v} ${ideaCounted(k)}`).join(", ") || "no candidates"}
              {rv.people != null ? ` · ${plural(rv.people, "thread")} of what people said` : ""}
              {rv.recent != null ? ` · ${plural(rv.recent, "sender/subject line")} from the last two days · ${plural(rv.week, "task")} closed this week`
                : ` · ${plural(rv.today, "message")} from today`}
              {` · ${plural(rv.open, "open task")} · ${plural(rv.said, "line")} already said`}
            </>}
            {rv.model ? " · the model chose the lines" : " · no model — the hub's facts in its own words"}
          </Typography>
          {/* what it left for its next check - so you can see what it will NOT research again */}
          {rv.notes && (
            <Typography variant="caption" sx={{ display: "block", color: DIM, lineHeight: 1.45, mt: 0.3 }}>
              <Box component="span" sx={{ fontWeight: 600, color: "#6b5f45" }}>note to its next check · </Box>{rv.notes}
            </Typography>
          )}
          {!!rv.skipped?.length && (
            <>
              <Typography variant="caption" onClick={() => setShowSkipped((v) => !v)}
                sx={{ display: "block", mt: 0.3, color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                {showSkipped ? "hide" : "show"} what it looked at and let go — {rv.skipped.length} {showSkipped ? "↑" : "↓"}</Typography>
              {showSkipped && rv.skipped.map((c) => (
                <Typography key={c.key} variant="caption" sx={{ display: "block", color: FAINT, mt: 0.3, pl: 1, borderLeft: `2px solid ${BORDER}`, whiteSpace: "pre-wrap" }}>
                  <Box component="span" sx={{ fontWeight: 600 }}>{ideaCounted(c.kind)} · </Box>{c.facts}</Typography>
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

const ReviewActions = ({ reviewId, draft, editText, setEditText, decide, sendErr, clearSendErr, canSend, onChanged, channel, review, compare = null, clearCompare = null }) => {
  const [generating, setGenerating] = useState(false);
  // the server's two facts about this reply, said the same way on every surface (sendState.js):
  // whether it can leave from here, and whether a draft exists or failed to be written
  const blocked = sendBlockLine({ ...(review || {}), CanSend: canSend, Channel: channel });
  const drafting = draftState({ ...(review || {}), HasDraft: (editText ?? draft ?? "").trim() ? 1 : 0 });
  const [draftErr, setDraftErr] = useState("");
  const envelope = replyEnvelope(review);
  const [editedCc, setCc] = useState(null);
  const cc = editedCc ?? envelope?.cc ?? [];
  const deliveryUnknown = sendErr?.unknown || envelope?.delivery === "unknown";
  const files = envelope?.attachments || [];
  const text = editText ?? draft ?? "";
  const save = async (value = text) => {
    try { await api.patch(`/api/reviews/${reviewId}`, { body: value }); onChanged?.(); }
    catch (e) { setDraftErr(e?.response?.data?.detail || "Could not save this draft"); }
  };
  const generate = async () => {
    setGenerating(true); setDraftErr("");
    try {
      const { data } = await api.post(`/api/reviews/${reviewId}/draft`);
      setEditText(data.draft || ""); onChanged?.();
    } catch (e) { setDraftErr(e?.response?.data?.detail || "Could not generate a draft"); }
    setGenerating(false);
  };
  return (
  <Box>
    {envelope && <Typography data-reply-recipients variant="caption" sx={{ display: "block", mb: 0.75 }}>
      To: {envelope.to.join(", ") || "No recipient selected"}
      {cc.length > 0 && <> · CC: {cc.join(", ")}</>}
    </Typography>}
    <CcRow cc={cc} setCc={setCc} channel={channel} />
    <TextField fullWidth multiline minRows={3} size="small" placeholder="Type your reply, or generate a draft with AI"
      value={text} onChange={(e) => setEditText(e.target.value)} onBlur={(e) => save(e.target.value)} sx={{ mb: 1 }} />
    <ReplyFiles reviewId={reviewId} files={envelope?.attachments || []} text={text} channel={channel} onChanged={onChanged} />
    {drafting.line && (
      <Typography variant="caption" sx={{ display: "block", mb: 0.75, color: drafting.state === "failed" ? ALERT_INK : DIM }}>{drafting.line}</Typography>
    )}
    {blocked && (
      <Typography variant="caption" sx={{ display: "block", mb: 0.75, color: DIM }}>{blocked}</Typography>
    )}
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
      {/* ONE approve: it sends what is in the box, edited or not - two buttons asked you to
          declare something the text already shows. A channel that cannot CARRY the reply
          (github with replies off) offers closing instead of a send that bounces. */}
      {canSend === false ? (
        <Button size="small" variant="contained" disableElevation
          sx={{ bgcolor: "#8a8276", "&:hover": { bgcolor: "#6b6459" } }}
          title="GitHub replies are off (GitHub card → Reply to issue/PR authors) — mark it done without sending"
          onClick={() => decide(reviewId, "close_unsent")}>{bLabel("close")}</Button>
      ) : (
        <>
          <Button size="small" variant="contained" disabled={!text.trim() || (channel === "email" && !review) || (envelope && !envelope.to.length)}
            onClick={() => decide(reviewId, "approve", text, cc)}
            title="Sends the text above on the channel it arrived on">
            {deliveryUnknown ? "Check delivery and retry"
              : [bLabel("approve"), files.length ? plural(files.length, "file") : "",
                 cc.length ? `copying ${cc.length}` : ""].filter(Boolean).join(" · ")}</Button>
          {/* Mark done, not "No reply needed": one word for the one close (the owner, 2026-09-24) */}
          <Button size="small" sx={{ color: "#867f74" }} onClick={() => decide(reviewId, "no_reply")}
            title={`${bHint("close")} - this draft is not sent`}>{bLabel("close")}</Button>
        </>
      )}
      <Box sx={{ flex: 1 }} />
      <Button size="small" variant="outlined" disabled={generating} onClick={generate}>
        {generating ? <CircularProgress size={12} /> : text.trim() ? "Regenerate with AI" : "Generate with AI"}
      </Button>
    </Box>
    {draftErr && <Alert severity="error" sx={{ mt: 1 }} onClose={() => setDraftErr("")}>{draftErr}</Alert>}
    {compare?.reviewId === reviewId && (
      <Box sx={{ mt: 1, border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75 }}>
        <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 600, display: "block" }}>
          Refreshed draft - written after the new message. Your edit stays in the box above.
        </Typography>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: 12.5, mt: 0.5 }}>{compare.refreshed || "(no refreshed draft - hit Redraft)"}</Typography>
        <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
          <Button size="small" variant="outlined" disabled={!compare.refreshed}
            onClick={() => { setEditText(compare.refreshed); clearCompare?.(); }}>Use the refreshed draft</Button>
          <Button size="small" onClick={() => clearCompare?.()}>Keep mine</Button>
        </Box>
      </Box>
    )}
    {(sendErr || deliveryUnknown) && (
      <Alert severity="error" sx={{ mt: 1 }} onClose={clearSendErr}>
        <b>{deliveryUnknown ? "Delivery is unknown." : "Approved, but it did not send."}</b> {sendErr?.message || sendErr}
        <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
          {deliveryUnknown ? "The provider may have sent this reply. Check delivery before sending another copy; retry checks the provider first. Your draft is retained."
            : "The draft is retained. Resolve the delivery error before retrying."}
        </Box>
      </Alert>
    )}
  </Box>
  );
};
