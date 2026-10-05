import { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { ACCENT2, BORDER, FAINT, INK } from "./theme.jsx";
import api from "./api";
import { bulkSendable, slotReviews, slotState } from "./taskLifecycle.js";

// The emails that close this task (slots.py, spec 2026-10-05): each one with its own draft, approved on its own; the task
// closes when the last is sent or dropped. A name with no address yet wears a "?" - it is never guessed into one.
export default function SlotList({ taskId, checklist = [], reviews = [], onChanged }) {
  const [busy, setBusy] = useState(false);
  const items = (checklist || []).filter((i) => i.out);
  if (!items.length) return null;
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  const waiting = bulkSendable(items, reviews);
  // letting one email go - its draft (if any) is never sent, and the task closes when nothing else is owed
  const drop = async (i) => {
    setBusy(true);
    try { await api.patch(`/api/tasks/${taskId}/checklist/${i.id}`, { done: true }); } catch { /* the card reloads either way */ }
    finally { setBusy(false); onChanged?.(); }
  };
  // one press, the same decide each card's own Approve sends - a refused one stays pending on its card
  const approveAll = async () => {
    setBusy(true);
    try { for (const r of waiting) await api.post(`/api/reviews/${r.ReviewId}/decide`, { verb: "approve", final_text: null, note: null, cc: null }).catch(() => null); }
    finally { setBusy(false); onChanged?.(); }
  };
  return (
    <Box sx={{ mt: 1.2, pt: 1, borderTop: `1px solid ${BORDER}`, maxWidth: 900 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.6 }}>
        <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.25, fontSize: 9, fontWeight: 750 }}>
          {`Closes when sent · ${items.filter((i) => i.done).length} of ${items.length}`}
        </Typography>
        {waiting.length > 1 && <Button size="small" disabled={busy} onClick={approveAll}>{busy ? "Sending…" : `Approve all (${waiting.length})`}</Button>}
      </Box>
      {items.map((i) => {
        const rv = byRid[i.rid];
        const named = String(i.out.to || "");
        return (
          <Box key={i.id} sx={{ mb: 1 }}>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8 }}>
              <Typography variant="body2" sx={{ color: i.done ? FAINT : INK, fontWeight: 600 }}>{named}{named.includes("@") ? "" : " ?"}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{slotState(i, rv)}{i.out.by === "agent" ? " · added by the agent" : ""}
                {i.out.candidates?.length ? ` · could be ${i.out.candidates.slice(0, 3).join(" or ")}` : ""}</Typography>
              {!i.done && rv?.Status !== "pending" && <Button size="small" disabled={busy} onClick={() => drop(i)}>Drop</Button>}
            </Box>
            {rv?.Status === "pending" && <ReviewDecision review={rv} onChanged={onChanged} onDrop={() => drop(i)} />}
          </Box>
        );
      })}
    </Box>
  );
}
