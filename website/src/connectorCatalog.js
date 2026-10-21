// ONE CATALOGUE, in taskuary/connectorcatalog.json: the working cards and the planned ones, each with
// a group, a line and the words that mean that system. This page reads the planned ones from it; the
// Assistant report reads the same file on the server to suggest what to connect (connectorcatalog.py,
// assistant.connect_evidence) - which it could not do while the roadmap lived only here (2026-09-18).
// Keeping the roadmap in data rather than scattering one-off cards through ConnectorsView makes it
// harder for a category to quietly become empty.
import catalogue from "../../taskuary/connectorcatalog.json" with { type: "json" };

const grouped = {};
for (const c of catalogue.cards) {
  if (!c.planned) continue;
  (grouped[c.group] ||= []).push({ type: c.type, title: c.title, desc: c.desc });
}
export const PLANNED_CONNECTORS = Object.freeze(grouped);
export const CATALOGUE = Object.freeze(catalogue.cards);
export const plannedFor = (category) => PLANNED_CONNECTORS[category] || [];
// THE CARD THE WORDS NAME (a tester, 2026-10-20: "i want to connect taskuary to linkedin" typed into New's agent job had no way to
// Connections): a working card whose type or title stands in the words as a whole word - read from the catalogue, never a word list.
// Only the catalogue's own names count (a match word is used when it carries the type, "outlook mail"), so "online" is never QuickBooks.
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const connectorNamed = (text, cards = CATALOGUE) => {
  const t = ` ${String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, " ")} `;
  if (!t.trim()) return null;
  const names = (c) => [c.type.replace(/_/g, " "), c.title.toLowerCase(), ...(c.match || []).map((m) => m.toLowerCase()).filter((m) => m.includes(c.type))];
  const hits = cards.filter((c) => !c.planned && names(c).some((n) => new RegExp(` ${esc(n.replace(/[^a-z0-9]+/g, " ").trim())} `).test(t)));
  return hits.sort((a, b) => b.title.length - a.title.length)[0] || null;      // "azure openai" over "openai"
};
// ONE CARD PER SYSTEM: a planned card is dropped where a card for the same type is already on the page - a live one anywhere, or
// the same planned type earlier. The server's planned list (reports.PLANNED) and this catalogue are kept apart, and PointClickCare
// drew twice: once by its catalogue name under Corporate systems, once as a bare "pointclickcare" under Everything else (2026-10-19 UI walk)
export const onceEach = (groups) => {
  const live = new Set(groups.flatMap((g) => g.cards.filter((c) => !c.planned).map((c) => c.type || c.channel))), seen = new Set();
  return groups.map((g) => ({ ...g, cards: g.cards.filter((c) => {
    const t = c.type || c.channel;
    if (!c.planned) return true;
    if (live.has(t) || seen.has(t)) return false;
    seen.add(t); return true; }) }));
};

// WHAT ONE CARD IS, so Add another says what it adds - "Add another Outlook mailbox", "Add another bank" (the owner,
// 2026-10-20). Most read off the catalogue: the card's name (its title, the parenthesis, a "/ ..." or " - ..." tail off)
// and what one card of its section is. The few the name cannot say, say it here; null is a card that is one by nature -
// the phone WhatsApp pairs, this Mac's Messages, the app's own knowledge, a keyless public feed.
const UNIT = { Databases: "database", "AI — agents & models": "key", "AI — voice": "key", "AI — images": "key", "Agentic web": "key",
  "Agent tools": "connection" };
const ONE = { outlook: "Outlook mailbox", gmail: "Gmail account", imap: "IMAP mailbox", teams: "Teams account", slack: "Slack workspace",
  telegram: "Telegram bot", discord: "Discord bot", database: "database", sharepoint: "SharePoint site", smb_file: "file share",
  sftp: "SFTP server", winrm: "Windows machine", azure: "Azure subscription", azdo: "Azure DevOps organization", teller: "bank",
  simplefin: "bank", ollama: "Ollama server", chatgpt: "ChatGPT account", hipaa_ai: "HIPAA AI access code", stt_server: "Whisper server",
  image_server: "image server", prometheus: "Prometheus server", screen: "strategy screen",
  whatsapp: null, imessage: null, knowledge: null, handbook: null, local_whisper: null,
  coingecko: null, frankfurter: null, yahoo: null, sec_edgar: null, fred: null };
const BY_TYPE = Object.fromEntries(catalogue.cards.map((c) => [c.type, c]));
const shortName = (t) => t.replace(/\s*\(.*?\)\s*/g, " ").replace(/\s+(\/|-)\s.*$/, "").trim();
/** "Outlook mailbox" for "Add another Outlook mailbox" - null where a second card makes no sense. */
export const oneOf = (type) => {
  if (type in ONE) return ONE[type];
  const c = BY_TYPE[type];
  return c ? `${shortName(c.title)} ${UNIT[c.group] || "account"}` : `${type} connection`;
};
