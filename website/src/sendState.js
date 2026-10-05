// One statement of "can this reply be sent, and is there a draft to send" for every surface
// that shows a review - Review, the task panel, the assistant's cards (PW-044, PW-046).
// The server decides CanSend (outbound.can_reply) and says why in SendBlock; a draft that
// could not be written carries its reason in DraftError. The UI repeats those facts and never
// invents its own: hiding a button is not authorization, and a missing draft is not an fyi.

const FALLBACK_BLOCK = { github: "GitHub replies are off (GitHub card)" };

export function replyEnvelope(review) {
  try {
    const env = typeof review?.Deliver === "string" ? JSON.parse(review.Deliver) : review?.Deliver;
    if (env?.kind !== "reply") return null;
    return { ...env, to: Array.isArray(env.to) ? env.to.filter((v) => typeof v === "string") : [],
      cc: Array.isArray(env.cc) ? env.cc.filter((v) => typeof v === "string") : [],
      // what RIDES with the words (verdicts.attach) - a card that does not show these is a card
      // that looks identical whether two workbooks are going or none are
      attachments: Array.isArray(env.attachments) ? env.attachments.filter((f) => f && f.name) : [] };
  } catch { return null; }
}

export function replySendFailure(data) {
  const message = data?.send_error || data?.reply?.send_error;
  const unknown = [data?.delivery, data?.reply?.delivery].some(state => state === "unknown" || state === "sending");
  return message ? { message, unknown } : null;
}

// An uncertain send keeps the exact attempted payload. Checking it is a different
// action from authorizing a new send, and a live claim never offers another one.
export function reviewDeliveryState(review) {
  const parse = (value) => {
    try { return typeof value === "string" ? JSON.parse(value) : value; } catch { return null; }
  };
  const saved = parse(review?.DeliveryEnvelope);
  const envelope = parse(review?.Deliver);
  const state = review?.DeliveryState || envelope?.delivery || "";
  const active = !!review?.DeliveryClaim || state === "sending";
  const frozen = active || state === "unknown";
  return { state, active, frozen, canCheck: state === "unknown" && !active,
    body: frozen ? saved?.body ?? review?.FinalText ?? review?.DraftText ?? "" : null,
    envelope: frozen ? saved?.envelope || envelope || {} : null,
    label: active ? state === "unknown" ? "Checking delivery…" : "Sending…" : "Check delivery",
    line: active ? "Delivery is in progress. The attempted text, recipients and attachments are kept unchanged while the provider responds."
      : state === "unknown" ? "The provider has not confirmed this attempt. Check delivery to look for the original reply. A missing receipt will not send it again. The attempted text, recipients and attachments stay unchanged." : "" };
}

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
