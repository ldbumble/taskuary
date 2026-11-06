// THE CHAT'S DETAIL LEVEL, a slider like the app's other sliders (the combine level on a connection card): three stops, named under them
// (chatDetail.js). Settings draws it for the two defaults, a chat's corner for its own.
import React, { useEffect, useState } from "react";
import api from "./api.js";
import { Box, Slider, Typography } from "@mui/material";
import { LABELS, LEVELS, SETTING, defaultDetail, detailFor, keepOwnDetail, useOwnDetail } from "./chatDetail.js";
import { DIM, FAINT, INK } from "./theme.jsx";

// ...the two defaults from Settings, read once and kept in step when Settings saves one (chatDefaultsChanged)
let read = null, got = {};
const listeners = new Set();
export function chatDefaultsChanged(name, value) {
  if (!Object.values(SETTING).includes(name)) return;
  got = { ...got, [name]: value }; listeners.forEach((f) => f(got));
}
export function useChatDefaults() {
  const [s, setS] = useState(got);
  useEffect(() => {
    listeners.add(setS);
    read ||= api.get("/api/settings").then(({ data }) => {
      const rows = Array.isArray(data?.data) ? data.data : [];
      got = { ...Object.fromEntries(rows.filter((r) => Object.values(SETTING).includes(r?.Name)).map((r) => [r.Name, r.Value])), ...got };
      listeners.forEach((f) => f(got));
    }).catch(() => {});
    return () => { listeners.delete(setS); };
  }, []);
  return s;
}
const MARKS = LEVELS.map((l, value) => ({ value, label: LABELS[l] }));
export const SAYS = {
  summary: "What the agent said and what it made, and its cards - its steps behind one line.",
  steps: "One line a step, folded under each turn.",
  everything: "Every tool call, with its command, output and diff a press away.",
};

export default function DetailSlider({ value, onChange, label = "How much of the agent's work the chat shows", says = true, width = 260 }) {
  const i = Math.max(0, LEVELS.indexOf(value));
  return <Box data-tq-detail-slider={value} sx={{ px: 1.5, maxWidth: width }}>
    <Slider size="small" min={0} max={LEVELS.length - 1} step={1} marks={MARKS} value={i} aria-label={label}
      getAriaValueText={(v) => LABELS[LEVELS[v]]} onChange={(_, v) => onChange(LEVELS[v])}
      sx={{ mt: 0.5, mb: 2.5, "& .MuiSlider-markLabel": { fontSize: 11, color: FAINT }, "& .MuiSlider-markLabelActive": { color: INK } }} />
    {says && <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.45, mx: -1.5 }}>{SAYS[LEVELS[i]]}</Typography>}
  </Box>;
}

// ...and the chat's own, in its header corner (TaskPage HeadPop): this task's level, kept per task; the default named and one press back to it
export function ChatDetail({ taskId, source }) {
  const defaults = useChatDefaults(), own = useOwnDetail(taskId), dflt = defaultDetail(source, defaults), level = detailFor({ source, settings: defaults, own });
  return <Box data-tq-chat-detail={level}>
    <Typography sx={{ fontSize: 12.5, color: DIM, mb: 1 }}>How much of the agent's work this chat shows</Typography>
    <DetailSlider value={level} onChange={(v) => keepOwnDetail(taskId, v === dflt ? null : v)} width={320} />
    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
      {own ? <>Just this task. <Box component="button" type="button" data-tq-chat-detail-reset="" onClick={() => keepOwnDetail(taskId, null)}
        sx={{ border: 0, p: 0, bgcolor: "transparent", color: "inherit", textDecoration: "underline", cursor: "pointer", font: "inherit" }}>
        Back to the default ({LABELS[dflt]})</Box></> : `The default for ${source === "coding" ? "coding work" : "other work"} - Settings changes it.`}</Typography>
  </Box>;
}
