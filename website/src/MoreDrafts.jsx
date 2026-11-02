// THE OTHER REPLIES WAITING on this task (pendingDrafts.js): each under its own "Answering <who>" line, with the same decision the
// queue mounts - its own To, its own Send. One letter's press never sends, rewrites or hides another.
import React from "react";
import { Box, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { draftAnswers } from "./pendingDrafts.js";
import { cleanText } from "./ui.jsx";
import { BORDER, DIM, FAINT } from "./theme.jsx";

export default function MoreDrafts({ reviews = [], messages = [], onChanged }) {
  if (!reviews.length) return null;
  return reviews.map((r) => {
    const a = draftAnswers(r, messages), who = a?.FromName || a?.FromEmail || r.FromName || r.FromEmail || "";
    return (
      <Box key={r.ReviewId} data-tq-more-draft={r.ReviewId} sx={{ mt: 1.4, pt: 1.1, borderTop: `1px solid ${BORDER}` }}>
        {who && <Typography sx={{ fontSize: 12.5, color: FAINT, mb: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          Answering <Box component="span" sx={{ color: DIM, fontWeight: 600 }}>{who}</Box>{a ? `: ${cleanText(a.ReadText || a.BodyText || a.Subject || "")}` : ""}</Typography>}
        <ReviewDecision review={r} onChanged={onChanged} />
      </Box>);
  });
}
