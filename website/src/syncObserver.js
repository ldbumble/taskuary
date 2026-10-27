import { syncStatusDelay } from './syncTiming.js';

// One cancellable status reader. Live events prompt a read; periodic reads also
// discover completion when an event is lost. Elapsed time never means completion.
// `gather`: live events that come in a burst are read ONCE, `gather` ms after the last of them - a press of Next sends two or three
// (the walk's settle, the rail's, the turn's), and each asked the status again (the overnight walk, 2026-10-26)
export function observeSync({ read, changed, failed, subscribe, now = Date.now,
  schedule = setTimeout, cancel = clearTimeout, gather = 0 }) {
  let alive = true, flight = null, again = false, timer = null, soon = null;
  let running = false, nextAt = null, unavailable = false;
  const refresh = () => {
    if (!alive) return Promise.resolve();
    if (flight) { again = true; return flight; }
    cancel(timer);
    flight = Promise.resolve().then(read).then(data => {
      if (!alive) return;
      unavailable = false;
      running = data.status?.state === 'running';
      nextAt = data.nextPollAt ? now() + (data.nextPollAt - data.now) * 1000 : null;
      changed(data);
    }).catch(error => { if (alive) { unavailable = true; failed(error); } }).finally(() => {
      flight = null;
      if (!alive) return;
      const delay = again ? 0 : syncStatusDelay({ running: running || unavailable, nextAt, now: now() });
      again = false;
      timer = schedule(refresh, delay);
    });
    return flight;
  };
  const nudge = () => { if (!gather) return refresh(); cancel(soon); soon = schedule(() => { soon = null; refresh(); }, gather); };
  const unsubscribe = subscribe(nudge);
  refresh();
  return { refresh, stop() { alive = false; cancel(timer); cancel(soon); unsubscribe(); } };
}
