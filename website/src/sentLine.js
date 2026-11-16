// where a reply went, in the owner's words, and what the task does now (TaskPage SentHere, the owner 2026-11-05)
import { inDemo } from "./demoWorld.js";
import { label } from "./buttons.js";
const SENT = label("approve", "done");
// ...IN THE DEMO A SEND IS PLAYED (the owner, 2026-11-15; demo.SENT is the server's same sentence): the card settles as it would, and says what did not happen
export const DEMO_SENT = "Sent - in the demo, nothing left this computer";
const SENT_ON = { email: "Sent by email", outlook: "Sent by email", gmail: "Sent by email", whatsapp: "Sent on WhatsApp", teams: "Sent on Teams",
  slack: "Sent on Slack", telegram: "Sent on Telegram", sms: "Sent by text" };
// ...`done`: a card whose press is no send says its own word - an invite "Accepted", never "Sent by email" (replyDelivery.pressWords)
export const sentLine = ({ channel, to, closing, kept, done = "", demo = inDemo() }) => {
  const c = String(channel || "").toLowerCase(), on = demo ? DEMO_SENT : done || SENT_ON[c] || (to ? `Sent to ${to}` : SENT);
  return `${on}${closing ? " - closing the task" : kept ? `. The task stays open: ${kept}` : ""}`;
};
// ...and on the sent card (SentCard): its title - the subject as it went (deliverySubject already says "Re:" for a reply; a new email of its
// own is no reply, 2026-11-13) - and the line beside its pressed "✓ Sent"
export const sentTitle = ({ to, subject }) => subject || (to ? `Reply to ${to}` : "Your reply");
export const sentSaid = (p) => sentLine(p).replace(new RegExp(`^${p.done && !p.demo ? p.done : SENT}(?: - | )?`), "");
export const sentMark = (p) => `✓ ${p.done || SENT}`;
// THE SENT CARD STANDS IN FOR ITS OWN DRAFT, NEVER FOR WHAT COMES AFTER IT (the audit, 2026-11-13, recorded on the real CLI: he pressed Send
// and stayed on the task, the sender wrote again, the agent drafted the new reply - and where its card belonged stood the letter that had
// gone, "✓ Sent", no Send anywhere while the agent said "it waits for your Send"; a reload showed it). What the press leaves (TaskPage
// sentHere) holds the draft's place only until the task's own read has that reply as gone: from then it is its card in the turn that drafted
// it (turnCards), and the block under the chat is whatever waits now. A task with no turns has no such card, and keeps it where it stood.
export const WENT = ["approved", "edited", "sent"];
export const sentStands = (sentHere, reviews, inTurns) => (sentHere && !(inTurns && (reviews || []).some((r) => r.ReviewId === sentHere.id && WENT.includes(r.Status))) ? sentHere : null);
