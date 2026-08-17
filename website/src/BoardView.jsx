// Board: the agent kanban - every task as a card in a status column. Some cards arrive
// from triage, some you start yourself; drag between columns to change status, click a
// card to open the task (where you can message the agent working it). House design.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, Checkbox, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, hoverable, mono } from "./theme.jsx";
import { ChannelIcon, ActionChip, timeAgo, Empty } from "./ui.jsx";

// Column model: where a card sits is derived from task status + its latest review.
const COLS = [
  { key: "queued", title: "Queued", dot: "#8a94a6", status: "open",
    match: (t) => t.Status === "open" && t.ReviewStatus !== "pending" },
  { key: "working", title: "Agent working", dot: "#0e7490", status: "in_progress",
    match: (t) => t.Status === "in_progress" && t.ReviewStatus !== "pending" },
  { key: "waiting", title: "Waiting on you", dot: "#b45309", status: "waiting",
    match: (t) => t.ReviewStatus === "pending" && !["done", "dropped"].includes(t.Status) },
  { key: "done", title: "Done", dot: "#15803d", status: "done",
    match: (t) => t.Status === "done" },
];

export default function BoardView({ onOpenTask }) {
  const [tasks, setTasks] = useState(null);
  const [err, setErr] = useState("");
  const [dragId, setDragId] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [repos, setRepos] = useState([]);
  const [nt, setNt] = useState({ Title: "", Summary: "", toCoder: true, repo: "" });

  const load = useCallback(async () => {
    try { setTasks(((await api.get("/api/tasks")).data.data || []).filter((t) => t.Status !== "dropped")); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load the board"); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  useEffect(() => {
    // repo choices = the GitHub sources the connector discovered (FanApp, TopE, ...)
    api.get("/api/sources").then(({ data }) => {
      const gh = (data.data || []).filter((s) => s.Channel === "github" && s.Active).map((s) => s.Address);
      setRepos(gh);
      if (gh.length) setNt((cur) => ({ ...cur, repo: gh[0] }));
    }).catch(() => {});
  }, []);

  const drop = async (col) => {
    if (!dragId || col.key === "waiting") { setDragId(null); return; }   // waiting is review-driven
    await api.patch(`/api/tasks/${dragId}`, { Status: col.status });
    setDragId(null); load();
  };

  const create = async () => {
    const { data } = await api.post("/api/tasks", { Title: nt.Title, Summary: nt.Summary || null, Kind: "coding",
      Tags: nt.repo ? `repo:${nt.repo}` : null });
    if (nt.toCoder) await api.post(`/api/tasks/${data.taskId}/code`, { repo: nt.repo || null });
    setNewOpen(false); setNt((cur) => ({ ...cur, Title: "", Summary: "", toCoder: true }));
    load();
  };

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 17, flex: 1 }}>Agent board</Typography>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => setNewOpen(true)}>New task for the agent</Button>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, minmax(0, 1fr))" }, gap: 2, alignItems: "start" }}>
        {COLS.map((col) => {
          const cards = tasks.filter(col.match);
          return (
            <Box key={col.key} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(col)}
              sx={{ bgcolor: "#f1f3f6", border: `1px solid ${BORDER}`, borderRadius: 2.5, p: 1,
                minHeight: 220, outline: dragId && col.key !== "waiting" ? "2px dashed #c9cff0" : "none", outlineOffset: -4 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 0.5, pb: 1 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: col.dot }} />
                <Typography variant="body2" sx={{ color: INK, fontWeight: 700, flex: 1 }}>{col.title}</Typography>
                <Chip size="small" label={cards.length} sx={{ height: 18, fontSize: 10.5, bgcolor: PANEL, border: `1px solid ${BORDER}`, color: DIM }} />
              </Box>
              {!cards.length && <Empty>Nothing here.</Empty>}
              {cards.map((t) => (
                <Box key={t.TaskId} draggable onDragStart={() => setDragId(t.TaskId)} onDragEnd={() => setDragId(null)}
                  onClick={() => onOpenTask(t.TaskId)}
                  sx={{ ...card, ...hoverable, p: 1.25, mb: 1, cursor: "grab", "&:active": { cursor: "grabbing" } }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                    <Typography variant="caption" sx={{ ...mono, color: "#4f46e5", fontWeight: 700 }}>{t.ref}</Typography>
                    <ChannelIcon channel={t.Source} sx={{ fontSize: 13 }} />
                    {String(t.Assignee || "").startsWith("agent:") && <SmartToyIcon sx={{ fontSize: 13, color: "#7e22ce" }} />}
                    {t.RunStatus && (
                      <Chip size="small" label={`${t.RunAgent || "agent"} · ${t.RunStatus}`}
                        sx={{ height: 17, fontSize: 9.5, fontWeight: 700,
                          bgcolor: t.RunStatus === "running" ? "#fef4e6" : t.RunStatus === "error" ? "#fdecec" : "#e8f6ee",
                          color: t.RunStatus === "running" ? "#b45309" : t.RunStatus === "error" ? "#b91c1c" : "#15803d" }} />
                    )}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ color: FAINT }}>{timeAgo(t.CreatedAt)}</Typography>
                  </Box>
                  <Typography variant="body2" sx={{ color: INK, fontWeight: 600, lineHeight: 1.35, mt: 0.5,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {t.Title}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.75 }}>
                    <Chip size="small" label={t.Kind} sx={{ height: 17, fontSize: 9.5, bgcolor: PANEL2, border: `1px solid ${BORDER}`, color: DIM }} />
                    {t.ReviewStatus && <ActionChip reviewStatus={t.ReviewStatus} taskStatus={t.Status}
                      action={t.ReviewKind === "escalation" ? "escalate" : t.ReviewKind === "auto" ? "auto" : "draft"} />}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 10.5 }}>open →</Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          );
        })}
      </Box>

      {/* ── start a task for the agent ─────────────────────────────────── */}
      <Dialog open={newOpen} onClose={() => setNewOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New task for the agent</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: "8px !important" }}>
          <TextField label="What needs to happen" value={nt.Title} onChange={(e) => setNt({ ...nt, Title: e.target.value })} />
          <TextField label="Details (optional)" multiline minRows={3} value={nt.Summary}
            onChange={(e) => setNt({ ...nt, Summary: e.target.value })} />
          {repos.length > 0 && (
            <Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
                Repository — the issue lands here and the agent works in this context
              </Typography>
              <Select fullWidth size="small" value={nt.repo} onChange={(e) => setNt({ ...nt, repo: e.target.value })}>
                {repos.map((r) => <MenuItem key={r} value={r} sx={{ fontSize: 12.5 }}>{r}</MenuItem>)}
              </Select>
            </Box>
          )}
          <FormControlLabel control={<Checkbox checked={nt.toCoder} onChange={(e) => setNt({ ...nt, toCoder: e.target.checked })} />}
            label={<Typography variant="body2">Send to the coder immediately (issue → work → report)</Typography>} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>Cancel</Button>
          <Button variant="contained" disableElevation disabled={!nt.Title.trim()} onClick={create}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
