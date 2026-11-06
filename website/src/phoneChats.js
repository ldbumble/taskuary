// PHONE & CHATS (Settings, the owner 2026-11-06: "we need better settings in whatsapp or somewhere to configure what channels can talk to coding
// agents when dev mode is enabled. it's not clear where that is. and then setting for walk through to talk to whatsapp as well"): one page, two
// sections - the owner's private Assistant chat (remote_assistant.py), and in Developer mode the chats bound to coding agents (agentchannels.py).
// The decisions are here, so node --test holds them without a DOM; PhoneChats.jsx draws them.

// the schema group whose knobs (phone_assistant, phone_walk_channel, phone_morning_line...) sit on this page rather than under Configuration
export const PHONE_GROUP = "Assistant on your phone";
export const PHONE_PAGE = "phone";
export const SECTION_TITLE = { assistant: "The Assistant from your phone", agents: "Agent channels" };
// Agent channels are a developer's: with Developer mode off the section is not drawn at all - no heading, no "turn it on" teaser
export const phoneSections = ({ devMode = false } = {}) => ["assistant", ...(devMode ? ["agents"] : [])];

export const CHANNEL_NAME = { whatsapp: "WhatsApp", telegram: "Telegram", slack: "Slack", teams: "Teams" };
export const ASSISTANT_LINE = "Walk through your tasks, answer and approve from your phone. It only speaks when you write first.";
// how a chat that is not set yet gets set - the chat is offered once Taskuary has SEEN it, so the first step is always the owner's message
export const SETUP_STEPS = {
  whatsapp: ["On your phone, open WhatsApp and send yourself a message (the “Message yourself” chat).", "Press Look again here.",
    "Pick that chat in the box - it becomes your Assistant chat."],
  telegram: ["In Telegram, send your Taskuary bot a direct message.", "Press Look again here.",
    "Pick that chat in the box - it becomes your Assistant chat."],
};

// One channel's row, in words: {state, line}. `r` is a doorway_state row; `handoff` the live hand-over ({channel, chat}) or null.
export function doorwayStatus(r, handoff = null) {
  const name = CHANNEL_NAME[r?.channel] || r?.channel || "This channel";
  if (!r?.live) return { state: "off", line: `${name} is not switched on yet.` };
  if (!r.chat) return { state: "unset", line: "Not set up - no chat is picked yet." };
  if (handoff && handoff.channel === r.channel && String(handoff.chat || "") === String(r.chat)) return { state: "walking", line: "On - walking you through your tasks there now." };
  return r.listens === "always" ? { state: "on", line: "On - it answers whenever you write to it." }
    : { state: "walk", line: "On during a walk - quiet until you hand one over, and after it comes back." };
}

// the Hand the walk button is offered where a walk can actually go: switched on, a chat picked, nothing already walking there
export const canHandOver = (r, handoff = null) => ["on", "walk"].includes(doorwayStatus(r, handoff).state);

// One agent-channel binding, as the page reads it: what it talks to, where, who is in it.
export function bindingRow(c = {}) {
  const mates = (c.members || []).filter((m) => m.role === "teammate").map((m) => m.name);
  return {
    id: c.id, channel: c.label || CHANNEL_NAME[c.kind] || c.kind, chat: c.chat || "",
    what: c.task ? `${c.ref || `task ${c.task}`}'s agent` : "the coding agents",
    href: c.task ? `#task=${c.task}` : "",
    repo: c.repoName || c.repo || (c.task ? "" : "any repository"),
    people: ["you", ...mates].join(", "),
  };
}

export const RULES = ["Only the people listed on a channel are heard; everyone else in the chat is ignored.",
  "Teammates can talk to the agent, but they can't approve, land, push or send anything - that stays yours.",
  "The agent's replies go back to the same chat."];
