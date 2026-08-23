// Board: the agent kanban - every task as a card in a status column. Some cards arrive
// from triage, some you start yourself; drag between columns to change status, click a
// card to open the task (where you can message the agent working it). House design.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, MenuItem, Select, TextField, Tooltip, Typography,
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

// WHICH agent is on the card, said out loud: a small legend sitting ON the border with the
// CLI's name, in a hue from the app's own palette - subtle but distinct, never brand colors
// that fight the theme. Live or running only; a finished run's card goes back to house style.
const AGENT_HUES = { claude: "#7c6cf0", codex: "#0e7490", gemini: "#2563eb",
                     cursor: "#7e22ce", copilot: "#64748b" };
// 'coder' says nothing about which model family answers - resolve every display through
// the profile's actual command, so the board speaks CLI names (claude, codex, gemini)
export const cliName = (name, cmds = {}) =>
  String(cmds[name] || name || "").split(/[\\/]/).pop().replace(/\.(cmd|exe|bat|ps1)$/i, "").toLowerCase();

const agentBadge = (name, runStatus, isLive, cmds = {}) => {
  if (!isLive && runStatus !== "running") return null;
  const cmd = cliName(name, cmds);
  const hit = Object.entries(AGENT_HUES).find(([k]) => cmd.includes(k));
  if (!hit) return name ? { word: String(name), color: "#8a94a6" } : null;
  return { word: hit[0], color: hit[1] };
};

// A card's peephole into the running agent: the last couple of console lines, live - and the
// blackboard line above them: the files THIS agent has modified so far (git-attributed, so it
// is true even when the agent never says so). Every other agent is told the same list.
const basename = (f) => String(f).split(/[\\/]/).pop();
const FileChips = ({ files }) => (files || []).length === 0 ? null : (
  <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5, mb: 0.5 }}>
    {files.slice(0, 4).map((f) => (
      <Tooltip key={f} title={f} arrow>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10, lineHeight: "16px", px: 0.6,
          color: CATPPUCCIN.green, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 0.75 }}>
          ✎ {basename(f)}
        </Typography>
      </Tooltip>
    ))}
    {files.length > 4 && (
      <Tooltip title={files.slice(4).map(basename).join(", ")} arrow>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: CATPPUCCIN.dim }}>+{files.length - 4}</Typography>
      </Tooltip>
    )}
  </Box>
);

const LiveTail = ({ run }) => {
  const waiting = run.kind === "session" && run.idle >= IDLE_WAITING;
  return (
  <Box sx={{ mt: 0.6, bgcolor: CATPPUCCIN.bg, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 1.25, px: 0.85, py: 0.5 }}>
    <FileChips files={run.files} />
    {(run.tail || []).slice(-2).map((l, i, all) => (
      <Typography key={i} noWrap variant="caption"
        sx={{ ...mono, display: "block", fontSize: 9.5, lineHeight: 1.5,
          color: l.startsWith("→") ? CATPPUCCIN.blue : l.startsWith("✗") ? CATPPUCCIN.red : CATPPUCCIN.dim,
          opacity: i === all.length - 1 ? 1 : 0.55 }}>
        {l.replace(/\n/g, " ")}
      </Typography>
    ))}
    <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: waiting ? CATPPUCCIN.yellow : CATPPUCCIN.cyan,
      ...(waiting ? {} : { "@keyframes tqBlink": { "50%": { opacity: 0.25 } }, animation: "tqBlink 1.1s step-end infinite" }) }}>
      {waiting ? `⏸ ${run.AgentName} is waiting on you — answer it`
        : `▮ ${run.AgentName} working ${elapsed(run.StartedAt)}`}
    </Typography>
  </Box>
  );
};

// What one agent left for the next. The note was already written and already re-seeded into
// the next agent's prompt - the owner just could never SEE it, so the board could not answer
// "what did the last one work out?". A chip on the card, the whole thing in a dialog.
const NOTE_FIELDS = ["found", "did", "next"];
const noteBody = (n) => String(n || "").replace(/^HANDOVER NOTE\s*/i, "").trim();

const NoteChip = ({ onOpen }) => (
  <Tooltip arrow title="what this agent left for whoever picks the task up next">
    <Box onClick={(e) => { e.stopPropagation(); onOpen(); }}
      sx={{ display: "inline-flex", alignItems: "center", gap: 0.3, px: 0.6, height: 16,
        borderRadius: 0.75, bgcolor: "#f5f3ff", border: "1px solid #ddd6fe", cursor: "pointer",
        "&:hover": { bgcolor: "#ede9fe" } }}>
      <Typography sx={{ color: "#6b21a8", fontWeight: 800, fontSize: 8.5, letterSpacing: ".05em" }}>
        ✎ NOTE
      </Typography>
    </Box>
  </Tooltip>
);

// found / did / next as sections, each with its own colour and icon so the eye can jump
// straight to "the next step" - plus the files git says that agent actually touched, which
// is the other half of the handover (the note tells you the thinking, the files tell you
// the blast radius). Anything the agent wrote outside the found/did/next shape is shown
// verbatim rather than dropped: a note we cannot parse is still the note it left.
const SECTION = {
  found: { title: "WHAT IT WORKED OUT", icon: "🔍", fg: "#0e7490", bg: "#e6f7fb", bd: "#c2e7f0" },
  did: { title: "WHAT IT ALREADY CHANGED", icon: "✓", fg: "#15803d", bg: "#e8f6ee", bd: "#cdeeda" },
  next: { title: "THE NEXT STEP", icon: "→", fg: "#b45309", bg: "#fef4e6", bd: "#f3ddb8" },
};

const NoteDialog = ({ open, task, onClose }) => {
  const body = noteBody(task?.HandoverNote);
  const [proof, setProof] = useState(null);
  useEffect(() => {
    setProof(null);
    if (!open || !task?.TaskId) return;
    api.get(`/api/tasks/${task.TaskId}/proof`).then(({ data }) => setProof(data)).catch(() => {});
  }, [open, task?.TaskId]);
  const secs = NOTE_FIELDS.map((k) => {
    const m = body.match(new RegExp(`^\\s*${k}\\s*:\\s*([\\s\\S]*?)(?=^\\s*(?:${NOTE_FIELDS.join("|")})\\s*:|$)`, "im"));
    return [k, (m?.[1] || "").trim()];
  }).filter(([, v]) => v);
  const files = proof?.files || [];
  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="sm" fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontSize: 14.5, pb: 0.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography sx={{ ...mono, color: "#4f46e5", fontWeight: 700, fontSize: 12 }}>{task?.ref}</Typography>
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14 }}>the handover note</Typography>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", fontWeight: 400, mt: 0.25 }}>
          Written when this session paused — and this is the same text the next agent is seeded
          with, so what you read here is what it will know.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pb: 1 }}>
        {!body && <Empty>No note on this task.</Empty>}
        {secs.length ? secs.map(([k, v]) => (
          <Box key={k} sx={{ mb: 1, px: 1.25, py: 0.9, bgcolor: SECTION[k].bg,
            border: `1px solid ${SECTION[k].bd}`, borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: SECTION[k].fg, fontWeight: 800, fontSize: 9.5,
              letterSpacing: ".08em", display: "block", mb: 0.35 }}>
              {SECTION[k].icon} {SECTION[k].title}
            </Typography>
            <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5, lineHeight: 1.55 }}>{v}</Typography>
          </Box>
        )) : body && (
          <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5 }}>{body}</Typography>
        )}
        {/* the note is the agent's account of itself; this is git's */}
        {files.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" sx={{ color: "#6b21a8", fontWeight: 800, fontSize: 9.5,
              letterSpacing: ".08em", display: "block", mb: 0.5 }}>
              ✎ FILES IT TOUCHED — {files.length}, per git
            </Typography>
            <Box sx={{ maxHeight: 168, overflowY: "auto", border: `1px solid ${BORDER}`, borderRadius: 2 }}>
              {files.map((f, i) => (
                <Box key={f.path} sx={{ display: "flex", gap: 1, alignItems: "baseline", px: 1, py: 0.45,
                  borderTop: i ? `1px solid ${BORDER}` : "none" }}>
                  <Typography sx={{ ...mono, color: INK, fontSize: 10.5, flex: 1, minWidth: 0 }} noWrap
                    title={f.path}>{f.path}</Typography>
                  <Typography sx={{ ...mono, color: "#15803d", fontSize: 10 }}>+{f.added}</Typography>
                  <Typography sx={{ ...mono, color: "#b91c1c", fontSize: 10 }}>−{f.removed}</Typography>
                </Box>
              ))}
            </Box>
          </Box>
        )}
        {proof && !files.length && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.5 }}>
            No file changes recorded yet — the agent may have only read, or not committed.
          </Typography>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
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
  if (t.RunStatus === "error") return "waiting";       // it failed: your move, never back to "queued"
  if (t.ReviewStatus === "pending" || t.Status === "waiting") return "waiting";
  if (t.RunStatus === "running") return "working";
  if (t.Status === "in_progress") return "waiting";    // its session ended without a wrap-up: your move
  return "queued";
};

// Done is a TODAY column: yesterday's finished work is history, not board furniture - it
// lives on in Tasks, reopenable any time.
const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
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
  const [noteFor, setNoteFor] = useState(null);   // the task whose handover note is open
  const [repos, setRepos] = useState([]);
  const { agents, models, cmds } = useAgents();
  const [live, setLive] = useState({});                // TaskId -> {tail, AgentName} while a run works
  // how = does an agent start on it now, or does it just get filed. There is no third
  // option: work always happens in a session you can watch and talk to.
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
    // the details field IS the prompt - it gets typed into the session
    if (nt.how === "live") return onOpenTask(data.taskId, { start: true, agent: nt.agent, model: nt.model });
    load();
  };

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", mb: 1.25, gap: 1.5 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, flex: 1 }}>Agent board</Typography>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>
          Done shows today only — older finished work lives in Tasks, reopenable any time.
        </Typography>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => setNewOpen(true)}>New task for the agent</Button>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, minmax(0, 1fr))" }, gap: 2, alignItems: "start" }}>
        {COLS.map((col) => {
          const today = localToday();
          const cards = tasks.filter((t) => laneOf(t, live) === col.key
            && (col.key !== "done" || String(t.ClosedAt || t.UpdatedAt || "").startsWith(today)));
          return (
            // the lanes run to the bottom of the window: four columns of different heights
            // read as four unrelated boxes floating on the page, and a short lane gave a
            // drop target the size of its one card
            <Box key={col.key} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(col)}
              sx={{ bgcolor: "#f1f3f6", border: `1px solid ${BORDER}`, borderRadius: 2.5, p: 0.85,
                minHeight: { xs: 200, md: "calc(100vh - 190px)" }, alignSelf: "stretch",
                outline: dragId && col.key !== "waiting" ? "2px dashed #c9cff0" : "none", outlineOffset: -4 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.4, pb: 0.85 }}>
                <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: col.dot }} />
                <Typography variant="body2" sx={{ color: INK, fontWeight: 700, flex: 1, fontSize: 11.5 }}>{col.title}</Typography>
                <Chip size="small" label={cards.length} sx={{ height: 16, fontSize: 9.5, bgcolor: PANEL,
                  border: `1px solid ${BORDER}`, color: DIM, "& .MuiChip-label": { px: 0.65 } }} />
              </Box>
              {!cards.length && <Empty>Nothing here.</Empty>}
              {cards.map((t) => {
                const badge = agentBadge(live[t.TaskId]?.AgentName || t.RunAgent, t.RunStatus, !!live[t.TaskId], cmds);
                return (
                <Box key={t.TaskId} draggable onDragStart={() => setDragId(t.TaskId)} onDragEnd={() => setDragId(null)}
                  onClick={() => onOpenTask(t.TaskId)}
                  sx={{ ...card, ...hoverable, p: 1.1, mb: 0.9, cursor: "grab", "&:active": { cursor: "grabbing" },
                    position: "relative",
                    ...(badge ? { mt: 1.1, borderColor: `${badge.color}55` } : {}) }}>
                  {badge && (
                    <Typography variant="caption" sx={{ ...mono, position: "absolute", top: -8, left: 10,
                      px: 0.6, fontSize: 9, fontWeight: 700, lineHeight: "13px", letterSpacing: ".06em",
                      color: badge.color, bgcolor: PANEL, border: `1px solid ${badge.color}55`,
                      borderRadius: 1 }}>
                      {badge.word}
                    </Typography>
                  )}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
                    <Typography variant="caption" sx={{ ...mono, color: "#4f46e5", fontWeight: 700, fontSize: 10,
                      whiteSpace: "nowrap", flexShrink: 0 }}>{t.ref}</Typography>
                    <ChannelIcon channel={t.Source} sx={{ fontSize: 12 }} />
                    {String(t.Assignee || "").startsWith("agent:") && <SmartToyIcon sx={{ fontSize: 12, color: "#7e22ce" }} />}
                    {t.RunStatus && (
                      <Chip size="small" label={`${cliName(t.RunAgent, cmds) || "agent"} · ${t.RunStatus}`
                        + (live[t.TaskId] ? ` · ${elapsed(live[t.TaskId].StartedAt)}` : "")}
                        sx={{ height: 15, fontSize: 8.5, fontWeight: 700, "& .MuiChip-label": { px: 0.7 },
                          bgcolor: t.RunStatus === "running" ? "#fef4e6" : t.RunStatus === "error" ? "#fdecec" : "#e8f6ee",
                          color: t.RunStatus === "running" ? "#b45309" : t.RunStatus === "error" ? "#b91c1c" : "#15803d" }} />
                    )}
                    {t.HandoverNote && <NoteChip onOpen={() => setNoteFor(t)} />}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ color: FAINT, fontSize: 9.5 }}>{timeAgo(t.CreatedAt)}</Typography>
                  </Box>
                  <Typography variant="body2" sx={{ color: INK, fontWeight: 600, fontSize: 12, lineHeight: 1.35, mt: 0.4,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {t.Title}
                  </Typography>
                  {/* a held-back dispatch says so ON the card - who it waits for and why, readable
                      without hovering anything */}
                  {t.Queued && (
                    <Box sx={{ mt: 0.75, px: 1.1, py: 0.8, bgcolor: "#eef2ff", border: "1px solid #dfe3fb",
                      borderLeft: "3px solid #7c6cf0", borderRadius: 1.25 }}>
                      <Typography variant="caption" sx={{ color: "#4f46e5", fontWeight: 700, display: "block",
                        fontSize: 10, lineHeight: 1.4 }}>
                        ⏳ {t.Queued.behind ? `Waiting on ${t.Queued.behind}` : "Waiting for a free agent slot"}
                        {t.Queued.behindTitle ? ` — “${t.Queued.behindTitle}”` : ""}
                      </Typography>
                      <Typography variant="caption" sx={{ color: "#5b5f97", display: "block", fontSize: 9.5,
                        lineHeight: 1.45, mt: 0.2 }}>
                        {t.Queued.reason ? `${t.Queued.reason} · ` : ""}starts by itself when it can
                      </Typography>
                    </Box>
                  )}
                  {live[t.TaskId] && <LiveTail run={live[t.TaskId]} />}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mt: 0.6 }}>
                    <Chip size="small" label={t.Kind} sx={{ height: 15, fontSize: 8.5, bgcolor: PANEL2,
                      border: `1px solid ${BORDER}`, color: DIM, "& .MuiChip-label": { px: 0.7 } }} />
                    {t.ReviewStatus && <ActionChip reviewStatus={t.ReviewStatus} taskStatus={t.Status}
                      action={t.ReviewKind === "auto" ? "auto" : "draft"} />}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 9.5 }}>open →</Typography>
                  </Box>
                </Box>
                );
              })}
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
              <MenuItem value="live" sx={{ fontSize: 12.5 }}>Start {nt.agent} on it — opens the task, prompt typed in, you can talk to it</MenuItem>
              <MenuItem value="file" sx={{ fontSize: 12.5 }}>Just file it — nobody starts working yet</MenuItem>
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>Cancel</Button>
          <Button variant="contained" disableElevation disabled={!nt.Title.trim()} onClick={create}>Create</Button>
        </DialogActions>
      </Dialog>

      <NoteDialog open={!!noteFor} task={noteFor} onClose={() => setNoteFor(null)} />
    </Box>
  );
}
