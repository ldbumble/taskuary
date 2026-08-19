// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  Drawer, IconButton, Link, MenuItem, Select, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import BlockIcon from "@mui/icons-material/Block";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, selSx, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { Handoff } from "./Handoff.jsx";
import { ChannelIcon, StateChip, stateOf, AgentPicker, useAgents, RunTrace, DiffBlock, CoderReport, timeAgo, fmtDateTime, cleanText, Empty, FilterPills } from "./ui.jsx";
import TerminalIcon from "@mui/icons-material/Terminal";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import PauseCircleIcon from "@mui/icons-material/PauseCircleOutline";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
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
  const [wrapped, setWrapped] = useState(null);      // the closing report, shown where the session was
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
  // "We're done": nothing is typed at the agent. The session closes, its transcript becomes the
  // report (written by the main AI), the responder drafts the reply out of that report, and the
  // result lands right here under where the terminal was.
  const wrapUp = async () => {
    if (!term) return;
    setWrapping("wrap"); setErr("");
    try {
      const { data } = await api.post(`/api/terminals/${term.sid}/wrap`, { task_id: selected, close: true });
      setWrapped({ report: data.report, drafting: data.drafting });
      setTerm(null); loadDetail(selected); loadTasks(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not wrap up the session"); }
    setWrapping(false);
  };
  // Pausing is not finishing: no report, no reply draft, the task stays open. What it worked
  // out becomes a handover note that gets typed into the NEXT session, because a pty has no
  // resumable id - killing the session used to throw all of that away.
  const pause = async () => {
    if (!term) return;
    setWrapping("pause"); setErr("");
    try {
      const { data } = await api.post(`/api/terminals/${term.sid}/pause`, { task_id: selected });
      setWrapped({ note: data.note });
      setTerm(null); loadDetail(selected); loadTasks(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not pause the session"); }
    setWrapping(false);
  };
  useEffect(() => { setWrapping(false); setWrapped(null); }, [selected]);

  const [handoff, setHandoff] = useState(false);
  useEffect(() => { setHandoff(false); }, [selected]);
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
      // an exited session still holds its scrollback (they stay listed ~10 min), and that
      // transcript is exactly what Done and Pause need - dropping it left a task you could
      // not close out because the CLI had finished on its own
      setTerm(rows.find((x) => x.taskId === tid && x.alive) || rows.find((x) => x.taskId === tid) || null);
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
                {/* THE SESSION IS THE PAGE. Your CLI, in this task's repo, with the task in
                    its lap - you type into it like any other terminal. Everything below is
                    reference material about the same task, folded away. */}
                {/* the session just closed: its write-up takes the space the terminal had, so the
                    result of the work is the thing you are looking at */}
                {wrapped ? (
                  <Box sx={{ ...card, bgcolor: wrapped.note ? "#fff8e6" : "#f5f3ff",
                    border: `1px solid ${wrapped.note ? "#f3ddb8" : "#ddd6fe"}` }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      {wrapped.note ? <PauseCircleIcon sx={{ fontSize: 17, color: "#b45309" }} />
                        : <DoneAllIcon sx={{ fontSize: 17, color: "#15803d" }} />}
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, flex: 1 }}>
                        {wrapped.note ? "Paused — here is where it got to" : "Session closed — here is what it did"}
                      </Typography>
                      <Button size="small" sx={{ fontSize: 11 }} onClick={() => setWrapped(null)}>dismiss</Button>
                    </Box>
                    <CoderReport body={wrapped.report || wrapped.note} />
                    <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 1 }}>
                      {wrapped.note
                        ? "Nothing was sent and nothing closed — the task is still open. Start a session again and the agent is handed this note, so it carries on instead of starting over."
                        : wrapped.drafting
                        ? "The reply to whoever wrote in is drafted and waiting in Review — approving it sends it and closes this task."
                        : "Nothing to reply to on this task, so it closed here."}
                    </Typography>
                  </Box>
                ) : term ? (
                  <>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
                      <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1, minWidth: 0 }} noWrap>
                        {term.cmd} · {term.cwd}
                      </Typography>
                      {!term.alive && (
                        <Chip size="small" label="exited — its output is still here"
                          sx={{ height: 18, fontSize: 10, bgcolor: PANEL2, border: `1px solid ${BORDER}`, color: DIM }} />
                      )}
                      <Button size="small" variant="contained" disableElevation disabled={!!wrapping}
                        startIcon={wrapping === "wrap" ? <CircularProgress size={11} sx={{ color: "#fff" }} />
                          : <DoneAllIcon sx={{ fontSize: 15 }} />}
                        sx={{ fontSize: 11.5, bgcolor: "#15803d", "&:hover": { bgcolor: "#166534" } }}
                        onClick={wrapUp}>
                        {wrapping === "wrap" ? "wrapping up…" : "Done — wrap it up"}
                      </Button>
                      <Button size="small" disabled={!!wrapping} sx={{ fontSize: 11, color: DIM }}
                        startIcon={wrapping === "pause" ? <CircularProgress size={11} /> : <PauseCircleIcon sx={{ fontSize: 15 }} />}
                        title="Stop for now without losing what it worked out - the next session is handed its note"
                        onClick={pause}>
                        {wrapping === "pause" ? "saving what it found…" : term.alive ? "Pause — save what it found" : "Save what it found"}
                      </Button>
                    </Box>
                    <TerminalPane sid={term.sid} height="55vh" onExit={() => findTerm(selected)} />
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#0e7490", display: "block", mt: 0.5 }}>
                        {wrapping === "pause" ? "Writing the handover note from what is on screen, then stopping."
                          : "Closing the session and writing up what is on screen — the agent is not asked anything."}
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

      {/* ── hand off: a right-hand drawer, so it cannot hide above a tall terminal ── */}
      <Drawer anchor="right" open={!!handoff && !!t} onClose={() => setHandoff(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 460 }, p: 2, bgcolor: PANEL } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <ForwardToInboxIcon sx={{ fontSize: 18, color: "#4f46e5" }} />
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>Hand this to a person</Typography>
          <IconButton size="small" onClick={() => setHandoff(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {t?.Title}
        </Typography>
        {handoff && <Handoff taskId={selected} onSent={() => { loadDetail(selected); loadTasks(); }} />}
      </Drawer>

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
