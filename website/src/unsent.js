// WHAT IS TYPED AND NOT SENT STAYS IN ITS TASK'S BOX (the owner, 2026-11-10: "Back on the task, text kept"): a reload, a restart of the app
// or the chat pane drawn afresh emptied the box under a half-written line. Kept per task, in this browser only - the words were never sent,
// so they are nobody's but the page's. A browser that keeps nothing (private mode, storage blocked) keeps them in the box alone, as before.
const key = (id) => `tq-unsent:${id}`;
export const unsent = (id, store = globalThis.localStorage) => { try { return (id && store?.getItem(key(id))) || ""; } catch { return ""; } };
export const keepUnsent = (id, text, store = globalThis.localStorage) => {
  try { if (!id) return; if (String(text || "").trim()) store?.setItem(key(id), text); else store?.removeItem(key(id)); } catch { /* the box still has them */ }
};
// ...a COMPOSER that stays while its task changes under it (the Assistant's walk moves from one task to the next in the same pane): its box
// shows the new task's own words - never the last task's, which were then kept as the new one's draft too. `c`: assistant-ui's composer
// ({ getState, setText, subscribe }), `was`: a ref of the task the box last held. Returns the unsubscribe
export const holdUnsent = (c, id, was, store = globalThis.localStorage) => {
  if (was.current !== id) { was.current = id; c.setText(unsent(id, store)); }
  else if (!c.getState().text && unsent(id, store)) c.setText(unsent(id, store));     // ...put back into an empty box only
  return c.subscribe(() => keepUnsent(id, c.getState().text, store));
};
