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
};
export const GROUPS = ["Tasks", "Email", "Chats", "Code", "Advisor", "Reports", "Other", "Sources"];
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

// the filter strip: "All" and each kind that has something, with its count
export function filters(hits) {
  const n = {};
  for (const h of hits || []) { const g = kindOf(h).group; n[g] = (n[g] || 0) + 1; }
  return [{ key: "", label: "All", n: (hits || []).length },
    ...GROUPS.filter((g) => n[g]).map((g) => ({ key: g, label: FILTER_LABEL[g] || g, n: n[g] }))];
}

// The words typed, as the server reads them, for marking matches. A word is matched as a prefix of a word in the line,
// the way the index matched it - "digic" marks the start of "DigiCert", not every "ic".
export const terms = (q) => (String(q || "").match(/[\w@.\-]+/g) || []).filter((w) => w.length > 1 || /\d/.test(w));
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
  if (h.type === "source") return [h.channel];
  return [h.who, h.where && h.where !== h.who ? h.where : ""].filter(Boolean);
}
