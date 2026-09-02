// Board: the agent kanban - every task as a card in a status column. Some cards arrive
// from triage, some you start yourself; drag between columns to change status, click a
// card to open the task (where you can message the agent working it). House design.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, MenuItem, Select, Switch, TextField, Tooltip, Typography,
} from "@mui/material";
import ViewKanbanIcon from "@mui/icons-material/ViewKanban";
import ViewInArIcon from "@mui/icons-material/ViewInAr";
import StudioView from "./StudioView.jsx";
import WallView from "./WallView.jsx";
import GridViewIcon from "@mui/icons-material/GridView";
import ForumIcon from "@mui/icons-material/Forum";
import AddIcon from "@mui/icons-material/Add";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import api from "./api";
import AgentWall from "./AgentWall.jsx";
import { NO_REPO, planTask } from "./newTask.js";
import { pollWhileVisible } from "./visible.js";
import { ALERT, GRADIENT, PANEL, PANEL2, BORDER, CATPPUCCIN, DIM, FAINT, INK, ROLES, card, hoverable, mono } from "./theme.jsx";
import { ChannelIcon, ActionChip, AgentPicker, useAgents, timeAgo, Empty, IDLE_WAITING, isWaiting, PromptThumbs, TellAgent, WorkPane, usePromptImages, TaskuaryMark } from "./ui.jsx";

// Not every ask is about a codebase - "what does this policy mean", "draft me a note", "prepare
// me for this meeting". The task carries `repo:none`, which is the one answer the picker could
// never give before: with the field left blank Taskuary still GUESSED a checkout, so a general
// question opened in whichever repo scored highest and the agent went looking for code to change.

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
const AGENT_HUES = { claude: "#7d9a7c", codex: "#6f8a6e", gemini: "#55697a",
                     cursor: "#6f8a6e", copilot: "#8a8276" };
// 'coder' says nothing about which model family answers - resolve every display through
// the profile's actual command, so the board speaks CLI names (claude, codex, gemini)
export const cliName = (name, cmds = {}) =>
  String(cmds[name] || name || "").split(/[\\/]/).pop().replace(/\.(cmd|exe|bat|ps1)$/i, "").toLowerCase();

const agentBadge = (name, runStatus, isLive, cmds = {}) => {
  if (!isLive && runStatus !== "running") return null;
  const cmd = cliName(name, cmds);
  const hit = Object.entries(AGENT_HUES).find(([k]) => cmd.includes(k));
  if (!hit) return name ? { word: String(name), color: "#867f74" } : null;
  return { word: hit[0], color: hit[1] };
};

// A card's peephole into the running agent: the last couple of console lines, live - and the
// blackboard line above them: the files THIS agent has modified so far (git-attributed, so it
// is true even when the agent never says so). Every other agent is told the same list.
const basename = (f) => String(f).split(/[\\/]/).pop();
export const FileChips = ({ files }) => (files || []).length === 0 ? null : (
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
  const waiting = run.kind === "session" && isWaiting(run);
  // a session reports what the agent HOLDS (ui.WorkPane); the raw-tail pane below stays only for
  // a run with no witness at all
  if (run.work) return <WorkPane run={run} />;
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
        borderRadius: 0.75, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", cursor: "pointer",
        "&:hover": { bgcolor: "#d2d6cf" } }}>
      <Typography sx={{ color: ROLES.working.ink, fontWeight: 800, fontSize: 8.5, letterSpacing: ".05em" }}>
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
  found: { title: "WHAT IT WORKED OUT", icon: "🔍", fg: "#6f8a6e", bg: "#e3e6e1", bd: "#d2d6cf" },
  did: { title: "WHAT IT ALREADY CHANGED", icon: "✓", fg: "#47654a", bg: "#dfeade", bd: "#c8d9c7" },
  next: { title: "THE NEXT STEP", icon: "→", fg: "#55697a", bg: "#eae4d8", bd: "#d8cfbe" },
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
          <Typography sx={{ ...mono, color: "#55697a", fontWeight: 700, fontSize: 12 }}>{task?.ref}</Typography>
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
            <Typography variant="caption" sx={{ color: ROLES.working.ink, fontWeight: 800, fontSize: 9.5,
              letterSpacing: ".08em", display: "block", mb: 0.5 }}>
              ✎ FILES IT TOUCHED — {files.length}, per git
            </Typography>
            <Box sx={{ maxHeight: 168, overflowY: "auto", border: `1px solid ${BORDER}`, borderRadius: 2 }}>
              {files.map((f, i) => (
                <Box key={f.path} sx={{ display: "flex", gap: 1, alignItems: "baseline", px: 1, py: 0.45,
                  borderTop: i ? `1px solid ${BORDER}` : "none" }}>
                  <Typography sx={{ ...mono, color: INK, fontSize: 10.5, flex: 1, minWidth: 0 }} noWrap
                    title={f.path}>{f.path}</Typography>
                  <Typography sx={{ ...mono, color: "#47654a", fontSize: 10 }}>+{f.added}</Typography>
                  <Typography sx={{ ...mono, color: "#6b2733", fontSize: 10 }}>−{f.removed}</Typography>
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
  // Work started again on a finished task is work in progress, whatever the Status column
  // still says. The tell is WHEN the session began: one that started after the task was
  // closed means somebody picked it back up, while one that predates the close is just a
  // terminal nobody shut - and bouncing every card out of Done because its window is still
  // open would be its own bug. No ClosedAt to compare against (a row closed before the
  // column existed) trusts the live session: it is the fact happening right now.
  const resumed = l && (!t.ClosedAt || String(l.StartedAt || "") > String(t.ClosedAt));
  if (t.Status === "done" && !resumed) return "done";
  if (l) return l.kind === "session" && isWaiting(l) ? "waiting" : "working";
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
  { key: "queued", title: "Queued", dot: "#867f74", status: "open" },
  { key: "working", title: "Agent working", dot: "#6f8a6e", status: "in_progress" },
  { key: "waiting", title: "Waiting on you", dot: ALERT, status: "waiting" },
  { key: "done", title: "Done", dot: "#47654a", status: "done" },
];

export default function BoardView({ onOpenTask, onOpenReports }) {
  const [tasks, setTasks] = useState(null);
  const [err, setErr] = useState("");
  const [view, setView] = useState("columns");   // columns | studio | wall - three looks at one board
  const [boardTick, setBoardTick] = useState(0); // bumped when a session starts here: the active board view reloads at once
  const [dragId, setDragId] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [noteFor, setNoteFor] = useState(null);   // the task whose handover note is open
  const [feedOpen, setFeedOpen] = useState(false); // Feed the agent: the funnel's front door
  const [feedTask, setFeedTask] = useState(null);
  useEffect(() => {
    if (!feedOpen) return;
    const liveIds = Object.keys(live || {}).map(Number);
    if (!feedTask || !(tasks || []).some((t) => t.TaskId === feedTask)) setFeedTask(liveIds.length === 1 ? liveIds[0] : (liveIds[0] || null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedOpen]);
  const [repos, setRepos] = useState([]);
  const { agents, models, cmds } = useAgents();
  const [live, setLive] = useState({});                // TaskId -> {tail, AgentName} while a run works
  // how = does an agent start on it now, or does it just get filed. There is no third
  // option: work always happens in a session you can watch and talk to.
  // stayOpen defaults ON: a session started from this box is one the owner means to sit in, and
  // the self-close judge would otherwise end it the first time they looked away (selfclose.STAY_TAG)
  const [nt, setNt] = useState({ Title: "", Summary: "", how: "live", repo: "", agent: "coder", model: "", browser: false, stayOpen: true });
  const shots = usePromptImages();      // screenshots on the new task's prompt, same as the Wall's queue box

  const load = useCallback(async () => {
    try { setTasks(((await api.get("/api/tasks", { params: { active: 1 } })).data.data || []).filter((t) => t.Status !== "dropped")); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load the board"); }
  }, []);
  useEffect(() => { load(); return pollWhileVisible(load, 15000); }, [load]);
  // live tails poll fast (the cards are a status wall you watch); the task page has the full trace
  useEffect(() => {
    const tick = () => api.get("/api/runs/live").then(({ data }) =>
      setLive(Object.fromEntries((data.data || []).map((r) => [r.TaskId, r])))).catch(() => {});
    tick();
    return pollWhileVisible(tick, 4000);
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
      // no repositories discovered: the box says General rather than sitting blank, because
      // that IS the only thing it can be on a machine with no checkout connected
      setNt((cur) => ({ ...cur, repo: def || NO_REPO }));
    }).catch(() => {});
  }, []);

  const drop = async (col) => {
    if (!dragId || col.key === "waiting") { setDragId(null); return; }   // waiting is review-driven
    await api.patch(`/api/tasks/${dragId}`, { Status: col.status });
    setDragId(null); load();
  };

  // one reading of the repository box (newTask.js): who works it, and what the two fields
  // under it should say about that
  const plan = planTask(nt.repo, nt.how, nt.browser, nt.stayOpen && nt.how === "terminal");
  const noRepo = !plan.repo;                    // which of the two "live" readings the box offers
  const create = async () => {
    const { repo, kind, chat, tags } = plan;
    const { data } = await api.post("/api/tasks",
      { Title: nt.Title, Summary: nt.Summary || null, Kind: kind, Tags: tags });
    // The images can only be stored against a task, so they upload now and the prompt gains the
    // sentence that names them - the seed reads Summary, so this has to land before the session.
    try {
      const ref = await shots.upload(data.taskId);
      if (ref) await api.patch(`/api/tasks/${data.taskId}`, { Summary: [nt.Summary || "", ref].filter(Boolean).join("\n\n") });
    } catch (e) { setErr(e?.response?.data?.detail || "Task created, but the images could not be attached"); }
    shots.clear();
    setNewOpen(false); setNt((cur) => ({ ...cur, Title: "", Summary: "" }));
    // The details field IS the prompt - it gets typed into the session. A CODING task born on
    // the Board stays on the Board: start its terminal here, whichever board view is showing.
    if (plan.start && chat) {
      // the chat IS the page for a general task, and it lives on the Tasks tab - open it there
      // with the prompt as the first thing said
      onOpenTask(data.taskId, { start: true });
      return;
    }
    if (plan.start) {
      try {
        await api.post("/api/terminals", { agent: nt.agent, model: nt.model || null, task_id: data.taskId, repo, seed: true });
        setBoardTick((n) => n + 1);
      } catch (e) {
        // The task was created successfully, so keep it visible on the Board and explain only
        // the part that failed instead of navigating away and silently retrying elsewhere.
        setErr(e?.response?.data?.detail || "Task created, but the agent could not be started");
      }
    }
    load();
  };

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      {/* four things on one line is a laptop's worth of room; below that they wrap rather than
          push the page sideways */}
      <Box sx={{ display: "flex", alignItems: "center", mb: 1.25, gap: 1.5, flexWrap: "wrap" }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, flex: "1 1 auto" }}>Agent board</Typography>
        {view === "notes" && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>
          Short-lived task and checkout coordination — agents read it before starting; what stays true next month belongs on Social.
        </Typography>}
        {view === "floor" && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>
          One desk per agent that can run at once — an empty desk is capacity you are not using.
        </Typography>}
        {/* the same board, two ways to look at it - columns to move work, the floor to see how
            much of your capacity is actually busy */}
        <Box sx={{ display: "flex", gap: 0.25, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 2, p: "3px" }}>
          {[{ k: "columns", label: "Columns", icon: <ViewKanbanIcon sx={{ fontSize: 14 }} /> },
            { k: "studio", label: "Studio", icon: <ViewInArIcon sx={{ fontSize: 14 }} /> },
            { k: "wall", label: "Wall", icon: <GridViewIcon sx={{ fontSize: 14 }} /> },
            { k: "notes", label: "Live handoffs", icon: <ForumIcon sx={{ fontSize: 14 }} /> }].map((o) => (
              <Box key={o.k} onClick={() => setView(o.k)}
                sx={{ display: "flex", alignItems: "center", gap: 0.6, height: 24, px: 1.1, borderRadius: 1.5,
                  fontSize: 12, fontWeight: view === o.k ? 700 : 500, cursor: "pointer",
                  color: view === o.k ? INK : DIM, bgcolor: view === o.k ? PANEL : "transparent",
                  boxShadow: view === o.k ? "0 1px 2px rgba(30,50,38,.10)" : "none" }}>
                {o.icon}{o.label}
              </Box>
            ))}
        </Box>
        {/* the funnel's front door, as big as the task button: pick the agent, paste the prompts */}
        <Button size="small" variant="outlined" disableElevation onClick={() => setFeedOpen(true)}
          sx={{ color: "#6b5f45", borderColor: "#d8cfbe", bgcolor: "#f1ead9", "&:hover": { borderColor: "#8a7a5c", bgcolor: "#e9dfc5" } }}>✎ Feed the agent</Button>
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => setNewOpen(true)} sx={{ background: GRADIENT }}>New task for the agent</Button>
      </Box>
      <Dialog open={feedOpen} onClose={() => setFeedOpen(false)} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ pb: 0.5 }}>Feed the agent
          <Typography variant="caption" sx={{ color: FAINT, display: "block", fontWeight: 400, mt: 0.25 }}>
            Queue prompts for an agent - one, or a whole list. They land one per stop, in order, never mid-turn.
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1.25 }}>
            {(tasks || []).filter((t) => t.Kind !== "reply" && t.Status !== "done" && t.Status !== "dropped")
              .sort((a, b) => (live[b.TaskId] ? 1 : 0) - (live[a.TaskId] ? 1 : 0))
              .map((t) => (
                <Box key={t.TaskId} onClick={() => setFeedTask(t.TaskId)}
                  sx={{ px: 1.1, py: 0.5, borderRadius: 99, cursor: "pointer", fontSize: 11.5, fontWeight: 600, maxWidth: 360, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    border: `1px solid ${feedTask === t.TaskId ? "#8a7a5c" : BORDER}`, bgcolor: feedTask === t.TaskId ? "#f1ead9" : PANEL, color: INK }}>
                  {live[t.TaskId] ? "▮ " : ""}{t.ref} · {t.Title}
                </Box>
              ))}
            {(tasks || []).filter((t) => t.Kind !== "reply" && t.Status !== "done" && t.Status !== "dropped").length === 0 && (
              <Typography variant="caption" sx={{ color: FAINT }}>No open coding task yet - make one with New task for the agent, then feed it.</Typography>
            )}
          </Box>
          {feedTask ? <TellAgent taskId={feedTask} taskRef={(tasks || []).find((t) => t.TaskId === feedTask)?.ref} onQueued={load} />
            : <Typography variant="caption" sx={{ color: FAINT }}>Pick the task above - ▮ marks one with an agent on it right now.</Typography>}
        </DialogContent>
      </Dialog>

      {/* what the agents are telling EACH OTHER - the half of the board git cannot show */}
      {view === "notes" && <AgentWall onOpenTask={onOpenTask} refresh={boardTick} />}
      {view === "studio" && <StudioView onOpenTask={onOpenTask} refresh={boardTick} />}
      {view === "wall" && <WallView onOpenTask={onOpenTask} onOpenReports={onOpenReports} refresh={boardTick} />}

      <Box sx={{ display: view === "columns" ? "grid" : "none", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(4, minmax(0, 1fr))" }, gap: 2, alignItems: "start" }}>
        {COLS.map((col) => {
          const today = localToday();
          // Done is agent work finished today. A reply the owner answered by hand, or a to-do
          // ticked off in Tasks, never came through here - it lives in Tasks, not on this board.
          const agentWork = (t) => t.HadAgent || t.Kind === "coding" || t.Kind === "setup" || !!t.Session;
          const cards = tasks.filter((t) => laneOf(t, live) === col.key
            && (col.key !== "done" || (String(t.ClosedAt || t.UpdatedAt || "").startsWith(today) && t.Kind !== "reply" && agentWork(t))));
          // rank mode: the Queued lane reads top-down in the order the funnel will take them
          if (col.key === "queued") cards.sort((a, b) => (b.Queued?.value ?? 0.5) - (a.Queued?.value ?? 0.5));
          return (
            // the lanes run to the bottom of the window: four columns of different heights
            // read as four unrelated boxes floating on the page, and a short lane gave a
            // drop target the size of its one card
            <Box key={col.key} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(col)}
              sx={{ bgcolor: "#e9e3d8", border: `1px solid ${BORDER}`, borderRadius: 2.5, p: 0.85,
                // stacked on a phone, an EMPTY column that keeps a desktop's height is 200px of
                // "Nothing here." between you and the column that has the work in it
                minHeight: { xs: cards.length ? 200 : 0, md: "calc(100vh - 190px)" }, alignSelf: "stretch",
                outline: dragId && col.key !== "waiting" ? "2px dashed #d8cfbe" : "none", outlineOffset: -4 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.4, pb: 0.85 }}>
                <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: col.dot }} />
                <Typography variant="body2" sx={{ color: INK, fontWeight: 700, flex: 1, fontSize: 11.5 }}>{col.title}</Typography>
                <Chip size="small" label={cards.length} sx={{ height: 16, fontSize: 9.5, bgcolor: PANEL,
                  border: `1px solid ${BORDER}`, color: DIM, "& .MuiChip-label": { px: 0.65 } }} />
              </Box>
              {col.key === "done" && <Typography variant="caption" sx={{ display: "block", color: FAINT, fontSize: 10, px: 0.4, mb: 0.85, lineHeight: 1.3 }}>
                Today only — older finished work lives in Tasks, reopenable any time.
              </Typography>}
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
                    <Typography variant="caption" sx={{ ...mono, color: "#55697a", fontWeight: 700, fontSize: 10,
                      whiteSpace: "nowrap", flexShrink: 0 }}>{t.ref}</Typography>
                    <ChannelIcon channel={t.Source} sx={{ fontSize: 12 }} />
                    {String(t.Assignee || "").startsWith("agent:") && <TaskuaryMark size={12} />}
                    {t.RunStatus && (
                      <Chip size="small" label={`${cliName(t.RunAgent, cmds) || "agent"} · ${t.RunStatus}`
                        + (live[t.TaskId] ? ` · ${elapsed(live[t.TaskId].StartedAt)}` : "")}
                        sx={{ height: 15, fontSize: 8.5, fontWeight: 700, "& .MuiChip-label": { px: 0.7 },
                          bgcolor: t.RunStatus === "running" ? "#eae4d8" : t.RunStatus === "error" ? "#f0e2e4" : "#dfeade",
                          color: t.RunStatus === "running" ? "#55697a" : t.RunStatus === "error" ? "#6b2733" : "#47654a" }} />
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
                    <Box sx={{ mt: 0.75, px: 1.1, py: 0.8, bgcolor: ROLES.working.tint, border: `1px solid ${ROLES.working.bd}`,
                      borderLeft: `3px solid ${ROLES.working.solid}`, borderRadius: 1.25 }}>
                      <Typography variant="caption" sx={{ color: "#55697a", fontWeight: 700, display: "block",
                        fontSize: 10, lineHeight: 1.4 }}>
                        ⏳ {t.Queued.behind ? `Waiting on ${t.Queued.behind}` : "Waiting for a free agent slot"}
                        {t.Queued.behindTitle ? ` — “${t.Queued.behindTitle}”` : ""}
                      </Typography>
                      <Typography variant="caption" sx={{ color: ROLES.working.ink, display: "block", fontSize: 9.5,
                        lineHeight: 1.45, mt: 0.2 }}>
                        {t.Queued.why ? `${t.Queued.why} · ` : t.Queued.reason ? `${t.Queued.reason} · ` : ""}starts by itself when it can
                      </Typography>
                    </Box>
                  )}
                  {live[t.TaskId] && <LiveTail run={live[t.TaskId]} />}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mt: 0.6 }}>
                    <Chip size="small" label={t.Kind} sx={{ height: 15, fontSize: 8.5, bgcolor: PANEL2,
                      border: `1px solid ${BORDER}`, color: DIM, "& .MuiChip-label": { px: 0.7 } }} />
                    {t.ReviewStatus && <ActionChip reviewStatus={t.ReviewStatus} taskStatus={t.Status}
                      action={t.ReviewKind === "auto" ? "auto" : "draft"} />}
                    {/* the funnel is invisible until it isn't: a queued prompt is a promise the owner made
                        to this agent, and the card is where they look for it */}
                    {t.Waiting > 0 && (
                      <Chip size="small" onClick={(e) => { e.stopPropagation(); setFeedTask(t.TaskId); setFeedOpen(true); }}
                        label={`✎ ${t.Waiting} queued prompt${t.Waiting === 1 ? "" : "s"}`}
                        title="waiting in the funnel - lands at the agent's next stop; click to add more"
                        sx={{ height: 15, fontSize: 8.5, bgcolor: "#f1ead9", border: "1px solid #d8cfbe", color: "#6b5f45", fontWeight: 700,
                          cursor: "pointer", "& .MuiChip-label": { px: 0.7 } }} />
                    )}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" sx={{ color: "#55697a", fontWeight: 600, fontSize: 9.5 }}>open →</Typography>
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
          <Box>
            <TextField fullWidth label="Prompt — what you want the agent to do" multiline minRows={4} maxRows={12} value={nt.Summary}
              placeholder="Exactly what to do, where to look, what done means. This text is sent to the agent as its instruction. Paste a screenshot to send it along."
              onChange={(e) => setNt({ ...nt, Summary: e.target.value })} onPaste={shots.onPaste} />
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
              <Button size="small" component="label" startIcon={<AttachFileIcon sx={{ fontSize: 14 }} />} sx={{ fontSize: 10.5, color: DIM }}>
                attach images
                <input hidden multiple type="file" accept="image/*"
                  onChange={(e) => { shots.add(e.target.files); e.target.value = ""; }} />
              </Button>
              <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>or paste one straight into the prompt</Typography>
            </Box>
            <PromptThumbs imgs={shots.imgs} onDrop={shots.drop} />
          </Box>
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
              Repository — the issue lands here and the agent works in this context
            </Typography>
            <Select fullWidth size="small" value={nt.repo} onChange={(e) => setNt({ ...nt, repo: e.target.value })}>
              {/* the choice here decides WHO works it: a repository means a CLI in that checkout,
                  General means the assistant's chat. Everything below this box follows from it. */}
              {repos.map((r) => <MenuItem key={r} value={r} sx={{ fontSize: 12.5 }}>{r}</MenuItem>)}
              <MenuItem value={NO_REPO} sx={{ fontSize: 12.5 }}>General — no repository, just a question to answer</MenuItem>
            </Select>
          </Box>
          {/* a general question is answered by an AI connector, not a CLI - unless the owner
              asked for a terminal below, in which case the CLI is exactly what matters */}
          <Box sx={{ display: plan.chat ? "none" : "block" }}>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
              Agent and model — which CLI works it, and which model that CLI runs
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <AgentPicker agents={agents} models={models} agent={nt.agent} model={nt.model}
                onAgent={(a) => setNt({ ...nt, agent: a, model: "" })} onModel={(m) => setNt({ ...nt, model: m })} />
            </Box>
            {agents.length < 2 && (
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                Add more CLIs under Connections → AI CLI agents to choose between them here.
              </Typography>
            )}
          </Box>
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
              How it gets worked — one agent, one way
            </Typography>
            <Select fullWidth size="small" value={nt.how} onChange={(e) => setNt({ ...nt, how: e.target.value })}
              renderValue={(v) => v === "file" ? "Just file it" : v === "terminal" ? `Start ${nt.agent} in a terminal`
                : noRepo ? "Ask the assistant" : `Start ${nt.agent} on it`}>
              <MenuItem value="live" sx={{ fontSize: 12.5 }}>{noRepo
                ? "Ask the assistant — opens the chat on the Tasks tab with your prompt as the first message"
                : `Start ${nt.agent} on it — stays on the board with the prompt typed in`}</MenuItem>
              {/* a question you would rather work in a CLI: the old behaviour, now asked for */}
              {noRepo && <MenuItem value="terminal" sx={{ fontSize: 12.5 }}>
                Start {nt.agent} in a terminal instead — no repository, its own folder
              </MenuItem>}
              <MenuItem value="file" sx={{ fontSize: 12.5 }}>Just file it — nobody starts working yet</MenuItem>
            </Select>
            {/* a portal with no API, a page behind a login: the session opens a browser with it,
                you watch it beside the terminal, and you type the password yourself */}
            <Box sx={{ display: "flex", alignItems: "center", mt: 0.5 }}>
              <Switch size="small" checked={!!nt.browser} onChange={(e) => setNt({ ...nt, browser: e.target.checked })} />
              <Typography variant="caption" sx={{ color: nt.browser ? INK : DIM }}>
                It needs a browser — one opens with the session, watched beside it, and you type any password
              </Typography>
            </Box>
            {/* the difference between a session that works FOR you and one you work IN. Only a
                terminal can be sat in, so the switch is only true where it means anything. */}
            {nt.how === "terminal" && (
              <Box sx={{ display: "flex", alignItems: "center" }}>
                <Switch size="small" checked={!!nt.stayOpen} onChange={(e) => setNt({ ...nt, stayOpen: e.target.checked })} />
                <Typography variant="caption" sx={{ color: nt.stayOpen ? INK : DIM }}>
                  Leave it open when it goes quiet — only you end it; off, it closes itself the moment it reads as finished
                </Typography>
              </Box>
            )}
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
