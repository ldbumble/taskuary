// THE QUESTION ITSELF, under the pane (B11, the owner, 2026-10-11). While Taskuary holds a Claude question the pane shows
// only a spinner and the heading said "coder is asking you" - no question, no options, and nothing to let the terminal
// have it. Each question with its options as quiet pills; a group goes back whole; held, a way to answer in the pane.
import React, { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { ALERT_BD, ALERT_INK, DIM, FAINT, INK } from "./theme.jsx";
import { asksOf, answerCall, allPicked } from "./agentAsks.js";

export default function AgentAsks({ taskId, session, onAnswered }) {
  const ask = asksOf(session);
  const [picks, setPicks] = useState({}), [busy, setBusy] = useState(""), [err, setErr] = useState("");
  if (!ask) return null;
  const one = ask.questions.length === 1;
  const send = async (p) => {
    setBusy("send"); setErr("");
    try { const [url, body] = answerCall(taskId, ask, p); await api.post(url, body); setPicks({}); onAnswered?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "That did not reach the agent."); }
    finally { setBusy(""); }
  };
  const release = async () => {
    setBusy("release"); setErr("");
    try { await api.post(`/api/tasks/${taskId}/worker/release`); onAnswered?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Taskuary didn't answer."); }
    finally { setBusy(""); }
  };
  // one question: a pill IS the answer. Several: a pill marks that question, and Send takes them all together.
  const pick = (q, c) => one ? send({ [q.request_id]: c }) : setPicks((p) => ({ ...p, [q.request_id]: c }));
  return (
    <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.75, px: 1.1, py: 0.8, flexShrink: 0, border: `1px solid ${ALERT_BD}`, borderRadius: 1.25 }}>
      {ask.questions.map((q, i) => (
        <Box key={q.request_id} sx={{ mt: i ? 0.8 : 0 }}>
          <Typography variant="body2" sx={{ color: INK, fontSize: 12.5, lineHeight: 1.45 }}>
            {!one && <Box component="span" sx={{ color: FAINT, mr: 0.6 }}>{i + 1}.</Box>}{q.text}
          </Typography>
          {q.choices.length > 0 && <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
            {q.choices.map((c) => (
              <Button key={c} size="small" variant={picks[q.request_id] === c ? "contained" : "outlined"} disableElevation disabled={!!busy}
                onClick={() => pick(q, c)} sx={{ fontSize: 11, minHeight: 24, py: 0, px: 1, textTransform: "none" }}>{c}</Button>
            ))}
          </Box>}
        </Box>
      ))}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.6, flexWrap: "wrap" }}>
        {!one && <Button size="small" variant="contained" disableElevation disabled={!!busy || !allPicked(ask, picks)} onClick={() => send(picks)}
          sx={{ fontSize: 11, minHeight: 24, py: 0, px: 1.1 }}>{busy === "send" ? "Sending…" : "Send answers"}</Button>}
        <Typography variant="caption" sx={{ color: DIM, fontSize: 10.5 }}>
          {ask.held ? "Or write your own answer below - it goes straight in."
            /* the hold ran out and its form is in the pane: a pick goes in as its number, other words cannot (B12) */
            : ask.questions.some((q) => q.choices.length) ? "Its form is up in the terminal - pick here or there."
            : ask.kind === "approval_needed" ? "Answer below with one of the options the terminal shows, or pick it there."
            : "Answer below - it goes straight in."}
        </Typography>
        {ask.held && <Button size="small" variant="text" disabled={!!busy} onClick={release} title="Taskuary lets go of the question, and the agent shows its own form in the terminal."
          sx={{ fontSize: 10.5, minHeight: 22, py: 0, px: 0.75, ml: "auto", textTransform: "none" }}>{busy === "release" ? "Letting go…" : "Answer in the terminal instead"}</Button>}
      </Box>
      {err && <Typography variant="caption" sx={{ color: ALERT_INK, display: "block", mt: 0.4, fontSize: 10.5 }}>{err}</Typography>}
    </Box>
  );
}
