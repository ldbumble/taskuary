import { Box, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { FAINT, INK } from "./theme.jsx";
import api from "./api";
import { slotReviews } from "./taskLifecycle.js";

// The task's emails still waiting for Send (slots.py), each its own card with its own Send. A name with no address yet wears a "?" - never guessed
// into one; a dropped one is its line in the chat.
// ...ONLY AN EMAIL SOMEBODY WROTE (the owner, 2026-11-10: "it created reply with nothing in it ... action is only needed if it helps user")
export const letterItems = (checklist = [], reviews = []) => {
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  return (checklist || []).filter((i) => i.out && !i.done && byRid[i.rid]?.Status === "pending").map((i) => ({ item: i, rv: byRid[i.rid] }));
};
// ONE EMAIL IS ONE NODE, FROM ITS DRAFT TO ITS SENT (the walk, 2026-11-17): where a chat has turns it is drawn in its turn by its review
// (TaskPage turnCards, `rv:<id>`) and its card turns Sent in place (ReviewDecision); over a to-do's box, which has none, the list below holds it
export function Letter({ taskId, item = null, rv, onChanged, went = null }) {
  // letting one email go - its draft (if any) is never sent; the task stays open
  const drop = async () => {
    try { await api.patch(`/api/tasks/${taskId}/checklist/${item.id}`, { done: true }); } catch { /* the card reloads either way */ }
    finally { onChanged?.(); }
  };
  const out = item?.out || {};
  return (
    <Box sx={{ mb: 1 }}>
      {(out.name || out.candidates?.length) && <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8 }}>
        {out.name && <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{out.name}</Typography>}
        {!!out.candidates?.length && <Typography variant="caption" sx={{ color: FAINT }}>{`could be ${out.candidates.slice(0, 3).join(" or ")}`}</Typography>}
      </Box>}
      <ReviewDecision review={rv} onChanged={onChanged} onDrop={item ? drop : null} went={went} />
    </Box>
  );
}
export default function SlotList({ taskId, checklist = [], reviews = [], onChanged }) {
  const items = letterItems(checklist, reviews);
  return !items.length ? null : <Box sx={{ mt: 1.5, maxWidth: 900 }}>{items.map(({ item, rv }) => <Letter key={item.id} taskId={taskId} item={item} rv={rv} onChanged={onChanged} />)}</Box>;
}
