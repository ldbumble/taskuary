// One statement of "can this reply be sent, and is there a draft to send" for every surface
// that shows a review - Review, the task panel, the assistant's cards (PW-044, PW-046).
// The server decides CanSend (outbound.can_reply) and says why in SendBlock; a draft that
// could not be written carries its reason in DraftError. The UI repeats those facts and never
// invents its own: hiding a button is not authorization, and a missing draft is not an fyi.

const FALLBACK_BLOCK = { github: "GitHub replies are off (GitHub card)" };

export function sendBlockLine(rv) {
  if (!rv || rv.CanSend !== false) return "";
  const why = rv.SendBlock || FALLBACK_BLOCK[String(rv.Channel || "").toLowerCase()] || `replies cannot go out on ${rv.Channel || "this channel"}`;
  return `Cannot send from here: ${why}. The draft stays here to copy or edit.`;
}

export function draftState(rv) {
  const drafted = rv?.HasDraft === 1 || (rv?.HasDraft == null && !!String(rv?.DraftText || "").trim());
  if (drafted) return { state: "drafted", line: "", retry: false };
  if (rv?.DraftError) return { state: "failed", line: `Draft failed: ${rv.DraftError}. Retry drafting or write the answer yourself.`, retry: true };
  return { state: "undrafted", line: "No draft yet — draft it with AI or write the answer.", retry: true };
}
