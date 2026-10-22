// Task Hub shell - clean light enterprise workspace, compact: slim top bar, pill tabs,
// content underneath. The Assistant (the Timeline's rail + Taskuary's chat) in the middle,
// Board, Tasks and Reports to its left, Hub, Connections and Settings to its right.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Badge, Box, Button, CircularProgress, IconButton, MenuItem, Popover, Select, Snackbar, Tooltip, Typography } from "@mui/material";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import { pollWhileVisible } from "./visible.js";
import { holdLive, onLive } from "./live.js";
import { ThemeProvider, CssBaseline } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import GridViewIcon from "@mui/icons-material/GridViewOutlined";
import SportsEsportsIcon from "@mui/icons-material/SportsEsportsOutlined";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import api from "./api";
import { track } from "./demoTrack";
import { fmtStamp } from "./dates.js";
import { theme, ACCENT, ALERT, BG, BORDER, DIM, FAINT, INK, PANEL, GRADIENT, BRAND } from "./theme.jsx";
import { lazyView } from "./lazyView.jsx";
const BoardView = lazyView(() => import("./BoardView.jsx"));   // the Board is a tab away from the first screen
import { canvasRequestFromHash } from "./canvasLinks.js";
import { readLists } from "./connectorLists.js";
// a link to Connections asks for its lists the moment the address is read - not once the canvas, its chunk and Connections' own
// chunk have all come in (connectorLists.js: a cold #connector=whatsapp sent its first read ~1.4 s after the page was asked for)
const readAhead = (req) => { if (req?.kind === "browse" && req.area === "connections") readLists(api); };
import { onPlace, openAppLink } from "./appLinks.js";
import { restartBridge } from "./waBridge.js";
import { SetupChip, useSetup } from "./SetupWizard.jsx";
import { DEMO } from "./demoApi.js";
import { buildMove, isBusy, loadedAsset, markReloaded, reloadedFor, staleWhat } from "./staleBuild.js";
import { useHandRaise, playSound, desktopNotify } from "./handraise.js";
import { dismissHandRaise, enqueueHandRaise, handRaiseWhat, isWatchingTask } from "./handraiseState.js";
import { TaskuaryMark, asUtc, timeAgo } from "./ui.jsx";
import AssistantView from "./AssistantView.jsx";
import { SEARCH_PICKED, SearchBar, openSearch } from "./SearchEverything.jsx";
import BugReportDialog from "./BugReportDialog.jsx";
import { label as btnLabel } from "./buttons.js";
import { REPORT_EVENT, bellError, openBugReport } from "./bugReportOpen.js";
import { plural } from "./timeWords.js";
const AssistantGame = React.lazy(() => import("./AssistantGame.jsx"));

// The strip reads left to right as the day does: what arrived (Timeline), what is being worked
// (Board, Tasks), then what has been WRITTEN DOWN - Reports and Hub, which holds hard-earned
// discoveries and developed company ideas - and last the plumbing. Hub was next to Board first,
// which put a slow surface in the middle of the two fast ones. Nine tabs was the most this strip
// held at a readable size; it holds seven now, and the next one still has to displace something.
//
// THERE IS NO REVIEW TAB. It used to be here because a proposal (proposals.py, Kind 'action')
// carries no MessageId and so has no Timeline row of its own - but it does have a TASK, and the
// task page decides it now, in stage 3 beside the reply. Nothing is left needing a third place:
// work's decisions live on its task, and answering filed chatter - the one thing that never
// becomes a task - is decided in the Assistant, on the card that offered the reply.
// Its red count came with it and sits on Tasks, counting TASKS rather than reviews.
//
// Docs is not here either: it is a section of Settings, after About you. That also keeps the
// strip symmetric about the Assistant, three tabs to each side.
//
// The Assistant IS the Timeline: one tab, the Timeline's rail with the pipe at its top on the left
// and Taskuary's chat on the right (AssistantView.jsx, funnel.py). It wears the mark in the MIDDLE
// of the strip - what is being worked to the left of it, what has been written down and the
// plumbing to the right. "Timeline" as a destination still resolves to it (go()).
// THE CANVAS REDESIGN (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md): the tab strip is gone. The
// Assistant IS the app - its sidebar drives the work and its canvas shows a task, an agent, a connector, a setting or a
// report inside the conversation - and the Board, the agents and their wall, is the one full-screen view, reached from the
// top bar. Every old destination still lands: go("Connections") and #connector=... open that card in the canvas.
const VIEWS = ["Assistant", "Board"];
const BROWSED = { Reports: "reports", Connections: "connections", Settings: "settings", Hub: "hub" };
const DEMO_SETUP = { left: 0 };      // the static demo: nothing to finish, so the plain Setup pill the finished app shows
const SUPPORT_URL ="https://github.com/ldbumble/taskuary/issues/new/choose";

// The bell: what is FAILING right now - a connector whose poll errors, the triage brain down, a
// report that failed - in the last few hours (problems.STALE_HOURS) - each with the way to where it is fixed. The setup chip beside it says
// what is not yet set up; this says what was working and is not. Grey and quiet when nothing is.
// "3h ago" alone hides a day boundary: the clock time says which morning
const fmtWhen = (s) => fmtStamp(asUtc(s), [], { weekday: "short", hour: "numeric", minute: "2-digit" });
function Bell({ onGo }) {
  const [items, setItems] = useState([]);
  const [el, setEl] = useState(null);
  const [busy, setBusy] = useState(null);
  // news: something that ENDED on its own - "Back on. 14 came in, 2 need you." (problems.news). A quiet dot, never the red count.
  const [news, setNews] = useState([]);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/api/problems"); setItems(data.data || []); setNews(data.news || []); } catch { /* the bell is optional */ }
  }, []);
  useEffect(() => pollWhileVisible(load, 30000), [load]);
  const n = items.length;
  const put = async (p) => {
    setBusy(p.key);
    try { await api.post(`/api/problems/${encodeURIComponent(p.key)}/dismiss`); } catch { /* it may have cleared itself */ }
    await load(); setBusy(null);
  };
  const restart = async (p) => {
    setBusy(`restart:${p.key}`);
    try { await restartBridge(p.connector); } catch { /* the next poll says whether it answers */ }
    await load(); setBusy(null);
  };
  return (
    <>
      <Tooltip title={n ? `${plural(n, "thing")} failing — click to see` : news.length ? news[news.length - 1].title : "Nothing is failing"}>
        <IconButton size="small" onClick={(e) => { setEl(e.currentTarget); load(); }} sx={{ position: "relative" }}>
          {n ? <NotificationsActiveIcon sx={{ fontSize: 18, color: ALERT }} /> : <NotificationsNoneIcon sx={{ fontSize: 18, color: DIM }} />}
          {!n && news.length > 0 && (
            <Box component="span" sx={{ position: "absolute", top: 3, right: 3, width: 7, height: 7, borderRadius: 99, bgcolor: "#47654a" }} />
          )}
          {n > 0 && (
            <Box component="span" sx={{ position: "absolute", top: 1, right: 1, minWidth: 14, height: 14, px: 0.3, borderRadius: 99,
              bgcolor: ALERT, color: "#fffdfb", fontSize: 9, fontWeight: 600, display: "grid", placeItems: "center", lineHeight: 1 }}>
              {n > 9 ? "9+" : n}
            </Box>
          )}
        </IconButton>
      </Tooltip>
      <Popover open={!!el} anchorEl={el} onClose={() => setEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 440, p: 1.5, mt: 0.5 } } }}>
        <Typography sx={{ fontWeight: 600, fontSize: 13, color: INK, mb: n ? 0.25 : 0.5 }}>{n ? "Failing right now" : "Nothing is failing"}</Typography>
        {!n && <Typography variant="caption" sx={{ color: DIM, display: "block" }}>Nothing has failed in the last few hours: connections, the triage brain and reports. Anything you dismissed comes back if it happens again.</Typography>}
        {items.map((p) => (
          <Box key={p.key} sx={{ py: 0.85, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1.25, alignItems: "flex-start" }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: INK, fontSize: 12.5 }}>{p.title}</Typography>
              <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.45, wordBreak: "break-word" }}>{p.detail}</Typography>
              {/* the two said in the assistant's voice (problems.collect `kind`) are a state, not a failure: "since" */}
              {p.since && <Typography variant="caption" sx={{ color: FAINT }} title={p.since}>{p.kind ? "since" : "failed"} {timeAgo(p.since)} · {fmtWhen(p.since)}</Typography>}
            </Box>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.4, alignItems: "stretch", flexShrink: 0 }}>
              <Button size="small" variant="outlined" sx={{ fontSize: 11, whiteSpace: "nowrap" }}
                onClick={() => { setEl(null); onGo(p); }}>{p.fix || "Fix"} →</Button>
              {/* "Restart bridge starts it" is said right here, so the button is here too (problems.collect `restart`) */}
              {p.restart && p.connector && <Button size="small" variant="outlined" data-tq-restart-bridge="" disabled={busy === `restart:${p.key}`}
                sx={{ fontSize: 11, whiteSpace: "nowrap" }} onClick={() => restart(p)}>
                {busy === `restart:${p.key}` ? "Restarting…" : "Restart bridge"}</Button>}
              {/* Reading it, not fixing it. It comes back the moment the same thing fails again
                  (problems.signature), so this quiets something you have decided to live with. */}
              <Button size="small" disabled={busy === p.key} sx={{ fontSize: 10.5, color: FAINT, textTransform: "none" }}
                title="I have read this. It returns if it happens again."
                onClick={() => put(p)}>{busy === p.key ? "…" : "Dismiss"}</Button>
              <Button size="small" sx={{ fontSize: 10.5, color: DIM, textTransform: "none", p: 0, minWidth: 0 }}
                onClick={() => { setEl(null); openBugReport(bellError(p)); }}>{btnLabel("report_bug")}</Button>
            </Box>
          </Box>
        ))}
        {news.length > 0 && (
          <Typography sx={{ fontWeight: 600, fontSize: 12, color: DIM, mt: n ? 1 : 0, mb: 0.25 }}>Back to normal</Typography>
        )}
        {news.map((p) => (
          <Box key={p.key} sx={{ py: 0.85, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1.25, alignItems: "flex-start" }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: INK, fontSize: 12.5 }}>{p.title}</Typography>
              {p.detail && <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.45 }}>{p.detail}</Typography>}
              {p.since && <Typography variant="caption" sx={{ color: FAINT }} title={p.since}>{timeAgo(p.since)}</Typography>}
            </Box>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.4, alignItems: "stretch", flexShrink: 0 }}>
              <Button size="small" variant="outlined" sx={{ fontSize: 11, whiteSpace: "nowrap" }}
                onClick={() => { setEl(null); onGo(p); }}>{p.fix || "Show me"} →</Button>
              <Button size="small" disabled={busy === p.key} sx={{ fontSize: 10.5, color: FAINT, textTransform: "none" }}
                onClick={() => put(p)}>{busy === p.key ? "…" : "Got it"}</Button>
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
   fixed. This is the only honest way to tell the difference from inside the page: at rest it
   reloads (once per server build), and to someone typing it says so, quietly (staleBuild.js). */
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
        <Typography variant="caption" noWrap sx={{ fontWeight: 600, color: "#6b5f45" }}>demo data</Typography>
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
    // the dev server's page names no hashed bundle: the first build the server reports stands in for its own
    let mine = loadedAsset();
    // `act`: only on load, focus and a socket (re)connect - the cheap moments a restart shows up at. The minute poll
    // keeps only the line, so the page never reloads under someone reading it.
    const check = (act) => api.get("/api/build").then(({ data }) => {
      if (!mine) mine = data?.asset || "";
      const s = staleWhat(mine, data);
      setStale(s);
      if (act && buildMove(mine, data, { busy: isBusy(), reloaded: reloadedFor() }) === "reload" && markReloaded(data.asset)) window.location.reload();
    }).catch(() => {});
    check(true);
    const t = setInterval(() => check(false), 60000);
    const onFocus = () => check(true);
    window.addEventListener("focus", onFocus);
    const off = onLive("hello", () => check(true));
    return () => { clearInterval(t); window.removeEventListener("focus", onFocus); off(); };
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
        <Typography variant="caption" sx={{ fontWeight: 600, color: "#55697a" }}>{stale}</Typography>
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

const SWITCH_VIEWS = [
  { k: "chat", label: "Chat", icon: (on) => <TaskuaryMark size={17} sx={{ borderRadius: 1, ...(on ? { boxShadow: "0 0 0 1.5px #fff" } : {}) }} />,
    title: "The Assistant - it walks you through what is waiting, one item at a time" },
  { k: "board", label: "Board", icon: () => <GridViewIcon sx={{ fontSize: 18 }} />, title: "Every agent and its session, full screen" },
  { k: "game", label: "Game", icon: () => <SportsEsportsIcon sx={{ fontSize: 19 }} />,
    title: "The same items as an office you walk around - people in the lobby, fyi's in the coffee room" },
];
export const ViewSwitch = ({ view, onView }) => (
  <Box role="tablist" aria-label="View" data-tq-view-switch={view}
    sx={{ display: "flex", gap: 0.4, p: 0.4, ml: { xs: 0.25, md: 1 }, borderRadius: 99, bgcolor: "#efe9df", border: "1px solid #ddd5c8", flexShrink: 0 }}>
    {SWITCH_VIEWS.map((v) => {
      const on = view === v.k;
      return (
        <Box key={v.k} component="button" type="button" role="tab" aria-selected={on} data-tq-view={v.k} title={v.title}
          // ...and Chat during setup is setup, as it was left: a page opened over it goes (W2; AssistantView acts on it only in setup)
          onClick={() => { onView(v.k); if (v.k === "chat") window.dispatchEvent(new Event("tq-setup-back")); }}
          sx={{ display: "flex", alignItems: "center", gap: 0.8, height: 34, px: { xs: 1.1, md: 1.8 }, borderRadius: 99, border: 0, cursor: "pointer",
            fontFamily: "inherit", fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", color: on ? "#fff" : INK,
            background: on ? BRAND.solid : "transparent", "&:hover": on ? {} : { bgcolor: "#fff" } }}>
          {v.icon(on)}<Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>{v.label}</Box>
        </Box>
      );
    })}
  </Box>
);

export default function TaskHubPage() {
  // Honor a deep link on the first render. Starting every reload on Assistant meant its hidden
  // conversation, feed and funnel all fetched before #task=356 (or a report) was allowed to load.
  // On a busy live session that left the requested page looking completely blank for many seconds.
  const [tab, setTab] = useState("Assistant");
  // what the canvas is asked to open - a task, or a browse card - numbered so the same one asked twice opens twice
  const [canvasReq, setCanvasReq] = useState(() => { const r = canvasRequestFromHash(window.location.hash || "", 1); readAhead(r); return r && { ...r, fromUrl: true }; });
  const ask = useCallback((req) => setCanvasReq((cur) => ({ ...req, n: (cur?.n || 0) + 1 })), []);
  const demo = useDemo();          // the badge, and what the header hides to make room for it
  useEffect(() => holdLive(), []);
  const [selectedTask, setSelectedTask] = useState(null);
  // the one "Report this bug" popup: any screen asks for it through REPORT_EVENT (bugReportOpen.js)
  const [bug, setBug] = useState(null);
  useEffect(() => { const f = (e) => setBug({ error: e.detail || null }); window.addEventListener(REPORT_EVENT, f); return () => window.removeEventListener(REPORT_EVENT, f); }, []);
  const [pending, setPending] = useState(0);
  const [tick, setTick] = useState(0);
  // the counter, and the panel it opens
  const [setup, reloadSetup] = useSetup(tick);
  useEffect(() => { window.addEventListener("tq-setup-changed", reloadSetup); return () => window.removeEventListener("tq-setup-changed", reloadSetup); }, [reloadSetup]);
  // the agent raised its hand: sound + desktop notification + a toast with the way to it.
  // The toast queues immediately; settings are read only for sound/desktop delivery. Making the
  // visible notification wait on that request made it appear at arbitrary times on a busy server.
  const [raisedQueue, setRaisedQueue] = useState([]);
  const raised = raisedQueue[0] || null;
  const tabRef = useRef(tab), selRef = useRef(null);
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
  // SETUP IS THE ASSISTANT CANVAS (the owner, 2026-10-14: "Remove the popup things just use the assistant canvas"): the
  // chip takes you there, where FirstRun asks its three questions. No dialog opens itself over the app any more.
  const openSetup = () => { go("Assistant"); setTimeout(() => window.dispatchEvent(new Event("tq-first-run")), 60); };

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
    if (t === "Timeline" || t === "Tasks") t = "Assistant";       // the rail is the Timeline and the task list now
    // a page that used to be a tab opens as its browse card in the canvas
    if (BROWSED[t]) { ask({ kind: "browse", area: BROWSED[t] }); t = "Assistant"; }
    if (!VIEWS.includes(t)) t = "Assistant";
    if (t === tab) return;
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
  const [everBoard, setEverBoard] = useState(false);
  const [everAssistant, setEverAssistant] = useState(tab === "Assistant");
  // the Assistant as a chat or as the game - remembered per browser, like any view choice
  // The public demo always opens on the chat: a visitor who tried the game once still lands on the chat next visit.
  const [asstGame, setAsstGame] = useState(() => {
    if (import.meta.env.VITE_DEMO === "1") return false;
    try { return localStorage.getItem("taskuary.assistantMode") === "game"; } catch { return false; }
  });
  const pickAsstGame = (on) => { setAsstGame(on); try { localStorage.setItem("taskuary.assistantMode", on ? "game" : "chat"); } catch { /* private window */ } };
  // SEARCH FROM ANY VIEW (the owner, 2026-10-15: "search doesn't work in game or in board, it reroutes you to the chat"): the
  // dialog opens over the Board or the Game where you are; a PICK is what brings Chat up, since that is where it is drawn.
  // Ctrl+K works there too - Chat's own rail listens for it only while Chat is on screen.
  const toChat = useRef(null);
  toChat.current = () => { pickAsstGame(false); go("Assistant"); };
  useEffect(() => {
    const picked = () => toChat.current?.();
    window.addEventListener(SEARCH_PICKED, picked);
    return () => window.removeEventListener(SEARCH_PICKED, picked);
  }, []);
  useEffect(() => {
    if (tab === "Assistant" && !asstGame) return undefined;
    const k = (e) => { if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [tab, asstGame]);
  // ...and the Board, which can hold a live session too: mounted once opened, hidden after. The
  // Assistant is the normal landing tab, but a deep link does not boot it until it is opened.
  useEffect(() => { if (tab === "Board") setEverBoard(true); }, [tab]);
  useEffect(() => { if (tab === "Assistant") setEverAssistant(true); }, [tab]);

  const refreshPending = useCallback(async () => {
    try {
      const rows = (await api.get("/api/reviews", { params: { status: "pending" } })).data.data || [];
      setPending(new Set(rows.map((r) => r.TaskId ?? `rv:${r.ReviewId}`)).size);
    }
    catch { /* badge is optional */ }
  }, []);
  useEffect(() => { refreshPending(); }, [refreshPending, tick]);
  // The badge counts a queue the server changes on its own - a drafter finishing, a reply that
  // landed. Counting only on mount and on the refresh icon left "Tasks · 2" over three drafts.
  useEffect(() => onLive(["feed-changed", "task-changed"], refreshPending, { wait: 250, max: 1500 }), [refreshPending]);

  // EVERY OLD LINK STILL LANDS - in the canvas (canvasLinks.js): #task=123 opens that task's view, #connector=,
  // #settings=, #report=, #playbook= open their browse card, #new-task the New sheet, #msg= that message's card
  // ...and the browser's Back and Forward come the same road (appLinks.onPlace): a step back to the address with no place is the walk's
  // own table, the page put down (the 2026-10-19 UI walk: Back left the app). `fromUrl`: the address already says it - the canvas
  // writes it more exactly, never as a new step
  useEffect(() => onPlace((h, back) => {
    const req = canvasRequestFromHash(h, 0);
    readAhead(req);
    if (req || (back && !h)) { ask({ ...(req || { kind: "home" }), fromUrl: true }); setTab("Assistant"); tabRef.current = "Assistant"; }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), []);
  // A terminal belongs to the task it is working. Opening a task with start=true means "and put your CLI on it now";
  // `act` opens it with one of its dialogs up (a card's "Not a task…")
  const openTask = (taskId, opts) => {
    selectTask(taskId);
    ask({ kind: "task", tid: taskId, start: opts?.start ? { agent: opts.agent, model: opts.model } : null, act: opts?.act || null });
    if (tab !== "Assistant") { setTab("Assistant"); tabRef.current = "Assistant"; }
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
          action={raised && <Button size="small" sx={{ color: ACCENT, fontWeight: 600 }} onClick={() => { openTask(raised.tid); setRaisedQueue(dismissHandRaise); }}>Open</Button>} />
        {/* ── slim top bar ───────────────────────────────────────────── */}
        {/* Full width, deliberately. Constraining this to the page column squeezed the tab strip
            until its overflowX put a horizontal SCROLLBAR under the nav - a slider you have to
            drag to reach Settings - and pushed the whole page into horizontal scroll with it. A
            nav bar is chrome; it spans. */}
        {/* id + top z: the Timeline's frozen dock pins itself right below this bar (it measures
            the height by id) - z above the dock so nothing ever slides over the tabs */}
        {/* ...and on a phone it WRAPS. Logo, view switch, Chat/Task/Game, the set-up ring and three icons are ~540px
            in one row; at 390 that row set the page's layout width to 493, so every screen drew zoomed out with
            the right-hand icons off the edge (the 2026-10-02 pane pass, a 390-wide phone on a task with a browser). */}
        <Box id="tqTopNav" sx={{ display: "flex", alignItems: "center", gap: { xs: 0.75, md: 1.25 },
          flexWrap: { xs: "wrap", md: "nowrap" }, rowGap: 0.5,
          px: { xs: 1.25, md: 2.5 }, py: 1,
          bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, zIndex: 30 }}>
          <TaskuaryMark size={26} sx={{ borderRadius: 1.5 }} />
          {/* the word gives way on a phone: with it the bar wrapped, and the bell and refresh sat alone on a second row (2026-10-06) */}
          <Typography sx={{ fontWeight: 600, fontSize: 14.5, color: INK, letterSpacing: 0.2, display: { xs: "none", sm: "block" } }}>Taskuary</Typography>
          {/* no tagline here (the cleanup, 2026-10-06): the top bar is the logo, the views and three icons */}
          <ServerVersion />
          <DemoBadge demo={demo} />

          {/* ONE SWITCH, THREE VIEWS (the owner, 2026-10-15: "Chat which is the regular workflow, then Board, then Game ... make
              it a little bigger so they are more obvious"). The Board button beside a Chat | Task | Game switch was two controls
              for one question, and Task - rows opening on their own - is what a click in Chat already does. */}
          <ViewSwitch view={tab === "Board" ? "board" : asstGame ? "game" : "chat"}
            onView={(v) => { if (v === "board") { go("Board"); return; } pickAsstGame(v === "game"); go("Assistant"); }} />
          {/* SEARCH, on the top line (the owner, 2026-10-14) - from the Board it goes to the Assistant, whose rail owns the hits */}
          {/* ...on a phone too, as its icon at the line's end (SearchBar): it was display:none there (the 2026-10-19 UI walk) */}
          <Box sx={{ flex: 1, display: "flex", justifyContent: { xs: "flex-end", sm: "center" }, minWidth: 0, px: { xs: 0, md: 2 } }}>
            <Box sx={{ width: { xs: "auto", sm: "100%" }, maxWidth: 420 }}>
              <SearchBar onOpen={openSearch} />
            </Box>
          </Box>
          {/* on the RIGHT, with the other transient chrome. On the left it grew the brand cluster
              until it slid UNDER the tab strip, which is absolutely centred on the window and so
              yields to nothing - the banner sat on top of "Timeline". */}
          <StaleBuild />
          {/* ...and the static demo has the same Setup, which says how to install Taskuary: the chat's own setup button went (the owner,
              2026-10-19) and the demo was left with no way to that page. A server run with --demo keeps its badge where it was */}
          {(DEMO || !demo) && <SetupChip state={DEMO ? DEMO_SETUP : setup} onOpen={openSetup} />}
          <Tooltip title="Report a problem">
            <IconButton onClick={() => openBugReport()} size="small" aria-label="Report a problem">
              <HelpOutlineIcon sx={{ fontSize: 17, color: DIM }} />
            </IconButton>
          </Tooltip>
          {/* the Fix button lands on the card itself: Connectors reads #connector=<type> on the way in */}
          <Bell onGo={(p) => {
            if (p.connector) { openAppLink(`connector=${p.connector}`); return; }   // the link opens its card in the canvas
            if (p.report) { openAppLink(`report=${p.report}`); return; }
            go(p.where || "Connections");
          }} />
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => setTick(tick + 1)}><RefreshIcon sx={{ fontSize: 17, color: DIM }} /></IconButton>
          </Tooltip>
        </Box>

        {/* tighter side padding than top/bottom: the horizontal margin is dead space on a wide
            window, and every tab inside already caps its own content width where it wants to */}
        <Box sx={{ px: { xs: 1.5, md: 1.75 }, py: { xs: 1.5, md: 2.25 } }}>
          {/* Timeline and Board stay MOUNTED behind another tab, like Tasks: each can hold a live
              pty session, and unmounting closed its websocket - so coming back replayed the whole
              scrollback and ran the pane top to bottom. Their polling is gated on `active`. */}
          {/* Once opened, the Assistant (the Timeline's rail + chat) stays mounted: its conversation
              and pipe animation are on-screen state worth keeping, and polling is gated on `active`. */}
          {everAssistant && (
            <Box sx={{ display: tab === "Assistant" ? "block" : "none" }}>
              {/* Game is the same Assistant, walked: the chat stays mounted behind it so its conversation survives the switch */}
              <Box sx={{ display: asstGame ? "none" : "block" }}>
                <AssistantView key={`a${tick}`} onOpenTask={openTask} onNavigate={go} onChanged={refreshPending}
                  active={tab === "Assistant" && !asstGame} request={canvasReq} />
              </Box>
              {asstGame && (
                <React.Suspense fallback={<CircularProgress size={22} sx={{ m: 4 }} />}>
                  <AssistantGame onOpenTask={openTask} onNavigate={go} onExit={() => pickAsstGame(false)} active={tab === "Assistant"} />
                </React.Suspense>
              )}
            </Box>
          )}
          {(everBoard || tab === "Board") && (
            <Box sx={{ display: tab === "Board" ? "block" : "none" }}>
              <BoardView key={`b${tick}`} onOpenTask={openTask} active={tab === "Board"} />
            </Box>
          )}
        </Box>
        {/* The floating mark is gone (the owner, 2026-09-15: "we also don't need the taskuary image in
            bottom right corner anymore"). It was the same assistant the Assistant tab already is, and
            it sat on top of the work - over the browser pane's own Take over button, in full screen. */}
      </Box>
      <BugReportDialog open={!!bug} onClose={() => setBug(null)} screen={tab} error={bug?.error} supportUrl={SUPPORT_URL} />
    </ThemeProvider>
  );
}
