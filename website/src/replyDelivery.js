// THE ENVELOPE ON A DRAFT: who it goes to, who is copied, what rides with it.
//
// Review has always read these out of the review's `Deliver` blob. The task page's Reply card now
// shows the same three facts above the same draft, and two readings of one JSON column is how the
// two surfaces start disagreeing about what a reply looks like - so they read it from here.
export const deliveryMeta = (review) => {
  try { return JSON.parse(review?.Deliver || "null") || {}; } catch { return {}; }
};
// THE NAME RIDES WITH ITS ADDRESS: the envelope keeps bare addresses (what the send needs), so a redraft - which pins one - turned
// "Erin Blake <erin@…>" on the To line into the address alone. The sender's name is on the review: looked up by address.
const named = (a, review) => {
  const e = String(a || "").trim(), { FromName: n, FromEmail: em } = review || {};
  return n && em && !e.includes("<") && e.toLowerCase() === String(em).trim().toLowerCase() ? `${n} <${e}>` : e;
};
// ...and back to addresses for the To box and its save (ui.ToRow): "Erin Blake <erin@…>, gail@…" -> ["erin@…", "gail@…"]
export const bareAddresses = (to) => String(to || "").replace(/[^,<]*<([^>]+)>/g, "$1").split(",").map((a) => a.trim()).filter(Boolean);
export const deliveryTo = (review) => {
  const raw = deliveryMeta(review).to;
  const to = (Array.isArray(raw) ? raw : [raw]).map((a) => named(a, review)).filter(Boolean).join(", ");
  if (to) return to;                                    // replies to inbound messages carry no Deliver
  if (review?.FromName && review?.FromEmail) return `${review.FromName} <${review.FromEmail}>`;
  return review?.FromName || review?.FromEmail || review?.ConversationId || "this conversation";
};
export const deliveryFiles = (review) => {
  const raw = deliveryMeta(review).attachments;
  return Array.isArray(raw) ? raw.filter((f) => f && f.name) : [];
};
export const deliveryCc = (review) => {
  const raw = deliveryMeta(review).cc;
  return Array.isArray(raw) ? raw.filter(Boolean) : [];
};
// A chat has members, not recipients: name the room so "TO Sarah" does not read as a DM when it
// is a channel everyone can see.
const ROOMS = ["whatsapp", "teams", "slack", "telegram", "discord", "imessage"];
export const replyContext = (review) => {
  const channel = String(review?.Channel || "").toLowerCase();
  if (!ROOMS.includes(channel)) return deliveryTo(review);
  return `${deliveryTo(review)} in ${review.SourceName || (channel === "whatsapp" ? "the chat" : channel)}`;
};
