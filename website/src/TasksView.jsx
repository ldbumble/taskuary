// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import { says } from "./laneSays.js";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, IconButton, InputAdornment, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import SearchIcon from "@mui/icons-material/Search";
import api from "./api";
import { completionTransition, cutAway, filterForSelectedState, remindWaiting, remindDay } from "./taskFilter.js";
import { onLive } from "./live.js";
import { PANEL2, BORDER, DIM, FAINT, INK, card, ACCENT, PILL_COLORS, ALERT } from "./theme.jsx";
import { StateChip, stateOf, TASK_STATES, asUtc, timeAgo, Empty, FilterPills, isWaiting, assignedAgent } from "./ui.jsx";
import { ListItemText } from "@mui/material";
import TaskPage from "./TaskPage.jsx";

// An open tab can still hold yesterday's entry bundle after a local upgrade. Vite names lazy
// chunks by content, so that tab asks the new server for a filename the build no longer has.
// Recover once automatically; a real module error still reaches the view boundary on retry.
import { isGeneralKind } from "./autostart.js";
import { ASK_TAG } from "./newTask.js";

// three pills (the owner, 2026-09-25): what is on a plate, what is put away until a day, and what is done.
// "all" held the other two over again, so a live task sat in two pills at once ("we don't want one for
// all if it's another group"); every task now has one pill. Dropped has none - search finds it.
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
  { key: "live", label: "in progress", c: ST_C.working },
  { key: "upcoming", label: "upcoming", c: ST_C.queued },
  { key: "done", label: "done", c: ST_C.done },
];
// "today" as the person reading the list means it - the server's clock, in local terms
const isToday = (s) => !!s && asUtc(String(s)).toDateString() === new Date().toDateString();
const touchedToday = (t) => isToday(t.ClosedAt) || isToday(t.UpdatedAt) || isToday(t.CreatedAt);
// everything still on somebody's plate - yours or an agent's. Dropped is neither, and
// has no pill - search finds it.
const bucketOf = (t) => (remindWaiting(t) ? "upcoming" : stateOf(t).key);
const inBucket = (t, key) => (key === "live" ? !["done", "dropped"].includes(stateOf(t).key) && !remindWaiting(t)
                                             : bucketOf(t) === key);
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
const kindLabel = (kind) => KIND_OPTIONS.find((o) => o.key === kind)?.label || kind;

// The task's settings read as FACTS you can change, not as a form: pill-shaped, label-less,
// sitting on the card's bottom edge. Stacked "Type / Task status / Priority" labels over boxed
// selects made a four-field form out of four words, and put the one button that completes the
// task at the end of it (the owner, 2026-09-16: "on bottom the filters agent·coding, waiting").
// the repo is a filter like the others, but it opens a picker rather than a menu of values
// ...and the one filled move beside them. Every card's bar reads [ primaryBtn ] | [ barBtn ] [ barBtn ].
// A LIVE SESSION'S CONTROLS LOOK LIKE CONTROLS. These were bare text buttons sitting next to
// the outlined role/brain/repo pills, so the two things you could press had less edge than the
// three facts you can only read - "buttons are still not clear what they are. and they are
// floating" (the owner, 2026-09-16). Same pill geometry as the facts beside them, in the slate
// the app uses for every control: the colour says pressable, the border says where it ends.
// Not filled - filled is Mark done's, one strip up, and a live session has no primary.
// ...and SMALL, because every row this bar spends is a row the terminal does not get.
// the same pill as chipBtn, for a fact you read rather than a control you press

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

export default function TasksView({ selected, onSelect, onChanged, autostart, onAutostarted, onGoReports, active = true, openAct, onActOpened }) {
  const [tasks, setTasks] = useState(null);
  const [leavingId, setLeavingId] = useState(null);     // a task closed at the press, still closing on the server (finishWith)
  // "live" on arrival: what is still on somebody's plate is what you came here for. "done"
  // opens on a list whose top is whatever finished most recently.
  const [filter, setFilter] = useState("live");
  // A ROW'S STATE CHIP IS THE FILTER (the owner, 2026-09-28: "filter by waiting to start / on you / agent waiting on you
  // ... as minimal as possible", on this page): click it and In progress shows only that state; its pill clears it
  const [only, setOnly] = useState(null);
  const [query, setQuery] = useState("");
  // what the loaded rows are FOR. The box is debounced because every change is now a round trip.
  const [sent, setSent] = useState("");
  // "done" piles up for months; today's are the ones you came to look at, the rest
  // wait behind one button. In progress is never cut: what is still on a plate must show.
  const [older, setOlder] = useState(false);
  const selRef = useRef(selected); selRef.current = selected;
  const [repos, setRepos] = useState([]);
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => setRepos(
      (data.data || []).filter((x) => x.Channel === "github" && x.Active).map((x) => x.Address)
    )).catch(() => {});
  }, []);
  const taskLoadSeq = useRef(0);
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
  // the tab always lands on what is still in progress - whatever it was left on last time
  useEffect(() => { if (active) { setFilter("live"); setOlder(false); } }, [active]);
  useEffect(() => { setOlder(false); }, [filter]);
  // ...and keep it honest: the rows are re-asked on every task change while this tab is on screen (the open task's own
  // view, TaskPage, reloads itself on the same event)
  useEffect(() => {
    if (!active) return undefined;
    loadTasks();
    return onLive("task-changed", () => loadTasks());
  }, [active, loadTasks]);
  // A SESSION THAT GOES QUIET is an agent waiting on you, and no event says so: the rows are read again when one
  // flips, the same check the Board makes, so the two pages move together (T9)
  useEffect(() => {
    if (!active) return undefined;
    let sig = null;
    const tick = () => api.get("/api/runs/live").then(({ data }) => {
      const now = (data.data || []).map((r) => `${r.TaskId}:${isWaiting(r) ? 1 : 0}`).sort().join(",");
      if (sig !== null && now !== sig) loadTasks();
      sig = now;
    }).catch(() => {});
    tick(); const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [active, loadTasks]);
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
  const search = query.trim();
  useEffect(() => {
    const id = setTimeout(() => setSent(search), 250);
    return () => clearTimeout(id);
  }, [search]);
  // The one gesture that needs more than the live set. "done" on its own does NOT: ?active=1
  // already carries today's, which is what it shows until "show older". A search no longer
  // belongs here at all - it asks the server for its own answer.
  useEffect(() => {
    if (older && !fullLoaded.current) loadTasks(true);
  }, [older, loadTasks]);
  // Search means the whole archive, regardless of the selected state pill or today's cutoff. That
  // is what makes a completed PR/task discoverable instead of merely searching the visible rows -
  // and the rows ARE the matches now, so there is nothing left here to filter them by.
  const bucket = (tasks || []).filter((x) => x.TaskId !== leavingId).filter((x) => sent || ((!filter || inBucket(x, filter)) && (!only || filter !== "live" || stateOf(x).label === only)));
  // ONE RULE, FOR THE ROWS AND FOR THE COUNTS. The cut used to be decided per pill, which gave
  // `in progress` a wider window than `all` - live work of any age against today only - so two
  // live rows from last night counted for one pill and not the other and "all 5" sat over
  // "in progress 4 · done 2" (the owner, 2026-09-22: "that doesn't add up?").
  // ...and a task the work rail shows, or showed you today, is never history, whatever day it closed (the owner, 2026-09-24)
  const keep = (x) => !!sent || x.OnWorkToday || !cutAway(stateOf(x).key, touchedToday(x), older);
  // upcoming reads as a calendar: soonest first. Done is by task number, highest first (T17, the owner, 2026-09-25) -
  // it came in the server's order, which a comment called "by when it finished" and was not.
  const shown = bucket.filter(keep).sort((a, b) => (sent ? 0 : filter === "upcoming" ? String(a.RemindAt).localeCompare(String(b.RemindAt))
    : filter === "done" ? b.TaskId - a.TaskId : 0));
  const nOlder = bucket.length - shown.length;
  // A count that outruns the rows beneath it reads as a bug: "done 175" over fifteen rows says
  // the list is broken, not cut. Each pill counts what clicking it would SHOW, by the same rule.
  const countIn = (key) => (tasks || []).filter((x) => (!key || inBucket(x, key)) && keep(x)).length;
  const liveStates = Object.values((tasks || []).filter((x) => inBucket(x, "live") && keep(x)).reduce((acc, x) => {
    const st = stateOf(x);
    acc[st.label] = { key: st.label, label: st.label, c: st.c, n: (acc[st.label]?.n || 0) + 1 };
    return acc;
  }, {})).sort((a, b) => b.n - a.n);
  // A task may finish while its detail stays open (especially an assistant conversation). Move
  // the selected bucket with it so Done never sits under an In progress filter. Search is a
  // deliberate cross-status view, so it is not changed.
  // ...but ONLY when the task changed under you. This also fired on the filter itself, which
  // made the pills unusable: with a done task selected, clicking "in progress" set the filter,
  // this read the still-done selection and put it straight back - the pill lit for an instant
  // and the list never moved.
  const seenState = useRef({ id: null, key: null });
  useEffect(() => {
    if (!active || !selected || !tasks || search || !filter) return;
    const row = tasks.find((x) => x.TaskId === selected);
    if (!row) return;
    const key = bucketOf(row);
    const was = seenState.current;
    seenState.current = { id: selected, key };
    if (was.id === selected && was.key === key) return;   // nothing moved
    // A closed task opened from a deep link or another tab must not sit under a highlighted
    // In progress pill. New selections align the rail too; explicit filter clicks move the
    // selection in `changeFilter` below, so this cannot make the pills snap back.
    const next = filterForSelectedState(filter, key);
    if (next !== filter) { setFilter(next); setOlder(false); }
  }, [active, selected, tasks, search, filter]);

  // ...except when the owner ENDS it. The effect above exists so a task that moves state under you stays on screen, and
  // for done it did exactly the wrong thing: Mark done followed the task into the Done list. Closing a task is a
  // statement that you are finished looking at it, so let go of it and stay where the work is. TaskPage runs the close
  // (`close`); this pre-records the state it is about to see - the server emits task-changed during the PATCH, and
  // without the guard that event makes the effect above chase the closing task into Done - then picks the next live row.
  const finishWith = async (status, close) => {
    const liveIds = (tasks || []).filter((x) => inBucket(x, "live")).map((x) => x.TaskId);
    const transition = completionTransition(liveIds, selected, status);
    const before = seenState.current;
    seenState.current = transition.seen;
    setFilter(transition.filter); setOlder(false); setQuery("");
    // PUT DOWN AT THE PRESS, as the Assistant's canvas does (the owner, 2026-10-02: "the task stays open for a 2 count then
    // closes"): it leaves the list and the next one opens now; the close runs behind, and one that fails comes back with why
    const was = selected;
    setLeavingId(was); onSelect(transition.next);
    try { await close(); } catch (e) { seenState.current = before; setLeavingId(null); onSelect(was); throw e; }
  };
  // ...and it stays off the list until a reload no longer has it as live work
  useEffect(() => {
    if (leavingId && tasks && !tasks.some((x) => x.TaskId === leavingId && inBucket(x, "live"))) setLeavingId(null);
  }, [tasks, leavingId]);
  // Remind me: put away until a day, the list moves on with it - into Upcoming, or back into In progress
  const reminded = (out) => {
    if (out?.remindAt && filter === "live") {
      const tr = completionTransition((tasks || []).filter((x) => inBucket(x, "live")).map((x) => x.TaskId), selected, "upcoming");
      seenState.current = tr.seen; onSelect(tr.next);
    }
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
          {/* THE STATES OF WHAT IS IN PROGRESS, ON TOP (the owner, 2026-09-28: "don't see the filter on top of tasks") -
              the same pills as the row above, a count each, only when there is more than one state to tell apart */}
          {filter === "live" && !search && liveStates.length > 1 && (
            <Box className="tq-tasks-states" sx={{ px: 1, pt: 0.75, bgcolor: PANEL2, flexShrink: 0 }}>
              <FilterPills value={only || ""} onChange={(k) => setOnly(k || null)}
                options={[{ key: "", label: "all", n: liveStates.reduce((a, x) => a + x.n, 0) }, ...liveStates]} />
            </Box>
          )}
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
                // the one shown is unmistakable: 2px ring + a wash of its colour (2026-09-28: "barely tell which task is shown")
                sx={{ px: 1.25, py: 0.9, mb: 0.75, cursor: "pointer", borderRadius: 1.75,
                  bgcolor: sel ? `color-mix(in srgb, ${st.solid} 9%, #fff)` : "#fff",
                  border: sel ? `2px solid ${st.solid}` : `1px solid ${BORDER}`, borderLeft: `${sel ? 5 : 3}px solid ${st.solid}`,
                  boxShadow: sel ? `0 2px 12px color-mix(in srgb, ${st.solid} 28%, transparent)` : "none",
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
                    {remindWaiting(task) ? `back ${remindDay(task.RemindAt)}` : timeAgo(task.CreatedAt)}
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
                  {/* the state says it once - "agent stopped" had its own chip beside it (T1) */}
                  <Box component="span" role="button" tabIndex={0} sx={{ cursor: "pointer", display: "inline-flex" }}
                    title={only ? "Show everything in progress again" : `Show only “${st.label}”`}
                    onClick={(e) => { e.stopPropagation(); setFilter("live"); setOnly(only ? null : st.label); }}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); setFilter("live"); setOnly(only ? null : st.label); } }}>
                    <StateChip task={task} />
                  </Box>
                </Box>
                {/* the third line, and ONLY when it has something to say - a queued task with no list
                    stays two lines, so the rail does not pay for this everywhere */}
                {/* A START THAT FAILED says so on the row, with the error (T10) - it said "starts by itself when it can" */}
                {task.State === "queued" && task.Queued?.state === "failed" && (
                  <Typography noWrap title={task.Queued.lastError || ""} sx={{ fontSize: 10.5, mt: 0.45, color: ALERT, fontWeight: 600 }}>
                    could not start{task.Queued.lastError ? ` - ${task.Queued.lastError}` : ""}
                  </Typography>
                )}
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

      {/* ── the task view (TaskPage.jsx) ─────────────────────────────────── */}
      <TaskPage taskId={selected} listRow={(tasks || []).find((x) => x.TaskId === selected) || null}
        onListChanged={loadTasks} onSelect={onSelect} onClose={dismiss} onFinish={finishWith} onReminded={reminded}
        onChanged={onChanged} autostart={autostart} onAutostarted={onAutostarted} onGoReports={onGoReports}
        active={active} openAct={openAct} onActOpened={onActOpened} />
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
    </Box>
  );
}
