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
import { ChannelIcon, StateChip, stateOf, AgentPicker, useAgents, RunTrace, DiffBlock, CoderReport, timeAgo, fmtDateTime, cleanText, Empty, FilterPills } from "./ui.jsx";
import TerminalIcon from "@mui/icons-material/Terminal";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import { Autocomplete } from "@mui/material";
import { TerminalPane } from "./TerminalView.jsx";

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

const STATUSES = ["open", "in_progress", "waiting", "done", "dropped"];
// the filters ARE the states now - no more guessing how Status and ReviewStatus combine
const STATE_FILTERS = [
  { key: "", label: "all" },
  { key: "needs_you", label: "needs you", c: PILL_COLORS.amber },
  { key: "working", label: "working", c: PILL_COLORS.purple },
  { key: "done", label: "done", c: PILL_COLORS.green },
];
const PRIORITIES = ["low", "normal", "high", "urgent"];

// Compact modern select styling shared by the detail-header dropdowns.
const selSx = { fontSize: 12.5, bgcolor: "#fff", borderRadius: 2,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: "#e5e8ee" },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#c9cff0" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: "#4f46e5" } };

export default function TasksView({ selected, onSelect, onChanged, autostart, onAutostarted }) {
  const [tasks, setTasks] = useState(null);
  const [filter, setFilter] = useState("");            // "" = all; the rest are derived states
  const [detail, setDetail] = useState(null);
  const { agents, models } = useAgents();
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
  const [run, setRun] = useState({ agent: "coder", model: "", instruction: "" });
  const [comment, setComment] = useState("");
  const [wrapping, setWrapping] = useState(false);   // declared up here: the poll effect below reads it
  const pollRef = useRef(null);

  // fetch everything once and filter on the derived state - the server only knows raw
  // Status, and the state a person cares about is a combination of three columns
  const loadTasks = useCallback(async () => {
    try { setTasks((await api.get("/api/tasks")).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load tasks"); }
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/api/tasks/${id}`);
      setDetail(data);
      // opened a task the current filter hides (e.g. from the Board)? widen to "all" so
      // the list and the detail never contradict each other
      setFilter((f) => (f && stateOf({ ...data.task, ReviewStatus: (data.reviews || [])[0]?.Status }).key !== f ? "" : f));
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
    if ((running || wrapping) && selected) pollRef.current = setInterval(() => loadDetail(selected), 3000);
    return () => clearInterval(pollRef.current);
  }, [detail, selected, loadDetail, wrapping]);

  const patch = async (fields) => { await api.patch(`/api/tasks/${selected}`, fields); loadDetail(selected); loadTasks(); onChanged?.(); };
  const create = async () => {
    const { data } = await api.post("/api/tasks", nt);
    setNewOpen(false); setNt({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
    setFilter(""); loadTasks(); onSelect(data.taskId);
  };
  const post = async () => {
    if (!comment.trim()) return;
    await api.post(`/api/tasks/${selected}/comments`, { body: comment });
    setComment(""); loadDetail(selected);
  };
  // "We're done": the agent writes its own closing summary, it files under What the agent
  // did, and the task closes. No copy-pasting out of the terminal.
  const wrapUp = async () => {
    if (!term) return;
    setWrapping(true);
    try { await api.post(`/api/terminals/${term.sid}/wrap`, { task_id: selected, close: true }); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not ask the agent to wrap up"); setWrapping(false); }
  };
  useEffect(() => { setWrapping(false); }, [selected]);
  useEffect(() => {
    if (!wrapping || detail?.task?.Status !== "done") return;
    setWrapping(false); loadTasks(); onChanged?.();     // the list still said "agent working"
  }, [wrapping, detail, loadTasks, onChanged]);

  // The agent stopped because it needs a person. Answering IS the work: "go ahead" hands
  // the same task back to the same agent with your words attached.
  const [approve, setApprove] = useState("");
  const [handoff, setHandoff] = useState(false);
  useEffect(() => { setHandoff(false); }, [selected]);
  const goAhead = async (rid) => {
    await api.post(`/api/reviews/${rid}/decide`, { verb: "go_ahead", note: approve.trim() || null });
    setApprove(""); setTimeout(() => { loadDetail(selected); loadTasks(); onChanged?.(); }, 800);
  };
  const notATask = async () => {
    await api.post(`/api/tasks/${selected}/not-a-task`);
    onSelect(null); loadTasks(); onChanged?.();
  };
  // The task's own session - the only terminal in the app. undefined means "not looked
  // yet", null means "looked, none running": the difference decides whether we may
  // auto-start one, so they must not collapse into each other.
  const [term, setTerm] = useState(undefined);
  const findTerm = useCallback(async (tid) => {
    if (!tid) { setTerm(null); return; }
    try {
      const rows = (await api.get("/api/terminals")).data.data || [];
      setTerm(rows.find((x) => x.taskId === tid && x.alive) || null);
    } catch { setTerm(null); }
  }, []);
  useEffect(() => { setTerm(undefined); findTerm(selected); }, [selected, findTerm]);
  const openTerm = useCallback(async (body) => {
    try { const { data } = await api.post("/api/terminals", body); setTerm(data); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not start a terminal"); }
  }, []);
  // "New task -> live session" lands here: put the CLI on it once we know this task has no
  // session already, so a reload never spawns a second one
  useEffect(() => {
    if (!autostart || autostart.taskId !== selected || term !== null || !detail) return;
    onAutostarted?.();
    openTerm({ agent: autostart.agent || run.agent, model: autostart.model || run.model || null,
      task_id: selected, repo: repoOf(detail.task), seed: true });
  }, [autostart, selected, term, detail, openTerm, onAutostarted, run.agent]);


  const t = detail?.task;
  const shown = (tasks || []).filter((x) => !filter || stateOf(x).key === filter);
  const report = [...(detail?.comments || [])].reverse().find(
    (c) => c.ActorType === "agent" && String(c.Body || "").replace("CODER REPORT", "").trim()
      && String(c.Body || "").startsWith("CODER REPORT"));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const liveRun = (detail?.runs || []).find((r) => r.Status === "running");
  const esc = (detail?.reviews || []).find((r) => r.Kind === "escalation" && r.Status === "pending");
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      {/* ── list: one anchored panel - filter header on top, rows scroll inside ── */}
      <Box sx={{ width: 340, flexShrink: 0 }}>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
        <Box sx={{ ...card, p: 0, overflow: "hidden", display: "flex", flexDirection: "column",
          height: "calc(100vh - 118px)", minHeight: 420 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.75,
            borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2, flexShrink: 0 }}>
            <FilterPills options={STATE_FILTERS} value={filter} onChange={setFilter} />
            <Box sx={{ flex: 1 }} />
            <Button size="small" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => setNewOpen(true)}>New</Button>
          </Box>
          <Box sx={{ overflowY: "auto", flex: 1 }}>
            {!tasks ? <CircularProgress size={20} sx={{ m: 2 }} /> : !shown.length ? <Empty>No tasks here.</Empty> : shown.map((task) => (
              <Box key={task.TaskId} onClick={() => onSelect(task.TaskId)}
                sx={{ px: 1.25, py: 0.75, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
                  bgcolor: selected === task.TaskId ? "#eef0ff" : "transparent",
                  borderLeft: `3px solid ${selected === task.TaskId ? "#4f46e5" : "transparent"}`,
                  "&:hover": { bgcolor: selected === task.TaskId ? "#eef0ff" : "#f7f8fa" } }}>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                  <Typography variant="caption" sx={{ ...mono, color: "#4f46e5", fontWeight: 700 }}>{task.ref}</Typography>
                  <StateChip task={task} />
                  {task.Priority === "urgent" && <Chip size="small" label="urgent" sx={{ bgcolor: "#fdecec", color: "#b91c1c", height: 17, fontSize: 10 }} />}
                  {String(task.Assignee || "").startsWith("agent:") && <SmartToyIcon sx={{ fontSize: 13, color: "#7e22ce" }} />}
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" sx={{ color: FAINT }}>{timeAgo(task.CreatedAt)}</Typography>
                </Box>
                <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 500, mt: 0.1 }}>{task.Title}</Typography>
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
                  <StateChip task={{ ...t, ReviewStatus: (detail.reviews || [])[0]?.Status,
                    RunStatus: (detail.runs || [])[0]?.Status }} />
                  <Select value={t.Status} onChange={(e) => patch({ Status: e.target.value })} sx={selSx}
                    title="the raw status, if you need to move it by hand">
                    {STATUSES.map((s) => <MenuItem key={s} value={s} sx={{ fontSize: 12 }}>{s}</MenuItem>)}
                  </Select>
                  <Select value={t.Priority} onChange={(e) => patch({ Priority: e.target.value })} sx={selSx}>
                    {PRIORITIES.map((p) => <MenuItem key={p} value={p} sx={{ fontSize: 12 }}>{p}</MenuItem>)}
                  </Select>
                  {t.Status !== "done" && (
                    <Button size="small" variant="contained" disableElevation sx={{ bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                      onClick={() => patch({ Status: "done" })}>Mark done — I took care of it</Button>
                  )}
                  <Button size="small" variant="outlined" startIcon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                    sx={{ bgcolor: PANEL, color: handoff ? "#4f46e5" : undefined }}
                    onClick={() => setHandoff((h) => !h)}
                    title="Not ours to do? Send it to the person whose job it is">Hand off</Button>
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
                </Box>
              </Box>
              <Box sx={{ px: 2, py: 1.5, overflowY: "auto", flex: 1 }}>
                {handoff && (
                  <Box sx={{ ...card, p: 1.5, mb: 1.5, bgcolor: PANEL2 }}>
                    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>
                      Hand this to a person
                    </Typography>
                    <Handoff taskId={selected} onSent={() => { loadDetail(selected); loadTasks(); }} />
                  </Box>
                )}
                {esc && (
                  <Box sx={{ bgcolor: "#fff8e6", border: "1px solid #f3ddb8", borderRadius: 2, px: 1.5, py: 1.25, mb: 1.5 }}>
                    <Typography variant="body2" sx={{ color: "#b45309", fontWeight: 700 }}>The agent needs you before it goes on</Typography>
                    <Typography variant="body2" sx={{ color: DIM, mt: 0.25 }}>{esc.Reason}</Typography>
                    <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center", flexWrap: "wrap" }}>
                      <TextField size="small" sx={{ flex: 1, minWidth: 240, bgcolor: "#fff" }} value={approve}
                        placeholder="Anything to tell it with your approval (optional)"
                        onChange={(e) => setApprove(e.target.value)} onKeyDown={(e) => e.key === "Enter" && goAhead(esc.ReviewId)} />
                      <Button size="small" variant="contained" disableElevation
                        sx={{ bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                        onClick={() => goAhead(esc.ReviewId)}>Go ahead — approved</Button>
                    </Box>
                  </Box>
                )}
                {/* THE SESSION IS THE PAGE. Your CLI, in this task's repo, with the task in
                    its lap - you type into it like any other terminal. Everything below is
                    reference material about the same task, folded away. */}
                {term ? (
                  <>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
                      <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1, minWidth: 0 }} noWrap>
                        {term.cmd} · {term.cwd}
                      </Typography>
                      <Button size="small" variant="contained" disableElevation disabled={wrapping}
                        startIcon={wrapping ? <CircularProgress size={11} sx={{ color: "#fff" }} />
                          : <DoneAllIcon sx={{ fontSize: 15 }} />}
                        sx={{ fontSize: 11.5, bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                        onClick={wrapUp}>
                        {wrapping ? "wrapping up…" : "Done — wrap it up"}
                      </Button>
                      <Button size="small" sx={{ fontSize: 11 }}
                        onClick={async () => { await api.delete("/api/terminals/" + term.sid).catch(() => {}); setTerm(null); }}>
                        end session
                      </Button>
                    </Box>
                    <TerminalPane sid={term.sid} height="55vh" onExit={() => findTerm(selected)} />
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#0e7490", display: "block", mt: 0.5 }}>
                        Asked it to wrap up — its summary lands under <b>What the agent did</b> and the task closes itself.
                      </Typography>
                    )}
                  </>
                ) : (
                  <Box sx={{ ...card, p: 2, textAlign: "center", bgcolor: PANEL2 }}>
                    <Typography variant="body2" sx={{ color: DIM, mb: 1.25 }}>
                      Start your CLI on this task — a real session in {repoOf(t) || "the agent's folder"}: its own
                      prompts, its questions, your keystrokes.
                    </Typography>
                    {liveRun && (
                      <Typography variant="caption" sx={{ color: "#b45309", display: "block", mb: 1.25 }}>
                        {liveRun.AgentName} has a run going on this task (run {liveRun.RunId}) — watch it under Earlier
                        runs below. Starting a session here puts a second agent on the same task.
                      </Typography>
                    )}
                    <Box sx={{ display: "flex", justifyContent: "center", gap: 1, flexWrap: "wrap" }}>
                      <AgentPicker agents={agents} models={models} agent={run.agent} model={run.model}
                        onAgent={(a) => setRun({ ...run, agent: a, model: "" })} onModel={(m) => setRun({ ...run, model: m })} />
                      <Button variant="contained" size="small" disableElevation startIcon={<TerminalIcon sx={{ fontSize: 15 }} />}
                        onClick={() => openTerm({ agent: run.agent, model: run.model || null, task_id: selected,
                          repo: repoOf(t), seed: true })}>
                        Start session
                      </Button>
                    </Box>
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
                      Everything the agent does happens here, in the open — you can read it, interrupt it and answer it.
                    </Typography>
                  </Box>
                )}

                {/* the summary the agent left behind, once it has finished */}
                {report && (
                  <Block title="What the agent did">
                    <Box sx={{ bgcolor: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: 1.5, px: 1.25, py: 0.5 }}>
                      <CoderReport body={report.Body} />
                    </Box>
                    {diffRun && <Box sx={{ mt: 0.75 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                  </Block>
                )}

                {t.Summary && (
                  <Fold title="The ask">
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: DIM }}>{cleanText(t.Summary)}</Typography>
                  </Fold>
                )}

                <Fold title={`Messages · ${detail.messages.length}`}>
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
                        <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block",
                          maxHeight: 220, overflowY: "auto", "&::-webkit-scrollbar": { width: 8 },
                          "&::-webkit-scrollbar-thumb": { background: "#d6dae2", borderRadius: 99 } }}>
                          {cleanText(m.BodyText)}
                        </Typography>
                      </Box>
                    );
                  })}
                  {!detail.messages.length && <Typography variant="caption" sx={{ color: FAINT }}>Manually created — no source messages.</Typography>}
                </Fold>

                {/* runs from before sessions (and any API-driven run) keep their trace here */}
                {detail.runs.length > 0 && (
                  <Fold title={`Earlier runs · ${detail.runs.length}`}>
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
                        {r.LastError && <Alert severity="error" sx={{ mt: 0.5, py: 0 }}>{r.LastError}</Alert>}
                      </Box>
                    ))}
                  </Fold>
                )}

                <Fold title={`Notes & history · ${detail.comments.length}`}>
                  <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", tableLayout: "auto" }}>
                    <tbody>{detail.comments.map((c) => <CommentRow key={c.CommentId} c={c} />)}</tbody>
                  </Box>
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                    <TextField fullWidth placeholder="Add a note (humans only)" value={comment}
                      onChange={(e) => setComment(e.target.value)} onKeyDown={(e) => e.key === "Enter" && post()} />
                    <Button size="small" onClick={post}>Post</Button>
                  </Box>
                </Fold>
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

// Some work is not ours to do: hand it to the person whose job it is, with the AI writing
// the forward message out of the task's own context (systems, ids, errors) so you are not
// retyping the thread into an email.
const Handoff = ({ taskId, onSent }) => {
  const [to, setTo] = useState("");
  const [channel, setChannel] = useState("email");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [people, setPeople] = useState([]);
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get("/api/people").then(({ data }) => setPeople(data.data || [])).catch(() => {}); }, []);
  const call = async (body) => (await api.post(`/api/tasks/${taskId}/handoff`, body)).data;
  const draft = async () => {
    setBusy("draft"); setErr("");
    try { setText((await call({ to, channel, draft_only: true })).draft); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not write the message"); }
    setBusy("");
  };
  const send = async () => {
    setBusy("send"); setErr("");
    try { const d = await call({ to, channel, text }); setSent(d.sent); onSent?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not send it"); }
    setBusy("");
  };
  if (sent) return (
    <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>
      ✓ sent to {(sent.to || []).join(", ") || "the chat"} by {sent.channel}
    </Typography>
  );
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Select size="small" value={channel} onChange={(e) => setChannel(e.target.value)} sx={{ ...selSx, minWidth: 110 }}>
          <MenuItem value="email" sx={{ fontSize: 12.5 }}>email</MenuItem>
          <MenuItem value="teams" sx={{ fontSize: 12.5 }}>Teams chat</MenuItem>
        </Select>
        <Autocomplete freeSolo size="small" sx={{ flex: 1, minWidth: 220 }} options={people.map((p) => p.Email)}
          value={to} onInputChange={(_e, v) => setTo(v || "")}
          getOptionLabel={(o) => String(o)}
          renderOption={(props, o) => {
            const p = people.find((x) => x.Email === o);
            return <li {...props} style={{ fontSize: 12.5 }}>{p?.Name || o}<span style={{ color: FAINT }}>&nbsp;· {o}</span></li>;
          }}
          renderInput={(params) => <TextField {...params} placeholder="who should own this — email address" />} />
        <Button size="small" onClick={draft} disabled={!!busy}>
          {busy === "draft" ? <CircularProgress size={12} /> : text ? "Rewrite" : "Draft with AI"}
        </Button>
      </Box>
      <TextField multiline minRows={4} size="small" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="What they need to know. Draft with AI writes it from this task's own context — you edit before it goes." />
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Button size="small" variant="contained" disableElevation disabled={!!busy || !to.trim() || !text.trim()}
          startIcon={busy === "send" ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <ForwardToInboxIcon sx={{ fontSize: 15 }} />}
          onClick={send}>Send it</Button>
        {err && <Typography variant="caption" sx={{ color: "#b91c1c" }}>{err}</Typography>}
      </Box>
    </Box>
  );
};

// The history is a log, so it reads like one: who, when, what - one line each until you
// open it. Agent answers run to thousands of characters and used to bury the page.
const CommentRow = ({ c }) => {
  const [open, setOpen] = useState(false);
  const body = String(c.Body || "").trim();
  const long = body.length > 150 || body.includes("\n");
  return (
    <Box component="tr" sx={{ borderTop: `1px solid ${BORDER}`, verticalAlign: "top",
      "&:hover": { bgcolor: open ? "transparent" : PANEL2 } }}>
      <Box component="td" sx={{ py: 0.6, pr: 1, whiteSpace: "nowrap" }}>
        <Typography variant="caption" sx={{ ...mono, fontWeight: 700, fontSize: 10.5,
          color: c.ActorType === "agent" ? "#7e22ce" : "#4f46e5" }}>{c.Actor}</Typography>
      </Box>
      <Box component="td" sx={{ py: 0.6, pr: 1.25, whiteSpace: "nowrap" }}>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{timeAgo(c.CreatedAt)}</Typography>
      </Box>
      <Box component="td" sx={{ py: 0.6, width: "100%", cursor: long ? "pointer" : "default" }}
        onClick={() => long && setOpen(!open)}>
        <Typography variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap", lineHeight: 1.5,
          ...(open ? {} : { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>
          {body}
        </Typography>
        {long && (
          <Typography variant="caption" sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 10.5 }}>
            {open ? "less ↑" : `${body.length.toLocaleString()} chars ↓`}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

// Reference material about the task: present, but never competing with the session.
const Fold = ({ title, children }) => (
  <Box component="details" sx={{ mt: 1.5 }}>
    <Box component="summary" sx={{ cursor: "pointer", color: ACCENT2, fontSize: 10.5, letterSpacing: 1.5,
      textTransform: "uppercase", fontWeight: 700 }}>{title}</Box>
    <Box sx={{ mt: 0.5 }}>{children}</Box>
  </Box>
);

const Block = ({ title, children }) => (
  <Box sx={{ mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontSize: 10 }}>{title}</Typography>
    <Box sx={{ mt: 0.25 }}>{children}</Box>
  </Box>
);
