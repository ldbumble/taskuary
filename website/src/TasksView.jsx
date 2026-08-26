// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress,
  Drawer, IconButton, Link, MenuItem, Select, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import BlockIcon from "@mui/icons-material/Block";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import DifferenceIcon from "@mui/icons-material/Difference";
import RefreshIcon from "@mui/icons-material/Refresh";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, selSx, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { RepoPicker } from "./RepoPicker.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon, StateChip, stateOf, AgentPicker, useAgents, RunTrace, DiffBlock, DiffFiles, CoderReport, timeAgo, fmtDateTime, cleanText, Empty, FilterPills, ConfirmDelete } from "./ui.jsx";
import TerminalIcon from "@mui/icons-material/Terminal";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import PauseCircleIcon from "@mui/icons-material/PauseCircleOutline";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import { Divider, ListItemIcon, ListItemText, Menu } from "@mui/material";
import { TerminalPane } from "./TerminalView.jsx";

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

const STATUSES = ["open", "in_progress", "waiting", "done", "dropped"];
// CATEGORY is where a task is; the chip on the row says what it needs. Filtering by "needs
// you" and "working" separately made those two look like opposites, so a task whose agent
// picked it up vanished out of the bucket you were watching - and a task sitting in "needs
// you" WITH an agent thinking on it read as a contradiction, because it was one. One
// in-progress bucket holds everything still open; the label inside it is what changes.
const STATE_FILTERS = [
  { key: "", label: "all" },
  { key: "live", label: "in progress", c: PILL_COLORS.working },
  { key: "done", label: "done", c: PILL_COLORS.done },
];
// everything still on somebody's plate - yours or an agent's. Dropped is neither, and only
// ever shows under "all".
const inBucket = (t, key) => (key === "live" ? !["done", "dropped"].includes(stateOf(t).key)
                                             : stateOf(t).key === key);
const PRIORITIES = ["low", "normal", "high", "urgent"];
// what a task IS decides which machinery works it: coding gets a repo session, a reply
// gets the responder and the Review queue, general is your own list
const KINDS = ["general", "coding", "reply"];

export default function TasksView({ selected, onSelect, onChanged, autostart, onAutostarted, onGoReview, active = true }) {
  const [tasks, setTasks] = useState(null);
  // "live" on arrival: what is still on somebody's plate is what you came here for. "all"
  // opens on a list whose top is whatever finished most recently. ("" = all; the rest derive.)
  const [filter, setFilter] = useState("live");
  const [detail, setDetail] = useState(null);
  const { agents, models } = useAgents();
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
  const [run, setRun] = useState({ agent: "", model: "", instruction: "" });   // "" = the roster's default (served first)
  const [comment, setComment] = useState("");
  const [wrapping, setWrapping] = useState(false);   // declared up here: the poll effect below reads it
  const [wrapped, setWrapped] = useState(null);      // the closing report, shown where the session was
  const [diffOpen, setDiffOpen] = useState(false);   // the pre-push review, in its own drawer
  const [diff, setDiff] = useState(null);
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
      setFilter((f) => (f && !inBucket({ ...data.task, Session: data.session,
                                         ReviewStatus: (data.reviews || [])[0]?.Status }, f) ? "" : f));
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load task"); }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);
  // ...and keep it honest. The list was fetched ONCE, so a task whose agent picked it up
  // kept wearing "needs you" - and the pill counts kept agreeing with it - until something
  // else happened to reload. "Agent working" is a fact with a 45-second shelf life (a live
  // session that goes quiet is waiting on you); a row that states it has to be re-asked.
  // Only while this tab is the one on screen: it stays mounted behind the others.
  useEffect(() => {
    if (!active) return;
    const id = setInterval(loadTasks, 5000);
    return () => clearInterval(id);
  }, [active, loadTasks]);
  // the roster is user-config - default to whatever actually exists
  useEffect(() => {
    if (agents.length && !agents.includes(run.agent)) setRun((r) => ({ ...r, agent: agents[0] }));
  }, [agents, run.agent]);
  useEffect(() => { loadDetail(selected); }, [selected, loadDetail]);
  useEffect(() => {
    // a LIVE SESSION counts as much as a headless run here: the header chip is derived from
    // how long the pty has been quiet, so without re-asking it froze on whatever it said
    // when the task was opened - "needs you" over an agent that was mid-thought
    const running = (detail?.runs || []).some((r) => r.Status === "running") || detail?.session?.alive;
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
    if (!canWrap) return;
    setWrapping("wrap"); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${selected}/wrap`, { close: true });
      setWrapped({ report: data.report, drafting: data.drafting });
      setTerm(null); loadDetail(selected); loadTasks(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not wrap up the session"); }
    setWrapping(false);
  };
  // Pausing is not finishing: no report, no reply draft, the task stays open. What it worked
  // out becomes a handover note that gets typed into the NEXT session, because a pty has no
  // resumable id - killing the session used to throw all of that away.
  const pause = async () => {
    if (!canWrap) return;
    setWrapping("pause"); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${selected}/pause`, {});
      setWrapped({ note: data.note });
      setTerm(null); loadDetail(selected); loadTasks(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not pause the session"); }
    setWrapping(false);
  };
  useEffect(() => { setWrapping(false); setWrapped(null); }, [selected]);

  const [handoff, setHandoff] = useState(false);
  const [reshape, setReshape] = useState(false);
  const [repoPick, setRepoPick] = useState(false);
  const [menuEl, setMenuEl] = useState(null);
  useEffect(() => { setHandoff(false); setReshape(false); setRepoPick(false); setDiffOpen(false); }, [selected]);
  // asked when the drawer opens, and only then: shelling out to git on every task poll would
  // spend a subprocess a second on an answer nobody is looking at
  const loadDiff = useCallback(async (id) => {
    setDiff(null);
    try { setDiff((await api.get(`/api/tasks/${id}/diff`)).data); }
    catch (e) { setDiff({ files: [], why: e?.response?.data?.detail || "Could not read the checkout" }); }
  }, []);
  useEffect(() => { if (diffOpen && selected) loadDiff(selected); }, [diffOpen, selected, loadDiff]);
  // A fold DROPS the task you were looking at, so follow the work to the survivor - staying
  // put would leave the detail pane on a task that no longer holds anything.
  const reshaped = (r) => {
    loadTasks(); onChanged?.();
    if (r?.dropped === selected) onSelect(r.merged); else loadDetail(selected);
  };
  // one click, inside a MENU, where the pointer is already moving - and it deletes the task and
  // writes a standing rule about its sender. The two sharpest things in the app were the two
  // easiest to hit by accident.
  const [confirmNAT, setConfirmNAT] = useState(false);
  const notATask = async () => {
    await api.post(`/api/tasks/${selected}/not-a-task`);
    onSelect(null); await loadTasks(); onChanged?.();
  };
  // The task's own session - the only terminal in the app. undefined means "not looked
  // yet", null means "looked, none running": the difference decides whether we may
  // auto-start one, so they must not collapse into each other.
  const [term, setTerm] = useState(undefined);
  // Wrapping up belongs to the TASK, not to the pty. An exited session is dropped after ten
  // minutes, and with it went the only handle these buttons had - so a task whose CLI had
  // finished on its own could never be closed out. The transcript is filed when a session ends.
  const canWrap = !!term || !!detail?.transcript;
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
    catch (e) {
      const msg = e?.response?.data?.detail || "Could not start a terminal";
      setErr(msg);
      // the repo guard refused (right repo, no local path): the fix IS the picker, so open it
      // here instead of sending the user off to read the error's directions
      if (/no local path/i.test(msg)) setRepoPick(true);
    }
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
  const shown = (tasks || []).filter((x) => !filter || inBucket(x, filter));
  const report = [...(detail?.comments || [])].reverse().find(
    (c) => c.ActorType === "agent" && String(c.Body || "").replace("CODER REPORT", "").trim()
      && String(c.Body || "").startsWith("CODER REPORT"));
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const liveRun = (detail?.runs || []).find((r) => r.Status === "running");
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      {/* ── list: one anchored panel - filter header on top, rows scroll inside ── */}
      {/* 372, not 340: the header ran ~6px over - "done 30" lost its last digit, and a count
          you cannot read is worse than no count. The extra room buys the row titles a few
          characters too, which is where taskuary#18 [Containerization]... was being cut. */}
      <Box sx={{ width: 372, flexShrink: 0 }}>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
        <Box sx={{ ...card, p: 0, overflow: "hidden", display: "flex", flexDirection: "column",
          height: "calc(100vh - 118px)", minHeight: 420 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.75,
            borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2, flexShrink: 0 }}>
            {/* each pill says how many live behind it - a filter you cannot size up is a guess.
                The pills give way, never the New button: four-digit counts must not be able to
                push it off the edge of a 340px panel again. */}
            <Box sx={{ flex: 1, minWidth: 0, overflowX: "auto", "&::-webkit-scrollbar": { display: "none" },
              scrollbarWidth: "none" }}>
              <FilterPills value={filter} onChange={setFilter}
                options={STATE_FILTERS.map((f) => ({ ...f,
                  n: !tasks ? null : f.key ? tasks.filter((x) => inBucket(x, f.key)).length : tasks.length }))} />
            </Box>
            {/* flexShrink: the pills would otherwise squeeze this until only half the + was
                left on screen, and a clipped button reads as a rendering fault */}
            <Button size="small" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => setNewOpen(true)}
              sx={{ flexShrink: 0, minWidth: "auto", px: 1 }}>New</Button>
          </Box>
          {/* rows as separated cards on a soft ground - air between tasks instead of a ruled
              ledger, selection said with the border alone. Scandinavian: fewer lines, calmer. */}
          <Box sx={{ overflowY: "auto", flex: 1, bgcolor: "#f1ede7", px: 1, py: 1 }}>
            {!tasks ? <CircularProgress size={20} sx={{ m: 2 }} /> : !shown.length ? <Empty>No tasks here.</Empty> : shown.map((task) => (
              <Box key={task.TaskId} onClick={() => onSelect(task.TaskId)}
                sx={{ px: 1.25, py: 1, mb: 0.75, cursor: "pointer", bgcolor: "#fff", borderRadius: 1.75,
                  border: `1px solid ${selected === task.TaskId ? "#55697a" : BORDER}`,
                  boxShadow: selected === task.TaskId ? "0 1px 8px rgba(47,107,79,.14)" : "none",
                  transition: "border-color .12s, box-shadow .12s",
                  "&:hover": { borderColor: selected === task.TaskId ? "#55697a" : "#d8cfbe" } }}>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                  <Typography variant="caption" sx={{ ...mono, color: "#55697a", fontWeight: 700 }}>{task.ref}</Typography>
                  <StateChip task={task} />
                  {task.Priority === "urgent" && <Chip size="small" label="urgent" sx={{ bgcolor: "#f0e2e4", color: "#6b2733", height: 17, fontSize: 10 }} />}
                  {String(task.Assignee || "").startsWith("agent:") && <SmartToyIcon sx={{ fontSize: 13, color: "#6f8a6e" }} />}
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" sx={{ color: FAINT }}>{timeAgo(task.CreatedAt)}</Typography>
                </Box>
                <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 500, mt: 0.4 }}>{task.Title}</Typography>
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
              {/* header strip: identity + controls. Calm on purpose - white ground, one quiet
                  outlined action, ghost icons: the loud green block + boxed dots read as three
                  alarms where nothing was wrong */}
              <Box sx={{ px: 2.5, py: 1.5, bgcolor: "#fff", borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
                {/* one primary action, everything else behind one tidy menu - six buttons in a
                    row read as none of them mattering */}
                <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Typography sx={{ ...mono, color: "#55697a", fontWeight: 700, fontSize: 12.5 }}>{detail.ref}</Typography>
                  <Typography sx={{ color: INK, flex: 1, fontWeight: 650, fontSize: 15, minWidth: 200, letterSpacing: "-.01em" }} noWrap>
                    {t.Title}
                  </Typography>
                  <StateChip task={{ ...t, ReviewStatus: (detail.reviews || [])[0]?.Status,
                    RunStatus: (detail.runs || [])[0]?.Status, Session: detail.session }} />
                  {t.Status !== "done" && (
                    <Tooltip title="I took care of it — close the task and wrap anything running">
                      <Button size="small" variant="outlined" startIcon={<DoneAllIcon sx={{ fontSize: 15 }} />}
                        sx={{ color: "#47654a", borderColor: "#47654a66", px: 1.25,
                          "&:hover": { borderColor: "#47654a", bgcolor: "#f0faf4" } }}
                        onClick={() => patch({ Status: "done" })}>Mark done</Button>
                    </Tooltip>
                  )}
                  <Tooltip title="Hand off, split or merge, pick the repo, not a task…">
                    <IconButton size="small" onClick={(e) => setMenuEl(e.currentTarget)}>
                      <MoreHorizIcon sx={{ fontSize: 18 }} />
                    </IconButton>
                  </Tooltip>
                  <Menu anchorEl={menuEl} open={!!menuEl} onClose={() => setMenuEl(null)}
                    slotProps={{ paper: { sx: { minWidth: 280 } } }}>
                    <MenuItem onClick={() => { setMenuEl(null); setHandoff(true); }}>
                      <ListItemIcon><ForwardToInboxIcon sx={{ fontSize: 17, color: "#55697a" }} /></ListItemIcon>
                      <ListItemText primary="Hand it to a person"
                        secondary="not ours to do — the AI writes the forward, you send it" />
                    </MenuItem>
                    <MenuItem onClick={() => { setMenuEl(null); setReshape(true); }}>
                      <ListItemIcon><CallSplitIcon sx={{ fontSize: 17, color: "#6f8a6e" }} /></ListItemIcon>
                      <ListItemText primary="Two jobs in here, or a duplicate?"
                        secondary="break it in two, or fold it into the task it repeats" />
                    </MenuItem>
                    <MenuItem onClick={() => { setMenuEl(null); setRepoPick(true); }}>
                      <ListItemIcon><AccountTreeIcon sx={{ fontSize: 17, color: "#55697a" }} /></ListItemIcon>
                      <ListItemText primary={repoOf(t) ? `Repo: ${repoOf(t)}` : "Pick the repository"}
                        secondary="which checkout the session works in" />
                    </MenuItem>
                    <Divider />
                    <MenuItem onClick={() => { setMenuEl(null); setConfirmNAT(true); }} sx={{ color: "#6b2733" }}>
                      <ListItemIcon><BlockIcon sx={{ fontSize: 16, color: "#6b2733" }} /></ListItemIcon>
                      <ListItemText primary="Not a task" secondary="delete it and teach triage why" />
                    </MenuItem>
                  </Menu>
                  <Tooltip title="Close — back to the list (the task stays)">
                    <IconButton size="small" onClick={() => onSelect(null)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
                  </Tooltip>
                </Box>
                {/* the meta row carries the knobs. Kind is a CONTROL, not a caption: "this is not
                    a coding task" is said here, and saying reply routes it to the Review queue */}
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1 }}>
                  <Select value={t.Kind || "general"} onChange={(e) => patch({ Kind: e.target.value })} sx={selSx}
                    title="What this IS decides who works it: coding gets a repo session, a reply gets a draft in Review, general stays on your list">
                    {[...new Set([t.Kind || "general", ...KINDS])].map((k) =>
                      <MenuItem key={k} value={k} sx={{ fontSize: 12 }}>{k === "reply" ? "reply — just needs an answer" : k}</MenuItem>)}
                  </Select>
                  <Select value={t.Status} onChange={(e) => patch({ Status: e.target.value })} sx={selSx}
                    title="the raw status, if you need to move it by hand">
                    {STATUSES.map((s) => <MenuItem key={s} value={s} sx={{ fontSize: 12 }}>{s}</MenuItem>)}
                  </Select>
                  <Select value={t.Priority} onChange={(e) => patch({ Priority: e.target.value })} sx={selSx}>
                    {PRIORITIES.map((p) => <MenuItem key={p} value={p} sx={{ fontSize: 12 }}>{p}</MenuItem>)}
                  </Select>
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    from {t.Source} · assignee {t.Assignee || "—"} · created {timeAgo(t.CreatedAt)} by {t.CreatedBy}
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ px: 2, py: 1.5, overflowY: "auto", flex: 1 }}>
                {/* THE SESSION IS THE PAGE. Your CLI, in this task's repo, with the task in
                    its lap - you type into it like any other terminal. Everything below is
                    reference material about the same task, folded away. */}
                {/* the session just closed: its write-up takes the space the terminal had, so the
                    result of the work is the thing you are looking at */}
                {/* The checkout, and why. A wrong guess means an agent editing the wrong tree in
                    good faith, so it is stated on the page rather than buried in the prompt. */}
                {repoPick && (
                  <Box sx={{ ...card, mb: 1, bgcolor: PANEL2 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      <AccountTreeIcon sx={{ fontSize: 16, color: "#55697a" }} />
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13, flex: 1 }}>
                        Which repository is this about?
                      </Typography>
                      <IconButton size="small" onClick={() => setRepoPick(false)}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
                    </Box>
                    <RepoPicker taskId={selected} agent={term?.agent || run.agent || "coder"}
                      hasSession={!!term?.alive}
                      onDone={() => { loadDetail(selected); loadTasks(); findTerm(selected); }} />
                  </Box>
                )}
                {wrapping && !wrapped ? (
                  <Box sx={{ ...card, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <CircularProgress size={15} />
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5 }}>
                        {wrapping === "pause" ? "Saving what this session found…" : "Wrapping up this session…"}
                      </Typography>
                    </Box>
                    <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>
                      {wrapping === "pause"
                        ? "Reading the transcript and writing the handover note for the next session. The agent is not asked anything."
                        : "Reading the transcript, writing the report from it, then drafting the reply for your approval. The agent is not asked anything — this takes a few seconds."}
                    </Typography>
                    <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />
                  </Box>
                ) : wrapped ? (
                  <Box sx={{ ...card, bgcolor: wrapped.note ? "#dfeade" : "#e3e6e1",
                    border: `1px solid ${wrapped.note ? "#d8cfbe" : "#d2d6cf"}` }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      {wrapped.note ? <PauseCircleIcon sx={{ fontSize: 17, color: "#55697a" }} />
                        : <DoneAllIcon sx={{ fontSize: 17, color: "#47654a" }} />}
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
                    {/* the card used to name Review without offering a way to get there */}
                    {wrapped.drafting && onGoReview && (
                      <Button size="small" variant="contained" disableElevation sx={{ mt: 1 }}
                        startIcon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                        onClick={onGoReview}>Read the draft in Review</Button>
                    )}
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
                      {/* the look you take BEFORE wrapping up - it sits next to Done on purpose,
                          because that is the moment the decision gets made */}
                      <Button size="small" startIcon={<DifferenceIcon sx={{ fontSize: 15 }} />}
                        sx={{ fontSize: 11, color: DIM }} onClick={() => setDiffOpen(true)}
                        title="What has it actually changed in this checkout, per file — before anything is pushed">
                        Review changes
                      </Button>
                      <Button size="small" variant="contained" disableElevation disabled={!!wrapping}
                        startIcon={wrapping === "wrap" ? <CircularProgress size={11} sx={{ color: "#fff" }} />
                          : <DoneAllIcon sx={{ fontSize: 15 }} />}
                        sx={{ fontSize: 11.5, bgcolor: "#47654a", "&:hover": { bgcolor: "#166534" } }}
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
                    {/* sized to what is actually left on screen below the header and the button strip, so the
    detail panel does not have to be scrolled to see the bottom of the session - the
    terminal has its own scrollbar for its own scrollback */}
                    <TerminalPane sid={term.sid} height="clamp(300px, calc(100vh - 300px), 820px)"
                      onExit={() => findTerm(selected)} />
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mt: 0.5 }}>
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
                      <Typography variant="caption" sx={{ color: "#55697a", display: "block", mb: 1.25 }}>
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
                    {/* An earlier session finished and its terminal is long gone, but the work it
                        did is still un-closed-out. The transcript outlives the pty, so the two
                        buttons that were only ever on the terminal strip belong here too. */}
                    {detail?.transcript && (
                      <Box sx={{ mt: 1.5, pt: 1.25, borderTop: `1px dashed ${BORDER}` }}>
                        <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 0.75 }}>
                          A {detail.transcript.agent || "coder"} session ran this task on{" "}
                          {fmtDateTime(detail.transcript.at)} and its terminal has since closed — what it
                          did was kept, so you can still write it up.
                        </Typography>
                        <Box sx={{ display: "flex", justifyContent: "center", gap: 1, flexWrap: "wrap" }}>
                          <Button size="small" variant="contained" disableElevation disabled={!!wrapping}
                            startIcon={wrapping === "wrap" ? <CircularProgress size={11} sx={{ color: "#fff" }} />
                              : <DoneAllIcon sx={{ fontSize: 15 }} />}
                            sx={{ fontSize: 11.5, bgcolor: "#47654a", "&:hover": { bgcolor: "#166534" } }}
                            onClick={wrapUp}>
                            {wrapping === "wrap" ? "wrapping up…" : "Done — wrap it up"}
                          </Button>
                          <Button size="small" disabled={!!wrapping} sx={{ fontSize: 11, color: DIM }}
                            startIcon={wrapping === "pause" ? <CircularProgress size={11} /> : <PauseCircleIcon sx={{ fontSize: 15 }} />}
                            onClick={pause}>
                            {wrapping === "pause" ? "saving what it found…" : "Save what it found"}
                          </Button>
                        </Box>
                      </Box>
                    )}
                  </Box>
                )}

                {/* the summary the agent left behind, once it has finished */}
                {report && !wrapped && (
                  <Block title="What the agent did">
                    <Box sx={{ bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.5 }}>
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
                            <Typography variant="caption" sx={{ color: "#6f8a6e", display: "flex", alignItems: "center", gap: 0.4 }}>
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
                        <Attachments messageId={m.MessageId} canFetch={m.Channel === "email"} dense />
                      </Box>
                    );
                  })}
                  {!detail.messages.length && <Typography variant="caption" sx={{ color: FAINT }}>Manually created — no source messages.</Typography>}
                </Fold>

                {/* runs from before sessions (and any API-driven run) keep their trace here */}
                {detail.runs.length > 0 && (
                  <Fold title={`Earlier runs · ${detail.runs.length}`}>
                    {detail.runs.map((r) => (
                      <Box key={r.RunId} sx={{ mb: 0.75, p: 1, bgcolor: r.Status === "running" ? "#dfeade" : PANEL2, borderRadius: 1.5, border: `1px solid ${BORDER}` }}>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                          <SmartToyIcon sx={{ fontSize: 13, color: "#6f8a6e" }} />
                          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>run {r.RunId} · {r.AgentName} · {r.Status}</Typography>
                          {r.Status === "running" && <CircularProgress size={11} />}
                          <Typography variant="caption" sx={{ color: FAINT }}>· {timeAgo(r.StartedAt)} · by {r.DispatchedBy}</Typography>
                        </Box>
                        <RunTrace traceJson={r.TraceJson} running={r.Status === "running"} />
                        {r.Result && <Typography variant="caption" sx={{ mt: 0.25, whiteSpace: "pre-wrap", color: "#47654a", display: "block" }}>{r.Result}</Typography>}
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

      {/* ── review the change: the widest drawer of the three, because code needs the room.
             Read-only by construction - it runs git diff and git status and nothing else, so
             opening it can never disturb what the agent is in the middle of. ── */}
      <Drawer anchor="right" open={!!diffOpen && !!t} onClose={() => setDiffOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 760 }, p: 2, bgcolor: PANEL2 } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <DifferenceIcon sx={{ fontSize: 18, color: "#6f8a6e" }} />
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>What has it changed?</Typography>
          {diff && !!diff.files?.length && (
            <Typography sx={{ ...mono, fontSize: 11.5, color: DIM }}>
              {diff.files.length} file{diff.files.length === 1 ? "" : "s"}
              <Box component="span" sx={{ color: "#47654a", ml: 1 }}>+{diff.added}</Box>
              <Box component="span" sx={{ color: "#6b2733", ml: 0.75 }}>−{diff.removed}</Box>
            </Typography>
          )}
          <Tooltip title="Ask git again — the agent may have written more since you opened this">
            <IconButton size="small" onClick={() => loadDiff(selected)}><RefreshIcon sx={{ fontSize: 16 }} /></IconButton>
          </Tooltip>
          <IconButton size="small" onClick={() => setDiffOpen(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · everything a push would carry
          {/* an agent told to "commit locally and stop" leaves a CLEAN tree - saying only
              "uncommitted work" over a finished job read as "it did nothing" */}
          {diff?.ahead ? ` — ${diff.ahead} commit${diff.ahead === 1 ? "" : "s"} ahead of ${diff.upstream}, plus anything uncommitted`
                       : diff?.upstream ? ` — measured against ${diff.upstream}` : ""}
        </Typography>
        {!diff ? <CircularProgress size={20} sx={{ m: 2 }} />
          : diff.why ? <Empty>{diff.why}</Empty>
            : <DiffFiles files={diff.files} cwd={diff.cwd} branch={diff.branch} />}
      </Drawer>

      {/* ── hand off: a right-hand drawer, so it cannot hide above a tall terminal ── */}
      <Drawer anchor="right" open={!!handoff && !!t} onClose={() => setHandoff(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 460 }, p: 2, bgcolor: PANEL } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <ForwardToInboxIcon sx={{ fontSize: 18, color: "#55697a" }} />
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>Hand this to a person</Typography>
          <IconButton size="small" onClick={() => setHandoff(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {t?.Title}
        </Typography>
        {handoff && <Handoff taskId={selected} onSent={() => { loadDetail(selected); loadTasks(); }} />}
      </Drawer>

      {/* ── split / merge: the same right-hand drawer, because it is one question ── */}
      <Drawer anchor="right" open={!!reshape && !!t} onClose={() => setReshape(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <CallSplitIcon sx={{ fontSize: 18, color: "#6f8a6e" }} />
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 14.5, flex: 1 }}>Is this one job?</Typography>
          <IconButton size="small" onClick={() => setReshape(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {t?.Title}
        </Typography>
        {reshape && <Reshape taskId={selected} taskRef={detail?.ref} onDone={reshaped} />}
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
      <ConfirmDelete open={confirmNAT} what={t ? `"${(t.Title || "this task").slice(0, 60)}"` : "this task"}
        consequence={"It is deleted, and its sender is taught that mail like this is never a task — so their future messages file themselves. "
          + "Its messages stay on the Timeline."}
        onClose={() => setConfirmNAT(false)} onConfirm={notATask} />
    </Box>
  );
}

// The history is a log, so it reads like one: who, when, what - one line each until you
// open it. Agent answers run to thousands of characters and used to bury the page.
const CommentRow = ({ c }) => {
  const [open, setOpen] = useState(false);
  const [clamped, setClamped] = useState(false);
  const ref = useRef(null);
  const body = String(c.Body || "").trim();
  // Whether anything is actually HIDDEN is a layout question, not a character count. Any
  // two-line note counted as long, then fitted both lines on show - so the expander sat there
  // saying "252 chars" and did nothing when clicked. Measure the clamp, only while applied.
  useEffect(() => {
    if (!open && ref.current) setClamped(ref.current.scrollHeight > ref.current.clientHeight + 1);
  }, [body, open]);
  const long = clamped || open;
  return (
    <Box component="tr" sx={{ borderTop: `1px solid ${BORDER}`, verticalAlign: "top",
      "&:hover": { bgcolor: open ? "transparent" : PANEL2 } }}>
      <Box component="td" sx={{ py: 0.6, pr: 1, whiteSpace: "nowrap" }}>
        <Typography variant="caption" sx={{ ...mono, fontWeight: 700, fontSize: 10.5,
          color: c.ActorType === "agent" ? "#6f8a6e" : "#55697a" }}>{c.Actor}</Typography>
      </Box>
      <Box component="td" sx={{ py: 0.6, pr: 1.25, whiteSpace: "nowrap" }}>
        <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{timeAgo(c.CreatedAt)}</Typography>
      </Box>
      <Box component="td" sx={{ py: 0.6, width: "100%", cursor: long ? "pointer" : "default" }}
        onClick={() => long && setOpen(!open)}>
        <Typography ref={ref} variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap", lineHeight: 1.5,
          ...(open ? {} : { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>
          {body}
        </Typography>
        {long && (
          <Typography variant="caption" sx={{ color: "#55697a", fontWeight: 600, fontSize: 10.5 }}>
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
