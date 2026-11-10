import { useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import { ACCENT2, BORDER, FAINT, INK, label } from "./theme.jsx";
import api from "./api";
import { press } from "./press.js";
import { bulkSendable, slotReviews, slotState, slotTally } from "./taskLifecycle.js";

// The emails that close this task (slots.py, spec 2026-10-05): each one with its own draft, approved on its own; the task
// closes when the last is sent or dropped. A name with no address yet wears a "?" - it is never guessed into one.
export default function SlotList({ taskId, checklist = [], reviews = [], onChanged }) {
  const [busy, setBusy] = useState(false);
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  // ...ONLY AN EMAIL SOMEBODY WROTE (the owner, 2026-11-10: "it created reply with nothing in it ... action is only needed if it helps user"): a
  // recipient with no draft is no card, and a "To <them> · to draft" row under a turn read as the turn's empty answer
  const items = (checklist || []).filter((i) => i.out && (i.done || byRid[i.rid]?.Status === "pending"));
  if (!items.length) return null;
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
    try { for (const r of waiting) await press(api, r.ReviewId, { verb: "approve", cc: null }); }
    finally { setBusy(false); onChanged?.(); }
  };
  return (
    <Box sx={{ mt: 1.5, maxWidth: 900 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.6 }}>
        <Typography sx={{ ...label }}>
          {`Closes when sent · ${slotTally(items, reviews)}`}
        </Typography>
        {waiting.length > 1 && <Button size="small" disabled={busy} onClick={approveAll}>{busy ? "Sending…" : `Approve all (${waiting.length})`}</Button>}
      </Box>
      {items.map((i) => {
        const rv = byRid[i.rid];
        const named = String(i.out.to || "");
        // ...a drafted EMAIL's To is its card's own row, with its Change - said here as well it read twice (agent-flow audit, 2026-11-07)
        const carded = rv?.Status === "pending" && (i.out.kind || "email") === "email";
        return (
          <Box key={i.id} sx={{ mb: 1 }}>
            {/* ...each wears its OWN To, drafted or not (the owner, 2026-11-02): the sender's To under it read as this email's */}
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8 }}>
              {carded ? i.out.name && <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{i.out.name}</Typography> : <>
              <Typography sx={{ ...label, flexShrink: 0 }} data-tq-slot-to={i.id}>To</Typography>
              <Typography variant="body2" sx={{ color: i.done ? FAINT : INK, fontWeight: 600 }}>{(i.out.kind || "email") === "email"
                ? <>{i.out.name ? `${i.out.name} · ` : ""}{named}{named.includes("@") ? "" : " ?"}</>
                : `${i.out.name || named} · ${i.out.kind}`}</Typography></>}
              <Typography variant="caption" sx={{ color: FAINT }}>{slotState(i, rv)}{i.out.by === "agent" ? " · added by the agent" : ""}
                {i.out.candidates?.length ? ` · could be ${i.out.candidates.slice(0, 3).join(" or ")}` : ""}</Typography>
            </Box>
            {rv?.Status === "pending" && <ReviewDecision review={rv} onChanged={onChanged} onDrop={() => drop(i)} />}
          </Box>
        );
      })}
    </Box>
  );
}
