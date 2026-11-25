// "The page just wrote something." The Timeline's status observer used to be restarted - and so re-read the status - on every
// render of the Assistant, which happened to follow every press; that is how a change the owner made (a setting, a connection,
// a chat that changed one) reached the sync caption at once. With the observer kept alive across renders (perf 2.8, 2026-10-19)
// that has to be said on purpose: every write asks the status again, so nothing the owner does waits for the poll.
export const WROTE = "taskuary:wrote";
export const noteWrite = () => { try { window.dispatchEvent(new Event(WROTE)); } catch { /* no window: nothing listens */ } };
export const onWrote = fn => { window.addEventListener(WROTE, fn); return () => window.removeEventListener(WROTE, fn); };
// ...a WRITE, that is: not a read, and not one sent `quiet` changes nothing the caption
// shows, and asked the status again on every press of Next (the overnight walk, 2026-10-26)
export const isWrite = c => !!c && !c.quiet && !/^(get|head|options)$/i.test(c.method || "get");
// ...AND A WRITE TO WHAT AN AI OR A SOURCE IS (a card switched on or off, a setting, a setup step) MOVES SETUP: every view that reads which AI
// answers - the top bar's setup chip, the task's AI pill, the chat's "No AI is connected yet" - reads it again (walk 19: the AI card came back on
// and the bar still said "Setup: pick your AI" over a greyed pill while the AI answered)
export const SETUP_CHANGED = "tq-setup-changed";
export const movesSetup = c => isWrite(c) && /^\/api\/(connectors|settings|setup)(\/|\?|$)/.test(String(c.url || ""));
export const noteSetup = c => { if (movesSetup(c)) try { window.dispatchEvent(new Event(SETUP_CHANGED)); } catch { /* no window */ } };
