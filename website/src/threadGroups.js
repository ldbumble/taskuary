// Several rows that are ONE THING, folded into one row - and "one thing" means ONE TASK.
//
// The first cut of this grouped by ConversationId, which was wrong in the way that matters: on a
// report, the assistant's posts and a WhatsApp chat, the conversation id is the CHANNEL, not the
// subject. So five runs of "Process Error Check", twelve assistant posts and a day of messages
// from one person each collapsed into a single line - random grouping, and it HID a photo the
// owner was looking for. A fold that hides the wrong rows is worse than no fold.
//
// A task is the honest unit. Messages on one task are one thing by construction: triage put them
// there, or a thread attached to it, and the app already treats them as one piece of work. Rows
// with no task - filed, fyi, ignored, a report nobody acted on - never fold, however alike they
// look, because nothing has judged them to be the same thing.
//
// WHERE THE FOLD SITS is the newest member's time. Anchored to the first message instead, a live
// thread sinks down the rail while it is still live - the failure mode of every inbox sorted by
// when a thread began. A new message bumps the whole fold to now: that is the point of it.

export const FOLD_MIN = 2;                 // two rows on one task are already a repetition

const at = (r) => String(r?.SentAt || "");
const taskOf = (r) => (r?.TaskId === 0 || r?.TaskId ? String(r.TaskId) : "");

/** One day's rows (newest first) as a list of entries: a plain row, or a fold of several.
 *  Folds keep the position of their newest member; everything else stays exactly where it was. */
export const groupThreads = (rows, { min = FOLD_MIN } = {}) => {
  const list = rows || [];
  const bucket = new Map();
  for (const r of list) {
    const key = taskOf(r);
    if (!key) continue;
    (bucket.get(key) || bucket.set(key, []).get(key)).push(r);
  }
  const out = [];
  const spent = new Set();
  for (const r of list) {
    const key = taskOf(r);
    const group = key ? bucket.get(key) : null;
    if (!group || group.length < min) { out.push({ kind: "row", key: `m${r.MessageId}`, row: r }); continue; }
    if (spent.has(key)) continue;          // already emitted at its newest member's place
    spent.add(key);
    const members = [...group].sort((a, b) => at(b).localeCompare(at(a)));   // newest first, like the rail
    out.push({ kind: "fold", key: `t${key}`, tid: key, rows: members, row: members[0] });
  }
  return out;
};

/** The state the FOLD wears: the loudest thing inside it. A pending reply two messages down must
 *  not be hidden by a fold whose newest line happens to be fyi - that would make folding a way to
 *  lose work. `rank` is the order of demand, passed in so this file stays pure. */
export const loudest = (members, stateOf, rank) => {
  let best = null, bestAt = Infinity;
  for (const m of members || []) {
    const k = stateOf(m);
    const i = rank.indexOf(k);
    if (i >= 0 && i < bestAt) { best = k; bestAt = i; }
  }
  return best || (members?.length ? stateOf(members[0]) : "fyi");
};

/** "1:00 PM – 1:47 PM", or the one time when a fold happens to span a minute. `fmt` is the rail's
 *  own clock formatter. */
export const spanText = (members, fmt) => {
  const ms = members || [];
  if (!ms.length) return "";
  const first = fmt(at(ms[ms.length - 1])), last = fmt(at(ms[0]));
  return first === last ? last : `${first} – ${last}`;
};
