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

export default function RemindMe({ task, compact = false, sx, onDone }) {
  const [at, setAt] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const away = remindWaiting(task);
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const set = async (until) => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${task.TaskId}/remind`, { until });
      setAt(null); onDone?.(data);
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "could not set the reminder"); }
    finally { setBusy(false); }
  };
  const title = away ? `Away until ${remindDay(task.RemindAt)} - change the day or bring it back now`
                     : "Remind me - put it away until a day; it is back on your work rail that morning";
  return (
    <>
      {compact
        ? <Tooltip title={title}><IconButton size="small" sx={{ color: "#55697a", ...sx }} onClick={(e) => setAt(e.currentTarget)}>
            <EventIcon sx={{ fontSize: 16 }} /></IconButton></Tooltip>
        : <Button size="small" variant="outlined" sx={sx} title={title} startIcon={<EventIcon sx={{ fontSize: 16, color: "#55697a" }} />}
            onClick={(e) => setAt(e.currentTarget)}>{away ? `Back ${remindDay(task.RemindAt)}` : "Remind me"}</Button>}
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
        <Box sx={{ p: 1.5, display: "grid", gap: 1, width: 240 }}>
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#41525f" }}>
            {away ? `Away until ${remindDay(task.RemindAt)}` : "Bring it back on…"}</Typography>
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
          {away && <Button size="small" disabled={busy} onClick={() => set("none")} sx={{ justifySelf: "start", fontSize: 11 }}>Bring it back now</Button>}
          {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
        </Box>
      </Popover>
    </>
  );
}
