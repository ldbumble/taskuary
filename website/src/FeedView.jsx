// Timeline: left time rail, messages slide in as compact blurbs - who/where, the subject,
// and one plain sentence saying what the hub DID with it (routed where, drafted, filed,
// ignored) plus its current status. Hover or click a blurb for the whole story. Refreshes
// itself every 30s so new mail animates in while the tab is open.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Drawer, IconButton, ListSubheader, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import VolumeOffIcon from "@mui/icons-material/VolumeOff";
import api from "./api";
import EventIcon from "@mui/icons-material/Event";
import { pollWhileVisible } from "./visible.js";
import { feedHeaders, feedOk, takeFeed } from "./feedLoad.js";
import { ALERT, ALERT_INK, ROLES, PILL_COLORS, BG, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, card, frame, frameInner, hoverable, mono, fadeIn } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon, RefChip, ActionChip, ChoiceRow, ChoiceList, CoderReport, DiffBlock, Empty, FilterPills, ProofCard, SendToAgent, NotMine, fmtTime12, fmtDateTime, localDay, cleanText, splitQuoted, IDLE_WAITING, TellAgentButton, LiveConsole } from "./ui.jsx";
import { subjectOf, sourceOf } from "./feedText.js";

// Each filter carries a muted hue for its selected state: attention amber for needs-me,
// Outlook blue, Teams purple, quiet indigo for everything.
// Two different dimensions, two controls: WHAT STATE it's in (everything vs needs me)
// and WHICH CHANNEL it came from - they combine (e.g. "needs me" + "email").
// STATE dimension, so these do get semantic colour - "needs me" is the one filter on this
// screen that names something being on you.
const VIEW_FILTERS = [
  { key: "", label: "everything", c: PILL_COLORS.pick },
  { key: "pending", label: "needs me", c: PILL_COLORS.you },
];
// The pill row is a fixed set of CATEGORIES - it must not grow as connections do (a
// pill per mailbox, repo, channel and report would be unreadable by connection five).
// Everything narrower lives in one grouped picker: category -> channel -> connection.
const CATEGORIES = [
  { key: "", label: "everything", channels: null, c: PILL_COLORS.pick },
  { key: "messages", label: "messages", channels: ["email", "teams", "slack", "telegram", "whatsapp", "imessage", "discord"],
    c: PILL_COLORS.pick },
  { key: "code", label: "code", channels: ["github", "gitlab"], c: PILL_COLORS.pick },
  { key: "pm", label: "boards", channels: ["jira", "asana", "monday", "clickup", "todoist", "linear", "trello", "notion", "azdo"],
    c: PILL_COLORS.pick },
  { key: "alerts", label: "alerts", channels: ["sentry", "pagerduty"], c: PILL_COLORS.pick },
  { key: "cloud", label: "cloud", channels: ["aws", "azure"], c: PILL_COLORS.pick },
  { key: "reports", label: "reports", channels: ["report"], c: PILL_COLORS.pick },
];
const CHANNEL_LABELS = { email: "Mailboxes", teams: "Teams chats", slack: "Slack channels",
  telegram: "Telegram chats", whatsapp: "WhatsApp chats", imessage: "Apple Messages chats", discord: "Discord channels",
  github: "Repositories", gitlab: "GitLab instances", report: "Reports",
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
  if (r.Channel === "report") return "Scheduled report — hover to read the summary";
  if (r.MsgStatus === "feed") return "Shown for information — this connection is a feed, not a task trigger";
  if (r.MsgStatus === "triaging") return "On the timeline first — triage is deciding what it is";
  if (r.MsgStatus === "ignored") return `Ignored by policy — ${r.RouteReason || "no task created"}`;
  if (r.Category === "info") return `Info from a person, nothing to do — ${r.RouteReason || "informational"}`;
  if (r.Category === "promo") return `Promotional — a newsletter or marketing mail, nothing to do — ${r.RouteReason || ""}`;
  if (r.Category === "automated") return `Automated notice, nothing to do — ${r.RouteReason || ""}`;
  if (r.MsgStatus === "filed") return `Filed, nothing to do — ${r.RouteReason || "informational"}`;
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
  : r.Category === "info" ? "#6f8a6e"                      // a person told you something: worth the eye
  : ["ignored", "filed", "triaging"].includes(r.MsgStatus) ? "#cfc9bf"
    : r.ReviewStatus === "auto" || r.TaskStatus === "done" ? "#b8b2a9"
      : r.TaskId ? ACCENT2 : "#a7b0a8");

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
        <Typography variant="caption" sx={{ fontWeight: 700, color: "#5b5f97", fontSize: 11 }}>
          Next up {f.queued.length} {open ? "▾" : "▸"}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
          {f.working.slice(0, 4).map((w) => (
            <Box key={w.tid} sx={{ display: "inline-flex", alignItems: "center", gap: 0.4 }}>
              <Typography variant="caption" onClick={() => onOpenTask && onOpenTask(w.tid)} sx={{ ...{ fontFamily: "ui-monospace, monospace" }, color: "#47654a", fontSize: 10.5, fontWeight: 700, cursor: "pointer" }} title={w.title}>{w.ref}</Typography>
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
              <Typography variant="caption" sx={{ ...{ fontFamily: "ui-monospace, monospace" }, color: "#5b5f97", fontWeight: 700, width: 18, fontSize: 11 }}>{i + 1}</Typography>
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
  if (m < 0) return { text: "just ended", hot: false };
  if (m < 60) return { text: `in ${m} min`, hot: m <= 15 };
  if (m < 60 * 24) return { text: `in ${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`, hot: false };
  return { text: `in ${Math.round(m / 1440)} day${Math.round(m / 1440) === 1 ? "" : "s"}`, hot: false };
};
const ComingUp = () => {
  const [cal, setCal] = useState(null);
  const [tick, setTick] = useState(0);            // re-render every 30 s so the countdowns move
  useEffect(() => {
    let alive = true;
    const load = async () => { try { const { data } = await api.get("/api/calendar/upcoming", { params: { hours: 72 } }); if (alive) setCal(data); } catch { /* no calendar */ } };
    load();
    const a = setInterval(load, 300000), b = setInterval(() => setTick((t) => t + 1), 30000);
    return () => { alive = false; clearInterval(a); clearInterval(b); };
  }, []);
  if (!cal || !cal.events?.length) return null;
  return (
    <Box sx={{ mb: 0.5 }} data-tick={tick}>
      {cal.events.map((e, i) => {
        const u = untilText(e.start, e.end);
        return (
          <Box key={`${e.start}-${i}`} sx={{ display: "grid", gridTemplateColumns: `${GUTTER}px 14px minmax(0,1fr)`, alignItems: "stretch", mb: "4px" }}>
            <Typography sx={{ ...mono, fontSize: 10.5, color: "#8a7a5c", textAlign: "right", pt: "8px", pr: "11px", whiteSpace: "nowrap" }}>
              {e.all_day ? "all day" : fmtTime12(e.start)}
            </Typography>
            <Box sx={{ position: "relative" }}>
              <Box sx={{ position: "absolute", left: "6px", top: "-6px", bottom: "-6px", width: "1px", bgcolor: BORDER }} />
              <Box sx={{ position: "absolute", left: "2.5px", top: "11px", width: 8, height: 8, borderRadius: "50%", bgcolor: u.hot ? "#8a3646" : "#8a7a5c", boxShadow: `0 0 0 3.5px ${BG}` }} />
            </Box>
            <Box sx={{ bgcolor: "#f5f0e4", border: "1px solid #e3d9c2", borderRadius: "8px", px: "11px", py: "6px", minWidth: 0,
              display: "flex", gap: 0.85, alignItems: "center" }}>
              <EventIcon sx={{ fontSize: 16, color: "#8a7a5c", flexShrink: 0 }} />
              <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: INK, fontSize: 12.5, minWidth: 0 }}>{e.subject}</Typography>
              {e.where && <Typography variant="caption" noWrap sx={{ color: FAINT, maxWidth: 200 }}>· {e.where}</Typography>}
              {e.status === "tentative" && <Typography variant="caption" sx={{ color: FAINT }}>· tentative</Typography>}
              <Box sx={{ flex: 1 }} />
              <Typography variant="caption" sx={{ ...mono, fontSize: 10.5, fontWeight: 700, whiteSpace: "nowrap",
                color: u.hot ? "#fffdfb" : "#6b5f45", bgcolor: u.hot ? "#8a3646" : "#eee7d6", px: 0.8, py: 0.15, borderRadius: 99 }}>{u.text}</Typography>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};

export default function FeedView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [view, setView] = useState("");              // "" everything | "pending" needs me
  const [cat, setCat] = useState("");                // "" everything | messages | code | reports
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
    const chans = (CATEGORIES.find((x) => x.key === cat) || {}).channels;
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
  }, [view, cat, pick]);

  // Every channel is a CATEGORY; the picker next to it narrows to one actual connection —
  // this mailbox, this repo, this Slack channel, this report.
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => {
      const by = {};
      for (const s of data.data || []) {
        if (!s.Active) continue;
        const ch = s.Channel === "report" ? "report" : s.Channel;
        const name = s.Channel === "report" ? (JSON.parse(s.ConfigJson || "{}").title || s.Address) : s.Address;
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
  const syncNow = useCallback(async (silent) => {
    if (!silent) setSyncing(true);
    try { await api.post("/api/ingest/poll"); } catch { /* poll failures surface in Connectors */ }
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
    return pollWhileVisible(() => load(rowsLen.current), 30000);
  }, [load]);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => e.isIntersecting && loadMore());
    if (endRef.current) obs.observe(endRef.current);
    return () => obs.disconnect();
  }, [loadMore]);
  useEffect(() => { (rows || []).forEach((r) => seen.current.add(r.MessageId)); }, [rows]);

  // Hovering a line auto-opens it in the review panel (260ms intent delay so scrolling
  // doesn't thrash); click selects instantly. A draft mid-edit locks the panel in place.
  const [sel, setSel] = useState(null);
  const [sendErr, setSendErr] = useState("");     // approved, but the channel refused it
  const hoverTimer = useRef(null);
  const want = useRef(null);                    // newest selection wins if fetches land out of order
  const drill = async (row) => {
    setSel(row); setDetail(null); setEditText(null); setSendErr(""); setPanelLock(false); want.current = row.MessageId;
    // no task = report / filed / ignored: fetch the message itself so the panel shows the
    // WHOLE body (the feed row only carries a truncated preview)
    try {
      const d = row.TaskId ? (await api.get(`/api/tasks/${row.TaskId}`)).data
        : { messages: [(await api.get(`/api/messages/${row.MessageId}`)).data] };
      if (want.current === row.MessageId) setDetail(d);
    } catch {
      if (want.current === row.MessageId) setDetail({ messages: [] });   // panel falls back to the preview
    }
  };
  // A verdict being TYPED locks the panel the same way a draft does. It did not, and a sync
  // is when it hurts: rows arrive at the top every two seconds, the list slides under a
  // stationary cursor, hover selects whatever moved into place, and the panel - keyed on the
  // selected message - took the half-written "not our task" note down with it.
  const [panelLock, setPanelLock] = useState(false);
  const hoverSelect = (row) => {
    clearTimeout(hoverTimer.current);
    if (sel?.MessageId === row.MessageId) return;
    if (sel && ((editText ?? "").trim() || panelLock)) return;   // don't yank an OPEN panel mid-edit
    hoverTimer.current = setTimeout(() => drill(row), 260);
  };
  const hoverCancel = () => clearTimeout(hoverTimer.current);

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
  const catChans = (CATEGORIES.find((x) => x.key === cat) || {}).channels;
  const sorted = [...(rows || [])].filter((r) => !catChans || catChans.includes(r.Channel))
    .sort((a, b) => (b.SentAt || "").localeCompare(a.SentAt || ""));
  const days = sorted.reduce((acc, r) => {
    const d = localDay(r.SentAt) || "undated";
    (acc[d] = acc[d] || []).push(r);
    return acc;
  }, {});

  // only offer channels that actually have a connection behind them. With no category
  // picked, EVERY connected channel is offered - a hardcoded five-channel list here
  // silently hid telegram/whatsapp/jira/... sources from the picker as connectors grew
  const pickerChannels = ((CATEGORIES.find((x) => x.key === cat) || {}).channels
    || [...new Set([...CATEGORIES.flatMap((c) => c.channels || []), ...Object.keys(srcByChannel)])])
    .filter((ch) => (srcByChannel[ch] || []).length);

  const today = new Date().toLocaleDateString("sv-SE");
  const todays = (rows || []).filter((r) => localDay(r.SentAt) === today);
  const stats = [
    { label: "in today", n: todays.length, f: "" },
    { label: "auto", n: todays.filter((r) => r.ReviewStatus === "auto").length, f: "" },
    { label: "needs me", n: (rows || []).filter(needsYou).length, f: "pending", hot: true },
    { label: "info", n: todays.filter((r) => r.Category === "info").length, f: "" },
    { label: "promo", n: todays.filter((r) => r.Category === "promo").length, f: "" },
    { label: "ignored", n: todays.filter((r) => r.MsgStatus === "ignored").length, f: "" },
  ];

  return (
    // rowGap is tighter than columnGap on purpose: the stats caption already pads the
    // header's bottom edge, and a full 16px under it left the timeline floating loose
    <Box sx={{ display: "grid", columnGap: 2, rowGap: 0.75, alignItems: "start",
      // Both tracks are now FRACTIONS of the page, not fixed pixels centred in it. Capping the
      // timeline at 820px and centring the pair left a wide empty gutter down either side on
      // any real monitor, and squeezed the panel that has to hold a whole message plus the
      // draft. The timeline sits hard left, the panel takes a third, and the page is used.
      // 44% to the panel: a timeline row is one line of text and gains nothing past a readable
      // measure, while the panel holds a whole message, the draft and the action list - so the
      // width belongs there. The rows were running to 1100px of mostly empty middle.
      width: "100%",
      gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) minmax(520px, 44%)" } }}>
      {/* floating dock: one detached pill with Sync now DEAD-CENTER between the two filter
          groups, and the stats as a quiet caption line beneath. The old two-row toolbar
          card boxed the controls into the timeline column; the dock frees them to belong
          to the whole page. */}
      <Box sx={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", alignItems: "center", gap: 0.75 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap", justifyContent: "center",
          bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 99, px: 1.5, py: 0.6,
          boxShadow: "0 8px 28px rgba(30,50,38,.10)" }}>
          <FilterPills options={VIEW_FILTERS} value={view} onChange={setView} />
          <Box sx={{ width: "1px", height: 20, bgcolor: BORDER, flexShrink: 0 }} />
          {/* the label stays SHORT while it works: the "catching up on…" story lives in the
              caption line below, which exists for exactly that */}
          <Button size="small" variant="contained" disableElevation disabled={syncing || bgSync} onClick={() => syncNow(false)}
            title={syncing || bgSync ? syncWhat : undefined}
            startIcon={syncing || bgSync ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 14 }} />}
            sx={{ py: 0.4, fontSize: 11.5, whiteSpace: "nowrap", borderRadius: 99,
              background: "linear-gradient(90deg, #55697a, #7d9a7c)" }}>{syncing || bgSync ? "Syncing…" : "Sync now"}</Button>
          <Box sx={{ width: "1px", height: 20, bgcolor: BORDER, flexShrink: 0 }} />
          <FilterPills options={CATEGORIES} value={cat} onChange={setCat} />
          {pickerChannels.length > 0 && (
            <Select size="small" value={pick} displayEmpty onChange={(e) => setPick(e.target.value)}
              onClose={() => setSrcQ("")}
              MenuProps={{ PaperProps: { sx: { maxHeight: 440, maxWidth: 460 } } }}
              renderValue={(v) => (!v ? "all sources"
                : v.startsWith("channel:") ? `all ${CHANNEL_LABELS[v.slice(8)] || v.slice(8)}`.toLowerCase()
                  : String(v.split(":").slice(2).join(":")).split("@")[0])}
              sx={{ fontSize: 11.5, fontWeight: 600, borderRadius: 99, bgcolor: pick ? "#e3e6e1" : "#fff", height: 26,
                color: pick ? "#7c7367" : DIM, maxWidth: 210,
                "& .MuiSelect-select": { py: 0.3, px: 1.25 },
                "& .MuiOutlinedInput-notchedOutline": { borderColor: pick ? "#d2d6cf" : BORDER } }}>
              {/* 96 discovered buckets turned this into a page-long wall. It is a bounded,
                  searchable list now: type to narrow, and each channel shows a few with a
                  count for the rest rather than every object it has ever seen. */}
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
                // a channel whose name matches keeps its "all of them" row even when no
                // individual source does; one that matches nothing at all drops out
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
                    <MenuItem key={`${ch}:${n}`} value={`src:${ch}:${n}`}
                      sx={{ fontSize: 11.5, pl: 2.5, maxWidth: 420 }}>
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
          )}
        </Box>
        {/* the stats, demoted from tiles to a caption line - still clickable where a tile
            was ("needs me" filters), and the sync story rides the same line */}
        {rows && (
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 2, flexWrap: "wrap", justifyContent: "center" }}>
            {/* one face for the whole line: the mono digits next to Inter labels read as two
                different UIs stitched together - the numbers are just bolder Inter now */}
            {stats.map((s) => (
              <Box key={s.label} onClick={() => s.f && setView(s.f)}
                sx={{ display: "flex", alignItems: "baseline", gap: 0.6, cursor: s.f ? "pointer" : "default",
                  ...(s.f ? { "&:hover .thubStatLbl": { color: "#55697a" } } : {}) }}>
                <Typography sx={{ fontWeight: 800, fontSize: 12.5,
                  color: s.hot && s.n ? ALERT : s.n ? "#55697a" : INK }}>{s.n}</Typography>
                <Typography className="thubStatLbl" variant="caption" sx={{ color: FAINT, transition: "color .15s" }}>{s.label}</Typography>
              </Box>
            ))}
            <Typography variant="caption" noWrap sx={{ color: syncing || bgSync ? "#55697a" : FAINT }}>
              {syncing || bgSync ? `· ${syncWhat || "syncing…"}`
                : lastSync
                  ? `· last sync ${lastSync.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`
                  : every ? `· auto-syncs every ${every} min` : "· background sync is off (Settings)"}
            </Typography>
          </Box>
        )}
        {/* the failure belongs to the dock, not the timeline column: a full-width slab
            left of a centered header read as a stray banner. Shrink-to-fit pill, same
            radius/shadow as the dock above it, and it OFFERS the retry instead of
            leaving a dead spinner spinning underneath. */}
        {err && (
          <Alert severity="error" variant="outlined" onClose={() => setErr("")}
            action={<Button size="small" color="error" onClick={() => { setErr(""); setRows(null); load(rowsLen.current); }}
              sx={{ fontSize: 11.5, borderRadius: 99 }}>Retry</Button>}
            sx={{ py: 0.1, borderRadius: 99, bgcolor: PANEL, alignItems: "center", boxShadow: "0 8px 28px rgba(30,50,38,.10)",
              "& .MuiAlert-message": { fontSize: 12.5, py: 0.75 }, "& .MuiAlert-action": { pt: 0, alignItems: "center" } }}>
            {err}
          </Alert>
        )}
      </Box>
      <FunnelBar onOpenTask={onOpenTask} />
      {/* timeline column: grid's minmax(0,...) hard-caps both tracks, so the panel can
          never spill past the viewport and the list keeps its layout */}
      <Box sx={{ minWidth: 0 }}>
        {/* syncing = the TIMELINE is loading, so the timeline says so: rows dim and a
            spinner sits on the list itself - the old 3px bar over just the left column
            read as a broken artifact, not a state */}
        <Box sx={{ position: "relative", opacity: syncing ? 0.55 : 1, transition: "opacity .25s" }}>
          {syncing && (
            <Box sx={{ position: "absolute", inset: 0, zIndex: 4, display: "flex",
              alignItems: "flex-start", justifyContent: "center", pointerEvents: "none" }}>
              <CircularProgress size={26} sx={{ mt: 14 }} />
            </Box>
          )}
          {!rows ? (err ? null : <CircularProgress size={22} sx={{ m: 4 }} />) : !rows.length ? (
            // the empty line has to know WHY it is empty: "activate a mailbox" under the
            // code filter told someone with three mailboxes to add a fourth
            <Empty>{view || cat || pick
              ? "Nothing here matches this filter — try “everything”, or widen the Timeline lookback in Settings."
              : "Nothing in the feed yet — connect a source in Connectors (a mailbox, a chat, a repo, a board…) and hit Sync now."}</Empty>
          ) : Object.entries(days).map(([day, items], di) => (
            <Box key={day} sx={{ mt: 1 }}>
              <DayHeader label={fmtDay(day)} />
              {di === 0 && !cat && !pick && <ComingUp onOpen={() => {}} />}
              <Box>
                {items.map((r, i) => (
                  <React.Fragment key={r.MessageId}>
                    <Box sx={{ display: "grid", gridTemplateColumns: `${GUTTER}px 14px minmax(0,1fr)`,
                      alignItems: "stretch", mb: "4px",
                      ...(seen.current.has(r.MessageId) ? {} : { ...fadeIn, animationDelay: `${Math.min(i * 45, 400)}ms` }) }}>
                      {/* time sits OUTSIDE the card, in its own gutter - wide enough that
                          "12:40 PM" can never wrap onto a second line */}
                      <Typography sx={{ ...mono, fontSize: 10.5, color: "#6e685f", textAlign: "right",
                        pt: "8px", pr: "11px", whiteSpace: "nowrap", letterSpacing: "-.2px" }}>
                        {fmtTime12(r.SentAt)}
                      </Typography>
                      {/* rail + dot: the dot carries STATE, not channel - the icon already says
                          where it came from, and three encodings of one fact read as noise */}
                      <Box sx={{ position: "relative" }}>
                        <Box sx={{ position: "absolute", left: "6px", top: "-6px", bottom: "-6px", width: "1px", bgcolor: BORDER }} />
                        <Box sx={{ position: "absolute", left: "2.5px", top: "11px", width: 8, height: 8, borderRadius: "50%",
                          bgcolor: dotOf(r), boxShadow: `0 0 0 3.5px ${BG}` }} />
                      </Box>
                      {/* one DEFINED object per message: who and what on top, what the hub did
                          underneath. Hover adds the message gist; click opens the panel. */}
                      <Box onClick={() => drill(r)} onMouseEnter={() => hoverSelect(r)} onMouseLeave={hoverCancel}
                        sx={{ bgcolor: ["ignored", "filed"].includes(r.MsgStatus) ? "#faf8f4" : PANEL,
                          border: `1px solid ${BORDER}`, borderRadius: "8px", px: "11px", pt: "5px", pb: "6px",
                          minWidth: 0, overflow: "hidden",
                          transition: "box-shadow .18s, border-color .18s",
                          ...(sel?.MessageId === r.MessageId
                            ? { borderColor: "#d8cfbe", boxShadow: "inset 2px 0 0 #55697a, 0 1px 3px rgba(30,50,38,.07)",
                                "& .thubDetail": { gridTemplateRows: "1fr" }, "& .thubDetailText": { opacity: 1 } } : {}),
                          "&:hover": { borderColor: "#d8cfbe", boxShadow: "0 2px 8px rgba(47,107,79,.10)", cursor: "pointer" },
                          "&:hover .thubDetail": { gridTemplateRows: "1fr" },
                          "&:hover .thubDetailText": { opacity: 1 },
                          "&:hover .thubGo": { opacity: 1, transform: "translateX(0)" } }}>
                        <Box sx={{ display: "flex", gap: 0.85, alignItems: "baseline", minWidth: 0 }}>
                          <Box sx={{ alignSelf: "center", display: "flex", flexShrink: 0 }}>
                            <ChannelIcon channel={r.Channel} sx={{ fontSize: 17 }} />
                          </Box>
                          <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: ["ignored", "filed"].includes(r.MsgStatus) ? DIM : INK,
                            fontSize: 12.5, letterSpacing: "-.1px", maxWidth: { sm: 200 }, minWidth: 0, flexShrink: { xs: 1, sm: 0 } }}>
                            {r.FromName || r.FromEmail || "unknown"}
                          </Typography>
                          {sourceOf(r) && <Typography variant="caption" noWrap sx={{ color: FAINT, maxWidth: 140, flexShrink: 0 }}>· {sourceOf(r)}</Typography>}
                          <Typography variant="body2" noWrap sx={{ color: DIM, fontSize: 12.5, flex: 1, minWidth: 0,
                            display: { xs: "none", sm: "block" } }}>{subjectOf(r) || ""}</Typography>
                          <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexShrink: 0 }}>
                            {r.Attachments > 0 && (
                              <Typography variant="caption" title={`${r.Attachments} attached`}
                                sx={{ color: FAINT, display: "flex", alignItems: "center", fontSize: 10.5 }}>
                                <AttachFileIcon sx={{ fontSize: 13 }} />{r.Attachments > 1 ? r.Attachments : ""}
                              </Typography>
                            )}
                            <RefChip taskId={r.TaskId} onClick={(e) => { e.stopPropagation(); onOpenTask(r.TaskId); }} />
                            {/* which way the work went. Without it "sent to Dana" and "received
                                from Dana" are the same row, and the funnel only ever looked one way. */}
                            {r.Direction === "out" && (
                              <Chip size="small" label="out" title="Taskuary sent this"
                                sx={{ height: 19, fontSize: 10.5, fontWeight: 700, bgcolor: "#eae4d8", color: "#55697a" }} />
                            )}
                            <ActionChip action={actionOf(r)} category={r.Category} working={r.Working} reviewStatus={r.ReviewStatus} taskStatus={r.TaskStatus} needsYou={needsYou(r)} />
                            <ChevronRightIcon className="thubGo" sx={{ fontSize: 16, color: "#55697a",
                              opacity: sel?.MessageId === r.MessageId ? 1 : 0,
                              transform: sel?.MessageId === r.MessageId ? "translateX(0)" : "translateX(-6px)",
                              transition: "opacity .18s, transform .18s" }} />
                          </Box>
                        </Box>
                        {/* ONE line per message. A timeline is for scanning, and the second line
                            was costing about a third of the items on a screen - which is the whole
                            job of this tab. The blurb and the gist ride in on hover and stay open
                            on the selected row; the panel spells the verdict out in full either way. */}
                        <Box className="thubDetail" sx={{ display: "grid", gridTemplateRows: "0fr", transition: "grid-template-rows .22s ease" }}>
                          <Box sx={{ overflow: "hidden" }}>
                            <Typography className="thubDetailText" noWrap
                              sx={{ fontSize: 11, lineHeight: 1.35, pt: "3px", opacity: 0, transition: "opacity .22s ease .05s",
                                color: needsYou(r) ? ALERT_INK : "#867f74" }}>{blurb(r)}</Typography>
                            {r.Preview && (
                              <Typography className="thubDetailText" variant="caption" noWrap
                                sx={{ display: "block", color: INK, pt: "3px", opacity: 0, transition: "opacity .22s ease .05s" }}>
                                “{r.Preview}”
                              </Typography>
                            )}
                          </Box>
                        </Box>
                      </Box>
                    </Box>
                  </React.Fragment>
                ))}
              </Box>
            </Box>
          ))}
          {/* infinite-scroll sentinel: crossing it loads the next page */}
          <Box ref={endRef} sx={{ height: 8 }} />
          {rows && rows.length > 0 && !noMore && <CircularProgress size={16} sx={{ display: "block", mx: "auto", my: 1 }} />}
        </Box>
      </Box>

      {/* ── review panel: pinned to the top of whatever is currently visible. The column
          MUST stretch the full grid height - sticky needs that track to slide in (a
          content-height column leaves sticky stranded at the page top). ── */}
      {sel && (
        // pushed DOWN so the panel's top edge lines up with the first timeline card (past
        // the day-group margin + day header + row margin ≈ 44px), instead of floating
        // above the list it annotates. Sticky still takes over once you scroll.
        <Box sx={{ minWidth: 0, display: { xs: "none", md: "block" }, alignSelf: "stretch", mt: "34px" }}>
          <Box sx={{ position: "sticky", top: 62 }}>
            <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText}
              decide={decide} onOpenTask={onOpenTask} onClose={() => setSel(null)}
              onSkipped={() => { setSel(null); load(); onChanged?.(); }} onRefresh={() => load()}
              sendErr={sendErr} clearSendErr={() => setSendErr("")} onLock={setPanelLock} />
          </Box>
        </Box>
      )}
    </Box>
  );
}

// Day rail label: "Today · Friday, Aug 14" / "Yesterday · ..." / "Thursday, Aug 13".
const fmtDay = (d) => {
  if (d === "undated") return "undated";
  const nice = new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
  const today = new Date(); const yest = new Date(Date.now() - 864e5);
  if (d === today.toLocaleDateString("sv-SE")) return `Today · ${nice}`;
  if (d === yest.toLocaleDateString("sv-SE")) return `Yesterday · ${nice}`;
  return nice;
};

// Compact what-happened rail: opened -> routed -> agent runs -> decisions -> closed,
// oldest first, with consecutive duplicates collapsed into one row with a ×N count.
const historyOf = (sel, detail) => {
  const ev = [];
  if (detail?.task) ev.push({ at: detail.task.CreatedAt, label: `Task ${detail.ref} opened`, sub: detail.task.Kind, c: "#55697a" });
  (detail?.routes || []).forEach((r) => ev.push({ at: detail.task?.CreatedAt, c: "#6f8a6e",
    label: r.Decision === "attach" ? "Routed — attached to this thread"
      : r.Decision === "create" ? "Routed — new task created" : `Routed — ${r.Decision}` }));
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

const PanelLabel = ({ children }) => (
  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.8, fontSize: 10, fontWeight: 700,
    display: "block", mt: 1.75, mb: 0.25 }}>
    {children}
  </Typography>
);

// The pop-out review panel: everything about the selected line, editable and decidable
// without leaving the page. All text hard-left-aligned.
const ReviewCanvas = ({ sel, detail, editText, setEditText, decide, onOpenTask, onClose, onSkipped, onRefresh,
                        sendErr, clearSendErr, onLock }) => {
  // one click turns a flood sender (100s of automated mails) into a skip policy - their
  // mail is deduped but never shows on the timeline again, and their HISTORY goes with it
  const [skipped, setSkipped] = useState(null);
  // you usually realise it is somebody else's job while reading it here, not after opening
  // the Tasks tab - so the hand-off form opens in this panel too
  const [handoff, setHandoff] = useState(false);
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
  // "type their answer into the working session" - the round trip's last leg (answer_to_agent=ask)
  const [handed, setHanded] = useState(false);
  const handToAgent = async () => {
    try { await api.post(`/api/tasks/${sel.TaskId}/answer`, { message_id: sel.MessageId }); setHanded(true); }
    catch { /* session gone between render and click: the row's hint still points at the task */ }
  };
  useEffect(() => { setHandoff(false); setReshape(false); setOpened(null); setOpening(false); setHanded(false); }, [sel.MessageId]);
  const skipSender = async () => {
    const { data } = await api.post("/api/policies", { Name: `skip:${sel.FromEmail}`, Kind: "sender", Pattern: sel.FromEmail,
      Action: "skip", Reason: "flood sender — skipped from the timeline", SortOrder: 10, Active: true });
    setSkipped(data.affected || 0);
    setTimeout(() => onSkipped?.(), 1400);          // let the count land, then drop the rows
  };
  const rep = [...(detail?.comments || [])].reverse().find((c) => c.Actor === "coder" && String(c.Body || "").startsWith("CODER REPORT"));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const pending = sel.ReviewId && sel.ReviewStatus === "pending";
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
    const poll = async () => { try { const { data } = await api.get("/api/runs/live", { params: { lines: 6 } }); if (alive) setLiveRow((data.data || []).find((r) => r.TaskId === sel.TaskId) || null); } catch { /* keep the last */ } };
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
  return (
    <Box key={sel.MessageId} sx={{ ...frame, textAlign: "left",
      // grows out of the clicked blurb: slides rightward from the row and scales up
      "@keyframes thubGrow": { from: { opacity: 0, transform: "translateX(-32px) scale(.965)" },
        to: { opacity: 1, transform: "none" } },
      animation: "thubGrow .3s cubic-bezier(.2,.8,.3,1) both", transformOrigin: "left center" }}>
      <Box sx={{ ...frameInner, display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 108px)" }}>
        {/* header */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.25, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
          <ChevronRightIcon sx={{ fontSize: 17, color: "#55697a" }} />
          <ChannelIcon channel={sel.Channel} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ color: INK, fontWeight: 700, fontSize: 13.5, lineHeight: 1.25, textAlign: "left" }} noWrap>
              {sel.Subject || `${sel.FromName || sel.FromEmail} in ${sel.SourceName || "chat"}`}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", textAlign: "left" }} noWrap>
              {sel.FromName || sel.FromEmail}{sel.SourceName ? ` · ${sel.SourceName}` : ""} · {fmtDateTime(sel.SentAt)}
            </Typography>
          </Box>
          <RefChip taskId={sel.TaskId} onClick={() => onOpenTask(sel.TaskId)} />
          <ActionChip action={actionOf(sel)} category={sel.Category} working={sel.Working} reviewStatus={sel.ReviewStatus} taskStatus={sel.TaskStatus} needsYou={needsYou(sel)} />
          <IconButton size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
        </Box>

        <Box sx={{ px: 2, py: 1.5, overflowY: "auto", textAlign: "left", flex: 1, minHeight: 150 }}>
          {loading ? <CircularProgress size={20} sx={{ m: 2 }} /> : (
            <>
              {/* the router's verdict, verbatim - triage is inspectable, not a vibe: the route
                  reason carries "triage: <verdict> - <why>" straight from the classifier */}
              {sel.RouteReason && (
                <Typography variant="caption" sx={{ display: "block", color: FAINT, mb: 1.25,
                  bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1, px: 1, py: 0.5 }}>
                  <Box component="b" sx={{ color: DIM }}>Why it's here:</Box> {sel.RouteReason}
                </Typography>
              )}
              <PanelLabel>{(detail?.messages || []).length > 1 ? `Emails in this chain (${detail.messages.length})` : "Message"}</PanelLabel>
              <MessageBlock key={sel.MessageId} messages={detail?.messages} focusId={sel.MessageId} fallback={sel.Preview} />

              {rep && (
                <>
                  <PanelLabel>What the coder did</PanelLabel>
                  <Box sx={{ bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.5 }}>
                    <CoderReport body={rep.Body} />
                  </Box>
                </>
              )}
              {/* the report above is the agent's CLAIM; this is the evidence - files git
                  says moved, the tests the session ran, CI on the PR, and what is missing */}
              {sel.TaskId && (rep || diffRun) && (
                <>
                  <PanelLabel>Proof of work</PanelLabel>
                  <ProofCard taskId={sel.TaskId} onOpenTask={onOpenTask} />
                </>
              )}

              {diffRun && (
                <>
                  <PanelLabel>Code changes</PanelLabel>
                  <DiffBlock text={diffRun.DiffText} />
                </>
              )}

              {history.length > 0 && (
                <>
                  <PanelLabel>History</PanelLabel>
                  <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.25, py: 0.25 }}>
                    {history.map((h, i) => (
                      <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.6,
                        borderTop: i ? `1px solid ${BORDER}` : "none" }}>
                        <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: h.c, flexShrink: 0 }} />
                        <Typography variant="caption" sx={{ color: INK, fontWeight: 600, flexShrink: 0 }}>{h.label}</Typography>
                        {h.sub ? <Typography variant="caption" sx={{ color: DIM, flex: 1, minWidth: 0 }} noWrap>{h.sub}</Typography> : <Box sx={{ flex: 1 }} />}
                        {h.n > 1 && <Chip size="small" label={`×${h.n}`} sx={{ height: 16, fontSize: 9.5, bgcolor: "#eae4d8", color: "#55697a" }} />}
                        {h.at && <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 9.5, flexShrink: 0 }}>{fmtDateTime(h.at)}</Typography>}
                      </Box>
                    ))}
                  </Box>
                </>
              )}

              {pending && (
                <>
                  <PanelLabel>Draft reply — review, edit, approve</PanelLabel>
                  <ReviewActions reviewId={sel.ReviewId} draft={pendingDraft(detail || { runs: [] }, sel)}
                    editText={editText} setEditText={setEditText} decide={decide}
                    sendErr={sendErr} clearSendErr={clearSendErr} canSend={sel.CanSend} />
                </>
              )}
              {/* no reply on the table (the coder ran, or triage filed it) - put one there. The
                  box was simply UNREACHABLE from here before: nothing pending meant no way to
                  answer at all. */}
              {!pending && opened && (
                <>
                  <PanelLabel>Draft reply — review, edit, approve</PanelLabel>
                  <ReviewActions reviewId={opened.reviewId} draft={opened.draft}
                    editText={editText} setEditText={setEditText} decide={decide}
                    sendErr={sendErr} clearSendErr={clearSendErr} canSend={sel.CanSend} />
                </>
              )}
              {!pending && !opened && sel.Channel !== "report" && (
                <ChoiceRow tint="#eae4d8" busy={opening} onClick={openReply}
                  icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                  label="Reply to this"
                  hint="the AI drafts it from the thread (and the coder's report, if one ran) — approving sends" />
              )}

            </>
          )}
        </Box>

        {/* pinned: whatever the message does, the four options are on screen */}
        {!loading && (
          <Box sx={{ flexShrink: 0, borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2, px: 2, pt: 0.25, pb: 1.25 }}>
          {/* These were four buttons in two rows, four sizes, two right-aligned - so "what are
              my options" needed a hunt, and a long message pushed the fourth off-screen. */}
            <PanelLabel>What should happen with this?</PanelLabel>
            <ChoiceList>
              {onIt ? (
                <Box sx={{ width: "100%", p: 1, bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}`, display: "flex", flexDirection: "column", gap: 1 }}>
                  {/* the black console: the agent's own last lines, live - the same peephole the Board
                      cards wear, so "working this now" is something you watch, not read */}
                  <LiveConsole run={liveRow} agent={onIt.agent} onOpen={() => onOpenTask(sel.TaskId)} />
                </Box>
              ) : !codeless ? (
                <SendToAgent row first messageId={sel.MessageId} subject={sel.Subject} onOpenTask={onOpenTask} />
              ) : null}
              {/* the agent asked, the person answered on the thread - one click puts the
                  answer in front of the agent (Settings → answer_to_agent; auto skips the click) */}
              {onIt && sel.MessageId && (
                <ChoiceRow tint="#e3e6e1" busy={handed} onClick={handToAgent}
                  icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: "#6f8a6e" }} />}
                  label={handed ? "Answer typed into the session" : `Type this into ${onIt.agent}'s session`}
                  hint={handed ? "the agent has it — watch it continue on the task" : "their message is typed into the live session, as if you relayed it"} />
              )}
              {sel.TaskId ? (
                <ChoiceRow tint="#eae4d8" onClick={() => onOpenTask(sel.TaskId)}
                  icon={<OpenInFullIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                  label={`Open task ${ref(sel.TaskId)}`} hint="the whole story: session, report, history" />
              ) : (
                <MineToDo messageId={sel.MessageId} onMade={() => onRefresh?.()} />
              )}
              {sel.TaskId && (
                <ChoiceRow tint="#eae4d8" onClick={() => setHandoff((h) => !h)}
                  icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                  label="Hand it to a person" hint="not ours to do — the AI writes the forward, you send it" />
              )}
              {/* under the row that OPENED it. It used to render after the whole list, past the
                  drawer, so clicking a button near the top scrolled a tray in at the bottom with
                  nothing connecting the two - and every other tray here expands in place. */}
              {handoff && sel.TaskId && (
                <Box sx={{ width: "100%", bgcolor: PANEL2, borderTop: `1px solid ${BORDER}`, px: 1.25, py: 1 }}>
                  <PanelLabel>Hand this to a person</PanelLabel>
                  <Handoff taskId={sel.TaskId} onSent={() => onRefresh?.()} />
                </Box>
              )}
              {/* the default is the agent - everything that is work goes to it - so the exception is
                  the button: real work, not for the coder. The task stays on your list and the
                  verdict is remembered for the next message like it. */}
              {sel.TaskId && (
                <ChoiceRow tint="#eee7d6" onClick={async () => { await api.post(`/api/tasks/${sel.TaskId}/not-coding`); onRefresh?.(); }}
                  icon={<CloseIcon sx={{ fontSize: 14, color: "#8a7a5c" }} />}
                  label="Not a coding task" hint={`keep ${ref(sel.TaskId)} on your list, take the agent off it — and remember that for mail like this`} />
              )}
              <SplitTask row={sel} onSplit={() => onRefresh?.()} />
              {sel.TaskId && (
                <ChoiceRow tint="#e3e6e1" onClick={() => setReshape(true)}
                  icon={<CallSplitIcon sx={{ fontSize: 14, color: "#6f8a6e" }} />}
                  label="Two jobs in here, or a duplicate?"
                  hint={`break ${ref(sel.TaskId)} in two, or fold it into the task it repeats`} />
              )}
              {/* a chat about someone's job is not a coding job. Triage already said so, and
                  leading with "send it to a coding agent" argued with its own verdict - the
                  offer stays available, it just stops being the first thing you reach for */}
              {codeless && !onIt && (
                <SendToAgent row messageId={sel.MessageId} subject={sel.Subject} onOpenTask={onOpenTask} />
              )}
              {/* THE HARMLESS EXIT, and it used to be missing whenever there was no task: the
                  only way off the timeline was "Not our task", which writes a verdict against
                  the sender - or against EVERY sender on a channel with no address, like Teams.
                  One wrong click there teaches the funnel to stop listening to a colleague. */}
              <ChoiceRow tint="#e9e3d8" onClick={async () => {
                  await api.post(`/api/messages/${sel.MessageId}/file`);
                  onSkipped?.();
                }}
                icon={<CloseIcon sx={{ fontSize: 14, color: "#5e685f" }} />}
                label={sel.TaskId ? "Not a task — just conversation" : "Nothing to do here"}
                hint={sel.TaskId ? `delete ${ref(sel.TaskId)} and file the rest of this conversation; nothing is learned about the sender`
                                 : "file it and the rest of this conversation — nothing is learned about the sender or the topic"} />
              {/* not ours -> the reason goes to memory, and triage reads it next time. Below the
                  harmless one on purpose: this is the durable verdict, not the tidy-up. */}
              <NotMine row messageId={sel.MessageId} onDone={onSkipped} onLock={onLock} />
              {sel.Channel === "email" && sel.FromEmail && (skipped !== null ? (
                <ChoiceRow tint="#dfeade" busy
                  icon={<VolumeOffIcon sx={{ fontSize: 14, color: "#47654a" }} />}
                  label="Sender skipped"
                  hint={skipped ? `${skipped} past message${skipped === 1 ? "" : "s"} hidden too` : "they will not appear again"} />
              ) : (
                <ChoiceRow tint="#e9e3d8" onClick={skipSender}
                  icon={<VolumeOffIcon sx={{ fontSize: 14, color: "#867f74" }} />}
                  label="Skip this sender" hint={`hide ${sel.FromEmail} and their past mail — undo in Settings`} />
              ))}
            </ChoiceList>

            <Drawer anchor="right" open={!!reshape && !!sel.TaskId} onClose={() => setReshape(false)}
              PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <CallSplitIcon sx={{ fontSize: 18, color: "#6f8a6e" }} />
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

// Sticky day rail that POPS into a pill the moment you scroll past its date boundary -
// a 1px sentinel above it leaves the viewport exactly when the header becomes stuck.
const DayHeader = ({ label }) => {
  const [stuck, setStuck] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), { threshold: 0 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return (
    <>
      <Box ref={ref} sx={{ height: "1px" }} />
      <Box sx={{ position: "sticky", top: 0, zIndex: 3, py: 0.75, display: "flex", justifyContent: "center" }}>
        <Box sx={{ display: "inline-block", px: stuck ? 1.75 : 1.25, py: stuck ? 0.5 : 0.25,
          bgcolor: stuck ? PANEL : BG, border: `1px solid ${stuck ? BORDER : "transparent"}`,
          borderRadius: 99, boxShadow: stuck ? "0 6px 18px rgba(30,50,38,.14)" : "none",
          transform: stuck ? "scale(1.12)" : "scale(1)", transformOrigin: "center",
          transition: "all .25s cubic-bezier(.34,1.56,.64,1)" }}>
          <Typography variant="caption" sx={{ ...mono, color: stuck ? "#55697a" : INK, fontWeight: 800,
            fontSize: 11.5, letterSpacing: 0.5 }}>
            {label}
          </Typography>
        </Box>
      </Box>
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
  return (
    <>
      {msgs.length > 1 && (
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 0.75 }}>
          {msgs.map((m) => {
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
            <Chip size="small" label={you ? "↩ your reply" : "inbound"}
              sx={{ height: 17, fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                bgcolor: you ? ROLES.working.tint : ROLES.muted.tint,
                color: you ? ROLES.working.ink : ROLES.muted.ink }} />
            <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>
              {you ? "you" : cur.FromName || cur.FromEmail || "unknown"}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>· {fmtDateTime(cur.SentAt)}</Typography>
            {quoted && <Typography variant="caption" sx={{ color: FAINT }}>· replying on this thread</Typography>}
          </Box>
        )}
        {cur?.Channel === "report" ? <SectionedText text={text} />
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

// The pending draft text for this message's review - stored on the review row; a
// responder run's result is the fallback for drafts written before that column existed.
const pendingDraft = (detail, open) => {
  const rv = (detail.reviews || []).find((r) => r.ReviewId === open.ReviewId);
  if (rv?.DraftText) return rv.DraftText;
  const run = (detail.runs || []).find((r) => r.AgentName === "responder" && r.Status === "done");
  return run?.Result || "";
};

// Two asks arriving in one chat thread are one conversation but two jobs - and an agent
// sent at the task only ever receives the first one's prompt.
// Not everything a person has to do is an agent's job: approve the workflow in ADP, click the
// thing in the portal. That is still work, and filing it as "nothing to do" is a lie - so it
// becomes a task with YOUR name on it and no agent sent at it. (A computer-use connector would
// take its queue from exactly here.)
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

const SplitTask = ({ row, onSplit }) => {
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
  return (
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
