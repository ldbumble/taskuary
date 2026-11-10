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

// WHAT A PERMISSION CARD SAYS (permissions.py `pending`): a command is led by the agent's own words for the step (`about`), else by what the
// shell gate holds in it (`what`), with why it waits - and the command itself, whole, under a fold. It was 'It wants to run "git add ...
// | tail -1; gi"': cut mid-word, the held step past the cut (the agent walk, 2026-11-09). A command nobody said anything about is shown
// open; what is no command is the server's own line
const upFirst = (x) => (x ? x[0].toUpperCase() + x.slice(1) : x);
export function permissionLead(p) {
  const about = String(p?.about || "").trim(), what = String(p?.what || "").trim(), command = String(p?.command || "");
  if (!command) return { lead: `It ${String(p?.line || "asks to go on").replace(/\x60([^\x60]+)\x60/g, "\u201c$1\u201d")}.`, why: "", command, open: false };
  return { lead: upFirst(about || what) || "Run a command in its shell", command, open: !(about || what),
    why: what ? `Held before it ran - ${p?.why || "it leaves this computer"}${about ? `: it would ${what}` : ""}.` : "" };
}

// "Slack · C0LEDGER · with Gail Moreno, Ray Colton"
export function channelLine(c) {
  const mates = (c?.members || []).filter((m) => m.role === "teammate").map((m) => m.name);
  return [c?.label || c?.kind, c?.chat, mates.length ? `with ${mates.join(", ")}` : "just you"].filter(Boolean).join(" · ");
}
