// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, Link, MenuItem, Select, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import BlockIcon from "@mui/icons-material/Block";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, TaskStatusChip, ActionChip, AgentPicker, useAgents, RunTrace, DiffBlock, timeAgo, fmtDateTime, cleanText, Empty, FilterPills } from "./ui.jsx";
import { OpenTerminalButton } from "./TerminalView.jsx";

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

const STATUSES = ["open", "in_progress", "waiting", "done", "dropped"];
const STATUS_FILTERS = [
  { key: "", label: "all" }, { key: "open", label: "open" },
  { key: "in_progress", label: "in progress", c: PILL_COLORS.amber },
  { key: "waiting", label: "waiting", c: PILL_COLORS.purple },
  { key: "done", label: "done", c: PILL_COLORS.green },
];
const PRIORITIES = ["low", "normal", "high", "urgent"];

// Compact modern select styling shared by the detail-header dropdowns.
const selSx = { fontSize: 12.5, bgcolor: "#fff", borderRadius: 2,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: "#e5e8ee" },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#c9cff0" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: "#4f46e5" } };

export default function TasksView({ selected, onSelect, onChanged, onOpenTerminal }) {
  const [tasks, setTasks] = useState(null);
  const [filter, setFilter] = useState("open");        // default: real work, not history
  const [detail, setDetail] = useState(null);
  const { agents, models } = useAgents();
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
  const [run, setRun] = useState({ agent: "coder", model: "", instruction: "" });
  const [comment, setComment] = useState("");
  const pollRef = useRef(null);

  const loadTasks = useCallback(async () => {
    try { setTasks((await api.get("/api/tasks", { params: filter ? { status: filter } : {} })).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load tasks"); }
  }, [filter]);

  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/api/tasks/${id}`);
      setDetail(data);
      // opened a task the current list filter hides (e.g. from the Board)? widen to
      // "all" so the list and the detail never contradict each other
      setFilter((f) => (f && data.task.Status !== f ? "" : f));
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load task"); }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);
  // the roster is user-config - default to whatever actually exists
  useEffect(() => {
    if (agents.length && !agents.includes(run.agent)) setRun((r) => ({ ...r, agent: agents[0] }));
  }, [agents, run.agent]);
  useEffect(() => { loadDetail(selected); }, [selected, loadDetail]);
  useEffect(() => {
    const running = (detail?.runs || []).some((r) => r.Status === "running");
    clearInterval(pollRef.current);
    if (running && selected) pollRef.current = setInterval(() => loadDetail(selected), 3000);
    return () => clearInterval(pollRef.current);
  }, [detail, selected, loadDetail]);

  const patch = async (fields) => { await api.patch(`/api/tasks/${selected}`, fields); loadDetail(selected); loadTasks(); onChanged?.(); };
  const create = async () => {
    const { data } = await api.post("/api/tasks", nt);
    setNewOpen(false); setNt({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
    setFilter(""); loadTasks(); onSelect(data.taskId);
  };
  // ONE way to start work on a task: pick the agent + model, optionally say what to do,
  // Run. The full coder lifecycle (issue -> work -> report -> close) runs behind it.
  const runAgent = async () => {
    await api.post(`/api/tasks/${selected}/code`, { agent: run.agent, model: run.model || null,
      instruction: run.instruction || null, repo: repoOf(detail?.task) });
    setRun((r) => ({ ...r, instruction: "" }));
    setTimeout(() => { loadDetail(selected); loadTasks(); }, 800);   // run row appears; polling takes over
  };
  const post = async () => {
    if (!comment.trim()) return;
    await api.post(`/api/tasks/${selected}/comments`, { body: comment });
    setComment(""); loadDetail(selected);
  };
  const notATask = async () => {
    await api.post(`/api/tasks/${selected}/not-a-task`);
    onSelect(null); loadTasks(); onChanged?.();
  };
  const [chat, setChat] = useState("");
  const messageAgent = async () => {
    if (!chat.trim()) return;
    await api.post(`/api/tasks/${selected}/message`, { body: chat });
    setChat(""); setTimeout(() => loadDetail(selected), 900);        // chat run appears; polling refreshes the reply
  };

  const t = detail?.task;
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      {/* ── list: one anchored panel - filter header on top, rows scroll inside ── */}
      <Box sx={{ width: 340, flexShrink: 0 }}>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
        <Box sx={{ ...card, p: 0, overflow: "hidden", display: "flex", flexDirection: "column",
          height: "calc(100vh - 118px)", minHeight: 420 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.75,
            borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2, flexShrink: 0 }}>
            <FilterPills options={STATUS_FILTERS} value={filter} onChange={setFilter} />
            <Box sx={{ flex: 1 }} />
            <Button size="small" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => setNewOpen(true)}>New</Button>
          </Box>
          <Box sx={{ overflowY: "auto", flex: 1 }}>
            {!tasks ? <CircularProgress size={20} sx={{ m: 2 }} /> : !tasks.length ? <Empty>No tasks here.</Empty> : tasks.map((task) => (
              <Box key={task.TaskId} onClick={() => onSelect(task.TaskId)}
                sx={{ px: 1.25, py: 0.75, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
                  bgcolor: selected === task.TaskId ? "#eef0ff" : "transparent",
                  borderLeft: `3px solid ${selected === task.TaskId ? "#4f46e5" : "transparent"}`,
                  "&:hover": { bgcolor: selected === task.TaskId ? "#eef0ff" : "#f7f8fa" } }}>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                  <Typography variant="caption" sx={{ ...mono, color: "#4f46e5", fontWeight: 700 }}>{task.ref}</Typography>
                  <TaskStatusChip status={task.Status} />
                  {task.Priority === "urgent" && <Chip size="small" label="urgent" sx={{ bgcolor: "#fdecec", color: "#b91c1c", height: 17, fontSize: 10 }} />}
                  {String(task.Assignee || "").startsWith("agent:") && <SmartToyIcon sx={{ fontSize: 13, color: "#7e22ce" }} />}
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" sx={{ color: FAINT }}>{timeAgo(task.CreatedAt)}</Typography>
                </Box>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", mt: 0.1 }}>
                  <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 500, flex: 1, minWidth: 0 }}>{task.Title}</Typography>
                  {/* the answer at a glance: needs review / reviewed·approved / no reply needed */}
                  {task.ReviewStatus && <ActionChip reviewStatus={task.ReviewStatus}
                    action={task.ReviewKind === "escalation" ? "escalate" : task.ReviewKind === "auto" ? "auto" : "draft"} />}
                </Box>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>

      {/* ── detail ────────────────────────────────────────────────────── */}
      <Box sx={{ ...frame, flex: 1, minWidth: 0, height: "calc(100vh - 118px)", minHeight: 420 }}>
        <Box sx={{ ...frameInner, height: "100%", display: "flex", flexDirection: "column" }}>
          {!t ? <Empty>Select a task to see its full story.</Empty> : (
            <>
              {/* header strip: identity + controls, framed off from the story below */}
              <Box sx={{ px: 2, py: 1.25, bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
                <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Typography sx={{ ...mono, color: "#4f46e5", fontWeight: 700, fontSize: 12.5 }}>{detail.ref}</Typography>
                  <Typography sx={{ color: INK, flex: 1, fontWeight: 700, fontSize: 14.5, minWidth: 200 }}>{t.Title}</Typography>
                  <Select value={t.Status} onChange={(e) => patch({ Status: e.target.value })} sx={selSx}>
                    {STATUSES.map((s) => <MenuItem key={s} value={s} sx={{ fontSize: 12 }}>{s}</MenuItem>)}
                  </Select>
                  <Select value={t.Priority} onChange={(e) => patch({ Priority: e.target.value })} sx={selSx}>
                    {PRIORITIES.map((p) => <MenuItem key={p} value={p} sx={{ fontSize: 12 }}>{p}</MenuItem>)}
                  </Select>
                  {t.Status !== "done" && (
                    <Button size="small" variant="contained" disableElevation sx={{ bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                      onClick={() => patch({ Status: "done" })}>Mark done — I took care of it</Button>
                  )}
                  <Button size="small" color="error" variant="outlined" startIcon={<BlockIcon sx={{ fontSize: 14 }} />}
                    sx={{ bgcolor: PANEL }} onClick={notATask}>Not a task</Button>
                  <Tooltip title="Close — back to the list (the task stays)">
                    <IconButton size="small" onClick={() => onSelect(null)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
                  </Tooltip>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    {t.Kind} · from {t.Source} · assignee {t.Assignee || "—"} · created {timeAgo(t.CreatedAt)} by {t.CreatedBy}
                  </Typography>
                  <Box sx={{ flex: 1 }} />
                  {onOpenTerminal && <OpenTerminalButton taskId={selected} repo={repoOf(t)} onOpen={onOpenTerminal} />}
                </Box>
              </Box>
              <Box sx={{ px: 2, py: 1.5, overflowY: "auto", flex: 1 }}>
                {t.Summary && <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: DIM }}>{cleanText(t.Summary).slice(0, 600)}</Typography>}

                <Block title={`Messages · ${detail.messages.length}`}>
                  {detail.messages.map((m) => {
                    const route = detail.routes.find((r) => r.MessageId === m.MessageId);
                    return (
                      <Box key={m.MessageId} sx={{ mb: 0.75, p: 1, bgcolor: PANEL2, borderRadius: 1.5, border: `1px solid ${BORDER}` }}>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                          <ChannelIcon channel={m.Channel} sx={{ color: FAINT }} />
                          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{m.FromName || m.FromEmail}</Typography>
                          {m.SourceName && <Typography variant="caption" sx={{ color: FAINT }}>· {m.SourceName}</Typography>}
                          <Typography variant="caption" sx={{ color: FAINT }}>· {fmtDateTime(m.SentAt)}</Typography>
                          {m.SourceLink && <Link href={m.SourceLink} target="_blank" rel="noopener" sx={{ fontSize: 11 }}>source</Link>}
                          <Box sx={{ flex: 1 }} />
                          {route && (
                            <Typography variant="caption" sx={{ color: "#7e22ce", display: "flex", alignItems: "center", gap: 0.4 }}>
                              <AltRouteIcon sx={{ fontSize: 12 }} /> {route.Decision}
                            </Typography>
                          )}
                        </Box>
                        <Typography variant="body2" sx={{ color: INK }}>{m.Subject}</Typography>
                        {/* full body, scrolled in place - mail is stored whole now, not a 255-char preview */}
                        <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block",
                          maxHeight: 220, overflowY: "auto", "&::-webkit-scrollbar": { width: 8 },
                          "&::-webkit-scrollbar-thumb": { background: "#d6dae2", borderRadius: 99 } }}>
                          {cleanText(m.BodyText)}
                        </Typography>
                      </Box>
                    );
                  })}
                  {!detail.messages.length && <Typography variant="caption" sx={{ color: FAINT }}>Manually created — no source messages.</Typography>}
                </Block>

                <Block title={`Agent runs · ${detail.runs.length}`}>
                  {detail.runs.map((r) => (
                    <Box key={r.RunId} sx={{ mb: 0.75, p: 1, bgcolor: r.Status === "running" ? "#fff8e6" : PANEL2, borderRadius: 1.5, border: `1px solid ${BORDER}` }}>
                      <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                        <SmartToyIcon sx={{ fontSize: 13, color: "#7e22ce" }} />
                        <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>run {r.RunId} · {r.AgentName} · {r.Status}</Typography>
                        {r.Status === "running" && <CircularProgress size={11} />}
                        <Typography variant="caption" sx={{ color: FAINT }}>· {timeAgo(r.StartedAt)} · by {r.DispatchedBy}</Typography>
                      </Box>
                      <RunTrace traceJson={r.TraceJson} running={r.Status === "running"} />
                      {r.Result && <Typography variant="caption" sx={{ mt: 0.25, whiteSpace: "pre-wrap", color: "#15803d", display: "block" }}>{r.Result}</Typography>}
                      {r.DiffText && <Box sx={{ mt: 0.75 }}><DiffBlock text={r.DiffText} /></Box>}
                      {r.LastError && <Alert severity="error" sx={{ mt: 0.5, py: 0 }}>{r.LastError}</Alert>}
                    </Box>
                  ))}
                  {/* the one place work starts: who, on which model, with what prompt */}
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                    <AgentPicker agents={agents} models={models} agent={run.agent} model={run.model}
                      onAgent={(a) => setRun({ ...run, agent: a, model: "" })} onModel={(m) => setRun({ ...run, model: m })} />
                    <TextField sx={{ flex: 1, minWidth: 220 }} placeholder="Prompt for this run (optional — it already has the task)"
                      value={run.instruction} onChange={(e) => setRun({ ...run, instruction: e.target.value })} />
                    <Button variant="contained" size="small" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />}
                      onClick={runAgent}>Run agent</Button>
                  </Box>
                  <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                    Runs the full lifecycle: GitHub issue → the agent works it → report → close or escalate to you.
                  </Typography>
                </Block>

                <Block title="Activity">
                  {detail.comments.map((c) => <CommentLine key={c.CommentId} c={c} />)}
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                    <TextField fullWidth placeholder="Add a note (humans only)" value={comment} onChange={(e) => setComment(e.target.value)} onKeyDown={(e) => e.key === "Enter" && post()} />
                    <Button size="small" onClick={post}>Post</Button>
                  </Box>
                  {/* talk to the agent: resumes its claude session; the reply lands above */}
                  <Box sx={{ display: "flex", gap: 1, mt: 1, p: 1, bgcolor: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: 1.5 }}>
                    <SmartToyIcon sx={{ fontSize: 17, color: "#7e22ce", alignSelf: "center" }} />
                    <TextField fullWidth placeholder="Message the agent — it resumes its session and replies here"
                      value={chat} onChange={(e) => setChat(e.target.value)} onKeyDown={(e) => e.key === "Enter" && messageAgent()}
                      sx={{ bgcolor: "#fff" }} />
                    <Button size="small" variant="contained" disableElevation sx={{ bgcolor: "#7e22ce", "&:hover": { bgcolor: "#6b21a8" } }}
                      onClick={messageAgent}>Send</Button>
                  </Box>
                </Block>
              </Box>
            </>
          )}
        </Box>
      </Box>

      {/* ── new task dialog ───────────────────────────────────────────── */}
      <Dialog open={newOpen} onClose={() => setNewOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New task</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: "8px !important" }}>
          <TextField label="Title" value={nt.Title} onChange={(e) => setNt({ ...nt, Title: e.target.value })} autoFocus />
          <TextField label="Summary" value={nt.Summary} multiline minRows={2} onChange={(e) => setNt({ ...nt, Summary: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Select fullWidth value={nt.Kind} onChange={(e) => setNt({ ...nt, Kind: e.target.value })}>
              {["general", "coding", "reply", "triage"].map((k) => <MenuItem key={k} value={k}>{k}</MenuItem>)}
            </Select>
            <Select fullWidth value={nt.Priority} onChange={(e) => setNt({ ...nt, Priority: e.target.value })}>
              {PRIORITIES.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!nt.Title.trim()} onClick={create}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// An agent's answer can be thousands of characters - show the first screenful, keep the
// rest one click away, so the thread stays readable.
const CommentLine = ({ c }) => {
  const [open, setOpen] = useState(false);
  const body = String(c.Body || "");
  const long = body.length > 420;
  return (
    <Box sx={{ mb: 0.6 }}>
      <Typography variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap" }}>
        <b style={{ color: c.ActorType === "agent" ? "#7e22ce" : "#4f46e5" }}>{c.Actor}</b>
        <span style={{ color: "#98a1b3", fontSize: 11 }}> {timeAgo(c.CreatedAt)}</span> — {long && !open ? `${body.slice(0, 420)}…` : body}
      </Typography>
      {long && (
        <Typography variant="caption" onClick={() => setOpen(!open)}
          sx={{ color: "#4f46e5", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
          {open ? "show less ↑" : `show all ${body.length.toLocaleString()} chars ↓`}
        </Typography>
      )}
    </Box>
  );
};

const Block = ({ title, children }) => (
  <Box sx={{ mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>{title}</Typography>
    <Box sx={{ mt: 0.25 }}>{children}</Box>
  </Box>
);
