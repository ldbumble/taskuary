// THE AGENT'S DRAFT IS SAID WHERE THE AGENT IS, AND SENT FROM CLOSE OUT (the owner, 2026-11-02). First: "when we ask the agent to ask the
// sender, we should have the approve right there" - a pop-up over the terminal, a card under the chat. Then, the same day: "then Close out
// has the same thing?? ... in agent we should just say 'agent drafted a message' and take you to the Close out screen". So the agent's pane
// says it in one small notice - who drafted it, to whom - and its one press opens Close out at the draft, the one place it is sent from.
// A draft an agent saved for a person: its own `taskuary --reply` (wrapup.agent_reply: DraftBy "agent:<name>"), or its question to the
// sender (the clarification kind). Taskuary's own drafts and the emails a task owes are Close out's alone, as before.
import { deliveryMeta, deliveryTo } from "./replyDelivery.js";

const isReply = (r) => r?.Kind !== "action" && r?.Kind !== "slot";
export const isAgentDraft = (r) => !!r && r.Status === "pending" && isReply(r) && !!String(r.DraftText || "").trim()
  && (String(r.DraftBy || "").startsWith("agent:") || r.Kind === "clarification");
// ...one per draft as filed: the same review written again by the agent is a new draft
export const draftKey = (r) => `${r.ReviewId}|${String(r.DraftText || "")}`;
// the drafts the agent pane says, in the order the task holds them
export const agentAsks = (reviews = []) => (reviews || []).filter(isAgentDraft);
// where it is said: over a terminal (a CLI agent) in its corner, at the foot of a general agent's conversation - nowhere else
export const askWhere = (mode) => (mode === "live" ? "popup" : mode === "general" ? "chat" : null);
// the notice's words: the agent by the name it wrote under, the person by name ("Erin Blake", not "Erin Blake <erin@...>")
export const draftedBy = (r, agent = "The agent") => (String(r?.DraftBy || "").startsWith("agent:") ? String(r.DraftBy).slice(6) || agent : agent);
export const draftedTo = (r) => deliveryTo(r).split(",").map((a) => a.replace(/\s*<[^>]*>/, "").trim() || a.trim()).filter(Boolean).join(", ");
export const noticeLine = (r, agent) => (r.Kind === "clarification" ? `${draftedBy(r, agent)} drafted a question to ${draftedTo(r)}` : `${draftedBy(r, agent)} drafted a message to ${draftedTo(r)}`);

// ALREADY ANSWERED (the owner, 2026-11-02: "if you responded to it already, the draft should say you responded already"): a reply that went
// to that person after the message the draft answers - sent outside Taskuary (the round's "You answered ... in <mailbox>") or from here.
// `sent`: the current round's replies (closeoutRounds: [{at, text, review | msg}]); `against`: the message the draft was written against
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

// THE REPLY BESIDE THE AGENT (the owner, 2026-11-02: "if the agent makes a reply, bring out the reply (Close out) tab side by side"): the task
// view pairs Agent | Close out on its own for the agent's draft - once the agent has STOPPED RUNNING, where the work area holds two halves,
// and once per draft (`done`: draftKeys); never again for a draft whose pair the owner closed (`shut`: draftKeys). `running`: a live session,
// working or waiting on you, or a run in flight - its notice's press pairs them (a general agent's chat that answered is not running). It
// was "not working", once per draft AND view: a live agent's word flips between working and waiting as it goes, and a re-read that read it
// waiting opened Close out over it (the owner, 2026-11-03: "every 10 seconds it opens the response tab ??? stop opening that until the agent
// stopped running")
export const autoPair = ({ draft, running = false, canPair = false, paired = false, shut = new Set(), done = new Set() } = {}) =>
  !!draft && !running && canPair && !paired && !shut.has(draftKey(draft)) && !done.has(draftKey(draft));
