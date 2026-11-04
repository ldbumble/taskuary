// EACH TURN ENDS IN THREE PARTS (the closeout-in-chat spec, 2026-11-04): what this is about, what the agent did, and the next steps - the
// drafts waiting on Send, the steps only the owner can take ("On you: …"), or "Nothing left to do here". Words only for now: the draft cards
// come inside Next steps with Task 4.2, and an On you step's mark says whose it is, never a press.
import React from "react";
import { Box, Typography } from "@mui/material";
import { nextSteps } from "./agentSummary.js";
import { Md } from "./md.jsx";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

const HEAD = { display: "block", color: FAINT, fontSize: 11.5, fontWeight: 700, mt: 1, mb: 0.25 };
const LINE = { fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere" };
const who = (r) => r.FromName || r.FromEmail || "";

export default function AgentSummary({ summary, reviews = [], checklist = [], acts = [], cards = true, folded = false }) {
  if (!summary) return null;
  const did = String(summary.did || "").trim(), about = String(summary.about || "").trim();
  if (folded) return did ? (
    <Box component="details" data-tq-summary="folded" className="tq-aui-summary" sx={{ mt: 0.75 }}>
      <Box component="summary" sx={{ ...HEAD, mt: 0, cursor: "pointer", "&:hover": { color: INK } }}>What I did</Box>
      <Box sx={{ ...LINE, color: DIM }}><Md text={did} /></Box>
    </Box>) : null;
  const { drafts, onYou, held, nothing } = nextSteps({ summary, reviews, checklist, acts, cards });
  return (
    <Box data-tq-summary="open" className="tq-aui-summary" sx={{ mt: 1, pt: 0.5, borderTop: `1px solid ${BORDER}` }}>
      {!!about && <><Typography component="span" sx={HEAD}>What this is about</Typography><Typography sx={LINE}>{about}</Typography></>}
      {!!did && <><Typography component="span" sx={HEAD}>What I did</Typography><Box sx={LINE}><Md text={did} /></Box></>}
      {(drafts.length || onYou.length || held.length || nothing) ? <>
        <Typography component="span" sx={HEAD}>Next steps</Typography>
        {drafts.map((r) => <Typography key={r.ReviewId} data-tq-summary-draft={r.ReviewId} sx={LINE}>
          {who(r) ? `A reply to ${who(r)} is drafted and waits for your Send.` : "A reply is drafted and waits for your Send."}</Typography>)}
        {!!held.length && <Typography data-tq-summary-held={held.length} sx={LINE}>
          {held.length === 1 ? "One step waits for your Approve, below." : `${held.length} steps wait for your Approve, below.`}</Typography>}
        {onYou.map((i) => <Typography key={i.id || i.text} data-tq-on-you={i.id || ""} sx={LINE}>
          <Box component="span" title="Only you can do this one" sx={{ color: FAINT, fontWeight: 700, fontSize: 12, mr: 0.6 }}>On you:</Box>{i.text}</Typography>)}
        {nothing && <Typography data-tq-nothing-left="" sx={{ ...LINE, color: DIM }}>Nothing left to do here.</Typography>}
      </> : null}
    </Box>
  );
}
