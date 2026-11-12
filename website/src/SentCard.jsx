// A SENT REPLY IS ITS CARD, PRESSED (the owner, 2026-11-09: "leave the card in the turn with the pressed button"): where the draft stood, the
// words that went (three lines, the rest a press away), "✓ Sent" on the button it took, and where it went and what the task does now on the
// same line - the separate "sent" block it gave way to said the same thing with no card around it. Drawn at the press (TaskPage sentHere) and
// after, in the turn that drafted it (TaskPage turnCards), the same card both times.
import React, { useState } from "react";
import { Box, Typography } from "@mui/material";
import { PressedButton } from "./PassedCard.jsx";
import { sentSaid, sentTitle } from "./sentLine.js";
import { fmtDateTime } from "./dates.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";


export default function SentCard(p) {
  const [open, setOpen] = useState(false), long = String(p.text || "").split("\n").length > 3 || String(p.text || "").length > 260;
  return (
    <Box data-tq-sent-here={p.id || ""} data-tq-act-state="sent" sx={{ mt: 0.75, px: 1.25, py: 0.9, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{sentTitle(p)}</Typography>
      {p.to && p.subject && <Typography noWrap sx={{ fontSize: 11.5, color: FAINT }}>To {p.to}</Typography>}
      <Typography data-tq-sent-text="" sx={{ mt: 0.4, fontSize: 13, lineHeight: 1.5, color: DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
        ...(open ? {} : { display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>{p.text}</Typography>
      {long && <Typography {...pressable(() => setOpen((o) => !o))} aria-expanded={open} sx={{ ...FOCUS_RING, display: "inline-block", fontSize: 11.5, color: "var(--tq-link, #55697a)",
        cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>{open ? "Show less" : "Show all"}</Typography>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.6, flexWrap: "wrap" }}>
        <PressedButton pressed="sent" label="✓ Sent" />
        <Typography role="status" data-tq-sent-line="" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>
          {sentSaid(p)}{p.at ? ` · ${fmtDateTime(p.at)}` : ""}</Typography>
      </Box>
    </Box>
  );
}
