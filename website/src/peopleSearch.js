// FINDING A PERSON BY WHAT YOU REMEMBER OF THEM (the owner, 2026-10-27: "I search 'dynamo' and a list of Dynamo people should show
// up"). The server searches everyone known - mail both ways, the org chart, a connected directory, a chat channel's chats - by name,
// company and the parts of an address, ranked by how much the owner writes with them (/api/people/search, peoplesearch.py). The model
// is asked only after the plain answer came back empty or the words describe someone, and once per query: typing never waits on it.
export const SEARCH_MS = 200, AI_MS = 600;
const STOP = new Set(["the", "a", "an", "at", "from", "of", "in", "on", "for", "person", "guy", "lady", "someone", "who", "and", "my", "our", "with"]);
const words = (q) => String(q || "").toLowerCase().match(/[a-z0-9]+/g) || [];
export const describes = (q) => { const w = words(q); return w.length >= 3 || (w.length >= 2 && w.some((x) => STOP.has(x))); };
export const wantsAi = (q, rows) => String(q || "").trim().length >= 3 && (!(rows || []).length || describes(q));

// the line under a person's name: their company (the directory's, else the domain's), and whether the model chose them
export const personLine = (o) => [o?.company || o?.org || "", o?.ai ? "suggested by AI" : ""].filter(Boolean).join(" · ");

// a server row as the recipient pickers' option ({to, name, hint}), so one renderer serves both
export const asOption = (r, ai) => ({ to: r.to, name: r.name || "", hint: personLine({ ...r, ai }), company: r.company || r.org || "", ai: !!ai, found: true });

// what the box offers: the server's ranked people for THIS query first, then the local matches it did not already name. An answer for
// an older query is not shown over a newer one's local matches.
export function withFound(local, found, query) {
  const q = String(query || "").trim();
  if (!q || !found || found.q !== q || !(found.rows || []).length) return local;
  const key = (o) => String(typeof o === "string" ? o : o?.to || "").toLowerCase();
  const top = found.rows.map((r) => asOption(r, found.ai)), have = new Set(top.map(key));
  return [...top, ...local.filter((o) => !have.has(key(o)))];
}

// one search per pause in typing; the model's turn after it, only when wanted, and never twice for the same words
const aiSaid = new Map();
export function runSearch(get, q, channel, set, { wait = SEARCH_MS, aiWait = AI_MS } = {}) {
  const t = String(q || "").trim();
  let on = true, ai = 0;
  if (t.length < 2) { set({ q: t, rows: [], ai: false }); return () => {}; }
  const ask = (withAi) => Promise.resolve(get("/api/people/search", { params: { q: t, channel, ...(withAi ? { ai: 1 } : {}) } })).then(({ data }) => data || {});
  const id = setTimeout(async () => {
    try {
      const d = await ask(false); if (!on) return;
      set({ q: t, rows: d.data || [], ai: false });
      if (!wantsAi(t, d.data)) return;
      const k = `${channel}|${t.toLowerCase()}`;
      if (aiSaid.has(k)) { const a = aiSaid.get(k); if (a.length) set({ q: t, rows: a, ai: true }); return; }
      ai = setTimeout(async () => {
        try {
          const a = await ask(true); const rows = a.ai ? a.data || [] : [];
          aiSaid.set(k, rows);
          if (on && rows.length) set({ q: t, rows, ai: true });
        } catch { /* the plain answer stands */ }
      }, aiWait);
    } catch { /* the local list still answers */ }
  }, wait);
  return () => { on = false; clearTimeout(id); clearTimeout(ai); };
}
export const forgetAi = () => aiSaid.clear();
