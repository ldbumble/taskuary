// Review queue: decide without leaving the row - inbound message on the left, the agent's
// draft on the right, verdict buttons underneath. Escalations carry no draft by design.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, RefChip, timeAgo, Empty, FilterPills } from "./ui.jsx";

const FILTERS = [
  { key: "pending", label: "pending", c: PILL_COLORS.amber }, { key: "auto", label: "auto-handled", c: PILL_COLORS.teal },
  { key: "approved", label: "approved", c: PILL_COLORS.green }, { key: "edited", label: "edited" },
  { key: "no_reply", label: "no reply", c: PILL_COLORS.gray }, { key: "rejected", label: "rejected", c: PILL_COLORS.red },
  { key: "", label: "all" },
];

export default function ReviewView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setRows((await api.get("/api/reviews", { params: filter ? { status: filter } : {} })).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load reviews"); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const decide = async (r, verb) => {
    setBusy(r.ReviewId);
    try {
      await api.post(`/api/reviews/${r.ReviewId}/decide`, { verb, final_text: verb === "edit" ? edits[r.ReviewId] : null,
        note: verb === "go_ahead" ? (edits[r.ReviewId] || "").trim() || null : null });
      load(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
    setBusy(null);
  };

  const redraft = async (r) => {
    setBusy(r.ReviewId);
    try { await api.post(`/api/reviews/${r.ReviewId}/draft`); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "Redraft failed"); }
    setBusy(null);
  };

  return (
    <Box sx={{ maxWidth: 980 }}>
      <Box sx={{ ...card, px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <FilterPills options={FILTERS} value={filter} onChange={setFilter} />
        <Box sx={{ flex: 1 }} />
        {rows && <Typography variant="caption" sx={{ color: FAINT }}>{rows.length} shown</Typography>}
      </Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mt: 1.5 }}>{err}</Alert>}
      {!rows ? <CircularProgress size={22} sx={{ m: 4 }} /> : !rows.length ? (
        <Empty>{filter === "pending" ? "Queue is clear — nothing needs you." : "Nothing here."}</Empty>
      ) : rows.map((r) => (
        <Box key={r.ReviewId} sx={{ ...card, mt: 1.25, p: 0, overflow: "hidden" }}>
          {/* header strip: what kind of decision this is + who/what it's about */}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", px: 1.5, py: 1,
            bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}` }}>
            <Box sx={{ width: 28, height: 28, borderRadius: 1.5, flexShrink: 0, display: "flex",
              alignItems: "center", justifyContent: "center",
              bgcolor: r.Kind === "escalation" ? "#fdecec" : "#e6f7fb" }}>
              {r.Kind === "escalation"
                ? <ReportProblemIcon sx={{ fontSize: 15, color: "#b91c1c" }} />
                : <AutoAwesomeIcon sx={{ fontSize: 15, color: "#0e7490" }} />}
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: INK, fontWeight: 700, lineHeight: 1.25 }} noWrap>
                {r.Subject || r.Title || "(no subject)"}
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
                {r.Kind === "escalation" ? "Escalation" : r.Kind === "auto" ? "Auto-answered" : "Draft reply"} · {r.FromEmail} · {timeAgo(r.CreatedAt)}
              </Typography>
            </Box>
            <ChannelIcon channel={r.Channel} />
            <RefChip taskId={r.TaskId} onClick={() => onOpenTask(r.TaskId)} />
            <Chip size="small" label={r.Status} sx={{ height: 19, fontSize: 10, bgcolor: PANEL, border: `1px solid ${BORDER}`, color: DIM }} />
          </Box>
          <Box sx={{ px: 1.5, py: 1.25 }}>
            {r.Reason && <Typography variant="caption" sx={{ color: "#7e22ce", display: "block", mb: 0.5 }}>{r.Reason}</Typography>}

            {r.Status === "pending" && r.Kind !== "escalation" && (
              <Box sx={{ mt: 0.5 }}>
                <TextField fullWidth multiline minRows={2} maxRows={8}
                  value={edits[r.ReviewId] ?? (r.DraftText || "")}
                  onChange={(e) => setEdits({ ...edits, [r.ReviewId]: e.target.value })}
                  placeholder={r.DraftText ? "" : "No draft yet — hit Draft with AI"}
                  inputProps={{ style: { fontSize: 12.5, lineHeight: 1.45 } }} />
                <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
                  <Button size="small" variant="contained" disabled={busy === r.ReviewId || !r.DraftText}
                    onClick={() => decide(r, "approve")}>Approve</Button>
                  <Button size="small" variant="outlined"
                    disabled={busy === r.ReviewId || !(edits[r.ReviewId] || "").trim() || edits[r.ReviewId] === r.DraftText}
                    onClick={() => decide(r, "edit")}>Approve my edit</Button>
                  <Button size="small" sx={{ color: "#8a94a6" }} disabled={busy === r.ReviewId}
                    onClick={() => decide(r, "no_reply")}>No reply needed</Button>
                  <Button size="small" color="error" disabled={busy === r.ReviewId} onClick={() => decide(r, "reject")}>Reject</Button>
                  <Box sx={{ flex: 1 }} />
                  <Button size="small" disabled={busy === r.ReviewId} onClick={() => redraft(r)}>
                    {busy === r.ReviewId ? <CircularProgress size={12} /> : r.DraftText ? "Redraft" : "Draft with AI"}
                  </Button>
                </Box>
              </Box>
            )}
            {/* An escalation is one question: may the agent go on? Answer it here - either
                approve (and the same agent picks the task straight back up with your words)
                or take it yourself. */}
            {r.Status === "pending" && r.Kind === "escalation" && (
              <Box sx={{ mt: 0.75 }}>
                <TextField fullWidth size="small" placeholder="Anything to tell the agent with your approval (optional)"
                  value={edits[r.ReviewId] ?? ""} onChange={(e) => setEdits({ ...edits, [r.ReviewId]: e.target.value })}
                  inputProps={{ style: { fontSize: 12.5 } }} />
                <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
                  <Button size="small" variant="contained" disableElevation disabled={busy === r.ReviewId}
                    sx={{ bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                    onClick={() => decide(r, "go_ahead")}>Go ahead — approved</Button>
                  <Button size="small" variant="outlined" onClick={() => onOpenTask(r.TaskId)}>Open the task</Button>
                  <Box sx={{ flex: 1 }} />
                  <Button size="small" color="error" disabled={busy === r.ReviewId} onClick={() => decide(r, "reject")}>Dismiss — I handled it</Button>
                </Box>
              </Box>
            )}
            {r.Status !== "pending" && (r.FinalText || r.DraftText) && (
              <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block", mt: 0.75,
                bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1 }}>
                {(r.FinalText || r.DraftText).slice(0, 500)}
              </Typography>
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
