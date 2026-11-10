// A DRAFT THE AGENT REPLACED IN A LATER TURN (wrapup.REPLACED; the owner, 2026-11-10: "it should go gray and then it should generate new email
// action box under it with new email.."): the card it was, where it stood and as it looked once he prompted past it - greyed, its words as they
// were, nothing to press - and its line laid over its corner. Drawn as the waiting card was (the same card, under the same head in
// GeneralWorkspace RowCards, no row of its own), so the moment it is replaced nothing on the page moves
import React from "react";
import { Box, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { PassedCtx } from "./passedCtx.js";
import { DIM } from "./theme.jsx";

export default function ReplacedDraft({ review: r }) {
  // ...as it waited: its settling (when, why, what went) is not the card's to show again
  const was = { ...r, Status: "pending", DecideNote: null, DecidedAt: null, DecidedBy: null, FinalText: null, DeliveryState: null };
  return (
    <Box data-tq-replaced={r.ReviewId} sx={{ position: "relative", pt: 0.5 }}>
      <PassedCtx.Provider value><ReviewDecision review={was} toRow /></PassedCtx.Provider>
      <Typography role="status" data-tq-replaced-line="" sx={{ position: "absolute", top: 8, right: 0, fontSize: 12, fontWeight: 600, color: DIM }}>Replaced by a newer draft</Typography>
    </Box>
  );
}
