// CLOSING AN AGENT'S WORK - one road, wherever it is pressed (the owner, 2026-10-15: "a close agent button ... should do the
// same exact thing and save down the agent's last work ... make sure it uses same code not new code"). The task page's Mark
// done on a live session and the Wall's Close agent both run this: the session's write-up is saved with the task (no reply
// drafted - a close dismisses drafts), then the task closes through the shared task.complete operation (PW-215). A write-up
// that fails still closes. And both show the same card while it works.
import React from "react";
import { Box, CircularProgress, LinearProgress, Typography } from "@mui/material";
import { runOperation } from "./taskOps.js";
import { DIM, INK, card } from "./theme.jsx";

// what the session did, saved with the task before it closes
export const writeUpSession = (api, tid) => api.post(`/api/tasks/${tid}/wrap`, { close: false, no_reply: true }).then((r) => r.data).catch(() => null);
// the close itself: the one completion road every surface takes
export const completeTask = (api, tid, note) => runOperation(api, "task.complete", tid, note ? { note } : {});
// ...both, in order, as ONE job the server owns (writeup.py, 2026-10-20): answered once the session is harvested, the write-up
// and then the close run behind the press - a close pressed anywhere meanwhile waits for it. True when the job started.
export const writeUpThenClose = (api, tid) => api.post(`/api/tasks/${tid}/wrap`, { close: false, no_reply: true, background: true, then_close: true })
  .then(() => true).catch(() => false);
// the Wall's Close agent and the task page's Mark done on a live session (TaskPage.stopAndFinish): the job, or - when it cannot
// start (nothing on screen to write up) - the close alone, as a write-up that fails always did
// ...and says which: {writing: true} while the job writes up and closes, null once the task closed here
export const closeAgentWork = async (api, tid) => {
  if (await writeUpThenClose(api, tid)) return { writing: true };
  await completeTask(api, tid); return null;
};

const SAYS = {
  stop: ["Stopping this session…", "The session is ending. The task and reply are not changed."],
  done: ["Writing up this session, then marking it done…", "Reading the transcript and saving what this session did. The task closes when that is filed."],
  wrap: ["Writing up this session…", "Reading the transcript and writing up what this session did. The task and reply remain separate — this takes a few seconds."],
};

export const ClosingCard = ({ mode = "done", sx }) => {
  const [head, line] = SAYS[mode] || SAYS.wrap;
  return (
    <Box data-tq-closing={mode} sx={{ ...card, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", ...sx }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <CircularProgress size={15} />
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }}>{head}</Typography>
      </Box>
      <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>{line}</Typography>
      <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />
    </Box>
  );
};

// over a pane that is closing: the card, and nothing under it can be typed into or pressed until it is done
export const ClosingCover = ({ mode = "done" }) => (
  <Box data-tq-closing-cover="" sx={{ position: "absolute", inset: 0, zIndex: 5, display: "flex", alignItems: "center", justifyContent: "center",
    p: 2, bgcolor: "rgba(250,248,245,.82)", backdropFilter: "blur(1px)", cursor: "progress" }}>
    <ClosingCard mode={mode} sx={{ maxWidth: 420, width: "100%" }} />
  </Box>
);
