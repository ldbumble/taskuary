// "The page just wrote something." The Timeline's status observer used to be restarted - and so re-read the status - on every
// render of the Assistant, which happened to follow every press; that is how a change the owner made (a setting, a connection,
// a chat that changed one) reached the sync caption at once. With the observer kept alive across renders (perf 2.8, 2026-10-19)
// that has to be said on purpose: every write asks the status again, so nothing the owner does waits for the poll.
export const WROTE = "taskuary:wrote";
export const noteWrite = () => { try { window.dispatchEvent(new Event(WROTE)); } catch { /* no window: nothing listens */ } };
export const onWrote = fn => { window.addEventListener(WROTE, fn); return () => window.removeEventListener(WROTE, fn); };
