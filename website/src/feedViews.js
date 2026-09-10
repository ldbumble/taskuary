// What each view is FOR, in its own word. "unread / all" described a mail state and said nothing
// about the point of either: one is the ranked run through what matters, taken one item at a time;
// the other is the whole history in order (the owner, 2026-09-07: "rename the all vs unread as
// timeline vs work as thats the goal of the unread tab to go through important stuff one by one").
// The KEYS are unchanged - they are the wire and the hash, not the label.
const ALL = Object.freeze({ key: "", label: "timeline" });
const UNREAD = Object.freeze({ key: "unread", label: "work" });

// The Assistant owns the Unread pipe. A standalone Timeline can still render its All list,
// but it must not invent another state filter.
export const feedViews = (hasUnread) => (hasUnread ? [UNREAD, ALL] : [ALL]);

// Keep the interaction boundary independent from the row renderer: All always opens detail.
// Only an Unread chat rail may pull a row into the Assistant conversation.
export const feedInteraction = (view, rowMode, hasPull) => {
  const unread = view === "unread";
  return {
    unread,
    showChatStage: unread,
    pullRowIntoChat: unread && rowMode === "chat" && !!hasPull,
  };
};
