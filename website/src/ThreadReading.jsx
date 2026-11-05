import React from "react";
import { Box, Typography } from "@mui/material";
import { readingLines, readingOf } from "./threadReading.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

const LEAD = { ask: "Asking", part: "Your part", others: "Others", aside: "Aside", onyou: "On you" };
// What triage made of the thread, in plain lines: drawn atop the general agent's chat and as "What's going on" in Came from. Text only -
// nothing here is pressed (on_you is words until an agent has taken a turn).
export default function ThreadReading({ reading, mails = [], variant = "chat", sx = null }) {
  const r = readingOf(reading), ls = readingLines(r, mails);
  if (!ls.length) return null;
  const from = variant === "from";
  return <Box data-tq-reading={variant} sx={{ minWidth: 0, flexShrink: 0, ...(from ? {} : { px: 1.5, py: 0.75, borderBottom: `1px solid ${BORDER}` }), ...sx }}>
    {from && <Typography sx={{ fontSize: 12, fontWeight: 700, color: DIM, mb: 0.4 }}>What's going on</Typography>}
    {ls.map((l, i) => <Typography key={i} data-tq-reading-line={l.k} sx={{ fontSize: 13, lineHeight: 1.5, color: l.k === "aside" ? FAINT : INK, overflowWrap: "anywhere" }}>
      <Box component="span" sx={{ color: FAINT, fontWeight: 600, fontSize: 11.5, mr: 0.75 }}>{LEAD[l.k]}</Box>{" "}{l.text}</Typography>)}
  </Box>;
}
