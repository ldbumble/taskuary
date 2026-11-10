// WHAT IS TYPED AND NOT SENT STAYS IN ITS TASK'S BOX (the owner, 2026-11-10: "Back on the task, text kept"): a reload, a restart of the app
// or the chat pane drawn afresh emptied the box under a half-written line. Kept per task, in this browser only - the words were never sent,
// so they are nobody's but the page's. A browser that keeps nothing (private mode, storage blocked) keeps them in the box alone, as before.
const key = (id) => `tq-unsent:${id}`;
export const unsent = (id, store = globalThis.localStorage) => { try { return (id && store?.getItem(key(id))) || ""; } catch { return ""; } };
export const keepUnsent = (id, text, store = globalThis.localStorage) => {
  try { if (!id) return; if (String(text || "").trim()) store?.setItem(key(id), text); else store?.removeItem(key(id)); } catch { /* the box still has them */ }
};
