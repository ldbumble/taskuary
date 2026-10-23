// The Assistant page's sidebar and stage: the buttons, the filter and the sync line over the Work rail (the
// ranked pipe AssistantView draws), and beside it the stage - the conversation, where every item opens as its
// card. A live socket pushes new rows in; the list is not on a timer. (The Timeline - every message in date
// order, a tab beside Work - was removed 2026-10-15; its row detail panel, 2026-10-20.)
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, ListSubheader, MenuItem, Popover, TextField, Tooltip, Typography, useMediaQuery,
} from "@mui/material";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import api from "./api";
import { label as bLabel, hint as bHint } from "./buttons.js";
import { plainError } from "./apiError.js";
import SearchEverything, { OPEN_SEARCH, searchPicked } from "./SearchEverything.jsx";
import { fadeBand } from "./timelineFade.js";
import { syncFace, syncPhaseLabel } from "./syncTiming.js";
import { observeSync } from "./syncObserver.js";
import { onWrote } from "./wrote.js";
import { availablePickerChannels, channelsForCategory } from "./feedFilters.js";
import { splitTimelineMeetings } from "./timelineMeetings.js";
import { onLive } from "./live.js";
import { feedHeaders, feedOk, takeFeed } from "./feedLoad.js";
import { ALERT_INK, PILL_COLORS, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import BarChartIcon from "@mui/icons-material/BarChart";
import PowerOutlinedIcon from "@mui/icons-material/PowerOutlined";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import TuneIcon from "@mui/icons-material/Tune";
import { SIDE_NAV } from "./sideNav.js";
import { localDay, tsMs, tzNow } from "./ui.jsx";
import NewSheet from "./NewSheet.jsx";
import AddIcon from "@mui/icons-material/Add";
import { processingErrorMessage, processingTransportLimit, unreadProcessingRows } from "./processingAll.js";
import { fyiTail, pileRows } from "./funnelPile.js";

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
// is the conversation; a #msg= link puts that message's card on it (canvasLinks).
// On a phone the chat and the rail take turns: `railOnNarrow` says which one is up.
// The countdown ticks on its own. As a 1 s state change on FeedView it re-rendered every row of the rail
// every second for as long as the tab was open.
function NextIn({ atRef, render }) {
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((t) => t + 1), 1000); return () => clearInterval(id); }, []);
  return render(atRef.current ? Math.max(0, Math.round((atRef.current - Date.now()) / 1000)) : null);
}

export default function FeedView({ onOpenTask, onChanged, active = true, top = null, stage = null, onPull = null, railOnNarrow = false, onInventoryFilter = null, unreadInventory = null, onGo = null, navOn = "", openNew = 0, setupMode = false, setupRail = null }) {
  // below md there is no stage beside the rail; whatever is opened slides over it instead, so a
  // tap on a row is never a tap that did nothing
  const narrow = useMediaQuery("(max-width:899.95px)");
  // WORK IS THE ONLY VIEW. The Timeline - every message in date order, a second tab beside Work - is gone (the owner,
  // 2026-10-15: "removing the timeline tab ... replace it with the filter being a little larger"); the rail is the pipe.
  const visibleStage = stage;
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
  // A REFUSED OR FAILED SYNC SAYS SO IN THE CLOCK'S OWN SLOT (the UX walk, 2026-10-22): a refusal read as "status unavailable" and a
  // source that failed read as "checked 9:41". Both are the line's status, not a receipt - gone at the next press or clean status
  const [syncErr, setSyncErr] = useState("");
  const [syncFailed, setSyncFailed] = useState([]);
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
    setSyncFailed(Array.isArray(data.failed) ? data.failed : []);
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
  // The newest applyStatus, read when a status lands. Depending on it restarted the observer - an immediate status read - on
  // every render of the Assistant (its inline `top` reaches `load`): 15 reads a press, and a rail re-render each (perf 2.8,
  // 2026-10-19). What that accident also did, bring an owner's change to the caption at once, is now said by onWrote.
  const applyLatest = useRef(applyStatus); applyLatest.current = applyStatus;
  useEffect(() => {
    // gated on `active`: the Timeline stays mounted behind another tab, and coming back
    // re-asks at once. Hidden windows stay subscribed via onLive but do not refetch.
    if (!active) return undefined;
    const observer = observeSync({
      read: () => api.get("/api/ingest/status", { timeout: 10000 }).then(({ data }) => data),
      changed: d => applyLatest.current(d),
      failed: () => setSyncUnknown(true),
      subscribe: refresh => { const off = onLive(["feed-changed", "ingest-status"], refresh), offWrote = onWrote(refresh); return () => { off(); offWrote(); }; },
    });
    syncObserver.current = observer;
    return () => { observer.stop(); syncObserver.current = null; clearTimeout(completionTimer.current); };
  }, [active]);
  const syncNow = useCallback(async (silent) => {
    if (syncUnknown) { await syncObserver.current?.refresh(); return; }
    if (!silent) setSyncing(true);
    setSyncErr("");
    // ...an answer that refused is its own words; only no answer at all leaves the state unknown
    try { await api.post("/api/ingest/poll"); }
    catch (e) { if (e?.response) { setSyncing(false); setSyncErr(plainError(e, "The sync was refused.")); } else setSyncUnknown(true); }
    await syncObserver.current?.refresh();
  }, [syncUnknown]);

  const loadLatest = useRef(load);
  loadLatest.current = load;
  useEffect(() => {
    // a real filter change only: `load` also changes whenever the Assistant supplies a newer Work inventory
    etagRef.current = "";                        // a new filter is not the same page
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

  // only offer channels that actually have a connection behind them. With no category
  // picked, EVERY connected channel is offered - a hardcoded five-channel list here
  // silently hid telegram/whatsapp/jira/... sources from the picker as connectors grew
  // ...and the FYI the rail has not been sent whole yet (funnel.page_fyi) have their channels all the same
  const availableChannels = [...new Set([...Object.keys(srcByChannel), ...(rows || []).map((r) => r.Channel),
    ...(unreadInventory?.canonical ? fyiTail(unreadInventory).map((i) => i.channel || "") : [])])];
  const pickerChannels = availablePickerChannels(cat, availableChannels);

  const today = new Date().toLocaleDateString("sv-SE");
  // localDay over every row on every render (each key, each poll) was seconds on a large home; the set only changes with the
  // rows, the day, or the zone the settings load in (2026-10-19)
  // every row is counted, the FYI tail the page has not asked for whole included (pileRows)
  const canon = !!unreadInventory?.canonical, canonItems = useMemo(() => pileRows(unreadInventory), [unreadInventory]), tz = tzNow();
  const todays = useMemo(() => (canon
    ? (canonItems || []).map(i => ({ SentAt: i.when, Category: i.category, MsgStatus: i.status }))
    : (rows || [])).filter((r) => localDay(r.SentAt) === today), [canon, canonItems, rows, today, tz]);
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
      {/* ── the rail ────────────────────────────────────────────────────────────── */}
      <Box data-tq-keep
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
          {/* A HIT OPENS ON THE ASSISTANT CANVAS, whatever the mode, through the same pull a rail click takes (pull switches the
              stage to chat) - it opened the task-mode panel, titled "undefined in chat" (the owner, 2026-10-14: "searched task
              should show up on assistant canvas regardless not on the task view") */}
          {/* ...and QUIET: a pick is not something the owner said, so no "Tell me about ..." bubble rides in above the task
              (the owner, 2026-10-15: "why does the gray thing show up when clicking on searched task. Just show the task") */}
          <SearchEverything open={searchOpen} onClose={() => setSearchOpen(false)}
            onOpenTask={(tid, h) => { searchPicked(); return onPull ? onPull({ TaskId: tid, Title: h?.title }, { quiet: true }) : onOpenTask?.(tid); }}
            onOpenMessage={(mid, h) => { searchPicked(); return onPull ? (onPull({ MessageId: mid, TaskId: h?.tid, Subject: h?.title }, { quiet: true }), true) : false; }}
            onPickSource={(next) => {
              searchPicked();
              loadRequest.current += 1;
              if (cat) { pendingPick.current = next; setCat(""); } else setPick(next);
            }} />

          {/* THE FILTER TAKES THE ROW. Work | Timeline sat here; with the Timeline gone (the owner, 2026-10-15) the filter
              is the row's one control and says on its face what the rail is narrowed to. */}
          <Box sx={{ display: setupMode ? "none" : "flex", alignItems: "center", minWidth: 0 }}>
            <FilterButton cat={cat} pick={pickerChannels.length ? pick : ""} channels={pickerChannels}
              srcByChannel={srcByChannel} srcQ={srcQ} setSrcQ={setSrcQ}
              onChange={(nextCat, nextPick) => {
                loadRequest.current += 1;
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
            <Typography variant="caption" noWrap data-tq-sync-line="" title={syncErr || (syncFailed.length ? `${syncFailed.join(", ")} could not be read - its card says why` : undefined)}
              sx={{ color: syncErr || (syncFailed.length && !(syncing || bgSync)) ? ALERT_INK : syncing || bgSync ? ACCENT : FAINT, fontSize: 10.5, flex: 1, minWidth: 0, textAlign: "right" }}>
              {syncErr ? `✗ ${syncErr}` : syncUnknown ? "Sync status unavailable — rechecking"
                : <NextIn atRef={nextAtRef} render={(nextIn) => syncFace({ busy: syncing || bgSync, what: syncWhat, every, lastAt: lastSync, nextIn, checked: true, started: syncStarted,
                    terse: !(syncing || bgSync), failed: syncFailed })} />}
            </Typography>
            <Button size="small" variant="text" disabled={!syncUnknown && (syncing || bgSync)} onClick={() => syncNow(false)}
              title={syncing || bgSync ? syncWhat : bHint("sync_now", syncUnknown ? "unknown" : undefined)}
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
              {syncUnknown ? bLabel("sync_now", "unknown") : syncing || bgSync ? syncPhaseLabel(syncPhase) : bLabel("sync_now")}
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
          {setupRail ? null : top}
        </Box>
        {bottomFade && more && (
          <Box data-tq-bottom-fade={fade} aria-hidden sx={{
            position: "absolute", left: "1px", right: "1px", bottom: "1px", zIndex: 6,
            height: bottomFade.height, pointerEvents: "none",
            background: `linear-gradient(transparent, ${PANEL} ${bottomFade.solidAt}%)`,
          }} />
        )}
      </Box>

      {/* ── the stage: the conversation, where every item opens as its card ────────── */}
      {/* a flex column so the chat can fill it; the canvas and the event panel size themselves to 100% */}
      {/* ONE CANVAS (the owner, 2026-10-20: "it should not take you there regardless"): this stage also drew a second view of a row -
          a Summary / Message / Triage / Agent panel with a tray of its own - that a #msg= link, a search hit or Task mode opened.
          Each of those roads now puts the item's own card on the canvas (canvasLinks: #msg=N is a pull of msg:N). */}
      <Box data-tq-keep data-tq-timeline-stage
        sx={{ minWidth: 0, minHeight: 0, display: stageShown ? "flex" : "none", flexDirection: "column", "& > *": { minHeight: 0 } }}>
        {visibleStage}
      </Box>

      <NewSheet open={newOpen} onClose={() => setNewOpen(false)} onOpenTask={onOpenTask}
        onDone={() => { load(); onChanged?.(); }} />
    </Box>
  );
}

