// THE AGENT'S DRAFT, ASKED WHERE THE AGENT IS (agentDraftAsk.js; the owner, 2026-11-02). Over a CLI agent's terminal it is a POP-UP: a small
// card floating over the pane's top-right corner, under the terminal's own buttons there - laid over the terminal, never beside or under
// it, so the terminal keeps every row and column it had. Under a general agent it is a card at the foot of its conversation, where its questions are asked. Both draw the card
// Close out draws for the draft (ReviewDecision), handed the very props Close out hands it: its Send is Close out's Send.
import React, { useRef } from "react";
import { Box, Button, Typography } from "@mui/material";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import ReviewDecision from "./ReviewDecision.jsx";
import { useViewExtras, rootOf } from "./pageView.js";
import { BORDER, DIM, INK } from "./theme.jsx";

const who = (r, agent) => String(r.DraftBy || "").startsWith("agent:") ? String(r.DraftBy).slice(6) || agent : agent;
const head = (r, agent) => r.Kind === "clarification" ? `${who(r, agent)} wants to ask the sender` : `${who(r, agent)} drafted a message`;
const sendOf = (box) => box?.querySelector("[data-tq-moves] > button") || null;

// `asks`: the agent's pending drafts (agentDraftAsk.agentAsks); `later(r)` puts one off; `decision`: Close out's own ReviewDecision props
export function AgentDraftPopup({ asks = [], later, agent = "The agent", decision }) {
  const box = useRef(null);
  // ...named for the Assistant (pageView.js): the pop-up's Send is an outward send - lit for the owner, never pressed by the chat - and its
  // box is "Reply draft in the pop-up", told apart from Close out's
  useViewExtras(() => rootOf(box.current), { buttons: asks.map((r, i) => {
    const at = () => sendOf(box.current?.querySelector(`[data-tq-agent-ask="${r.ReviewId}"]`));
    return { id: `popup_send${i ? `_${i + 1}` : ""}`, label: `Send in the pop-up${i ? ` (${i + 1})` : ""}`, send: true, press: () => {},
      get el() { return at(); }, get enabled() { const b = at(); return !!b && !b.disabled; } };
  }) });
  if (!asks.length) return null;
  return (
    <Box ref={box} data-tq-agent-popup="" role="dialog" aria-label="Approve the agent's message"
      sx={{ position: "absolute", top: 36, right: 10, zIndex: 6, width: "min(400px, calc(100% - 20px))", maxHeight: "calc(100% - 46px)", overflowY: "auto",
        display: "grid", gap: 1, "& textarea": { fontSize: "13px !important", lineHeight: "1.5 !important", color: INK, maxHeight: 180 } }}>
      {asks.map((r) => (
        <Box key={r.ReviewId} data-tq-agent-ask={r.ReviewId} sx={{ bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 2.5, px: 1.5, pt: 1, pb: 1.25,
          boxShadow: "0 10px 28px rgba(32,38,30,.22), 0 2px 6px rgba(32,38,30,.12)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
            <ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a" }} />
            <Typography sx={{ flex: 1, minWidth: 0, color: INK, fontWeight: 600, fontSize: 13 }} noWrap>{head(r, agent)}</Typography>
            <Button size="small" data-tq-agent-later="" onClick={() => later?.(r)} title="Hides this - the draft stays in Close out"
              sx={{ minWidth: 0, fontSize: 11.5, color: DIM, py: 0 }}>Later</Button>
          </Box>
          <ReviewDecision review={r} {...decision} compact field="popup_draft" fieldLabel="Reply draft in the pop-up" />
        </Box>
      ))}
    </Box>
  );
}

// ...and under a general agent: the same card at the foot of its conversation, where the agent's questions and their answer box stand
export function AgentDraftCard({ asks = [], agent = "The agent", decision }) {
  if (!asks.length) return null;
  return asks.map((r) => (
    <Box key={r.ReviewId} data-tq-agent-ask={r.ReviewId} data-tq-agent-card="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff",
      "& textarea": { fontSize: "13px !important", lineHeight: "1.5 !important", color: INK } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a" }} />
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13 }}>{head(r, agent)}</Typography>
      </Box>
      <ReviewDecision review={r} {...decision} compact field="agent_draft" fieldLabel="Reply draft under the agent" />
    </Box>
  ));
}
