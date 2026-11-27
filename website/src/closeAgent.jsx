// CLOSING A TASK AN AGENT WORKS - one road, wherever it is pressed (the owner, 2026-10-15: "should do the same exact thing ... make sure it
// uses same code not new code"). The task page's Mark done and the Wall's Close agent both close through the shared task.complete operation
// (PW-215): the agent stops and the task closes (the owner, 2026-11-27) - no write-up of the app's own runs behind it, the chat is the record.
import React from "react";
import { Box, CircularProgress, LinearProgress, Typography } from "@mui/material";
import { runOperation } from "./taskOps.js";
import { DIM, INK, card } from "./theme.jsx";

// the close itself: the one completion road every surface takes
export const completeTask = (api, tid, note) => runOperation(api, "task.complete", tid, note ? { note } : {});

// over a pane that is closing: what the press does, and nothing under it can be typed into or pressed until it is done
export const ClosingCover = () => (
  <Box data-tq-closing-cover="" sx={{ position: "absolute", inset: 0, zIndex: 5, display: "flex", alignItems: "center", justifyContent: "center",
    p: 2, bgcolor: "rgb(var(--tq-panel-rgb, 250 248 245) / .82)", backdropFilter: "blur(1px)", cursor: "progress" }}>
    <Box data-tq-closing="done" sx={{ ...card, bgcolor: "var(--tq-inset, #e3e6e1)", border: "1px solid var(--tq-border, #d2d6cf)", maxWidth: 420, width: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <CircularProgress size={15} />
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }}>Stopping the agent and closing the task…</Typography>
      </Box>
      <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>Its chat stays on the task.</Typography>
      <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />
    </Box>
  </Box>
);
