// THE CHAT PICKER (the owner, 2026-11-06, on Agent channels > Add a channel: "this does not have dropdown? ... it's just the code not the
// same as whatsapp dropdown. why is it not the same code with dropdown above"). One picker for every chat Taskuary can be reached on:
// the Assistant chat (Settings > Phone & chats), a new agent channel there and on a coding task's "Talk to this agent from…". The rows
// come from one server list (chatpick.py, GET /api/chats/{kind}); the decisions are here so node --test holds them without a DOM.
import { recipientId, recipientLabel, recipientOptions } from "./recipientOptions.js";
import { isWaJid } from "./waChats.js";

export const chatUrl = (kind, { agent = false } = {}) => `/api/chats/${encodeURIComponent(kind)}${agent ? "?agent=1" : ""}`;

// what a row is called, and the small id under it (a WhatsApp chat is found by its name and number, never its JID - waChats.js)
export const chatName = (o) => recipientLabel(o);
export const chatId = (o) => (isWaJid(o?.to) ? recipientId(o) : o?.to && chatName(o) !== o.to ? o.to : "");

// the mark beside the name: a chat only the owner is in, a group (with its size when known), a direct chat
export function chatTag(o = {}) {
  if (o.kind === "you") return "only you";
  if (o.kind === "group") return Number(o.people) > 1 ? `group · ${o.people} people` : "group";
  return "direct";
}

// typing filters the whole list, by name, number and hint - the closed picker shows it all too: a handful of chats is the common case
export const filterChats = (options = [], q = "") => recipientOptions(options, q, options.length);

// the chat picked, as a row - one the list does not carry (the bridge restarting) is still shown by its own id
export const pickedChat = (options = [], to = "") => options.find((o) => o.to === to) || (to ? { to, name: recipientLabel({ to }), kind: "" } : null);

// rows a binding cannot take stay listed, greyed, with why - never dropped, or the owner hunts for a chat that is "missing"
export const isBlocked = (o) => !!o?.blocked;

export const WA_TIP = "Tip: make a WhatsApp group with only you in it (e.g. Coding) and pick it here.";
export const chatHint = (kind) => (kind === "whatsapp" ? WA_TIP : "");

// the empty list, in words that say what to do next
export function noChats(kind, { agent = false } = {}) {
  if (!agent) return kind === "whatsapp" ? "no private chat seen yet — message yourself on WhatsApp, then press Look again"
    : "no private chat seen yet — send your bot a direct message, then press Look again";
  return {
    whatsapp: "no chats from WhatsApp yet — is the bridge running? Then press Look again",
    telegram: "no chats seen yet — write in the chat (add your bot to a group first), then press Look again",
    slack: "no channels seen yet — invite the Taskuary app to the channel, then press Look again",
    teams: "no chats seen yet — sign in on the Teams card, then press Look again",
  }[kind] || "no chats seen yet — press Look again";
}
