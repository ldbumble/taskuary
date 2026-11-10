import React, { useRef, useState } from "react";
import { Box, Button, Popover, Typography } from "@mui/material";
import api from "./api.js";
import { usePromptImages } from "./promptImages.jsx";
import { PromptBox } from "./AgentSummary.jsx";
import { label } from "./buttons.js";

// CONTINUE SESSION (A19, the owner, 2026-09-25: "should work for both coding and non coding agents? Maybe add a new
// prompt inside that continue session"). The agent picks up where it left off - its own CLI session, or its saved
// conversation - and what you type here is the first thing it hears. Leave it empty to continue as is.
// IN LINE, LIKE NEW (the owner, 2026-09-30: "shouldn't this show up in line of the assistant ... same as the new box ... with
// voice note/images"): on the canvas it is a card in the conversation, with the mic and pictures; elsewhere still a popover.
// `onPress` fires AT THE PRESS, before the server answers, so the rail can ring the row's icon at once;
// `onFail(error)` if it could not continue
// `initial`: words the box opens holding - the owner's notes when the Assistant lit Continue with them ("rerun it with these notes: ...")
// `asked`: the question the run was still asking when it ended (workerstate.left_asking) - the box is its answer, and says so
export default function ContinueBox({ task, anchor, onClose, onDone, inline = false, taskRef = "", onPress, onFail, initial = "", asked = "", signin = "" }) {
  const [note, setText] = useState(initial || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pics = usePromptImages();
  const word = label("continue");
  // ...once: a double press (or Ctrl+Enter then a click) posted /continue-work twice before `busy` was drawn (the agents walk, 2026-10-26)
  const flight = useRef(false);
  const go = async () => {
    if (flight.current) return;
    flight.current = true;
    setBusy(true); setErr("");
    onPress?.();
    try {
      const { data } = await api.post(`/api/tasks/${task.TaskId}/continue-work`, { note: note.trim() || null, images: pics.paths });
      onClose?.(); onDone?.(data, note.trim() || (pics.imgs.length ? "(images)" : ""));
    } catch (e) { const msg = e?.response?.data?.detail || e?.message || "it could not continue"; setErr(msg); onFail?.(msg); }
    finally { flight.current = false; setBusy(false); }
  };
  const body = (
    <Box sx={{ p: 1.5, display: "grid", gap: 1, ...(inline ? {} : { width: 320 }) }}>
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: "var(--tq-link, #41525f)" }}>{word}{taskRef ? ` · ${taskRef}` : ""}</Typography>
      {/* a run that ended WAITING ON A SIGN-IN (2026-11-03): no answer in words - Continue opens its browser again, and the sign-in is asked there */}
      {!asked && signin && <Typography data-tq-left-signin={signin} sx={{ fontSize: 12.5, color: "var(--tq-link, #2b3a45)", overflowWrap: "anywhere" }}>
        {`Sign in to ${signin} to continue. Continue opens the agent browser on that page again - sign in there, or fill it in securely from the link it shows.`}</Typography>}
      {asked && <Typography data-tq-left-asking sx={{ fontSize: 12.5, color: "var(--tq-link, #2b3a45)", overflowWrap: "anywhere" }}>{asked}</Typography>}
      {/* THE ONE BOX (AgentSummary.PromptBox, the owner 2026-11-06: "it should be shared"): paperclip, pictures, words, mic, and its Send is
          Continue - empty is allowed, the agent carries on as it was */}
      <PromptBox text={note} setText={setText} pics={pics} busy={busy} onSend={go} emptyOk autoFocus label={word} title={word}
        placeholder={asked ? "Your answer - it goes to the agent as it picks up" : "Anything to tell it as it picks up? (optional)"} />
      <Box sx={{ display: "flex", gap: 0.75 }}>
        <Button size="small" disabled={busy} onClick={onClose}>Cancel</Button>
      </Box>
      {err && <Typography sx={{ fontSize: 11.5, color: "var(--tq-danger, #7a2f3c)" }}>{err}</Typography>}
    </Box>
  );
  if (inline) return <Box data-tq-continue-card sx={{ border: "1px solid var(--tq-border, #d5d0c7)", borderRadius: "12px", bgcolor: "var(--tq-panel, #fffdfb)" }}>{body}</Box>;
  return <Popover open={!!anchor} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>{body}</Popover>;
}
