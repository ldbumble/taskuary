import React, { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { onLive } from "./live.js";

export default function PreviousWork({ active = true, initiallyOpen = true, onOpenTask, onReview }) {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(initiallyOpen);
  const flight = useRef(false);
  useEffect(() => {
    if (!active) return undefined;
    let live = true, loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try { const { data } = await api.get("/api/assistant/previous-work"); if (live) setItems(data.data || []); }
      catch { /* The welcome page remains usable if this optional shelf cannot load. */ }
      finally { loading = false; }
    };
    load();
    const off = onLive(["task-changed", "feed-changed"], load, { wait: 1500, max: 5000 });
    return () => { live = false; off(); };
  }, [active]);

  const resume = async (item) => {
    if (flight.current) return;
    flight.current = true; setBusy(item.taskId); setError("");
    try {
      const { data } = await api.post(`/api/tasks/${item.taskId}/resume`);
      if (data.action === "review") onReview(data.reviewId);
      else onOpenTask(data.taskId);
    } catch (e) { setError(e?.response?.data?.detail || "Could not resume this task. Please try again."); }
    finally { flight.current = false; setBusy(null); }
  };

  if (!items.length) return null;
  return <Box component="section" aria-label="Continue previous work" sx={{ mt: 2, mb: 3, width: "100%", textAlign: "left" }}>
    <Button onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}
      sx={{ fontSize: 14, fontWeight: 700, mb: 0.5, px: 0, textTransform: "none" }}>Continue previous work ({items.length})</Button>
    {expanded && <>
    <Typography sx={{ fontSize: 12, color: "text.secondary", mb: 1 }}>Pick up an unfinished task or review a result that is ready.</Typography>
    {items.map((item) => <Box key={item.taskId} sx={{ p: 1.5, mb: 1, border: "1px solid #e1dcd5", borderRadius: 2, bgcolor: "#fffdfb" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{item.title}</Typography>
        <Button size="small" variant="outlined" disabled={busy !== null}
          onClick={() => item.action === "review" ? onReview(item.reviewId) : resume(item)}
          startIcon={busy === item.taskId ? <CircularProgress size={14} /> : undefined}>
          {busy === item.taskId ? "Resuming…" : item.action === "review" ? "Review draft" : "Resume"}
        </Button>
      </Box>
      <Typography sx={{ fontSize: 12, color: "text.secondary", mt: 0.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
        display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{item.recap}</Typography>
      <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.75 }}>TQ-{String(item.taskId).padStart(4, "0")} · Last worked {(item.lastWorkedAt || "").slice(0, 16)}</Typography>
    </Box>)}
    {error && <Alert severity="error">{error}</Alert>}
    </>}
  </Box>;
}
