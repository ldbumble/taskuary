// Timeline: left time rail, messages slide in as compact blurbs - who/where, the subject,
// and one plain sentence saying what the hub DID with it (routed where, drafted, filed,
// ignored) plus its current status. Hover or click a blurb for the whole story. Refreshes
// itself every 30s so new mail animates in while the tab is open.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Drawer, IconButton, LinearProgress, ListSubheader, MenuItem, Select, TextField, Typography,
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
import { BG, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, frame, frameInner, hoverable, mono, fadeIn } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon, CHANNEL_COLORS, RefChip, ActionChip, ChoiceRow, ChoiceList, CoderReport, DiffBlock, Empty, FilterPills, SendToAgent, NotMine, fmtTime12, fmtDateTime, localDay, cleanText, splitQuoted, IDLE_WAITING } from "./ui.jsx";

// Each filter carries a muted hue for its selected state: attention amber for needs-me,
// Outlook blue, Teams purple, quiet indigo for everything.
// Two different dimensions, two controls: WHAT STATE it's in (everything vs needs me)
// and WHICH CHANNEL it came from - they combine (e.g. "needs me" + "email").
const VIEW_FILTERS = [
  { key: "", label: "everything", c: { bg: "#eef0ff", fg: "#4f46e5", bd: "#c9cff0" } },
  { key: "pending", label: "needs me", c: { bg: "#fef4e6", fg: "#b45309", bd: "#f3ddb8" } },
];
// The pill row is a fixed set of CATEGORIES - it must not grow as connections do (a
// pill per mailbox, repo, channel and report would be unreadable by connection five).
// Everything narrower lives in one grouped picker: category -> channel -> connection.
const CATEGORIES = [
  { key: "", label: "everything", channels: null },
  { key: "messages", label: "messages", channels: ["email", "teams", "slack", "telegram", "whatsapp"],
    c: { bg: "#e8f1fa", fg: "#0F6CBD", bd: "#c4dcf2" } },
  { key: "code", label: "code", channels: ["github"], c: { bg: "#eceef1", fg: "#1c2536", bd: "#d3d8e0" } },
  { key: "reports", label: "reports", channels: ["report"], c: { bg: "#e6f7fb", fg: "#0e7490", bd: "#c2e7f0" } },
];
const CHANNEL_LABELS = { email: "Mailboxes", teams: "Teams chats", slack: "Slack channels",
  telegram: "Telegram chats", whatsapp: "WhatsApp chats", github: "Repositories", report: "Reports" };

const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;

// What the row is, for the chip. A scheduled report or a feed-only connection's item was
// never judged - it is information. Only a policy 'ignore' is a verdict.
const actionOf = (r) => (r.Channel === "report" ? "report"
  : r.MsgStatus === "feed" ? "feed"
    : r.MsgStatus === "ignored" ? "ignore"
      : r.MsgStatus === "filed" ? "filed"
        : r.ReviewKind === "auto" ? "auto"
          : r.ReviewId ? "draft" : "task_only");

// NeedsYou comes from the server and means one thing: nobody else is moving this. It
// outranks the verdict chip, because "what happened to it" matters less than "is it mine".
const needsYou = (r) => !!r.NeedsYou && r.TaskStatus !== "done";

// Teams chats get a synthesized "<sender> in <source>" subject - redundant next to the
// sender + source we already show, so drop it.
const subjectOf = (r) => {
  const s = r.Subject || "";
  return s === `${r.FromName} in ${r.SourceName}` ? "" : s;
};

// One plain-English sentence: what the hub did + where it stands.
const blurb = (r) => {
  if ((r.RouteReason || "").includes("your reply") || (r.RouteReason || "").includes("your sent reply"))
    return r.TaskId ? `Your reply — kept on ${ref(r.TaskId)} so the thread shows both sides` : "Your reply — kept for context, never a task";
  if (r.Channel === "report") return "Scheduled report — hover to read the summary";
  if (r.MsgStatus === "feed") return "Shown for information — this connection is a feed, not a task trigger";
  if (r.MsgStatus === "ignored") return `Ignored by policy — ${r.RouteReason || "no task created"}`;
  if (r.MsgStatus === "filed") return `Filed, nothing to do — ${r.RouteReason || "informational"}`;
  const routed = r.Decision === "attach" ? `Added to ${ref(r.TaskId)} (existing thread)` : `New task ${ref(r.TaskId)} created`;
  const state = r.ReviewStatus === "pending" ? "a reply is drafted — waiting on your review"
      : r.ReviewStatus === "auto" ? "AI answered automatically"
        : r.TaskStatus === "done" ? `completed${r.ReviewStatus ? ` · you said ${r.ReviewStatus.replace("_", " ")}` : ""}`
          : needsYou(r) ? "needs you — no agent is working it right now"
            : r.ReviewStatus ? `reviewed (${r.ReviewStatus})` : "an agent is working it";
  return `${routed} · ${state}`;
};

const PAGE = 100;

export default function FeedView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [view, setView] = useState("");              // "" everything | "pending" needs me
  const [cat, setCat] = useState("");                // "" everything | messages | code | reports
  const [pick, setPick] = useState("");              // "" all in category | "channel:x" | "src:channel:name"
  const [srcByChannel, setSrcByChannel] = useState({});   // channel -> connection names
  const [noMore, setNoMore] = useState(false);
  const [detail, setDetail] = useState(null);
  const [editText, setEditText] = useState(null);    // null = untouched; "" = deliberately cleared
  const [err, setErr] = useState("");
  const seen = useRef(new Set());               // MessageIds already animated in
  const rowsLen = useRef(0);
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
      const { data } = await api.get("/api/feed", { params: { limit, ...fparams() } });
      const batch = data.data || [];
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
  const syncNow = useCallback(async (silent) => {
    if (!silent) setSyncing(true);
    try { await api.post("/api/ingest/poll"); } catch { /* poll failures surface in Connectors */ }
    const t0 = Date.now();
    const settle = async () => { await load(rowsLen.current); setSyncing(false); setLastSync(new Date()); };
    const check = async () => {
      try {
        const { data } = await api.get("/api/ingest/status");
        if (data.status?.state === "running" && Date.now() - t0 < 180000) {
          setSyncWhat(data.status.what || ""); setTimeout(check, 2000); return;
        }
      } catch { /* fall through and settle */ }
      setSyncWhat(""); settle();
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
        if (data.status?.state === "running") {
          sawRunning = true;
          // background catch-up: say so and keep polling, but never dim rows that are already
          // real - a readable timeline behind a working banner, not a page that looks loading
          setBgSync(true); setSyncWhat(data.status.what || "");
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
    setSel(null); setEditText("");   // filter switch: never leave a stale review panel up
    load();
    const t = setInterval(() => load(rowsLen.current), 30000);       // cheap row refresh
    const s = setInterval(() => syncNow(true), 600000);              // real ingest poll every 10 min
    return () => { clearInterval(t); clearInterval(s); };
  }, [load, syncNow]);
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
    setSel(row); setDetail(null); setEditText(null); setSendErr(""); want.current = row.MessageId;
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
  const hoverSelect = (row) => {
    clearTimeout(hoverTimer.current);
    if (sel?.MessageId === row.MessageId) return;
    if (sel && (editText ?? "").trim()) return;        // don't yank an OPEN panel mid-edit
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
  const sorted = [...(rows || [])].sort((a, b) => (b.SentAt || "").localeCompare(a.SentAt || ""));
  const days = sorted.reduce((acc, r) => {
    const d = localDay(r.SentAt) || "undated";
    (acc[d] = acc[d] || []).push(r);
    return acc;
  }, {});

  // only offer channels that actually have a connection behind them
  const pickerChannels = ((CATEGORIES.find((x) => x.key === cat) || {}).channels
    || ["email", "teams", "slack", "github", "report"]).filter((ch) => (srcByChannel[ch] || []).length);

  const today = new Date().toLocaleDateString("sv-SE");
  const todays = (rows || []).filter((r) => localDay(r.SentAt) === today);
  const stats = [
    { label: "in today", n: todays.length, f: "" },
    { label: "auto", n: todays.filter((r) => r.ReviewStatus === "auto").length, f: "" },
    { label: "need me", n: (rows || []).filter(needsYou).length, f: "pending", hot: true },
    { label: "ignored", n: todays.filter((r) => r.MsgStatus === "ignored").length, f: "" },
  ];

  return (
    <Box sx={{ display: "grid", gap: 2, alignItems: "start",
      // Timeline column is a HARD 860px in both states - it cannot shrink or grow when
      // the panel opens; the panel takes exactly the leftover (minmax(0,1fr) = no spill).
      gridTemplateColumns: { xs: "minmax(0, 1fr)",
        md: sel ? "min(860px, 100%) minmax(0, 1fr)" : "min(860px, 100%)" } }}>
      {/* timeline column: grid's minmax(0,...) hard-caps both tracks, so the panel can
          never spill past the viewport and the list keeps its layout */}
      <Box sx={{ minWidth: 0, maxWidth: 860 }}>
        {/* contained toolbar, two deliberate rows: controls (filters left, sync anchored
            right) over a full-width stats strip - nothing floats in dead space */}
        <Box sx={{ ...card, p: 0, overflow: "hidden" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 1.5, py: 1, flexWrap: "wrap" }}>
            <FilterPills options={VIEW_FILTERS} value={view} onChange={setView} />
            <FilterPills options={CATEGORIES} value={cat} onChange={setCat} />
            {pickerChannels.length > 0 && (
              <Select size="small" value={pick} displayEmpty onChange={(e) => setPick(e.target.value)}
                renderValue={(v) => (!v ? "any connection"
                  : v.startsWith("channel:") ? `all ${CHANNEL_LABELS[v.slice(8)] || v.slice(8)}`.toLowerCase()
                    : String(v.split(":").slice(2).join(":")).split("@")[0])}
                sx={{ fontSize: 11.5, fontWeight: 600, borderRadius: 99, bgcolor: pick ? "#e8f1fa" : "#fff", height: 26,
                  color: pick ? "#0F6CBD" : DIM, maxWidth: 210,
                  "& .MuiSelect-select": { py: 0.3, px: 1.25 },
                  "& .MuiOutlinedInput-notchedOutline": { borderColor: pick ? "#c4dcf2" : BORDER } }}>
                <MenuItem value="" sx={{ fontSize: 12 }}>any connection</MenuItem>
                {pickerChannels.flatMap((ch) => [
                  <ListSubheader key={`h${ch}`} sx={{ fontSize: 10, lineHeight: 2, color: FAINT, letterSpacing: 1,
                    textTransform: "uppercase", bgcolor: "transparent" }}>
                    {CHANNEL_LABELS[ch] || ch}
                  </ListSubheader>,
                  <MenuItem key={`c${ch}`} value={`channel:${ch}`} sx={{ fontSize: 12 }}>
                    all {(CHANNEL_LABELS[ch] || ch).toLowerCase()}
                  </MenuItem>,
                  ...(srcByChannel[ch] || []).map((n) => (
                    <MenuItem key={`${ch}:${n}`} value={`src:${ch}:${n}`} sx={{ fontSize: 12, pl: 3 }}>{n}</MenuItem>
                  )),
                ])}
              </Select>
            )}
            <Box sx={{ flex: 1, minWidth: 8 }} />
            <Button size="small" variant="contained" disableElevation disabled={syncing || bgSync} onClick={() => syncNow(false)}
              startIcon={syncing || bgSync ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 14 }} />}
              sx={{ py: 0.4, fontSize: 11.5, background: "linear-gradient(90deg, #4f46e5, #7c6cf0)" }}>{syncing || bgSync ? (syncWhat || "Updating…") : "Sync now"}</Button>
          </Box>
          {/* stats strip - and the sync caption lives here, so the controls row above keeps
              its budget whether or not the mailbox picker is showing */}
          {rows && (
            <Box sx={{ display: "flex", alignItems: "center", borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
              {stats.map((s, i) => (
                <Box key={s.label} onClick={() => s.f && setView(s.f)}
                  sx={{ flex: 1, display: "flex", alignItems: "baseline", gap: 0.6, px: 1.5, py: 0.7,
                    borderLeft: i ? `1px solid ${BORDER}` : "none", transition: "background .15s",
                    cursor: s.f ? "pointer" : "default",
                    ...(s.f ? { "&:hover": { bgcolor: "#eef0ff" }, "&:hover .thubStatLbl": { color: "#4f46e5" } } : {}) }}>
                  <Typography sx={{ ...mono, fontWeight: 700, fontSize: 15,
                    color: s.hot && s.n ? "#b45309" : s.n ? "#4f46e5" : INK }}>{s.n}</Typography>
                  <Typography className="thubStatLbl" variant="caption" sx={{ color: FAINT, transition: "color .15s" }}>{s.label}</Typography>
                </Box>
              ))}
              <Typography variant="caption" noWrap sx={{ color: FAINT, px: 1.5, py: 0.7, flexShrink: 0,
                borderLeft: `1px solid ${BORDER}` }}>
                {lastSync
                  ? `last sync ${lastSync.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`
                  : "auto-syncs every 10 min"}
              </Typography>
            </Box>
          )}
        </Box>
        {(syncing || bgSync) && <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />}
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mt: 1.5 }}>{err}</Alert>}
        <Box sx={{ opacity: syncing ? 0.55 : 1, transition: "opacity .25s" }}>
          {!rows ? <CircularProgress size={22} sx={{ m: 4 }} /> : !rows.length ? (
            <Empty>Nothing in the feed yet — activate a mailbox in Connectors or run an ingest.</Empty>
          ) : Object.entries(days).map(([day, items]) => (
            <Box key={day} sx={{ mt: 1 }}>
              <DayHeader label={fmtDay(day)} />
              <Box>
                {items.map((r, i) => (
                  <Box key={r.MessageId} sx={{ display: "flex", alignItems: "stretch", gap: 0,
                    ...(seen.current.has(r.MessageId) ? {} : { ...fadeIn, animationDelay: `${Math.min(i * 45, 400)}ms` }) }}>
                    {/* time column */}
                    <Typography variant="caption" sx={{ ...mono, color: FAINT, width: 58, textAlign: "right", pt: 2.1, flexShrink: 0 }}>
                      {fmtTime12(r.SentAt)}
                    </Typography>
                    {/* rail + dot */}
                    <Box sx={{ width: 16, flexShrink: 0, position: "relative" }}>
                      <Box sx={{ position: "absolute", left: 7, top: 0, bottom: 0, width: "2px", bgcolor: BORDER }} />
                      <Box sx={{ position: "absolute", left: 4, top: 20, width: 8, height: 8, borderRadius: "50%",
                        bgcolor: r.ReviewStatus === "pending" ? "#f59e0b"
                          : ["ignored", "filed"].includes(r.MsgStatus) ? "#cbd2dd"
                            : CHANNEL_COLORS[r.Channel] || "#4f46e5",
                        border: `2px solid ${PANEL}` }} />
                    </Box>
                    {/* blurb: uniform one-line card; hover grows it (message gist) and shows the
                      go-arrow; click sends it to the review canvas on the right */}
                    <Box onClick={() => drill(r)} onMouseEnter={() => hoverSelect(r)} onMouseLeave={hoverCancel}
                      sx={{ ...card, ...hoverable, flex: 1, minWidth: 0, py: 0, px: 1.25, my: 0.5, ml: 1, overflow: "hidden",
                        position: "relative", pl: 1.75,
                        "&::before": { content: '""', position: "absolute", left: 6, top: 9, bottom: 9, width: "3px",
                          borderRadius: 99, bgcolor: CHANNEL_COLORS[r.Channel] || "#c9cff0" },
                        transition: "box-shadow .18s, border-color .18s, transform .18s",
                        ...(sel?.MessageId === r.MessageId ? { borderColor: "#4f46e5", boxShadow: "0 3px 12px rgba(79,70,229,.16)", bgcolor: "#fbfbff" } : {}),
                        "&:hover": { borderColor: "#c9cff0", boxShadow: "0 3px 12px rgba(79,70,229,.12)", cursor: "pointer", transform: "translateY(-1px)" },
                        "&:hover .thubDetail": { gridTemplateRows: "1fr" },
                        "&:hover .thubDetailText": { opacity: 1, transform: "none" },
                        "&:hover .thubGo": { opacity: 1, transform: "translateX(0)" } }}>
                      <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", minWidth: 0, height: 40 }}>
                        <Box sx={{ width: 24, height: 24, borderRadius: 1.25, flexShrink: 0, display: "flex",
                          alignItems: "center", justifyContent: "center",
                          bgcolor: `${CHANNEL_COLORS[r.Channel] || "#98a1b3"}18` }}>
                          <ChannelIcon channel={r.Channel} />
                        </Box>
                        <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: INK, maxWidth: 190, flexShrink: 0 }}>
                          {r.FromName || r.FromEmail || "unknown"}
                        </Typography>
                        {r.SourceName && <Typography variant="caption" noWrap sx={{ color: FAINT, maxWidth: 150, flexShrink: 0 }}>· {r.SourceName}</Typography>}
                        <Typography variant="body2" noWrap sx={{ color: DIM, flex: 1, minWidth: 0 }}>{subjectOf(r) ? `— ${subjectOf(r)}` : ""}</Typography>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexShrink: 0 }}>
                          {r.Attachments > 0 && (
                            <Typography variant="caption" title={`${r.Attachments} attached`}
                              sx={{ color: FAINT, display: "flex", alignItems: "center", fontSize: 10.5 }}>
                              <AttachFileIcon sx={{ fontSize: 13 }} />{r.Attachments > 1 ? r.Attachments : ""}
                            </Typography>
                          )}
                          <RefChip taskId={r.TaskId} onClick={(e) => { e.stopPropagation(); onOpenTask(r.TaskId); }} />
                          <ActionChip action={actionOf(r)} reviewStatus={r.ReviewStatus} taskStatus={r.TaskStatus} needsYou={needsYou(r)} />
                          <ChevronRightIcon className="thubGo" sx={{ fontSize: 18, color: "#4f46e5",
                            opacity: sel?.MessageId === r.MessageId ? 1 : 0,
                            transform: sel?.MessageId === r.MessageId ? "translateX(0)" : "translateX(-6px)",
                            transition: "opacity .18s, transform .18s" }} />
                        </Box>
                      </Box>
                      <Box className="thubDetail" sx={{ display: "grid", gridTemplateRows: "0fr", transition: "grid-template-rows .22s ease" }}>
                        <Box sx={{ overflow: "hidden" }}>
                          <Box className="thubDetailText" sx={{ pb: 1, ml: "23px",
                            opacity: 0, transform: "translateX(18px)", transition: "opacity .22s ease .05s, transform .22s ease .05s" }}>
                            {r.Preview && <Typography variant="caption" noWrap sx={{ display: "block", color: INK }}>
                            “{r.Preview}”
                            </Typography>}
                            <Typography variant="caption" noWrap sx={{ display: "block", color: DIM }}>{blurb(r)}</Typography>
                          </Box>
                        </Box>
                      </Box>
                    </Box>
                  </Box>
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
        <Box sx={{ minWidth: 0, display: { xs: "none", md: "block" }, alignSelf: "stretch" }}>
          <Box sx={{ position: "sticky", top: 60 }}>
            <ReviewCanvas sel={sel} detail={detail} editText={editText} setEditText={setEditText}
              decide={decide} onOpenTask={onOpenTask} onClose={() => setSel(null)}
              onSkipped={() => { setSel(null); load(); }} onRefresh={() => load()}
              sendErr={sendErr} clearSendErr={() => setSendErr("")} />
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
  if (detail?.task) ev.push({ at: detail.task.CreatedAt, label: `Task ${detail.ref} opened`, sub: detail.task.Kind, c: "#4f46e5" });
  (detail?.routes || []).forEach((r) => ev.push({ at: detail.task?.CreatedAt, c: "#7e22ce",
    label: r.Decision === "attach" ? "Routed — attached to this thread"
      : r.Decision === "create" ? "Routed — new task created" : `Routed — ${r.Decision}` }));
  (detail?.runs || []).forEach((r) => ev.push({ at: r.StartedAt, label: `${r.AgentName} run`, sub: r.Status,
    c: r.Status === "error" ? "#b91c1c" : "#0e7490" }));
  (detail?.comments || []).filter((c) => c.ActorType === "human").forEach((c) =>
    ev.push({ at: c.CreatedAt, label: c.Actor, sub: cleanText(c.Body).slice(0, 70), c: "#697386" }));
  if (sel.ReviewStatus && sel.ReviewStatus !== "pending") ev.push({ at: null, label: "You decided", sub: sel.ReviewStatus.replace("_", " "), c: "#15803d" });
  if (["done", "dropped"].includes(detail?.task?.Status)) ev.push({ at: detail.task.UpdatedAt, label: `Task ${detail.task.Status}`, c: "#15803d" });
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
  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 9.5, display: "block", mt: 1.5 }}>
    {children}
  </Typography>
);

// The pop-out review panel: everything about the selected line, editable and decidable
// without leaving the page. All text hard-left-aligned.
const ReviewCanvas = ({ sel, detail, editText, setEditText, decide, onOpenTask, onClose, onSkipped, onRefresh,
                        sendErr, clearSendErr }) => {
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
  useEffect(() => { setHandoff(false); setReshape(false); setOpened(null); setOpening(false); }, [sel.MessageId]);
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
  const onIt = ses ? { agent: ses.agent || ses.label, waiting: ses.idle >= IDLE_WAITING }
    : run ? { agent: run.AgentName, waiting: false } : null;
  const loading = sel.TaskId && !detail;
  const history = historyOf(sel, detail);
  return (
    <Box key={sel.MessageId} sx={{ ...frame, textAlign: "left",
      // grows out of the clicked blurb: slides rightward from the row and scales up
      "@keyframes thubGrow": { from: { opacity: 0, transform: "translateX(-32px) scale(.965)" },
        to: { opacity: 1, transform: "none" } },
      animation: "thubGrow .3s cubic-bezier(.2,.8,.3,1) both", transformOrigin: "left center" }}>
      <Box sx={{ ...frameInner, display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 140px)" }}>
        {/* header */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.25, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
          <ChevronRightIcon sx={{ fontSize: 17, color: "#4f46e5" }} />
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
          <ActionChip action={actionOf(sel)} reviewStatus={sel.ReviewStatus} taskStatus={sel.TaskStatus} needsYou={needsYou(sel)} />
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
                  <Box sx={{ bgcolor: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: 1.5, px: 1.25, py: 0.5 }}>
                    <CoderReport body={rep.Body} />
                  </Box>
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
                        {h.n > 1 && <Chip size="small" label={`×${h.n}`} sx={{ height: 16, fontSize: 9.5, bgcolor: "#eef0ff", color: "#4f46e5" }} />}
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
                    sendErr={sendErr} clearSendErr={clearSendErr} />
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
                    sendErr={sendErr} clearSendErr={clearSendErr} />
                </>
              )}
              {!pending && !opened && sel.Channel !== "report" && (
                <ChoiceRow tint="#eef0ff" busy={opening} onClick={openReply}
                  icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: "#4f46e5" }} />}
                  label="Reply to this"
                  hint="the AI drafts it from the thread (and the coder's report, if one ran) — approving sends" />
              )}

            </>
          )}
        </Box>

        {/* pinned: whatever the message does, the four options are on screen */}
        {!loading && (
          <Box sx={{ flexShrink: 0, borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2,
            px: 2, pt: 0.25, pb: 1.25, maxHeight: "46vh", overflowY: "auto" }}>
          {/* These were four buttons in two rows, four sizes, two right-aligned - so "what are
              my options" needed a hunt, and a long message pushed the fourth off-screen. */}
            <PanelLabel>What should happen with this?</PanelLabel>
            <ChoiceList>
              {onIt ? (
                <ChoiceRow first tint="#f5f3ff" onClick={() => onOpenTask(sel.TaskId)}
                  icon={<SmartToyIcon sx={{ fontSize: 15, color: onIt.waiting ? "#b45309" : "#7e22ce" }} />}
                  label={onIt.waiting ? `${onIt.agent} is waiting for your answer` : `${onIt.agent} is working this now`}
                  hint={onIt.waiting ? "open the task and answer it in the session" : "open the task to watch it live"} />
              ) : (
                <SendToAgent row first messageId={sel.MessageId} subject={sel.Subject} onOpenTask={onOpenTask} />
              )}
              {sel.TaskId ? (
                <ChoiceRow tint="#eef0ff" onClick={() => onOpenTask(sel.TaskId)}
                  icon={<OpenInFullIcon sx={{ fontSize: 14, color: "#4f46e5" }} />}
                  label={`Open task ${ref(sel.TaskId)}`} hint="the whole story: session, report, history" />
              ) : (
                <MineToDo messageId={sel.MessageId} onMade={() => onRefresh?.()} />
              )}
              {sel.TaskId && (
                <ChoiceRow tint="#eef0ff" onClick={() => setHandoff((h) => !h)}
                  icon={<ForwardToInboxIcon sx={{ fontSize: 14, color: "#4f46e5" }} />}
                  label="Hand it to a person" hint="not ours to do — the AI writes the forward, you send it" />
              )}
              <SplitTask row={sel} onSplit={() => onRefresh?.()} />
              {sel.TaskId && (
                <ChoiceRow tint="#e6f7fb" onClick={() => setReshape(true)}
                  icon={<CallSplitIcon sx={{ fontSize: 14, color: "#0e7490" }} />}
                  label="Two jobs in here, or a duplicate?"
                  hint={`break ${ref(sel.TaskId)} in two, or fold it into the task it repeats`} />
              )}
              {/* not ours -> the reason goes to memory, and triage reads it next time */}
              <NotMine row messageId={sel.MessageId} onDone={onSkipped} />
              {/* ...and the lighter verdict: THIS one is just chatter (someone said "yes"),
                  nothing to learn about the sender - the task goes, their mail keeps flowing */}
              {sel.TaskId && (
                <ChoiceRow tint="#f4f5f7" onClick={async () => {
                    await api.post(`/api/tasks/${sel.TaskId}/not-a-task`, { learn: false });
                    onSkipped?.();
                  }}
                  icon={<CloseIcon sx={{ fontSize: 14, color: "#697386" }} />}
                  label="Not a task — just conversation"
                  hint={`delete ${ref(sel.TaskId)}, learn nothing; the messages stay on the timeline`} />
              )}
              {sel.Channel === "email" && sel.FromEmail && (skipped !== null ? (
                <ChoiceRow tint="#e8f6ee" busy
                  icon={<VolumeOffIcon sx={{ fontSize: 14, color: "#15803d" }} />}
                  label="Sender skipped"
                  hint={skipped ? `${skipped} past message${skipped === 1 ? "" : "s"} hidden too` : "they will not appear again"} />
              ) : (
                <ChoiceRow tint="#eef0f3" onClick={skipSender}
                  icon={<VolumeOffIcon sx={{ fontSize: 14, color: "#8a94a6" }} />}
                  label="Skip this sender" hint={`hide ${sel.FromEmail} and their past mail — undo in Settings`} />
              ))}
            </ChoiceList>

            <Drawer anchor="right" open={!!reshape && !!sel.TaskId} onClose={() => setReshape(false)}
              PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                <CallSplitIcon sx={{ fontSize: 18, color: "#0e7490" }} />
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

            {handoff && sel.TaskId && (
              <Box sx={{ mt: 1, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.25, py: 1 }}>
                <PanelLabel>Hand this to a person</PanelLabel>
                <Handoff taskId={sel.TaskId} onSent={() => onRefresh?.()} />
              </Box>
            )}
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
      <Box sx={{ position: "sticky", top: 0, zIndex: 3, py: 0.75, ml: "56px" }}>
        <Box sx={{ display: "inline-block", px: stuck ? 1.5 : 0, py: stuck ? 0.4 : 0,
          bgcolor: stuck ? PANEL : BG, border: `1px solid ${stuck ? BORDER : "transparent"}`,
          borderRadius: 99, boxShadow: stuck ? "0 4px 14px rgba(16,24,40,.12)" : "none",
          transform: stuck ? "scale(1.08)" : "scale(1)", transformOrigin: "left center",
          transition: "all .25s cubic-bezier(.34,1.56,.64,1)" }}>
          <Typography variant="caption" sx={{ ...mono, color: stuck ? "#4f46e5" : INK, fontWeight: 800,
            fontSize: 11.5, letterSpacing: 0.5 }}>
            {label}
          </Typography>
        </Box>
      </Box>
    </>
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
                  border: `1px solid ${on ? "#c9cff0" : BORDER}`, color: on ? "#4f46e5" : you ? FAINT : DIM,
                  bgcolor: on ? "#eef0ff" : "#fff", whiteSpace: "nowrap", transition: "all .15s",
                  "&:hover": { borderColor: "#c9cff0", color: "#4f46e5" } }}>
                {you ? "↩ you" : (m.FromName || m.FromEmail || "?").split(" ")[0]} · {pt(m.SentAt)}
              </Box>
            );
          })}
        </Box>
      )}
      <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.25,
        borderLeft: `3px solid ${you ? "#c9cff0" : "#0F6CBD"}` }}>
        {/* who / which way / when - so "new inbound" is never confused with "your reply" */}
        {cur && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.6, flexWrap: "wrap" }}>
            <Chip size="small" label={you ? "↩ your reply" : "inbound"}
              sx={{ height: 17, fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                bgcolor: you ? "#eef0ff" : "#e8f1fa", color: you ? "#4f46e5" : "#0F6CBD" }} />
            <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>
              {you ? "you" : cur.FromName || cur.FromEmail || "unknown"}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>· {fmtDateTime(cur.SentAt)}</Typography>
            {quoted && <Typography variant="caption" sx={{ color: FAINT }}>· replying on this thread</Typography>}
          </Box>
        )}
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, textAlign: "left" }}>
          {text}
        </Typography>
        {raw && (
          <Box sx={{ mt: 1, borderTop: `1px dashed ${BORDER}`, pt: 0.75 }}>
            <Typography variant="caption" onClick={() => setShowRaw(!showRaw)}
              sx={{ color: DIM, fontWeight: 600, cursor: "pointer", "&:hover": { color: "#4f46e5" } }}>
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
              sx={{ color: DIM, fontWeight: 600, cursor: "pointer", "&:hover": { color: "#4f46e5" } }}>
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
    <ChoiceRow tint="#eef0ff" busy={busy || !!made} onClick={go}
      icon={<AssignmentIndIcon sx={{ fontSize: 14, color: "#4f46e5" }} />}
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
    <ChoiceRow tint="#e6f7fb" busy={busy || !!done} onClick={go}
      icon={<CallSplitIcon sx={{ fontSize: 14, color: "#0e7490" }} />}
      label={done ? `Now its own task ${ref(done)}` : "Give this message its own task"}
      hint={err || (done ? "send it to an agent above" : `a separate ask from the rest of ${ref(row.TaskId)}`)} />
  );
};

const ReviewActions = ({ reviewId, draft, editText, setEditText, decide, sendErr, clearSendErr }) => (
  <Box>
    <TextField fullWidth multiline minRows={3} size="small" placeholder="Edit the draft (or approve as-is)"
      value={editText ?? draft ?? ""} onChange={(e) => setEditText(e.target.value)} sx={{ mb: 1 }} />
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      {/* ONE approve: it sends what is in the box, edited or not - two buttons asked you to
          declare something the text already shows */}
      <Button size="small" variant="contained" disabled={!(editText ?? draft ?? "").trim()}
        onClick={() => decide(reviewId, "approve", editText ?? draft)}
        title="Sends the text above on the channel it arrived on">Approve &amp; send</Button>
      <Button size="small" sx={{ color: "#8a94a6" }} onClick={() => decide(reviewId, "no_reply")}>No reply needed</Button>
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
