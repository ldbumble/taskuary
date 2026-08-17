// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  Link, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import BlockIcon from "@mui/icons-material/Block";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { ChannelIcon, TaskStatusChip, ActionChip, PromptBlock, DiffBlock, timeAgo, fmtDateTime, cleanText, Empty, FilterPills } from "./ui.jsx";

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

export default function TasksView({ selected, onSelect, onChanged }) {
  const [tasks, setTasks] = useState(null);
  const [filter, setFilter] = useState("open");        // default: real work, not history
  const [detail, setDetail] = useState(null);
  const [agents, setAgents] = useState([]);
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
  const [dispatchAgent, setDispatchAgent] = useState("responder");
  const [instruction, setInstruction] = useState("");
  const [comment, setComment] = useState("");
  const pollRef = useRef(null);

  const loadTasks = useCallback(async () => {
    try { setTasks((await api.get("/api/tasks", { params: filter ? { status: filter } : {} })).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load tasks"); }
  }, [filter]);

  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    try { setDetail((await api.get(`/api/tasks/${id}`)).data); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load task"); }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);
  useEffect(() => {
    api.get("/api/agents").then(({ data }) => {
      const rows = data.data || [];
      setAgents(rows);
      // FanApp had a fixed 'responder'; here the roster is user-config - default to what exists
      if (rows.length) setDispatchAgent((cur) => (rows.some((a) => a.Name === cur) ? cur : rows[0].Name));
    }).catch(() => {});
  }, []);
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
  const dispatch = async () => {
    await api.post(`/api/tasks/${selected}/dispatch`, { agent: dispatchAgent, instruction: instruction || null });
    setInstruction(""); setTimeout(() => loadDetail(selected), 800);
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
  const sendToCoder = async () => {
    await api.post(`/api/tasks/${selected}/code`);
    setTimeout(() => { loadDetail(selected); loadTasks(); }, 800);   // run row appears; polling takes over
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
                  <Button size="small" variant="outlined" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />}
                    sx={{ color: "#7e22ce", borderColor: "#7e22ce55", bgcolor: PANEL }} onClick={sendToCoder}>Send to coder</Button>
                  <Button size="small" color="error" variant="outlined" startIcon={<BlockIcon sx={{ fontSize: 14 }} />}
                    sx={{ bgcolor: PANEL }} onClick={notATask}>Not a task</Button>
                </Box>
                <Typography variant="caption" sx={{ color: FAINT }}>
                  {t.Kind} · from {t.Source} · assignee {t.Assignee || "—"} · created {timeAgo(t.CreatedAt)} by {t.CreatedBy}
                </Typography>
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
                        <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block" }}>{cleanText(m.BodyText).slice(0, 400)}</Typography>
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
                      {(JSON.parse(r.TraceJson || "[]")).map((ev, i) => ev.kind === "prompt"
                        ? <PromptBlock key={i} text={ev.detail} />
                        : (
                          <Typography key={i} variant="caption" sx={{ ...mono, display: "block", color: FAINT, fontSize: 10.5 }}>
                            {ev.at.slice(11)} [{ev.kind}] {ev.name}: {ev.detail.slice(0, 120)}
                          </Typography>
                        ))}
                      {r.Result && <Typography variant="caption" sx={{ mt: 0.25, whiteSpace: "pre-wrap", color: "#15803d", display: "block" }}>{r.Result}</Typography>}
                      {r.DiffText && <Box sx={{ mt: 0.75 }}><DiffBlock text={r.DiffText} /></Box>}
                      {r.LastError && <Alert severity="error" sx={{ mt: 0.5, py: 0 }}>{r.LastError}</Alert>}
                    </Box>
                  ))}
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                    <Select value={dispatchAgent} onChange={(e) => setDispatchAgent(e.target.value)} sx={selSx}>
                      {agents.map((a) => <MenuItem key={a.Name} value={a.Name} sx={{ fontSize: 12 }}>{a.Name} ({a.Runner})</MenuItem>)}
                    </Select>
                    <TextField fullWidth placeholder="Instruction (optional)" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
                    <Button variant="contained" size="small" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />} onClick={dispatch}>Dispatch</Button>
                  </Box>
                </Block>

                <Block title="Activity">
                  {detail.comments.map((c) => (
                    <Typography key={c.CommentId} variant="body2" sx={{ mb: 0.4, color: DIM }}>
                      <b style={{ color: c.ActorType === "agent" ? "#7e22ce" : "#4f46e5" }}>{c.Actor}</b>
                      <span style={{ color: "#98a1b3", fontSize: 11 }}> {timeAgo(c.CreatedAt)}</span> — {c.Body}
                    </Typography>
                  ))}
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

const Block = ({ title, children }) => (
  <Box sx={{ mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>{title}</Typography>
    <Box sx={{ mt: 0.25 }}>{children}</Box>
  </Box>
);
