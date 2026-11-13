// where a reply went, in the owner's words, and what the task does now (TaskPage SentHere, the owner 2026-11-05)
const SENT_ON = { email: "Sent by email", outlook: "Sent by email", gmail: "Sent by email", whatsapp: "Sent on WhatsApp", teams: "Sent on Teams",
  slack: "Sent on Slack", telegram: "Sent on Telegram", sms: "Sent by text" };
export const sentLine = ({ channel, to, closing, kept }) => {
  const c = String(channel || "").toLowerCase(), on = SENT_ON[c] || (to ? `Sent to ${to}` : "Sent");
  return `${on}${closing ? " - closing the task" : kept ? `. The task stays open: ${kept}` : ""}`;
};
// ...and on the sent card (SentCard): its title - the subject as it went (deliverySubject already says "Re:" for a reply; a new email of its
// own is no reply, 2026-11-13) - and the line beside its pressed "✓ Sent"
export const sentTitle = ({ to, subject }) => subject || (to ? `Reply to ${to}` : "Your reply");
export const sentSaid = (p) => sentLine(p).replace(/^Sent ?/, "");
