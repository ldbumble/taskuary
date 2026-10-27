// ONE READ OF THE FIRST RUN FOR EVERY VIEW OF IT (the overnight setup walk, 2026-10-26): setup's canvas read /api/setup/first-run every
// 5 s, the setup rail every 8 s and the Assistant again on each step - four or five GETs of the same answer every twelve seconds while
// a person sets up. A read in flight is shared, an answer younger than `fresh` ms is reused, and whoever listens hears every answer.
import api from "./api";

let last = null, at = 0, flight = null;
const subs = new Set();

export function readFirstRun(fresh = 0, opts = {}) {
  if (fresh && last && Date.now() - at < fresh) return Promise.resolve(last);
  if (!flight) flight = api.get("/api/setup/first-run", opts)
    .then(({ data }) => { last = data; at = Date.now(); subs.forEach((f) => f(data)); return data; })
    .finally(() => { flight = null; });
  return flight;
}

// every answer, whoever asked for it
export function onFirstRun(f) { subs.add(f); return () => subs.delete(f); }
