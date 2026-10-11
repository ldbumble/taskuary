// The agent step's account when nothing is live: the reason it never started, or - for a session that went - its last
// message and the moments of the run, the cut in oxblood. Facts the worker recorded, no model (funnel.agent_story).
import React, { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import { BORDER, DIM, FAINT, INK, PALETTE, PANEL2, mono } from "./theme.jsx";
import { hhmm, storyAlarm } from "./agentStory.js";

// the other kinds' sentences already name the agent ("It was handed to coder…", "coder ran on this…")
const LEAD = { held: "did not start", interrupted: "was cut off" };
const head = { fontSize: 11, fontWeight: 600, color: PALETTE.sage, letterSpacing: ".06em", textTransform: "uppercase" };

export function StoryChip({ kind, text }) {
  const hot = storyAlarm(kind);
  return text ? <Box component="span" sx={{ fontSize: 11, fontWeight: 600, borderRadius: 99, px: 1, py: 0.2, whiteSpace: "nowrap",
    color: hot ? PALETTE.oxblood : PALETTE.slate, bgcolor: hot ? "#f3e6e8" : "#e6ebef" }}>{text}</Box> : null;
}

export default function AgentStory({ story, who, showSaid = true }) {
  const [open, setOpen] = useState(false);
  if (!story?.line) return null;
  const hot = storyAlarm(story.kind), steps = story.steps || [], said = showSaid && story.said;
  return (
    <Box sx={{ mt: 1, pl: { xs: 0, sm: 4 } }}>
      <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
        <ErrorOutlineIcon sx={{ fontSize: 16, mt: 0.25, flex: "none", color: hot ? PALETTE.oxblood : PALETTE.slate }} />
        <Typography sx={{ fontSize: 13.5, lineHeight: 1.45, color: INK }}>
          {who && LEAD[story.kind] && <b style={{ fontWeight: 600 }}>{who} {LEAD[story.kind]}: </b>}
          {story.line}
        </Typography>
      </Box>
      {(said || steps.length > 0) && (
        <Box sx={{ mt: 1.2, pt: 1.2, borderTop: `1px solid ${BORDER}`, display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={head}>What it did so far</Typography>
          {said && <Box>
            <Box sx={{ fontSize: 13, lineHeight: 1.5, color: INK, bgcolor: PANEL2, borderRadius: 2, px: 1.5, py: 1.2, whiteSpace: "pre-wrap",
              maxHeight: open ? "none" : 132, overflow: "hidden" }}>{said}</Box>
            <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", mt: 0.4 }}>
              <Typography sx={{ fontSize: 11.5, color: FAINT }}>{who || "the agent"}'s last message{story.said_at ? `, ${hhmm(story.said_at)}` : ""}</Typography>
              {said.length > 320 && <Button size="small" sx={{ fontSize: 11, minHeight: 0, p: 0, minWidth: 0 }}
                onClick={() => setOpen(!open)}>{open ? "Show less" : "Show more"}</Button>}
            </Box>
          </Box>}
          {steps.length > 0 && <Box sx={{ display: "grid", gridTemplateColumns: "52px minmax(0, 1fr)", rowGap: 0.6, columnGap: 1.25 }}>
            {steps.map((s, i) => <React.Fragment key={i}>
              <Typography sx={{ ...mono, fontSize: 11.5, color: s.cut ? PALETTE.oxblood : FAINT }}>{hhmm(s.at)}</Typography>
              <Typography sx={{ fontSize: 12.5, color: s.cut ? PALETTE.oxblood : DIM, fontWeight: s.cut ? 500 : 400 }}>{s.text}</Typography>
            </React.Fragment>)}
          </Box>}
        </Box>
      )}
    </Box>
  );
}
