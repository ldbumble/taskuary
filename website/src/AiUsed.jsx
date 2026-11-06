// "AI used ▸" - shut until pressed (aiUsed.js). Opened, it reads the task's calls once and lists them. `pop`: in the task header's popover
// (TaskPage HeadPop, the owner 2026-11-06: "not at the bottom of the chat") - open from the start, its heading the list's own
import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api.js";
import { fmtDateTime } from "./dates.js";
import { usedLine, usedTotal } from "./aiUsed.js";
import { DIM, FAINT, INK } from "./theme.jsx";

export default function AiUsed({ taskId, pop = false }) {
  const [open, setOpen] = useState(pop), [got, setGot] = useState(null);
  useEffect(() => { setOpen(pop); setGot(null); }, [taskId, pop]);
  useEffect(() => {
    if (!open || got || !taskId) return;
    let live = true;
    api.get(`/api/tasks/${taskId}/ai-used`).then((r) => live && setGot(r.data || { rows: [] })).catch(() => live && setGot({ rows: [], failed: true }));
    return () => { live = false; };
  }, [open, got, taskId]);
  if (!taskId) return null;
  const flip = () => setOpen(!open), rows = got?.rows || [];
  return (
    <Box data-tq-ai-used={open ? "open" : "shut"} sx={{ mt: pop ? 0 : 1.25 }}>
      {pop ? <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>AI used{got && usedTotal(got.total) ? ` · ${usedTotal(got.total)}` : ""}</Typography>
      : <Typography role="button" tabIndex={0} aria-expanded={open} onClick={flip} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), flip())}
        sx={{ fontSize: 11.5, color: FAINT, cursor: "pointer", display: "inline-block", "&:hover": { color: INK } }}>
        AI used {open ? "▾" : "▸"}{open && got && usedTotal(got.total) ? ` · ${usedTotal(got.total)}` : ""}</Typography>}
      {open && <Box sx={{ mt: 0.4, maxHeight: "30vh", overflowY: "auto" }}>
        {!got ? <Typography sx={{ fontSize: 12, color: FAINT }}>Reading…</Typography>
          : !rows.length ? <Typography sx={{ fontSize: 12, color: FAINT }}>{got.failed ? "Could not read it just now." : "No AI has run on this task yet."}</Typography>
          : rows.map((r) => (
            <Box key={r.id} data-tq-ai-call={r.id} sx={{ display: "flex", gap: 1, fontSize: 12, lineHeight: 1.6, minWidth: 0 }}>
              <Box component="span" sx={{ color: FAINT, flexShrink: 0 }}>{fmtDateTime(r.at)}</Box>
              <Box component="span" title={usedLine(r)} sx={{ color: DIM, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{usedLine(r)}</Box>
            </Box>))}
      </Box>}
    </Box>);
}
