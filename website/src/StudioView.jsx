// The Board, drawn as the same little 3D world used on taskuary.com. Every visible
// character is backed by a real task/run, every empty workstation is actual capacity,
// and the list and room are two controls over the same selection.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Box, CircularProgress, Slider, Typography } from "@mui/material";

import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { onLive } from "./live.js";
import { PANEL, BORDER, DIM, FAINT, INK, ACCENT, ROLES, mono } from "./theme.jsx";
import { FileChips } from "./BoardView.jsx";
import { WorkLine, isWaiting } from "./ui.jsx";
import { studioSeats, studioTaskIsLive, studioTaskState } from "./studioModel.js";

const StudioScene = React.lazy(() => import("./StudioScene.jsx"));

export default function StudioView({ onOpenTask, refresh = 0, active = true }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [cap, setCap] = useState(null);
  const [live, setLive] = useState({});
  const [pick, setPick] = useState(null);
  const [clock, setClock] = useState(Date.now());

  const load = useCallback(async () => {
    const [taskResponse, agentResponse, settingResponse] = await Promise.all([
      api.get("/api/tasks", { params: { active: 1 } }).catch(() => ({ data: {} })),
      api.get("/api/agents").catch(() => ({ data: {} })),
      api.get("/api/settings").catch(() => ({ data: {} })),
    ]);
    setTasks((taskResponse.data.data || []).filter((task) => task.Status !== "dropped"));
    setAgents(agentResponse.data.data || agentResponse.data.agents || []);
    const row = (settingResponse.data.data || []).find((setting) => setting.Name === "auto_sessions");
    setCap((current) => current == null ? Math.max(1, Math.min(8, parseInt(row?.Value, 10) || 4)) : current);
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    load();
    return onLive("task-changed", load);
  }, [active, load]);
  useEffect(() => { if (active && refresh) load(); }, [active, refresh, load]);
  useEffect(() => {
    const update = () => api.get("/api/runs/live").then(({ data }) => {
      setLive(Object.fromEntries((data.data || []).map((run) => [run.TaskId, run])));
    }).catch(() => {});
    if (!active) return undefined;
    update();
    const interval = setInterval(update, 3000);
    return () => clearInterval(interval);
  }, [active]);
  useEffect(() => active ? pollWhileVisible(() => setClock(Date.now()), 30000) : undefined, [active]);

  const desks = useMemo(() => studioSeats(tasks || [], cap ?? 4), [tasks, cap]);
  const queue = useMemo(() => (tasks || []).filter((task) => task.Status === "open"
    && !studioTaskIsLive(task) && !desks.includes(task)), [tasks, desks]);
  const sceneSeats = useMemo(() => desks.map((task) => task ? {
    task,
    liveRow: live[task.TaskId] || null,
    state: studioTaskState(task, live[task.TaskId], agents, clock),
  } : null), [desks, live, agents, clock]);

  useEffect(() => {
    if (pick && !desks.some((task) => task?.TaskId === pick)) setPick(null);
  }, [desks, pick]);

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  const free = desks.filter((desk) => !desk).length;
  const seated = desks.filter(Boolean);

  return (
    <Box sx={{ position: "relative", width: "100%", height: "calc(100vh - 190px)", minHeight: 540,
      overflow: "hidden", bgcolor: "#f8f6f2" }}>
      <Box sx={{ position: "absolute", inset: { xs: "0", md: "0 0 0 238px" } }}>
        <React.Suspense fallback={<Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
          <StudioScene seats={sceneSeats} selectedId={pick} onSelect={setPick} />
        </React.Suspense>
      </Box>

      <Box sx={{ position: "absolute", zIndex: 6, left: 16, top: 12, width: 300, bgcolor: PANEL,
        border: `1px solid ${BORDER}`, borderRadius: "12px", boxShadow: "0 12px 34px rgba(30,50,38,.12)",
        overflow: "hidden", display: "flex", flexDirection: "column", maxHeight: "calc(100% - 82px)" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.4, pb: 1.1,
          borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: ROLES.working.solid,
            boxShadow: "0 0 0 4px rgba(111,138,110,.10)" }} />
          <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT, flex: 1 }}>
            IN THE STUDIO
          </Typography>
          <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{seated.length}/{desks.length}</Typography>
        </Box>

        <Box sx={{ overflowY: "auto", minHeight: 0 }}>
          {seated.map((task) => {
            const liveRow = live[task.TaskId];
            const state = studioTaskState(task, liveRow, agents, clock);
            const selected = pick === task.TaskId;
            const color = state.tone === "waiting" ? ROLES.you.solid : ROLES.working.solid;
            return (
              <Box key={task.TaskId} onClick={() => setPick(task.TaskId)}
                sx={{ px: 1.75, py: 1.05, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
                  borderLeft: `3px solid ${selected ? color : "transparent"}`,
                  bgcolor: selected ? "#f4f1ec" : "transparent", "&:hover": { bgcolor: "#f4f1ec" } }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />
                  <Typography noWrap sx={{ fontSize: 10.5, fontWeight: 700, color }}>{state.agent}</Typography>
                  <Typography sx={{ ...mono, fontSize: 10, color: FAINT, ml: "auto" }}>{task.ref}</Typography>
                  {task.Waiting > 0 && (
                    <Typography sx={{ ...mono, fontSize: 10, color: "#6b5f45", fontWeight: 700 }}
                      title={`${task.Waiting} queued prompt${task.Waiting === 1 ? "" : "s"} waiting in the funnel`}>
                      ✎ {task.Waiting}
                    </Typography>
                  )}
                </Box>
                <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 650, color: INK, pt: 0.35 }}>{task.Title}</Typography>
                <Typography sx={{ fontSize: 10.5, color, pt: 0.2 }}>{state.label}</Typography>
                {liveRow?.work && (
                  <Box sx={{ pt: 0.5 }}>
                    <WorkLine work={liveRow.work} who={state.agent} waiting={liveRow.kind === "session" && isWaiting(liveRow)}
                      asking={liveRow.asking} startedAt={liveRow.StartedAt} />
                  </Box>
                )}
                {liveRow?.files?.length > 0 && <Box sx={{ pt: 0.6 }}><FileChips files={liveRow.files} /></Box>}
                {selected && (
                  <Typography onClick={(event) => { event.stopPropagation(); onOpenTask(task.TaskId); }}
                    sx={{ fontSize: 11.5, fontWeight: 700, color: ACCENT, pt: 0.6,
                      "&:hover": { textDecoration: "underline" } }}>
                    Open the task →
                  </Typography>
                )}
              </Box>
            );
          })}
          {!seated.length && (
            <Typography sx={{ px: 1.75, py: 1.5, fontSize: 12, color: FAINT, lineHeight: 1.55 }}>
              The studio is quiet. New work will bring an agent to a desk.
            </Typography>
          )}

          {queue.length > 0 && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.15, pb: 0.85,
              bgcolor: "#f4f1ec", borderBottom: `1px solid ${BORDER}` }}>
              <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.15, color: FAINT, flex: 1 }}>
                WAITING FOR A DESK
              </Typography>
              <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{queue.length}</Typography>
            </Box>
          )}
          {queue.slice(0, 6).map((task) => (
            <Box key={task.TaskId} onClick={() => onOpenTask(task.TaskId)}
              sx={{ px: 1.75, py: 0.9, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
                "&:hover": { bgcolor: "#f4f1ec" } }}>
              <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>
                {task.ref}{task.Waiting > 0 ? <Box component="span" sx={{ color: "#6b5f45", fontWeight: 700, ml: 0.75 }}>✎ {task.Waiting}</Box> : null}
              </Typography>
              <Typography noWrap sx={{ fontSize: 12.5, color: DIM, pt: 0.2 }}>{task.Title}</Typography>
            </Box>
          ))}
          {queue.length > 6 && (
            <Typography sx={{ px: 1.75, py: 0.9, fontSize: 11, color: FAINT }}>
              +{queue.length - 6} more waiting · Columns lists them all
            </Typography>
          )}
        </Box>

        <Box sx={{ px: 1.75, pt: 1.1, pb: 1.3, borderTop: `1px solid ${BORDER}`, flexShrink: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75 }}>
            <Typography sx={{ fontSize: 11, color: DIM, flex: 1 }}>Agents at once</Typography>
            <Typography sx={{ ...mono, fontSize: 12.5, fontWeight: 700, color: INK }}>{cap ?? "—"}</Typography>
            <Typography sx={{ fontSize: 11, color: FAINT }}>{free} free</Typography>
          </Box>
          <Slider size="small" min={1} max={8} step={1} marks value={cap ?? 4}
            onChange={(_, value) => setCap(value)}
            onChangeCommitted={(_, value) => api.patch("/api/settings", {
              name: "auto_sessions", value: String(value),
            }).catch(() => {})}
            sx={{ mt: 0.25, color: ACCENT, "& .MuiSlider-markActive": { bgcolor: PANEL } }} />
        </Box>
      </Box>

      <Typography sx={{ position: "absolute", zIndex: 5, right: 16, bottom: 14, fontSize: 10.5,
        color: FAINT, textAlign: "right", lineHeight: 1.6, pointerEvents: "none" }}>
        Real tasks · real agents · live session output on each screen
      </Typography>
    </Box>
  );
}
