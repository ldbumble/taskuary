// A RUN OF CARDS IS ONE CARD WITH TABS (taskuary/cardqueue.py tabs; the owner, 2026-11-25: "we write 1 of 3 anyway so a little carousel thing on
// top that scrolls from one to the other is fine"). `tabs`: [{key, rids, name, done, front}], the run's cards oldest first, as the server reads it.

// ...which tab it shows: the one he picked while it is his to look at (a settled one he opened stays; one that waits stays until it is
// settled), else the next that waits after it, else the one in front, else the first that waits - and once none waits, the one it shows
// (`at`: the last he pressed stays, saying what it did), else the last
export const lineAt = (tabs, pick = null, at = -1) => {
  const i = pick ? tabs.findIndex((t) => t.key === pick.key) : -1;
  if (i >= 0 && (pick.done || !tabs[i].done)) return i;
  const next = i >= 0 ? tabs.findIndex((t, j) => j > i && !t.done) : -1;
  if (next >= 0) return next;
  const f = tabs.findIndex((t) => t.front);
  if (f >= 0) return f;
  const w = tabs.findIndex((t) => !t.done);
  return w >= 0 ? w : at >= 0 && at < tabs.length ? at : Math.max(0, tabs.length - 1);
};

// ...and where the one card stands: at the row of the card in front, else at the newest of its cards the chat's log has a row for (`rowed`:
// review ids, as strings) - one held behind the front has none yet. A run with no row drawn is not drawn either, as its cards were not
const rowOf = (tabs, rowed) => tabs.find((t) => t.front && rowed.has(String(t.rids[0]))) || [...tabs].reverse().find((t) => rowed.has(String(t.rids[0])));
export const lineRuns = (runs, rowed) => (runs || []).map((tabs) => ({ tabs, at: rowOf(tabs, rowed)?.key })).filter((r) => r.at && r.tabs.length > 1);

// ...AND A RUN OF ONE CARD IS A LATER RUN'S FRONT (cardqueue.tabs serves no other run of one): raised after a line of his while an older card
// still waits above that line, it is the card it is at its own row under the line - no tabs, and never a tab of the card above (walk 24)
export const standsAlone = (runs) => new Set((runs || []).filter((tabs) => tabs.length === 1).map((tabs) => tabs[0].key));
