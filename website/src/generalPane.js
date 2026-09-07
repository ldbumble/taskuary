// Which of the three bodies the assistant workspace shows - and, the whole point of it, that the
// CHAT is not one of the things a live session gates.
//
// A general task begins with NO session: since 1c0169d the pane only READS state on mount, because
// looking at a task is not dispatching it. The body still asked `session ? <thread> : null`, so a
// task created from the Board opened as an empty box - no welcome, no composer, and the question
// the owner typed never asked, because the thread that asks it (newTask.js's ask tag) was never
// rendered at all (TQ-0420, 2026-09-07). Sending is what starts a session, server-side
// (/assistant/stream), so the chat needs none to be usable.
export const paneFor = (view, hasSession) => view === "numbers" ? "numbers"
  : view === "terminal" ? (hasSession ? "terminal" : "terminal-empty") : "chat";
