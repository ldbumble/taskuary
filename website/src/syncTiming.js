// The server's scheduler wakes every 30 seconds. Far from the next scheduled sync the Timeline
// can check quietly; near (and just after) the due time it must watch closely or a short refresh
// can start and finish between UI checks and the sync glyph never moves.
export const syncStatusDelay = ({ running = false, nextAt = null, now = Date.now() } = {}) => {
  if (running) return 2000;
  if (!nextAt) return 30000;
  const untilDue = nextAt - now;
  return untilDue > 35000 ? Math.min(30000, untilDue - 30000) : 500;
};

// One face for the sync clock, so the Timeline's caption and the pipe's chip can never disagree
// about when the mail was last read. `lastAt` is a real Date (built from the SERVER's clock, not
// from parsing a UTC string as local time - that read "in 3h" on an east-coast box).
export const syncFace = ({ busy = false, what = "", every = 10, lastAt = null, nextIn = null, terse = false } = {}) => {
  if (busy) return what && !terse ? what : "syncing…";
  if (!every) return terse ? "sync off" : "background sync off";
  const at = lastAt ? lastAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "—";
  if (terse) return `synced ${at}`;
  const nxt = nextIn == null ? "" : nextIn <= 0 ? " · next sync due now" : ` · next in ${Math.floor(nextIn / 60)}:${String(nextIn % 60).padStart(2, "0")}`;
  return `synced ${at}${nxt}`;
};
