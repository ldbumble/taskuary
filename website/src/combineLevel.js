// HOW FAR TRIAGE COMBINES a connection's messages into one task (the owner, 2026-10-29): one level per connection type, 1 keep
// separate .. 5 combine. Kept server-side under the type (taskuary/combine.py, /api/combine/{kind}); a mailbox card and the email
// channel its mail arrives on share one level. What a level means is triage's guide; the slider only sets it.
export const MAILBOXES = new Set(["outlook", "gmail", "imap"]);
export const MESSAGING = new Set(["teams", "slack", "telegram", "whatsapp", "discord", "imessage", "mattermost", "rocketchat", "matrix", "google_chat"]);
export const DEFAULTS = { whatsapp: 4, email: 4 };
export const LO = 1, HI = 5, BASE = 3;
export const kindOf = (t) => { const k = String(t || "").toLowerCase(); return MAILBOXES.has(k) ? "email" : k; };
export const defaultLevel = (t) => DEFAULTS[kindOf(t)] ?? BASE;
export const combines = (t) => MAILBOXES.has(String(t || "").toLowerCase()) || MESSAGING.has(String(t || "").toLowerCase());
export const clampLevel = (v) => { const n = Math.round(Number(v)); return n >= LO && n <= HI ? n : null; };
export const MARKS = [
  { value: 1, label: "Keep separate" }, { value: 2, label: "" }, { value: 3, label: "" }, { value: 4, label: "" }, { value: 5, label: "Combine" },
];
// what the level does, said under the slider in the card's own words
export const SAYS = {
  1: "A message joins a task only when it is the same problem.",
  2: "A message joins a task when it is the same problem or very close to it.",
  3: "A message joins a task on the same project or product - two fixes to one app are one task.",
  4: "A message joins a task on the same project, and most work close to its subject.",
  5: "A message joins a task on anything close to its subject, even a different fix or part.",
};
export const ALWAYS = "Unrelated messages - an article shared, small talk, another ask - never join: they stay FYI or become their own task.";
