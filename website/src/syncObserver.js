import { syncStatusDelay } from './syncTiming.js';

// One cancellable status reader. Live events prompt a read; periodic reads also
// discover completion when an event is lost. Elapsed time never means completion.
export function observeSync({ read, changed, failed, subscribe, now = Date.now,
  schedule = setTimeout, cancel = clearTimeout }) {
  let alive = true, flight = null, again = false, timer = null;
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
  const unsubscribe = subscribe(refresh);
  refresh();
  return { refresh, stop() { alive = false; cancel(timer); unsubscribe(); } };
}
