// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import { says, subState } from "./laneSays.js";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress,
  Drawer, IconButton, InputAdornment, Link, MenuItem, Select, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import BlockIcon from "@mui/icons-material/Block";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import DifferenceIcon from "@mui/icons-material/Difference";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import api from "./api";
import { runOperation } from "./taskOps.js";
import { agentName } from "./agentWork.js";
import { lazyGeneral } from "./lazyGeneral.js";
import { outcomeOf } from "./dispatchOutcome.js";
import { progressLine } from "./checklist.js";
import { deliveryCc, deliveryFiles, replyContext } from "./replyDelivery.js";
import { sizeText } from "./replyFiles.js";
import { completionTransition, cutAway, filterForSelectedState } from "./taskFilter.js";
import ReviewDecision from "./ReviewDecision.jsx";
import { onLive } from "./live.js";
import { pollWhileActive } from "./visible.js";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, ACCENT, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { RepoPicker } from "./RepoPicker.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon, LifecycleChip, StateChip, stateOf, TASK_STATES, asUtc, tsMs, AgentPicker, useAgents, RunTrace, DiffBlock, DiffFiles, CoderReport, timeAgo, fmtDateTime, cleanText, Empty, FilterPills, ConfirmDelete, TellAgent, WorkStrip, isWaiting, TaskuaryMark, agentAssignee, assignedAgent, assigneeLabel } from "./ui.jsx";
import { Md, looksMd } from "./md.jsx";
import TerminalIcon from "@mui/icons-material/Terminal";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import HistoryIcon from "@mui/icons-material/History";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import { Divider, ListItemText } from "@mui/material";
import { TerminalPane } from "./TerminalView.jsx";

// An open tab can still hold yesterday's entry bundle after a local upgrade. Vite names lazy
// chunks by content, so that tab asks the new server for a filename the build no longer has.
// Recover once automatically; a real module error still reaches the view boundary on retry.
import { autostartPlan, isGeneralKind } from "./autostart.js";
import { agentWorkspaceMode } from "./taskWorkspace.js";
import { ASK_TAG } from "./newTask.js";
import {
  agentPhase, focusStage, hasCorrespondent, ownerControlsCompletion, pendingProposals, pendingReplyReview, replyPhase, sentReplyReview, taskPhase,
} from "./taskLifecycle.js";

const GeneralWorkspace = React.lazy(lazyGeneral("GeneralWorkspace"));   // the guard lives in lazyGeneral.js

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

const STATUSES = ["open", "in_progress", "waiting", "done", "dropped"];
const statusLabel = (s) => String(s || "").replace(/_/g, " ");
// `assistant` is a legacy alias from Timeline discussions. New discussions use `general`, but
// old ones must still open here instead of falling through to the coding terminal.
// CATEGORY is where a task is; the chip on the row says what it needs. Filtering by "needs
// you" and "working" separately made those two look like opposites, so a task whose agent
// picked it up vanished out of the bucket you were watching - and a task sitting in "needs
// you" WITH an agent thinking on it read as a contradiction, because it was one. One
// in-progress bucket holds everything still open; the label inside it is what changes.
// the pills wear the same colours as the chips on the rows they hold: "in progress" in the
// slate-blue brand chrome next to a sage "agent working" chip read as two different states
const ST_C = Object.fromEntries(TASK_STATES.map((s) => [s.key, s.c]));
const STATE_FILTERS = [
  { key: "", label: "all" },
  { key: "live", label: "in progress", c: ST_C.working },
  { key: "done", label: "done", c: ST_C.done },
];
// "today" as the person reading the list means it - the server's clock, in local terms
const isToday = (s) => !!s && asUtc(String(s)).toDateString() === new Date().toDateString();
const touchedToday = (t) => isToday(t.ClosedAt) || isToday(t.UpdatedAt) || isToday(t.CreatedAt);
// everything still on somebody's plate - yours or an agent's. Dropped is neither, and only
// ever shows under "all".
const inBucket = (t, key) => (key === "live" ? !["done", "dropped"].includes(stateOf(t).key)
                                             : stateOf(t).key === key);
const PRIORITIES = ["low", "normal", "high", "urgent"];
// what a task IS decides which machinery works it: coding gets a repo session, a reply
// gets the responder and the review queue, general gets the visual conversation. Keep the
// explicit non-coding label: calling this only "assistant" hid the option the owner asked for.
// WHO works it, then what it is - the owner's own words (2026-09-10: "tag tasks as reply/your
// task/agent (maybe coding vs general)"). "your task" is deliberately the same phrase the work
// rail's own heading uses for band 2 (funnelPile.LEVEL_META), so one thing has one name in both
// places. The two `agent` kinds are the two that reach the Board; reply and your task do not.
const KIND_OPTIONS = [
  { key: "task", label: "your task", hint: "yours to do - nothing works it, and it is not on the Board" },
  { key: "general", label: "agent · general", hint: "research, writing, analysis, planning - an agent runs it without a repository" },
  { key: "coding", label: "agent · coding", hint: "the configured CLI in a repository terminal" },
  { key: "reply", label: "reply", hint: "drafted by the model triage uses and approved on the task - it never opens a session" },
];
const KINDS = KIND_OPTIONS.map((o) => o.key);
const kindLabel = (kind) => KIND_OPTIONS.find((o) => o.key === kind)?.label || kind;

// The task's settings read as FACTS you can change, not as a form: pill-shaped, label-less,
// sitting on the card's bottom edge. Stacked "Type / Task status / Priority" labels over boxed
// selects made a four-field form out of four words, and put the one button that completes the
// task at the end of it (the owner, 2026-09-16: "on bottom the filters agent·coding, waiting").
const chipSel = {
  fontSize: 11.5, fontWeight: 600, height: 26, bgcolor: "#f4f1ec", borderRadius: 13, color: INK,
  "& .MuiSelect-select": { py: 0, pl: 1.25, pr: "24px !important", minHeight: 0, display: "flex", alignItems: "center" },
  "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#d8cfbe" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: "#55697a" },
  "& .MuiSelect-icon": { right: 2, fontSize: 18, color: "rgba(0,0,0,.45)" },
};
// the repo is a filter like the others, but it opens a picker rather than a menu of values
const chipBtn = { fontSize: 11.5, fontWeight: 600, height: 26, minHeight: 26, py: 0, px: 1.25,
  borderRadius: 13, bgcolor: "#f4f1ec", color: INK, borderColor: BORDER,
  "&:hover": { borderColor: "#d8cfbe", bgcolor: "#f4f1ec" } };
const barBtn = { minHeight: 34, py: 0, px: 1.6, fontSize: 12.5, color: INK, borderColor: BORDER };
// ...and the one filled move beside them. Every card's bar reads [ primaryBtn ] | [ barBtn ] [ barBtn ].
const primaryBtn = { minHeight: 34, py: 0, px: 1.75, fontSize: 12.5 };
// A LIVE SESSION'S CONTROLS LOOK LIKE CONTROLS. These were bare text buttons sitting next to
// the outlined role/brain/repo pills, so the two things you could press had less edge than the
// three facts you can only read - "buttons are still not clear what they are. and they are
// floating" (the owner, 2026-09-16). Same pill geometry as the facts beside them, in the slate
// the app uses for every control: the colour says pressable, the border says where it ends.
// Not filled - filled is Mark task done's, one strip up, and a live session has no primary.
// ...and SMALL, because every row this bar spends is a row the terminal does not get.
const liveCtl = { fontSize: 10.5, fontWeight: 650, height: 23, minHeight: 23, py: 0, px: 0.9,
  borderRadius: 11.5, color: ACCENT, bgcolor: "#f1f4f7", borderColor: "#c7d2dc", whiteSpace: "nowrap",
  "& .MuiButton-startIcon": { mr: 0.5, ml: 0 },
  "&:hover": { borderColor: ACCENT, bgcolor: "#e7eef4" } };
// the same pill as chipBtn, for a fact you read rather than a control you press
const chipBtnStatic = { display: "inline-flex", alignItems: "center", height: 26, px: 1.25,
  borderRadius: 13, bgcolor: "#f4f1ec", border: `1px solid ${BORDER}`, color: INK,
  fontSize: 11.5, fontWeight: 600 };

// ── the list rail's row ──────────────────────────────────────────────────────────────────
// One word for the kind: the agent's own name follows it on the same line, so "agent · coding ·
// coder" spent three words saying an agent has it.
const shortKind = (kind) => String(kindLabel(kind || "task")).replace(/^agent · /, "");
// The checklist is already on every list row - store.list_tasks selects t.* and the Checklist
// column rides along - so the rail draws progress without a request per task.
const rowChecklist = (t) => {
  try { const a = JSON.parse(t?.Checklist || "[]"); return Array.isArray(a) ? a.filter((i) => i && i.text) : []; }
  catch { return []; }
};
// How long a parked agent has been holding its question. The row already carries the session that
// stateOf() reads, so this costs nothing - and a question you have left for an hour should say so
// on the rail rather than only inside the task.
const askedAgo = (t) => {
  const s = t?.Session;
  if (!s || !isWaiting(s)) return "";
  const mins = Math.round((Number(s.idle) || 0) / 60);
  if (mins < 1) return "asked you just now";
  return `asked you ${mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`} ago`;
};

export default function TasksView({ selected, onSelect, onChanged, autostart, onAutostarted, onGoReports, active = true }) {
  const [tasks, setTasks] = useState(null);
  // "live" on arrival: what is still on somebody's plate is what you came here for. "all"
  // opens on a list whose top is whatever finished most recently. ("" = all; the rest derive.)
  const [filter, setFilter] = useState("live");
  const [query, setQuery] = useState("");
  // what the loaded rows are FOR. The box is debounced because every change is now a round trip.
  const [sent, setSent] = useState("");
  // "all" and "done" pile up for months; today's are the ones you came to look at, the rest
  // wait behind one button. In progress is never cut: what is still on a plate must show.
  const [older, setOlder] = useState(false);
  const [detail, setDetail] = useState(null);
  // Which task is on screen RIGHT NOW, readable from inside any await. Every fetch here is
  // keyed to a task, and a response that lands after you clicked another one must be dropped:
  // a wrap-up finishing 8 seconds later used to paint ITS task's header and report over the
  // one you had moved to, while the funnel below still belonged to the new one - two tasks
  // in one pane, and "Done" a click away from the wrong session.
  const selRef = useRef(selected); selRef.current = selected;
  // The Board's new-task box asks which checkout a coding task lands in; this one did not, so the
  // same task made here fell back to guess_repo matching the words against SOUL.md's repo map -
  // right often enough to be trusted, and wrong silently when it was not.
  const [repos, setRepos] = useState([]);
  const sessionAlive = !!detail?.session?.alive;
  const hasRunningRun = (detail?.runs || []).some((r) => r.Status === "running");
  const hasCoderReport = (detail?.comments || []).some((c) => /^CODER REPORT(?:\r?\n|$)/.test(String(c.Body || "").trimStart()));
  const hasTranscript = !!detail?.transcript;
  const detailTaskStatus = detail?.task?.Status;
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => setRepos(
      (data.data || []).filter((x) => x.Channel === "github" && x.Active).map((x) => x.Address)
    )).catch(() => {});
  }, []);
  // A refresh already in flight when the tab is left can finish after the refresh
  // fired on return. Only the newest request is allowed to repaint the list.
  const taskLoadSeq = useRef(0);
  const stale = (id) => selRef.current !== id;
  const { agents, models, kinds, brains, brainList, brainModels, generalBrains } = useAgents();
  const pickerTask = useRef(null);          // initialize each task from its durable worker once
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "task", Priority: "normal" });
  useEffect(() => {
    const fromHash = () => {
      if (window.location.hash === "#new-task") {
        setNewOpen(true);
        history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      }
    };
    fromHash(); window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);
  const [run, setRun] = useState({ agent: "", model: "", instruction: "" });   // "" = the roster's default (served first)
  // Which KIND of worker this row is configuring. "Use non-coding agent" used to dispatch on the
  // spot, so there was no moment at which a profile or a brain could be chosen for it - the block
  // is called "Configure the next run" and could not configure that one (the owner, 2026-09-18).
  const [handOff, setHandOff] = useState(false);
  // A finished run should lead with what it accomplished. Harness/model/prompt choices stay
  // behind an explicit restart action instead of looking like the main thing to do next.
  const [restartOpen, setRestartOpen] = useState(false);
  const [startingAgent, setStartingAgent] = useState("");
  const [generalRevision, setGeneralRevision] = useState(0);
  const [comment, setComment] = useState("");
  // the waiting room: notes for the agent, typed in when it stops (waitroom.py)
  const [wait, setWait] = useState({ data: [], state: null });
  const [waitText, setWaitText] = useState("");
  const [wrapping, setWrapping] = useState(false);   // declared up here: the poll effect below reads it
  const [wrapped, setWrapped] = useState(null);      // the closing report, shown where the session was
  // Once a live session disappears, its report and reply draft are still being filed. Keep
  // checking briefly so the page cannot freeze forever on the pre-close status it last saw.
  const sessionSettleUntil = useRef(0);
  const [diffOpen, setDiffOpen] = useState(false);   // the pre-push review, in its own drawer
  // THE TASK BEHIND THE SESSION. A live session takes the whole task page, and with it went the
  // one thing the X was expected to reach: the task itself - what it is, where it came from, its
  // thread (the owner, 2026-09-18: "even if the coding cli is open i want to be able to go back to
  // see the actual task and where it came from"). peek shows the task card with the session folded
  // to one line; the session keeps running, and the terminal comes back on a click or a new pick.
  const [peek, setPeek] = useState(false);
  const [askSenderOpen, setAskSenderOpen] = useState(false);
  const [senderQuestion, setSenderQuestion] = useState("");
  // "this one is mine" - the verdict that used to be a silent dropdown (TQ-0501)
  const [mineOpen, setMineOpen] = useState(false);
  const [belongsTo, setBelongsTo] = useState("");
  const [savingMine, setSavingMine] = useState(false);
  const [askingSender, setAskingSender] = useState(false);
  const [openingReply, setOpeningReply] = useState(false);
  const [openStage, setOpenStage] = useState(null);   // a stage you opened by hand, overriding the computed focus
  const waitingN = (tasks || []).find((x) => x.TaskId === selected)?.Waiting || 0;   // prompts in this task's funnel
  const [diff, setDiff] = useState(null);
  const [diffScope, setDiffScope] = useState("task");   // this task's footprint, or the whole checkout

  // fetch everything once and filter on the derived state - the server only knows raw
  // Status, and the state a person cares about is a combination of three columns
  // ?active=1 is open/in_progress/waiting PLUS today's done - exactly what "in progress" and an
  // un-expanded "done" show. The archive waits until something asks: "show older", or "all".
  //
  // A SEARCH IS ITS OWN QUERY. It used to mean "load every task ever filed, with six GROUP_CONCAT
  // aggregates over the whole message table, and grep them here" - which is how you search only if
  // you have already paid to hold the archive in a browser. ?q= searches in SQL and returns the
  // matches, so the rows below ARE the result and nothing is shipped to be filtered.
  const fullLoaded = useRef(false);
  const loadTasks = useCallback(async (full = false) => {
    const want = full || fullLoaded.current;      // once upgraded, never silently downgrade
    const seq = ++taskLoadSeq.current;
    try {
      const params = sent ? { q: sent } : want ? {} : { active: 1 };
      const next = (await api.get("/api/tasks", { params })).data.data || [];
      if (seq === taskLoadSeq.current) {
        setTasks(next);
        if (want && !sent) fullLoaded.current = true;   // a search result is not the full set
      }
    } catch (e) {
      if (seq === taskLoadSeq.current) setErr(e?.response?.data?.detail || "Failed to load tasks");
    }
  }, [sent]);

  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/api/tasks/${id}`);
      if (stale(id)) return;
      setDetail(data);
      try { const w = (await api.get(`/api/tasks/${id}/waitroom`)).data; if (!stale(id)) setWait(w); }
      catch { if (!stale(id)) setWait({ data: [], state: null }); }
    } catch (e) {
      if (stale(id)) return;
      // A task can vanish under an open pane: "not mine" on its message deletes the task and
      // closes its session. The detail poll then asked for a dead id every three seconds and
      // repainted "task not found" each time, which reads as the app being broken rather than
      // as the thing you just did. Let go of it, and say it once.
      if (e?.response?.status === 404) {
        setDetail(null); onSelect(null);
        setErr("That task is gone - it was deleted.");
        return;
      }
      setErr(e?.response?.data?.detail || "Failed to load task");
    }
  }, [onSelect]);
  // the tab always lands on what is still in progress - whatever it was left on last time
  useEffect(() => { if (active) { setFilter("live"); setOlder(false); } }, [active]);
  useEffect(() => { setOlder(false); }, [filter]);

  // ...and keep it honest. The list was fetched ONCE, so a task whose agent picked it up
  // kept wearing "needs you" - and the pill counts kept agreeing with it - until something
  // else happened to reload. "Agent working" is a fact with a 45-second shelf life (a live
  // session that goes quiet is waiting on you); a row that states it has to be re-asked.
  // Only while this tab is the one on screen: it stays mounted behind the others.
  useEffect(() => {
    // Refresh now as well as on events: otherwise returning from Board shows the hidden
    // tab's old list until the next task-changed.
    if (!active) return undefined;
    loadTasks();
    // ...and the OPEN task with it. A session can be started from anywhere - the Assistant's
    // "send to the coding agent", the Board, a second window - and the detail poll only runs
    // once something is already known to be live, so a task sitting open on this page could
    // never learn it had an agent (TQ-0500: the Board showed a live coder session while this
    // page offered to start one, which would have made a second).
    return onLive("task-changed", () => { loadTasks(); if (selRef.current) loadDetail(selRef.current); });
  }, [active, loadTasks, loadDetail]);
  // the roster is user-config - default to whatever actually exists
  useEffect(() => {
    if (agents.length && !agents.includes(run.agent)) setRun((r) => ({ ...r, agent: agents[0], model: "" }));
  }, [agents, run.agent]);
  useEffect(() => { loadDetail(selected); }, [selected, loadDetail]);
  useEffect(() => {
    const task = detail?.task;
    if (!task || task.TaskId !== selected || !agents.length || pickerTask.current === task.TaskId) return;
    pickerTask.current = task.TaskId;
    const owned = assignedAgent(task.Assignee);
    setRun((r) => ({ ...r, agent: agents.includes(owned) ? owned : agents[0], model: "" }));
  }, [selected, detail?.task, agents]);
  useEffect(() => { setRestartOpen(false); }, [selected]);
  useEffect(() => {
    // a LIVE SESSION counts as much as a headless run here: the header chip is derived from
    // how long the pty has been quiet, so without re-asking it froze on whatever it said
    // when the task was opened - "needs you" over an agent that was mid-thought
    const running = hasRunningRun || sessionAlive;
    if (sessionAlive) sessionSettleUntil.current = Date.now() + 120000;
    const settling = detailTaskStatus === "in_progress" && hasTranscript
      && (hasCoderReport || Date.now() < sessionSettleUntil.current);
    if (!((running || wrapping || settling) && selected)) return undefined;

    // Terminal bytes already travel over their own websocket. Turning each output frame into a
    // task + waitroom fetch made switching and typing wait behind the terminal's own repaints.
    // The surrounding lifecycle state only needs a calm check; the terminal remains fully live.
    return pollWhileActive(active, () => loadDetail(selected), 3000);
  }, [active, detailTaskStatus, hasCoderReport, hasRunningRun, hasTranscript, loadDetail, selected, sessionAlive, wrapping]);

  const patch = async (fields) => { await api.patch(`/api/tasks/${selected}`, fields); loadDetail(selected); loadTasks(); onChanged?.(); };
  // Reopen changes the task's status and nothing else: no worker starts until the owner chooses one (PW-217)
  const reopen = async () => {
    try { await runOperation(api, "task.reopen", selected); } catch (e) { setErr(e?.message || "Could not reopen the task"); return; }
    loadDetail(selected); loadTasks(); onChanged?.();
  };
  const create = async () => {
    // A general task made HERE is the same thing the Board makes: a question with an answer
    // wanted. It gets the same ask tag, so the chat opens with the question already asked
    // instead of with the owner's own words sitting in a box above an empty thread.
    const ask = isGeneralKind(nt.Kind) && String(nt.Summary || "").trim();
    // `repo` is not a task column - it rides as a tag, the same one the Board writes
    const { repo, ...fields } = nt;
    const tags = [repo && nt.Kind === "coding" ? `repo:${repo}` : "", ask ? ASK_TAG : ""].filter(Boolean);
    const { data } = await api.post("/api/tasks", { ...fields, ...(tags.length ? { Tags: tags.join(",") } : {}) });
    setNewOpen(false); setNt({ Title: "", Summary: "", Kind: "task", Priority: "normal" });
    setFilter("live"); loadTasks(); onSelect(data.taskId);
  };
  const queueNote = async () => {
    if (!waitText.trim() || !selected) return;
    try {
      const { data } = await api.post(`/api/tasks/${selected}/waitroom`, { text: waitText });
      setWaitText("");
      setErr(data.delivered ? (data.state === "restarted" ? "Session reopened with your note." : "Typed into the session - the agent was parked.") : "");
      loadDetail(selected);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not queue the note"); }
  };

  const post = async () => {
    if (!comment.trim()) return;
    await api.post(`/api/tasks/${selected}/comments`, { body: comment });
    setComment(""); loadDetail(selected);
  };
  // Finish the AGENT RUN, not the task. It files the durable result and closes this session;
  // task completion and any reply remain explicit controls in their own sections.
  const wrapUp = async () => {
    if (!canWrap) return;
    const id = selected;
    setWrapping("wrap"); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${id}/wrap`, { close: false });
      loadTasks(); onChanged?.();
      if (stale(id)) return;                    // moved on meanwhile: the report is on the task's history
      setWrapped({ report: data.report, drafting: data.drafting });
      setTerm(null); loadDetail(id);
    } catch (e) { if (!stale(id)) setErr(e?.response?.data?.detail || "Could not wrap up the session"); }
    if (!stale(id)) setWrapping(false);
  };
  // Pausing is not finishing: no report, no reply draft, the task stays open. What it worked
  // out becomes a handover note that gets typed into the NEXT session, because a pty has no
  // resumable id - killing the session used to throw all of that away.
  useEffect(() => {
    setWrapping(false); setWrapped(null);
    setAskSenderOpen(false); setSenderQuestion(""); setAskingSender(false); setOpeningReply(false);
    setOpenStage(null);
  }, [selected]);

  const [handoff, setHandoff] = useState(false);
  const [reshape, setReshape] = useState(false);
  const [repoPick, setRepoPick] = useState(false);
  const [resumeAfterRepo, setResumeAfterRepo] = useState(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  useEffect(() => { setHandoff(false); setReshape(false); setRepoPick(false); setResumeAfterRepo(null); setDiffOpen(false); setSourceOpen(false); setPeek(false); }, [selected]);
  // asked when the drawer opens, and only then: shelling out to git on every task poll would
  // spend a subprocess a second on an answer nobody is looking at
  const loadDiff = useCallback(async (id) => {
    setDiff(null);
    try { setDiff((await api.get(`/api/tasks/${id}/diff`, { params: { scope: diffScope } })).data); }
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
  // writes a standing verdict triage reads. The two sharpest things in the app were the two
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
  // ...and general work has no transcript at all: the chat IS the record, so a conversation that
  // has answered can be closed out after its provider session is gone (coder.py, 2026-09-07).
  const hasGeneralHistory = (detail?.comments || []).some((c) =>
    c.ActorType === "assistant_user" || c.ActorType === "assistant_agent");
  const canWrap = !!term || !!detail?.transcript || hasGeneralHistory;
  const findTerm = useCallback(async (tid) => {
    if (!tid) { setTerm(null); return; }
    try {
      // Selecting a task only needs the session identity/lifecycle. Rich files + witness data is
      // fetched by WorkStrip if the owner opens it; waiting on git here blocked the terminal pane.
      const rows = (await api.get("/api/terminals", { params: { details: false } })).data.data || [];
      if (stale(tid)) return;
      // an exited session still holds its scrollback (they stay listed ~10 min), and that
      // transcript is exactly what Done and Pause need - dropping it left a task you could
      // not close out because the CLI had finished on its own
      setTerm(rows.find((x) => x.taskId === tid && x.alive) || rows.find((x) => x.taskId === tid) || null);
    } catch { if (!stale(tid)) setTerm(null); }
  }, []);
  useEffect(() => { setTerm(undefined); findTerm(selected); }, [selected, findTerm]);
  // The task's own detail already carries the live session (it is where sessionAlive is read
  // from), so take it rather than wait for a re-selection to go looking. A session that has
  // ENDED is deliberately not adopted: findTerm keeps the dead one because its scrollback is
  // exactly what Done and Pause need, and `for_task` only ever returns a live one.
  useEffect(() => {
    const live = detail?.session;
    if (live?.alive && live.sid !== term?.sid) setTerm(live);
  }, [detail?.session, term?.sid]);
  const openTerm = useCallback(async (body) => {
    try {
      const { data } = await api.post("/api/terminals", body); setTerm(data);
      // Starting a session reopens a completed task. Refresh both surfaces immediately so the
      // chip and buckets say in progress on the same click that makes the terminal appear.
      loadDetail(body.task_id); loadTasks(); onChanged?.();
    }
    catch (e) {
      const msg = e?.response?.data?.detail || "Could not start a terminal";
      // Both repo guards are questions: either the repo is known but its path is missing, or
      // several checkouts exist and this task did not identify one confidently. Ask here, retain
      // the attempted launch, and continue it as soon as the owner chooses.
      if (/no local path|could not tell which checkout/i.test(msg)) {
        setErr(""); setRepoPick(true); setResumeAfterRepo(body);
      } else setErr(msg);
    }
  }, [loadDetail, loadTasks, onChanged]);
  const generalSession = useCallback((session) => setTerm(session), []);
  // "New task -> live session" lands here: put the CLI on it once we know this task has no
  // session already, so a reload never spawns a second one.
  // A GENERAL task has no repository and no CLI - it is a question, worked in the assistant's
  // own chat below. Starting a terminal on it was the bug behind "why did this open in a
  // terminal?": the prompt is handed to the chat instead, which asks it as the first message.
  useEffect(() => {
    const plan = autostartPlan({ autostart, selected, detail, hasSession: term !== null });
    if (plan.do === "wait") return;
    onAutostarted?.();
    // a general task asks its own question, off the tag the Board put on it (GeneralWorkspace)
    if (plan.do === "chat") return;
    openTerm({ agent: autostart.agent || run.agent, brain: autostart.brain || run.brain || null, model: autostart.model || run.model || null,
      task_id: selected, repo: repoOf(detail.task), seed: true });
  }, [autostart, selected, term, detail, openTerm, onAutostarted, run.agent]);


  // the pane shows the selected task or nothing - never the previous one while this loads
  const t = detail?.task?.TaskId === selected ? detail.task : null;
  const isGeneral = isGeneralKind(t?.Kind);
  const search = query.trim();
  useEffect(() => {
    const id = setTimeout(() => setSent(search), 250);
    return () => clearTimeout(id);
  }, [search]);
  // The two gestures that need more than the live set. "done" on its own does NOT: ?active=1
  // already carries today's, which is what it shows until "show older". "all" does, because
  // today's DROPPED tasks only ever appear there and active does not include them. A search no
  // longer belongs here at all - it asks the server for its own answer.
  useEffect(() => {
    if ((older || filter === "") && !fullLoaded.current) loadTasks(true);
  }, [older, filter, loadTasks]);
  // Search means the whole archive, regardless of the selected state pill or today's cutoff. That
  // is what makes a completed PR/task discoverable instead of merely searching the visible rows -
  // and the rows ARE the matches now, so there is nothing left here to filter them by.
  const bucket = (tasks || []).filter((x) => sent || (!filter || inBucket(x, filter)));
  // ONE RULE, FOR THE ROWS AND FOR THE COUNTS. The cut used to be decided per pill, which gave
  // `in progress` a wider window than `all` - live work of any age against today only - so two
  // live rows from last night counted for one pill and not the other and "all 5" sat over
  // "in progress 4 · done 2" (the owner, 2026-09-22: "that doesn't add up?").
  const keep = (x) => !!sent || !cutAway(stateOf(x).key, touchedToday(x), older);
  const shown = bucket.filter(keep);
  const nOlder = bucket.length - shown.length;
  // A count that outruns the rows beneath it reads as a bug: "done 175" over fifteen rows says
  // the list is broken, not cut. Each pill counts what clicking it would SHOW, by the same rule.
  const countIn = (key) => (tasks || []).filter((x) => (!key || inBucket(x, key)) && keep(x)).length;
  // A task may finish while its detail stays open (especially an assistant conversation). Move
  // the selected bucket with it so Done never sits under an In progress filter. Search and All
  // are deliberate cross-status views, so neither is changed.
  // ...but ONLY when the task changed under you. This also fired on the filter itself, which
  // made the pills unusable: with a done task selected, clicking "in progress" set the filter,
  // this read the still-done selection and put it straight back - the pill lit for an instant
  // and the list never moved.
  const seenState = useRef({ id: null, key: null });
  useEffect(() => {
    if (!active || !selected || !tasks || search || !filter) return;
    const row = tasks.find((x) => x.TaskId === selected);
    if (!row) return;
    const key = stateOf(row).key;
    const was = seenState.current;
    seenState.current = { id: selected, key };
    if (was.id === selected && was.key === key) return;   // nothing moved
    // A closed task opened from a deep link or another tab must not sit under a highlighted
    // In progress pill. New selections align the rail too; explicit filter clicks move the
    // selection in `changeFilter` below, so this cannot make the pills snap back.
    const next = filterForSelectedState(filter, key);
    if (next !== filter) { setFilter(next); setOlder(false); }
  }, [active, selected, tasks, search, filter]);

  // ...except when the owner ENDS it. The effect above exists so a task that moves state under
  // you stays on screen, and for done it did exactly the wrong thing: click Mark task done and
  // the view followed the task into the Done list and sat there on the row you had just
  // finished with. Closing a task is a statement that you are finished looking at it, so let go
  // of it and stay where the work is.
  const finish = async (status) => {
    // Mark task done always means "continue with the work still in progress", even when this task
    // was opened from All/search. Choose from the complete live bucket rather than `shown`, which
    // may be filtered or cut to today. Pre-record the state we are about to write: the server emits
    // task-changed during the PATCH, and without this guard that event can make the effect above
    // chase the closing task into Done before this continuation selects the next row.
    const liveIds = (tasks || []).filter((x) => inBucket(x, "live")).map((x) => x.TaskId);
    const transition = completionTransition(liveIds, selected, status);
    const before = seenState.current;
    seenState.current = transition.seen;
    setFilter(transition.filter); setOlder(false); setQuery("");
    try {
      // the shared road (PW-215): the same close the assistant's card runs - draft dismissed, agent stopped
      await runOperation(api, "task.complete", selected);
    } catch (e) {
      seenState.current = before;
      setErr(e?.response?.data?.detail || e?.message || "Failed to finish task");
      loadTasks();
      return;
    }
    onSelect(transition.next);
    loadTasks(); onChanged?.();
  };
  // The desktop page is a master/detail workspace. Opening it with a populated list but no
  // detail selected leaves most of the screen as a dead blank panel and makes the first click
  // compulsory. Follow the visible list to its first task on arrival (and after removing the
  // selected task); an explicitly selected task is never replaced when filters change.
  const firstShownId = shown[0]?.TaskId;
  // ...but never over the owner's own Close. The X on the detail means "show me the list", and
  // following the list straight back to its first row - the task just closed, whenever it leads
  // the list - made the X a flicker that landed you where you started (the owner, 2026-09-18:
  // "when you hit x ... it just flickers and comes back"). A real pick, or leaving and returning
  // to the tab, lifts it.
  const dismissed = useRef(false);
  const dismiss = () => { dismissed.current = true; onSelect(null); };
  useEffect(() => { if (selected || !active) dismissed.current = false; }, [selected, active]);
  useEffect(() => {
    if (active && !selected && firstShownId && !dismissed.current) onSelect(firstShownId);
  }, [active, selected, firstShownId, onSelect]);
  const changeFilter = (next) => {
    setFilter(next); setQuery(""); setOlder(false);
    if (!next || !selected) return;
    const row = (tasks || []).find((x) => x.TaskId === selected);
    if (!row || inBucket(row, next)) return;
    const replacement = (tasks || []).find((x) => inBucket(x, next))?.TaskId ?? null;
    seenState.current = { id: null, key: null };
    onSelect(replacement);
  };
  // The report is identified by its durable marker, not the actor label. Named coding agents
  // appear as coder/claude/codex in the record; requiring ActorType === "agent" hid valid results.
  const report = [...(detail?.comments || [])].reverse().find((c) => {
    const body = String(c.Body || "").trimStart();
    return /^CODER REPORT(?:\r?\n|$)/.test(body) && body.replace(/^CODER REPORT/, "").trim();
  });
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const liveRun = (detail?.runs || []).find((r) => r.Status === "running");
  // TWO QUESTIONS, TWO FLAGS. `liveCodingSession` answered both "is a session live on this page"
  // (so the whole page goes compact and the terminal gets the room) and "is this a coding CLI
  // with a diff to review". A general session is live but not coding, so it failed the test and
  // took the ROOMY block layout: a heading, then a near-empty band with one right-aligned
  // button, then the brain pill under a rule - three stacked rows where the coder gets one, on
  // the page where space is the whole point (the owner, 2026-09-16: "why is it so tall... you
  // are taking away precious agent space"). Live is live, whoever is working.
  const liveSession = !!term?.alive;
  // what fills the page: the session, unless the owner stepped back to the task behind it (peek)
  const sessionView = liveSession && !peek;
  // ...and a stage you opened by hand does not outlive the session you opened it on. The agent
  // finishes, its wrap-up writes the reply (coder.wrap), and the page went on showing the closed
  // pane with that draft folded away below (the owner, 2026-09-22: "when you hit session closed a
  // reply should automatically pop up"). Cleared, focusStage picks - and a draft ready outranks all.
  useEffect(() => { if (!liveSession) { setPeek(false); setOpenStage(null); } }, [liveSession]);
  const liveCodingSession = !isGeneral && liveSession;
  const agentWaiting = liveSession && isWaiting(term);
  // Proposals are queued after the reply, so they must not be mistaken for it - but they SHARE
  // its stage. lanes.json has one lane for both ("a reply or an action is drafted and waits for
  // your yes"), and one lane on the rail is one section on the page (the owner, 2026-09-22: "put
  // playbook proposal combined into the reply ready section as it's part of the approval/action").
  const pendingReview = pendingReplyReview(detail?.reviews || []);
  const proposals = pendingProposals(detail?.reviews || []);
  const sentReview = sentReplyReview(detail?.reviews || []);
  // A successful Review send is the reply even before (or when) the external channel ingests an
  // outbound copy. Put that receipt into the task's conversation as a real-looking outgoing
  // message; otherwise completed tasks showed one inbound message and claimed that was the whole
  // exchange while Notes separately said "Sent by email".
  const storedMessages = detail?.messages || [];
  const ownBodies = new Set(storedMessages
    .filter((m) => m.Status === "context" || m.Direction === "out")
    .map((m) => cleanText(m.BodyText)));
  const reviewMessages = (detail?.reviews || [])
    .filter((r) => ["approved", "edited", "sent"].includes(r.Status) && r.Kind !== "action")
    .map((r) => ({
      MessageId: `review:${r.ReviewId}`, ReviewSent: true, Direction: "out", Status: "context",
      Channel: storedMessages.find((m) => m.MessageId === r.MessageId)?.Channel || t?.Source || "email",
      FromName: "You", SentAt: r.DecidedAt || r.CreatedAt,
      Subject: storedMessages.find((m) => m.MessageId === r.MessageId)?.Subject || "Reply",
      BodyText: r.FinalText || r.DraftText || "",
    }))
    .filter((m) => cleanText(m.BodyText) && !ownBodies.has(cleanText(m.BodyText)));
  const taskMessages = [...storedMessages, ...reviewMessages]
    .sort((a, b) => tsMs(a.SentAt) - tsMs(b.SentAt));
  const sourceMessage = [...storedMessages].reverse()
    .find((m) => m.Status !== "context" && m.Direction !== "out");
  // ...and whether there is anybody at the other end of it (taskLifecycle.hasCorrespondent). Every
  // reply door hangs off this, so a task you typed yourself offers no reply to write.
  const replyMessage = hasCorrespondent(sourceMessage) ? sourceMessage : null;
  const workContext = t?.Playbook
    ? `Playbook · ${t.Playbook.title}${t.Playbook.uses?.length ? ` · uses ${t.Playbook.uses.join(", ")}` : ""}`
    : t?.Source === "report" && sourceMessage?.SourceName
      ? `Report · ${sourceMessage.SourceName}` : "";
  const askSender = async () => {
    const text = senderQuestion.trim();
    if (!selected || !sourceMessage?.MessageId || !text || askingSender) return;
    const id = selected;
    setAskingSender(true); setErr("");
    try {
      await api.post(`/api/tasks/${id}/clarify`, { body: text, message_id: sourceMessage.MessageId });
      if (stale(id)) return;
      setAskSenderOpen(false); setSenderQuestion("");
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not prepare the question for the sender");
    } finally { if (!stale(id)) setAskingSender(false); }
  };
  // The owner overturning the routing verdict: the task becomes theirs, any agent on it stops, and
  // - the half that never existed - they can say where the work actually lives. "Not for the agent"
  // only ever said where it does NOT go, so the next message like it was judged no better.
  const takeItMyself = async () => {
    if (!selected || savingMine) return;
    const id = selected;
    setSavingMine(true); setErr("");
    try {
      await api.post(`/api/tasks/${id}/not-coding`, { learn: true, belongs_to: belongsTo.trim() || null });
      if (stale(id)) return;
      setMineOpen(false); setBelongsTo("");
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not put the task on your list");
    } finally { if (!stale(id)) setSavingMine(false); }
  };
  const openReply = async (generate = false) => {
    if (!replyMessage?.MessageId || openingReply) return;
    const id = selected;
    setOpeningReply(generate ? "generate" : "write"); setErr("");
    try {
      await api.post(`/api/messages/${replyMessage.MessageId}/reply`, { draft: generate });
      if (stale(id)) return;
      await loadDetail(id);
      onChanged?.();
    } catch (e) { if (!stale(id)) setErr(e?.response?.data?.detail || "Could not open the reply"); }
    if (!stale(id)) setOpeningReply(false);
  };
  // The task itself leads when no coding terminal is open. Triage already distilled an inbound
  // item into Title + Summary; falling back to its newest inbound body keeps older/promoted rows
  // equally useful. This is the human TODO, not an agent-launch advertisement.
  const taskAsk = cleanText(t?.Summary || sourceMessage?.BodyText || "");
  // WHAT THEY ACTUALLY SAID. A task opens on one message and then keeps collecting the rest of
  // the conversation - three WhatsApp voice notes seconds apart are one thought, and ingest
  // attaches the later ones to the same task. The panel showed the FIRST and nothing else, so a
  // task whose answer arrived in message three read as an unanswered question (owner, 2026-09-02).
  const inbound = storedMessages.filter((m) => m.Status !== "context" && m.Direction !== "out");
  const alsoSaid = inbound.filter((m) => m.MessageId !== inbound[0]?.MessageId
                                      && cleanText(m.BodyText) && cleanText(m.BodyText) !== taskAsk);
  const completionIsManual = ownerControlsCompletion(t);
  const interruptedTask = String(t?.Tags || "").split(/[\s,]+/).includes("interrupted");
  const taskState = taskPhase(t?.Status);
  // the triage verdict behind THIS task, for "Where this came from"
  const sourceRoute = (detail?.routes || []).find((r) => r.MessageId === sourceMessage?.MessageId);
  // WHAT RUNS THIS, in the vocabulary the brain layer landed on 2026-09-16: a ROLE picks the
  // document (every coding task's role is `coder`), a BRAIN is the CLI that runs it, and the model
  // is the brain's - it is not a property of the task, so the card does not offer one. A live
  // session names the CLI it was ASKED to run; otherwise the roster says which brain the role uses.
  const runRole = assignedAgent(t?.Assignee) || (t?.Kind === "coding" ? "coder" : "");
  // NAME THE BRAIN, NOT THE PRODUCT. `term.cli` is hardcoded to the string "taskuary" on every
  // general session (general.info), so the one card that could not say which brain was running
  // read "brain taskuary" - the product's own name, on the row whose whole job is to answer that
  // (the owner, 2026-09-16). A general session reports what it actually reached for instead:
  // `provider` is the connector's or the CLI's own label, `model` the gear it runs on.
  // ...and once that session is GONE, what it actually ran on (detail.ranOn: the saved pick a general
  // session resumes from, or the transcript's brain) - never the roster, which names what the role
  // WOULD run on today. A researcher session on the owner's Azure connector read "brain claude" an
  // hour after it closed, because that is the default for a role with no override (2026-09-22).
  const runBrain = term?.provider || term?.cli || term?.agent || detail?.ranOn?.brain || (runRole && brains[runRole]) || "";
  // ...and on a general session that brain is ALREADY on screen, as the live picker in the
  // workspace toolbar a few pixels below - the same two facts twice, one of them editable and one
  // of them stale ("why is it there, the model is below it?"). The pill goes where the picker is.
  const brainPill = runBrain && !(isGeneral && term?.alive) ? runBrain : "";
  // the envelope on the reply, read from the same Deliver blob Review reads
  const replyOf = pendingReview || sentReview;
  const replyCc = deliveryCc(replyOf), replyFiles = deliveryFiles(replyOf);
  const replyPrimary = pendingReview ? "Open the draft" : sentReview ? "Write another" : "Write reply";
  const checklist = detail?.checklist || [];
  const checklistPct = checklist.length ? (checklist.filter((i) => i.done).length / checklist.length) * 100 : 0;
  const tickItem = async (i) => {
    try {
      const { data } = await api.patch(`/api/tasks/${t.TaskId}/checklist/${i.id}`, { done: !i.done });
      loadDetail(t.TaskId);
      // the last tick closed it (server: tick_checklist): the list and the rail move with it now,
      // not on the next poll, or the row you just finished sits there looking open
      if (data?.closed) { loadTasks(); onChanged?.(); }
    } catch { /* the list reloads on the next refresh */ }
  };
  // what the folded strip says on its left: the header already has the id, title and state, so
  // this carries the two things it cannot - how far the list got, and what the task is
  const foldedFacts = [checklist.length ? progressLine(checklist) : "", kindLabel(t?.Kind || "task"),
    t?.Assignee ? assigneeLabel(t.Assignee) : "", repoOf(t) || ""].filter(Boolean).join(" · ");
  const generalStarted = isGeneral && (!!term?.alive || hasGeneralHistory
    || String(t?.Tags || "").split(/[\s,]+/).includes(ASK_TAG));
  // ONE BAR, THE SAME BAR. The Task and Reply cards both open with [ primary ] | [ named ]
  // [ named ] ... fact, and the Agent card alone answered with a row of default-size buttons UNDER
  // its body, in a different order, with no rule between the move and the alternatives (the owner,
  // 2026-09-16: "this agent card is still weird and doesn't match ... it should match the other
  // ones"). Coding and general differ only in WHICH session is picked back up, so it is one bar.
  const canContinue = !term?.alive && (isGeneral ? generalStarted : !!detail?.resumable);
  const canSave = !report && !wrapped;            // nothing filed yet, so this session is still worth writing up
  const agentBar = !term?.alive && !restartOpen && (isGeneral ? generalStarted : !!(report || detail?.transcript));
  const agentState = agentPhase({
    session: term?.alive ? { ...term, waiting: isWaiting(term) } : null,
    run: liveRun, transcript: detail?.transcript, report,
    conversation: generalStarted,
  });
  const workspaceMode = agentWorkspaceMode({ isGeneral, generalStarted, session: term, wrapping, wrapped });
  const replyState = replyPhase(detail?.reviews || []);
  // ONE question per page. A running session is itself the agent stage, so it is never folded; the
  // hand-picked stage wins over the computed one until you leave the task (start an agent on a task
  // whose draft is waiting, or answer a sender the agent is still working for).
  // ...and stepping back from a live session (peek) opens the TASK stage: the point of the step was
  // to read what the task is and where it came from, and that lives on the task card, not folded
  // to a strip under a heading that says the agent is working.
  const stage = sessionView ? "agent" : (openStage || (peek ? "task" : focusStage({
    kind: t?.Kind, task: taskState, agent: agentState, reply: replyState, hasSender: !!replyMessage,
    // what the agent is parked ON decides whether the proposal or the agent opens: an agent
    // waiting for approval is released by the very proposal sitting in stage 3
    proposal: proposals.length > 0, agentSub: term ? subState(term) : null,
  })));
  // only a folded heading is a control: exactly one stage is open, so clicking the open one has
  // nothing to do and must not offer a chevron that does nothing.
  const stageProps = (name) => ({ folded: stage !== name, onToggle: stage === name ? null : () => setOpenStage(name) });
  const startCodingAgent = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("coding"); setErr("");
    try {
      // one shared dispatch for coding too (PW-216): the kind switch, the live-worker check (409), the unknown
      // agent (422) and the repository come from the same road the general button and the assistant use -
      // no Kind PATCH before a terminal, so a failed start never leaves a relabelled, unstarted task
      const data = await runOperation(api, "dispatch.prepare", id, { kind: "coding", agent: run.agent, brain: run.brain || null,
        model: run.model || null, instructions: run.instruction.trim() || null });
      if (!stale(id)) setTerm(data?.session || null);
      if (!stale(id)) {
        setRun((current) => ({ ...current, instruction: "" }));
        setRestartOpen(false);
      }
    } catch (e) {
      if (stale(id)) return;
      // A repository still to choose is the same QUESTION here as on the terminal road: open the
      // chooser and resume this start on the answer. Printing the sentence instead sent the owner
      // looking for a task menu that no longer exists (2026-09-22).
      const msg = e?.response?.data?.detail || e?.message || "Could not start the coding agent";
      if (e?.outcome?.dispatch === "needs_repo" || /no local path|could not tell which checkout/i.test(msg)) {
        setErr(""); setRepoPick(true); setResumeAfterRepo({ dispatch: true });
      } else setErr(msg);
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  const startGeneralAgent = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("general"); setErr("");
    try {
      // one shared dispatch whatever the task's kind was: it switches the kind, starts (or reuses) the
      // assistant session and records the live worker - a relabelled task is not a started one (PW-213)
      // profile, brain and model - whichever of them was chosen; blank means "as configured"
      const { data } = await api.post(`/api/tasks/${id}/dispatch`,
        { kind: "general", agent: run.agent || null, pick: run.pick || null, model: run.model || null });
      const outcome = outcomeOf(data);
      if (!stale(id)) setTerm(outcome.state === "started" || outcome.state === "existing" ? (data.session || null) : null);
      if (!stale(id)) setRestartOpen(false);
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not start the non-coding agent");
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  // Reopening the agent's OWN conversation - the assistant through /resume, a coding pane through
  // its saved session id. Two roads because the two agents are held differently; one button, one
  // set of words, because to the owner it is the same act (2026-09-15).
  const continueSession = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("resume"); setErr("");
    try {
      await api.post(`/api/tasks/${id}/continue-session`);
      if (!stale(id)) setGeneralRevision((n) => n + 1);
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not continue this session");
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  const resumeGeneralAgent = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("resume"); setErr("");
    try {
      await api.post(`/api/tasks/${id}/resume`);
      if (!stale(id)) setGeneralRevision((n) => n + 1);
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not resume this conversation");
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  // THE BAR THE AGENT CARD ACTS THROUGH, built here so it can ride inside the heading beside the
  // chip - where the Task and Reply strips keep theirs. Group one is THIS session, group two is
  // another one, and exactly one move is filled. It is an element, not a component: the handlers
  // it calls are declared just above, and a component defined mid-render remounts on every keystroke.
  const agentBarRow = (
    <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
      {canContinue && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent} sx={primaryBtn}
        startIcon={startingAgent === "resume" ? <CircularProgress size={12} /> : <HistoryIcon sx={{ fontSize: 16 }} />}
        title={isGeneral
          ? "Reopens the saved provider conversation and continues from its existing context."
          : `Reopens ${detail?.resumable?.agent}'s own session in ${detail?.resumable?.cwd}. It still has what it read, changed and asked.`}
        onClick={isGeneral ? resumeGeneralAgent : continueSession}>
        {startingAgent === "resume" ? "Continuing…" : "Continue this session"}</Button>}
      {canSave && <Button size="small" variant={canContinue ? "outlined" : "contained"} disableElevation
        disabled={!!wrapping} sx={canContinue ? barBtn : primaryBtn}
        startIcon={<DoneAllIcon sx={{ fontSize: 16, color: canContinue ? "#6f8a6e" : undefined }} />}
        title="Writes up what this session did and files it as the task's result. The task stays open: Mark task done completes it and drafts the reply."
        onClick={wrapUp}>{isGeneral ? "Save this conversation's result" : "Save stopped run result"}</Button>}
      {!isGeneral && <>
        {(canContinue || canSave) && <Divider orientation="vertical" flexItem sx={{ mx: 0.4, my: 0.6, borderColor: BORDER }} />}
        <Button size="small" variant={canContinue || canSave ? "outlined" : "contained"} disableElevation
          sx={canContinue || canSave ? barBtn : primaryBtn}
          startIcon={<RefreshIcon sx={{ fontSize: 16, color: canContinue || canSave ? "#6f8a6e" : undefined }} />}
          title="A fresh session with a different harness, model or prompt. It receives the saved result, not the old conversation."
          onClick={() => setRestartOpen(true)}>Run another agent</Button>
      </>}
      {report && <>
        {isGeneral && <Divider orientation="vertical" flexItem sx={{ mx: 0.4, my: 0.6, borderColor: BORDER }} />}
        <Button size="small" variant="outlined" sx={barBtn}
          startIcon={<ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a" }} />}
          title="Forwards the saved result to a person. The AI writes it, you send it."
          onClick={() => setHandoff(true)}>Send this result to someone</Button>
      </>}
    </Box>
  );
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      {/* ── list: one anchored panel - filter header on top, rows scroll inside ── */}
      {/* 372, not 340: the header ran ~6px over - "done 30" lost its last digit, and a count
          you cannot read is worse than no count. The extra room buys the row titles a few
          characters too, which is where taskuary#18 [Containerization]... was being cut. */}
      {/* On a phone the two panes take turns: the list until a task is picked, then the task, and
          its Close (back to the list) button is the way back. Side by side they were 372px of list
          and a detail pane pushed clean off the right edge - a selected task showed nothing. */}
      <Box sx={{ width: { xs: "100%", md: 372 }, flexShrink: 0, display: { xs: selected ? "none" : "block", md: "block" } }}>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
        <Box sx={{ ...card, p: 0, overflow: "hidden", display: "flex", flexDirection: "column",
          height: "calc(100vh - 118px)", minHeight: 420 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.75,
            borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2, flexShrink: 0 }}>
            {/* each pill says how many rows it would put on screen (countIn) - a filter you cannot
                size up is a guess, and one that counts rows it does not show is worse.
                The pills give way, never the New button: four-digit counts must not be able to
                push it off the edge of a 340px panel again. */}
            <Box sx={{ flex: 1, minWidth: 0, overflowX: "auto", "&::-webkit-scrollbar": { display: "none" },
              scrollbarWidth: "none" }}>
              <FilterPills value={search ? "" : filter} onChange={changeFilter}
                options={STATE_FILTERS.map((f) => ({ ...f, n: !tasks ? null : countIn(f.key) }))} />
            </Box>
            {/* flexShrink: the pills would otherwise squeeze this until only half the + was
                left on screen, and a clipped button reads as a rendering fault */}
            <Button size="small" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => setNewOpen(true)}
              sx={{ flexShrink: 0, minWidth: "auto", px: 1 }}>New</Button>
          </Box>
          <Box sx={{ px: 1, py: 0.75, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL2, flexShrink: 0 }}>
            <TextField fullWidth size="small" placeholder="Search system, name, summary, PR…" value={query}
              onChange={(e) => setQuery(e.target.value)}
              inputProps={{ "aria-label": "Search all tasks" }}
              InputProps={{
                startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 16, color: FAINT }} /></InputAdornment>,
                endAdornment: query ? <InputAdornment position="end"><IconButton size="small" aria-label="Clear task search"
                  onClick={() => setQuery("")}><CloseIcon sx={{ fontSize: 15 }} /></IconButton></InputAdornment> : null,
              }}
              sx={{ "& .MuiOutlinedInput-root": { bgcolor: "#fff", fontSize: 12.5 } }} />
          </Box>
          {/* rows as separated cards on a soft ground - air between tasks instead of a ruled
              ledger, selection said with the border alone. Scandinavian: fewer lines, calmer. */}
          <Box sx={{ overflowY: "auto", flex: 1, bgcolor: "#f1ede7", px: 1, py: 1 }}>
            {!tasks ? <CircularProgress size={20} sx={{ m: 2 }} /> : !shown.length && !nOlder
              ? <Empty>{search ? `No tasks match “${search}”.`
                : !tasks.length ? "No tasks yet — they arrive from the Timeline as work comes in, or start one with New."
                : "Nothing here."}</Empty> : shown.map((task) => {
              const st = stateOf(task), sel = selected === task.TaskId;
              const list = rowChecklist(task), nDone = list.filter((i) => i.done).length;
              const asked = askedAgo(task), worker = assignedAgent(task.Assignee);
              return (
              // the selected row is outlined in its STATE's colour - a working task in the same sage as
              // its chip - not in the brand slate, which read as a fourth state nobody could name. The
              // left rule wears it always, so the column can be scanned without reading a single word.
              <Box key={task.TaskId} onClick={() => onSelect(task.TaskId)} data-tq-task-row=""
                sx={{ px: 1.25, py: 0.9, mb: 0.75, cursor: "pointer", bgcolor: "#fff", borderRadius: 1.75,
                  border: `1px solid ${sel ? st.solid : BORDER}`, borderLeft: `3px solid ${st.solid}`,
                  boxShadow: sel ? "0 1px 8px rgba(47,107,79,.14)" : "none",
                  transition: "border-color .12s, box-shadow .12s",
                  "&:hover": { borderColor: sel ? st.solid : "#d8cfbe", borderLeftColor: st.solid } }}>
                {/* THE TITLE FIRST. It used to come third, under as many as five chips - ref, kind,
                    task phase, state, agent - which wrap to two lines on a 372px rail, so the one
                    line that says what the task IS was the last thing read (the owner, 2026-09-16).
                    The age moves up here too: nothing can push it off a row it shares only with a
                    title that is allowed to ellipsis. */}
                <Box sx={{ display: "flex", gap: 1, alignItems: "baseline", minWidth: 0 }}>
                  <Typography noWrap sx={{ color: INK, fontSize: 13, fontWeight: 600, lineHeight: 1.3, flex: 1, minWidth: 0 }}>
                    {task.Title}
                  </Typography>
                  <Typography data-tq-task-age="" sx={{ color: FAINT, fontSize: 10.5, whiteSpace: "nowrap", flexShrink: 0 }}>
                    {timeAgo(task.CreatedAt)}
                  </Typography>
                </Box>
                {/* the identity line. WHO works it stays on every row - the split that decides whether
                    it reaches the Board at all (the owner, 2026-09-10) - but as words, not chips: the
                    state is the only thing here allowed a shape, and it is now said ONCE. "task · in
                    progress" used to sit beside "agent working", the same duplication the detail
                    header carried. */}
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", mt: 0.4, minWidth: 0 }}>
                  <Typography noWrap sx={{ color: FAINT, fontSize: 10.5, flex: 1, minWidth: 0 }}>
                    <Box component="span" data-tq-task-ref="" sx={{ color: "#55697a", fontWeight: 750,
                      fontVariantNumeric: "tabular-nums", letterSpacing: ".015em" }}>{task.ref}</Box>
                    {` · ${shortKind(task.Kind)}`}{worker ? ` · ${worker}` : ""}
                  </Typography>
                  {task.Priority === "urgent" && <Chip size="small" label="urgent" sx={{ bgcolor: PILL_COLORS.red.bg,
                    color: PILL_COLORS.red.fg, height: 17, fontSize: 9.5, flexShrink: 0 }} />}
                  {String(task.Tags || "").split(/[\s,]+/).includes("interrupted") && <Chip size="small" label="interrupted"
                    title="Taskuary closed while an agent was working this. Nothing restarts until you choose an agent."
                    sx={{ height: 17, fontSize: 9.5, bgcolor: "#eee7d6", color: "#7a5c1e", flexShrink: 0 }} />}
                  <StateChip task={task} />
                </Box>
                {/* the third line, and ONLY when it has something to say - a queued task with no list
                    stays two lines, so the rail does not pay for this everywhere */}
                {(list.length > 0 || asked) && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.9, mt: 0.55, minWidth: 0 }}>
                    {list.length > 0 && <LinearProgress variant="determinate" value={(nDone / list.length) * 100}
                      sx={{ width: 68, height: 3, borderRadius: 2, bgcolor: PANEL2, flexShrink: 0,
                        "& .MuiLinearProgress-bar": { bgcolor: "#6f8a6e" } }} />}
                    <Typography noWrap sx={{ fontSize: 10.5, flex: 1, minWidth: 0,
                      color: asked ? st.solid : FAINT, fontWeight: asked ? 600 : 400 }}>
                      {[asked, list.length ? `${nDone} of ${list.length} done` : ""].filter(Boolean).join(" · ")}
                    </Typography>
                  </Box>
                )}
                {task.Playbook && <Typography variant="caption" noWrap sx={{ color: "#6b5f45", display: "block", mt: 0.2 }}>
                  Playbook · {task.Playbook.title}
                </Typography>}
                {!task.Playbook && task.Source === "report" && task.SearchSources
                  && <Typography variant="caption" noWrap sx={{ color: "#6b5f45", display: "block", mt: 0.2 }}>
                    Report · {String(task.SearchSources).split(",")[0]}
                  </Typography>}
                {search && <Typography variant="caption" noWrap sx={{ color: FAINT, display: "block", mt: 0.2 }}>
                  {[task.Source, task.SearchSources, task.Summary].filter(Boolean).join(" · ")}
                </Typography>}
              </Box>
              );
            })}
            {tasks && nOlder > 0 && (
              <Button size="small" fullWidth onClick={() => setOlder(true)} sx={{ color: DIM, fontSize: 11.5, mt: 0.25 }}>
                {shown.length ? `show ${nOlder} more from before today` : `nothing from today — show ${nOlder} older`}
              </Button>
            )}
          </Box>
        </Box>
      </Box>

      {/* ── detail ────────────────────────────────────────────────────── */}
      <Box sx={{ ...frame, flex: 1, minWidth: 0, height: "calc(100vh - 118px)", minHeight: 420,
        display: { xs: selected ? "block" : "none", md: "block" } }}>
        <Box sx={{ ...frameInner, height: "100%", display: "flex", flexDirection: "column" }}>
          {!t ? (
            <Box sx={{ height: "100%", display: "grid", placeItems: "center" }}>
              {selected ? <CircularProgress size={20} /> : <Empty>{tasks?.length ? "Select a task to see its full story." : "The task you open will show here — its messages, its session, its history."}</Empty>}
            </Box>
          ) : (
            <>
              {/* header strip: ONE LINE, and it is the Task card's heading too. It used to be a
                  tall block - id, title, dots, close, then "from email · created 10h ago by router"
                  - sitting directly above a second heading that said "Task · the job itself". The
                  provenance line moved into "Where this came from" inside the card, where you go
                  and look at it rather than read it every time. */}
              <Box sx={{ px: liveSession ? 1.5 : 1.75, py: liveSession ? 0.7 : 1,
                bgcolor: "#fff", borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
                <Box sx={{ display: "flex", gap: 0.9, alignItems: "center" }}>
                  <Box sx={{ width: 18, height: 18, borderRadius: "50%", bgcolor: "#55697a", color: "#fff",
                    display: "grid", placeItems: "center", flexShrink: 0, fontSize: 9.5, fontWeight: 800 }}>1</Box>
                  <Typography sx={{ color: "#41525f", fontVariantNumeric: "tabular-nums", flexShrink: 0,
                    letterSpacing: ".015em", fontWeight: 750, fontSize: 11.5 }}>{detail.ref}</Typography>
                  <Typography sx={{ color: INK, flex: 1, fontWeight: 650,
                    fontSize: liveSession ? 12.5 : 13,
                    minWidth: { xs: 90, sm: 180 }, letterSpacing: "-.005em" }} noWrap>
                    {t.Title}
                  </Typography>
                  {/* the list row said this and the task page did not, so a held task looked merely open */}
                  {interruptedTask && <Chip size="small" label="interrupted"
                    title="Taskuary closed while an agent was working this. Nothing restarts until you choose one."
                    sx={{ height: 17, fontSize: 9.5, bgcolor: "#eee7d6", color: "#7a5c1e", flexShrink: 0 }} />}
                  {/* A LIVE SESSION HIDES THE TASK CARD ENTIRELY (the gate is !term?.alive below), so
                      with the card goes every task control - and the owner wants the session to keep
                      the space (2026-09-16: "if agent in progress we want it small to give the most
                      space to the agent canvas"). The four controls ride up here instead: the same
                      four, in the same order, labels dropped to icons after the first. */}
                  {sessionView && !["done", "dropped"].includes(t.Status) && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, flexShrink: 0 }}>
                      <Button size="small" variant="contained" disableElevation startIcon={<DoneAllIcon sx={{ fontSize: 13 }} />}
                        sx={{ fontSize: 10.5, minHeight: 24, py: 0, px: 1 }}
                        title="Closes the task and ends the live agent session with it."
                        onClick={() => finish("done")}>Mark task done</Button>
                      <Tooltip title="Not a task — delete it and teach triage why">
                        <IconButton size="small" sx={{ color: "#7a2f3c" }} onClick={() => setConfirmNAT(true)}>
                          <BlockIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                      <Tooltip title="Hand it to a person — the AI writes the forward, you send it">
                        <IconButton size="small" sx={{ color: "#55697a" }} onClick={() => setHandoff(true)}>
                          <ForwardToInboxIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                      <Tooltip title="Split or merge — break it in two, or fold it into the task it repeats">
                        <IconButton size="small" sx={{ color: "#6f8a6e" }} onClick={() => setReshape(true)}>
                          <CallSplitIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                    </Box>
                  )}
                  <LifecycleChip kind="task" phase={taskState} compact sx={{ flexShrink: 0 }} />
                  {/* ONE X, TWO STEPS BACK. With the session filling the page, X first steps back to
                      the task behind it - the session keeps running; from the task, X goes to the list. */}
                  <Tooltip title={sessionView ? "Back to the task — the session keeps running" : "Close — back to the list (the task stays)"}>
                    <IconButton size="small" onClick={() => (sessionView ? setPeek(true) : dismiss())}><CloseIcon sx={{ fontSize: 15 }} /></IconButton>
                  </Tooltip>
                </Box>
                {workContext && <Typography variant="caption" sx={{ color: "#6b5f45", display: "block",
                  mt: 0.15, ml: 3.4, fontWeight: 650, fontSize: 10 }}>
                  {workContext}
                </Typography>}
              </Box>
              {/* a flex column so the terminal takes exactly what is left between the strip above and the
                  waiting room below - a fixed-height formula clipped its bottom line on shorter screens */}
              <Box sx={{ px: liveSession ? 1 : 2, py: liveSession ? 0.65 : 1.5,
                overflowY: "auto", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
                {/* THE SESSION IS THE PAGE. Your CLI, in this task's repo, with the task in
                    its lap - you type into it like any other terminal. Everything below is
                    reference material about the same task, folded away. */}
                {/* the session just closed: its write-up takes the space the terminal had, so the
                    result of the work is the thing you are looking at */}
                {/* The checkout, and why. A wrong guess means an agent editing the wrong tree in
                    good faith, so it is stated on the page rather than buried in the prompt. */}
                {!sessionView && (
                  <Box sx={{ ...card, mb: 1.25, px: 1.5, py: stage === "task" ? 1.5 : 0.85,
                    bgcolor: "#fff", flexShrink: 0, borderLeft: "4px solid #55697a" }}>
                    {/* FOLDED - the same controls the open card has, in the same order, with their
                        labels dropped. The left half carries what the header cannot: how far the
                        checklist got, and what the task is. The whole strip reopens the task. */}
                    {stage !== "task" && (
                      <Box onClick={() => setOpenStage("task")}
                        sx={{ display: "flex", alignItems: "center", gap: 0.85, minWidth: 0, cursor: "pointer", flexWrap: { xs: "wrap", sm: "nowrap" } }}>
                        <Typography sx={{ color: FAINT, fontSize: 9, fontWeight: 750, letterSpacing: 1.35, flexShrink: 0 }}>TASK</Typography>
                        <Typography noWrap sx={{ color: DIM, fontSize: 11.5, flex: 1, minWidth: 0 }}>{foldedFacts}</Typography>
                        {!["done", "dropped"].includes(t.Status) && (
                          <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.35, flexShrink: 0, flexBasis: { xs: "100%", sm: "auto" }, order: { xs: 9, sm: 0 } }}>
                            <Button size="small" variant="contained" disableElevation startIcon={<DoneAllIcon sx={{ fontSize: 14 }} />}
                              sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                              title="Closes the task and ends the live agent session with it."
                              onClick={() => finish("done")}>Mark task done</Button>
                            <Tooltip title="Not a task — delete it and teach triage why">
                              <IconButton size="small" sx={{ color: "#7a2f3c" }} onClick={() => setConfirmNAT(true)}>
                                <BlockIcon sx={{ fontSize: 16 }} /></IconButton>
                            </Tooltip>
                            <Divider orientation="vertical" flexItem sx={{ mx: 0.25, my: 0.5, borderColor: BORDER }} />
                            <Tooltip title="Hand it to a person — the AI writes the forward, you send it">
                              <IconButton size="small" sx={{ color: "#55697a" }} onClick={() => setHandoff(true)}>
                                <ForwardToInboxIcon sx={{ fontSize: 16 }} /></IconButton>
                            </Tooltip>
                            <Tooltip title="Split or merge — break it in two, or fold it into the task it repeats">
                              <IconButton size="small" sx={{ color: "#6f8a6e" }} onClick={() => setReshape(true)}>
                                <CallSplitIcon sx={{ fontSize: 16 }} /></IconButton>
                            </Tooltip>
                          </Box>
                        )}
                        <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0, transform: "rotate(-90deg)" }} />
                      </Box>
                    )}
                    {stage === "task" && <>
                    {/* 1 - WHAT YOU CAN DO. The two endings first, grouped, then a rule, then the two
                        reroutes. Nothing behind a menu: "no one knows where the other buttons were
                        unless you click the 3 options" (the owner, 2026-09-16). */}
                    {!["done", "dropped"].includes(t.Status) ? (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
                        <Button size="small" variant="contained" disableElevation startIcon={<DoneAllIcon sx={{ fontSize: 16 }} />}
                          sx={primaryBtn}
                          title="Closes the task and ends the live agent session with it."
                          onClick={() => finish("done")}>Mark task done</Button>
                        <Button size="small" variant="outlined" startIcon={<BlockIcon sx={{ fontSize: 15 }} />}
                          sx={{ ...barBtn, color: "#7a2f3c", borderColor: "#e0c6cb" }}
                          title="Delete it and teach triage why — the sender keeps writing to you."
                          onClick={() => setConfirmNAT(true)}>Not a task</Button>
                        <Divider orientation="vertical" flexItem sx={{ mx: 0.4, my: 0.6, borderColor: BORDER }} />
                        <Button size="small" variant="outlined" sx={barBtn}
                          startIcon={<ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a" }} />}
                          title="Not ours to do — the AI writes the forward, you send it."
                          onClick={() => setHandoff(true)}>Hand it to a person</Button>
                        <Button size="small" variant="outlined" sx={barBtn}
                          startIcon={<CallSplitIcon sx={{ fontSize: 16, color: "#6f8a6e" }} />}
                          title="Two jobs in here, or a duplicate? Break it in two, or fold it into the task it repeats."
                          onClick={() => setReshape(true)}>Split or merge</Button>
                      </Box>
                    ) : (
                      <Button size="small" variant="outlined" startIcon={<RefreshIcon sx={{ fontSize: 15 }} />}
                        title="Reopens the task only. No agent starts until you choose one."
                        onClick={reopen}>Reopen task</Button>
                    )}
                    <Divider sx={{ my: 1.4, borderColor: BORDER }} />
                    {/* 2 - WHAT THERE IS TO DO. The title is in the header now; repeating it here was
                        the same words twice, an inch apart. */}
                    <Box sx={{ minWidth: 0 }}>
                        <Typography variant="overline" sx={{ color: FAINT, fontSize: 9,
                          fontWeight: 750, letterSpacing: 1.35, lineHeight: 1.2, display: "block" }}>What needs doing</Typography>
                        {taskAsk && (
                          <Typography variant="body2" sx={{ color: DIM, mt: 0.45, lineHeight: 1.55,
                            whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxWidth: 900,
                            display: "-webkit-box", WebkitLineClamp: 5, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                            {taskAsk}
                          </Typography>
                        )}
                        {/* the checklist triage drew from the ask (PW-075): boxes are progress on the list,
                            never task completion - closing the task stays the owner's separate decision.
                            The WHOLE LINE is the target, not the 16px box: on a manual task ticking these
                            off IS the work (the owner, 2026-09-16), and a box that small did not look
                            like something you were meant to click. */}
                        {(detail?.checklist || []).length > 0 && (
                          <Box sx={{ mt: 0.85, maxWidth: 900 }}>
                            {detail.checklist.map((i) => (
                              <Box key={i.id} onClick={() => tickItem(i)}
                                sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.75, ml: -0.75, py: 0.15,
                                  borderRadius: 1, cursor: "pointer", "&:hover": { bgcolor: "#faf8f4" } }}>
                                <Checkbox size="small" checked={!!i.done} onChange={() => {}} tabIndex={-1}
                                  sx={{ p: 0.25, pointerEvents: "none", color: "rgba(0,0,0,.54)", "&.Mui-checked": { color: "#6f8a6e" } }} />
                                <Typography variant="body2" sx={{ color: i.done ? FAINT : INK, textDecoration: i.done ? "line-through" : "none", lineHeight: 1.6 }}>
                                  {i.text}
                                </Typography>
                              </Box>
                            ))}
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.6 }}>
                              <LinearProgress variant="determinate" value={checklistPct} sx={{ width: 120, height: 4,
                                borderRadius: 2, bgcolor: PANEL2, "& .MuiLinearProgress-bar": { bgcolor: "#6f8a6e" } }} />
                              <Typography variant="caption" sx={{ color: FAINT }}>{progressLine(detail.checklist)}</Typography>
                            </Box>
                          </Box>
                        )}
                        {/* the rest of what they said, in order - indented so it reads as the same
                            person continuing rather than as separate business */}
                        {alsoSaid.map((m) => (
                          <Box key={m.MessageId} sx={{ mt: 0.6, pl: 1, borderLeft: `2px solid ${BORDER}`, maxWidth: 900 }}>
                            <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>
                              {m.FromName || m.FromEmail || m.Channel}{m.SentAt ? ` · ${fmtDateTime(m.SentAt)}` : ""}
                            </Typography>
                            <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap",
                              overflowWrap: "anywhere", display: "-webkit-box", WebkitLineClamp: 4,
                              WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                              {cleanText(m.BodyText)}
                            </Typography>
                          </Box>
                        ))}
                        {/* WHERE THIS CAME FROM - the header's old "from email · created 10h ago by
                            router" caption, turned into something worth reading: the message, what
                            triage decided about it and why, then the task it made. At the END of the
                            task list, because it is the last thing in the task's story. */}
                        <Box sx={{ display: "flex", gap: 0.8, alignItems: "center", flexWrap: "wrap", mt: 1 }}>
                          <Button size="small" variant="outlined" onClick={() => setSourceOpen((v) => !v)}
                            startIcon={<AltRouteIcon sx={{ fontSize: 15 }} />}
                            endIcon={<ExpandMoreIcon sx={{ fontSize: 16, transition: "transform .15s",
                              transform: sourceOpen ? "rotate(180deg)" : "none" }} />}
                            sx={{ minHeight: 26, py: 0, px: 1, fontSize: 11.5, color: DIM, borderColor: BORDER }}>
                            Where this came from
                          </Button>
                          {!!detail.attachments?.length && <Chip size="small" icon={<AttachFileIcon sx={{ fontSize: 13 }} />}
                            label={`${detail.attachments.length} attachment${detail.attachments.length === 1 ? "" : "s"}`}
                            sx={{ height: 19, fontSize: 10, bgcolor: PANEL2 }} />}
                        </Box>
                        {sourceOpen && (
                          <Box sx={{ mt: 0.85, maxWidth: 900, border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden" }}>
                            {sourceMessage && (
                              <Box sx={{ p: 1.1, display: "flex", gap: 1.1, alignItems: "flex-start" }}>
                                <ChannelIcon channel={sourceMessage.Channel} sx={{ color: "#55697a", mt: 0.25 }} />
                                <Box sx={{ minWidth: 0, flex: 1 }}>
                                  <Box sx={{ display: "flex", gap: 0.75, alignItems: "baseline", flexWrap: "wrap" }}>
                                    <Typography sx={{ color: INK, fontSize: 11.5, fontWeight: 650 }}>
                                      {sourceMessage.FromName || sourceMessage.FromEmail || sourceMessage.Channel}
                                    </Typography>
                                    <Typography variant="caption" sx={{ color: FAINT }}>
                                      {sourceMessage.SentAt ? `· ${fmtDateTime(sourceMessage.SentAt)}` : ""}
                                      {inbound.length > 1 ? ` · ${inbound.length} messages` : ""}
                                    </Typography>
                                    {sourceMessage.SourceLink && <Link href={sourceMessage.SourceLink} target="_blank"
                                      rel="noopener" sx={{ fontSize: 11 }}>open the original</Link>}
                                  </Box>
                                  {sourceMessage.Subject && <Typography variant="body2" sx={{ color: INK, fontWeight: 600, mt: 0.1 }}>
                                    {sourceMessage.Subject}</Typography>}
                                  <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap",
                                    overflowWrap: "anywhere", display: "-webkit-box", WebkitLineClamp: 3,
                                    WebkitBoxOrient: "vertical", overflow: "hidden" }}>{cleanText(sourceMessage.BodyText)}</Typography>
                                </Box>
                              </Box>
                            )}
                            {sourceRoute && (
                              <Box sx={{ p: 1.1, bgcolor: PANEL2, borderTop: `1px solid ${BORDER}`,
                                display: "flex", gap: 1.1, alignItems: "flex-start" }}>
                                <AltRouteIcon sx={{ fontSize: 16, color: ACCENT2, mt: 0.3 }} />
                                <Box sx={{ minWidth: 0, flex: 1 }}>
                                  <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                                    <Typography variant="overline" sx={{ color: FAINT, fontSize: 8.5,
                                      fontWeight: 750, letterSpacing: 1.25 }}>Triage</Typography>
                                    <Chip size="small" label={sourceRoute.Decision}
                                      sx={{ height: 17, fontSize: 9.5, fontWeight: 700, bgcolor: "#e4e9ee", color: "#41525f" }} />
                                  </Box>
                                  {sourceRoute.Reason && <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55 }}>
                                    {sourceRoute.Reason}</Typography>}
                                </Box>
                              </Box>
                            )}
                            <Box sx={{ p: 1.1, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1.1, alignItems: "center" }}>
                              <DoneAllIcon sx={{ fontSize: 16, color: "#55697a" }} />
                              <Typography variant="caption" sx={{ color: FAINT }}>
                                {detail.ref} · from {t.Source || "manual"} · created {timeAgo(t.CreatedAt)} by {t.CreatedBy}
                                {detail.comments?.length ? ` · ${detail.comments.length} note${detail.comments.length === 1 ? "" : "s"}` : ""}
                              </Typography>
                            </Box>
                          </Box>
                        )}
                    </Box>
                    {/* 3 - WHAT THE TASK IS. Settings, not actions: pills on the bottom edge, and the
                        repo is one of them now instead of an item in a menu. */}
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.7, flexWrap: "wrap",
                      mt: 1.4, pt: 1.2, borderTop: `1px solid ${BORDER}` }}>
                      {!["done", "dropped"].includes(t.Status) && <>
                        <Select value={t.Kind || "task"} onChange={(e) => patch({ Kind: e.target.value })} sx={chipSel}
                          renderValue={kindLabel} title="What kind of work this task contains">
                          {(KINDS.includes(t.Kind || "task") ? KIND_OPTIONS
                            : [{ key: t.Kind, label: t.Kind, hint: "legacy task type" }, ...KIND_OPTIONS]).map((o) =>
                            <MenuItem key={o.key} value={o.key} sx={{ py: 0.6 }}>
                              <ListItemText primary={o.label} secondary={o.hint}
                                primaryTypographyProps={{ fontSize: 12 }} secondaryTypographyProps={{ fontSize: 10.5 }} />
                            </MenuItem>)}
                        </Select>
                        <Select value={t.Status || "open"} onChange={(e) => patch({ Status: e.target.value })} sx={chipSel}
                          renderValue={statusLabel} title="Task status — independent of its agent and reply">
                          {STATUSES.filter((s) => !["done", "dropped"].includes(s) || s === t.Status)
                            .map((s) => <MenuItem key={s} value={s} sx={{ fontSize: 12 }}>{statusLabel(s)}</MenuItem>)}
                        </Select>
                        <Select value={t.Priority || "normal"} onChange={(e) => patch({ Priority: e.target.value })}
                          sx={chipSel} title="Priority">
                          {PRIORITIES.map((p) => <MenuItem key={p} value={p} sx={{ fontSize: 12 }}>{p}</MenuItem>)}
                        </Select>
                        <Select value={t.Assignee || ""} onChange={(e) => {
                          const assignee = e.target.value, worker = assignedAgent(assignee);
                          patch({ Assignee: assignee });
                          if (worker && agents.includes(worker)) setRun((r) => ({ ...r, agent: worker, model: "" }));
                        }} sx={chipSel} title="Who works it" displayEmpty renderValue={assigneeLabel}>
                          <MenuItem value="" sx={{ fontSize: 12 }}>unassigned</MenuItem>
                          <MenuItem value="owner" sx={{ fontSize: 12 }}>you</MenuItem>
                          {agents.map((name) => <MenuItem key={name} value={agentAssignee(name)} sx={{ fontSize: 12 }}>
                            <TaskuaryMark size={12} />&nbsp; {name}
                          </MenuItem>)}
                          {t.Assignee && t.Assignee !== "owner" && !assignedAgent(t.Assignee)
                            && <MenuItem value={t.Assignee} sx={{ fontSize: 12 }}>{t.Assignee}</MenuItem>}
                        </Select>
                        {!isGeneral && <Button size="small" variant="outlined" sx={chipBtn}
                          startIcon={<AccountTreeIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                          title="Which checkout the session works in"
                          onClick={() => setRepoPick(true)}>{repoOf(t) || "pick a repo"}</Button>}
                      </>}
                      {/* a finished task still says what it WAS - the settings read as the record,
                          not as controls. Reopen is the only thing you can do to it, and it lives
                          in the action row above with everything else you can do. */}
                      {["done", "dropped"].includes(t.Status) && (
                        <Typography variant="caption" sx={{ color: FAINT }}>{foldedFacts}</Typography>
                      )}
                      <Box sx={{ flex: 1, minWidth: 12 }} />
                      <Typography variant="caption" sx={{ color: FAINT, textAlign: "right", maxWidth: 340 }}>
                        {completionIsManual
                          ? "You control completion. Ending an agent run or sending a reply leaves this task open."
                          : "Automatic task. When its triaged work finishes, Taskuary may close it and prepare the reply."}
                      </Typography>
                    </Box>
                    </>}
                  </Box>
                )}
                {/* ONE SHORT LINE, LIVE OR NOT. A running session has always been a single strip -
                    heading, chip, controls - while the stopped card answered with a heading, a
                    sentence under it, and a row of buttons under that: three lines for the same
                    question (the owner, 2026-09-17: "can we also keep the agent header simple and
                    short like it is when coder is active"). The bar rides IN the heading now, so
                    the sentence and the row that held it both go. */}
                <Box sx={{ ...card, mb: liveSession ? 0.55 : 1.25,
                  px: liveSession ? 1 : 1.5, py: liveSession ? 0.55 : stage === "agent" ? (agentBar ? 0.8 : 1.5) : 1.1,
                  bgcolor: "#fff", flexShrink: 0, borderLeft: "4px solid #6f8a6e",
                  display: liveSession ? "flex" : "block", alignItems: "center",
                  gap: liveSession ? 1 : 0, flexWrap: "wrap" }}>
                  <Box sx={{ minWidth: 0, flex: liveSession ? "0 1 auto" : "initial" }}>
                    {/* the agent by NAME, not by which binary is running: "Agent running · Claude Code
                        · coder (your CLI)" named a product and a profile (the owner, 2026-09-08) */}
                    {/* A LIVE SESSION IS NOT A WORKING ONE. This asked only whether a pty existed,
                        so the heading read "coder is working" directly above its own chip saying
                        "agent · needs you" - on a coder that had been parked on a question for an
                        hour (the owner, 2026-09-11, TQ-0499). agentState is the session's own word
                        (taskLifecycle.agentPhase); the heading now says what the chip says. */}
                    <WorkflowHeading number="2" title={!term?.alive ? "Agent work"
                      : agentState === "needs you" ? `${agentName(t)} needs you`
                        : `${agentName(t)} is working`}
                    chip={<LifecycleChip kind="agent" phase={agentState} compact />} tone="#6f8a6e" {...stageProps("agent")}
                    /* folded, this heading carried NOTHING - it passed no action at all, so the one
                       card that can actually be picked back up was the one row you could not act on.
                       It gets the move that matches its state, the way the Task strip does. */
                    action={stage === "agent" && agentBar ? agentBarRow :
                      stage !== "agent" && !term?.alive && !["done", "dropped"].includes(t.Status)
                      ? <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.35 }}>
                          {detail?.resumable ? (
                            <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                              sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                              startIcon={startingAgent === "resume" ? <CircularProgress size={11} /> : <HistoryIcon sx={{ fontSize: 14 }} />}
                              title={`Reopens ${detail.resumable.agent}'s own session in ${detail.resumable.cwd}.`}
                              onClick={continueSession}>Continue this session</Button>
                          ) : (
                            <Button size="small" variant="contained" disableElevation
                              sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                              startIcon={<TerminalIcon sx={{ fontSize: 14 }} />}
                              title="Opens the agent step so you can choose a harness, a model and a prompt."
                              onClick={() => setOpenStage("agent")}>
                              {report || detail?.transcript ? "Run another agent" : "Start an agent"}</Button>
                          )}
                          {report && <Tooltip title="Send this result to someone">
                            <IconButton size="small" sx={{ color: "#55697a" }} onClick={() => setHandoff(true)}>
                              <ForwardToInboxIcon sx={{ fontSize: 15 }} /></IconButton>
                          </Tooltip>}
                        </Box>
                      : null} />
                  </Box>
                  {stage === "agent" && <>
                  {term?.alive && (
                    // on a phone the two buttons take their own row: sharing one with the heading, they
                    // stacked over the "agent · needs you" chip (2026-09-20)
                    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end",
                      gap: 0.35, flexWrap: "wrap", flex: { xs: "1 0 100%", sm: 1 }, minWidth: 0, mt: liveSession ? { xs: 0.5, sm: 0 } : 1 }}>
                      {/* A LIVE SESSION HAS NO PRIMARY. "Answer agent" / "Give new prompt" opened a
                          Dialog whose whole body was the SAME TellAgent that is already inline under
                          the terminal - a modal copy of a control on the page (the owner, 2026-09-16:
                          "answer agent really does nothing, it's just type into the prompt window").
                          While an agent is working the next move is typing, so nothing here is filled;
                          the notification stays on the chip and beside the waiting room. */}
                      {liveCodingSession && <Button size="small" variant="outlined" sx={liveCtl} startIcon={<DifferenceIcon sx={{ fontSize: 13 }} />}
                        title="A viewer of the agent's diff. Nothing is approved or committed here."
                        onClick={() => setDiffOpen(true)}>Review changes</Button>}
                      {/* ONE ENDING. Three buttons all ended the session and differed only in what they
                          wrote down - a result, a handover note, or nothing - and the labels buried the
                          half they shared (the owner, 2026-09-16: "save result vs end session vs stop
                          session???"). It writes the session up either way now: on a run that finished
                          that is its result, and on one that did not it is where it got to, which is
                          what the handover note was for.
                          Task completion stays separate (PW-217/218): this ends the AGENT. */}
                      <Button size="small" variant="outlined" sx={liveCtl} disabled={!!wrapping} startIcon={<DoneAllIcon sx={{ fontSize: 13 }} />}
                        title="Writes up what this session did and ends it. The task stays open: Mark task done completes it and drafts the reply."
                        onClick={wrapUp}>Save and end session</Button>

                    </Box>
                  )}
                  {report && !wrapped && !sessionView && (
                    <Box sx={{ mt: 1.1, pt: 1.1, borderTop: `1px solid ${BORDER}` }}>
                      <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.35,
                        fontSize: 9, fontWeight: 750 }}>Latest saved result</Typography>
                      <Box sx={{ mt: 0.35, bgcolor: PANEL2, border: `1px solid ${BORDER}`,
                        borderRadius: 1.5, overflow: "hidden" }}>
                        <CoderReport body={report.Body} artifacts={detail?.artifacts || []} />
                      </Box>
                      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                        Finished by {report.Actor || "the coding agent"}{report.CreatedAt ? ` · ${fmtDateTime(report.CreatedAt)}` : ""}
                      </Typography>
                      {diffRun && <Box sx={{ mt: 0.75 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                    </Box>
                  )}
                  {!term?.alive && !isGeneral && (restartOpen || (!report && !detail?.transcript)) && (
                    <Box sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      <Typography sx={{ color: INK, fontSize: 12.5, fontWeight: 700, mb: 0.75 }}>
                        {report || detail?.transcript ? "Configure the next run" : "Start an agent"}
                      </Typography>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
                        {/* coding asks ONE question (which CLI); a hand-off asks three - which profile,
                            which brain, which model - and all three reach the session. */}
                        <AgentPicker agents={agents} models={models} kinds={kinds} coding={!handOff}
                          agent={run.agent} model={run.model}
                          brains={brainList} brainModels={brainModels} brain={run.brain || ""}
                          generalBrains={generalBrains} pick={run.pick || ""}
                          onPick={(p) => setRun({ ...run, pick: p })}
                          onBrain={(b) => setRun({ ...run, brain: b, model: "" })}
                          onAgent={(a) => setRun({ ...run, agent: a, model: "" })}
                          onModel={(m) => setRun({ ...run, model: m })} size={28} />
                        <Typography variant="caption" sx={{ color: FAINT }}>
                          This run receives the task, messages, attachments, and the latest saved result.
                        </Typography>
                      </Box>
                      <TextField fullWidth multiline minRows={2} maxRows={5} size="small" value={run.instruction}
                        onChange={(e) => setRun({ ...run, instruction: e.target.value })}
                        placeholder={detail?.transcript ? "What should this new agent do next?" : "Extra instructions for this session (optional)"}
                        sx={{ mt: 0.85, bgcolor: "#fff" }} />
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>
                        {!handOff && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                          startIcon={startingAgent === "coding" ? <CircularProgress size={11} /> : <TerminalIcon sx={{ fontSize: 14 }} />}
                          onClick={startCodingAgent}>
                          {startingAgent === "coding" ? "Starting…" : detail?.transcript ? "Start new coding session" : "Start coding session"}
                        </Button>}
                        {detail?.transcript && !report && !handOff && <Button size="small" variant="outlined" disabled={!!wrapping}
                          title="Saves the stopped session's result and report. The task stays open."
                          startIcon={<DoneAllIcon sx={{ fontSize: 15 }} />} onClick={wrapUp}>Save stopped run result</Button>}
                        {/* it SWITCHES the row rather than dispatching on the spot: the pickers above
                            become the profile, brain and model, and the next press starts it */}
                        {!handOff && <Button size="small" variant="outlined" disabled={!!startingAgent}
                          startIcon={<TaskuaryMark size={13} />}
                          onClick={() => setHandOff(true)}>Use non-coding agent</Button>}
                        {handOff && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                          startIcon={startingAgent === "general" ? <CircularProgress size={11} /> : <TaskuaryMark size={13} />}
                          onClick={startGeneralAgent}>
                          {startingAgent === "general" ? "Starting…" : "Send to non-coding agent"}
                        </Button>}
                        {handOff && <Button size="small" variant="text" disabled={!!startingAgent}
                          onClick={() => { setHandOff(false); setRun({ ...run, agent: "", pick: "", model: "" }); }}>Back to coding</Button>}
                        {(report || detail?.transcript) && <Button size="small" variant="text"
                          onClick={() => setRestartOpen(false)}>Cancel</Button>}
                        {repoOf(t) && <Typography variant="caption" sx={{ ...mono, color: FAINT }}>repo · {repoOf(t)}</Typography>}
                      </Box>
                    </Box>
                  )}
                  {isGeneral && !generalStarted && (
                    <Box sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      {/* the same three answers the hand-off asks - this door had none at all */}
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mb: 1 }}>
                        <AgentPicker agents={agents} models={models} kinds={kinds} agent={run.agent} model={run.model}
                          generalBrains={generalBrains} pick={run.pick || ""}
                          onPick={(p) => setRun({ ...run, pick: p })}
                          onAgent={(a) => setRun({ ...run, agent: a, model: "" })}
                          onModel={(m) => setRun({ ...run, model: m })} size={28} />
                      </Box>
                      <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                        startIcon={startingAgent === "general" ? <CircularProgress size={11} /> : <TaskuaryMark size={13} />}
                        onClick={startGeneralAgent}>
                        {startingAgent === "general" ? "Starting…" : "Send to agent"}
                      </Button>
                      <Typography variant="caption" sx={{ color: FAINT, ml: 1 }}>
                        Starts the regular assistant with this task and its messages.
                      </Typography>
                    </Box>
                  )}
                  {/* folded onto the live bar these facts share a ROW with the controls, where a
                      rule above them is stray chrome - they get a rule beside them instead, so the
                      pills you press and the pills you read are two groups and not five in a line */}
                  {(term?.alive || report || detail?.transcript) && !restartOpen && (runRole || brainPill || repoOf(t)) && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.7, flexWrap: "wrap",
                      ...(liveSession
                        ? { ml: 0.9, pl: 1.1, borderLeft: `1px solid ${BORDER}`, flexShrink: 0 }
                        : { mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }) }}>
                      {runRole && <Box sx={{ ...chipBtnStatic }} title="The role: which document this worker follows. Every coding task's role is `coder`.">
                        <Box component="span" sx={{ color: FAINT, fontWeight: 600 }}>role</Box>&nbsp;{runRole}</Box>}
                      {brainPill && <Box sx={{ ...chipBtnStatic }}
                        title={brainPill === detail?.ranOn?.brain
                          ? `What ran this session${detail.ranOn.model ? `, on ${detail.ranOn.model}` : ""}. A brain is chosen on Settings → Triage & agents, or by this role's override — not per task.`
                          : "The brain: which CLI or API connector actually runs it. Chosen on Settings → Triage & agents, or by this role's override — not per task."}>
                        <Box component="span" sx={{ color: FAINT, fontWeight: 600 }}>brain</Box>&nbsp;{brainPill}</Box>}
                      {!isGeneral && <Button size="small" variant="outlined" sx={chipBtn}
                        startIcon={<AccountTreeIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                        title="Which checkout the session works in"
                        onClick={() => setRepoPick(true)}>{repoOf(t) || "pick a repo"}</Button>}
                    </Box>
                  )}
                  </>}
                </Box>
                {repoPick && (
                  <Box sx={{ ...card, mb: 1, bgcolor: PANEL2 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      <AccountTreeIcon sx={{ fontSize: 16, color: "#55697a" }} />
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13, flex: 1 }}>
                        Which repository is this about?
                      </Typography>
                      <IconButton size="small" onClick={() => { setRepoPick(false); setResumeAfterRepo(null); }}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
                    </Box>
                    <RepoPicker taskId={selected} agent={term?.agent || run.agent || "coder"}
                      hasSession={!!term?.alive}
                      onDone={(data) => {
                        loadDetail(selected); loadTasks(); findTerm(selected);
                        if (resumeAfterRepo && data?.repo) {
                          const launch = resumeAfterRepo;
                          setResumeAfterRepo(null); setRepoPick(false);
                          // the start that asked the question is the start that resumes: the Start
                          // button's own road (operations) or the terminal it was opening
                          if (launch.dispatch) startCodingAgent();
                          else openTerm({ ...launch, repo: data.repo, cwd: null });
                        }
                      }} />
                  </Box>
                )}
                {workspaceMode === "general" ? (
                  /* the chat is this task's session: it gets the room a terminal gets, not the
                     height of its own content squeezed between the cards above and below it */
                  <Box sx={{ flex: "1 1 0", minHeight: { xs: 360, md: 420 },
                    display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                    <React.Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
                      <GeneralWorkspace key={`${t.TaskId}-${generalRevision}`} task={t} compact onSession={generalSession} onOpenReports={onGoReports} />
                    </React.Suspense>
                  </Box>
                ) : workspaceMode === "wrapping" ? (
                  <Box sx={{ ...card, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <CircularProgress size={15} />
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5 }}>
                        {wrapping === "stop" ? "Stopping this session…" : "Writing up this session…"}
                      </Typography>
                    </Box>
                    <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>
                      {wrapping === "stop" ? "The session is ending. The task and reply are not changed."
                        : "Reading the transcript and writing up what this session did. The task and reply remain separate — this takes a few seconds."}
                    </Typography>
                    <LinearProgress sx={{ mt: 1, borderRadius: 1, height: 3 }} />
                  </Box>
                ) : workspaceMode === "wrapped" ? (
                  <Box sx={{ ...card, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      <DoneAllIcon sx={{ fontSize: 17, color: "#47654a" }} />
                      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5, flex: 1 }}>
                        Session closed — here is what it did
                      </Typography>
                      <Button size="small" sx={{ fontSize: 11 }} onClick={() => setWrapped(null)}>dismiss</Button>
                    </Box>
                    <CoderReport body={wrapped.report} artifacts={wrapped.artifacts || []} />
                    <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 1 }}>
                      The session ended and its write-up was saved. The task stays open until you mark it done;
                      reply separately if someone is waiting. Start another session and the agent is handed this,
                      so it carries on instead of starting over.
                    </Typography>
                    {/* the card used to name Review without offering a way to get there */}
                    {wrapped.drafting && (
                      <Button size="small" variant="contained" disableElevation sx={{ mt: 1 }}
                        startIcon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                        onClick={() => setOpenStage("reply")}>Read the draft</Button>
                    )}
                  </Box>
                ) : workspaceMode === "live" && peek ? (
                  /* the session, folded to one line while the task behind it is being read */
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.8, borderRadius: 1.5,
                    border: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: 99, bgcolor: "#6f8a6e", flexShrink: 0 }} />
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 0, color: INK, fontSize: 12.5 }} noWrap>
                      {agentState === "needs you" ? says(subState(term), agentName(t)) : `${agentName(t)} is working`} in its session — it keeps running while you read the task.
                    </Typography>
                    <Button size="small" variant="contained" disableElevation sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                      onClick={() => setPeek(false)}>Back to the session</Button>
                  </Box>
                ) : workspaceMode === "live" ? (
                  <>
                    {/* said and did, above the session: the agent's own list beside the files it wrote */}
                    <WorkStrip taskId={selected} live={!!term.alive} session={term} defaultCollapsed={!!term.alive}
                      provenance={{ from: t.Source || "task", kind: t.Kind, by: term.cli || term.agent }} />
                    {!term.alive && <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
                      <Typography variant="caption" sx={{ ...mono, color: FAINT, flex: 1, minWidth: 0 }} noWrap>
                        {term.cmd} · {term.cwd}
                      </Typography>
                      <Chip size="small" label="exited — its output is still here"
                        sx={{ height: 18, fontSize: 10, bgcolor: PANEL2, border: `1px solid ${BORDER}`, color: DIM }} />
                    </Box>}
                    {/* A live coding session is the primary workspace, not a preview squeezed by
                        the report and history below it. Give it a terminal-sized viewport and let
                        the surrounding task page scroll to the evidence after the session. */}
                    {/* it takes what is left between the strip above and the waiting room below, and
                        never less than a readable terminal - a fixed 64vh pushed the waiting room under
                        the fold the moment the strip above it had anything to say */}
                    <Box sx={{ flex: "1 1 0", minHeight: { xs: 360, md: 0 },
                      display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                      <TerminalPane sid={term.sid} height="100%" onExit={() => findTerm(selected)} />
                    </Box>
                    {/* the waiting room, right under the session it feeds: type here instead of into the
                        terminal, and it goes in when the agent stops rather than on top of its work */}
                    {/* the waiting room IS the answer box: when the agent is parked on a question,
                        waitroom.deliver() types what you write straight in rather than queueing it */}
                    {term.alive && <Box sx={{ mt: 0.75, flexShrink: 0, display: "flex", alignItems: "center", gap: 0.9 }}>
                      <Box sx={{ flex: 1, minWidth: 0, ...(agentWaiting ? { "& .MuiOutlinedInput-notchedOutline": { borderColor: "#dfc7cc" } } : {}) }}>
                        <TellAgent taskId={selected} taskRef={detail?.ref} compact onQueued={() => loadDetail(selected)} />
                      </Box>
                      {!!waitingN && <Typography variant="caption" sx={{ color: FAINT, flexShrink: 0 }}>{waitingN} queued</Typography>}
                    </Box>}
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mt: 0.5 }}>
                        Closing the session and writing up what is on screen — the agent is not asked anything.
                      </Typography>
                    )}
                  </>
                ) : null}

                {!sessionView && <Box sx={{ ...card, mt: 1.25, p: stage === "reply" ? 1.5 : 1.1,
                  bgcolor: "#fff", flexShrink: 0,
                  borderLeft: "4px solid #9a7444" }}>
                  <WorkflowHeading number="3" title="Reply"
                    description={term?.alive
                      ? (replyMessage ? "Reply controls return when the agent stops." : "No inbound sender is attached to this task.")
                      : replyMessage
                        ? "What goes back to the sender. Sending and task completion are separate decisions."
                        : "Nobody sent this one, so there is nobody to answer. Work it, or write what you found on the task."}
                    chip={<LifecycleChip kind="reply" phase={replyMessage ? replyState : "not available"} compact />}
                    tone="#9a7444" {...stageProps("reply")}
                    action={stage !== "reply" && replyMessage
                      ? <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.35 }}>
                          <Button size="small" variant="contained" disableElevation disabled={!!openingReply}
                            sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                            startIcon={<ForwardToInboxIcon sx={{ fontSize: 14 }} />}
                            onClick={() => (pendingReview ? setOpenStage("reply") : openReply(true))}>
                            {replyPrimary}</Button>
                          <Tooltip title="Ask sender — a question waits on the task for your approval">
                            <IconButton size="small" sx={{ color: "#9a7444" }} onClick={() => setAskSenderOpen(true)}>
                              <ChatBubbleOutlineIcon sx={{ fontSize: 15 }} /></IconButton>
                          </Tooltip>
                        </Box>
                      : null} />
                  {stage === "reply" && ((pendingReview || proposals.length || replyMessage) ? (
                    <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      {/* the bar comes FIRST, above the letter it acts on. What it no longer holds is
                          that jump to another tab: the draft is right here, and a button whose whole job
                          was sending you to another tab to do this card's own job is gone. */}
                      {replyMessage && (
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
                          {/* ONE button, and it WRITES. "Write reply" opened an empty box and left the
                              model behind a second press ("you should not have to hit draft with AI again
                              to make it go" - the owner, 2026-09-22), and the twin beside it did the thing
                              the first one was named for. The box is still editable, and Redraft below
                              writes it again. */}
                          {!pendingReview && (
                            <Button size="small" variant="contained" disableElevation disabled={!!openingReply}
                              sx={primaryBtn}
                              startIcon={openingReply ? <CircularProgress size={12} /> : <ForwardToInboxIcon sx={{ fontSize: 16 }} />}
                              title="Drafts the reply here, from this task's own context. Nothing is sent until you approve it."
                              onClick={() => openReply(true)}>{replyPrimary}</Button>
                          )}
                          <Button size="small" variant="outlined" sx={barBtn}
                            startIcon={<ChatBubbleOutlineIcon sx={{ fontSize: 15, color: "#9a7444" }} />}
                            title="Drafts a question to the sender. It waits here for your approval; nothing is sent now."
                            onClick={() => setAskSenderOpen(true)}>Ask sender</Button>
                          <Box sx={{ flex: 1, minWidth: 12 }} />
                          <Typography variant="caption" sx={{ color: FAINT, textAlign: "right", maxWidth: 320 }}>
                            {/* no More button: with these on the surface there is nothing left to hide */}
                            {pendingReview
                              ? "Nothing is sent until you approve it."
                              : sentReview
                              ? `Sent${sentReview.DecidedAt ? ` · ${fmtDateTime(sentReview.DecidedAt)}` : ""}. ${completionIsManual ? "The task remains under your control." : "The automatic task can now be complete."}`
                              : "A reply is optional. Starting or stopping an agent does not send one."}
                          </Typography>
                        </Box>
                      )}
                      {/* THE DECISION ITSELF, on the task that owns it - the same component the review
                          queue mounts, so two surfaces cannot say different things about one draft. */}
                      {pendingReview ? (
                        <ReviewDecision review={pendingReview}
                          onChanged={() => { loadDetail(selected); onChanged?.(); }} />
                      ) : (
                        <>
                          {/* THE ENVELOPE over what was sent, read from the same Deliver blob
                              (replyDelivery.js). Read-only: this one is history, not a decision. */}
                          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mt: 1.1, minWidth: 0 }}>
                            <Typography sx={{ color: ACCENT2, fontSize: 9.5, fontWeight: 800, letterSpacing: "1.5px", flexShrink: 0 }}>TO</Typography>
                            <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 650 }}>
                              {replyContext(sentReview || sourceMessage)}
                            </Typography>
                          </Box>
                          {replyCc.length > 0 && (
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mt: 0.6, flexWrap: "wrap", minWidth: 0 }}>
                              <Typography sx={{ color: ACCENT2, fontSize: 9.5, fontWeight: 800, letterSpacing: "1.5px", flexShrink: 0 }}>CC</Typography>
                              {replyCc.map((a) => (
                                <Box key={a} sx={{ px: 0.8, py: 0.15, borderRadius: 99, bgcolor: "#eef1ec", border: "1px solid #d9e0d6" }}>
                                  <Typography sx={{ fontSize: 11.5, color: INK }}>{a}</Typography>
                                </Box>
                              ))}
                            </Box>
                          )}
                          {replyFiles.length > 0 && (
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.7, mt: 0.6, flexWrap: "wrap" }}>
                              {replyFiles.map((f) => (
                                <Chip key={f.name} size="small" icon={<AttachFileIcon sx={{ fontSize: 13 }} />}
                                  label={f.size ? `${f.name} · ${sizeText(f.size)}` : f.name}
                                  sx={{ height: 21, fontSize: 10.5, bgcolor: PANEL2, maxWidth: 320 }} />
                              ))}
                            </Box>
                          )}
                          {sentReview?.DraftText && (
                            <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.25,
                              px: 1.1, py: 0.85, mt: 0.9 }}>
                              <Typography variant="overline" sx={{ color: FAINT, fontSize: 8.5,
                                fontWeight: 750, letterSpacing: 1.25 }}>What was sent</Typography>
                              <Typography variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap",
                                overflowWrap: "anywhere", display: "-webkit-box", WebkitLineClamp: 3,
                                WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                {sentReview.DraftText}</Typography>
                            </Box>
                          )}
                        </>
                      )}
                      {/* A PROPOSAL IS THE SAME KIND OF ASK, so it shares this section rather than
                          taking a fourth stage: lanes.json has one `approve` lane for a reply and an
                          action alike, and one lane on the rail is one section on the page. */}
                      {proposals.length > 0 && (
                        <Box sx={{ mt: 1.4, pt: 1.1, borderTop: `1px solid ${BORDER}` }}>
                          <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.25,
                            fontSize: 9, fontWeight: 750, display: "block", mb: 0.5 }}>
                            {proposals.length === 1 ? "Also waiting on you" : `Also waiting on you · ${proposals.length}`}
                          </Typography>
                          {proposals.map((p) => (
                            <ReviewDecision key={p.ReviewId} review={p}
                              onChanged={() => { loadDetail(selected); onChanged?.(); }} />
                          ))}
                        </Box>
                      )}
                    </Box>
                  ) : (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.9 }}>
                      Nothing is waiting on you here, and no inbound sender is attached to this task.
                    </Typography>
                  ))}
                </Box>}

                {!sessionView && <Fold title={`Context & history ·${taskMessages.length} message${taskMessages.length === 1 ? "" : "s"} · ${detail.comments.length} note${detail.comments.length === 1 ? "" : "s"}`}>
                  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.25,
                    fontSize: 9, fontWeight: 750, display: "block", mb: 0.65 }}>Messages</Typography>
                  {taskMessages.map((m) => {
                    const route = detail.routes.find((r) => r.MessageId === m.MessageId);
                    const mine = m.Status === "context" || m.Direction === "out";
                    return (
                      <Box key={m.MessageId} sx={{ display: "flex", justifyContent: mine ? "flex-end" : "flex-start", mb: 0.85 }}>
                      <Box sx={{ width: "fit-content", maxWidth: { xs: "96%", md: "84%" }, p: 1.15,
                        bgcolor: mine ? "#e9e3d8" : "#fff",
                        borderRadius: mine ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                        border: `1px solid ${mine ? "#d8d0c4" : BORDER}`,
                        borderLeft: `3px solid ${mine ? "#8a7a5c" : "#6f8a6e"}` }}>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                          <ChannelIcon channel={m.Channel} sx={{ color: FAINT }} />
                          <Chip size="small" label={m.ReviewSent ? "sent reply" : mine ? "your reply" : "inbound"}
                            sx={{ height: 17, fontSize: 9.5, fontWeight: 700,
                              bgcolor: mine ? "#f1ead9" : "#edf3ea", color: mine ? "#6b5f45" : "#47654a" }} />
                          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{mine ? "you" : m.FromName || m.FromEmail}</Typography>
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
                        <Box sx={{ minWidth: 0, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                          {m.Channel === "report" && looksMd(m.BodyText)
                            ? <Md text={cleanText(m.BodyText)} />
                            : <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere",
                              wordBreak: "break-word", color: DIM, display: "block" }}>{cleanText(m.BodyText)}</Typography>}
                        </Box>
                        {!m.ReviewSent && <Attachments messageId={m.MessageId} canFetch={m.Channel === "email"} dense />}
                      </Box>
                      </Box>
                    );
                  })}
                  {!taskMessages.length && <Typography variant="caption" sx={{ color: FAINT }}>Manually created — no source messages.</Typography>}
                  <Divider sx={{ my: 1.2, borderColor: BORDER }} />
                  <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.25,
                    fontSize: 9, fontWeight: 750, display: "block", mb: 0.35 }}>Notes & activity</Typography>
                  <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", tableLayout: "auto" }}>
                    <tbody>{detail.comments.map((c) => <CommentRow key={c.CommentId} c={c} />)}</tbody>
                  </Box>
                  {!detail.comments.length && <Typography variant="caption" sx={{ color: FAINT }}>No notes yet.</Typography>}
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                    <TextField fullWidth placeholder="Add a note (humans only)" value={comment}
                      onChange={(e) => setComment(e.target.value)} onKeyDown={(e) => e.key === "Enter" && post()} />
                    <Button size="small" onClick={post}>Post</Button>
                  </Box>
                </Fold>}

                {/* runs from before sessions (and any API-driven run) keep their trace here */}
                {!sessionView && detail.runs.length > 0 && (
                  <Fold title={`Earlier runs · ${detail.runs.length}`}>
                    {detail.runs.map((r) => (
                      <Box key={r.RunId} sx={{ mb: 0.75, p: 1, bgcolor: r.Status === "running" ? "#dfeade" : PANEL2, borderRadius: 1.5, border: `1px solid ${BORDER}` }}>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                          <TaskuaryMark size={13} />
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
          {detail?.ref} · {diff?.scope === "pr" ? `the pull request's own diff — ${diff.pr?.repo}#${diff.pr?.number}, what is being reviewed`
            : diffScope === "task" ? "what this task's agent changed" : "everything a push would carry, whoever wrote it"}
          {/* an agent told to "commit locally and stop" leaves a CLEAN tree - saying only
              "uncommitted work" over a finished job read as "it did nothing" */}
          {diffScope === "task" && diff?.commits?.length ? ` — ${diff.commits.length} commit${diff.commits.length === 1 ? "" : "s"} of its own, unpushed` : ""}
          {diffScope === "checkout" && diff?.ahead ? ` — ${diff.ahead} commit${diff.ahead === 1 ? "" : "s"} ahead of ${diff.upstream}, plus anything uncommitted`
                       : diffScope === "checkout" && diff?.upstream ? ` — measured against ${diff.upstream}` : ""}
          {/* a shared checkout carries other tasks' work; the old drawer showed all of it as this
              task's - a database-only task wore two other agents' commits. The whole view is one
              click away, and says whose it is. */}
          <Box component="span" onClick={() => { const next = diffScope === "task" ? "checkout" : "task"; setDiffScope(next);
              api.get(`/api/tasks/${selected}/diff`, { params: { scope: next } }).then((r) => setDiff(r.data)).catch(() => {}); }}
            sx={{ ml: 1, color: "#55697a", cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
            {diff?.scope === "pr" ? "show the agent's checkout instead" : diffScope === "task" ? `show the whole checkout${diff?.checkout_files ? ` (${diff.checkout_files} file${diff.checkout_files === 1 ? "" : "s"})` : ""}` : (diff?.pr ? "back to the pull request's diff" : "back to this task's changes")}
          </Box>
        </Typography>
        {!diff ? <CircularProgress size={20} sx={{ m: 2 }} />
          : diff.why ? <Empty>{diff.why}</Empty>
            : diff.note && !diff.files?.length ? <Empty>{diff.note}</Empty>
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
      <Dialog open={askSenderOpen} onClose={() => !askingSender && setAskSenderOpen(false)} fullWidth maxWidth="sm"
        PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle>Ask the sender · {detail?.ref}</DialogTitle>
        <DialogContent sx={{ pt: "8px !important" }}>
          <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
            Write the one fact the agent or task needs. This becomes a clarification draft on the task; it is not sent until you approve it.
            The task stays open while you wait for the sender's answer.
          </Typography>
          <TextField autoFocus fullWidth multiline minRows={3} label="Question for the sender"
            value={senderQuestion} onChange={(e) => setSenderQuestion(e.target.value)}
            placeholder="Which distribution spreadsheet and which dashboard should I use?" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAskSenderOpen(false)} disabled={askingSender}>Cancel</Button>
          <Button variant="contained" disableElevation onClick={askSender}
            disabled={askingSender || !senderQuestion.trim()}>
            {askingSender ? <CircularProgress size={15} /> : "Put it on the task"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={mineOpen} onClose={() => !savingMine && setMineOpen(false)} fullWidth maxWidth="sm"
        PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle>Yours, not the agent's · {detail?.ref}</DialogTitle>
        <DialogContent sx={{ pt: "8px !important" }}>
          <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
            The task stays and goes on your list; any agent working it stops. Triage learns from this,
            so the next message like it is judged better.
          </Typography>
          <TextField autoFocus fullWidth label="Where does this work actually live? (optional)"
            value={belongsTo} onChange={(e) => setBelongsTo(e.target.value)}
            placeholder="ADP" helperText="Name the system that really holds it. This is the part triage cannot work out on its own — it only knows the repositories it has the code for." />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMineOpen(false)} disabled={savingMine}>Cancel</Button>
          <Button variant="contained" disableElevation onClick={takeItMyself} disabled={savingMine}>
            {savingMine ? <CircularProgress size={15} /> : "Put it on my list"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={newOpen} onClose={() => setNewOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New task</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: "8px !important" }}>
          <TextField label="Title" value={nt.Title} onChange={(e) => setNt({ ...nt, Title: e.target.value })} autoFocus />
          <TextField label="Summary" value={nt.Summary} multiline minRows={2} onChange={(e) => setNt({ ...nt, Summary: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Select fullWidth value={nt.Kind} renderValue={kindLabel} onChange={(e) => setNt({ ...nt, Kind: e.target.value })}>
              {KIND_OPTIONS.map((o) => <MenuItem key={o.key} value={o.key} sx={{ py: 0.7 }}>
                <ListItemText primary={o.label} secondary={o.hint}
                  primaryTypographyProps={{ fontSize: 13 }} secondaryTypographyProps={{ fontSize: 10.5 }} />
              </MenuItem>)}
            </Select>
            <Select fullWidth value={nt.Priority} onChange={(e) => setNt({ ...nt, Priority: e.target.value })}>
              {PRIORITIES.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
            </Select>
          </Box>
          {nt.Kind === "coding" && !!repos.length && (
            <Box>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
                Repository — the agent works in this checkout
              </Typography>
              <Select fullWidth size="small" value={nt.repo || ""} displayEmpty
                onChange={(e) => setNt({ ...nt, repo: e.target.value })}>
                {/* empty is not "none": it is "you decide", which is guess_repo reading the ask
                    against SOUL.md's repo map - the behaviour this box used to have unavoidably */}
                <MenuItem value="" sx={{ fontSize: 12.5 }}>Let Taskuary pick from what I wrote</MenuItem>
                {repos.map((r) => <MenuItem key={r} value={r} sx={{ fontSize: 12.5 }}>{r}</MenuItem>)}
              </Select>
            </Box>
          )}
          <Typography variant="caption" sx={{ color: DIM }}>
            To do stays on your list. General / non-coding opens the visual assistant. Coding opens the agent's repository terminal. Reply creates a draft on the task.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!nt.Title.trim()} onClick={create}>Create</Button>
        </DialogActions>
      </Dialog>
      <ConfirmDelete open={confirmNAT} what={t ? `"${(t.Title || "this task").slice(0, 60)}"` : "this task"}
        consequence={"It is deleted, and triage is taught that this topic is never a task. Its messages stay on the Timeline, "
          + "and the sender is not muted — that is \"Skip this sender\"."}
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
  <Box component="details" sx={{ mt: 1 }}>
    <Box component="summary" sx={{ cursor: "pointer", color: ACCENT2, fontSize: 10.5, letterSpacing: 1.5,
      textTransform: "uppercase", fontWeight: 700, py: 0.6, "&:hover": { color: INK } }}>{title}</Box>
    <Box sx={{ mt: 0.5 }}>{children}</Box>
  </Box>
);

// ONE ROW ON A DESKTOP, TWO ON A PHONE. The bar is flexShrink: 0 so it never loses a button, which
// at 390px meant it kept its width by sitting ON the title ("A… w…" under Continue this session,
// Save this c… cut off at the card's edge, 2026-09-18). Below sm the bar takes the whole next line.
const WorkflowHeading = ({ number, title, description, chip, tone, folded, onToggle, action }) => (
  <Box onClick={onToggle} sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: { xs: "wrap", sm: "nowrap" },
    cursor: onToggle ? "pointer" : "default", opacity: folded ? 0.72 : 1,
    "&:hover": onToggle ? { opacity: 1 } : undefined }}>
    <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: tone, color: "#fff",
      display: "grid", placeItems: "center", flexShrink: 0, fontSize: 11.5, fontWeight: 800 }}>
      {number}
    </Box>
    <Box sx={{ minWidth: 0, flex: 1 }}>
      <Typography sx={{ color: INK, fontSize: 13.5, fontWeight: 750, lineHeight: 1.25 }}>{title}</Typography>
      {description && !folded && <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.35 }}>{description}</Typography>}
    </Box>
    {/* the one action a stage cannot afford to hide when it folds. Its click is its own, not the fold's. */}
    {action && <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", flexShrink: 0, flexBasis: { xs: "100%", sm: "auto" }, order: { xs: 9, sm: 0 } }}>{action}</Box>}
    {chip}
    {onToggle && <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0,
      transform: folded ? "rotate(-90deg)" : "none", transition: "transform .15s" }} />}
  </Box>
);

