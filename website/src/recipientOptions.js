import { isWaJid, waLabel, waMatches } from "./waChats.js";

export const RECENT_RECIPIENTS = 5;

// The API supplies newest-first options. Keep the closed/fresh picker short like a chat
// sidebar, then search the complete address book as soon as the owner types.
// A WhatsApp chat is matched by its name and phone number only - its JID is never what finds it (waChats.js).
export function recipientOptions(options, query, recentLimit = RECENT_RECIPIENTS) {
  const q = String(query || "").trim();
  const words = q.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return options.slice(0, recentLimit);
  return options.filter((option) => {
    if (isWaJid(option.to)) return waMatches(q, option.to, option.name);
    const haystack = `${option.name || ""} ${option.to || ""} ${option.hint || ""}`.toLocaleLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

export function recipientLabel(option) {
  if (typeof option === "string") return option;
  return isWaJid(option?.to) ? waLabel(option.to, option.name) : option?.name || option?.to || "";
}

// the small muted line under a WhatsApp chat's name: its id, shown - never searched
export const recipientId = (option) => (isWaJid(option?.to) && recipientLabel(option) !== option.to ? option.to : "");

export function validEmail(value) {
  return /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(String(value || "").trim());
}

export function normalizeEmails(values) {
  const out = [];
  const seen = new Set();
  for (const value of values || []) {
    const raw = typeof value === "string" ? value : value?.to;
    for (const part of String(raw || "").split(/[,;]+/)) {
      const email = part.trim();
      const key = email.toLocaleLowerCase();
      if (validEmail(email) && !seen.has(key)) { seen.add(key); out.push(email); }
    }
  }
  return out;
}

export function emailRecipientOptions(options, query) {
  const q = String(query || "").trim();
  const matches = recipientOptions(options, q);
  if (!validEmail(q) || matches.some((option) => String(option.to || "").toLocaleLowerCase() === q.toLocaleLowerCase())) {
    return matches;
  }
  return [q, ...matches];
}
