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
  // ...and a bare type the card's own title writes in lower case is a plain word, not a name: "on my screen" is no Strategy screen,
  // "the database" no Any database (a New sheet job about a screenshot offered the Strategy screen card, 2026-11-03)
  const plain = (c, n) => n === c.type.replace(/_/g, " ") && ` ${c.title.replace(/[^A-Za-z0-9]+/g, " ")} `.includes(` ${n} `);
  const names = (c) => [c.type.replace(/_/g, " "), c.title.toLowerCase(), ...(c.match || []).map((m) => m.toLowerCase()).filter((m) => m.includes(c.type))]
    .filter((n) => !plain(c, n));
  const hits = cards.filter((c) => !c.planned && names(c).some((n) => new RegExp(` ${esc(n.replace(/[^a-z0-9]+/g, " ").trim())} `).test(t)));
  return hits.sort((a, b) => b.title.length - a.title.length)[0] || null;      // "azure openai" over "openai"
};
// THE CONNECTIONS BOX'S MATCHES (the owner, 2026-10-21: "link" typed, and LinkedIn sat third behind Outlook and WhatsApp, whose
// guides only say "link"): a card whose NAME holds the words leads, then its type, then whatever its guide mentions. Several names
// at once, comma-separated - setup types the Advisor's picks here (FirstRun): "Sage Intacct, QuickBooks Online".
export const matchCards = (groups, q) => {
  const terms = String(q || "").split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
  if (!terms.length) return [];
  const rank = (c) => terms.some((x) => String(c.title || "").toLowerCase().includes(x)) ? 0
    : terms.some((x) => String(c.channel || "").replace(/_/g, " ").includes(x)) ? 1 : 2;
  const hits = groups.flatMap((g) => g.cards.map((c) => ({ ...c, crumb: g.title })).filter((c) => rank(c) < 2
    || terms.some((x) => String(c.haystack || "").toLowerCase().includes(x))));
  return hits.map((c, i) => [rank(c), c.planned ? 1 : 0, i, c]).sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]).map((x) => x[3]);
};
// A CARD'S STATE: what it says outright (`state`), else read off its status line. CONNECTED IS SAID, NEVER ASSUMED (the owner,
// 2026-11-10: "it says not added but then green. come on"): any line that did not read as off - a vendor MCP card's "not added", a
// guide card's sentence - fell through to "on" and wore the green ring and the Connected pill. Only a line that says it is on is on:
// a channel card's "on · ...", a data card's "connection ✓", an agent tool's "added · ...".
export const cardState = (c) => (c.state || (c.planned ? "planned" : c.guide ? "guide"
  : /failing|test failed/.test(c.desc) ? "failing"
    : /^on\b|^added\b|connection ✓/.test(c.desc || "") ? "on" : "off"));
// ...and the state a card that is not set up says, one wording for every kind (an MCP card said "not added", a data card "not set up")
export const NOT_SET_UP = "not set up";

// ONE CARD PER SYSTEM, BY THE CATALOGUE'S `system` (the owner, 2026-11-10: "why is there regualr and mcp"): a vendor's MCP entry that
// names another card's type is not a card of its own - the native card stands for the system, and the MCP server is offered inside
// it as one of its two ways in (waysOf below). Where the MCP route is the live one and the native card is not, the one card says so - a connection
// made either way shows as that card connected. With no native card on the page, the MCP card stays, named for the system.
export const oneCardPerSystem = (groups, cards = CATALOGUE) => {
  const sys = Object.fromEntries(cards.filter((c) => c.mcp && c.system).map((c) => [c.type, c.system]));
  const key = (c) => c.type || c.channel, all = groups.flatMap((g) => g.cards);
  const native = new Map();
  for (const c of all) if (!c.planned && !sys[key(c)] && !native.has(key(c))) native.set(key(c), c);
  const folded = new Map();      // native type -> the MCP card folded into it
  for (const c of all) { const s = sys[key(c)]; if (s && native.has(s) && !folded.has(s)) folded.set(s, c); }
  const one = (c) => {
    const m = native.get(key(c)) === c && folded.get(key(c));
    if (!m) return c;
    const live = cardState(m) === "on" && cardState(c) !== "on" && cardState(c) !== "failing";
    return { ...c, haystack: `${c.haystack || ""} ${m.haystack || ""} mcp`, ...(live ? { state: "on", desc: m.desc } : {}) };
  };
  return groups.map((g) => ({ ...g, cards: g.cards.filter((c) => !(sys[key(c)] && native.has(sys[key(c)]))).map(one) }));
};
// ...and ON THAT ONE CARD'S PAGE, ITS TWO WAYS IN as two equal choices (the owner, 2026-11-10: "it's mcp vs api for cards. there should be 2
// options.. yes"): the system's own connector and its vendor's MCP server, each row as it is - `byType` the page's pick of a row per type.
// Null where the system has one way: no choice is drawn. Either way can be open; either or both set up
export const WAY_NAMES = ["API", "MCP"];
// ...each said so a person who has never heard of MCP knows what it gives (the owner, 2026-11-10: "yes simplify")
export const WAYS = { API: "Taskuary reads this system for you: its items reach your rail, reports and agents.",
  MCP: "Your agents use this system's own tools directly." };
export const waysOf = (conn, byType, cards = CATALOGUE) => {
  const cat = conn && cards.find((c) => c.type === conn.Type);
  const twin = cat && (cat.mcp ? cat.system : cards.find((c) => c.mcp && c.system === cat.type)?.type), row = twin && byType[twin];
  return row ? (cat.mcp ? { API: row, MCP: conn } : { API: conn, MCP: row }) : null;
};
export const wayState = (w, c) => ((w === "MCP" ? c?.Active : c?.Active || c?.LastSyncAt) ? "set up" : NOT_SET_UP);
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
  simplefin: "bank", amazon_sp: "seller account", ollama: "Ollama server", chatgpt: "ChatGPT account", hipaa_ai: "HIPAA AI access code", stt_server: "Whisper server",
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

// A MAILBOX PRESET (Fastmail, Yahoo, Proton Mail Bridge, Exchange): a catalogue card whose `preset` is an IMAP card with its servers
// filled in - no protocol of its own. Pressing it makes that card; the card remembers which preset it came from (ConfigJson.preset),
// so its steps say the provider's own words and the preset is not offered again.
export const PRESETS = Object.freeze(Object.fromEntries(catalogue.cards.filter((c) => c.preset).map((c) => [c.type, c])));
const cfgOf = (conn) => { try { return JSON.parse(conn?.ConfigJson || "{}"); } catch { return {}; } };
/** The catalogue card a connection was made from, or null. */
export const presetOf = (conn) => { const p = PRESETS[cfgOf(conn).preset]; return p && p.preset.type === conn.Type ? p : null; };
/** The new card's body for a preset - its type, its name and the servers it starts with. */
export const presetBody = (type) => { const p = PRESETS[type];
  return { Type: p.preset.type, Name: p.title, ConfigJson: JSON.stringify({ ...p.preset.config, preset: type }) }; };
/** The presets still to offer: none already made into a card. */
export const presetsLeft = (types, connectors) => types.filter((t) => PRESETS[t] && !(connectors || []).some((c) => cfgOf(c).preset === t));
// A SOURCE THAT ANSWERS ON ITS OWN THREAD (inboxes.REPLY): what a reply becomes there, and where its card's Replies switch starts - on for a
// helpdesk or a chat, off for a public post (the owner, 2026-11-08). The card's own `replies` / `reply_note` once the owner moved them.
export const repliesOf = (type) => CATALOGUE.find((c) => c.type === type)?.replies || null;
export const repliesOn = (type, cfg = {}) => (cfg.replies == null ? !!repliesOf(type)?.on : [true, 1, "1", "true", "on"].includes(cfg.replies));
