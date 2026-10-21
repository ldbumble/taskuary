// A saved close/pause result belongs to the session that just ended - and it is drawn on the Agent work step as that
// session's record, never as a workspace of its own: a "Session closed" card told the run a second time under the step
// that already told it (the owner, 2026-10-12). So the workspace is only ever what is happening now.
export const agentWorkspaceMode = ({ isGeneral, generalStarted, session, wrapping } = {}) => {
  if (wrapping) return "wrapping";
  if (isGeneral) return session?.alive || generalStarted ? "general" : "empty";
  return session?.alive ? "live" : "empty";
};

// CONTINUE ON THE AGENT'S OWN BAR. A coding agent's Continue reopens its CLI session, which nothing else on the page does. A general
// agent's open card has its composer, and what you type there continues the same conversation - a second door (the owner,
// 2026-09-29) - EXCEPT when its run ended under it (`ended`, the task detail's runEnded: its CLI died part-way through a turn, failed,
// was stopped or cut off): then nothing is running to type into, and Continue picks the saved conversation back up (2026-10-21).
export const RUN_ENDED = ["failed", "stopped", "disconnected"];
export const barContinues = ({ canContinue, isGeneral, ended } = {}) => !!canContinue && (!isGeneral || RUN_ENDED.includes(ended));
