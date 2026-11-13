import { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { FAINT, INK } from "./theme.jsx";
import api from "./api";
import { press } from "./press.js";
import { bulkSendable, slotReviews } from "./taskLifecycle.js";

// The task's emails still waiting for Send (slots.py), each its own card with its own Send. One that went is its SentCard in its turn
// (TaskPage turnCards), as a reply is; a dropped one is its line in the chat. A name with no address yet wears a "?" - never guessed into one.
export default function SlotList({ taskId, checklist = [], reviews = [], onChanged }) {
  const [busy, setBusy] = useState(false);
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  // ...ONLY AN EMAIL SOMEBODY WROTE (the owner, 2026-11-10: "it created reply with nothing in it ... action is only needed if it helps user")
  const items = (checklist || []).filter((i) => i.out && !i.done && byRid[i.rid]?.Status === "pending");
  if (!items.length) return null;
  const waiting = bulkSendable(items, reviews);
  // letting one email go - its draft (if any) is never sent; the task stays open
  const drop = async (i) => {
    setBusy(true);
    try { await api.patch(`/api/tasks/${taskId}/checklist/${i.id}`, { done: true }); } catch { /* the card reloads either way */ }
    finally { setBusy(false); onChanged?.(); }
  };
  // one press, the same decide each card's own Approve sends - a refused one stays pending on its card
  const approveAll = async () => {
    setBusy(true);
    try { for (const r of waiting) await press(api, r.ReviewId, { verb: "approve", cc: null }); }
    finally { setBusy(false); onChanged?.(); }
  };
  return (
    <Box sx={{ mt: 1.5, maxWidth: 900 }}>
      {waiting.length > 1 && <Box sx={{ mb: 0.6 }}><Button size="small" disabled={busy} onClick={approveAll}>{busy ? "Sending…" : `Approve all (${waiting.length})`}</Button></Box>}
      {items.map((i) => {
        const rv = byRid[i.rid];
        return (
          <Box key={i.id} sx={{ mb: 1 }}>
            {(i.out.name || i.out.candidates?.length) && <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8 }}>
              {i.out.name && <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{i.out.name}</Typography>}
              {!!i.out.candidates?.length && <Typography variant="caption" sx={{ color: FAINT }}>{`could be ${i.out.candidates.slice(0, 3).join(" or ")}`}</Typography>}
            </Box>}
            <ReviewDecision review={rv} onChanged={onChanged} onDrop={() => drop(i)} />
          </Box>
        );
      })}
    </Box>
  );
}
