// THE AGENT'S DRAFT, SAID WHERE THE AGENT IS (agentDraftAsk.js; the owner, 2026-11-02: "in agent we should just say 'agent drafted a message'
// and take you to the Close out screen"). One small notice per draft - "<agent> drafted a message to <who>" and Open in Close out - never
// the draft itself: it is read, edited and sent in Close out alone. Over a CLI agent's terminal it floats in the pane's top-right corner,
// under the terminal's own buttons there, laid over the terminal so it keeps every row and column; under a general agent it stands at the
// foot of the conversation, where its questions are asked. It goes once the draft is sent or dropped.
import React from "react";
import { Box, Button, Typography } from "@mui/material";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import { noticeLine } from "./agentDraftAsk.js";
import { BORDER, INK } from "./theme.jsx";

// `asks`: the agent's pending drafts (agentDraftAsk.agentAsks); `at`: "popup" (over a terminal) or "chat"; `onOpen(r)`: Close out at that draft
export default function AgentDraftNotice({ asks = [], at = "popup", agent = "The agent", onOpen }) {
  if (!asks.length) return null;
  const pop = at === "popup";
  return (
    <Box data-tq-agent-notice={at} sx={pop ? { position: "absolute", top: 36, right: 10, zIndex: 6, maxWidth: "min(460px, calc(100% - 20px))", display: "grid", gap: 0.75 }
      : { mt: 1.5, mx: { xs: 1, sm: 2 }, display: "grid", gap: 0.75 }}>
      {asks.map((r) => (
        <Box key={r.ReviewId} data-tq-agent-ask={r.ReviewId} role="status" sx={{ display: "flex", alignItems: "center", gap: 0.75, bgcolor: "#fff",
          border: `1px solid ${BORDER}`, borderRadius: pop ? 2 : 1.5, pl: 1.25, pr: 0.5, py: 0.5, minWidth: 0,
          ...(pop ? { boxShadow: "0 8px 22px rgba(32,38,30,.2), 0 2px 5px rgba(32,38,30,.1)" } : {}) }}>
          <ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a", flexShrink: 0 }} />
          <Typography sx={{ flex: 1, minWidth: 0, color: INK, fontWeight: 600, fontSize: 12.5, lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
            title={noticeLine(r, agent)}>{noticeLine(r, agent)}</Typography>
          {/* ...a door to Close out, never a send (pageView.js reads it as the owner's own press) */}
          <Button size="small" data-tq-view-btn="open_draft_in_close_out" onClick={() => onOpen?.(r)} title="Read, edit and send it in Close out"
            sx={{ flexShrink: 0, fontSize: 11.5, minHeight: 26, py: 0, px: 1, whiteSpace: "nowrap" }}>Open in Close out</Button>
        </Box>
      ))}
    </Box>
  );
}
