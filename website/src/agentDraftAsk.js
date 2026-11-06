// AN AGENT'S DRAFT, in the one chat (the owner, 2026-11-06): its card is drawn under the turn that wrote it, Send under it - no notice that
// points elsewhere, for there is nowhere else. What is left here is which drafts are the page's, and whether the owner already answered.
import { deliveryMeta, deliveryTo } from "./replyDelivery.js";

// AN EARLIER SESSION'S DRAFT IS NOT THE REPLY (the owner, 2026-11-03: "when you continue on general agent it shows the prior reply on bottom that
// the agent generated. Don't show that reply if it was based off another general session not the latest one"). A draft keeps the session that
// wrote it (DraftSid; "owner" once the owner edited it); while another session is live (`sid`) its pending draft is not the page's - the server
// holds it the same way (wrapup.stale_draft) and this keeps a read from before the hold from drawing it, its notice or its Send
export const earlierSession = (r, sid) => !!sid && r?.Status === "pending" && String(r.DraftBy || "").startsWith("agent:")
  && !!r.DraftSid && r.DraftSid !== "owner" && r.DraftSid !== sid;
export const latestDrafts = (reviews = [], sid = "") => (reviews || []).filter((r) => !earlierSession(r, sid));
// the person by name ("Erin Blake", not "Erin Blake <erin@...>")
export const draftedTo = (r) => deliveryTo(r).split(",").map((a) => a.replace(/\s*<[^>]*>/, "").trim() || a.trim()).filter(Boolean).join(", ");

// ALREADY ANSWERED (the owner, 2026-11-02: "if you responded to it already, the draft should say you responded already"): a reply that went
// to that person after the message the draft answers - sent outside Taskuary (the round's "You answered ... in <mailbox>") or from here.
// `sent`: the current round's replies (replyRounds: [{at, text, review | msg}]); `against`: the message the draft was written against
// (its MessageId); `ms` the app's clock. -> {who, at, words} of the newest such reply, or null.
const emails = (v) => (JSON.stringify(v ?? "").toLowerCase().match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]+/g) || []);
const toOf = (s) => emails(s.msg ? s.msg.RecipientsJson : [deliveryMeta(s.review).to, s.review?.FromEmail]);
export function alreadyAnswered({ draft, sent = [], against = null, ms = (s) => Date.parse(s) || 0 } = {}) {
  if (!draft) return null;
  const t = (s) => ms(s) || 0, after = against ? t(against.SentAt) || t(against.CreatedAt) : 0;
  const person = emails([deliveryMeta(draft).to, draft.FromEmail, against?.FromEmail])[0] || "";
  // ...to that person: a reply that names its recipients and leaves them out went to someone else on the thread
  const hit = (sent || []).filter((s) => s.review?.ReviewId !== draft.ReviewId && t(s.at) > after && String(s.text || "").trim()
    && (!person || !toOf(s).length || toOf(s).includes(person))).at(-1);
  if (!hit) return null;
  const flat = String(hit.text).replace(/\s+/g, " ").trim(), words = flat.length > 60 ? `${flat.slice(0, 60).replace(/\s+\S*$/, "")}...` : flat;
  return { who: draftedTo(draft) || against?.FromName || "them", at: hit.at, words };
}
export const answeredLine = (a, when = (s) => s) => (a ? `You already answered ${a.who} at ${when(a.at)}: "${a.words}"` : "");
