// MORE THAN ONE LETTER WAITING (2026-11-02): a task that joined a second person's thread can hold a reply to each - an agent's question
// to one requester and an answer to the other. Close out drew only the newest, and its "Answering" line named whoever wrote last, so a
// question to one person read as an answer to the other. Each pending reply is drawn on its own, with what it answers and its own Send.
const isReply = (r) => r && r.Kind !== "action" && r.Kind !== "slot" && r.Status === "pending";

// the pending replies other than the one Close out already draws (`shown`), oldest first
export const otherPendingReplies = (reviews = [], shown = null) =>
  reviews.filter((r) => isReply(r) && r.ReviewId !== shown?.ReviewId).sort((a, b) => (a.ReviewId || 0) - (b.ReviewId || 0));

// the task's message a pending reply answers - its own MessageId - or null when it is not one of them
export const draftAnswers = (review, messages = []) => (review?.MessageId && messages.find((m) => m.MessageId === review.MessageId)) || null;
