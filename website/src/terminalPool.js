// Panes kept alive out of sight. Leaving an agent used to dispose its xterm and close its socket, so coming back
// rebuilt both and waited on a replay from the server; switching between the agents you are juggling was never
// instant. A pane put away now stays connected and drawing (off screen) until the pool is over its cap - the
// "Agents at once" setting, since that is how many agents there are to switch between - and the oldest goes first.
// Measured 2026-10-01: ~1 MB a pane as opened, ~35 MB with a full 10,000-line scrollback of wide output.

export const paneCap = (value) => {                     // read exactly as the server reads auto_sessions (ingest.auto_sessions)
  const n = parseInt(value, 10);
  return Number.isNaN(n) ? 4 : Math.max(1, Math.min(16, n));
};

export function createPool(dispose) {
  const kept = new Map();                          // sid -> session, oldest first
  return {
    take(sid) { const s = kept.get(sid) || null; kept.delete(sid); return s; },
    keep(sid, s, cap) {
      const old = kept.get(sid);
      if (old && old !== s) dispose(old);          // two panes on one session were both put away: the later one stays
      kept.delete(sid); kept.set(sid, s);
      for (const [k, v] of kept) { if (kept.size <= cap) break; kept.delete(k); dispose(v); }
    },
    forget(sid, s) { if (kept.get(sid) === s) kept.delete(sid); },
    size: () => kept.size,
  };
}
