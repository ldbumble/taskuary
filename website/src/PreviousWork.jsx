import React, { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { onLive } from "./live.js";

// UNFINISHED WORK, as a label along the bottom of the pane rather than a shelf at the top of it.
// Four saved recaps at full height filled the whole window and pushed "Walk me through my tasks" -
// the one thing this page is for - below the fold, where it only appeared after a scroll (the owner,
// 2026-09-17: "you can't see the walk me through tasks??? ... show them in bottom label like open
// tasks not as notification but main window should be walk me through it"). It is shut by default,
// opens upward into a capped list, and wears none of the by-the-way strip's urgency: nothing here
// is new, it is work you already know about, waiting where you left it.
export default function PreviousWork({ active = true, initiallyOpen = false, onOpenTask, onReview }) {
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
  const ref = (id) => `TQ-${String(id).padStart(4, "0")}`;
  return <Box component="section" aria-label="Continue previous work" className="tq-prev">
    {/* shut, the label says WHICH tasks are waiting, not just how many: a count alone is a number to
        act on blind, and the refs are what the owner reads a task by everywhere else */}
    <button type="button" className="tq-prev-bar" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
      <b>Continue previous work ({items.length})</b>
      <span className="refs">{items.slice(0, 3).map((i) => ref(i.taskId)).join(" · ")}{items.length > 3 ? ` +${items.length - 3}` : ""}</span>
      <span className="caret" aria-hidden>{expanded ? "⌄" : "⌃"}</span>
    </button>
    {expanded && <div className="tq-prev-list">
      <Typography sx={{ fontSize: 12, color: "text.secondary", mb: 1 }}>Pick up an unfinished task or review a result that is ready.</Typography>
      {items.map((item) => <Box key={item.taskId} sx={{ p: 1.5, mb: 1, border: "1px solid #e1dcd5", borderRadius: 2, bgcolor: "#fffdfb" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{item.title}</Typography>
          <Button size="small" variant="outlined" disabled={busy !== null}
            onClick={() => item.action === "review" ? onReview(item.reviewId) : resume(item)}
            startIcon={busy === item.taskId ? <CircularProgress size={14} /> : undefined}>
            {busy === item.taskId ? "Continuing…" : item.action === "review" ? "Review draft" : "Continue"}
          </Button>
        </Box>
        <Typography sx={{ fontSize: 12, color: "text.secondary", mt: 0.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{item.recap}</Typography>
        <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.75 }}>{ref(item.taskId)} · Last worked {(item.lastWorkedAt || "").slice(0, 16)}</Typography>
      </Box>)}
      {error && <Alert severity="error">{error}</Alert>}
    </div>}
  </Box>;
}
