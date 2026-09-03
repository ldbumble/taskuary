// Task Hub shell - clean light enterprise workspace, compact: slim top bar, pill tabs,
// content underneath. Five spaces: Timeline, Tasks, Review, Connections, Settings.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Badge, Box, Button, CircularProgress, IconButton, MenuItem, Popover, Select, Snackbar, Tooltip, Typography } from "@mui/material";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import { pollWhileVisible } from "./visible.js";
import { holdLive } from "./live.js";
import { ThemeProvider, CssBaseline } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import api from "./api";
import { track } from "./demoTrack";
import { theme, ACCENT, ALERT, BG, BORDER, DIM, FAINT, INK, PANEL, GRADIENT } from "./theme.jsx";
import FeedView from "./FeedView.jsx";
import BoardView from "./BoardView.jsx";
const HubView = React.lazy(() => import("./HubView.jsx"));
import TasksView from "./TasksView.jsx";
import ReviewView from "./ReviewView.jsx";
import ConnectorsView from "./ConnectorsView.jsx";
import ReportsView from "./ReportsView.jsx";
import DocsView from "./DocsView.jsx";
import SettingsView from "./SettingsView.jsx";
import { SetupChip, SetupPanel, useSetup } from "./SetupWizard.jsx";
import { DEMO } from "./demoApi.js";
import { loadedAsset, staleWhat } from "./staleBuild.js";
import { useHandRaise, playSound, desktopNotify } from "./handraise.js";
import { dismissHandRaise, enqueueHandRaise, handRaiseWhat, isWatchingTask } from "./handraiseState.js";
import { TaskuaryMark } from "./ui.jsx";
import FloatingAssistant from "./FloatingAssistant.jsx";
import AssistantView from "./AssistantView.jsx";

// The strip reads left to right as the day does: what arrived (Timeline), what is being worked
// (Board, Tasks), what is waiting on you (Review), then what has been WRITTEN DOWN - Reports and
// Hub, which holds hard-earned discoveries and developed company ideas - and last the plumbing.
// Hub was next to Board first, which put a slow surface in the middle of
// the two fast ones. Nine tabs is the most this strip holds at a readable size; the next one has
// to displace something.
//
// Review stays even though a draft reply also shows on the Timeline: a proposal (proposals.py,
// Kind 'action') carries no MessageId, so it has no Timeline row to live on. Drop this tab and an
// agent asking permission has nowhere to ask.
// Assistant first: it is where the day starts now - Taskuary walks you through the pipe, and the
// other tabs are where you go to see the whole of something (AssistantView.jsx, funnel.py).
const TABS = ["Timeline", "Board", "Tasks", "Review", "Assistant", "Reports", "Hub", "Connections", "Docs", "Settings"];
const SUPPORT_URL = "https://github.com/ldbumble/taskuary/issues/new/choose";

// The bell: what is FAILING right now - a connector whose poll errors, the triage brain down, a
// report that failed today - each with the way to where it is fixed. The setup chip beside it says
// what is not yet set up; this says what was working and is not. Grey and quiet when nothing is.
function Bell({ onGo }) {
  const [items, setItems] = useState([]);
  const [el, setEl] = useState(null);
  const [busy, setBusy] = useState(null);
  const load = useCallback(async () => { try { setItems((await api.get("/api/problems")).data.data || []); } catch { /* the bell is optional */ } }, []);
  useEffect(() => pollWhileVisible(load, 30000), [load]);
  const n = items.length;
  return (
    <>
      <Tooltip title={n ? `${n} thing${n === 1 ? "" : "s"} failing — click to see` : "Nothing is failing"}>
        <IconButton size="small" onClick={(e) => { setEl(e.currentTarget); load(); }} sx={{ position: "relative" }}>
          {n ? <NotificationsActiveIcon sx={{ fontSize: 18, color: ALERT }} /> : <NotificationsNoneIcon sx={{ fontSize: 18, color: DIM }} />}
          {n > 0 && (
            <Box component="span" sx={{ position: "absolute", top: 1, right: 1, minWidth: 14, height: 14, px: 0.3, borderRadius: 99,
              bgcolor: ALERT, color: "#fffdfb", fontSize: 9, fontWeight: 700, display: "grid", placeItems: "center", lineHeight: 1 }}>
              {n > 9 ? "9+" : n}
            </Box>
          )}
        </IconButton>
      </Tooltip>
      <Popover open={!!el} anchorEl={el} onClose={() => setEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 440, p: 1.5, mt: 0.5 } } }}>
        <Typography sx={{ fontWeight: 700, fontSize: 13, color: INK, mb: n ? 0.25 : 0.5 }}>{n ? "Failing right now" : "Nothing is failing"}</Typography>
        {!n && <Typography variant="caption" sx={{ color: DIM, display: "block" }}>Every connection polled clean, the triage brain answered, no report failed today. Anything you dismissed comes back if it happens again.</Typography>}
        {items.map((p) => (
          <Box key={p.key} sx={{ py: 0.85, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1.25, alignItems: "flex-start" }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 650, color: INK, fontSize: 12.5 }}>{p.title}</Typography>
              <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.45, wordBreak: "break-word" }}>{p.detail}</Typography>
              {p.since && <Typography variant="caption" sx={{ color: FAINT }}>last tried {p.since}</Typography>}
            </Box>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.4, alignItems: "stretch", flexShrink: 0 }}>
              <Button size="small" variant="outlined" sx={{ fontSize: 11, whiteSpace: "nowrap" }}
                onClick={() => { setEl(null); onGo(p); }}>{p.fix || "Fix"} →</Button>
              {/* Reading it, not fixing it. It comes back the moment the same thing fails again
                  (problems.signature), so this quiets something you have decided to live with. */}
              <Button size="small" disabled={busy === p.key} sx={{ fontSize: 10.5, color: FAINT, textTransform: "none" }}
                title="I have read this. It returns if it happens again."
                onClick={async () => {
                  setBusy(p.key);
                  try { await api.post(`/api/problems/${encodeURIComponent(p.key)}/dismiss`); } catch { /* it may have cleared itself */ }
                  await load(); setBusy(null);
                }}>{busy === p.key ? "…" : "Dismiss"}</Button>
            </Box>
          </Box>
        ))}
      </Popover>
    </>
  );
}

/* The tab can be older than the app. Taskuary updates underneath an open page - a pull and a
   rebuild, pip install -U, the coding agent shipping its own fix - and the page keeps running
   the bundle it loaded hours ago. Every symptom of that looks like a bug that was already
   fixed. This is the only honest way to tell the difference from inside the page, so it says
   so, quietly, and reloads only when asked. */
/* A demo has to SAY so - a visitor clicking Approve on an invented refund should never wonder
   for a second whether it went anywhere. It never does: demo.py refuses at the API layer. */
function useDemo() {
  const [demo, setDemo] = useState(null);
  useEffect(() => { api.get("/api/demo").then(({ data }) => setDemo(data)).catch(() => {}); }, []);
  return demo?.demo ? demo : null;
}

/* One word and a dot. It said "demo · invented data · you are Dana Whitfield", which is 250px
   of left-hand flow - and the tab strip above xl is centred on the WINDOW, so the sentence ran
   underneath the tabs. What it has to do is answer "is any of this real?" at a glance; the rest
   of the sentence is what a tooltip is for. */
function DemoBadge({ demo }) {
  if (!demo) return null;
  return (
    <Tooltip title={`Everything here is invented${demo.owner ? ` - you are ${demo.owner}, who does not exist` : ""}: the people, the mail, the agents. Nothing sends, nothing connects, and no real system is reachable from this page.`}>
      <Box sx={{ display: { xs: "none", sm: "flex" }, alignItems: "center", gap: 0.5, px: 0.9, py: 0.3, borderRadius: 99,
        flexShrink: 0, border: "1px solid #d8cfbe", bgcolor: "#f1ead9" }}>
        <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#8a7a5c" }} />
        <Typography variant="caption" noWrap sx={{ fontWeight: 700, color: "#6b5f45" }}>demo data</Typography>
      </Box>
    </Tooltip>
  );
}

function StaleBuild() {
  const [stale, setStale] = useState("");
  useEffect(() => {
    // the static demo IS a recording: its /api/build is whatever the instance it was dumped
    // from was running, which is not a newer version of anything
    if (import.meta.env.VITE_DEMO === "1") return undefined;
    const mine = loadedAsset();
    const check = () => api.get("/api/build")
      .then(({ data }) => setStale(staleWhat(mine, data))).catch(() => {});
    check();
    const t = setInterval(check, 60000);
    return () => clearInterval(t);
  }, []);
  if (!stale) return null;
  const restart = /restart/.test(stale);
  return (
    <Tooltip title={restart ? "pyproject.toml carries a newer version than this server started with - the header, the API and the CLI all report the old one until Taskuary is restarted. Nothing is lost by restarting."
      : "Taskuary has been updated on disk since this page was opened. Nothing is lost by reloading."}>
      <Box onClick={() => !restart && window.location.reload()}
        sx={{ display: "flex", alignItems: "center", gap: 0.6, cursor: restart ? "default" : "pointer", px: 1, py: 0.3,
          borderRadius: 99, border: "1px solid #d8cfbe", bgcolor: "#f1ead9" }}>
        <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#6f8a6e" }} />
        <Typography variant="caption" sx={{ fontWeight: 700, color: "#55697a" }}>{stale}</Typography>
      </Box>
    </Tooltip>
  );
}

function ServerVersion() {
  const [v, setV] = useState(null);
  useEffect(() => { api.get("/api/version").then(({ data }) => setV(data)).catch(() => {}); }, []);
  if (!v) return null;
  return (
    <Tooltip title={`server started ${v.started} — if this version looks old, restart taskuary`}>
      <Typography variant="caption" sx={{ color: "#a9a294", fontFamily: "Consolas, monospace", fontSize: 10.5,
        display: { xs: "none", md: "block" } }}>
        v{v.version}
      </Typography>
    </Tooltip>
  );
}

export default function TaskHubPage() {
  const [tab, setTab] = useState("Assistant");
  const demo = useDemo();          // the badge, and what the header hides to make room for it
  useEffect(() => holdLive(), []);
  const [selectedTask, setSelectedTask] = useState(null);
  const [pending, setPending] = useState(0);
  const [tick, setTick] = useState(0);
  // the counter, and the panel it opens
  const [setup, reloadSetup] = useSetup(tick);
  const [setupOpen, setSetupOpen] = useState(false);
  const [greeted, setGreeted] = useState(false);
  // the agent raised its hand: sound + desktop notification + a toast with the way to it.
  // The toast queues immediately; settings are read only for sound/desktop delivery. Making the
  // visible notification wait on that request made it appear at arbitrary times on a busy server.
  const [raisedQueue, setRaisedQueue] = useState([]);
  const raised = raisedQueue[0] || null;
  const tabRef = useRef("Assistant"), selRef = useRef(null);
  const selectTask = useCallback((tid) => { setSelectedTask(tid); selRef.current = tid; }, []);
  const onRaise = useCallback((r) => {
    // already looking at this very task's session: no ring, you are watching it stop
    if (isWatchingTask(tabRef.current, selRef.current, r.tid)) return;
    const what = handRaiseWhat(r);
    setRaisedQueue((q) => enqueueHandRaise(q, { ...r, what }));
    (async () => {
      let sound = "chime", desktop = true;
      try {
        const { data } = await api.get("/api/settings", { timeout: 2000 });
        const v = (k, d) => { const row = (data.data || data || []).find?.((x) => x.Name === k); return row ? row.Value : d; };
        sound = v("hand_sound", "chime"); desktop = v("hand_desktop", "1") === "1";
      } catch { /* defaults */ }
      // The toast was immediate. If the owner opened the task while settings loaded, a late
      // sound or OS popup would be noise and would look unrelated to the thing now on screen.
      if (isWatchingTask(tabRef.current, selRef.current, r.tid)) return;
      playSound(sound);
      if (desktop) desktopNotify(`${r.ref} · ${what}`, r.title || r.tail || "", () => openTask(r.tid));
    })();
  }, []);
  useHandRaise(onRaise);
  // a first run opens it once, unprompted: somebody who has just installed this should not have
  // to find the checklist. Once put away (or once required steps are done) it never opens itself.
  useEffect(() => {
    if (DEMO || demo || greeted || !setup || setup.ready || setup.dismissed) return;
    if (setup.done === 0) setSetupOpen(true);
    setGreeted(true);
  }, [setup, greeted, demo]);
  const dismissSetup = async (d) => {
    await api.post("/api/setup/dismiss", { dismissed: d });
    reloadSetup();
    if (d) setSetupOpen(false);
  };

  // Leaving a tab and coming back used to land you at the TOP of it. Nothing scrolled the
  // page: the tall tab unmounted, the document shrank to the short one, and the browser
  // clamped scrollY to 0 - by the time the tall tab came back there was no position left to
  // return to. So each tab remembers where it was, and gets it back on the way in. (The
  // second pass covers a tab that fetches its list on mount: on the switching frame it has
  // no height yet, so the first scrollTo has nothing to scroll to.)
  const scrollAt = useRef({});
  // clicking the tab you are already on is "take me back to the top of it": the view remounts
  // to its landing (Connectors out of a card, Settings to its first page) instead of doing nothing
  const [reset, setReset] = useState(0);
  const go = (t) => {
    if (t === tab) { scrollAt.current[t] = 0; window.scrollTo(0, 0); setReset((r) => r + 1); return; }
    scrollAt.current[tab] = window.scrollY; setTab(t); tabRef.current = t;
    track("tab", t);
  };
  useLayoutEffect(() => {
    const y = scrollAt.current[tab] || 0;
    if (!y) return;
    window.scrollTo(0, y);
    const id = requestAnimationFrame(() => window.scrollTo(0, y));
    return () => cancelAnimationFrame(id);
  }, [tab]);

  // ...and Tasks, once opened, stays MOUNTED behind the other tabs. It is the one space
  // holding a live pty: unmounting it dropped the websocket, so every trip to the Board and
  // back rebuilt the pane and redrew the CLI's screen from the top of its scrollback. Hidden
  // is enough - fit() reads a display:none pane as NaN and skips, then refits on the way back.
  const [everTasks, setEverTasks] = useState(false);
  const [everTimeline, setEverTimeline] = useState(false);
  const [everAssistant, setEverAssistant] = useState(true);   // the landing tab: mounted from the first paint
  const [everBoard, setEverBoard] = useState(false);
  useEffect(() => { if (tab === "Tasks") setEverTasks(true); }, [tab]);
  // ...and the two views that can hold a live session: mounted once opened, hidden after
  useEffect(() => { if (tab === "Timeline") setEverTimeline(true); if (tab === "Board") setEverBoard(true); if (tab === "Assistant") setEverAssistant(true); }, [tab]);

  const refreshPending = useCallback(async () => {
    try { setPending(((await api.get("/api/reviews", { params: { status: "pending" } })).data.data || []).length); }
    catch { /* badge is optional */ }
  }, []);
  useEffect(() => { refreshPending(); }, [refreshPending, tick]);

  // A terminal belongs to the task it is working - there is no dock and no terminal tab.
  // Opening a task with start=true means "and put your CLI on it now".
  const [autostart, setAutostart] = useState(null);
  // #task=123 opens that task - the digest's links, a chat ping, a bookmark
  useEffect(() => {
    const fromHash = () => {
      const m = /task=(\d+)/.exec(window.location.hash || ""); if (m) openTask(Number(m[1]));
      // a card's "open on the Timeline": FeedView reads the same hash and opens the row
      if (/^#msg=\d+/.test(window.location.hash || "")) go("Timeline");
      // a connector card's playbook link: the words live on the Docs tab (DocsView reads the hash itself)
      if (/playbook=/.test(window.location.hash || "")) go("Docs");
    };
    fromHash(); window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const openTask = (taskId, opts) => {
    selectTask(taskId); go("Tasks");
    setAutostart(opts?.start ? { taskId, agent: opts.agent, model: opts.model } : null);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* textAlign left kills the CRA-default .App { text-align: center } leaking in */}
      <Box sx={{ minHeight: "100vh", bgcolor: BG, textAlign: "left" }}>
        {/* bottom-right, not under the top bar: up there it covered the row every tab keeps its
            actions on (the Board's buttons, a task's Mark done) for twelve seconds per hand raised */}
        {/* ...and not on the Assistant tab: the pipe and its by-the-way line already carry a raised hand */}
        <Snackbar key={raised?.eventId || "no-hand-raised"} open={!!raised && tab !== "Assistant"} autoHideDuration={12000}
          onClose={() => setRaisedQueue(dismissHandRaise)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          sx={{ mb: 8 }}
          message={raised ? `${raised.ref} · ${raised.what}${raised.title ? ` — ${raised.title}` : ""}` : ""}
          action={raised && <Button size="small" sx={{ color: ACCENT, fontWeight: 700 }} onClick={() => { openTask(raised.tid); setRaisedQueue(dismissHandRaise); }}>Open</Button>} />
        {/* ── slim top bar ───────────────────────────────────────────── */}
        {/* Full width, deliberately. Constraining this to the page column squeezed the tab strip
            until its overflowX put a horizontal SCROLLBAR under the nav - a slider you have to
            drag to reach Settings - and pushed the whole page into horizontal scroll with it. A
            nav bar is chrome; it spans. */}
        {/* id + top z: the Timeline's frozen dock pins itself right below this bar (it measures
            the height by id) - z above the dock so nothing ever slides over the tabs */}
        <Box id="tqTopNav" sx={{ display: "flex", alignItems: "center", gap: { xs: 0.75, md: 1.25 },
          px: { xs: 1.25, md: 2.5 }, py: 1,
          bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, zIndex: 30 }}>
          <Box sx={{ width: 26, height: 26, borderRadius: 1.5, background: GRADIENT, display: "flex",
            alignItems: "center", justifyContent: "center" }}>
            <TaskuaryMark size={22} />
          </Box>
          <Typography sx={{ fontWeight: 800, fontSize: 14.5, color: INK, letterSpacing: 0.2 }}>Taskuary</Typography>
          {/* the tagline waits for xl. Below that its width is what pushed the tab strip off true
              centre, and the tabs are the thing people aim at all day - a strapline is not. */}
          <Typography variant="caption" noWrap sx={{ color: DIM, display: demo ? "none" : { xs: "none", xl: "block" } }}>
            everything in → one funnel → agents + you
          </Typography>
          <ServerVersion />
          <DemoBadge demo={demo} />

          {/* Below 900px the full tab strip had no room: it began under the brand and its
              off-screen pages had no visible affordance. One labelled selector keeps the
              current page and every destination reachable without a mystery swipe. */}
          <Select size="small" value={tab} onChange={(e) => go(e.target.value)}
            inputProps={{ "aria-label": "Taskuary page" }}
            sx={{ display: { xs: "flex", md: "none" }, height: 30, minWidth: 0,
              width: { xs: 112, sm: 160 }, ml: 0.25, bgcolor: "#f4efe6", borderRadius: 99,
              color: "#55697a", fontSize: 12, fontWeight: 700,
              "& .MuiSelect-select": { py: 0.4, pl: 1.25, pr: "28px !important" },
              "& .MuiOutlinedInput-notchedOutline": { borderColor: "#d8cfbe" } }}>
            {TABS.map((t) => (
              <MenuItem key={t} value={t} sx={{ fontSize: 12.5, fontWeight: t === "Assistant" ? 800 : 400 }}>
                {t === "Assistant" ? "✦ Taskuary" : t}{t === "Review" && pending > 0 ? ` · ${pending > 99 ? "99+" : pending}` : ""}
              </MenuItem>
            ))}
          </Select>

          {/* Centred on the WINDOW, not in the space left over. Two flex spacers would centre it
              between the brand and the counter, which lands well right of true centre because
              those two blocks are nothing like the same width - so it is absolute, from md up.
              It used to wait for xl (1536px) out of a fear of overlapping the tagline, which
              meant that at every ordinary window size the tabs sat wherever the brand happened
              to end. The tagline is the thing that yields now (it waits for xl); the tabs are
              what people aim at all day and they stay put. pointerEvents on the wrapper so the
              absolute strip cannot swallow clicks meant for the chrome behind it. */}
          <Box sx={{ display: { xs: "none", md: "flex" }, gap: 0.5, minWidth: 0, overflowX: "auto",
            position: "absolute", left: "50%", transform: "translateX(-50%)",
            maxWidth: { md: "58%", xl: "62%" }, pointerEvents: "auto" }}>
            {TABS.map((t) => t === "Assistant" ? (
              // the Assistant sits in the MIDDLE of the strip wearing the mark: it is the main way through the
              // day now, and the other tabs are where you go to see the whole of something
              <Box key={t} onClick={() => go(t)} title="Taskuary — your assistant walks you through what needs you"
                sx={{ display: "flex", alignItems: "center", gap: 0.7, px: 1.6, py: 0.35, mx: 0.5, borderRadius: 99, cursor: "pointer",
                  fontSize: 13, fontWeight: 800, whiteSpace: "nowrap", color: tab === t ? "#fff" : "#41525f",
                  background: tab === t ? GRADIENT : "#e4e9ee", border: `1px solid ${tab === t ? "transparent" : "#cbd4dc"}`,
                  boxShadow: tab === t ? "0 4px 14px rgba(69,79,70,.28)" : "none", transition: "all .15s",
                  "&:hover": { boxShadow: "0 4px 14px rgba(69,79,70,.22)" } }}>
                <TaskuaryMark size={18} />{t}
              </Box>
            ) : (
              // the count rides INSIDE the pill. A MUI Badge hangs outside its child's box, and
              // this strip is overflowX:auto - so the number was being clipped by the scroller
              // it sits in, which is how "Review 1" showed up as a half-eaten dot.
              <Box key={t} onClick={() => go(t)}
                sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 1.5, py: 0.5, borderRadius: 99,
                  cursor: "pointer", fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap",
                  color: tab === t ? "#55697a" : DIM, bgcolor: tab === t ? "#eae4d8" : "transparent",
                  border: `1px solid ${tab === t ? "#d8cfbe" : "transparent"}`,
                  transition: "all .15s", "&:hover": { color: INK, bgcolor: tab === t ? "#eae4d8" : "#e9e3d8" } }}>
                {t}
                {t === "Review" && pending > 0 && (
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", justifyContent: "center",
                    minWidth: 16, height: 16, px: 0.45, borderRadius: 99, bgcolor: ALERT, color: "#fffdfb",
                    fontSize: 9.5, fontWeight: 700 }}>{pending > 99 ? "99+" : pending}</Box>
                )}
              </Box>
            ))}
          </Box>
          <Box sx={{ flex: 1 }} />
          {/* on the RIGHT, with the other transient chrome. On the left it grew the brand cluster
              until it slid UNDER the tab strip, which is absolutely centred on the window and so
              yields to nothing - the banner sat on top of "Timeline". */}
          <StaleBuild />
          {!DEMO && !demo && <SetupChip state={setup} onOpen={() => setSetupOpen(true)} />}
          <Tooltip title="Support — report a problem or attach screenshots on GitHub">
            <IconButton component="a" href={SUPPORT_URL} target="_blank" rel="noopener noreferrer"
              size="small" aria-label="Taskuary support and issue reporting">
              <HelpOutlineIcon sx={{ fontSize: 17, color: DIM }} />
            </IconButton>
          </Tooltip>
          {/* the Fix button lands on the card itself: Connectors reads #connector=<type> on the way in */}
          <Bell onGo={(p) => { if (p.connector) window.location.hash = `connector=${p.connector}`; go(p.where || "Connections"); }} />
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => setTick(tick + 1)}><RefreshIcon sx={{ fontSize: 17, color: DIM }} /></IconButton>
          </Tooltip>
        </Box>

        {!DEMO && !demo && (
          <SetupPanel open={setupOpen} state={setup} onClose={() => { setSetupOpen(false); reloadSetup(); }}
            onDismiss={dismissSetup} onRefresh={reloadSetup}
            onGo={(where) => { setSetupOpen(false); go(where); }} />
        )}

        {/* tighter side padding than top/bottom: the horizontal margin is dead space on a wide
            window, and every tab inside already caps its own content width where it wants to */}
        <Box sx={{ px: { xs: 1.5, md: 1.75 }, py: { xs: 1.5, md: 2.25 } }}>
          {/* Timeline and Board stay MOUNTED behind another tab, like Tasks: each can hold a live
              pty session, and unmounting closed its websocket - so coming back replayed the whole
              scrollback and ran the pane top to bottom. Their polling is gated on `active`. */}
          {/* the Assistant stays mounted too: its conversation and the pipe's animation state are
              on screen state worth keeping, and its polling is gated on `active` */}
          {(everAssistant || tab === "Assistant") && (
            <Box sx={{ display: tab === "Assistant" ? "block" : "none" }}>
              <AssistantView key={`a${tick}`} onOpenTask={openTask} onNavigate={go} active={tab === "Assistant"} />
            </Box>
          )}
          {(everTimeline || tab === "Timeline") && (
            <Box sx={{ display: tab === "Timeline" ? "block" : "none" }}>
              <FeedView key={`f${tick}`} onOpenTask={openTask} onChanged={refreshPending} active={tab === "Timeline"} />
            </Box>
          )}
          {(everBoard || tab === "Board") && (
            <Box sx={{ display: tab === "Board" ? "block" : "none" }}>
              <BoardView key={`b${tick}`} onOpenTask={openTask}
              onOpenReports={(sid) => { window.location.hash = `report=${sid}`; go("Reports"); }} active={tab === "Board"} />
            </Box>
          )}
          {everTasks && (
            <Box sx={{ display: tab === "Tasks" ? "block" : "none" }}>
              <TasksView key={`t${tick}`} selected={selectedTask} onSelect={selectTask} active={tab === "Tasks"}
                onChanged={refreshPending} autostart={autostart} onAutostarted={() => setAutostart(null)}
                onGoReview={() => { refreshPending(); go("Review"); }}
                onGoReports={(sid) => { window.location.hash = `report=${sid}`; go("Reports"); }} />
            </Box>
          )}
          {tab === "Hub" && (
            <React.Suspense fallback={<CircularProgress size={22} sx={{ m: 4 }} />}>
              <HubView key={`hub${tick}`} onOpenTask={openTask} />
            </React.Suspense>
          )}
          {tab === "Review" && <ReviewView key={`r${tick}`} onOpenTask={openTask} onChanged={refreshPending} />}
          {tab === "Reports" && <ReportsView key={`rp${tick}-${reset}`} />}
          {tab === "Connections" && <ConnectorsView key={`c${tick}-${reset}`} />}
          {tab === "Docs" && <DocsView key={`d${tick}-${reset}`} />}
          {tab === "Settings" && <SettingsView key={`s${tick}-${reset}`} />}
        </Box>
        {/* the bubble is the same assistant; on its own page it would be a second chat over the first */}
        {tab !== "Assistant" && <FloatingAssistant onNavigate={go} onChanged={refreshPending} activeTab={tab} />}
      </Box>
    </ThemeProvider>
  );
}
