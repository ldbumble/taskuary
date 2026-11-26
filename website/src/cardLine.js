// A RUN OF CARDS IS ONE CARD WITH TABS (taskuary/cardqueue.py tabs; the owner, 2026-11-25: "we write 1 of 3 anyway so a little carousel thing on
// top that scrolls from one to the other is fine"). `tabs`: [{key, rids, name, done, front}], the run's cards oldest first, as the server reads it.

// ...which tab it shows: THE ONE HE IS ON, AND A PRESS NEVER CHANGES IT (the owner, 2026-11-26: he approved one tab of two, the card slid on to
// the other and what he had just approved "disappeared" - "cards or anything generated on chat never go away"). The pressed tab stays in view
// saying what its press did; he moves by the arrows or a tab's name. `shown`: the key of the tab it shows - until it shows one, the card in
// front, else the first that waits, else the last
export const lineAt = (tabs, shown = null) => {
  const i = shown == null ? -1 : tabs.findIndex((t) => t.key === shown);
  if (i >= 0) return i;
  const f = tabs.findIndex((t) => t.front);
  if (f >= 0) return f;
  const w = tabs.findIndex((t) => !t.done);
  return w >= 0 ? w : Math.max(0, tabs.length - 1);
};
// ...kept by the card's own key for as long as the page is open: the card set down under a later turn (chatStream.waitsLast) is drawn anew there,
// and still shows the tab he was on
const SHOWN = new Map();
export const shownTab = (tabs, pick) => {
  const k = tabs[0]?.key;
  if (pick !== undefined) SHOWN.set(k, pick);
  else if (!SHOWN.has(k) || !tabs.some((t) => t.key === SHOWN.get(k))) SHOWN.set(k, tabs[lineAt(tabs)]?.key ?? null);
  return SHOWN.get(k);
};

// ...and the arrows beside "1 of 3" (the owner, 2026-11-26: "i should be able to click next if there are 3 in one card" - he pressed Dismiss on
// two cards to reach the third): the tab before or after the one shown, round the ends - the arrow keys' step too. The only way the card shown changes
export const lineStep = (tabs, at, d) => (tabs.length ? (at + d + tabs.length) % tabs.length : 0);

// ...and where the one card stands: at the row of the card in front, else at the newest of its cards the chat's log has a row for (`rowed`:
// review ids, as strings) - one held behind the front has none yet. A run with no row drawn is not drawn either, as its cards were not
const rowOf = (tabs, rowed) => tabs.find((t) => t.front && rowed.has(String(t.rids[0]))) || [...tabs].reverse().find((t) => rowed.has(String(t.rids[0])));
export const lineRuns = (runs, rowed) => (runs || []).map((tabs) => ({ tabs, at: rowOf(tabs, rowed)?.key })).filter((r) => r.at && r.tabs.length > 1);

// ...AND A RUN OF ONE CARD IS A LATER RUN'S FRONT (cardqueue.tabs serves no other run of one): raised after a line of his while an older card
// still waits above that line, it is the card it is at its own row under the line - no tabs, and never a tab of the card above (walk 24)
export const standsAlone = (runs) => new Set((runs || []).filter((tabs) => tabs.length === 1).map((tabs) => tabs[0].key));
