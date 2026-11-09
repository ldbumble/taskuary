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
// AN EMAIL WITH NOBODY TO GO TO (the owner, 2026-11-09: "To: <a bank's name>" - "it needs to be email address"): an envelope whose To
// holds no address - empty, or a name an older draft carried - asks for one; a reply to an inbound message carries no To, and is not it
export const needsAddress = (review) => {
  const raw = deliveryMeta(review).to;
  return raw !== undefined && !(Array.isArray(raw) ? raw : [raw]).some((a) => String(a || "").includes("@"));
};
export const deliveryFiles = (review) => {
  const raw = deliveryMeta(review).attachments;
  return Array.isArray(raw) ? raw.filter((f) => f && f.name) : [];
};
export const deliveryCc = (review) => {
  const raw = deliveryMeta(review).cc;
  return Array.isArray(raw) ? raw.filter(Boolean) : [];
};
// ...BCC the same way, and the SUBJECT the email card shows (the owner, 2026-11-08: one email card): the envelope's, else "Re:" the mail answered
export const deliveryBcc = (review) => {
  const raw = deliveryMeta(review).bcc;
  return Array.isArray(raw) ? raw.filter(Boolean) : [];
};
export const deliverySubject = (review) => {
  const own = String(deliveryMeta(review).subject || "").trim(), theirs = String(review?.Subject || "").trim();
  return own || (theirs ? (/^re:/i.test(theirs) ? theirs : `Re: ${theirs}`) : "");
};
// A chat has members, not recipients: name the room so "TO Sarah" does not read as a DM when it
// is a channel everyone can see.
const ROOMS = ["whatsapp", "teams", "slack", "telegram", "discord", "imessage"];
// ...and with no room named, the app by its own name - "Erin Blake in teams" read as a typo (the scenario run, 2026-11-06)
const APP = { teams: "Teams", slack: "Slack", telegram: "Telegram", discord: "Discord", imessage: "iMessage" };
export const replyContext = (review) => {
  const channel = String(review?.Channel || "").toLowerCase();
  if (!ROOMS.includes(channel)) return deliveryTo(review);
  // ...by the person's name: a chat's address is a phone or chat id ("Ray Colton <15550000332@s.whatsapp.net>"), nothing a person reads;
  // and a one-to-one chat is named after them, so it is no room to name ("Ray Colton in Ray Colton", the stress run 2026-11-05)
  const who = review?.FromName || deliveryTo(review), room = review?.SourceName;
  if (room && room === review?.FromName) return who;
  return `${who} in ${room || (channel === "whatsapp" ? "the chat" : APP[channel])}`;
};
