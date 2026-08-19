// Board: the agent kanban - every task as a card in a status column. Some cards arrive
// from triage, some you start yourself; drag between columns to change status, click a
// card to open the task (where you can message the agent working it). House design.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import api from "./api";
import { PANEL, PANEL2, BORDER, CATPPUCCIN, DIM, FAINT, INK, card, hoverable, mono } from "./theme.jsx";
import { ChannelIcon, ActionChip, AgentPicker, useAgents, timeAgo, Empty, IDLE_WAITING } from "./ui.jsx";

// "coder · running" says nothing you can act on. How long it has been going, and what it is
// touching right now, is what tells you whether to leave it alone or go look.
const elapsed = (since) => {
  if (!since) return "";
  const s = Math.max(0, (Date.now() - new Date(String(since).replace(" ", "T"))) / 1000);
  return s < 90 ? `${Math.round(s)}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`;
};

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

// A card's peephole into the running agent: the last couple of console lines, live.
// Click the card for the whole terminal (task page).
const LiveTail = ({ run }) => {
  const waiting = run.kind === "session" && run.idle >= IDLE_WAITING;
  return (
  <Box sx={{ mt: 0.75, bgcolor: CATPPUCCIN.bg, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 1.25, px: 1, py: 0.6 }}>
    {(run.tail || []).slice(-2).map((l, i, all) => (
      <Typography key={i} noWrap variant="caption"
        sx={{ ...mono, display: "block", fontSize: 9.5, lineHeight: 1.55,
          color: l.startsWith("→") ? CATPPUCCIN.blue : l.startsWith("✗") ? CATPPUCCIN.red : CATPPUCCIN.dim,
          opacity: i === all.length - 1 ? 1 : 0.55 }}>
        {l.replace(/\n/g, " ")}
      </Typography>
    ))}
    <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: waiting ? CATPPUCCIN.yellow : CATPPUCCIN.cyan,
      ...(waiting ? {} : { "@keyframes tqBlink": { "50%": { opacity: 0.25 } }, animation: "tqBlink 1.1s step-end infinite" }) }}>
      {waiting ? `⏸ ${run.AgentName} is waiting on you — answer it in the task`
        : `▮ ${run.AgentName} working ${elapsed(run.StartedAt)} — click the card for the full session`}
    </Typography>
  </Box>
  );
};

// Column model: where a card sits is derived from task status + its latest review.
// Which lane a card sits in is decided by what is TRUE right now - a live CLI session is an
// agent working, and that same session gone quiet is a question waiting on you. Reading it
// off the Status column alone left a card in "Queued" while its agent asked what to do.
const laneOf = (t, live) => {
  const l = live[t.TaskId];
  if (t.Status === "done") return "done";
  if (l) return l.kind === "session" && l.idle >= IDLE_WAITING ? "waiting" : "working";
  if (t.ReviewStatus === "pending" || t.Status === "waiting") return "waiting";
  if (t.RunStatus === "running") return "working";
  return "queued";
};
const COLS = [
  { key: "queued", title: "Queued", dot: "#8a94a6", status: "open" },
  { key: "working", title: "Agent working", dot: "#0e7490", status: "in_progress" },
  { key: "waiting", title: "Waiting on you", dot: "#b45309", status: "waiting" },
  { key: "done", title: "Done", dot: "#15803d", status: "done" },
];

export default function BoardView({ onOpenTask }) {
  const [tasks, setTasks] = useState(null);
  const [err, setErr] = useState("");
  const [dragId, setDragId] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [repos, setRepos] = useState([]);
  const { agents, models } = useAgents();
  const [live, setLive] = useState({});                // TaskId -> {tail, AgentName} while a run works
  // how = the ONE way this task gets worked. Two agents on one task (a live session plus a
  // headless run) was the confusing part, so it is a choice, not two buttons.
  const [nt, setNt] = useState({ Title: "", Summary: "", how: "live", repo: "", agent: "coder", model: "" });

  const load = useCallback(async () => {
    try { setTasks(((await api.get("/api/tasks")).data.data || []).filter((t) => t.Status !== "dropped")); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load the board"); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  // live tails poll fast (the cards are a status wall you watch); the task page has the full trace
  useEffect(() => {
    const tick = () => api.get("/api/runs/live").then(({ data }) =>
      setLive(Object.fromEntries((data.data || []).map((r) => [r.TaskId, r])))).catch(() => {});
    tick();
    const t = setInterval(tick, 4000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (agents.length && !agents.includes(nt.agent)) setNt((cur) => ({ ...cur, agent: agents[0] }));
  }, [agents, nt.agent]);
  useEffect(() => {
    // repo choices = the GitHub sources the connector discovered
    api.get("/api/sources").then(({ data }) => {
      const gh = (data.data || []).filter((s) => s.Channel === "github" && s.Active).map((s) => s.Address);
      setRepos(gh);
      const def = data.default_repo && gh.includes(data.default_repo) ? data.default_repo : gh[0];
      if (def) setNt((cur) => ({ ...cur, repo: def }));
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
    setNewOpen(false); setNt((cur) => ({ ...cur, Title: "", Summary: "" }));
    // the details field IS the prompt - it is typed into the live session, or sent down as
    // the headless run's instruction, depending on how you chose to work it
    if (nt.how === "live") return onOpenTask(data.taskId, { start: true, agent: nt.agent, model: nt.model });
    if (nt.how === "headless") await api.post(`/api/tasks/${data.taskId}/code`, { repo: nt.repo || null,
      agent: nt.agent || null, model: nt.model || null, instruction: nt.Summary || null });
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
          const cards = tasks.filter((t) => laneOf(t, live) === col.key);
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
                      <Chip size="small" label={`${t.RunAgent || "agent"} · ${t.RunStatus}`
                        + (live[t.TaskId] ? ` · ${elapsed(live[t.TaskId].StartedAt)}` : "")}
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
                  {live[t.TaskId] && <LiveTail run={live[t.TaskId]} />}
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
          <TextField label="Task name — how it reads on the board" value={nt.Title}
            onChange={(e) => setNt({ ...nt, Title: e.target.value })} />
          <TextField label="Prompt — what you want the agent to do" multiline minRows={4} value={nt.Summary}
            placeholder="Exactly what to do, where to look, what done means. This text is sent to the agent as its instruction."
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
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
              Agent and model — which CLI works it, and which model that CLI runs
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <AgentPicker agents={agents} models={models} agent={nt.agent} model={nt.model}
                onAgent={(a) => setNt({ ...nt, agent: a, model: "" })} onModel={(m) => setNt({ ...nt, model: m })} />
            </Box>
            {agents.length < 2 && (
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                Add more CLIs under Connectors → AI CLI agents to choose between them here.
              </Typography>
            )}
          </Box>
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
              How it gets worked — one agent, one way
            </Typography>
            <Select fullWidth size="small" value={nt.how} onChange={(e) => setNt({ ...nt, how: e.target.value })}>
              <MenuItem value="live" sx={{ fontSize: 12.5 }}>Live {nt.agent} session — opens the task, prompt typed in, you can talk to it</MenuItem>
              <MenuItem value="headless" sx={{ fontSize: 12.5 }}>Headless run — issue → work → report, nothing to watch</MenuItem>
              <MenuItem value="file" sx={{ fontSize: 12.5 }}>Just file it — nobody starts working yet</MenuItem>
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>Cancel</Button>
          <Button variant="contained" disableElevation disabled={!nt.Title.trim()} onClick={create}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
