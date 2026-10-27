// EVERYONE TASKUARY HAS SEEN (/api/people), read ONCE for every picker drawn within a minute: a draft's To and Cc rows each asked
// for the whole list, and every press of Next that drew a draft read it twice (the overnight walk, 2026-10-26). A failed read is not
// kept - the next picker asks again.
export const CONTACTS_MS = 60000;
let at = 0, held = null;
export function readContacts(get, now = Date.now()) {
  if (held && now - at < CONTACTS_MS) return held;
  at = now;
  const read = held = Promise.resolve().then(() => get("/api/people")).then(({ data }) => data?.data || []);
  read.catch(() => { if (held === read) held = null; });
  return read;
}
export const forgetContacts = () => { held = null; at = 0; };
