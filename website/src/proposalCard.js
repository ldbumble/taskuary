// The confirmation card's logic (PW-122..125), kept pure so it can be tested without a browser: the
// bottom suggestions are ordinary text; the card is built from the proposal the server returned, never
// from a guess about the words; the receipt after the click is what the server said happened.
export const SUGGESTIONS = ["Next", "Done", "Create task", "Create agent", "Reply"];

export function proposalOf(data) { return data && data.proposal && data.proposal.id ? data.proposal : null; }

// the box's four facts: what will happen, on what, with which parameters, and the button that does it
export function describe(p) {
  const hidden = new Set(["key", "tid", "rid", "hint"]);
  const params = Object.entries(p.params || {}).filter(([k, v]) => v != null && v !== "" && !hidden.has(k));
  return { title: p.label || p.title || p.kind, target: p.summary || "", params, confirm: p.label || "Confirm", cancel: "Cancel" };
}

// a hand-off to an agent (PW-135): when it STARTS, the walk moves on once and the delegated task stays in
// Unread as Working - nothing is settled; a repository still to choose is a decision the card asks for
export const isHandoff = (p) => p.kind === "task.create_from_message" && ["coding", "general"].includes(p.params?.kind);

export function afterExecute(p, res) {
  const label = p.label || p.title || p.kind;
  if (res?.status === "done" && res.duplicate) return { receipt: `Already done - ${label}.`, settle: false, status: "done" };
  if (res?.status === "done") return { receipt: `Done - ${label}.`, settle: !!p.settles, status: "done", handoff: isHandoff(p) && !!(res.outcome?.started || res.outcome?.chat) };
  if (res?.status === "error" && res.outcome?.dispatch === "needs_repo")
    return { receipt: `Not started - ${res.error || "it needs a repository first"}. Pick one on the card and confirm again.`, settle: false, status: "error",
             repo: { taskId: res.outcome.taskId, agent: res.outcome.agent } };
  if (res?.status === "stale") return { receipt: `Not done - ${res.error || "the proposal is out of date"}. Say it again if you still want it.`, settle: false, status: "stale" };
  return { receipt: `Not done - ${res?.error || "it failed"}. Nothing moved.`, settle: false, status: res?.status || "error" };
}

export function afterCancel(p) { return { receipt: `Cancelled - nothing changed; ${p.ref || "it"} is where it was.`, status: "cancelled" }; }
