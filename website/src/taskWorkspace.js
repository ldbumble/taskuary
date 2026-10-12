// A saved close/pause result belongs to the session that just ended - and it is drawn on the Agent work step as that
// session's record, never as a workspace of its own: a "Session closed" card told the run a second time under the step
// that already told it (the owner, 2026-10-12). So the workspace is only ever what is happening now.
export const agentWorkspaceMode = ({ isGeneral, generalStarted, session, wrapping } = {}) => {
  if (wrapping) return "wrapping";
  if (isGeneral) return session?.alive || generalStarted ? "general" : "empty";
  return session?.alive ? "live" : "empty";
};
