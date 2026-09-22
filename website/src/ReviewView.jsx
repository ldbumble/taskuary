// The review queue: the filter pills and the list. The DECISION itself is ReviewDecision.jsx,
// which the task page mounts too - the queue is one place it can be shown, not the only one.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Chip, CircularProgress, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import ReviewDecision from "./ReviewDecision.jsx";
import { onLive } from "./live.js";
import { proposalPresentation, reviewStatusLabel } from "./reviewProposal.js";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, RefChip, timeAgo, Empty, FilterPills } from "./ui.jsx";
import { deliveryMeta, replyContext } from "./replyDelivery.js";

const FILTERS = [
  { key: "pending", label: "pending", c: PILL_COLORS.you },
  { key: "held", label: "waiting on the agent", c: PILL_COLORS.teal },
  { key: "auto", label: "auto-handled", c: PILL_COLORS.teal },
  { key: "approved", label: "approved", c: PILL_COLORS.green }, { key: "edited", label: "edited" },
  { key: "no_reply", label: "no reply", c: PILL_COLORS.gray }, { key: "rejected", label: "rejected", c: PILL_COLORS.bad },
  { key: "", label: "all" },
];

export default function ReviewView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setRows((await api.get("/api/reviews", { params: filter ? { status: filter } : {} })).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load reviews"); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  // ...and again when the queue CHANGES under you. A review is poked as feed-changed/task-changed
  // (store._poke_review), but this tab never listened: a draft an agent filed while you sat here
  // stayed invisible until the header's refresh icon remounted the whole page (2026-09-10 audit).
  useEffect(() => onLive(["feed-changed", "task-changed"], load, { wait: 250, max: 1500 }), [load]);

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Box sx={{ ...card, px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <FilterPills options={FILTERS} value={filter} onChange={setFilter} />
        <Box sx={{ flex: 1 }} />
        {rows && <Typography variant="caption" sx={{ color: FAINT }}>{rows.length} shown</Typography>}
      </Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mt: 1.5 }}>{err}</Alert>}
      {!rows ? <CircularProgress size={22} sx={{ m: 4 }} /> : !rows.length ? (
        <Empty>{filter === "pending" ? "Queue is clear — nothing needs you."
          : filter === "held" ? "Nothing is waiting on an agent."
          : "Nothing here."}</Empty>
      ) : rows.map((r) => {
        const proposal = proposalPresentation(r);
        return (
        <Box key={r.ReviewId} sx={{ ...card, mt: 1.25, p: 0, overflow: "hidden" }}>
          {/* header strip: what kind of decision this is + who/what it's about */}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", px: 1.5, py: 1,
            bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}` }}>
            <Box sx={{ width: 28, height: 28, borderRadius: 1.5, flexShrink: 0, display: "flex",
              alignItems: "center", justifyContent: "center",
              bgcolor: "#e3e6e1" }}>
              <AutoAwesomeIcon sx={{ fontSize: 15, color: "#6f8a6e" }} />
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: INK, fontWeight: 700, lineHeight: 1.25 }} noWrap>
                {proposal?.title || r.Subject || r.Title || "(no subject)"}
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
                {proposal ? proposal.context
                  : deliveryMeta(r).kind === "zoho_invoice" ? `Zoho invoice · ${deliveryMeta(r).period}`
                  : r.Status === "held" ? "Reply on hold" : r.Kind === "auto" ? "Auto-answered" : "Draft reply"}
                {!proposal && <> · To {replyContext(r)}</>} · {timeAgo(r.CreatedAt)}
              </Typography>
            </Box>
            <ChannelIcon channel={r.Channel} />
            <RefChip taskId={r.TaskId} onClick={() => onOpenTask(r.TaskId)} />
            <Chip size="small" label={reviewStatusLabel(r.Status)} sx={{ height: 19, fontSize: 10, bgcolor: PANEL, border: `1px solid ${BORDER}`, color: DIM }} />
          </Box>
          <Box sx={{ px: 1.5, py: 1.25 }}>
            <ReviewDecision review={r} onOpenTask={onOpenTask}
              onChanged={() => { load(); onChanged?.(); }} />
          </Box>
        </Box>
        );
      })}
    </Box>
  );
}
