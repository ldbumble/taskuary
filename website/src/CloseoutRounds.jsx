// CLOSE OUT'S EARLIER ROUNDS (the owner, 2026-11-01: "let's update the close out to match the agent runs type of things that close out happens
// more than once"): under the current round, newest first, each one line - what was done and when - that opens in place to what it answered,
// what went, and how it closed. The same fold as an agent's earlier runs (AgentRecord.FoldLine), so the two panes read as one design.
// Read-only: a round that is over is history, its status lines with it - nothing on it is said on the current round.
import React from "react";
import { Box, Typography } from "@mui/material";
import { FoldLine, FoldList } from "./AgentRecord.jsx";
import { roundHead } from "./closeoutRounds.js";
import { fmtDateTime, fmtDay } from "./dates.js";
import { cleanText } from "./ui.jsx";
import { BORDER, DIM, FAINT } from "./theme.jsx";

const cap = { color: FAINT, fontSize: 10 }, said = { color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap", overflowWrap: "anywhere" };
const Quote = ({ head, children }) => (
  <Box sx={{ mt: 0.6, pl: 1, borderLeft: `2px solid ${BORDER}` }}>
    <Typography variant="caption" sx={cap}>{head}</Typography>
    <Typography variant="body2" sx={said}>{children}</Typography>
  </Box>);

// ONE ROUND, OPEN: what they asked, what went (from here, or typed outside Taskuary), a draft closed unsent, and the close
const Round = ({ r }) => {
  const a = r.answering, who = a?.FromName || a?.FromEmail || "";
  return (<>
    {a && <Typography sx={{ fontSize: 12.5, color: FAINT }}>Answering <Box component="span" sx={{ color: DIM, fontWeight: 600 }}>{who}</Box>:{" "}
      {cleanText(a.ReadText || a.BodyText || a.Subject || "")}{a.SentAt ? ` · ${fmtDateTime(a.SentAt)}` : ""}</Typography>}
    {r.sent.map((s, i) => <Quote key={i} head={s.msg ? ["Sent by you", s.msg.SourceName, fmtDateTime(s.at)].filter(Boolean).join(" · ")
      : `What was sent${s.at ? ` · ${fmtDateTime(s.at)}` : ""}`}>{cleanText(s.text)}</Quote>)}
    {r.unsent.slice(-1).map((u) => <Quote key={u.ReviewId} head="Not sent - closed without sending">{u.DraftText}</Quote>)}
    {r.close && <Typography data-tq-round-closed="" variant="body2" sx={{ mt: 0.75, color: "#47654a", fontWeight: 600, fontSize: 12.5 }}>
      ✓ {r.close.to === "dropped" ? "Put down" : r.close.note ? "Closed with a note" : "Marked done"} · {fmtDateTime(r.close.at)}
      {r.close.note && <Box component="span" sx={{ display: "block", color: DIM, fontWeight: 400, whiteSpace: "pre-wrap" }}>{r.close.note}</Box>}</Typography>}
  </>);
};

// `rounds` oldest first, the current one last (closeoutRounds.js): every one before it, newest on top
export default function EarlierRounds({ rounds = [] }) {
  const old = rounds.slice(0, -1).reverse();
  if (!old.length) return null;
  return (
    <FoldList mark={{ "data-tq-rounds-before": "" }} title="Earlier rounds" count={old.length}>
      {old.map((r) => { const h = roundHead(r, { when: fmtDateTime, day: fmtDay });
        return <FoldLine key={r.n} mark={{ "data-tq-round-before": r.n }} head={`Round ${r.n} · ${h.head}`} line={cleanText(h.line)}><Round r={r} /></FoldLine>; })}
    </FoldList>);
}
