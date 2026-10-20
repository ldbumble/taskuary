// CONNECTIONS' THREE LISTS, ASKED FOR WITH THE PAGE (the 2026-10-19 UI walk, G8): a cold #connector=whatsapp link waited for the canvas's
// chunk, then Connections' own chunk, and only then asked the server for the connections, sources and report types - the first of those
// reads went out ~1.4 s after the page was asked for, and the card waited on all three. They are asked for where the page is asked for
// (the address read in TaskHubPage, a sidebar press in AssistantView browse), beside the chunks, and the view's first load takes that
// answer; every later load reads anew.
const HOLD = 10000;                     // older than this, a list read ahead is not the view's first load: it reads its own
let held = null;                        // { at, p }
export const readLists = (api) => {
  if (held && Date.now() - held.at < HOLD) return held.p;
  const rec = { at: Date.now(), p: null };
  rec.p = Promise.all([api.get("/api/connectors"), api.get("/api/sources"), api.get("/api/report-types")]);
  rec.p.catch(() => { if (held === rec) held = null; });
  held = rec;
  return rec.p;
};
// the read ahead, once: the view's first load spends it, and a reload after a save never draws the lists from before the save
export const takeLists = () => { const e = held; held = null; return e && Date.now() - e.at < HOLD ? e.p : null; };
