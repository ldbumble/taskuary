// where a reply went, in the owner's words, and what the task does now (TaskPage SentHere, the owner 2026-11-05)
import { inDemo } from "./demoWorld.js";
import { label } from "./buttons.js";
import { pressWord } from "./pressResult.js";
const SENT = label("approve", "done");
// ...IN THE DEMO A SEND IS PLAYED (the owner, 2026-11-15; demo.SENT is the server's same sentence): the card settles as it would, and says what did not happen
export const DEMO_SENT = "Sent - in the demo, nothing left this computer";
const BY = { email: "by email", outlook: "by email", gmail: "by email", whatsapp: "on WhatsApp", teams: "on Teams", slack: "on Slack",
  telegram: "on Telegram", sms: "by text" };
// ONE SEND, ONE SENTENCE (walk 12: "Sent to erin@...", "Sent by email" and "Sent · closed by email" for one act): who it went to and how, both
// where both are known - "Sent to Erin Blake by email". `done`: a card whose press is no send says its own word - an invite "Accepted", never
// "Sent by email" (replyDelivery.pressWords)
export const sentLine = ({ channel, to, closing, kept, done = "", demo = inDemo() }) => {
  const how = [to ? `to ${to}` : "", BY[String(channel || "").toLowerCase()] || ""].filter(Boolean).join(" ");
  const on = demo ? DEMO_SENT : done || (how ? `${SENT} ${how}` : SENT);
  return `${on}${closing ? " - closing the task" : kept ? `. The task stays open: ${kept}` : ""}`;
};
// ...and on the sent card (SentCard): its title - the subject as it went (deliverySubject already says "Re:" for a reply; a new email of its
// own is no reply, 2026-11-13) - and the line beside its pressed "✓ Sent"
export const sentTitle = ({ to, subject }) => subject || (to ? `Reply to ${to}` : "Your reply");
// ...and SEND AND CLOSE SAYS SO ON ITS BUTTON, in the one press-result word (pressResult, the owner 2026-11-23: "Sent · closed"): the line beside
// it then says only where it went
export const sentSaid = (p) => sentLine({ ...p, closing: false }).replace(new RegExp(`^${p.done && !p.demo ? p.done : SENT}(?: - | )?`), "");
export const sentMark = (p) => `✓ ${p.closing ? pressWord("send_close") : p.done || SENT}`;
// THE SENT CARD STANDS IN FOR ITS OWN DRAFT, NEVER FOR WHAT COMES AFTER IT (the audit, 2026-11-13: the sender wrote again, the agent drafted
// the new reply, and where its card belonged stood the letter that had gone). AND NEVER BESIDE IT (his live app, 2026-11-23: "on hitting Send a
// duplicate appears quickly then it goes away" - recorded, ~170 ms of two "✓ Sent" letters: the card in its turn turned Sent in place, and the
// press's own SentCard was drawn again under the chat until the task's read came). In a chat with turns the card that was pressed IS where
// the press shows, from the press to its record (cardLook); what the press leaves (TaskPage sentHere) is drawn only on a task with no turns,
// where no turn holds a card.
export const WENT = ["approved", "edited", "sent"];
export const sentStands = (sentHere, inTurns) => (inTurns ? null : sentHere || null);
// WHERE A PRESS STANDS IS THE REVIEW'S, NOT ITS CARD'S (the walk, 2026-11-17: an email's Send read "sending…", then Send and Don't send lit
// again, then nothing, then a Sent card elsewhere - the card kept its press in its own state, and each time the chat drew it again it began over).
// Kept by review id for the page's life: `going` from the press until its answer, `sent` once the server said it went - and every card of that
// review, drawn now or again, reads it. A review the page has read as gone is Sent from its own row alone.
const marks = new Map(), ears = new Set();
export const markOf = (rid) => marks.get(rid) || null;
export const pressMark = (rid, m) => { if (m) marks.set(rid, m); else marks.delete(rid); ears.forEach((f) => f()); };
export const hearMarks = (f) => { ears.add(f); return () => { ears.delete(f); }; };
// ...AND AN ACT'S PRESS THAT LANDED STAYS PRESSED until the review reads decided (walk 9, 2026-11-23: "running…", then Approve lit again for
// 2-7 s, then "✓ Approved"): `landed` reads as going; the press's own busy ending (endPress) takes back only a press still going
export const cardLook = (r, m = markOf(r?.ReviewId)) => (WENT.includes(r?.Status) || m?.state === "sent" ? "sent"
  : m?.state === "going" || (m?.state === "landed" && (r?.Status || "pending") === "pending") ? "going" : "live");
export const endPress = (rid) => { if (markOf(rid)?.state === "going") pressMark(rid, null); };
