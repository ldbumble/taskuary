// One reading of a dispatch answer for every surface that starts a worker (PW-209/212).
//
// The server says four things: dispatch (session | assistant | needs_repo), started (a worker
// session was created for THIS request), existing (a live session was reused - nothing new
// started) and, for a coding session, accepted (the prompt was actually submitted, not merely
// typed into a booting TUI). A repository decision is never a start; a reused session is never
// "it started". Older servers without the flags: a session payload is a start.
export function outcomeOf(data) {
  const d = data || {};
  const who = d.agent || (d.dispatch === "assistant" ? "the assistant" : "the agent");
  const ref = d.ref || "";
  if (d.dispatch === "needs_repo")
    return { state: "needs_repo", text: `Which repository? ${d.reason || "pick one before the agent starts"}`, taskId: d.taskId, agent: d.agent };
  if (d.existing || (d.started === false && d.dispatch !== "needs_repo"))
    return { state: "existing", text: `${who} is already on it${ref ? ` - ${ref}` : ""}; nothing new was started`, taskId: d.taskId };
  if (d.started === true || d.session || d.dispatch === "assistant" || d.dispatch === "session") {
    const accepted = d.accepted;
    const text = accepted === false
      ? `${who} is opening on ${ref || "it"} - the ask is still being typed in`
      : `${who} is on it in a live session${ref ? ` - ${ref}` : ""}`;
    return { state: "started", text, taskId: d.taskId, accepted };
  }
  return { state: "unknown", text: "no start was reported", taskId: d.taskId };
}
