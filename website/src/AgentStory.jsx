import { t as tx } from "./i18n.js";
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

// the other kinds' sentences already name the agent ("It was handed to coder…", "coder ran on this…")
const LEAD = { held: "did not start", interrupted: "was cut off" };
const head = { fontSize: 11, fontWeight: 600, color: FAINT, letterSpacing: ".04em", textTransform: "uppercase", mb: 0.35 };
const link = { fontSize: 11, minHeight: 0, p: 0, minWidth: 0 };

export function StoryChip({ kind, text }) {
  const hot = storyAlarm(kind);
  return text ? <Box component="span" sx={{ fontSize: 11, fontWeight: 600, borderRadius: 99, px: 1, py: 0.2, whiteSpace: "nowrap",
    color: hot ? PALETTE.oxblood : PALETTE.slate, bgcolor: hot ? "#f3e6e8" : "#e6ebef" }}>{text}</Box> : null;
}

// the state in one sentence: what happened to the session and what you can do about it
export const StoryLine = ({ kind, line, who }) => (
  <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
    <ErrorOutlineIcon sx={{ fontSize: 16, mt: 0.25, flex: "none", color: storyAlarm(kind) ? PALETTE.oxblood : PALETTE.slate }} />
    <Typography sx={{ fontSize: 13.5, lineHeight: 1.45, color: INK }}>
      {who && LEAD[kind] && <b style={{ fontWeight: 600 }}>{who} {LEAD[kind]}: </b>}{line}
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

// folded (`compact`) the step says its one sentence; open, the last thing it said leads and the timeline is behind More
export default function AgentStory({ story, who, compact = false }) {
  const [more, setMore] = useState(false);
  if (!story?.line) return null;
  const steps = compact ? [] : story.steps || [], said = !compact && story.said;
  return (
    <Box sx={{ mt: 1, pl: { xs: 0, sm: 4 } }}>
      <StoryLine kind={story.kind} line={story.line} who={who} />
      {(said || steps.length > 0) && (
        <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          {said && <>
            <Typography sx={head}>{tx("Its last message")}{story.said_at ? <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · {hhmm(story.said_at)}</Box> : ""}</Typography>
            <Box sx={{ fontSize: 13, lineHeight: 1.5, color: INK, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{said}</Box>
          </>}
          {steps.length > 0 && <Box sx={{ mt: said ? 1 : 0 }}>
            <Button size="small" sx={link} onClick={() => setMore(!more)}>{tx("More · the timeline")} {more ? "▾" : "▸"}</Button>
            {more && <Box sx={{ mt: 0.8 }}><Timeline steps={steps} /></Box>}
          </Box>}
        </Box>
      )}
    </Box>
  );
}
