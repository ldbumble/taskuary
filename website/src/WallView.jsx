// The wall: every live coding session as a real terminal, side by side, so you work several
// agents at once the way you watch several screens. Each pane is one task - its ref on top, the
// session in the middle, its prompt queue at the bottom. Choose how many across (1 / 2 / 3 / 4)
// drag a pane by its header to rearrange, and drag the bar under any pane to make them all taller
// or shorter. The terminals are the same pty as the task page;
// a pane keeps its key=sid, so reordering moves it without tearing the session down.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, CircularProgress, IconButton, Tooltip, Typography } from "@mui/material";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { PANEL, BORDER, DIM, FAINT, INK, ACCENT, ROLES, mono } from "./theme.jsx";
import { TerminalPane } from "./TerminalView.jsx";

const GeneralWorkspace = React.lazy(() => import("./GeneralWorkspace.jsx"));
import { Confirm, TellAgent, WorkLine, isWaiting } from "./ui.jsx";
import { cliName } from "./BoardView.jsx";
import { defaultPaneHeight, holdWrappingSessions, movePane, resizedPaneHeight, wallPaneAtPoint, withoutWallSession } from "./wallLayout.js";

const COLS = [1, 2, 3, 4];
// two columns by default - except on a phone, where two panes side by side leave each too narrow
// for the terminal's own knobs (the A-/A+ row overflowed its pane) and for a readable line of code
const defaultCols = () => (typeof window !== "undefined" && window.innerWidth < 700 ? 1 : 2);
const savedCols = () => { try { return Number(localStorage.getItem("tq.wall.cols")) || defaultCols(); } catch { return defaultCols(); } };
// Pane height is yours to drag (the bar under each pane), and it sticks per browser PER column
// count - the height that suits one pane across is not the one that suits four. 0 = never
// dragged, use the formula below. The panes always share one height: a grid of ragged
// terminals reads as a mistake, so the bar under any pane resizes them all.
const MIN_H = 240;
const hKey = (c) => `tq.wall.h.${c}`;
const ORDER_KEY = "tq.wall.order";
const savedOrder = () => { try { const o = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]"); return Array.isArray(o) ? o.filter((x) => typeof x === "string") : []; } catch { return []; } };
const savedH = (c) => { try { return Number(localStorage.getItem(hKey(c))) || 0; } catch { return 0; } };
const storeH = (c, h) => { try { h ? localStorage.setItem(hKey(c), String(h)) : localStorage.removeItem(hKey(c)); } catch { /* private */ } };

export default function WallView({ onOpenTask, onOpenReports, refresh = 0 }) {
  const [sessions, setSessions] = useState(null);   // alive pty sessions with a task
  const [tasks, setTasks] = useState({});           // TaskId -> task row (title, ref)
  const [live, setLive] = useState({});             // TaskId -> {work, StartedAt, ...} from runs/live
  const [cols, setCols] = useState(savedCols);
  const [paneHpx, setPaneHpx] = useState(() => savedH(savedCols()));   // 0 = default formula
  useEffect(() => { setPaneHpx(savedH(cols)); }, [cols]);
  // the display order you drag into - kept per browser, so a reload (or the 8s poll) does not
  // put the panes back where they came from: a rearrangement that lasts one refresh reads as broken
  const [order, setOrder] = useState(savedOrder);
  useEffect(() => { if (order.length) { try { localStorage.setItem(ORDER_KEY, JSON.stringify(order)); } catch { /* private */ } } }, [order]);
  const [dragging, setDragging] = useState(null);   // rendered too: the pane visibly lifts while moving
  const [closing, setClosing] = useState(null);     // session awaiting an explicit stop confirmation
  const [wrapping, setWrapping] = useState({});     // sid -> true; several panes can finish independently
  const wrappingRef = useRef({});                   // load() must see this inside its stable callback
  const [wrapErrors, setWrapErrors] = useState({}); // sid -> visible reason the checkmark did not finish
  const [wrapNotice, setWrapNotice] = useState(""); // survives when the server already closed the failed pane
  const drag = useRef(null);

  const load = useCallback(async () => {
    const [tm, tk] = await Promise.all([
      api.get("/api/terminals").catch(() => ({ data: {} })),
      api.get("/api/tasks", { params: { active: 1 } }).catch(() => ({ data: {} })),
    ]);
    const fresh = (tm.data.data || []).filter((s) => s.alive && s.taskId);
    setSessions((current) => holdWrappingSessions(fresh, current, wrappingRef.current));
    setTasks(Object.fromEntries((tk.data.data || []).map((t) => [t.TaskId, t])));
  }, []);
  useEffect(() => { load(); return pollWhileVisible(load, 8000); }, [load]);
  useEffect(() => { if (refresh) load(); }, [refresh, load]);   // the Board just started a session: show it now, not in 8s
  useEffect(() => {   // the work line (tool in hand, its list) ticks fast, like the Board's
    const tick = () => api.get("/api/runs/live").then(({ data }) =>
      setLive(Object.fromEntries((data.data || []).map((r) => [r.TaskId, r])))).catch(() => {});
    tick(); return pollWhileVisible(tick, 4000);
  }, []);

  // keep `order` in step with what's alive: append new sids, drop the gone, honour drags
  const sids = useMemo(() => (sessions || []).map((s) => s.sid), [sessions]);
  useEffect(() => {
    if (!sessions) return;      // before the first load the list is empty, not "everything is gone" - reconciling then wiped the saved order
    setOrder((o) => { const set = new Set(sids); return [...o.filter((x) => set.has(x)), ...sids.filter((x) => !o.includes(x))]; });
  }, [sids, sessions]);
  const bySid = useMemo(() => Object.fromEntries((sessions || []).map((s) => [s.sid, s])), [sessions]);
  const panes = order.map((sid) => bySid[sid]).filter(Boolean);

  const setColsP = (n) => { setCols(n); try { localStorage.setItem("tq.wall.cols", String(n)); } catch { /* private */ } };
  // Native HTML drag-and-drop is not dependable over an interactive terminal grid: depending on
  // the browser and whether the pointer starts over the icon's SVG, dragstart may never happen.
  // Follow the pointer ourselves and ask which keyed pane is underneath. Reordering the keyed
  // wrappers moves the existing TerminalPane; it does not recreate or visually resize xterm.
  const startDrag = (e, sid) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    drag.current?.cleanup?.();
    const pointerId = e.pointerId, handle = e.currentTarget;
    const active = { sid, pointerId, handle, lastTarget: sid, cleanup: null };
    const cleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      try { if (handle.hasPointerCapture?.(pointerId)) handle.releasePointerCapture(pointerId); } catch { /* detached */ }
    };
    const move = (ev) => {
      if (ev.pointerId !== pointerId || drag.current !== active) return;
      const target = wallPaneAtPoint(document, ev.clientX, ev.clientY);
      if (!target || target === active.lastTarget) return;
      active.lastTarget = target;
      setOrder((o) => movePane(o, sid, target));
    };
    const finish = (ev) => {
      if (ev?.pointerId !== undefined && ev.pointerId !== pointerId) return;
      cleanup();
      if (drag.current === active) { drag.current = null; setDragging(null); }
    };
    active.cleanup = cleanup;
    drag.current = active; setDragging(sid);
    try { handle.setPointerCapture?.(pointerId); } catch { /* global listeners still own the drag */ }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
  };
  useEffect(() => () => drag.current?.cleanup?.(), []);
  const wrap = async (s) => {
    if (!s?.sid || wrappingRef.current[s.sid]) return;
    wrappingRef.current = { ...wrappingRef.current, [s.sid]: true };
    setWrapping({ ...wrappingRef.current });
    setWrapNotice("");
    setWrapErrors((errs) => { const next = { ...errs }; delete next[s.sid]; return next; });
    try {
      await api.post(`/api/tasks/${s.taskId}/wrap`, { close: true });
      // Do not wait for the eight-second Wall poll to prove a successful response meant success.
      // Remove this exact pane now; other agents on the Wall keep their place and keep working.
      setSessions((rows) => withoutWallSession(rows, s.sid));
      setOrder((rows) => rows.filter((sid) => sid !== s.sid));
      setLive((rows) => { const next = { ...rows }; delete next[s.taskId]; return next; });
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "the session could not be wrapped up";
      setWrapErrors((errs) => ({ ...errs, [s.sid]: msg }));
      setWrapNotice(`Could not finish ${tasks[s.taskId]?.ref || `TQ-${s.taskId}`}: ${msg}`);
    } finally {
      const next = { ...wrappingRef.current }; delete next[s.sid]; wrappingRef.current = next;
      setWrapping(next);
      await load();
    }
  };
  const closeSession = async () => {
    if (!closing?.sid) return;
    await api.delete(`/api/terminals/${closing.sid}`);
    setSessions((ss) => (ss || []).filter((s) => s.sid !== closing.sid));
    setOrder((o) => o.filter((sid) => sid !== closing.sid));
  };

  // The bar under a pane: drag it and every pane follows, live - the terminal inside refits
  // itself (TerminalPane watches its box and tells the pty). Frames are coalesced so a fast
  // drag does not fire a resize per pixel. Double-click puts the default height back.
  const onGrab = (e) => {
    const h0 = e.currentTarget.parentElement.getBoundingClientRect().height, y0 = e.clientY, el = e.currentTarget;
    let raf = 0, h = Math.round(h0);
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    const move = (ev) => { h = resizedPaneHeight(h0, y0, ev.clientY, MIN_H); if (!raf) raf = requestAnimationFrame(() => { raf = 0; setPaneHpx(h); }); };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up);
      cancelAnimationFrame(raf); raf = 0; setPaneHpx(h); storeH(cols, h); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); window.addEventListener("pointercancel", up);
  };
  const resetH = () => { setPaneHpx(0); storeH(cols, 0); };

  if (!sessions) return <CircularProgress size={22} sx={{ m: 4 }} />;
  // One row fills the screen. If the wall wraps, two rows share it; anything beyond scrolls.
  const paneH = paneHpx ? `${paneHpx}px` : defaultPaneHeight(panes.length, cols);
  return (
    <Box>
      {wrapNotice && <Alert severity="error" onClose={() => setWrapNotice("")} sx={{ mb: 1 }}>{wrapNotice}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.25 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15 }}>The wall</Typography>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5, flex: 1 }}>
          Every live session, side by side — code several agents at once. Drag a pane by its handle to rearrange; drag the bar under it to resize.
        </Typography>
        {!!panes.length && (
          <Box sx={{ display: "flex", gap: 0.25, bgcolor: "#e7eae2", borderRadius: 2, p: "3px" }}>
            {COLS.map((n) => (
              <Box key={n} onClick={() => setColsP(n)} title={n === 1 ? "one at a time" : n === 2 ? "two across (2×2)" : `${n} across`}
                sx={{ minWidth: 30, textAlign: "center", height: 24, lineHeight: "24px", px: 1, borderRadius: 1.5, cursor: "pointer",
                  ...mono, fontSize: 12, fontWeight: cols === n ? 700 : 500, color: cols === n ? INK : DIM,
                  bgcolor: cols === n ? PANEL : "transparent", boxShadow: cols === n ? "0 1px 2px rgba(30,50,38,.10)" : "none" }}>
                {n}×
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {!panes.length ? (
        <Box sx={{ ...pane0, p: 4, textAlign: "center" }}>
          <Typography variant="body2" sx={{ color: DIM }}>No agent is in a live session right now.</Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
            Start one from a task (Send to a coding agent), and it appears here as a terminal you can work in.
          </Typography>
        </Box>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(${cols > 2 ? "260px" : "0px"}, 1fr))`,
          gap: 1.5, alignItems: "start", overflowX: "auto", pb: 0.5 }}>
          {panes.map((s) => {
            const t = tasks[s.taskId] || {}, l = live[s.taskId];
            const wallRun = l || s, statusWork = l?.work || s.work;
            const waiting = isWaiting(wallRun);
            const wrapBusy = !!wrapping[s.sid], wrapError = wrapErrors[s.sid];
            const who = s.cli || cliName(s.agent || "agent");
            return (
              <Box key={s.sid} data-wall-pane={s.sid}
                sx={{ ...pane0, display: "flex", flexDirection: "column", height: paneH, minHeight: MIN_H,
                  borderColor: wrapBusy ? ROLES.working.bd : waiting ? ROLES.you.bd : BORDER,
                  opacity: dragging === s.sid ? 0.62 : 1, transform: dragging === s.sid ? "scale(.995)" : "none",
                  boxShadow: dragging === s.sid ? "0 7px 20px rgba(30,50,38,.16)" : pane0.boxShadow,
                  transition: "border-color .2s, transform .12s, opacity .12s, box-shadow .12s" }}>
                {/* Title owns the first row; live-agent status gets a second row and can never
                    squeeze the task name out. Only the handle is draggable, so the action buttons
                    remain buttons instead of occasionally starting a pane drag. */}
                <Box sx={{ borderBottom: `1px solid ${BORDER}`, bgcolor: wrapBusy ? ROLES.working.tint : waiting ? ROLES.you.tint : "#faf8f5", flexShrink: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 0.75, py: 0.35 }}>
                    <Box onPointerDown={(e) => startDrag(e, s.sid)}
                      role="button" aria-label={`Drag ${t.ref || `TQ-${s.taskId}`} to reorder`} tabIndex={0}
                      title="Drag to reorder this pane"
                      sx={{ width: 24, height: 26, display: "flex", alignItems: "center", justifyContent: "center",
                        flexShrink: 0, borderRadius: 1, cursor: "grab", touchAction: "none", userSelect: "none",
                        "&:hover": { bgcolor: "#e7eae2" }, "&:active": { cursor: "grabbing" } }}>
                      <DragIndicatorIcon sx={{ fontSize: 16, color: FAINT }} />
                    </Box>
                    <Typography sx={{ ...mono, fontSize: 11, fontWeight: 700, color: ACCENT, flexShrink: 0 }}>{t.ref || `TQ-${s.taskId}`}</Typography>
                    <Typography noWrap title={t.Title || s.cwd}
                      sx={{ fontSize: 12, fontWeight: 650, color: INK, minWidth: 0, flex: 1 }}>{t.Title || s.cwd}</Typography>
                    <Tooltip title="Open the full task page"><IconButton aria-label="Open full task" size="small" onClick={() => onOpenTask?.(s.taskId)}><OpenInFullIcon sx={{ fontSize: 14, color: DIM }} /></IconButton></Tooltip>
                    <Tooltip title={wrapBusy ? "Closing the session and writing its report…" : "Done — close the session and wrap up the task"}>
                      <IconButton aria-label={wrapBusy ? "Wrapping up task" : "Wrap up task"} size="small" disabled={wrapBusy} onClick={() => wrap(s)}>
                        {wrapBusy ? <CircularProgress size={14} /> : <DoneAllIcon sx={{ fontSize: 15, color: "#47654a" }} />}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Close session — stop the agent; keep the task and transcript"><span><IconButton aria-label="Close session" size="small" disabled={wrapBusy} onClick={() => setClosing(s)}><CloseIcon sx={{ fontSize: 16, color: DIM }} /></IconButton></span></Tooltip>
                  </Box>
                  {/* Always reserve the status row. A tool starting/stopping used to add/remove
                      this row, resize xterm, and make full-screen CLIs repaint in a visible jump. */}
                  <Box sx={{ height: 20, minWidth: 0, overflow: "hidden", px: 1, pb: 0.55, pl: 4.75,
                    display: "flex", alignItems: "center" }}>
                    {wrapBusy ? (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
                        <CircularProgress size={10} />
                        <Typography noWrap sx={{ ...mono, fontSize: 10, color: ROLES.working.ink }}>
                          closing session · writing report and reply draft…
                        </Typography>
                      </Box>
                    ) : wrapError ? (
                      <Tooltip title={wrapError}><Typography noWrap sx={{ ...mono, fontSize: 10, color: ROLES.bad.ink }}>
                        could not finish · {wrapError}
                      </Typography></Tooltip>
                    ) : (statusWork || waiting) ? (
                      <WorkLine work={statusWork} who={who} waiting={waiting}
                        asking={l?.asking ?? s.asking} startedAt={l?.StartedAt || s.started} />
                    ) : (
                      <Typography noWrap sx={{ ...mono, fontSize: 10, color: FAINT }}>● {who} session</Typography>
                    )}
                  </Box>
                </Box>
                {/* the session itself fills the middle */}
                <Box sx={{ flex: 1, minHeight: 0, p: 0.75, display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                  {s.mode === "assistant"
                    ? <React.Suspense fallback={<CircularProgress size={18} sx={{ m: "auto" }} />}>
                        <GeneralWorkspace task={{ ...t, TaskId: s.taskId }} onSession={load} onOpenReports={onOpenReports} compact />
                      </React.Suspense>
                    : <TerminalPane sid={s.sid} height="100%" onExit={load} />}
                </Box>
                {/* the queue, at the bottom of its own pane */}
                <Box sx={{ px: 0.75, pb: 0.25, flexShrink: 0 }}>
                  <TellAgent taskId={s.taskId} taskRef={t.ref} compact onQueued={load} />
                </Box>
                {/* the grab bar: taller or shorter panes, all of them at once; double-click resets */}
                <Box onPointerDown={onGrab} onDoubleClick={resetH} title="Drag to resize the panes — double-click for the default height"
                  sx={{ height: 10, flexShrink: 0, cursor: "ns-resize", touchAction: "none", display: "flex", alignItems: "center", justifyContent: "center",
                    "&:hover > span, &:active > span": { bgcolor: DIM, width: 56 } }}>
                  <Box component="span" sx={{ width: 36, height: 3, borderRadius: 99, bgcolor: BORDER, transition: "all .15s" }} />
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
      <Confirm open={!!closing} title="Close this session?" confirmLabel="Close session"
        text={`This stops ${closing?.cli || cliName(closing?.agent || "the agent")} now and removes its pane from the wall. The task stays open, and the session transcript stays with it.`}
        onClose={() => setClosing(null)} onConfirm={closeSession} />
    </Box>
  );
}

const pane0 = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", boxShadow: "0 1px 2px rgba(30,50,38,.04)" };
