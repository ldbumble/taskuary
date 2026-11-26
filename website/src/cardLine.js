// A SET RAISED IN ONE CALL IS ONE CARD WITH A TAB EACH (taskuary/cardqueue.py sets; the owner, 2026-11-26: the same post for X, Reddit and
// LinkedIn is one card with tabs - a routine change and a post are two cards, never tabs of one). `tabs`: [{key, name, done, no, front}], in
// the order they were raised.

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
