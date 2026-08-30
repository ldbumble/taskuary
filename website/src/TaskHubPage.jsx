// Task Hub shell - clean light enterprise workspace, compact: slim top bar, pill tabs,
// content underneath. Five spaces: Timeline, Tasks, Review, Connectors, Settings.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Badge, Box, Button, IconButton, Snackbar, Tooltip, Typography } from "@mui/material";
import { ThemeProvider, CssBaseline } from "@mui/material";
import HubIcon from "@mui/icons-material/Hub";
import RefreshIcon from "@mui/icons-material/Refresh";
import api from "./api";
import { theme, ALERT, BG, BORDER, DIM, INK, PANEL, GRADIENT } from "./theme.jsx";
import FeedView from "./FeedView.jsx";
import BoardView from "./BoardView.jsx";
import TasksView from "./TasksView.jsx";
import ReviewView from "./ReviewView.jsx";
import ConnectorsView from "./ConnectorsView.jsx";
import ReportsView from "./ReportsView.jsx";
import DocsView from "./DocsView.jsx";
import SettingsView from "./SettingsView.jsx";
import { SetupChip, SetupPanel, useSetup } from "./SetupWizard.jsx";
import { useHandRaise, playSound, desktopNotify } from "./handraise.js";
import { dismissHandRaise, enqueueHandRaise, handRaiseWhat, isWatchingTask } from "./handraiseState.js";

const TABS = ["Timeline", "Board", "Tasks", "Review", "Reports", "Connectors", "Docs", "Settings"];

function ServerVersion() {
  const [v, setV] = useState(null);
  useEffect(() => { api.get("/api/version").then(({ data }) => setV(data)).catch(() => {}); }, []);
  if (!v) return null;
  return (
    <Tooltip title={`server started ${v.started} — if this version looks old, restart taskuary`}>
      <Typography variant="caption" sx={{ color: "#a9a294", fontFamily: "Consolas, monospace", fontSize: 10.5 }}>
        v{v.version}
      </Typography>
    </Tooltip>
  );
}

export default function TaskHubPage() {
  const [tab, setTab] = useState("Timeline");
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
  const tabRef = useRef("Timeline"), selRef = useRef(null);
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
    if (greeted || !setup || setup.ready || setup.dismissed) return;
    if (setup.done === 0) setSetupOpen(true);
    setGreeted(true);
  }, [setup, greeted]);
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
  useEffect(() => { if (tab === "Tasks") setEverTasks(true); }, [tab]);

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
    const fromHash = () => { const m = /task=(\d+)/.exec(window.location.hash || ""); if (m) openTask(Number(m[1])); };
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
        <Snackbar key={raised?.eventId || "no-hand-raised"} open={!!raised} autoHideDuration={12000}
          onClose={() => setRaisedQueue(dismissHandRaise)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          message={raised ? `${raised.ref} · ${raised.what}${raised.title ? ` — ${raised.title}` : ""}` : ""}
          action={raised && <Button size="small" sx={{ color: "#a6e3a1" }} onClick={() => { openTask(raised.tid); setRaisedQueue(dismissHandRaise); }}>Open</Button>} />
        {/* ── slim top bar ───────────────────────────────────────────── */}
        {/* Full width, deliberately. Constraining this to the page column squeezed the tab strip
            until its overflowX put a horizontal SCROLLBAR under the nav - a slider you have to
            drag to reach Settings - and pushed the whole page into horizontal scroll with it. A
            nav bar is chrome; it spans. */}
        {/* id + top z: the Timeline's frozen dock pins itself right below this bar (it measures
            the height by id) - z above the dock so nothing ever slides over the tabs */}
        <Box id="tqTopNav" sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 2.5, py: 1,
          bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, zIndex: 30 }}>
          <Box sx={{ width: 26, height: 26, borderRadius: 1.5, background: GRADIENT, display: "flex",
            alignItems: "center", justifyContent: "center" }}>
            <HubIcon sx={{ color: "#fff", fontSize: 17 }} />
          </Box>
          <Typography sx={{ fontWeight: 800, fontSize: 14.5, color: INK, letterSpacing: 0.2 }}>Taskuary</Typography>
          <Typography variant="caption" noWrap sx={{ color: DIM, display: { xs: "none", lg: "block" } }}>
            everything in → one funnel → agents + you
          </Typography>
          <ServerVersion />

          {/* Centred on the WINDOW, not in the space left over. Two flex spacers would centre it
              between the tagline and the counter, which lands well right of true centre because
              those two blocks are nothing like the same width. Absolute is the only thing that
              actually centres - and it can overlap, so it only applies above xl (1536px), where
              there is provably room for the tagline on one side and the tabs in the middle.
              Below that the old flow returns, which is what narrow windows always had. */}
          <Box sx={{ display: "flex", gap: 0.5, minWidth: 0, overflowX: "auto",
            position: { xs: "static", xl: "absolute" },
            left: { xl: "50%" }, transform: { xl: "translateX(-50%)" }, ml: { xs: 3, xl: 0 } }}>
            {TABS.map((t) => (
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
          <SetupChip state={setup} onOpen={() => setSetupOpen(true)} />
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => setTick(tick + 1)}><RefreshIcon sx={{ fontSize: 17, color: DIM }} /></IconButton>
          </Tooltip>
        </Box>

        <SetupPanel open={setupOpen} state={setup} onClose={() => { setSetupOpen(false); reloadSetup(); }}
          onDismiss={dismissSetup} onRefresh={reloadSetup}
          onGo={(where) => { setSetupOpen(false); go(where); }} />

        {/* tighter side padding than top/bottom: the horizontal margin is dead space on a wide
            window, and every tab inside already caps its own content width where it wants to */}
        <Box sx={{ px: { xs: 1.5, md: 1.75 }, py: { xs: 1.5, md: 2.25 } }}>
          {tab === "Timeline" && <FeedView key={`f${tick}`} onOpenTask={openTask} onChanged={refreshPending} />}
          {tab === "Board" && <BoardView key={`b${tick}`} onOpenTask={openTask} />}
          {everTasks && (
            <Box sx={{ display: tab === "Tasks" ? "block" : "none" }}>
              <TasksView key={`t${tick}`} selected={selectedTask} onSelect={selectTask} active={tab === "Tasks"}
                onChanged={refreshPending} autostart={autostart} onAutostarted={() => setAutostart(null)}
                onGoReview={() => { refreshPending(); go("Review"); }} />
            </Box>
          )}
          {tab === "Review" && <ReviewView key={`r${tick}`} onOpenTask={openTask} onChanged={refreshPending} />}
          {tab === "Reports" && <ReportsView key={`rp${tick}-${reset}`} />}
          {tab === "Connectors" && <ConnectorsView key={`c${tick}-${reset}`} />}
          {tab === "Docs" && <DocsView key={`d${tick}-${reset}`} />}
          {tab === "Settings" && <SettingsView key={`s${tick}-${reset}`} />}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
