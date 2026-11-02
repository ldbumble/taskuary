// THE AGENT'S DRAFT IS APPROVED WHERE THE AGENT IS (the owner, 2026-11-02: "when we ask the agent to ask the sender, we should have the
// approve right there instead of having to go to the Close out tab to confirm sending a clarification. Keep as much space as possible for
// the CLI tool, so for a CLI agent it should be a POP-UP. A general agent should show it where we ask questions, in the bottom space").
// A draft an agent saved for a person (`taskuary --reply`, wrapup.agent_reply: DraftBy "agent:<name>"; or its question to the sender,
// the clarification kind) is drawn over the terminal's corner, or at the foot of the general agent's conversation, with the very card
// Close out draws for it (ReviewDecision) - the same Send, the same rules. Close out keeps it too; a send from either clears both.
import { useEffect, useState } from "react";

const isReply = (r) => r?.Kind !== "action" && r?.Kind !== "slot";
// the agent wrote it: its own --reply, or the question it asked the sender (server clarify_with_sender)
export const isAgentDraft = (r) => !!r && r.Status === "pending" && isReply(r) && !!String(r.DraftText || "").trim()
  && (String(r.DraftBy || "").startsWith("agent:") || r.Kind === "clarification");
// ...one per draft as filed: an agent that saves a new letter on the same review brings it back up after a Later
export const draftKey = (r) => `${r.ReviewId}|${String(r.DraftText || "")}`;
// the drafts the agent pane asks about, in the order the task holds them, less those put off on this visit
export const agentAsks = (reviews = [], off = new Set()) => (reviews || []).filter((r) => isAgentDraft(r) && !off.has(draftKey(r)));
// where it is asked: over a terminal (a CLI agent) as a pop-up, in a general agent's conversation as its card - nowhere else
export const askWhere = (mode) => (mode === "live" ? "popup" : mode === "general" ? "chat" : null);

// LATER PUTS IT OFF FOR THIS VISIT: the draft stays in Close out, and opening the task again brings the pop-up back. `all` is the chat's:
// the card at the conversation's foot covers nothing, so it has no Later
export function useAgentAsks(taskId, reviews) {
  const [off, setOff] = useState(() => new Set());
  useEffect(() => { setOff(new Set()); }, [taskId]);
  return { all: agentAsks(reviews), asks: agentAsks(reviews, off), later: (r) => setOff((s) => new Set([...s, draftKey(r)])) };
}
