// A saved close/pause result belongs to the session that just ended. If another session is
// already alive, its terminal is the current workspace even when the old transient result card
// has not yet been dismissed or cleared by React state.
export const agentWorkspaceMode = ({ isGeneral, session, wrapping, wrapped } = {}) => {
  if (isGeneral) return "general";
  if (wrapping && !wrapped) return "wrapping";
  if (session?.alive) return "live";
  if (wrapped) return "wrapped";
  return "empty";
};
