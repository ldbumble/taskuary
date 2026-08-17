// Timeline: left time rail, messages slide in as compact blurbs - who/where, the subject,
// and one plain sentence saying what the hub DID with it (routed where, drafted, escalated,
// ignored) plus its current status. Click a blurb for the full drill-through. Refreshes
// itself every 30s so new mail animates in while the tab is open.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Drawer, IconButton, LinearProgress, Link, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import { BG, PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, card, frame, frameInner, hoverable, mono, fadeIn } from "./theme.jsx";
import SyncIcon from "@mui/icons-material/Sync";
import { ChannelIcon, CHANNEL_COLORS, RefChip, ActionChip, RunTrace, CoderReport, DiffBlock, Empty, scoreBar, FilterPills, fmtTime12, fmtDateTime, localDay, cleanText } from "./ui.jsx";

// Each filter carries a muted hue for its selected state: attention amber for needs-me,
// Outlook blue, Teams purple, quiet indigo for everything.
// Two different dimensions, two controls: WHAT STATE it's in (everything vs needs me)
// and WHICH CHANNEL it came from - they combine (e.g. "needs me" + "email").
const VIEW_FILTERS = [
  { key: "", label: "everything", c: { bg: "#eef0ff", fg: "#4f46e5", bd: "#c9cff0" } },
  { key: "pending", label: "needs me", c: { bg: "#fef4e6", fg: "#b45309", bd: "#f3ddb8" } },
];
const CHANNEL_FILTERS = [
  { key: "", label: "all channels" },
  { key: "email", label: "email", c: { bg: "#e8f1fa", fg: "#0F6CBD", bd: "#c4dcf2" } },
  { key: "teams", label: "teams", c: { bg: "#efeffa", fg: "#6264A7", bd: "#d4d5ec" } },
  { key: "slack", label: "slack", c: { bg: "#f3ecf5", fg: "#611f69", bd: "#e0cbe4" } },
  { key: "report", label: "reports", c: { bg: "#e6f7fb", fg: "#0e7490", bd: "#c2e7f0" } },
];

const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;

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
  if (r.MsgStatus === "ignored") return `Ignored by policy — ${r.RouteReason || "no task created"}`;
  if (r.MsgStatus === "filed") return `Filed, nothing to do — ${r.RouteReason || "informational"}`;
  const routed = r.Decision === "attach" ? `Added to ${ref(r.TaskId)} (existing thread)` : `New task ${ref(r.TaskId)} created`;
  const state = r.ReviewStatus === "pending" && r.ReviewKind === "escalation" ? "escalated — waiting on you"
    : r.ReviewStatus === "pending" ? "AI drafted a reply — waiting on your review"
      : r.ReviewStatus === "auto" ? "AI answered automatically"
        : r.TaskStatus === "done" ? `completed${r.ReviewStatus ? ` · you said ${r.ReviewStatus.replace("_", " ")}` : ""}`
          : r.ReviewStatus ? `reviewed (${r.ReviewStatus})` : "queued for the coder to work";
  return `${routed} · ${state}`;
};

const PAGE = 100;

export default function FeedView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [view, setView] = useState("");              // "" everything | "pending" needs me
  const [channel, setChannel] = useState("");        // "" all | email | teams | slack | report
  const [mailbox, setMailbox] = useState("");        // "" all | one mailbox (shows when several are connected)
  const [mailboxes, setMailboxes] = useState([]);
  const [noMore, setNoMore] = useState(false);
  const [open, setOpen] = useState(null);
  const [detail, setDetail] = useState(null);
  const [editText, setEditText] = useState("");
  const [err, setErr] = useState("");
  const seen = useRef(new Set());               // MessageIds already animated in
  const rowsLen = useRef(0);
  const busyMore = useRef(false);
  const endRef = useRef(null);

  const fparams = useCallback(() => ({ ...(view === "pending" ? { pending_only: true } : {}),
    ...(channel ? { channel } : {}),
    ...(channel === "email" && mailbox ? { source: mailbox } : {}) }), [view, channel, mailbox]);

  // which mailboxes exist (the picker only appears when there is more than one)
  useEffect(() => {
    api.get("/api/sources").then(({ data }) =>
      setMailboxes((data.data || []).filter((s) => s.Channel === "email" && s.Active).map((s) => s.Address)))
      .catch(() => {});
  }, []);
  useEffect(() => { if (channel !== "email") setMailbox(""); }, [channel]);

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
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const syncNow = useCallback(async (silent) => {
    if (!silent) setSyncing(true);
    try { await api.post("/api/ingest/poll"); } catch { /* poll failures surface in Connectors */ }
    const t0 = Date.now();
    const settle = async () => { await load(rowsLen.current); setSyncing(false); setLastSync(new Date()); };
    const check = async () => {
      try {
        const { data } = await api.get("/api/ingest/status");
        if (data.status?.state === "running" && Date.now() - t0 < 180000) { setTimeout(check, 2000); return; }
      } catch { /* fall through and settle */ }
      settle();
    };
    setTimeout(check, 1500);
  }, [load]);

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
  const hoverTimer = useRef(null);
  const drill = async (row) => {
    setSel(row); setDetail(null); setEditText("");
    if (row.TaskId) setDetail((await api.get(`/api/tasks/${row.TaskId}`)).data);
  };
  const hoverSelect = (row) => {
    clearTimeout(hoverTimer.current);
    if (sel?.MessageId === row.MessageId) return;
    if (sel && editText.trim()) return;                // don't yank an OPEN panel mid-edit
    hoverTimer.current = setTimeout(() => drill(row), 260);
  };
  const hoverCancel = () => clearTimeout(hoverTimer.current);

  const decide = async (reviewId, verb, finalText) => {
    await api.post(`/api/reviews/${reviewId}/decide`, { verb, final_text: finalText || null });
    setOpen(null); setSel(null); setEditText("");      // stale edits must never block hover
    load(); onChanged?.();
  };

  // Strict newest-first by sent time (UTC strings compare correctly), then group by local day.
  const sorted = [...(rows || [])].sort((a, b) => (b.SentAt || "").localeCompare(a.SentAt || ""));
  const days = sorted.reduce((acc, r) => {
    const d = localDay(r.SentAt) || "undated";
    (acc[d] = acc[d] || []).push(r);
    return acc;
  }, {});

  const today = new Date().toLocaleDateString("sv-SE");
  const todays = (rows || []).filter((r) => localDay(r.SentAt) === today);
  const stats = [
    { label: "in today", n: todays.length, f: "" },
    { label: "auto", n: todays.filter((r) => r.ReviewStatus === "auto").length, f: "" },
    { label: "need me", n: (rows || []).filter((r) => r.ReviewStatus === "pending").length, f: "pending", hot: true },
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
        {/* contained toolbar: segmented filters + sync control + today's stats */}
        <Box sx={{ ...card, px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <FilterPills options={VIEW_FILTERS} value={view} onChange={setView} />
          <FilterPills options={CHANNEL_FILTERS} value={channel} onChange={setChannel} />
          {channel === "email" && mailboxes.length > 1 && (
            <Select size="small" value={mailbox} displayEmpty onChange={(e) => setMailbox(e.target.value)}
              sx={{ fontSize: 11.5, fontWeight: 600, borderRadius: 99, bgcolor: mailbox ? "#e8f1fa" : "#fff", height: 26,
                color: mailbox ? "#0F6CBD" : DIM,
                "& .MuiSelect-select": { py: 0.3, px: 1.25 },
                "& .MuiOutlinedInput-notchedOutline": { borderColor: mailbox ? "#c4dcf2" : BORDER } }}>
              <MenuItem value="" sx={{ fontSize: 12 }}>all mailboxes</MenuItem>
              {mailboxes.map((m) => <MenuItem key={m} value={m} sx={{ fontSize: 12 }}>{m}</MenuItem>)}
            </Select>
          )}
          <Box sx={{ width: "1px", alignSelf: "stretch", bgcolor: BORDER, my: 0.25 }} />
          <Button size="small" variant="contained" disableElevation disabled={syncing} onClick={() => syncNow(false)}
            startIcon={syncing ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 14 }} />}
            sx={{ py: 0.4, fontSize: 11.5, background: "linear-gradient(90deg, #4f46e5, #7c6cf0)" }}>{syncing ? "Updating…" : "Sync now"}</Button>
          <Typography variant="caption" sx={{ color: FAINT }}>
            {lastSync
              ? `last sync ${lastSync.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`
              : "auto-syncs every 10 min"}
          </Typography>
          <Box sx={{ flex: 1 }} />
          {rows && stats.map((s, i) => (
            <Box key={s.label} onClick={() => s.f && setView(s.f)}
              sx={{ display: "flex", alignItems: "baseline", gap: 0.5, px: 1.25,
                borderLeft: i ? `1px solid ${BORDER}` : "none",
                cursor: s.f ? "pointer" : "default",
                "&:hover .thubStatLbl": s.f ? { color: "#4f46e5" } : {} }}>
              <Typography sx={{ ...mono, fontWeight: 700, fontSize: 15,
                color: s.hot && s.n ? "#b45309" : s.n ? "#4f46e5" : INK }}>{s.n}</Typography>
              <Typography className="thubStatLbl" variant="caption" sx={{ color: FAINT, transition: "color .15s" }}>{s.label}</Typography>
            </Box>
          ))}
        </Box>
        {syncing && <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />}
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
                          <RefChip taskId={r.TaskId} onClick={(e) => { e.stopPropagation(); onOpenTask(r.TaskId); }} />
                          <ActionChip action={["ignored", "filed"].includes(r.MsgStatus) ? "ignore" : r.ReviewKind === "escalation" ? "escalate" : r.ReviewKind === "auto" ? "auto" : r.ReviewId ? "draft" : "task_only"} reviewStatus={r.ReviewStatus} taskStatus={r.TaskStatus} />
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
              decide={decide} onDetails={() => setOpen(sel)} onOpenTask={onOpenTask} onClose={() => setSel(null)} />
          </Box>
        </Box>
      )}

      {/* ── drill-through ──────────────────────────────────────────────── */}
      <Drawer anchor="right" open={!!open} onClose={() => setOpen(null)}
        PaperProps={{ sx: { width: 540, bgcolor: PANEL, p: 2.5, borderLeft: `1px solid ${BORDER}` } }}>
        {open && (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <ChannelIcon channel={open.Channel} sx={{ color: "#4f46e5" }} />
              <Typography variant="subtitle1" sx={{ color: INK, fontWeight: 700, flex: 1, fontSize: 14 }} noWrap>
                {open.Subject || "(no subject)"}
              </Typography>
              <IconButton size="small" onClick={() => setOpen(null)}><CloseIcon fontSize="small" /></IconButton>
            </Box>
            <Typography variant="caption" sx={{ color: DIM }}>
              {open.FromName || open.FromEmail}{open.SourceName ? ` · ${open.SourceName}` : ""} · {fmtDateTime(open.SentAt)}
              {open.SourceLink && (
                <Link href={open.SourceLink} target="_blank" rel="noopener" sx={{ ml: 1, color: ACCENT2 }}>
                  open source <OpenInNewIcon sx={{ fontSize: 11, verticalAlign: "middle" }} />
                </Link>
              )}
            </Typography>

            {open.TaskId ? !detail ? <CircularProgress size={20} sx={{ m: 3 }} /> : (
              <>
                <DrawerBlock title="What the router did">
                  {detail.routes.filter((rt) => rt.MessageId === open.MessageId).map((rt) => (
                    <Box key={rt.RouteId}>
                      <Typography variant="body2" sx={{ color: INK }}>{rt.Decision} — {rt.Reason}</Typography>
                      {(JSON.parse(rt.CandidatesJson || "[]")).map((c) => (
                        <Typography key={c.task_id} variant="caption" sx={{ display: "flex", alignItems: "center", color: DIM }}>
                          {scoreBar(c.score)} {ref(c.task_id)} (thread {c.signals.thread}, subj {c.signals.subject}, body {c.signals.body})
                        </Typography>
                      ))}
                    </Box>
                  ))}
                </DrawerBlock>
                <Box sx={{ mt: 2 }}>
                  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>
                    {detail.messages.length > 1 ? `Emails in this chain (${detail.messages.length})` : "Message"}
                  </Typography>
                  <Box sx={{ mt: 0.5 }}>
                    <MessageBlock key={open.MessageId} messages={detail.messages} focusId={open.MessageId} maxH={220} />
                  </Box>
                </Box>
                {(() => {
                  // The coder's report - did it change code, what it did, where it stands.
                  const rep = [...(detail.comments || [])].reverse().find((c) => c.Actor === "coder" && String(c.Body || "").startsWith("CODER REPORT"));
                  return rep ? (
                    <DrawerBlock title="What the coder did">
                      <Box sx={{ maxHeight: 260, overflow: "auto" }}><CoderReport body={rep.Body} /></Box>
                    </DrawerBlock>
                  ) : null;
                })()}
                {open.ReviewId && open.ReviewStatus === "pending" && (
                  <DrawerBlock title={open.ReviewKind === "escalation" ? "Escalated — needs you" : "Draft reply — needs you"}>
                    <ReviewActions reviewId={open.ReviewId} kind={open.ReviewKind} draft={pendingDraft(detail, open)}
                      editText={editText} setEditText={setEditText} decide={decide} />
                  </DrawerBlock>
                )}
                <DrawerBlock title="Agent activity">
                  {!detail.runs.length ? <Typography variant="caption" sx={{ color: DIM }}>No agent has touched this yet.</Typography>
                    : detail.runs.map((r) => (
                      <Box key={r.RunId} sx={{ mb: 1 }}>
                        <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>run {r.RunId} · {r.AgentName} · {r.Status}</Typography>
                        <RunTrace traceJson={r.TraceJson} running={r.Status === "running"} />
                        {r.Result && <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: "#15803d", display: "block", mt: 0.5 }}>{r.Result.slice(0, 700)}</Typography>}
                      </Box>
                    ))}
                </DrawerBlock>
                <Button size="small" onClick={() => { onOpenTask(open.TaskId); setOpen(null); }} sx={{ mt: 2 }}>
                  Open task {ref(open.TaskId)} →
                </Button>
              </>
            ) : (
              <DrawerBlock title={open.MsgStatus === "filed" ? "Filed — nothing to do" : "Ignored"}>
                <Typography variant="body2" sx={{ color: DIM }}>{open.RouteReason || "Policy ignored this message — no task was created."}</Typography>
              </DrawerBlock>
            )}
          </>
        )}
      </Drawer>
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
const ReviewCanvas = ({ sel, detail, editText, setEditText, decide, onDetails, onOpenTask, onClose }) => {
  // one click turns a flood sender (100s of automated mails) into a skip policy -
  // future mail from them is deduped but never shows on the timeline again
  const [skipped, setSkipped] = useState(false);
  const skipSender = async () => {
    await api.post("/api/policies", { Name: `skip:${sel.FromEmail}`, Kind: "sender", Pattern: sel.FromEmail,
      Action: "skip", Reason: "flood sender — skipped from the timeline", SortOrder: 10, Active: true });
    setSkipped(true);
  };
  const rep = [...(detail?.comments || [])].reverse().find((c) => c.Actor === "coder" && String(c.Body || "").startsWith("CODER REPORT"));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const pending = sel.ReviewId && sel.ReviewStatus === "pending";
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
          <ActionChip action={["ignored", "filed"].includes(sel.MsgStatus) ? "ignore" : sel.ReviewKind === "escalation" ? "escalate" : sel.ReviewKind === "auto" ? "auto" : sel.ReviewId ? "draft" : "task_only"} reviewStatus={sel.ReviewStatus} taskStatus={sel.TaskStatus} />
          <IconButton size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
        </Box>

        <Box sx={{ px: 2, py: 1.5, overflowY: "auto", textAlign: "left", flex: 1 }}>
          {loading ? <CircularProgress size={20} sx={{ m: 2 }} /> : (
            <>
              <PanelLabel>{(detail?.messages || []).length > 1 ? `Emails in this chain (${detail.messages.length})` : "Message"}</PanelLabel>
              <MessageBlock key={sel.MessageId} messages={detail?.messages} focusId={sel.MessageId} fallback={sel.Preview} />

              {rep && (
                <>
                  <PanelLabel>What the coder did</PanelLabel>
                  <Box sx={{ bgcolor: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: 1.5, px: 1.25, py: 0.5,
                    maxHeight: 280, overflow: "auto" }}>
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
                  <Box sx={{ maxHeight: 180, overflowY: "auto", bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.25, py: 0.25 }}>
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
                  <PanelLabel>{sel.ReviewKind === "escalation" ? "Escalated — needs you" : "Draft reply — review, edit, approve"}</PanelLabel>
                  <ReviewActions reviewId={sel.ReviewId} kind={sel.ReviewKind} draft={pendingDraft(detail || { runs: [] }, sel)}
                    editText={editText} setEditText={setEditText} decide={decide} />
                </>
              )}

              <Box sx={{ display: "flex", gap: 1, mt: 1.5, borderTop: `1px solid ${BORDER}`, pt: 1.25, alignItems: "center" }}>
                <Button size="small" onClick={onDetails}>See details →</Button>
                {sel.TaskId && <Button size="small" onClick={() => onOpenTask(sel.TaskId)}>Open task</Button>}
                <Box sx={{ flex: 1 }} />
                {sel.Channel === "email" && sel.FromEmail && (skipped
                  ? <Typography variant="caption" sx={{ color: "#15803d", fontWeight: 600 }}>✓ sender skipped from now on</Typography>
                  : <Button size="small" sx={{ color: "#8a94a6", fontSize: 11 }} onClick={skipSender}
                      title={`Never show ${sel.FromEmail} on the timeline again`}>Skip this sender</Button>)}
              </Box>
            </>
          )}
        </Box>
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
const MessageBlock = ({ messages, focusId, fallback, maxH = 240 }) => {
  const msgs = messages || [];
  const [mid, setMid] = useState(null);
  const cur = msgs.find((m) => m.MessageId === mid) || msgs.find((m) => m.MessageId === focusId) || msgs[msgs.length - 1];
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
      <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.25 }}>
        {msgs.length > 1 && cur && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5, textAlign: "left" }}>
            {cur.Status === "context" ? "You replied" : cur.FromName || cur.FromEmail} · {fmtDateTime(cur.SentAt)}
            {cur.Subject ? ` — ${cur.Subject}` : ""}
          </Typography>
        )}
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, maxHeight: maxH, overflow: "auto", textAlign: "left" }}>
          {cleanText(cur?.BodyText) || fallback || "…"}
        </Typography>
      </Box>
    </>
  );
};

// The pending draft text for this message's review - stored on the review row in the
// standalone (FanApp pulled it from a responder run; keep that as the fallback).
const pendingDraft = (detail, open) => {
  const rv = (detail.reviews || []).find((r) => r.ReviewId === open.ReviewId);
  if (rv?.DraftText) return rv.DraftText;
  const run = (detail.runs || []).find((r) => r.AgentName === "responder" && r.Status === "done");
  return run?.Result || "";
};

const DrawerBlock = ({ title, children }) => (
  <Box sx={{ mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>{title}</Typography>
    <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.25, mt: 0.5 }}>{children}</Box>
  </Box>
);

const ReviewActions = ({ reviewId, kind, draft, editText, setEditText, decide }) => (
  <Box>
    {kind !== "escalation" && (
      <TextField fullWidth multiline minRows={3} size="small" placeholder="Edit the draft (or approve as-is)"
        value={editText || draft} onChange={(e) => setEditText(e.target.value)} sx={{ mb: 1 }} />
    )}
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      {kind !== "escalation" && <Button size="small" variant="contained" onClick={() => decide(reviewId, "approve")}>Approve</Button>}
      {kind !== "escalation" && <Button size="small" variant="outlined" disabled={!editText.trim() || editText === draft}
        onClick={() => decide(reviewId, "edit", editText)}>Approve my edit</Button>}
      {kind !== "escalation" && <Button size="small" sx={{ color: "#8a94a6" }} onClick={() => decide(reviewId, "no_reply")}>
        No reply needed
      </Button>}
      <Button size="small" color="error" onClick={() => decide(reviewId, "reject")}>
        {kind === "escalation" ? "Dismiss — I handled it" : "Reject"}
      </Button>
    </Box>
  </Box>
);
