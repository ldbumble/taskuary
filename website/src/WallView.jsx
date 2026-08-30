// The wall: every live coding session as a real terminal, side by side, so you work several
// agents at once the way you watch several screens. Each pane is one task - its ref on top, the
// session in the middle, its prompt queue at the bottom. Choose how many across (1 / 2 / 3 / 4)
// drag a pane by its header to rearrange, and drag the bar under any pane to make them all taller
// or shorter. The terminals are the same pty as the task page;
// a pane keeps its key=sid, so reordering moves it without tearing the session down.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, CircularProgress, IconButton, Tooltip, Typography } from "@mui/material";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT, mono } from "./theme.jsx";
import { TerminalPane } from "./TerminalView.jsx";
import { TellAgent, WorkLine, isWaiting } from "./ui.jsx";
import { cliName } from "./BoardView.jsx";

const COLS = [1, 2, 3, 4];
const savedCols = () => { try { return Number(localStorage.getItem("tq.wall.cols")) || 2; } catch { return 2; } };
// Pane height is yours to drag (the bar under each pane), and it sticks per browser PER column
// count - the height that suits one pane across is not the one that suits four. 0 = never
// dragged, use the formula below. The panes always share one height: a grid of ragged
// terminals reads as a mistake, so the bar under any pane resizes them all.
const MIN_H = 240;
const hKey = (c) => `tq.wall.h.${c}`;
const savedH = (c) => { try { return Number(localStorage.getItem(hKey(c))) || 0; } catch { return 0; } };
const storeH = (c, h) => { try { h ? localStorage.setItem(hKey(c), String(h)) : localStorage.removeItem(hKey(c)); } catch { /* private */ } };

export default function WallView({ onOpenTask, refresh = 0 }) {
  const [sessions, setSessions] = useState(null);   // alive pty sessions with a task
  const [tasks, setTasks] = useState({});           // TaskId -> task row (title, ref)
  const [live, setLive] = useState({});             // TaskId -> {work, StartedAt, ...} from runs/live
  const [cols, setCols] = useState(savedCols);
  const [paneHpx, setPaneHpx] = useState(() => savedH(savedCols()));   // 0 = default formula
  useEffect(() => { setPaneHpx(savedH(cols)); }, [cols]);
  const [order, setOrder] = useState([]);           // sids, the display order you drag into
  const drag = useRef(null);

  const load = useCallback(async () => {
    const [tm, tk] = await Promise.all([
      api.get("/api/terminals").catch(() => ({ data: {} })),
      api.get("/api/tasks", { params: { active: 1 } }).catch(() => ({ data: {} })),
    ]);
    setSessions((tm.data.data || []).filter((s) => s.alive && s.taskId));
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
    setOrder((o) => { const set = new Set(sids); return [...o.filter((x) => set.has(x)), ...sids.filter((x) => !o.includes(x))]; });
  }, [sids]);
  const bySid = useMemo(() => Object.fromEntries((sessions || []).map((s) => [s.sid, s])), [sessions]);
  const panes = order.map((sid) => bySid[sid]).filter(Boolean);

  const setColsP = (n) => { setCols(n); try { localStorage.setItem("tq.wall.cols", String(n)); } catch { /* private */ } };
  const onDrop = (target) => {
    const from = drag.current; drag.current = null;
    if (!from || from === target) return;
    setOrder((o) => { const a = [...o], i = a.indexOf(from), j = a.indexOf(target); if (i < 0 || j < 0) return o; a.splice(j, 0, a.splice(i, 1)[0]); return a; });
  };
  const wrap = async (tid) => { try { await api.post(`/api/tasks/${tid}/wrap`, {}); load(); } catch { /* already gone */ } };

  // The bar under a pane: drag it and every pane follows, live - the terminal inside refits
  // itself (TerminalPane watches its box and tells the pty). Frames are coalesced so a fast
  // drag does not fire a resize per pixel. Double-click puts the default height back.
  const onGrab = (e) => {
    const h0 = e.currentTarget.parentElement.getBoundingClientRect().height, y0 = e.clientY, el = e.currentTarget;
    let raf = 0, h = Math.round(h0);
    el.setPointerCapture(e.pointerId);
    const move = (ev) => { h = Math.max(MIN_H, Math.round(h0 + ev.clientY - y0)); if (!raf) raf = requestAnimationFrame(() => { raf = 0; setPaneHpx(h); }); };
    const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up);
      cancelAnimationFrame(raf); raf = 0; setPaneHpx(h); storeH(cols, h); };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  };
  const resetH = () => { setPaneHpx(0); storeH(cols, 0); };

  if (!sessions) return <CircularProgress size={22} sx={{ m: 4 }} />;
  // default: two rows of panes sit in view at a glance; more than that scrolls
  const paneH = paneHpx ? `${paneHpx}px` : cols === 1 ? "min(70vh, 680px)" : `max(300px, calc((100vh - 250px) / 2))`;
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.25 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15 }}>The wall</Typography>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5, flex: 1 }}>
          Every live session, side by side — code several agents at once. Drag a pane by its handle to rearrange; drag the bar under it to resize.
        </Typography>
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
      </Box>

      {!panes.length ? (
        <Box sx={{ ...pane0, p: 4, textAlign: "center" }}>
          <Typography variant="body2" sx={{ color: DIM }}>No agent is in a live session right now.</Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
            Start one from a task (Send to a coding agent), and it appears here as a terminal you can work in.
          </Typography>
        </Box>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: `repeat(${cols}, minmax(0, 1fr))` }, gap: 1.5, alignItems: "start" }}>
          {panes.map((s) => {
            const t = tasks[s.taskId] || {}, l = live[s.taskId];
            const waiting = isWaiting(s);
            return (
              <Box key={s.sid} onDragOver={(e) => e.preventDefault()} onDrop={() => onDrop(s.sid)}
                sx={{ ...pane0, display: "flex", flexDirection: "column", height: paneH, minHeight: MIN_H }}>
                {/* header: task ref + title + what it is doing; the handle drags the whole pane */}
                <Box draggable onDragStart={() => { drag.current = s.sid; }} onDragEnd={() => { drag.current = null; }}
                  sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1, py: 0.6, borderBottom: `1px solid ${BORDER}`,
                    bgcolor: waiting ? "#f3e6e8" : "#faf8f5", cursor: "grab", "&:active": { cursor: "grabbing" }, flexShrink: 0 }}>
                  <DragIndicatorIcon sx={{ fontSize: 15, color: FAINT }} />
                  <Typography sx={{ ...mono, fontSize: 11, fontWeight: 700, color: ACCENT, flexShrink: 0 }}>{t.ref || `TQ-${s.taskId}`}</Typography>
                  <Typography noWrap sx={{ fontSize: 12, fontWeight: 600, color: INK, minWidth: 0, flexShrink: 1 }}>{t.Title || s.cwd}</Typography>
                  <Box sx={{ flex: 1, minWidth: 8 }} />
                  {s.work && <WorkLine work={s.work} who={s.cli || cliName(s.agent || "agent")} waiting={waiting} asking={s.asking} startedAt={s.started} />}
                  <Tooltip title="Open the full task page"><IconButton size="small" onClick={() => onOpenTask?.(s.taskId)}><OpenInFullIcon sx={{ fontSize: 14, color: DIM }} /></IconButton></Tooltip>
                  <Tooltip title="Done — wrap this session up"><IconButton size="small" onClick={() => wrap(s.taskId)}><DoneAllIcon sx={{ fontSize: 15, color: "#47654a" }} /></IconButton></Tooltip>
                </Box>
                {/* the session itself fills the middle */}
                <Box sx={{ flex: 1, minHeight: 0, p: 0.75, display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                  <TerminalPane sid={s.sid} height="100%" onExit={load} />
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
    </Box>
  );
}

const pane0 = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", boxShadow: "0 1px 2px rgba(30,50,38,.04)" };
