// One statement of "can this reply be sent, and is there a draft to send" for every surface
// that shows a review - Review, the task panel, the assistant's cards (PW-044, PW-046).
// The server decides CanSend (outbound.can_reply) and says why in SendBlock; a draft that
// could not be written carries its reason in DraftError. The UI repeats those facts and never
// invents its own: hiding a button is not authorization, and a missing draft is not an fyi.
import { label } from "./buttons.js";

// A SEND THAT NEVER ANSWERS (2026-10-23): the decide POST had no timeout, so behind a stalled server the button read "Sending…"
// for minutes. After a minute the press lets go and the card reads the review again: the server keeps the attempt's DeliveryState,
// so the card shows its own Sending… / Check delivery state - never a second free send and never a sentence of our own.
export const DECIDE_TIMEOUT = 60000;
export const timedOut = (e) => e?.code === "ECONNABORTED" || e?.code === "ETIMEDOUT";

const FALLBACK_BLOCK ={ github: "GitHub replies are off (GitHub card)" };

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
  const fix = data?.send_fix || data?.reply?.send_fix;
  return message ? { message, unknown, ...(fix ? { fix } : {}) } : null;
}

// THE PLACE THAT FIXES A FAILED SEND (outbound.Fixable): from the answer just now, else from the envelope a reload reads - a fix
// that lived only in the answer was gone after a refresh, and the sentence was all that was left
export function sendFix(review, failure) {
  if (failure?.fix?.href) return failure.fix;
  let env = null;
  try { env = typeof review?.Deliver === "string" ? JSON.parse(review.Deliver) : review?.Deliver; } catch { env = null; }
  return (review?.DeliveryState || env?.delivery) === "failed" && env?.fix?.href ? env.fix : null;
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
    label: active ? state === "unknown" ? "Checking delivery…" : "Sending…" : label("approve", "check"),
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
  if (rv?.DraftError) return { state: "failed", line: `Draft failed: ${rv.DraftError}. Press ${label("redraft", "none")} again or write the answer yourself.`, retry: true };
  return { state: "undrafted", line: "No draft yet — draft it with AI or write the answer.", retry: true };
}
