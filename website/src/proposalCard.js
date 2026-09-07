// The confirmation card's logic (PW-122..125), kept pure so it can be tested without a browser: the
// card is built from the proposal the server returned, never from a guess about the words; the receipt
// after the click is what the server said happened. The action words themselves are no longer here -
// they are concierge.CHIPS, chosen per item and rendered inside the assistant's own line.
export function proposalOf(data) { return data && data.proposal && data.proposal.id ? data.proposal : null; }

// the box's four facts: what will happen, on what, with which parameters, and the button that does it
export function describe(p) {
  const hidden = new Set(["key", "tid", "rid", "hint", "config", "processing_context"]);   // a revision map, not a fact for the owner
  // A nested value printed as "[object Object]", which is the one thing a confirmation card must never
  // do: the selector IS what the owner is being asked to approve (the owner, 2026-09-07). Flatten it
  // into the fields it actually holds.
  const show = (v) => (v && typeof v === "object" && !Array.isArray(v)
    ? Object.entries(v).filter(([, x]) => x != null && x !== "").map(([k, x]) => `${k.replace(/_/g, " ")}: ${x}`).join(", ")
    : Array.isArray(v) ? v.join(", ") : v);
  const params = Object.entries(p.params || {}).filter(([k, v]) => v != null && v !== "" && !hidden.has(k))
    .map(([k, v]) => [k.replace(/_/g, " "), show(v)]).filter(([, v]) => v !== "" && v != null);
  // a proposed report can be dry-run before the click (PW-195): read-only, nothing filed, sent, activated or started
  return { title: p.label || p.title || p.kind, target: p.summary || "", params, confirm: p.label || "Confirm", cancel: "Cancel", preview: p.kind === "report.create" };
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
