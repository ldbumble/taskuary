// A CARD YOU HAVE MOVED PAST IS OLD NEWS (the owner, 2026-11-10: "no once youa re passed it, it should stay where it is with buttons grayed
// out. You can ask the agent to bring it back?"): the server settles it (proposals.move_on) and it stays a row of the chat where its turn raised
// it - what it would have done, its button greyed, and the way back in one line. ONE look for every kind: a proposal, a post, held steps.
// ...AND A CARD YOU PRESSED stays the same way (the owner, 2026-11-09: "leave the approval card in the agent turn as well with approved"): the
// press it took drawn pressed, what came of it beside it - as the held steps' card does (HeldSteps, PressedButton)
import React from "react";
import { Box, Typography } from "@mui/material";
import { proposalPresentation, heldLead, proposalFrom, resultOf } from "./reviewProposal.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export const PASSED_NOTE = "set aside when you moved on";
// ...said as what happens next (the owner, 2026-11-12: "the agent should bring it up"): its agent was told, and raises it again if still needed
export const PASSED_LINE = "Set aside when you wrote again - the agent raises it again if it is still needed.";
export const isPassed = (r) => r?.Status === "superseded" && r?.DecideNote === PASSED_NOTE;

// A DRAFT THE AGENT REPLACED IN A LATER TURN (wrapup.REPLACED): its record where it stood - what it said, dimmed, nothing to press
export const REPLACED_NOTE = "superseded - a later turn's reply took its place";
export const isReplaced = (r) => r?.Status === "closed_unsent" && r?.DecideNote === REPLACED_NOTE && !!String(r?.DraftText || "").trim();

// the press a card took, drawn pressed: "approved" | "dismissed" (| "failed", the held steps') - or any other with its own `label` (a reply's
// "✓ Sent", a landing's "✓ Pushed"). A MARK, NEVER A BUTTON (the owner, 2026-11-11: "a card that cannot be pressed shows no button" - the card
// round, 2026-11-12, found a greyed <button> on every settled card: nothing to press, yet a stop for the Tab key and "button, dimmed" to a
// screen reader): the same look, said as the card's status. ONE mark for every card that was pressed
export const PressedButton = ({ pressed, label = "" }) => { const no = pressed === "dismissed" || pressed === "discard"; return (
  <Box component="span" role="status" data-tq-pressed={pressed} sx={{ display: "inline-flex", alignItems: "center", flexShrink: 0, px: 1.25, py: 0.5, borderRadius: 1, fontSize: 13, fontWeight: 500,
    lineHeight: 1.75, whiteSpace: "nowrap", ...(no ? { color: FAINT, boxShadow: `inset 0 0 0 1px ${BORDER}` } : { bgcolor: "var(--tq-tint-sage, #dfe8dd)", color: "var(--tq-success, #47654a)" }) }}>
    {label || (no ? "✗ Dismissed" : "✓ Approved")}</Box>); };

export default function PassedCard({ reviews }) {
  const rs = [...(reviews || [])].sort((a, b) => a.ReviewId - b.ReviewId), r = rs[0] || {};
  // ...A SETTLED CARD SAYS WHAT IT WAS, never that it waits (the card round, 2026-11-12: "The agent's browser waits for your yes" over
  // "✓ Approved", and over "Set aside when you moved on"): its lead - what it does, in words - where it has one, and its result once, not the
  // lead a second time
  const p = proposalPresentation(r), title = p?.lead || p?.title || heldLead(proposalFrom(r) || {}).lead;
  const passed = isPassed(r), done = resultOf(r), pressed = passed ? "passed" : done ? "approved" : "dismissed";
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
  const line = passed ? PASSED_LINE : done ? (!same(done.what, title) && done.what) || (p?.destination ? `${p.destinationLabel} ${p.destination}` : "") : "Nothing was done.";
  return (
    <Box data-tq-passed={r.ReviewId || ""} data-tq-act-state={pressed} sx={{ mt: 0.5, px: 1.25, py: 0.9, border: `1px solid ${BORDER}`, borderRadius: 1.5,
      bgcolor: "var(--tq-panel, #fff)", opacity: passed ? 0.6 : 1 }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>
        {rs.length > 1 ? `${title} - ${rs.length} steps` : title}</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.6, flexWrap: "wrap" }}>
        {/* ...one nobody can press draws no button (the owner, 2026-11-11: "2 approve buttons?"): what became of it, in words */}
        {!passed && <PressedButton pressed={pressed} />}
        {!!(line || done?.url) && <Typography role="status" data-tq-passed-line="" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>{line}
          {done?.url && <>{line ? " · " : ""}<a href={done.url} target="_blank" rel="noreferrer">{done.url.replace(/^https?:\/\//, "").slice(0, 70)}</a></>}</Typography>}
      </Box>
    </Box>
  );
}
