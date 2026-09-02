// The one thing a Timeline row says about itself: a small mark, its word, and the colour its
// card's left edge takes. See timelineState.js for WHY there is only one (three overlapping
// controls used to answer the same question and could disagree).
//
// Deliberately not a Chip. A pill on every row makes the whole column loud, which is the same
// as making none of it loud - and this app spends oxblood on exactly one thing. The mark and
// the word carry the meaning; the edge carries the colour.
import React from "react";
import { Box, CircularProgress, Tooltip } from "@mui/material";
import { BORDER, ROLES } from "./theme.jsx";
import { stateMeta, stateOf } from "./timelineState.js";
import { TaskuaryMark } from "./ui.jsx";

export const edgeOf = (key) => {
  const role = stateMeta(key).role;
  return role ? ROLES[role].solid : BORDER;
};

export const StateMark = ({ row, state, size = "sm", showWord = true }) => {
  const key = state || stateOf(row);
  const s = stateMeta(key, row);
  const ink = s.role ? ROLES[s.role].ink : ROLES.muted.ink;
  const big = size === "md";
  return (
    <Tooltip title={s.hint} placement="top" enterDelay={500}>
      <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, flexShrink: 0,
        color: ink, fontSize: big ? 11.5 : 10, fontWeight: s.loud ? 700 : 600, whiteSpace: "nowrap",
        lineHeight: 1.5, cursor: "default" }}>
        {/* the glyph is not decoration - it is the fastest-read half of the pair, so it gets
            its own line-height and never inherits the label's letter-spacing */}
        {s.mark === "spinner" ? <CircularProgress size={big ? 13 : 11.5} thickness={5}
          aria-label="triage in progress" sx={{ color: "currentColor" }} />
          : s.mark === "taskuary" ? <TaskuaryMark size={big ? 13 : 12} /> : (
          <Box component="span" aria-hidden sx={{ fontSize: big ? 13 : 11.5, lineHeight: 1,
            filter: "saturate(.9)" }}>{s.mark}</Box>
        )}
        {showWord && s.word}
      </Box>
    </Tooltip>
  );
};

export default StateMark;
