// A CARD YOU HAVE MOVED PAST IS OLD NEWS (the owner, 2026-11-10: "no once youa re passed it, it should stay where it is with buttons grayed
// out. You can ask the agent to bring it back?"): the server settles it (proposals.move_on) and it stays a row of the chat where its turn raised
// it - what it would have done, its button greyed, and the way back in one line. ONE look for every kind: a proposal, a post, held steps.
import React from "react";
import { Box, Button, Typography } from "@mui/material";
import { proposalPresentation, heldLead, proposalFrom } from "./reviewProposal.js";
import { label as btn } from "./buttons.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export const PASSED_NOTE = "set aside when you moved on";
export const PASSED_LINE = "Set aside when you moved on - ask the agent to bring it back.";
export const isPassed = (r) => r?.Status === "superseded" && r?.DecideNote === PASSED_NOTE;

export default function PassedCard({ reviews }) {
  const rs = [...(reviews || [])].sort((a, b) => a.ReviewId - b.ReviewId), r = rs[0] || {};
  const title = proposalPresentation(r)?.title || heldLead(proposalFrom(r) || {}).lead;
  return (
    <Box data-tq-passed={r.ReviewId || ""} data-tq-act-state="passed" sx={{ mt: 0.5, px: 1.25, py: 0.9, border: `1px solid ${BORDER}`, borderRadius: 1.5,
      bgcolor: "var(--tq-panel, #fff)", opacity: 0.6 }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>
        {rs.length > 1 ? `${title} - ${rs.length} steps` : title}</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.6, flexWrap: "wrap" }}>
        <Button size="small" variant="outlined" disabled data-tq-pressed="passed" sx={{ "&.Mui-disabled": { color: FAINT } }}>{btn("approve", "action")}</Button>
        <Typography role="status" data-tq-passed-line="" sx={{ fontSize: 12, color: DIM }}>{PASSED_LINE}</Typography>
      </Box>
    </Box>
  );
}
