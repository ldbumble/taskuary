// Task Hub shell - clean light enterprise workspace, compact: slim top bar, pill tabs,
// content underneath. Five spaces: Timeline, Tasks, Review, Connectors, Settings.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Badge, Box, IconButton, Tooltip, Typography } from "@mui/material";
import { ThemeProvider, CssBaseline } from "@mui/material";
import HubIcon from "@mui/icons-material/Hub";
import RefreshIcon from "@mui/icons-material/Refresh";
import api from "./api";
import { theme, BG, BORDER, DIM, INK, PANEL, GRADIENT } from "./theme.jsx";
import FeedView from "./FeedView.jsx";
import BoardView from "./BoardView.jsx";
import TasksView from "./TasksView.jsx";
import ReviewView from "./ReviewView.jsx";
import ConnectorsView from "./ConnectorsView.jsx";
import ReportsView from "./ReportsView.jsx";
import DocsView from "./DocsView.jsx";
import SettingsView from "./SettingsView.jsx";

const TABS = ["Timeline", "Board", "Tasks", "Review", "Reports", "Connectors", "Docs", "Settings"];

function ServerVersion() {
  const [v, setV] = useState(null);
  useEffect(() => { api.get("/api/version").then(({ data }) => setV(data)).catch(() => {}); }, []);
  if (!v) return null;
  return (
    <Tooltip title={`server started ${v.started} — if this version looks old, restart taskuary`}>
      <Typography variant="caption" sx={{ color: "#98a1b3", fontFamily: "Consolas, monospace", fontSize: 10.5 }}>
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

  // Leaving a tab and coming back used to land you at the TOP of it. Nothing scrolled the
  // page: the tall tab unmounted, the document shrank to the short one, and the browser
  // clamped scrollY to 0 - by the time the tall tab came back there was no position left to
  // return to. So each tab remembers where it was, and gets it back on the way in. (The
  // second pass covers a tab that fetches its list on mount: on the switching frame it has
  // no height yet, so the first scrollTo has nothing to scroll to.)
  const scrollAt = useRef({});
  const go = (t) => { scrollAt.current[tab] = window.scrollY; setTab(t); };
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
  const openTask = (taskId, opts) => {
    setSelectedTask(taskId); go("Tasks");
    setAutostart(opts?.start ? { taskId, agent: opts.agent, model: opts.model } : null);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* textAlign left kills the CRA-default .App { text-align: center } leaking in */}
      <Box sx={{ minHeight: "100vh", bgcolor: BG, textAlign: "left" }}>
        {/* ── slim top bar ───────────────────────────────────────────── */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 2.5, py: 1,
          bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, zIndex: 10 }}>
          <Box sx={{ width: 26, height: 26, borderRadius: 1.5, background: GRADIENT, display: "flex",
            alignItems: "center", justifyContent: "center" }}>
            <HubIcon sx={{ color: "#fff", fontSize: 17 }} />
          </Box>
          <Typography sx={{ fontWeight: 800, fontSize: 14.5, color: INK, letterSpacing: 0.2 }}>Taskuary</Typography>
          <Typography variant="caption" noWrap sx={{ color: DIM, display: { xs: "none", lg: "block" } }}>
            everything in → one funnel → agents + you
          </Typography>
          <ServerVersion />

          <Box sx={{ display: "flex", gap: 0.5, ml: 3 }}>
            {TABS.map((t) => (
              <Badge key={t} color="warning" badgeContent={t === "Review" ? pending : 0} max={99}
                sx={{ "& .MuiBadge-badge": { fontSize: 9.5, height: 15, minWidth: 15 } }}>
                <Box onClick={() => go(t)}
                  sx={{ px: 1.5, py: 0.5, borderRadius: 99, cursor: "pointer", fontSize: 12.5, fontWeight: 600,
                    color: tab === t ? "#4f46e5" : DIM, bgcolor: tab === t ? "#eef0ff" : "transparent",
                    border: `1px solid ${tab === t ? "#c9cff0" : "transparent"}`,
                    transition: "all .15s", "&:hover": { color: INK, bgcolor: tab === t ? "#eef0ff" : "#f1f3f6" } }}>
                  {t}
                </Box>
              </Badge>
            ))}
          </Box>
          <Box sx={{ flex: 1 }} />
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => setTick(tick + 1)}><RefreshIcon sx={{ fontSize: 17, color: DIM }} /></IconButton>
          </Tooltip>
        </Box>

        <Box sx={{ p: { xs: 1.5, md: 2.5 } }}>
          {tab === "Timeline" && <FeedView key={`f${tick}`} onOpenTask={openTask} onChanged={refreshPending} />}
          {tab === "Board" && <BoardView key={`b${tick}`} onOpenTask={openTask} />}
          {everTasks && (
            <Box sx={{ display: tab === "Tasks" ? "block" : "none" }}>
              <TasksView key={`t${tick}`} selected={selectedTask} onSelect={setSelectedTask}
                onChanged={refreshPending} autostart={autostart} onAutostarted={() => setAutostart(null)}
                onGoReview={() => { refreshPending(); go("Review"); }} />
            </Box>
          )}
          {tab === "Review" && <ReviewView key={`r${tick}`} onOpenTask={openTask} onChanged={refreshPending} />}
          {tab === "Reports" && <ReportsView key={`rp${tick}`} />}
          {tab === "Connectors" && <ConnectorsView key={`c${tick}`} />}
          {tab === "Docs" && <DocsView key={`d${tick}`} />}
          {tab === "Settings" && <SettingsView key={`s${tick}`} />}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
