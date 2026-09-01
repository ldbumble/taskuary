// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress,
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
import { taskMatchesQuery } from "./taskSearch.js";
import { filterForSelectedState } from "./taskFilter.js";
import { pollWhileActive, pollWhileVisible } from "./visible.js";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, hoverable, mono, selSx, ACCENT2, PILL_COLORS } from "./theme.jsx";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { RepoPicker } from "./RepoPicker.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon, StateChip, stateOf, TASK_STATES, asUtc, AgentPicker, useAgents, RunTrace, DiffBlock, DiffFiles, CoderReport, timeAgo, fmtDateTime, cleanText, Empty, FilterPills, ConfirmDelete, TellAgent, WorkStrip, WorkLine, isWaiting, TaskuaryMark } from "./ui.jsx";
import { Md, looksMd } from "./md.jsx";
import TerminalIcon from "@mui/icons-material/Terminal";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import PauseCircleIcon from "@mui/icons-material/PauseCircleOutline";
import ForwardToInboxIcon from "@mui/icons-material/ForwardToInbox";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import { Divider, ListItemIcon, ListItemText, Menu } from "@mui/material";
import { TerminalPane } from "./TerminalView.jsx";

// An open tab can still hold yesterday's entry bundle after a local upgrade. Vite names lazy
// chunks by content, so that tab asks the new server for a filename the build no longer has.
// Recover once automatically; a real module error still reaches the view boundary on retry.
const GENERAL_CHUNK_RELOAD = "tq-general-chunk-reload";
import { autostartPlan, isGeneralKind } from "./autostart.js";
import { ASK_TAG } from "./newTask.js";
import { continueCoding } from "./continueCoding.js";

const loadGeneralWorkspace = () => import("./GeneralWorkspace.jsx").then((module) => {
  try { sessionStorage.removeItem(GENERAL_CHUNK_RELOAD); } catch { /* storage disabled */ }
  return module;
}).catch((error) => {
  const stale = /dynamically imported module|importing a module script failed|failed to fetch/i.test(String(error?.message || error));
  let retried = false;
  try { retried = sessionStorage.getItem(GENERAL_CHUNK_RELOAD) === "1"; } catch { /* storage disabled */ }
  if (stale && !retried) {
    try { sessionStorage.setItem(GENERAL_CHUNK_RELOAD, "1"); } catch { /* storage disabled */ }
    window.location.reload();
    return new Promise(() => {});
  }
  throw error;
});
const GeneralWorkspace = React.lazy(loadGeneralWorkspace);

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;

const STATUSES = ["open", "in_progress", "waiting", "done", "dropped"];
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
// gets the responder and the Review queue, general gets the visual conversation. Keep the
// explicit non-coding label: calling this only "assistant" hid the option the owner asked for.
const KIND_OPTIONS = [
  { key: "general", label: "general / non-coding", hint: "research, writing, analysis, planning, and other assistant work" },
  { key: "coding", label: "coding", hint: "the configured CLI in a repository terminal" },
  { key: "reply", label: "reply", hint: "draft an answer for approval in Review" },
];
const KINDS = KIND_OPTIONS.map((o) => o.key);
const kindLabel = (kind) => KIND_OPTIONS.find((o) => o.key === kind)?.label || kind;

export default function TasksView({ selected, onSelect, onChanged, autostart, onAutostarted, onGoReview, onGoReports, active = true }) {
  const [tasks, setTasks] = useState(null);
  // "live" on arrival: what is still on somebody's plate is what you came here for. "all"
  // opens on a list whose top is whatever finished most recently. ("" = all; the rest derive.)
  const [filter, setFilter] = useState("live");
  const [query, setQuery] = useState("");
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
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => setRepos(
      (data.data || []).filter((x) => x.Channel === "github" && x.Active).map((x) => x.Address)
    )).catch(() => {});
  }, []);
  // A refresh already in flight when the tab is left can finish after the refresh
  // fired on return. Only the newest request is allowed to repaint the list.
  const taskLoadSeq = useRef(0);
  const stale = (id) => selRef.current !== id;
  const { agents, models } = useAgents();
  const [err, setErr] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [nt, setNt] = useState({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
  const [run, setRun] = useState({ agent: "", model: "", instruction: "" });   // "" = the roster's default (served first)
  const [continueOpen, setContinueOpen] = useState(false);
  const [continueText, setContinueText] = useState("");
  const [continuing, setContinuing] = useState(false);
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
  const [feedOpen, setFeedOpen] = useState(false);   // Feed the agent, for THIS task
  const waitingN = (tasks || []).find((x) => x.TaskId === selected)?.Waiting || 0;   // prompts in this task's funnel
  const [diff, setDiff] = useState(null);
  const [diffScope, setDiffScope] = useState("task");   // this task's footprint, or the whole checkout

  // fetch everything once and filter on the derived state - the server only knows raw
  // Status, and the state a person cares about is a combination of three columns
  const loadTasks = useCallback(async () => {
    const seq = ++taskLoadSeq.current;
    try {
      const next = (await api.get("/api/tasks")).data.data || [];
      if (seq === taskLoadSeq.current) setTasks(next);
    } catch (e) {
      if (seq === taskLoadSeq.current) setErr(e?.response?.data?.detail || "Failed to load tasks");
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/api/tasks/${id}`);
      if (stale(id)) return;
      setDetail(data);
      try { const w = (await api.get(`/api/tasks/${id}/waitroom`)).data; if (!stale(id)) setWait(w); }
      catch { if (!stale(id)) setWait({ data: [], state: null }); }
    } catch (e) { if (!stale(id)) setErr(e?.response?.data?.detail || "Failed to load task"); }
  }, []);
  // the tab always lands on what is still in progress - whatever it was left on last time
  useEffect(() => { if (active) { setFilter("live"); setOlder(false); } }, [active]);
  useEffect(() => { setOlder(false); }, [filter]);

  // ...and keep it honest. The list was fetched ONCE, so a task whose agent picked it up
  // kept wearing "needs you" - and the pill counts kept agreeing with it - until something
  // else happened to reload. "Agent working" is a fact with a 45-second shelf life (a live
  // session that goes quiet is waiting on you); a row that states it has to be re-asked.
  // Only while this tab is the one on screen: it stays mounted behind the others.
  useEffect(() => {
    // Refresh now as well as polling: otherwise returning from Board shows the hidden
    // tab's old list for five seconds.
    return pollWhileActive(active, loadTasks, 5000);
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
    if (detail?.session?.alive) sessionSettleUntil.current = Date.now() + 120000;
    const filedReport = (detail?.comments || []).some((c) => /^CODER REPORT(?:\r?\n|$)/.test(String(c.Body || "").trimStart()));
    const settling = detail?.task?.Status === "in_progress" && !!detail?.transcript
      && (filedReport || Date.now() < sessionSettleUntil.current);
    if (!((running || wrapping || settling) && selected)) return undefined;
    return pollWhileVisible(() => loadDetail(selected), 3000);
  }, [detail, selected, loadDetail, wrapping]);

  const patch = async (fields) => { await api.patch(`/api/tasks/${selected}`, fields); loadDetail(selected); loadTasks(); onChanged?.(); };
  const create = async () => {
    // A general task made HERE is the same thing the Board makes: a question with an answer
    // wanted. It gets the same ask tag, so the chat opens with the question already asked
    // instead of with the owner's own words sitting in a box above an empty thread.
    const ask = isGeneralKind(nt.Kind) && String(nt.Summary || "").trim();
    // `repo` is not a task column - it rides as a tag, the same one the Board writes
    const { repo, ...fields } = nt;
    const tags = [repo && nt.Kind === "coding" ? `repo:${repo}` : "", ask ? ASK_TAG : ""].filter(Boolean);
    const { data } = await api.post("/api/tasks", { ...fields, ...(tags.length ? { Tags: tags.join(",") } : {}) });
    setNewOpen(false); setNt({ Title: "", Summary: "", Kind: "general", Priority: "normal" });
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
  // "We're done": nothing is typed at the agent. The session closes, its transcript becomes the
  // report (written by the main AI), the responder drafts the reply out of that report, and the
  // result lands right here under where the terminal was.
  const wrapUp = async () => {
    if (!canWrap) return;
    const id = selected;
    setWrapping("wrap"); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${id}/wrap`, { close: true });
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
  const pause = async () => {
    if (!canWrap) return;
    const id = selected;
    setWrapping("pause"); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${id}/pause`, {});
      loadTasks(); onChanged?.();
      if (stale(id)) return;
      setWrapped({ note: data.note });
      setTerm(null); loadDetail(id);
    } catch (e) { if (!stale(id)) setErr(e?.response?.data?.detail || "Could not pause the session"); }
    if (!stale(id)) setWrapping(false);
  };
  useEffect(() => { setWrapping(false); setWrapped(null); }, [selected]);
  useEffect(() => { setContinueOpen(false); setContinueText(""); setContinuing(false); }, [selected]);

  const [handoff, setHandoff] = useState(false);
  const [reshape, setReshape] = useState(false);
  const [repoPick, setRepoPick] = useState(false);
  const [menuEl, setMenuEl] = useState(null);
  useEffect(() => { setHandoff(false); setReshape(false); setRepoPick(false); setDiffOpen(false); }, [selected]);
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
  const canWrap = !!term || !!detail?.transcript;
  const findTerm = useCallback(async (tid) => {
    if (!tid) { setTerm(null); return; }
    try {
      const rows = (await api.get("/api/terminals")).data.data || [];
      if (stale(tid)) return;
      // an exited session still holds its scrollback (they stay listed ~10 min), and that
      // transcript is exactly what Done and Pause need - dropping it left a task you could
      // not close out because the CLI had finished on its own
      setTerm(rows.find((x) => x.taskId === tid && x.alive) || rows.find((x) => x.taskId === tid) || null);
    } catch { if (!stale(tid)) setTerm(null); }
  }, []);
  useEffect(() => { setTerm(undefined); findTerm(selected); }, [selected, findTerm]);
  const openTerm = useCallback(async (body) => {
    try {
      const { data } = await api.post("/api/terminals", body); setTerm(data);
      // Starting a session reopens a completed task. Refresh both surfaces immediately so the
      // chip and buckets say in progress on the same click that makes the terminal appear.
      loadDetail(body.task_id); loadTasks(); onChanged?.();
    }
    catch (e) {
      const msg = e?.response?.data?.detail || "Could not start a terminal";
      setErr(msg);
      // the repo guard refused (right repo, no local path): the fix IS the picker, so open it
      // here instead of sending the user off to read the error's directions
      if (/no local path/i.test(msg)) setRepoPick(true);
    }
  }, [loadDetail, loadTasks, onChanged]);
  const continueWork = async () => {
    if (!continueText.trim() || !selected || continuing) return;
    const id = selected;
    setContinuing(true); setErr("");
    try {
      const agent = detail?.transcript?.agent || report?.Actor || "coder";
      const { data } = await continueCoding(api, id, continueText.trim(), agent);
      if (stale(id)) return;
      setTerm(data.session); setContinueOpen(false); setContinueText("");
      loadDetail(id); loadTasks(); onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(e?.response?.data?.detail || "Could not continue the coding work");
    } finally {
      if (!stale(id)) setContinuing(false);
    }
  };
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
    openTerm({ agent: autostart.agent || run.agent, model: autostart.model || run.model || null,
      task_id: selected, repo: repoOf(detail.task), seed: true });
  }, [autostart, selected, term, detail, openTerm, onAutostarted, run.agent]);


  // the pane shows the selected task or nothing - never the previous one while this loads
  const t = detail?.task?.TaskId === selected ? detail.task : null;
  const isGeneral = isGeneralKind(t?.Kind);
  const search = query.trim();
  // Search means the whole archive, regardless of the selected state pill or today's cutoff. That
  // is what makes a completed PR/task discoverable instead of merely searching the visible rows.
  const bucket = (tasks || []).filter((x) => search ? taskMatchesQuery(x, search) : (!filter || inBucket(x, filter)));
  const cut = !search && filter !== "live" && !older;
  const shown = cut ? bucket.filter(touchedToday) : bucket;
  const nOlder = bucket.length - shown.length;
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
    if (was.id !== selected || was.key === key) return;   // new selection, or nothing moved
    const next = filterForSelectedState(filter, key);
    if (next !== filter) { setFilter(next); setOlder(false); }
  }, [active, selected, tasks, search, filter]);
  // The desktop page is a master/detail workspace. Opening it with a populated list but no
  // detail selected leaves most of the screen as a dead blank panel and makes the first click
  // compulsory. Follow the visible list to its first task on arrival (and after removing the
  // selected task); an explicitly selected task is never replaced when filters change.
  const firstShownId = shown[0]?.TaskId;
  useEffect(() => {
    if (active && !selected && firstShownId) onSelect(firstShownId);
  }, [active, selected, firstShownId, onSelect]);
  // The report is identified by its durable marker, not the actor label. Named coding agents
  // appear as coder/claude/codex in the record; requiring ActorType === "agent" hid valid results.
  const report = [...(detail?.comments || [])].reverse().find((c) => {
    const body = String(c.Body || "").trimStart();
    return /^CODER REPORT(?:\r?\n|$)/.test(body) && body.replace(/^CODER REPORT/, "").trim();
  });
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const liveRun = (detail?.runs || []).find((r) => r.Status === "running");
  const liveCodingSession = !isGeneral && !!term?.alive;
  const pendingReview = (detail?.reviews || []).find((r) => r.Status === "pending");
  // A completed report is stronger evidence than an old in_progress value. This covers the few
  // seconds while the reply is being drafted, and old rows left behind by that former race.
  const effectiveStatus = t?.Status === "in_progress" && report && !liveCodingSession && !liveRun
    ? (pendingReview ? "waiting" : "done") : t?.Status;
  const displayTask = t ? { ...t, Status: effectiveStatus } : t;
  useEffect(() => { if (!liveCodingSession) setFeedOpen(false); }, [liveCodingSession]);
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
              <FilterPills value={search ? "" : filter} onChange={(next) => { setFilter(next); setQuery(""); }}
                options={STATE_FILTERS.map((f) => ({ ...f,
                  n: !tasks ? null : f.key ? tasks.filter((x) => inBucket(x, f.key)).length : tasks.length }))} />
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
              ? <Empty>{search ? `No tasks match “${search}”.` : "No tasks here."}</Empty> : shown.map((task) => (
              // the selected row is outlined in its STATE's colour - a working task in the same sage as
              // its chip - not in the brand slate, which read as a fourth state nobody could name
              <Box key={task.TaskId} onClick={() => onSelect(task.TaskId)}
                sx={{ px: 1.25, py: 1, mb: 0.75, cursor: "pointer", bgcolor: "#fff", borderRadius: 1.75,
                  border: `1px solid ${selected === task.TaskId ? stateOf(task).c.fg : BORDER}`,
                  boxShadow: selected === task.TaskId ? "0 1px 8px rgba(47,107,79,.14)" : "none",
                  transition: "border-color .12s, box-shadow .12s",
                  "&:hover": { borderColor: selected === task.TaskId ? stateOf(task).c.fg : "#d8cfbe" } }}>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                  <Typography variant="caption" sx={{ ...mono, color: "#55697a", fontWeight: 700 }}>{task.ref}</Typography>
                  <StateChip task={task} />
                  {task.Priority === "urgent" && <Chip size="small" label="urgent" sx={{ bgcolor: PILL_COLORS.red.bg, color: PILL_COLORS.red.fg, height: 17, fontSize: 10 }} />}
                  {String(task.Assignee || "").startsWith("agent:") && <TaskuaryMark size={13} />}
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" sx={{ color: FAINT }}>{timeAgo(task.CreatedAt)}</Typography>
                </Box>
                <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 500, mt: 0.4 }}>{task.Title}</Typography>
                {search && <Typography variant="caption" noWrap sx={{ color: FAINT, display: "block", mt: 0.2 }}>
                  {[task.Source, task.SearchSources, task.Summary].filter(Boolean).join(" · ")}
                </Typography>}
              </Box>
            ))}
            {tasks && nOlder > 0 && (
              <Button size="small" fullWidth onClick={() => setOlder(true)} sx={{ color: DIM, fontSize: 11.5, mt: 0.25 }}>
                {shown.length ? `show ${nOlder} more from before today` : `nothing from today — show ${nOlder} older`}
              </Button>
            )}
          </Box>
        </Box>
      </Box>

      {/* ── detail ────────────────────────────────────────────────────── */}
      <Box sx={{ ...frame, flex: 1, minWidth: 0, height: "calc(100vh - 118px)", minHeight: 420 }}>
        <Box sx={{ ...frameInner, height: "100%", display: "flex", flexDirection: "column" }}>
          {!t ? (selected ? <CircularProgress size={20} sx={{ m: 2 }} /> : <Empty>Select a task to see its full story.</Empty>) : (
            <>
              {/* header strip: identity + controls. Calm on purpose - white ground, one quiet
                  outlined action, ghost icons: the loud green block + boxed dots read as three
                  alarms where nothing was wrong */}
              <Box sx={{ px: 2.5, py: 1.5, bgcolor: "#fff", borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
                {/* one primary action, everything else behind one tidy menu - six buttons in a
                    row read as none of them mattering */}
                <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Typography sx={{ ...mono, color: "#55697a", fontWeight: 700, fontSize: 12.5 }}>{detail.ref}</Typography>
                  <Typography sx={{ color: INK, flex: 1, fontWeight: 650, fontSize: 15,
                    minWidth: { xs: 110, sm: 200 }, letterSpacing: "-.01em" }} noWrap>
                    {t.Title}
                  </Typography>
                  <StateChip task={{ ...displayTask, ReviewStatus: (detail.reviews || [])[0]?.Status,
                    RunStatus: (detail.runs || [])[0]?.Status, Session: detail.session }} />
                  {liveCodingSession && (
                    <Tooltip title="Queue prompts for this task's agent - one or a whole list; they land one per stop, never mid-turn">
                      <Button size="small" variant="contained" disableElevation onClick={() => setFeedOpen(true)}
                        sx={{ bgcolor: "#8a7a5c", "&:hover": { bgcolor: "#6b5f45" }, px: 1.25 }}>
                        ✎ Feed the agent{waitingN > 0 ? ` · ${waitingN} queued` : ""}
                      </Button>
                    </Tooltip>
                  )}
                  {effectiveStatus !== "done" && (
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
                      <ListItemText primary="Not a task" secondary="delete it and teach triage why — the sender keeps writing to you" />
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
                    renderValue={kindLabel}
                    title="Assistant is the visual chat over your configured agent; coding is its repository terminal; reply creates a draft in Review">
                    {(KINDS.includes(t.Kind || "general") ? KIND_OPTIONS
                      : [{ key: t.Kind, label: t.Kind, hint: "legacy task type" }, ...KIND_OPTIONS]).map((o) =>
                      <MenuItem key={o.key} value={o.key} sx={{ py: 0.6 }}>
                        <ListItemText primary={o.label} secondary={o.hint}
                          primaryTypographyProps={{ fontSize: 12 }} secondaryTypographyProps={{ fontSize: 10.5 }} />
                      </MenuItem>)}
                  </Select>
                  <Select value={effectiveStatus} onChange={(e) => patch({ Status: e.target.value })} sx={selSx}
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
              {/* a flex column so the terminal takes exactly what is left between the strip above and the
                  waiting room below - a fixed-height formula clipped its bottom line on shorter screens */}
              <Box sx={{ px: 2, py: 1.5, overflowY: "auto", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
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
                {isGeneral ? (
                  <React.Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
                    <GeneralWorkspace task={t} onSession={generalSession} onOpenReports={onGoReports} />
                  </React.Suspense>
                ) : wrapping && !wrapped ? (
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
                ) : term?.alive ? (
                  <>
                    {/* said and did, above the session: the agent's own list beside the files it wrote */}
                    <WorkStrip taskId={selected} live={!!term.alive} session={term}
                      provenance={{ from: t.Source || "task", kind: t.Kind, by: term.cli || term.agent }} />
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
                      {term.alive && term.work && (
                        <WorkLine work={term.work} who={term.cli || term.agent || term.label} waiting={isWaiting(term)} startedAt={term.started} />
                      )}
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
                    {/* A live coding session is the primary workspace, not a preview squeezed by
                        the report and history below it. Give it a terminal-sized viewport and let
                        the surrounding task page scroll to the evidence after the session. */}
                    <Box sx={{ height: { xs: "56vh", md: "clamp(500px, 64vh, 760px)" },
                      minHeight: { xs: 360, md: 500 }, flexShrink: 0,
                      display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                      <TerminalPane sid={term.sid} height="100%" onExit={() => findTerm(selected)} />
                    </Box>
                    {/* the waiting room, right under the session it feeds: type here instead of into the
                        terminal, and it goes in when the agent stops rather than on top of its work */}
                    {term.alive && <Box sx={{ mt: 0.75, flexShrink: 0 }}><TellAgent taskId={selected} taskRef={detail?.ref} compact onQueued={() => loadDetail(selected)} /></Box>}
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mt: 0.5 }}>
                        {wrapping === "pause" ? "Writing the handover note from what is on screen, then stopping."
                          : "Closing the session and writing up what is on screen — the agent is not asked anything."}
                      </Typography>
                    )}
                  </>
                ) : report ? null : (
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

                {/* The completed outcome is the first permanent record below the session. Lead
                    with Result; determination and actions are evidence, not the punchline. */}
                {report && !wrapped && (
                  <Block title="Agent result">
                    <Box sx={{ bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden" }}>
                      <CoderReport body={report.Body} />
                    </Box>
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                      Finished by {report.Actor || "the coding agent"}{report.CreatedAt ? ` · ${fmtDateTime(report.CreatedAt)}` : ""}
                    </Typography>
                    {diffRun && <Box sx={{ mt: 0.75 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                    {!liveCodingSession && (continueOpen ? (
                      <Box sx={{ mt: 1.25, pt: 1.25, borderTop: `1px solid ${BORDER}` }}>
                        <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 0.65 }}>
                          Tell {detail?.transcript?.agent || report.Actor || "the coder"} what to change next. Taskuary opens a new
                          live terminal in {detail?.transcript?.cwd || "the same repository"} with this saved result and task history.
                        </Typography>
                        <TextField fullWidth multiline minRows={2} maxRows={6} size="small" autoFocus
                          value={continueText} onChange={(e) => setContinueText(e.target.value)}
                          placeholder="What code changes should it make now?"
                          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) continueWork(); }} />
                        <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
                          <Button size="small" variant="contained" disableElevation disabled={!continueText.trim() || continuing}
                            startIcon={continuing ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <TerminalIcon sx={{ fontSize: 15 }} />}
                            onClick={continueWork}>{continuing ? "opening terminal…" : "Continue coding"}</Button>
                          <Button size="small" disabled={continuing} onClick={() => { setContinueOpen(false); setContinueText(""); }}>
                            Cancel
                          </Button>
                        </Box>
                      </Box>
                    ) : (
                      <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
                        <Button size="small" variant="outlined" startIcon={<TerminalIcon sx={{ fontSize: 15 }} />}
                          onClick={() => setContinueOpen(true)}>
                          Continue with {detail?.transcript?.agent || report.Actor || "coder"}
                        </Button>
                        {/* the other thing you want when an agent has finished: TELL SOMEONE. It
                            existed, in the overflow menu, phrased as "not ours to do" - which is
                            a different act from sending on a result you are pleased with. */}
                        <Button size="small" variant="outlined" startIcon={<ForwardToInboxIcon sx={{ fontSize: 15 }} />}
                          onClick={() => setHandoff(true)}>
                          Send this to someone
                        </Button>
                      </Box>
                    ))}
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
                        <Box sx={{ maxHeight: 220, overflowY: "auto", "&::-webkit-scrollbar": { width: 8 },
                          "&::-webkit-scrollbar-thumb": { background: "#d6dae2", borderRadius: 99 } }}>
                          {m.Channel === "report" && looksMd(m.BodyText)
                            ? <Md text={cleanText(m.BodyText)} />
                            : <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block" }}>{cleanText(m.BodyText)}</Typography>}
                        </Box>
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
      <Dialog open={feedOpen} onClose={() => setFeedOpen(false)} fullWidth maxWidth="md" PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ pb: 0.5 }}>Feed the agent · {detail?.ref}
          <Typography variant="caption" sx={{ color: FAINT, display: "block", fontWeight: 400, mt: 0.25 }}>
            Queue prompts for this task's agent - one, or a whole list. They land one per stop, in order, never mid-turn.
          </Typography>
        </DialogTitle>
        <DialogContent>
          {selected && liveCodingSession && <TellAgent taskId={selected} taskRef={detail?.ref} onQueued={() => loadDetail(selected)} />}
        </DialogContent>
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
            General / non-coding opens the visual assistant without a repository. Coding opens the agent's repository terminal. Reply creates a draft in Review.
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
