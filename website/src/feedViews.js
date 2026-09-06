const ALL = Object.freeze({ key: "", label: "all" });
const UNREAD = Object.freeze({ key: "unread", label: "unread" });

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
