// A CARD YOU PRESSED STAYS IN ITS TURN (the owner, 2026-11-09: "leave the approval card in the agent turn as well with approved"): the press it
// took drawn pressed, what came of it beside it - as the held steps' card does (HeldSteps, PressedButton).
// ...AND A CARD YOU MOVED PAST IS THE SAME CARD, ITS BUTTONS GREYED (the owner, 2026-11-18: "don't need reason. just keep it with buttons but
// the buttons grayed out once you moved on"): every card draws it by one prop, `past` (MovedPast) - its own layout and words, nothing to press,
// no line saying why
import React from "react";
import { Box, Typography } from "@mui/material";
import { failedAsk, proposalPresentation, heldLead, proposalFrom, resultOf } from "./reviewProposal.js";
import Artifact from "./Artifact.jsx";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export const PASSED_NOTE = "set aside when you moved on";
export const isPassed = (r) => r?.Status === "superseded" && [PASSED_NOTE, "not needed - the agent finished without it"].includes(r?.DecideNote);

// A DRAFT THE AGENT REPLACED IN A LATER TURN (wrapup.REPLACED): its record where it stood - what it said, dimmed, nothing to press
export const REPLACED_NOTE = "superseded - a later turn's reply took its place";
export const isReplaced = (r) => r?.Status === "closed_unsent" && r?.DecideNote === REPLACED_NOTE && !!String(r?.DraftText || "").trim();

// ...A MOVED-PAST CARD IS DRAWN AS IT STOOD WHILE IT WAITED: its review read as pending, nothing of how it was settled
export const asLive = (r) => (r ? { ...r, Status: "pending", DecidedAt: null, DecideNote: null, ActError: null, FinalText: null } : r);
// ...greyed, every control in it off at once - a disabled fieldset turns off each button, box and field under it, and `inert` the links drawn
// as text too: no press, no focus, no Tab stop. Once: a card inside one (a bulk card's rows) is greyed by it, never twice as faint
const Within = React.createContext(false);
const GREY = { border: 0, margin: 0, padding: 0, minWidth: 0, opacity: 0.6, filter: "grayscale(1)", pointerEvents: "none" };
export const MovedPast = ({ on, children }) => { const inside = React.useContext(Within); return !on || inside ? children
  : <Within.Provider value><fieldset disabled inert="" data-tq-moved-past="" aria-disabled="true" style={GREY}>{children}</fieldset></Within.Provider>; };

// the press a card took, drawn pressed: "approved" | "dismissed" (| "failed", the held steps') - or any other with its own `label` (a reply's
// "✓ Sent", a landing's "✓ Pushed"). A MARK, NEVER A BUTTON (the owner, 2026-11-11: "a card that cannot be pressed shows no button" - the card
// round, 2026-11-12, found a greyed <button> on every settled card: nothing to press, yet a stop for the Tab key and "button, dimmed" to a
// screen reader): the same look, said as the card's status. ONE mark for every card that was pressed
export const PressedButton = ({ pressed, label = "" }) => { const no = ["dismissed", "discard", "failed"].includes(pressed); return (
  <Box component="span" role="status" data-tq-pressed={pressed} sx={{ display: "inline-flex", alignItems: "center", flexShrink: 0, px: 1.25, py: 0.5, borderRadius: 1, fontSize: 13, fontWeight: 500,
    lineHeight: 1.75, whiteSpace: "nowrap", ...(no ? { color: FAINT, boxShadow: `inset 0 0 0 1px ${BORDER}` } : { bgcolor: "var(--tq-tint-sage, #dfe8dd)", color: "var(--tq-success, #47654a)" }) }}>
    {label || (pressed === "failed" ? "✗ Failed" : no ? "✗ Dismissed" : "✓ Approved")}</Box>); };

export default function PassedCard({ reviews }) {
  const rs = [...(reviews || [])].sort((a, b) => a.ReviewId - b.ReviewId), r = rs[0] || {};
  // ...A SETTLED CARD SAYS WHAT IT WAS, never that it waits (the card round, 2026-11-12: "The agent's browser waits for your yes" over
  // "✓ Approved", and over "Set aside when you moved on"): its lead - what it does, in words - where it has one, and its result once, not the
  // lead a second time
  const p = proposalPresentation(r), title = p?.lead || p?.title || heldLead(proposalFrom(r) || {}).lead;
  const done = resultOf(r), failed = failedAsk(r), pressed = done ? "approved" : failed ? "failed" : "dismissed";
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
  const line = done ? (!same(done.what, title) && done.what) || (p?.destination ? `${p.destinationLabel} ${p.destination}` : "") : failed ? String(r.ActError) : "Nothing was done.";
  return (
    <Artifact data-tq-passed={r.ReviewId || ""} data-tq-act-state={pressed} sx={{ px: 1.5, py: 1.25 }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>
        {rs.length > 1 ? `${title} - ${rs.length} steps` : title}</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.6, flexWrap: "wrap" }}>
        <PressedButton pressed={pressed} />
        {!!(line || done?.url) && <Typography role="status" data-tq-passed-line="" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>{line}
          {done?.url && <>{line ? " · " : ""}<a href={done.url} target="_blank" rel="noreferrer">{done.url.replace(/^https?:\/\//, "").slice(0, 70)}</a></>}</Typography>}
      </Box>
    </Artifact>
  );
}
