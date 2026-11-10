import { fmtTime } from "./dates.js";
import { span } from "./timeWords.js";
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

export const syncFace = ({ busy = false, what = "", every = 10, lastAt = null, nextIn = null, terse = false, checked = false, started = false } = {}) => {
  if (busy) return what && !terse ? what : "syncing…";
  if (!every) return terse ? "sync off" : "background sync off";
  const at = lastAt ? fmtTime(lastAt, "en-US", { hour: "numeric", minute: "2-digit" }) : "—";
  const verb = started ? 'check started' : checked ? 'checked' : 'synced';
  // terse is the narrowed sidebar's one line (2026-09-29): the whole time must fit, so a started check says just that. A source
  // that could not be read rode it in red (2026-10-22) until the owner moved it to the bell (2026-10-23): a clock, never an error
  // ...and a check started but not yet heard back from says nothing at rest: "started 7:50 PM" named no thing that started (audit, 2026-11-05)
  if (terse) return started ? "" : `${verb} ${at}`;
  const nxt = nextIn == null ? "" : nextIn <= 0 ? " · next sync due now" : ` · next in ${Math.floor(nextIn / 60)}:${String(nextIn % 60).padStart(2, "0")}`;
  return `${verb} ${at}${nxt}`;
};

// WHAT A SYNC IS BRINGING IN, from the server's own numbers (the owner, 2026-11-10: "we need the app to say how far back it's going and
// next to the word sync show brin[g]ing in emails count"): `back` = the hours a connection read for the first time reaches back,
// `landed` = how many came in so far (server._reading). A first read says how far back it goes; any sync its count once it has one;
// and the count it ended on stays a moment after (`brought`). '' = nothing of its own to say, and the clock's words stand.
const lastOf = (h) => span(h * 60, true).replace(/^1 /, "");      // "the last 3 days", "the last day"
export const broughtLine = (n, hours) => (hours ? `brought in ${n} from the last ${lastOf(hours)}` : n ? `brought in ${n}` : "");
export const syncLine = ({ busy = false, phase = "", what = "", landed = 0, back = 0, brought = null } = {}) => {
  if (!busy) return brought ? broughtLine(brought.n || 0, brought.hours || 0) : "";
  if (phase && phase !== "fetching") return landed ? [`brought in ${landed}`, what.replace(/^syncing( · )?/, "")].filter(Boolean).join(" · ") : "";
  return back ? `going back ${span(back * 60, true)}${landed ? ` · bringing in ${landed}…` : "…"}` : landed ? `bringing in ${landed}…` : "";
};
