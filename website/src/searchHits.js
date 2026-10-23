// What the search box's answers look like (SearchEverything.jsx; the server's search.py): the pill each kind of hit wears,
// the order the kinds are listed in, the filter strip's counts and the matched words picked out of a line.

// `tone` names the colour SearchEverything.jsx draws the pill in (TONES there)
export const KINDS = {
  task:    { label: "Task",    group: "Tasks", tone: "slate" },
  email:   { label: "Email",   group: "Email", tone: "oat" },
  chat:    { label: "Chat",    group: "Chats", tone: "sage" },
  pr:      { label: "PR",      group: "Code", tone: "brass" },
  issue:   { label: "Issue",   group: "Code", tone: "brass" },
  advisor: { label: "Advisor", group: "Advisor", tone: "advisor" },
  report:  { label: "Report",  group: "Reports", tone: "brass" },
  ticket:  { label: "Ticket",  group: "Other", tone: "oat" },
  note:    { label: "Note",    group: "Other", tone: "oat" },
  item:    { label: "Item",    group: "Other", tone: "oat" },
  source:  { label: "Source",  group: "Sources", tone: "pick" },
  // the app's own places (search.py's registry): a hit opens the page at it
  setting:   { label: "Setting", group: "Settings", tone: "oat" },
  connector: { label: "Connection", group: "Connections", tone: "pick" },
};
export const GROUPS = ["Tasks", "Email", "Chats", "Code", "Advisor", "Reports", "Other", "Sources", "Connections", "Settings"];
const FILTER_LABEL = { Code: "Pull requests", Chats: "Chats", Email: "Email" };
export const kindOf = (h) => KINDS[h?.type] || KINDS.item;

// The hits in list order - grouped by kind, each group in the server's own order (best match first) - narrowed to one
// group when a filter is on. `flat` is what the arrow keys walk.
export function arrange(hits, only = "") {
  const by = {};
  for (const h of hits || []) (by[kindOf(h).group] ||= []).push(h);
  const groups = GROUPS.filter((g) => by[g]?.length && (!only || only === g)).map((g) => ({ group: g, hits: by[g] }));
  return { groups, flat: groups.flatMap((g) => g.hits) };
}

// HOW MANY THERE WERE, not how many came back (the 2026-10-19 UI walk): the list is cut - eight tasks, thirty threads - and the
// footer said "15 of 15" over it. The server counts each type past its cap (search.py `totals`); a group is never fewer than it
// shows, and `capped` - the mail index stopped counting - makes it "30+"
export function totalOf(res, group = "") {
  const t = res?.totals || {}, hits = res?.hits || [];
  const types = new Set([...Object.keys(t), ...hits.map((h) => h.type)].filter((k) => !group || kindOf({ type: k }).group === group));
  const n = [...types].reduce((a, k) => a + Math.max(t[k] || 0, hits.filter((h) => h.type === k).length), 0);
  const mail = [...types].some((k) => !["task", "source", "setting", "connector"].includes(k));
  return { n, more: !!res?.capped && mail };
}
export const countWords = ({ n, more }) => `${n}${more ? "+" : ""}`;

// the filter strip: "All" and each kind that has something, with its count - the whole count, past the cap (totalOf)
export function filters(hits, res = null) {
  const n = {};
  for (const h of hits || []) { const g = kindOf(h).group; n[g] = (n[g] || 0) + 1; }
  const all = res ? countWords(totalOf(res)) : (hits || []).length;
  return [{ key: "", label: "All", n: all },
    ...GROUPS.filter((g) => n[g]).map((g) => ({ key: g, label: FILTER_LABEL[g] || g, n: res ? countWords(totalOf(res, g)) : n[g] }))];
}

// ONE WAY TO SAY NOTHING WAS FOUND, on every page with a box (the 2026-10-19 UI walk: each said it its own way, and none said where
// else to look). A page's own box says what it searched, and that the box at the top searches everything
export const nothingMatches = (q, where = "") =>
  `Nothing matches “${String(q || "").trim()}”${where ? ` in ${where}. The search at the top looks through everything` : ""}.`;

// The words typed, as the server reads them, for marking matches. A word is matched as a prefix of a word in the line,
// the way the index matched it - "digic" marks the start of "DigiCert", not every "ic".
// ...without `status:open`, which asks for a task's status by name and is no word of any line (search.py)
const STATUS = /^status:\S/i;
export const terms = (q) => (String(q || "").split(/\s+/).filter((t) => !/^status:/i.test(t)).join(" ").match(/[\w@.\-]+/g) || [])
  .filter((w) => w.length > 1 || /\d/.test(w));
// is there anything to ask the server for: a word, or a status
export const asks = (q) => terms(q).length > 0 || String(q || "").split(/\s+/).some((t) => STATUS.test(t));
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export function marks(text, words) {
  const s = String(text || "");
  if (!s || !words?.length) return [{ t: s, hit: false }];
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(${words.map(esc).sort((a, b) => b.length - a.length).join("|")})`, "giu");
  const out = [];
  let at = 0;
  for (const m of s.matchAll(re)) {
    if (m.index > at) out.push({ t: s.slice(at, m.index), hit: false });
    out.push({ t: m[0], hit: true }); at = m.index + m[0].length;
  }
  if (at < s.length) out.push({ t: s.slice(at), hit: false });
  return out;
}

// the small grey line under a title: who, where, and the task it is on when the title is not already the task
export function meta(h) {
  if (h.type === "task") return [h.sub, h.status && ["done", "dropped"].includes(h.status) ? (h.status === "done" ? "closed" : "dropped") : ""].filter(Boolean);
  // a WhatsApp source is titled by its name or number; its JID is the small line (search.py `sub`)
  if (h.type === "source") return [h.channel, h.sub].filter(Boolean);
  if (h.href) return [h.where, h.sub].filter(Boolean);
  return [h.who, h.where && h.where !== h.who ? h.where : ""].filter(Boolean);
}
