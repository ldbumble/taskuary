import React, { useEffect, useState } from "react";
import { Box, Button, Popover, Typography } from "@mui/material";
import api from "./api.js";
import { label } from "./buttons.js";

// PROPOSE A NEW TIME and FIND A TIME (calwrite.py): Remind me's picker, for a meeting - two or three of the owner's free times that
// fit (the invite's own length, or what the thread asked for), and a day and time of their own below them. A pick DRAFTS the answer
// for the owner's Send; nothing reaches the calendar from here. A card that may not write never opens the list: the server's one
// line comes back to the walk (onRefused) with its sign-in as the way out.
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const plus = (day, time, minutes) => {
  const d = new Date(`${day}T${time}`); d.setMinutes(d.getMinutes() + minutes);
  return `${iso(d)} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

export function SlotPicker({ mid, act, anchor, onClose, onPick, onRefused }) {
  const [got, setGot] = useState(null);
  const [err, setErr] = useState("");
  const [day, setDay] = useState("");
  useEffect(() => {
    let live = true;
    api.get(`/api/messages/${mid}/calendar/slots`, { params: { act } })
      .then(({ data }) => { if (!live) return; if (data?.ok === false) { onClose?.(); onRefused?.(data); } else setGot(data); })
      .catch((e) => { if (live) setErr(e?.response?.data?.detail || e?.message || "the free times could not be read"); });
    return () => { live = false; };
  }, [mid, act]);   // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (s) => { onClose?.(); onPick?.({ start: s.start, end: s.end }); };
  const minutes = got?.minutes || 30;
  return (
    <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
      <Box sx={{ p: 1.5, display: "grid", gap: 1, width: 260 }} data-tq-slots={act}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: "#41525f" }}>
          {act === "propose" ? `Instead of ${got?.now || "that time"}…` : `${minutes} minutes for ${got?.subject || "the meeting"}…`}</Typography>
        {!got && !err && <Typography sx={{ fontSize: 12, color: "#6b6459" }}>Reading your calendar…</Typography>}
        {got && !got.slots?.length && <Typography sx={{ fontSize: 12, color: "#6b6459" }}>No free time in those days - pick one below.</Typography>}
        <Box sx={{ display: "grid", gap: 0.5 }}>
          {(got?.slots || []).map((s) => (
            <Button key={s.start} size="small" variant="outlined" onClick={() => pick(s)} sx={{ justifyContent: "flex-start", fontSize: 12, minHeight: 28 }}>
              {s.label}</Button>
          ))}
        </Box>
        {got && <>
          <Box component="label" sx={{ display: "grid", gap: 0.4, fontSize: 11.5, color: "#6b6459" }}>
            Or pick a day
            <input type="date" min={iso(new Date())} value={day} onChange={(e) => setDay(e.target.value)}
              style={{ font: "inherit", fontSize: 13, padding: "4px 6px", borderRadius: 6, border: "1px solid #d8d1c5" }} />
          </Box>
          {!!day && <Box component="label" sx={{ display: "grid", gap: 0.4, fontSize: 11.5, color: "#6b6459" }}>
            …and a time ({minutes} minutes)
            <input type="time" onBlur={(e) => e.target.value && pick({ start: `${day} ${e.target.value}`, end: plus(day, e.target.value, minutes) })}
              style={{ font: "inherit", fontSize: 13, padding: "4px 6px", borderRadius: 6, border: "1px solid #d8d1c5" }} />
          </Box>}
        </>}
        <Typography sx={{ fontSize: 11, color: "#8a8378" }}>A pick is drafted for your {label("approve")} - nothing goes out before it.</Typography>
        {err && <Typography sx={{ fontSize: 11.5, color: "#7a2f3c" }}>{err}</Typography>}
      </Box>
    </Popover>
  );
}
