// A draft built on New, waiting for Reports to open it. New and Reports are separate views - one may not be mounted when the
// other builds - so the draft waits here: a view that is open hears it at once, one that opens later takes it on mount.
let pending = null;
const listeners = new Set();

export const handDraft = (kind, config, meta) => {
  pending = { kind, config, meta };
  for (const f of listeners) f();
};
export const takeDraft = () => { const p = pending; pending = null; return p; };
export const onDraftHanded = (f) => { listeners.add(f); return () => listeners.delete(f); };
// where each kind's draft opens (canvasLinks reads it; ReportsView reads the hash on its tab)
export const DRAFT_HASH = { report: "report=draft", workflow: "report=draft-workflow", dashboard: "report=draft-dashboard" };
