import React, { useState } from "react";
import { Box, Button, IconButton, Popover, Tooltip, Typography } from "@mui/material";
import EventIcon from "@mui/icons-material/Event";
import api from "./api.js";
import { remindDay, remindWaiting } from "./taskFilter.js";

// REMIND ME (the owner, 2026-09-25): put an open task away until a day - "remind me of this in 2 weeks, or
// whenever I want". Until then it is Upcoming in Tasks and off the work rail; that morning it is back. One road
// with the Assistant's tool (task.defer): POST /api/tasks/{id}/remind. Tomorrow and Later were the rail's; a
// date belongs to the task.
const QUICK = [["Tomorrow", "tomorrow"], ["Next week", "1 week"], ["In 2 weeks", "2 weeks"], ["In a month", "1 month"]];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// the day picker itself, anchored wherever it was asked for: the task page's button, or the walk's own
// "Remind me" word (the owner, 2026-09-25: "remind me should be a walk button")
// `path`: where the day goes - a task's reminder by default, or an Advisor idea's (its Remind me, 2026-09-27)
// `onLeave` fires AT THE PRESS, before the server answers, so the walk can put the task down at once; `onStay(error)` if it failed
// `live`: an agent session is still open on the task - the picker warns instead of offering days (the owner, 2026-10-01:
// it has to be saved and ended first); the server refuses the day with the same words if one slips through
export function RemindPicker({ task, anchor, onClose, onDone, path, onLeave, onStay, live = false }) {
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const away = remindWaiting(task);
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const set = async (until) => {
    setBusy(true); setErr("");
    const leaving = until !== "none";
    if (leaving) onLeave?.();
    try {
      const { data } = await api.post(path || `/api/tasks/${task.TaskId}/remind`, { until });
      onClose?.(); onDone?.(data);
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "could not set the reminder";
      setErr(msg); if (leaving) onStay?.(msg);
    }
    finally { setBusy(false); }
  };
  return (
    <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
      <Box sx={{ p: 1.5, display: "grid", gap: 1, width: 240 }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: "#41525f" }}>
          {away ? `Away until ${remindDay(task.RemindAt)}` : "Bring it back on…"}</Typography>
        {live && !away ? (
          <Typography sx={{ fontSize: 12, color: "#7a2f3c" }}>
            An agent session is still open on this task. Save and end session first, then put it away.</Typography>
        ) : <>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {QUICK.map(([label, until]) => (
              <Button key={until} size="small" variant="outlined" disabled={busy} onClick={() => set(until)}
                sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1 }}>{label}</Button>
            ))}
          </Box>
          <Box component="label" sx={{ display: "grid", gap: 0.4, fontSize: 11.5, color: "#6b6459" }}>
            Or pick a day
            <input type="date" id={`remind-${task.TaskId}`} min={iso(tomorrow)} disabled={busy}
              onChange={(e) => e.target.value && set(e.target.value)}
              style={{ font: "inherit", fontSize: 13, padding: "4px 6px", borderRadius: 6, border: "1px solid #d8d1c5" }} />
          </Box>
        </>}
        {away && <Button size="small" disabled={busy} onClick={() => set("none")} sx={{ justifySelf: "start", fontSize: 11 }}>Bring it back now</Button>}
        {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
      </Box>
    </Popover>
  );
}

export default function RemindMe({ task, compact = false, sx, onDone, onLeave, onStay, live = false }) {
  const [at, setAt] = useState(null);
  const away = remindWaiting(task);
  const title = away ? `Away until ${remindDay(task.RemindAt)} - change the day or bring it back now`
                     : "Remind me - put it away until a day; it is back on your work rail that morning";
  return (
    <>
      {compact
        ? <Tooltip title={title}><IconButton size="small" sx={{ color: "#55697a", ...sx }} onClick={(e) => setAt(e.currentTarget)}>
            <EventIcon sx={{ fontSize: 16 }} /></IconButton></Tooltip>
        : <Button size="small" variant="outlined" sx={sx} title={title} startIcon={<EventIcon sx={{ fontSize: 16, color: "#55697a" }} />}
            onClick={(e) => setAt(e.currentTarget)}>{away ? `Back ${remindDay(task.RemindAt)}` : "Remind me"}</Button>}
      <RemindPicker task={task} anchor={at} onClose={() => setAt(null)} onDone={onDone} onLeave={onLeave} onStay={onStay} live={live} />
    </>
  );
}
