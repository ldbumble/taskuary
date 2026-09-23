import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { useCalendarToday } from "./calendarToday.js";
import { fmtTime12 } from "./ui.jsx";
import { DIM, FAINT, INK, mono } from "./theme.jsx";

// The day's meetings as one strip above today's Morning digest: a track from 7 to 7, each
// meeting at its hour, plus the compact numbered list that still works for short meetings.
// Timeline and Assistant intentionally share this component so the brief cannot drift again.
export default function TodayMeetingsStrip() {
  // the last answer at once, a fresh one behind it (calendarToday.js) - never a pop-in
  const today = useCalendarToday();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((value) => value + 1), 60000);
    return () => clearInterval(id);
  }, []);
  if (!today) return null;
  const events = (today.events || []).filter((event) => !event.all_day);
  const allDay = (today.events || []).filter((event) => event.all_day);
  if (!today.events?.length) return null;
  const H0 = 7, H1 = 19, span = H1 - H0;
  const hourOf = (stamp) => {
    const date = new Date(String(stamp).replace(" ", "T"));
    return date.getHours() + date.getMinutes() / 60;
  };
  const now = new Date();
  const nowHour = now.getHours() + now.getMinutes() / 60;
  const pct = (hour) => `${Math.max(0, Math.min(100, ((hour - H0) / span) * 100))}%`;
  return (
    <Box data-tick={tick} sx={{ mb: 1.5, p: 1.25, bgcolor: "#f5f0e4", border: "1px solid #e3d9c2", borderRadius: 2,
      "@keyframes tqSlide": { from: { opacity: 0, transform: "translateY(6px) scaleX(.6)" }, to: { opacity: 1, transform: "none" } },
      "@keyframes tqPulse": { "0%": { boxShadow: "0 0 0 0 rgba(138,54,70,.45)" }, "100%": { boxShadow: "0 0 0 8px rgba(138,54,70,0)" } } }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.75 }}>
        <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: "#6b5f45", fontWeight: 700 }}>📅 TODAY’S MEETINGS · {today.events.length}</Typography>
        {allDay.map((event) => <Typography key={event.subject} variant="caption" sx={{ color: FAINT }}>· all day: {event.subject}</Typography>)}
      </Box>
      <Box sx={{ position: "relative", height: 44, borderTop: "1px solid #ddd2b9", borderBottom: "1px solid #ddd2b9" }}>
        {Array.from({ length: span + 1 }, (_, index) => H0 + index).map((hour) => (
          <Box key={hour} sx={{ position: "absolute", left: pct(hour), top: 0, bottom: 0, borderLeft: `1px dotted ${hour % 3 === 0 ? "#c9b98f" : "#e6dcc3"}` }}>
            {hour % 3 === 0 && <Typography sx={{ ...mono, fontSize: 8.5, color: FAINT, position: "absolute", top: 46, left: -8 }}>{hour > 12 ? `${hour - 12}p` : hour === 12 ? "12p" : `${hour}a`}</Typography>}
          </Box>
        ))}
        {events.map((event, index) => {
          const start = hourOf(event.start), end = event.end ? hourOf(event.end) : start + 0.5;
          const live = nowHour >= start && nowHour <= end, past = nowHour > end;
          const wide = end - start >= 1.25;
          return (
            <Box key={`${event.start}-${index}`} title={`${event.subject}${event.who?.length ? ` · with ${event.who.join(", ")}` : ""}${event.about ? `\n${event.about}` : ""}`}
              sx={{ position: "absolute", left: pct(start), width: `calc(${pct(Math.max(end, start + 0.35))} - ${pct(start)})`, top: 8, height: 28, borderRadius: 1,
                bgcolor: live ? "#8a3646" : past ? "#d9cfb6" : "#8a7a5c", color: live || !past ? "#fffdfb" : "#6b5f45",
                px: wide ? 0.75 : 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
                fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", textOverflow: "ellipsis",
                transformOrigin: "left center", animation: `tqSlide .5s ease ${index * 0.08}s both`, cursor: "default" }}>
              <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{wide ? event.subject : index + 1}</Box>
            </Box>
          );
        })}
        {nowHour >= H0 && nowHour <= H1 && (
          <Box sx={{ position: "absolute", left: pct(nowHour), top: -4, bottom: -4, width: 2, bgcolor: "#8a3646", borderRadius: 1 }}>
            <Box sx={{ position: "absolute", top: -5, left: -4, width: 10, height: 10, borderRadius: "50%", bgcolor: "#8a3646", animation: "tqPulse 1.6s ease-out infinite" }} />
          </Box>
        )}
      </Box>
      <Box sx={{ mt: 2.25, display: "flex", flexDirection: "column", gap: 0.35 }}>
        {events.map((event, index) => (
          <Typography key={`${event.start}-l${index}`} variant="caption" sx={{ color: INK, display: "flex", gap: 0.75, alignItems: "baseline", flexWrap: "wrap", animation: `tqSlide .4s ease ${0.3 + index * 0.06}s both` }}>
            <Box component="span" sx={{ ...mono, color: "#6b5f45", fontSize: 10, minWidth: 16, textAlign: "right" }}>{index + 1}.</Box>
            <Box component="span" sx={{ ...mono, color: "#6b5f45", fontSize: 10.5, minWidth: 62 }}>{fmtTime12(event.start)}</Box>
            <Box component="span" sx={{ fontWeight: 600, overflowWrap: "anywhere" }}>{event.subject}</Box>
            {!!(event.who || []).length && <Box component="span" sx={{ color: DIM }}>with {event.who.slice(0, 4).map((who) => who.split(" ")[0]).join(", ")}{event.who.length > 4 ? ` +${event.who.length - 4}` : ""}</Box>}
            {event.about && <Box component="span" sx={{ color: FAINT }}>— {event.about.length > 90 ? `${event.about.slice(0, 90)}…` : event.about}</Box>}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}
