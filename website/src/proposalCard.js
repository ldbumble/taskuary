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

export function afterExecute(p, res) {
  const label = p.label || p.title || p.kind;
  if (res?.status === "done" && res.duplicate) return { receipt: `Already done - ${label}.`, settle: false, status: "done" };
  if (res?.status === "done") return { receipt: `Done - ${label}.`, settle: !!p.settles, status: "done" };
  if (res?.status === "stale") return { receipt: `Not done - ${res.error || "the proposal is out of date"}. Say it again if you still want it.`, settle: false, status: "stale" };
  return { receipt: `Not done - ${res?.error || "it failed"}. Nothing moved.`, settle: false, status: res?.status || "error" };
}

export function afterCancel(p) { return { receipt: `Cancelled - nothing changed; ${p.ref || "it"} is where it was.`, status: "cancelled" }; }
