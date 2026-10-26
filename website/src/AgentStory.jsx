// The agent step's account when nothing is live: the reason it never started, or - for a session that went - its last
// message and the moments of the run, the cut in oxblood. Facts the worker recorded, no model (funnel.agent_story).
// With a record to show it is only the record's first line and its timeline (AgentRecord); this whole block is for a
// session that left no record at all (the owner, 2026-10-12: "follow the format of all agents. main summary, then
// details behind more").
import React, { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import { BORDER, DIM, FAINT, INK, PALETTE, mono } from "./theme.jsx";
import { hhmm, storyAlarm } from "./agentStory.js";
import { trustInBox } from "./strangerLine.js";

const head = { fontSize: 11, fontWeight: 600, color: FAINT, letterSpacing: ".04em", textTransform: "uppercase", mb: 0.35 };
const link = { fontSize: 11, minHeight: 0, p: 0, minWidth: 0 };

export function StoryChip({ kind, text }) {
  const hot = storyAlarm(kind);
  return text ? <Box component="span" sx={{ fontSize: 11, fontWeight: 600, borderRadius: 99, px: 1, py: 0.2, whiteSpace: "nowrap",
    color: hot ? PALETTE.oxblood : PALETTE.slate, bgcolor: hot ? "#f3e6e8" : "#e6ebef" }}>{text}</Box> : null;
}

// the state in one sentence: what happened to the session and what you can do about it. The server's sentence is whole
// and leads with its state ("Waiting for you.", "Couldn't start."): the profile's name and a verb glued in front named a
// profile as the actor over a reason fragment (the owner, 2026-10-16), so nothing is added here
export const StoryLine = ({ kind, line }) => (
  <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
    <ErrorOutlineIcon sx={{ fontSize: 16, mt: 0.25, flex: "none", color: storyAlarm(kind) ? PALETTE.oxblood : PALETTE.slate }} />
    <Typography sx={{ fontSize: 13.5, lineHeight: 1.45, color: INK }}>
      {line}
    </Typography>
  </Box>);

// the moments of the run - started, asked, finished a turn, cut off
export const Timeline = ({ steps }) => (
  <Box sx={{ display: "grid", gridTemplateColumns: "52px minmax(0, 1fr)", rowGap: 0.6, columnGap: 1.25 }}>
    {steps.map((s, i) => <React.Fragment key={i}>
      <Typography sx={{ ...mono, fontSize: 11.5, color: s.cut ? PALETTE.oxblood : FAINT }}>{hhmm(s.at)}</Typography>
      <Typography sx={{ fontSize: 12.5, color: s.cut ? PALETTE.oxblood : DIM, fontWeight: s.cut ? 500 : 400 }}>{s.text}</Typography>
    </React.Fragment>)}
  </Box>);

// A HELD STEP'S WAY OUT, in the box that says why nothing started (the owner, 2026-10-26: "we should have button on untrusted user to
// either trust user or trust domain"): the person, and their organisation when there is one to name (senders.trust_offer). A press
// only lifts the hold - the step's own Start is still the owner's to press
export const TrustButtons = ({ trust, onTrust }) => (
  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 0.9, pl: 3 }}>
    <Button size="small" variant="outlined" data-tq-trust="" sx={{ fontSize: 12, py: 0.2 }} onClick={() => onTrust("")}>{trust.person}</Button>
    {trust.org && <Button size="small" variant="outlined" data-tq-trust-org="" sx={{ fontSize: 12, py: 0.2 }} onClick={() => onTrust("org")}>{trust.org}</Button>}
  </Box>);

// folded (`compact`) the step says its one sentence; open, the last thing it said leads and the timeline is behind More
export default function AgentStory({ story, compact = false, onTrust }) {
  const [more, setMore] = useState(false);
  if (!story?.line) return null;
  const steps = compact ? [] : story.steps || [], said = !compact && story.said;
  return (
    <Box sx={{ mt: 1, pl: { xs: 0, sm: 4 } }}>
      <StoryLine kind={story.kind} line={story.line} />
      {onTrust && trustInBox(story) && <TrustButtons trust={story.trust} onTrust={onTrust} />}
      {(said || steps.length > 0) && (
        <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          {said && <>
            <Typography sx={head}>Its last message{story.said_at ? <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · {hhmm(story.said_at)}</Box> : ""}</Typography>
            <Box sx={{ fontSize: 13, lineHeight: 1.5, color: INK, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{said}</Box>
          </>}
          {steps.length > 0 && <Box sx={{ mt: said ? 1 : 0 }}>
            <Button size="small" sx={link} onClick={() => setMore(!more)}>More · the timeline {more ? "▾" : "▸"}</Button>
            {more && <Box sx={{ mt: 0.8 }}><Timeline steps={steps} /></Box>}
          </Box>}
        </Box>
      )}
    </Box>
  );
}
