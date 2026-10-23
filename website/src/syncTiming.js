import { fmtTime } from "./dates.js";
// The server's scheduler wakes every 30 seconds. Far from the next scheduled sync the Timeline
// can check quietly; near (and just after) the due time it must watch closely or a short refresh
// can start and finish between UI checks and the sync glyph never moves.
export const syncStatusDelay = ({ running = false, nextAt = null, now = Date.now() } = {}) => {
  if (running) return 2000;
  if (!nextAt) return 30000;
  const untilDue = nextAt - now;
  if (untilDue > 35000) return Math.min(30000, untilDue - 30000);
  // A minute overdue the scheduler is off, asleep or stuck (the demo never polls): 2 Hz for ever was ~120 reads an idle minute,
  // each a full re-render of the rail on a large home (perf 2.8, 2026-10-19). A sync that does start says so on the socket.
  return untilDue > -60000 ? 500 : 30000;
};

// One face for the sync clock, so the Timeline's caption and the pipe's chip can never disagree
// about when the mail was last read. `lastAt` is a real Date (built from the SERVER's clock, not
// from parsing a UTC string as local time - that read "in 3h" on an east-coast box).
export const syncPhaseLabel = phase => ({ fetching: 'Reading sources', triaging: 'Organizing',
  checking: 'Checking updates', running_reports: 'Running reports' }[phase] || 'Syncing');

export const syncFace = ({ busy = false, what = "", every = 10, lastAt = null, nextIn = null, terse = false, checked = false, started = false, failed = [] } = {}) => {
  if (busy) return what && !terse ? what : "syncing…";
  if (!every) return terse ? "sync off" : "background sync off";
  const at = lastAt ? fmtTime(lastAt, "en-US", { hour: "numeric", minute: "2-digit" }) : "—";
  const verb = started ? 'check started' : checked ? 'checked' : 'synced';
  const bad = failed.length ? ` · ${failed.join(", ")} failed` : "";   // a source that could not be read is never covered by "checked"
  // terse is the narrowed sidebar's one line (2026-09-29): the whole time must fit, so a started check says just that - and a
  // failed source still rides it: "checked 9:41" over a mailbox that refused was a sync that said nothing (2026-10-22)
  if (terse) return `${started ? 'started' : verb} ${at}${bad}`;
  const nxt = nextIn == null ? "" : nextIn <= 0 ? " · next sync due now" : ` · next in ${Math.floor(nextIn / 60)}:${String(nextIn % 60).padStart(2, "0")}`;
  return `${verb} ${at}${nxt}${bad}`;
};
