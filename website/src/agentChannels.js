// AGENT CHANNELS (agentchannels.py): a WhatsApp, Telegram, Slack or Teams chat bound to one coding agent, its teammates named by the owner.
// The words the server types into the agent for a teammate carry "[Gail Moreno (teammate) on Slack - ...]" - the chat row reads it back
// so the line is drawn as theirs, never as "You".
const TEAMMATE = /\[([^[\]()]{1,80}) \(teammate\) on (WhatsApp|Telegram|Slack|Teams) - [^\]]*\]\s*/;

// {who, via, text} for a typed line that is a teammate's, else null
export function teammateLine(text) {
  const m = TEAMMATE.exec(String(text || ""));
  if (!m) return null;
  const rest = String(text).slice(m.index + m[0].length);
  // ...the batch's own "(2) ..." after it is the next note, not this one's words
  return { who: m[1].trim(), via: m[2], text: rest.split(/\s\(\d+\)\s/)[0].replace(/\s*\(\d+ more notes? waits?.*$/, "").trim() };
}

// where the person's id is found, in the words of each channel
export const ID_HINT = {
  whatsapp: "their phone number, with the country code",
  telegram: "their numeric Telegram id",
  slack: "their Slack member ID (U…)",
  teams: "their work email",
};

// the members as the server takes them: the owner first (their id only where the channel cannot say a line is theirs), then teammates
export function membersOf({ owner = "", ownerId = "", teammates = [] } = {}) {
  return [{ name: owner, id: String(ownerId || "").trim(), role: "owner" },
    ...teammates.filter((t) => String(t.name || "").trim() && String(t.id || "").trim())
      .map((t) => ({ name: t.name.trim(), id: t.id.trim(), role: "teammate" }))];
}

// "Slack · C0LEDGER · with Gail Moreno, Ray Colton"
export function channelLine(c) {
  const mates = (c?.members || []).filter((m) => m.role === "teammate").map((m) => m.name);
  return [c?.label || c?.kind, c?.chat, mates.length ? `with ${mates.join(", ")}` : "just you"].filter(Boolean).join(" · ");
}
