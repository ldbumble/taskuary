// How Taskuary works: a short, replayable walkthrough of the pages a new owner actually uses.
//
// Not the setup wizard (that CONNECTS things) and not the Assistant's "walk me through my
// tasks" (that walks YOUR mail). This one names the rooms. The copy is the product: one idea
// per step, no jargon, nothing that needs a brain or a mailbox to make sense.

export const TOUR_KEY = "tq.tour";
export const TOUR_EVENT = "tq-tour";
export const TOUR_HASH = "tour";

export const TOUR_STEPS = [
  {
    id: "welcome",
    tab: "Assistant",
    target: null,
    kicker: "How Taskuary works",
    title: "Your work, in one place",
    body: "Mail, chats, and tasks land here. AI sorts them. Agents do the work. Nothing leaves until you say so.",
  },
  {
    id: "assistant",
    tab: "Assistant",
    target: "tab-Assistant",
    kicker: "The front door",
    title: "Start here",
    body: "The Assistant walks you through what needs you, one thing at a time. The other tabs are where you go to see the whole of something.",
  },
  {
    id: "pipe",
    tab: "Assistant",
    target: "pipe",
    kicker: "What needs you",
    title: "Ranked, not piled",
    body: "The list on the left is ordered by importance, not by when it arrived. The chat on the right explains the next item. The buttons under it take the action.",
  },
  {
    id: "review",
    tab: "Review",
    target: "review",
    kicker: "Outbound",
    title: "Nothing sends without you",
    body: "Replies wait here until you approve, edit, or dismiss them. Taskuary never sends on its own.",
  },
  {
    id: "board",
    tab: "Board",
    target: "board",
    kicker: "Agents",
    title: "Watch the work",
    body: "Tasks move from Queued to Working to Done. Open a card to see the live session. If an agent needs you, it raises a hand.",
  },
  {
    id: "connections",
    tab: "Connections",
    target: "connections",
    kicker: "Your tools",
    title: "Bring work in",
    body: "Connect a mailbox or a chat so work can arrive, and an AI so it can be sorted. A coding CLI can wait until you have code to do.",
  },
  {
    id: "done",
    tab: "Assistant",
    target: null,
    kicker: "That's it",
    title: "The whole idea",
    body: "Work in. Sorted. Worked. You approve. Replay this anytime from the question mark in the top bar.",
  },
];

const memoryStorage = () => {
  const data = {};
  return {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
};

export const defaultTourStorage = () => {
  try { return typeof localStorage === "undefined" ? memoryStorage() : localStorage; }
  catch { return memoryStorage(); }
};

export const tourStatus = (storage = defaultTourStorage()) => {
  try { return storage.getItem(TOUR_KEY) || ""; } catch { return ""; }
};

export const tourSeen = (storage = defaultTourStorage()) => {
  const s = tourStatus(storage);
  return s === "done" || s === "skipped";
};

export const rememberTour = (status, storage = defaultTourStorage()) => {
  try { storage.setItem(TOUR_KEY, status); } catch { /* private mode */ }
};

export const requestTour = () => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(TOUR_EVENT));
};

// A first visit should see the rooms once the setup panel is out of the way. Demo has no
// setup, so it offers immediately. A live install that is already ready (or was put away)
// is the other case: the walkthrough is new, and those people have never been shown it.
export const shouldOfferTour = ({ seen, demo, setupOpen, setupReady, setupDismissed, setupKnown }) => {
  if (seen) return false;
  if (setupOpen) return false;
  if (demo) return true;
  if (setupKnown === false) return false;
  return Boolean(setupReady || setupDismissed);
};

export const hashWantsTour = (hash) => /(^|#)tour(?:&|$)/.test(String(hash || "").replace(/^#/, "#"));

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

export const visibleRect = (el) => {
  if (!el || typeof el.getBoundingClientRect !== "function") return null;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height, bottom: r.bottom, right: r.right };
};

export const holeFor = (target, pad = 8, radius = 12) => {
  if (!target) return null;
  return {
    top: Math.max(0, target.top - pad),
    left: Math.max(0, target.left - pad),
    width: target.width + pad * 2,
    height: target.height + pad * 2,
    radius,
  };
};

// Four rectangles around the spotlight, so the dim captures clicks and the hole does not
// have to fake a mask. No hole → one full-screen dim.
export const dimRects = (hole, vw, vh) => {
  if (!hole) return [{ top: 0, left: 0, width: vw, height: vh }];
  const { top, left, width, height } = hole;
  return [
    { top: 0, left: 0, width: vw, height: top },
    { top: top + height, left: 0, width: vw, height: Math.max(0, vh - top - height) },
    { top, left: 0, width: left, height },
    { top, left: left + width, width: Math.max(0, vw - left - width), height },
  ].filter((r) => r.width > 0 && r.height > 0);
};

export const placeCard = ({ target, cardW, cardH, vw, vh, gap = 16, pad = 16 }) => {
  const center = () => ({
    top: Math.max(pad, (vh - cardH) / 2),
    left: Math.max(pad, (vw - cardW) / 2),
  });
  if (!target) return center();
  const left = clamp(target.left, pad, Math.max(pad, vw - cardW - pad));
  const below = target.bottom + gap;
  if (below + cardH + pad <= vh) return { top: below, left };
  const above = target.top - gap - cardH;
  if (above >= pad) return { top: above, left };
  const right = target.right + gap;
  if (right + cardW + pad <= vw) {
    return { top: clamp(target.top, pad, Math.max(pad, vh - cardH - pad)), left: right };
  }
  const leftSide = target.left - gap - cardW;
  if (leftSide >= pad) {
    return { top: clamp(target.top, pad, Math.max(pad, vh - cardH - pad)), left: leftSide };
  }
  return center();
};
