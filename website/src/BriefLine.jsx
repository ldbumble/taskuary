// TASKUARY'S INSTRUCTIONS ARE NOT THE OWNER'S WORDS (the owner, 2026-10-30): an agent that started by itself was shown its brief -
// "THIS TASK IS A REPLY OWED...", "A QUICK LOOK CAME FIRST..." - under YOU, as though the owner had typed it. The server marks it at the
// source (general.BRIEF_ACTOR on a chat turn, a `brief` step in a coding record); here it is one grey line, the full text a click away.
import React from "react";
import { Box } from "@mui/material";
import { FAINT, INK, PANEL2 } from "./theme.jsx";

export const BRIEF_LABEL = "Taskuary's instructions";

export default function BriefLine({ text, children }) {
  return (
    <Box component="details" data-tq-brief="" sx={{ minWidth: 0, fontSize: 12, color: FAINT }}>
      <Box component="summary" sx={{ cursor: "pointer", width: "fit-content", fontWeight: 600, "&:hover": { color: INK } }}>{BRIEF_LABEL}</Box>
      <Box sx={{ mt: 0.5, p: 1, borderRadius: 1, bgcolor: PANEL2, color: INK, fontSize: 12.5, lineHeight: 1.45, whiteSpace: "pre-wrap",
        overflowWrap: "anywhere", "& p": { m: 0, whiteSpace: "pre-wrap" } }}>{children ?? text}</Box>
    </Box>);
}
