// ONE READ IN FLIGHT PER KEY (2026-10-23). Every poke, poll and press read the open task again on its own, so while the server
// was stalled one task page held twenty GET /api/tasks/<id> open at once - each one more for the stalled server to answer before
// anything else. Now a call while that key's read runs marks it dirty and shares the ONE re-read that follows it (the newest
// arguments win), so a caller that awaits still gets an answer taken after its own write. `drop(keep)` aborts every other key's
// read - the page moved to another task, and an answer about the last one is of no use to it.
// fn(...args, signal) does the read; the AbortSignal goes to axios (`{ signal }`).
export function coalesce(fn) {
  const flights = new Map();          // key -> { ctl, args, p, next, dead }
  const go = (key, args) => {
    const f = { ctl: new AbortController(), args, next: null, dead: false };
    flights.set(key, f);
    f.p = Promise.resolve().then(() => fn(...args, f.ctl.signal))
      .finally(() => { if (flights.get(key) === f && !f.next) flights.delete(key); });
    return f.p;
  };
  const run = (key, ...args) => {
    const f = flights.get(key);
    if (!f) return go(key, args);
    f.args = args;
    return f.next ||= f.p.catch(() => {}).then(() => f.dead ? undefined : go(key, f.args));
  };
  const drop = (keep) => {
    for (const [k, f] of flights) if (k !== keep) { f.dead = true; f.ctl.abort(); flights.delete(k); }
  };
  return { run, drop, busy: (key) => flights.has(key) };
}
