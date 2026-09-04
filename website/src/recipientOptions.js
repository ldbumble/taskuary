export const RECENT_RECIPIENTS = 5;

// The API supplies newest-first options. Keep the closed/fresh picker short like a chat
// sidebar, then search the complete address book as soon as the owner types.
export function recipientOptions(options, query, recentLimit = RECENT_RECIPIENTS) {
  const words = String(query || "").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return options.slice(0, recentLimit);
  return options.filter((option) => {
    const haystack = `${option.name || ""} ${option.to || ""} ${option.hint || ""}`.toLocaleLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

export function recipientLabel(option) {
  if (typeof option === "string") return option;
  return option?.name || option?.to || "";
}

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
