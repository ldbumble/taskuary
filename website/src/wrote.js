// "The page just wrote something." The Timeline's status observer used to be restarted - and so re-read the status - on every
// render of the Assistant, which happened to follow every press; that is how a change the owner made (a setting, a connection,
// a chat that changed one) reached the sync caption at once. With the observer kept alive across renders (perf 2.8, 2026-10-19)
// that has to be said on purpose: every write asks the status again, so nothing the owner does waits for the poll.
export const WROTE = "taskuary:wrote";
export const noteWrite = () => { try { window.dispatchEvent(new Event(WROTE)); } catch { /* no window: nothing listens */ } };
export const onWrote = fn => { window.addEventListener(WROTE, fn); return () => window.removeEventListener(WROTE, fn); };
// ...a WRITE, that is: not a read, and not one sent `quiet` - the record of a press (pressLog.notePress) changes nothing the caption
// shows, and asked the status again on every press of Next (the overnight walk, 2026-10-26)
export const isWrite = c => !!c && !c.quiet && !/^(get|head|options)$/i.test(c.method || "get");
