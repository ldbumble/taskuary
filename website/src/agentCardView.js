// An assistant chat and a coding CLI both reach the Timeline as "an agent waiting on you", and the
// card rendered both as a terminal - so a general task's chat appeared in the Assistant tab as a
// black screen of raw tool JSON, with "This is the agent's own screen" under it (TQ-0420). The
// session says which it is (GeneralSession.mode = 'assistant'); funnel.py has always passed it on.
export const agentCardView = (mode) => mode === "assistant" ? "chat" : "terminal";
