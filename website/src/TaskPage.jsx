// THE TASK VIEW (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md): one task's
// three stages - Task, Agent work, Close out - with their bars, chips and the agent's pane. It was the right half of the
// Tasks tab; it is its own component now so the assistant canvas can show the very same view for the item on its table.
// The list around it (TasksView) owns selection, filters and what comes next; this owns everything about one task.
// Tasks: dense two-pane - list rows on the left, the selected task's full story right.
import { says, subState } from "./laneSays.js";
import ContinueBox from "./ContinueBox.jsx";
import { AttachImage, ImageTray, usePromptImages, withImages } from "./promptImages.jsx";
import QueuedStart from "./QueuedStart.jsx";
import { strangerLine } from "./strangerLine.js";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useCapabilities } from "./capabilities.js";
import { createPortal } from "react-dom";
import {
  Alert, Autocomplete, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  Drawer, IconButton, InputAdornment, Link, Menu, MenuItem, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import RemindMe, { RemindPicker } from "./RemindMe.jsx";
import { SlotPicker } from "./CalendarPick.jsx";
import { onPressed, useVerbs } from "./actionRow.js";
import { choice, hint as btnHint, hintOfRow, label as btn, labelOfRow } from "./buttons.js";   // theme.jsx owns `label`
import BlockIcon from "@mui/icons-material/Block";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import DifferenceIcon from "@mui/icons-material/Difference";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import api from "./api";
import { openReply as draftReply } from "./replyDraft.js";   // the component's own openReply below would shadow it, and call itself
import { opError, runOperation } from "./taskOps.js";
import { ClosingCard, WriteupBlock, completeTask, writeUpThenClose } from "./closeAgent.jsx";
import { writeupView } from "./writeupState.js";
import { agentName } from "./agentWork.js";
import { lazyGeneral } from "./lazyGeneral.js";
import { outcomeOf } from "./dispatchOutcome.js";
import { FailWays, failOf } from "./failure.jsx";
import { noteKey, noteOf, progressLine, saveNote, settleTick, withTicks } from "./checklist.js";
import { fmtDate, fmtTime } from "./dates.js";
import { deliveryCc, deliveryFiles, replyContext } from "./replyDelivery.js";
import { sizeText } from "./replyFiles.js";
import { completionTransition, cutAway, filterForSelectedState, remindWaiting, remindDay } from "./taskFilter.js";
import ReviewDecision from "./ReviewDecision.jsx";
import SlotList from "./SlotList.jsx";
import BatchItems from "./BatchItems.jsx";
import { progress as batchProgress } from "./batchItems.js";
import CloseNote from "./CloseNote.jsx";
import { onLive } from "./live.js";
import { pollWhileActive } from "./visible.js";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, frame, frameInner, label, step, PALETTE, hoverable, mono, ACCENT, ACCENT2, PILL_COLORS, ALERT, ALERT_BD, ALERT_INK, ALERT_TINT, BRAND } from "./theme.jsx";
import RunSteps from "./RunSteps.jsx";
import { cameFromLabel, channelName, expands, filesByMessage, groupConversations, groupMeta, headerFacts, isChat, latestRows, madeLine, previewRows, rowText, triageLine, workflowOrigin } from "./taskSources.js";
import { latestTriageVerdict, legacyTriageVerdict, parseTriageVerdict, routeIntent } from "./triageVerdict.js";
import { Handoff } from "./Handoff.jsx";
import { Reshape } from "./Reshape.jsx";
import { RepoPicker, RepoSelect } from "./RepoPicker.jsx";
import { Attachments, mentionsPicture } from "./Attachments.jsx";
import ChatThread from "./ChatThread.jsx";
import { ChannelIcon, MicButton, LifecycleChip, StateChip, stateOf, TASK_STATES, asUtc, tsMs, AgentPicker, useAgents, codingProfile, RunTrace, DiffBlock, DiffFiles, timeAgo, fmtDateTime, cleanText, Empty, FilterPills, Confirm, WorkStrip, isWaiting, TaskuaryMark, agentAssignee, assignedAgent, assigneeLabel } from "./ui.jsx";
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
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

// An open tab can still hold yesterday's entry bundle after a local upgrade. Vite names lazy
// chunks by content, so that tab asks the new server for a filename the build no longer has.
// Recover once automatically; a real module error still reaches the view boundary on retry.
import { autostartPlan, isGeneralKind } from "./autostart.js";
import { adviceKeyFor, suggestion } from "./advice.js";
import { agentWorkspaceMode, barContinues } from "./taskWorkspace.js";
import { ASK_TAG } from "./newTask.js";
import { completionFact, completionLine, waitingEmails, wentOut,
  AGENT, agentPhase, focusStage, generalAnswered, hasCorrespondent, ownerControlsCompletion, pendingProposals, pendingReplyReview, replyPhase, replySource, sentElsewhere, sentReplyReview, sessionWord, taskPhase, unsentReplyReview,
} from "./taskLifecycle.js";
import { closeoutOf } from "./reviewProposal.js";
import { AgentRecord } from "./AgentRecord.jsx";
import AgentStory, { StoryChip } from "./AgentStory.jsx";
import { STORY_CHIP, startLabel, storyPlace, storyShown } from "./agentStory.js";
import PublishedPages, { isPublished } from "./PublishedPages.jsx";
import EmailSomeone from "./EmailSomeone.jsx";
import { ago, filesLine, plural } from "./timeWords.js";
import { KIND_OPTIONS, KINDS, kindLabel, shortKind } from "./kinds.js";
import { openAppLink } from "./appLinks.js";
import { heldSteps, heldTask, heldTerm, heldWait, keepTask, keepTerms } from "./taskDetail.js";

const GeneralWorkspace = React.lazy(lazyGeneral("GeneralWorkspace"));   // the guard lives in lazyGeneral.js

const repoOf = (t) => (String(t?.Tags || "").match(/repo:([^\s,]+)/) || [])[1] || null;
// the repository question in plain words - "pick a repo" read as code-speak on the card (the walk's WORDS, 2026-10-17); it is only
// asked at all where a coding tool is connected (capabilities.coding)
const PICK_CODE = btn("pick_repo");
// a thread on the task reads newest first, like the task does (the owner, 2026-10-14)
export const newestFirst = (ms = []) => [...ms].sort((a, b) => String(b.SentAt || "").localeCompare(String(a.SentAt || "")));

// `assistant` is a legacy alias from Timeline discussions. New discussions use `general`, but
// old ones must still open here instead of falling through to the coding terminal.
const PRIORITIES = ["low", "normal", "high", "urgent"];
const NAT_TITLE = "Removes this task. Taskuary stops making tasks from messages like this; the email itself is kept, and search finds it.";

// WHAT TRIAGE DECIDED READS AS FACTS, NOT CONTROLS (the owner, 2026-10-16: "why are there dropdowns by the triage results? you
// can't change it"). The pills sit under the title, read-only; changing who does it, the priority, the assignee or the repository is
// on the bar by the prompt box (the row's Task menu) on the canvas, and behind Change on the Tasks tab's own bar.
const factPill = { display: "inline-flex", alignItems: "center", gap: 0.6, height: 22, px: 1.1, borderRadius: 11, border: `1px solid ${BORDER}`,
  bgcolor: "#fff", fontSize: 11.5, color: INK, whiteSpace: "nowrap", maxWidth: "100%", overflow: "hidden", minWidth: 0 };
// ...and SAID AS ONE LINE in plain words (the audit, 2026-10-17): "Triage decided · Intent task · Who does it an agent · general" was
// the sorter's own vocabulary. Now "Sorted as: a task for an assistant · normal priority". A held repository stays a pill: it is a warning.
const SAID = new Set(["intent", "who", "profile", "repo", "priority"]);
export const sortedLine = (facts, kind) => {
  const v = (k) => facts.pills.find((p) => p.key === k && p.tone !== "alert")?.value || "";
  const intent = v("intent"), reply = intent === "reply" || kind === "reply";
  const what = reply ? "a reply to send" : intent === "fyi" ? "for your information" : `a task ${{ general: "for an assistant", coding: "for your coding tool" }[kind] || "for you"}`;
  const head = facts.triaged ? `Sorted as: ${what}` : what.charAt(0).toUpperCase() + what.slice(1);
  return [head, v("repo") && `in ${v("repo")}`, `${v("priority") || "normal"} priority`].filter(Boolean).join(" · ");
};
const FACT_TONE = { agent: { bgcolor: BRAND.tint, borderColor: BRAND.bd, k: BRAND.ink }, alert: { bgcolor: ALERT_TINT, borderColor: ALERT_BD, color: ALERT_INK, k: ALERT_INK } };
// "09:06" today, "Oct 9" before - a row of messages reads its times at a glance
const whenShort = (s) => {
  if (!s) return "";
  const d = asUtc(String(s));
  if (!Number.isFinite(d.getTime())) return "";
  return d.toDateString() === new Date().toDateString() ? fmtTime(d, [], { hour: "2-digit", minute: "2-digit" })
    : fmtDate(d, [], { month: "short", day: "numeric" });
};
// SHOW ALL IS FOR READING (the owner, 2026-10-20: seven messages in a 360px box): the opened thread is as tall as the window
// leaves room for - the terminal's rule, every row the page can give - and never shorter than the box it was; past that it scrolls
const THREAD_MAX = "max(360px, calc(100vh - 160px))";
// A CONVERSATION CONDENSED: one line a message - who, the words, when - and "· · · N more" where rows are left out; a row opens its
// message in full under it. Task's Came from and Close out draw this SAME list (the owner, 2026-10-16: "full chat should be in task
// (condensed and full). in close out chats condensed version?"), so the two cannot tell one conversation two ways.
// THE GAP IS THE WAY IN (the owner, 2026-10-20: "··· 4 more - Gail Moreno, You" sat between the messages and Show all was at the top, where
// nobody looked): with `onExpand` the line itself opens the whole conversation - the same action as Show all above it. `files` is each
// message's attachments (taskSources.filesByMessage): what rode in with a message is drawn under ITS row, never loose under the card.
function ConversationRows({ rows, open, onOpen, onExpand, files = new Map(), fetchFor = null }) {
  return rows.map((r, ri) => r.gap ? (onExpand ? (
    <Box key={`gap${ri}`} component="button" type="button" data-tq-conversation-gap="" onClick={onExpand} title="Show the whole conversation"
      sx={{ appearance: "none", font: "inherit", display: "block", width: "100%", textAlign: "left", bgcolor: "transparent", border: 0, cursor: "pointer",
        color: FAINT, fontSize: 12, py: 0.2, px: 0.5, mx: -0.5, borderRadius: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        "&:hover": { color: INK, bgcolor: "#faf8f4" }, "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } }}>
      · · · {r.gap} more - {r.names}</Box>
  ) : (
    <Typography key={`gap${ri}`} variant="caption" sx={{ display: "block", color: FAINT, fontSize: 12, py: 0.2 }} noWrap>
      · · · {r.gap} more - {r.names}</Typography>
  )) : (
    <React.Fragment key={r.m.MessageId}>
      <Box component="button" type="button" data-tq-conversation-row="" aria-expanded={open === r.m.MessageId}
        onClick={() => onOpen((v) => (v === r.m.MessageId ? null : r.m.MessageId))}
        title="Open the message"
        sx={{ appearance: "none", font: "inherit", width: "100%", textAlign: "left", bgcolor: "transparent", border: 0, cursor: "pointer",
          display: "grid", gridTemplateColumns: { xs: "minmax(0, 88px) minmax(0, 1fr) auto", sm: "112px minmax(0, 1fr) 64px" }, columnGap: 1.25,
          alignItems: "baseline", px: 0.5, mx: -0.5, py: 0.25, borderRadius: 1, fontSize: 12.5, color: DIM, minWidth: 0,
          "&:hover": { bgcolor: "#faf8f4" }, "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } }}>
        <Box component="span" sx={{ color: INK, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.m.who}</Box>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rowText(r.m, files.get(r.m.MessageId))}</Box>
        <Box component="span" sx={{ color: FAINT, textAlign: "right", whiteSpace: "nowrap", fontSize: 11.5 }}>{whenShort(r.m.SentAt)}</Box>
      </Box>
      {open !== r.m.MessageId && (files.has(r.m.MessageId) || fetchFor === r.m.MessageId) && (
        <Box data-tq-row-files="" sx={{ pl: { xs: 0, sm: "122px" }, mt: -0.5, mb: 0.4, minWidth: 0 }}>
          <Attachments messageId={r.m.MessageId} canFetch={fetchFor === r.m.MessageId} dense /></Box>
      )}
      {open === r.m.MessageId && (
        <Box sx={{ my: 0.6, p: 1.1, border: `1px solid ${BORDER}`, borderRadius: 1, bgcolor: PANEL, minWidth: 0 }}>
          <Box sx={{ display: "flex", gap: 0.75, alignItems: "baseline", flexWrap: "wrap" }}>
            <Typography sx={{ color: INK, fontSize: 11.5, fontWeight: 600 }}>{r.m.who}</Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>{channelName(r.m.Channel)}{r.m.SentAt ? ` · ${fmtDateTime(r.m.SentAt)}` : ""}</Typography>
            {r.m.SourceLink && <Link href={r.m.SourceLink} target="_blank" rel="noopener" sx={{ fontSize: 11 }}>open the original</Link>}
          </Box>
          {r.m.Subject && <Typography variant="body2" sx={{ color: INK, fontWeight: 600, mt: 0.1 }}>{r.m.Subject}</Typography>}
          {/* WHERE IT CAME FROM IS THE WHOLE MESSAGE, in full and scrolling - three lines of it were never enough to check the ask
              against: first for a report run (the owner, 2026-09-30: "i can't see the full report once it gets sent to agent"), then
              for the email behind a task (2026-10-01: "don't see the full email that this task came from") */}
          <Box sx={{ mt: 0.5, maxHeight: 420, overflowY: "auto", minWidth: 0, overflowWrap: "anywhere" }}>
            {r.m.Channel === "report" && looksMd(r.m.BodyText) ? <Md text={cleanText(r.m.BodyText)} />
              : <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                  {cleanText(r.m.Channel === "report" ? r.m.BodyText : (r.m.ReadText ?? r.m.BodyText))}</Typography>}
          </Box>
          <Attachments messageId={r.m.MessageId} canFetch={r.m.Channel === "email" && mentionsPicture(r.m.BodyText)} dense />
        </Box>
      )}
    </React.Fragment>
  ));
}
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
// Not filled - filled is Mark done's, one strip up, and a live session has no primary.
// ...and SMALL, because every row this bar spends is a row the terminal does not get.
const liveCtl = { fontSize: 10.5, fontWeight: 600, height: 23, minHeight: 23, py: 0, px: 0.9,
  borderRadius: 11.5, color: ACCENT, bgcolor: "#f1f4f7", borderColor: "#c7d2dc", whiteSpace: "nowrap",
  "& .MuiButton-startIcon": { mr: 0.5, ml: 0 },
  "&:hover": { borderColor: ACCENT, bgcolor: "#e7eef4" } };
// the same pill as chipBtn, for a fact you read rather than a control you press
const chipBtnStatic = { display: "inline-flex", alignItems: "center", height: 26, px: 1.25,
  borderRadius: 13, bgcolor: "#f4f1ec", border: `1px solid ${BORDER}`, color: INK,
  fontSize: 11.5, fontWeight: 600 };

// ── the list rail's row ──────────────────────────────────────────────────────────────────
// One word for the kind (kinds.shortKind): the agent's own name follows it on the same line, so "agent · coding ·
// coding" spent three words saying an agent has it.
// The checklist is already on every list row - store.list_tasks selects t.* and the Checklist
// column rides along - so the rail draws progress without a request per task.
const rowChecklist = (t) => {
  try { const a = JSON.parse(t?.Checklist || "[]"); return Array.isArray(a) ? a.filter((i) => i && i.text) : []; }
  catch { return []; }
};

// A GOAL'S STEPS (spec 2026-10-12): the checklist, each box with the task behind it. Start makes a box a task of its own;
// a box with a task shows its ref and state and opens it. The parent's box ticks itself when the child closes (store).
// ONE PART OF THE TASK SECTION, its name in its own column (the owner, 2026-10-16: "no line but we need way to show came from|to do|
// the ask are separate sections"): the label column sets each part apart without drawing a rule; at phone width it sits above
function Part({ label, sub, subTitle, children, ...rest }) {
  return (
    <Box {...rest} sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "112px minmax(0, 1fr)" }, columnGap: 2, rowGap: 0.4, minWidth: 0 }}>
      <Box sx={{ pt: { sm: 0.2 }, minWidth: 0 }}>
        <Typography sx={{ color: INK, fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>{label}</Typography>
        {sub && <Typography variant="caption" title={subTitle} sx={{ color: FAINT, display: "block", lineHeight: 1.35 }}>{sub}</Typography>}
      </Box>
      <Box sx={{ minWidth: 0, maxWidth: 900 }}>{children}</Box>
    </Box>
  );
}

function GoalSteps({ task, onOpenTask, onChanged }) {
  // NULL UNTIL READ, AND A FAILED READ IS NOT AN EMPTY GOAL (G8): this started as [] and a failure set [] too, so every goal said
  // "no steps yet" while its steps loaded, and for good when they did not. Read ahead with the goal itself when it could be (taskDetail.js)
  const [steps, setSteps] = useState(() => heldSteps(task.TaskId));
  const [stepsFailed, setStepsFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const load = useCallback(() => api.get(`/api/tasks/${task.TaskId}/steps`).then((r) => { setSteps(r.data.steps || []); setStepsFailed(false); })
    .catch(() => setStepsFailed(true)), [task.TaskId]);
  useEffect(() => { load(); }, [load, task.UpdatedAt]);
  const start = async (s) => { const { data } = await api.post(`/api/tasks/${task.TaskId}/steps/${s.id}/start`); load(); onChanged?.(); onOpenTask?.(data.taskId); };
  // EVERY PRESS LEAVES A RECEIPT (Stream B, the owner 2026-10-18): the step doors are the task tools' own road (taskOps.runOperation) -
  // recorded, and said in the chat when this goal is on the Assistant's table
  const [stepErr, setStepErr] = useState("");
  const op = async (kind, params, fallback) => {
    setStepErr("");
    try { await runOperation(api, kind, task.TaskId, params); return true; } catch (e) { setStepErr(opError(e, fallback)); return false; }
  };
  // ...on a real move only: the field answers every blur, and an unchanged day pressed nothing
  const moveDate = async (e) => {
    if ((e.target.value || "") === String(task.DueAt || "").slice(0, 10)) return;
    await op("task.update", { due: e.target.value || "none" }, "The due day didn't change - pick it again."); onChanged?.();
  };
  // "Track it, I have the plan" needs doors of its own (the review, 2026-10-12): a step done by hand is ticked here, and a
  // step is added here - the same checklist tools the task card uses; a step with a child ticks itself when it closes
  const tick = async (s) => {
    await op("task.check", { item: String(steps.indexOf(s) + 1), id: s.id, done: !s.done }, "That step didn't change - tick it again.");
    load(); onChanged?.();
  };
  const add = async () => {
    const text = draft.trim(); if (!text) return;
    if (await op("task.checklist", { items: [...(steps || []).map((s) => s.text), text] }, "The step wasn't added - it is still in the box; add it again.")) setDraft("");
    load(); onChanged?.();
  };
  // RE-PLAN: the AI writes the steps again from the goal's words; a step already started keeps its place (server.plan_goal)
  const [replanning, setReplanning] = useState(false);
  const replan = async () => { setReplanning(true); try { await api.post(`/api/tasks/${task.TaskId}/read-ask`, { goal: true }); } finally { setTimeout(() => { setReplanning(false); load(); onChanged?.(); }, 4000); } };
  const list = steps || [], done = list.filter((s) => s.done).length;
  return (
    <Box sx={{ mt: 0.85, maxWidth: 900 }}>
      <Typography sx={{ ...label, display: "block", mb: 0.25 }}>Done when</Typography>
      <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{task.DoneWhen}</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 0.6, flexWrap: "wrap" }}>
        {/* while they are read the line says nothing rather than something untrue; a failed read says so, with its way past it */}
        {stepsFailed && !steps ? <Typography variant="caption" role="alert" sx={{ color: "#7a2f3c" }}>{"The steps didn't load. "}
            <Button size="small" variant="text" onClick={load} sx={{ fontSize: 11, textTransform: "none", minWidth: 0, p: 0, verticalAlign: "baseline" }}>{btn("try_again")}</Button></Typography>
          : <Typography variant="caption" data-tq-steps={steps ? list.length : "reading"} sx={{ color: FAINT, minWidth: 90 }}>{!steps ? "" : list.length ? `${done} of ${list.length} steps done` : "no steps yet"}</Typography>}
        <Typography variant="caption" sx={{ color: FAINT }}>by</Typography>
        <TextField type="date" size="small" defaultValue={String(task.DueAt || "").slice(0, 10)} onBlur={moveDate}
          inputProps={{ "aria-label": "Move the date" }} sx={{ "& .MuiInputBase-root": { fontSize: 12, height: 26 } }} />
        <Button size="small" variant="text" onClick={replan} disabled={replanning} sx={{ fontSize: 11, textTransform: "none", ml: "auto" }}
          title="The AI writes the steps again from what done looks like; a step already started keeps its place">{replanning ? "Planning…" : "Re-plan"}</Button>
      </Box>
      {list.map((s, k) => (
        <Box key={s.id} sx={{ borderBottom: `1px solid ${BORDER}` }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, py: 0.35 }}>
          <Typography variant="caption" sx={{ color: FAINT, width: 16, fontVariantNumeric: "tabular-nums" }}>{k + 1}</Typography>
          <Checkbox size="small" checked={!!s.done} onChange={() => tick(s)} disabled={!!s.ref} inputProps={{ "aria-label": `Step ${k + 1} done` }}
            sx={{ p: 0.25, color: "rgba(0,0,0,.54)", "&.Mui-checked": { color: "#6f8a6e" } }} />
          <Typography variant="body2" sx={{ flex: 1, color: s.done ? FAINT : INK, textDecoration: s.done ? "line-through" : "none" }}>{s.text}</Typography>
          {s.who && <Typography variant="caption" sx={{ color: FAINT }}>{s.who}</Typography>}
          {s.ref
            ? <Button size="small" variant="text" onClick={() => onOpenTask?.(s.tid)} sx={{ fontSize: 11, textTransform: "none" }}>{s.ref} · {s.state || s.status}</Button>
            : !s.done && <Button size="small" variant="outlined" onClick={() => start(s)} sx={{ fontSize: 11, textTransform: "none" }}
              title={btnHint("regular_agent")}>{btn("regular_agent")}</Button>}
        </Box>
        {/* the mail triage said served this step (store.step_arrivals) - who sent what, under the step it moved */}
        {(s.arrivals || []).map((a) => (
          <Typography key={a.mid} variant="caption" sx={{ color: FAINT, pl: 4.5, pb: 0.3, display: "block" }}>↳ {a.who} sent "{a.subject}" · {String(a.at || "").slice(0, 16)}</Typography>
        ))}
        </Box>
      ))}
      <Box sx={{ display: "flex", gap: 0.8, alignItems: "center", mt: 0.6 }}>
        <TextField size="small" fullWidth placeholder="Add a step" value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} inputProps={{ "aria-label": "Add a step" }}
          sx={{ "& .MuiInputBase-root": { fontSize: 12 } }} />
        <Button size="small" variant="outlined" onClick={add} disabled={!draft.trim()} sx={{ fontSize: 11, textTransform: "none" }}>Add</Button>
      </Box>
      {stepErr && <Typography variant="caption" role="alert" sx={{ color: "#7a2f3c", display: "block", mt: 0.4 }}>{stepErr}</Typography>}
    </Box>
  );
}

export default function TaskPage({ taskId: selected, listRow = null, onListChanged, onSelect, onClose, onFinish, onReminded, onLeave, onStay, onOpenTask,
  onChanged, autostart, onAutostarted, onGoReports, active = true, openAct, onActOpened, canvas = false,
  onNext = null, nextBusy = false, expanded = false, onExpand = null, backArrow = false, title = "" }) {
  const canCode = useCapabilities().coding;                   // no coding tool connected: coding is not offered (capabilities.js)
  // ...drawn from the task's read held ahead of it (taskDetail.js) - a view on the table opens whole, not as an empty shell (G8)
  const [detail, setDetail] = useState(() => heldTask(selected));
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
  const hasAgentReport = (detail?.comments || []).some((c) => /^(?:AGENT|CODER) REPORT(?:\r?\n|$)/.test(String(c.Body || "").trimStart()));
  const hasTranscript = !!detail?.transcript;
  const detailTaskStatus = detail?.task?.Status;
  useEffect(() => {
    api.get("/api/sources").then(({ data }) => setRepos(
      (data.data || []).filter((x) => x.Channel === "github" && x.Active).map((x) => x.Address)
    )).catch(() => {});
  }, []);
  const stale = (id) => selRef.current !== id;
  const { agents, models, kinds, brains, brainList, brainModels, generalBrains } = useAgents();
  const pickerTask = useRef(null);          // initialize each task from its durable worker once
  const [err, setErr] = useState("");
  const [startFail, setStartFail] = useState(null);   // a failed agent start's ways past it (failures.py), drawn on the error line
  const [run, setRun] = useState({ agent: "", model: "", instruction: "" });
  // the next run's pictures - pasted, dropped or attached - ride in its instruction as paths, like Continue's (ContinueBox)
  const runPics = usePromptImages();
  // the repository the Start panel will open the coding session in (RepoSelect); null = not loaded / not offered
  const [startRepo, setStartRepo] = useState(null);   // "" = the roster's default (served first)
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
  const [wait, setWait] = useState(() => heldWait(selected) || { data: [], state: null });   // ...its waiting room with it (taskDetail.js)
  const [waitText, setWaitText] = useState("");
  const [wrapping, setWrapping] = useState(false);   // declared up here: the poll effect below reads it
  const [wrapped, setWrapped] = useState(null);      // the closing report, shown where the session was
  // Stop and save's write-up, running on the server: {id, n, job} - the task, how many notes it had at the press, and the job the
  // press started. Close out draws it (writeupView: the job's own stage, from the detail's `writeup`) until the draft replaces it.
  const [writingUpAt, setWritingUpAt] = useState(null);
  const pressedHere = writingUpAt?.id === selected ? writingUpAt : null;
  const writeup = writeupView({ pressed: pressedHere, server: detail?.task?.TaskId === selected ? detail?.writeup : null,
    comments: detail?.comments, review: pendingReplyReview(detail?.reviews || []) });
  const writingUp = writeup?.state === "pending" ? selected : null;
  // ...and Close out is brought into view at the press, once it has drawn
  const closeOutRef = useRef(null);
  const [seekCloseOut, setSeekCloseOut] = useState(false);
  useEffect(() => {
    if (!seekCloseOut) return undefined;
    const f = requestAnimationFrame(() => { closeOutRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }); setSeekCloseOut(false); });
    return () => cancelAnimationFrame(f);
  }, [seekCloseOut]);
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
  const [emailOpen, setEmailOpen] = useState(false);          // Email someone (EmailSomeone.jsx)
  const [senderQuestion, setSenderQuestion] = useState("");
  // "this one is mine" - the verdict that used to be a silent dropdown (TQ-0501)
  const [askingSender, setAskingSender] = useState(false);
  const [openingReply, setOpeningReply] = useState(false);
  const [openStage, setOpenStage] = useState(null);   // a stage you opened by hand, overriding the computed focus
  const [diff, setDiff] = useState(null);
  const [diffScope, setDiffScope] = useState("task");   // this task's footprint, or the whole checkout


  // the list is the page around this view (TasksView, or the assistant canvas): it reloads its own rows when told
  // THE PAGE'S CALLBACKS, HELD: the canvas hands fresh functions every render, and a load that listed them in its deps
  // refetched the task and rebuilt its live subscription on every keystroke in the composer (the final review)
  const onSelectRef = useRef(onSelect); onSelectRef.current = onSelect;
  const listRef = useRef(onListChanged); listRef.current = onListChanged;
  const loadTasks = useCallback(async () => { await listRef.current?.(); }, []);
  const loadDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return; }
    const ahead = heldTask(id);
    if (ahead) { setDetail((d) => (d?.task?.TaskId === id ? d : ahead)); const w = heldWait(id); if (w) setWait(w); }
    try {
      const { data } = await api.get(`/api/tasks/${id}`);
      if (stale(id)) return;
      setDetail(data); keepTask(id, data);
      try { const w = (await api.get(`/api/tasks/${id}/waitroom`)).data; if (!stale(id)) { setWait(w); keepTask(id, data, w); } }
      catch { if (!stale(id)) setWait({ data: [], state: null }); }
    } catch (e) {
      if (stale(id)) return;
      // A task can vanish under an open pane: "not mine" on its message deletes the task and
      // closes its session. The detail poll then asked for a dead id every three seconds and
      // repainted "task not found" each time, which reads as the app being broken rather than
      // as the thing you just did. Let go of it, and say it once.
      if (e?.response?.status === 404) {
        setDetail(null); onSelectRef.current?.(null);
        setErr("That task is gone - it was deleted.");
        return;
      }
      setErr(e?.response?.data?.detail || "Failed to load task");
    }
  }, []);

  // ...and keep it honest. The list was fetched ONCE, so a task whose agent picked it up
  // kept wearing "needs you" - and the pill counts kept agreeing with it - until something
  // else happened to reload. "Agent working" is a fact with a 45-second shelf life (a live
  // session that goes quiet is waiting on you); a row that states it has to be re-asked.
  // Only while this tab is the one on screen: it stays mounted behind the others.
  useEffect(() => {
    // Refresh now as well as on events: otherwise returning from Board shows the hidden
    // tab's old list until the next task-changed.
    if (!active) return undefined;
    // ...and the OPEN task with it. A session can be started from anywhere - the Assistant's
    // "send to the coding agent", the Board, a second window - and the detail poll only runs
    // once something is already known to be live, so a task sitting open on this page could
    // never learn it had an agent (TQ-0500: the Board showed a live coding session while this
    // page offered to start one, which would have made a second).
    return onLive("task-changed", () => { if (selRef.current) loadDetail(selRef.current); });
  }, [active, loadDetail]);
  // the roster is user-config - default to whatever actually exists. A GENERAL task's blank is an answer, not a gap: it means
  // "the profile it has", and filling it with the roster's first name sent the coding profile - which the dispatch refuses on a non-coding task (422), so
  // Send to agent failed on every general task nobody had assigned a role (the owner, 2026-10-07: "we don't want the coding profile always")
  const generalTask = isGeneralKind(detail?.task?.Kind);
  // the profile a blank pick runs (general.py: the role triage gave, else the assistant's own)
  const ownProfile = (agents.includes(assignedAgent(detail?.task?.Assignee)) && assignedAgent(detail?.task?.Assignee)) || (agents.includes("assistant") ? "assistant" : "");
  useEffect(() => {
    // ...and nor is a hand-off's: on a reply or a coding task, "Use non-coding agent" left blank was refilled with the
    // roster's first role, so a task with no profile showed - and would have started - a researcher (2026-10-15)
    // ...nor with no coding tool connected: every start is the general agent's then, and the coding profile is refused (B3)
    if (agents.length && !agents.includes(run.agent) && !((generalTask || handOff || !canCode) && !run.agent)) setRun((r) => ({ ...r, agent: codingProfile(agents, kinds), model: "" }));
  }, [agents, kinds, run.agent, generalTask, handOff, canCode]);
  useEffect(() => { loadDetail(selected); }, [selected, loadDetail]);
  useEffect(() => {
    const task = detail?.task;
    if (!task || task.TaskId !== selected || !agents.length || pickerTask.current === task.TaskId) return;
    pickerTask.current = task.TaskId;
    setHandOff(false);                  // another task opens on its own question, not the last one's hand-off
    const owned = assignedAgent(task.Assignee);
    // a general task starts from the role it was handed, else blank (its configured profile) - never the roster's first name;
    // a coding task from the profile of kind coding, else blank and the server finds it
    setRun((r) => ({ ...r, agent: agents.includes(owned) ? owned : isGeneralKind(task.Kind) || !canCode ? "" : codingProfile(agents, kinds), model: "" }));
  }, [selected, detail?.task, agents, kinds, canCode]);
  // ...and an error belongs to the task it happened on: a failed Mark done stayed up over the next task opened, as if about it.
  // Only a move from one task straight to another clears it: "That task is gone" empties the selection, and the list then
  // opens its first row - that message must survive the hop.
  const prevSel = useRef(selected);
  useEffect(() => { setRestartOpen(false); if (selected && prevSel.current) setErr(""); prevSel.current = selected; }, [selected]);
  useEffect(() => {
    // a LIVE SESSION counts as much as a headless run here: the header chip is derived from
    // how long the pty has been quiet, so without re-asking it froze on whatever it said
    // when the task was opened - "needs you" over an agent that was mid-thought
    const running = hasRunningRun || sessionAlive;
    if (sessionAlive) sessionSettleUntil.current = Date.now() + 120000;
    const settling = detailTaskStatus === "in_progress" && hasTranscript
      && (hasAgentReport || Date.now() < sessionSettleUntil.current);
    if (!((running || wrapping || settling || writingUp === selected) && selected)) return undefined;

    // Terminal bytes already travel over their own websocket. Turning each output frame into a
    // task + waitroom fetch made switching and typing wait behind the terminal's own repaints.
    // The surrounding lifecycle state only needs a calm check; the terminal remains fully live.
    return pollWhileActive(active, () => loadDetail(selected), 3000);
  }, [active, detailTaskStatus, hasAgentReport, hasRunningRun, hasTranscript, loadDetail, selected, sessionAlive, wrapping, writingUp]);

  // THE MENUS' CHANGES ARE THE TASK TOOLS (Stream B, the owner 2026-10-18: "every act leaves a receipt"): who does it, priority and
  // who holds it run down the operations road, so each is recorded and said in the chat when the task is on the Assistant's table
  const change = async (kind, params) => {
    try { await runOperation(api, kind, selected, params); } catch (e) { setErr(opError(e, "That change didn't go through - pick it again.")); }
    loadDetail(selected); loadTasks(); onChanged?.();
  };
  // Reopen changes the task's status and nothing else: no worker starts until the owner chooses one (PW-217)
  const reopen = async () => {
    try { await runOperation(api, "task.reopen", selected); } catch (e) { setErr(e?.message || "Could not reopen the task"); return; }
    loadDetail(selected); loadTasks(); onChanged?.();
  };
  const queueNote = async () => {
    if (!waitText.trim() || !selected) return;
    try {
      const { data } = await api.post(`/api/tasks/${selected}/waitroom`, { text: waitText });
      setWaitText("");
      setErr(data.delivered ? (data.state === "restarted" ? "The agent picked up again with your note." : "Your note went to the agent.") : "");
      loadDetail(selected);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not send the note - press send again."); }
  };

  const [posting, setPosting] = useState(false);
  const post = async () => {
    if (!comment.trim() || posting) return;
    setPosting(true);
    try { await runOperation(api, "task.comment", selected, { text: comment }); setComment(""); loadDetail(selected); }
    catch (e) { setErr(`Your note wasn't saved - ${opError(e, "Taskuary didn't answer")}. It is still in the box; press Post again.`); }
    finally { setPosting(false); }
  };
  // Finish the AGENT RUN, not the task. It files the durable result, closes this session and drafts
  // the reply to whoever asked (wrapup.wrap -> finish(keep_open=True)); completing the task stays a
  // separate control, because what the work was worth is the owner's verdict and not the run's.
  // THE WRITE-UP RUNS BEHIND THE PRESS (writeup.py, 2026-10-20): the server harvests the session and answers at once; the
  // report lands on the task when the job has written it (the poll below reads it), and a failure is said on the task.
  // ...and the agent is put down AT THE PRESS, Close out opened with the write-up's pending block in it (the owner, 2026-10-21: "it
  // looks frozen"): the harvest the press waits for is the block's first step, not a pause with the pane still up.
  const wrapUp = async () => {
    if (!canWrap && !pressedHere) return;          // ...a write-up that failed here is tried again on the session it left open
    const id = selected, n = (detail?.comments || []).length, sid = term?.sid || pressedHere?.sid || null;
    setErr(""); setWritingUpAt({ id, n, sid }); setTerm(null); setSeekCloseOut(true);
    try {
      const { data } = await api.post(`/api/tasks/${id}/wrap`, { close: false, background: true });
      loadTasks(); onChanged?.();
      if (stale(id)) return;                    // moved on meanwhile: the report is on the task's history
      setWritingUpAt({ id, n, sid, job: data?.job || "?" }); loadDetail(id);   // "?": no job named - the task's notes say when it is done
    } catch (e) {
      if (stale(id)) return;
      setWritingUpAt(null); findTerm(id);      // nothing was written up: the session comes back as it was
      setErr(e?.response?.data?.detail || "Could not save the agent's work - press Stop and save again.");
    }
  };
  // Pausing is not finishing: no report, no reply draft, the task stays open. What it worked
  // out becomes a handover note that gets typed into the NEXT session, because a pty has no
  // resumable id - killing the session used to throw all of that away.
  useEffect(() => {
    setWrapping(false); setWrapped(null);
    // a press on another task is that task's: back on it, a job still writing is read from the server's own word (detail.writeup)
    setWritingUpAt((w) => (w?.id === selected ? w : null));
    setAskSenderOpen(false); setSenderQuestion(""); setAskingSender(false); setOpeningReply(false);
    setOpenStage(null);
  }, [selected]);

  const [handoff, setHandoff] = useState(false);
  const [reshape, setReshape] = useState(false);
  const [repoPick, setRepoPick] = useState(false);
  const [resumeAfterRepo, setResumeAfterRepo] = useState(null);
  // Came from: every message drawn instead of each conversation's ends, and the one message opened in full under its row
  const [showAll, setShowAll] = useState(false);
  const [openMsg, setOpenMsg] = useState(null);
  // Close out's "the whole conversation is in Task" opens step 1 and brings Came from into view - once it has drawn
  const cameFromRef = useRef(null);
  const [seekCameFrom, setSeekCameFrom] = useState(false);
  useEffect(() => {
    if (!seekCameFrom) return;
    cameFromRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    setSeekCameFrom(false);
  }, [seekCameFrom]);
  // the menu the old pills were: { what: "menu" | "kind" | "priority" | "assign", at } - opened from the row or the Tasks tab's bar
  const [pick, setPick] = useState(null);
  // a batch's items start FOLDED to their progress line: with them open, the agent's session - the thing being watched -
  // was pushed below the fold (the owner, 2026-10-13: "the coding agent should be the main view"). One click opens them.
  const [itemsOpen, setItemsOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  useEffect(() => { setHandoff(false); setReshape(false); setRepoPick(false); setResumeAfterRepo(null); setDiffOpen(false); setShowAll(false); setOpenMsg(null); setPick(null); setReportOpen(false); setPeek(false); }, [selected]);
  // asked when the drawer opens, and only then: shelling out to git on every task poll would
  // spend a subprocess a second on an answer nobody is looking at
  // ...in the scope ON SCREEN: with no dependencies this kept the first render's scope, so Refresh always went back to
  // the task view (T19) - and the diff stays up while the new one loads rather than blanking
  const loadDiff = useCallback(async (id) => {
    try { setDiff((await api.get(`/api/tasks/${id}/diff`, { params: { scope: diffScope } })).data); }
    catch (e) { setDiff({ files: [], why: e?.response?.data?.detail || "Could not read the checkout" }); }
  }, [diffScope]);
  useEffect(() => { if (diffOpen && selected) loadDiff(selected); }, [diffOpen, selected, loadDiff]);
  // A fold DROPS the task you were looking at, so follow the work to the survivor - staying
  // put would leave the detail pane on a task that no longer holds anything. On the walk it was put down at the press
  // like every close (2026-10-01), so the walk moves on as after one; the server has already dropped it.
  const reshaped = (r) => {
    loadTasks(); onChanged?.();
    if (r?.dropped !== selected) return loadDetail(selected);
    setReshape(false);
    canvas && onFinish ? onFinish("dropped", async () => {}).catch(() => {}) : onSelect(r.merged);
  };
  // a card asked for one of this page's dialogs (assistantCards Foot TASK_ACTS): open it once the task is the one shown. Remove
  // has no dialog any more (the owner, 2026-10-19: a hover, not a box) - its press removes, from the card as from the row.
  useEffect(() => {
    if (!openAct || openAct.taskId !== selected) return;
    if (openAct.act === "not_a_task") notATask();
    else ({ handoff: setHandoff, reshape: setReshape })[openAct.act]?.(true);
    onActOpened?.();
  }, [openAct, selected, onActOpened]);
  // MARK DONE SAYS IT IS WORKING (the owner, 2026-09-25): the close takes seconds with agents busy, and a button that
  // did nothing visible read as broken; with a live session it also stops an agent, which its hover says
  const [finishing, setFinishing] = useState(false);
  // ...put down AT THE PRESS, as Mark done is: cleared only once the delete returned, the task sat on the rail as an
  // open one already seen - under For later - then left, then its mail came back as the FYI it now is (press audit,
  // 2026-10-01). The FYI is right; the steps between were the flicker. A delete that fails puts it back with the reason.
  const notATask = async () => {
    onLeave?.();
    try { await runOperation(api, "task.not_a_task", selected); }
    catch (e) { const msg = opError(e, "Could not remove the task - it is still here; try Remove again."); setErr(msg); onStay?.(msg); return; }
    onSelect(null); await loadTasks(); onChanged?.();
  };
  // The task's own session - the only terminal in the app. undefined means "not looked
  // yet", null means "looked, none running": the difference decides whether we may
  // auto-start one, so they must not collapse into each other.
  const [term, setTerm] = useState(() => heldTerm(selected));   // the session list read ahead, when it was (taskDetail.js)
  // Wrapping up belongs to the TASK, not to the pty. An exited session is dropped after ten
  // minutes, and with it went the only handle these buttons had - so a task whose CLI had
  // finished on its own could never be closed out. The transcript is filed when a session ends.
  // ...and general work has no transcript at all: the chat IS the record, so a conversation that
  // has answered can be closed out after its provider session is gone (wrapup.py, 2026-09-07).
  const hasGeneralHistory = (detail?.comments || []).some((c) =>
    c.ActorType === "assistant_user" || c.ActorType === "assistant_agent");
  const canWrap = !!term || !!detail?.transcript || hasGeneralHistory;
  const findTerm = useCallback(async (tid) => {
    if (!tid) { setTerm(null); return; }
    try {
      // Selecting a task only needs the session identity/lifecycle. Rich files + witness data is
      // fetched by WorkStrip if the owner opens it; waiting on git here blocked the terminal pane.
      const rows = (await api.get("/api/terminals", { params: { details: false } })).data.data || [];
      keepTerms(rows);
      if (stale(tid)) return;
      // an exited session still holds its scrollback (they stay listed ~10 min), and that
      // transcript is exactly what Done and Pause need - dropping it left a task you could
      // not close out because the CLI had finished on its own
      setTerm(rows.find((x) => x.taskId === tid && x.alive) || rows.find((x) => x.taskId === tid) || null);
    } catch { if (!stale(tid)) setTerm(null); }
  }, []);
  useEffect(() => { setTerm(heldTerm(selected)); findTerm(selected); }, [selected, findTerm]);
  // The task's own detail already carries the live session (it is where sessionAlive is read
  // from), so take it rather than wait for a re-selection to go looking. A session that has
  // ENDED is deliberately not adopted: findTerm keeps the dead one because its scrollback is
  // exactly what Done and Pause need, and `for_task` only ever returns a live one.
  // ...and only THIS task's. Switching tasks clears `term` while `detail` still holds the previous
  // task until its reload lands, so this adopted that task's live session - and nothing cleared it
  // once the new detail arrived without one: a done task showed another task's agent working.
  // ...and the SAME session's new word too: the detail reloads on every task-changed, but only a new sid was adopted, so an agent
  // that asked while the page was open kept its header on "working" and its row without Answer it until the task was opened again (G7)
  const liveWord = sessionWord(detail?.session);
  useEffect(() => {
    const live = detail?.session;
    if (!live?.alive || live.taskId !== selected) return;
    // ...never the session Stop and save is writing up: its pty lives until the report is safe, and adopting it put the agent back
    if (pressedHere?.sid && live.sid === pressedHere.sid) return;
    if (live.sid !== term?.sid) setTerm(live);
    else if (liveWord !== sessionWord(term)) setTerm((was) => (was?.sid === live.sid ? { ...was, ...live } : was));
  }, [detail?.session, term?.sid, selected, liveWord]);   // eslint-disable-line react-hooks/exhaustive-deps
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

  // Closing it is this view's; what comes NEXT is the page around it (TasksView moves to the next live row, the canvas
  // walks on) - `onFinish(status, close)` runs the close itself so the list can pre-record the state it is about to see.
  const finish = async (status, note) => {
    setFinishing(true);
    // PUT DOWN AT THE PRESS (the owner, 2026-10-01: "you hit mark done it closes ... why does it take an extra second or 2?"): the
    // walk folds the task now and the close runs behind the "…"; a close that fails hands it back with the reason
    onLeave?.();
    const close = () => completeTask(api, selected, note);   // the shared road (PW-215), the Wall's Close agent too (closeAgent.jsx)
    try { await (onFinish ? onFinish(status, close) : close()); }
    catch (e) { const msg = e?.response?.data?.detail || e?.message || "Failed to finish task"; setErr(msg); onStay?.(msg); loadTasks(); return msg; }
    finally { setFinishing(false); }
    loadTasks(); onChanged?.();
  };
  // HANDED TO A PERSON: the forward went out and the task now waits on them (server.handoff - forward only, 2026-10-18), so
  // it is off you: the list moves on, the walk brings the next, and the task stays open for its own Mark done
  const handedOff = async () => { setHandoff(false); await closedHere("waiting"); };
  const closedHere = async (status = "done") => {
    try { await (onFinish ? onFinish(status, async () => {}) : loadDetail(selected)); } catch { /* already moved on the server */ }
    loadTasks(); onChanged?.();
  };
  // SENT (Send / Approve): the send already went through, so the task is read again - it stays open (a send never closes it,
  // 2026-10-18) and the page stays on it, its Mark done the move now; closed by something else meanwhile means walk on
  const sent = async () => {
    let done = false;
    try { done = String((await api.get(`/api/tasks/${selected}`)).data?.task?.Status || "") === "done"; } catch { /* read it below */ }
    if (done) { onLeave?.(); return closedHere(); }
    loadDetail(selected); loadTasks(); onChanged?.();
  };
  // Remind me: put away until a day - the page around this view decides where to go next
  const reminded = (out) => { onReminded?.(out); loadTasks(); onChanged?.(); };
  const dismiss = () => onClose?.();
  // The report is identified by its durable marker, not the actor label. Named coding agents
  // appear as coding/claude/codex in the record; requiring ActorType === "agent" hid valid results.
  const report = [...(detail?.comments || [])].reverse().find((c) => {
    const body = String(c.Body || "").trimStart();
    return /^(?:AGENT|CODER) REPORT(?:\r?\n|$)/.test(body) && body.replace(/^(?:AGENT|CODER) REPORT/, "").trim();
  });
  const diffRun = (detail?.runs || []).find((r) => r.DiffText);
  const liveRun = (detail?.runs || []).find((r) => r.Status === "running");
  // TWO QUESTIONS, TWO FLAGS. `liveCodingSession` answered both "is a session live on this page"
  // (so the whole page goes compact and the terminal gets the room) and "is this a coding CLI
  // with a diff to review". A general session is live but not coding, so it failed the test and
  // took the ROOMY block layout: a heading, then a near-empty band with one right-aligned
  // button, then the brain pill under a rule - three stacked rows where a running agent gets one, on
  // the page where space is the whole point (the owner, 2026-09-16: "why is it so tall... you
  // are taking away precious agent space"). Live is live, whoever is working.
  const liveSession = !!term?.alive;
  // No "are you sure" box on a live session (the owner, 2026-10-19: "this should be a hover over the buttons"): the press
  // is the decision, and what it does to the agent is said on the button's hover (markDoneHint).
  const askFinish = () => (liveSession ? stopAndFinish() : finish("done"));
  // MARK DONE ON A LIVE SESSION ends it the way Stop and save does (the owner, 2026-09-29: "make it the same like
  // when you hit stop session"): the terminal goes at once for the write-up's progress line, the result is filed, and
  // only then is the task closed. The close used to kill the pty with no write-up while the terminal stayed on screen
  // for the whole request. No reply is drafted - the close dismisses drafts - and a write-up that fails still closes.
  const stopAndFinish = async () => {
    const id = selected;
    // ...and it is put down at the press like any close: the write-up below takes as long as the AI does (18 s on
    // 2026-10-01), and the task sat open on the page and the rail all that time - under For later, already seen
    onLeave?.();
    // ...and the write-up runs on the server, which closes the task after it (writeup.py, 2026-10-20): the press is answered once
    // the session is harvested, and the page walks on. A write-up that cannot start closes the task here, as before.
    if (canWrap && await writeUpThenClose(api, id)) {
      if (stale(id)) return;
      setTerm(null);
      return closedHere("done");
    }
    await finish("done");
  };
  // what Mark done does HERE - it said "ends the live agent session" with no session in sight (T11), and a waiting
  // draft is kept on the task, never thrown away: it can be brought back and sent later
  const markDoneHint = ["Closes the task", liveSession ? "and stops the agent - what it did so far is written up and saved with the task first" : "",
    pendingReplyReview(detail?.reviews || []) ? "- your draft stays on it, to send later if you want" : ""].filter(Boolean).join(" ") + ".";
  // what fills the page: the session, unless the owner stepped back to the task behind it (peek)
  const sessionView = liveSession && !peek;
  // ...and a stage you opened by hand does not outlive the session you opened it on. The agent
  // finishes, its wrap-up writes the reply (wrapup.wrap), and the page went on showing the closed
  // pane with that draft folded away below (the owner, 2026-09-22: "when you hit session closed a
  // reply should automatically pop up"). Cleared, focusStage picks - and a draft ready outranks all.
  useEffect(() => { if (!liveSession) { setPeek(false); setOpenStage(null); } }, [liveSession]);
  const liveCodingSession = !isGeneral && liveSession;
  // Proposals are queued after the reply, so they must not be mistaken for it - but they SHARE
  // its stage. lanes.json has one lane for both ("a reply or an action is drafted and waits for
  // your yes"), and one lane on the rail is one section on the page (the owner, 2026-09-22: "put
  // playbook proposal combined into the reply ready section as it's part of the approval/action").
  const pendingReview = pendingReplyReview(detail?.reviews || []);
  const allProposals = pendingProposals(detail?.reviews || []);
  // the task's close-out beside its reply is ONE decision on the reply's card; alone, it is its own card below
  const closeoutRv = allProposals.find((p) => closeoutOf(p)) || null;
  const proposals = allProposals.filter((p) => !(pendingReview && p === closeoutRv));
  const sentReview = sentReplyReview(detail?.reviews || []);
  const unsentReview = sentReview ? null : unsentReplyReview(detail?.reviews || []);
  // the agent's record, drawn once, on the Agent work step
  const recordProps = { taskId: selected, pages: isGeneral ? [] : (detail?.artifacts || []).filter((a) => isPublished(a) || a.kind === "shown"),
    draft: (() => { const r = pendingReview || unsentReview || sentReview; return r ? r.FinalText || r.DraftText || "" : ""; })(),
    stamp: `${(detail?.comments || []).length}-${detail?.transcript?.at || ""}-${(detail?.artifacts || []).length}` };
  // ...and what already went out, so Close out says it instead of offering an empty letter: the ending upstream (a merge, a
  // close) and what you - or an agent under your login - sent outside Taskuary (the owner, 2026-10-12: "if agent already
  // sent message show what it sent")
  const ended = detail?.ended || null;
  const sentOutside = sentElsewhere(detail?.messages || [], detail?.reviews || []);
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
  const sourceMessage = replySource(storedMessages);
  // ...and whether there is anybody at the other end of it (taskLifecycle.hasCorrespondent). Every
  // reply door hangs off this, so a task you typed yourself offers no reply to write.
  // a BATCH owes nobody one reply: its items are four authors, each answered (or merged, or closed) on its own line (batch.py)
  const replyMessage = !detail?.batch && hasCorrespondent(sourceMessage) ? sourceMessage : null;
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
      await runOperation(api, "task.clarify", id, { text, message_id: sourceMessage.MessageId });
      if (stale(id)) return;
      setAskSenderOpen(false); setSenderQuestion("");
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) setErr(opError(e, "Could not prepare the question for the sender"));
    } finally { if (!stale(id)) setAskingSender(false); }
  };
  const openReply = async (generate = false) => {
    if (!replyMessage?.MessageId || openingReply) return;
    const id = selected;
    setOpeningReply(generate ? "generate" : "write"); setErr("");
    try {
      // the box at once and the AI's draft behind it, "Drafting…" in the decision meanwhile (replyDraft.js, 2026-10-01)
      await (generate ? draftReply(api, replyMessage.MessageId) : api.post(`/api/messages/${replyMessage.MessageId}/reply`, { draft: false }));
      if (stale(id)) return;
      await loadDetail(id);
      onChanged?.();
    } catch (e) { if (!stale(id)) setErr(e?.response?.data?.detail || "Could not open the reply"); }
    if (!stale(id)) setOpeningReply(false);
  };
  // The task itself leads when no coding terminal is open. Triage already distilled an inbound
  // item into Title + Summary; falling back to its newest inbound body keeps older/promoted rows
  // equally useful. This is the human TODO, not an agent-launch advertisement.
  // ...except where Summary is Taskuary's own brief to the agent (a playbook built with AI: the setup instructions and the example
  // email's raw record - ownwork.BRIEFED): its title is the ask, and the owner's words are in the conversation
  const taskAsk = cleanText(t?.SourceRef === "assistant:playbook" ? t?.Title : t?.Summary || sourceMessage?.BodyText || "");
  // WHAT THEY ACTUALLY SAID. A task opens on one message and then keeps collecting the rest of
  // the conversation - three WhatsApp voice notes seconds apart are one thought, and ingest
  // attaches the later ones to the same task. The panel showed the FIRST and nothing else, so a
  // task whose answer arrived in message three read as an unanswered question (owner, 2026-09-02).
  const inbound = storedMessages.filter((m) => m.Status !== "context" && m.Direction !== "out");
  const completionIsManual = ownerControlsCompletion(t);
  const interruptedTask = String(t?.Tags || "").split(/[\s,]+/).includes("interrupted");
  const taskState = taskPhase(t?.Status);
  // the triage verdict behind THIS task - the header's pills and Came from's last line. The reply source is the NEWEST message, and
  // a message that only joined the task is routed "same conversation thread", which decides nothing: then the route that made the
  // task speaks - the first one with a verdict or an intent in it.
  const judged = (r) => !!(r?.VerdictJson || routeIntent(r?.Reason) || r?.Decision === "create");
  const sourceRoute = (detail?.routes || []).find((r) => r.MessageId === sourceMessage?.MessageId && judged(r))
    || (detail?.routes || []).find(judged);
  const verdict = parseTriageVerdict(sourceRoute) || latestTriageVerdict(detail?.routes || [])
    || legacyTriageVerdict({ routes: detail?.routes || [], task: t || {}, checklist: detail?.checklist || [] });
  const facts = headerFacts({ verdict, route: sourceRoute, task: t || {}, workflow: detail?.workflow });
  // ...and a WORKFLOW RUN came from its workflow, not a message: which one, and what started it (workflows.of_task)
  const fromWorkflow = workflowOrigin(t || {}, detail?.workflow);
  // CAME FROM: the task's messages as the conversations they are, each its first message and its latest two (taskSources.js)
  const sources = groupConversations(storedMessages, { ms: tsMs, clean: cleanText });
  const sourceCount = sources.reduce((n, g) => n + g.count, 0);
  // ...and what they SENT with each message - the photo or screenshot is often the whole ask (the owner, 2026-09-30: "don't see the
  // image on the task incoming message") - drawn under its own row inside the thread; a mail that names a picture it does not
  // carry offers the fetch on the message that opened the task
  const sourceFiles = filesByMessage(detail?.attachments);
  const fetchFor = inbound[0]?.Channel === "email" && mentionsPicture(inbound[0].BodyText) ? inbound[0].MessageId : null;
  // CLOSE OUT'S CONVERSATION is the one being answered - the reply source's - condensed, newest first; never a batch's four authors
  const closeGroup = detail?.batch || !inbound.length ? null
    : sources.find((g) => g.msgs.some((m) => m.MessageId === sourceMessage?.MessageId)) || sources[0] || null;
  // ...and what you sent outside Taskuary in some OTHER conversation still says so under it, newest first
  const sentApart = newestFirst(sentOutside.filter((m) => !closeGroup?.msgs.some((x) => x.MessageId === m.MessageId)));
  const seeWholeConversation = () => { setShowAll(true); setOpenStage("task"); setSeekCameFrom(true); };
  const triaged = triageLine({ route: sourceRoute, verdict, task: t || {}, messages: storedMessages, ms: tsMs });
  // THE ASK: the task's summary, else what triage summed it up as, else the message itself - its first sentence, on one line
  // ...and with no summary, the message that OPENED it: the newest is often "and by the 15th", which is not the ask
  const opener = [...inbound].sort((a, b) => tsMs(a.SentAt) - tsMs(b.SentAt))[0];
  // THE ASK IS TRIAGE'S SUMMARY, whole (the owner, 2026-10-16: "the ask should be the triage summary") - its first sentence alone
  // read as the sender's voice ("Assistant for Backend Monitoring flags…") with the point cut off
  // ...never Taskuary's own brief to the agent (ownwork.BRIEFED: a playbook built with AI) - its title is the ask (taskAsk)
  const askText = (t?.SourceRef === "assistant:playbook" ? "" : cleanText(verdict?.summary || t?.Summary || opener?.ReadText || opener?.BodyText || "")) || taskAsk;
  const made = t ? madeLine(t, timeAgo(t.CreatedAt)) : "";   // "sorted 1m ago", never "created ... by triage" (taskSources.madeLine)
  // WHAT RUNS THIS, in the vocabulary the brain layer landed on 2026-09-16: a ROLE picks the
  // document (every coding task's role is the profile of kind coding), a BRAIN is the CLI that runs it, and the model
  // is the brain's - it is not a property of the task, so the card does not offer one. A live
  // session names the CLI it was ASKED to run; otherwise the roster says which brain the role uses.
  const runRole = assignedAgent(t?.Assignee) || (t?.Kind === "coding" ? codingProfile(agents, kinds) : "");
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
  // the AI writes the draft inside the request (server.open_reply), which can take a while: both buttons spin and say
  // "Drafting…" until it lands (the owner, 2026-09-24: "it should say spinning as it's waiting on ai to draft reply")
  // ONE NAME (buttons.json): "Write reply", "Open the draft" and "Write another" were three names for the one Reply
  const replyPrimary = labelOfRow("reply");
  // A TICK DRAWS AT THE CLICK (the owner, 2026-10-20: about a second to respond): the box waited on three round trips in a row - the
  // operation, its execute, and the task read again - before it moved. Now the press shows at once and the server's answer settles it:
  // the read that follows replaces the guess, and a refusal puts the box back with the reason. Presses run in order, one at a time,
  // so two quick ticks land as two and in the order they were made.
  const [ticks, setTicks] = useState({});
  const tickChain = useRef(Promise.resolve());
  useEffect(() => { setTicks({}); }, [selected]);
  const checklist = withTicks(detail?.checklist, ticks);
  // what the To do list shows: the emails a task owes are Close out's, not boxes to tick here
  const todo = checklist.filter((i) => !i.out);
  // the to-do being noted, and its words while the field is open (checklist.js saveNote; '' takes the note off)
  const [noting, setNoting] = useState(null), [noteText, setNoteText] = useState("");
  const putNote = async (i, text) => {
    if (noting !== i.id) return;
    setNoting(null);
    if (String(text || "").trim() === noteOf(i)) return;
    try { await saveNote(api, t.TaskId, i.id, text); loadDetail(t.TaskId); }
    catch (e) { setErr(`That note didn't save - ${opError(e, "Taskuary didn't answer")}. Write it again.`); }
  };
  const tickItem = (i) => {
    const tid = t.TaskId, done = !i.done, item = String(checklist.indexOf(i) + 1);
    setTicks((m) => ({ ...m, [i.id]: done }));
    const settle = () => setTicks((m) => settleTick(m, i.id, done));
    tickChain.current = tickChain.current.then(async () => {
      try {
        const data = await runOperation(api, "task.check", tid, { item, id: i.id, done });
        await loadDetail(tid);
        // the last tick closed it (server: tick_checklist): the list and the rail move with it now,
        // not on the next poll, or the row you just finished sits there looking open
        if (data?.closed) { loadTasks(); onChanged?.(); }
      } catch (e) { setErr(`That box didn't change - ${opError(e, "Taskuary didn't answer")}. Tick it again.`); }
      settle();
    });
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
  // ...but a general agent's open card already has its composer under the bar, and what you type there continues the same
  // conversation (/assistant) - a second door to one room (the owner, 2026-09-29: "why do we need continue session if
  // it's still open?"). A coding agent keeps it: that button reopens its own CLI session, which nothing else here does.
  const barContinue = barContinues({ canContinue, isGeneral, ended: detail?.runEnded });   // ...and a general run that ended under it
  // STOP AND SAVE ONLY WHILE THERE IS SOMETHING TO STOP (owner-approved, 2026-10-20): it stood on the row of an agent that was
  // already stopped (G7), and then of one that had failed, finished or been cut off by a restart. A session that has ENDED offers
  // what applies - Continue, Run another, Mark done, the write-up's own actions - and the live row keeps its Stop and save.
  const agentBar = !term?.alive && !restartOpen && (isGeneral ? generalStarted : !!(report || detail?.transcript));
  // the list's row for this task carries the server's state (taskstate.py): the page reads the same verdict
  const rowState = listRow?.State;
  const answered = generalAnswered(isGeneral, term);
  const agentState = agentPhase({
    session: term?.alive ? { ...term, waiting: answered || isWaiting(term) } : null,
    run: liveRun, transcript: detail?.transcript, report,
    conversation: generalStarted, finished: rowState === "agentdone", state: rowState,
    handed: !!assignedAgent(t?.Assignee) || rowState === "queued" || !!detail?.transcript || !!report || generalStarted,
  });
  // a sender wrote again after the agent's last session (funnel.news_since_agent): the task stage leads with that message
  const news = !term?.alive && detail?.agentStory?.kind === "news" ? detail.agentStory : null;
  // why nothing is running on the agent step - never started, or what it did before it went (funnel.agent_story)
  const story = storyShown(detail?.agentStory, { alive: term?.alive, liveRun, queued: rowState === "queued",
    closed: ["done", "dropped"].includes(t?.Status) }) ? detail.agentStory : null;
  // a record to show: the step draws the story INTO it (its sentence first, its timeline behind the record's More), never beside it
  const hasRecord = !!(report || detail?.transcript || (isGeneral && generalStarted)
    || (detail?.artifacts || []).some((a) => (isPublished(a) && !isGeneral) || a.kind === "agent_result"));
  const workspaceMode = agentWorkspaceMode({ isGeneral, generalStarted, session: term, wrapping });
  const replyState = replyPhase(detail?.reviews || []);
  // ONE question per page. A running session is itself the agent stage, so it is never folded; the
  // hand-picked stage wins over the computed one until you leave the task (start an agent on a task
  // whose draft is waiting, or answer a sender the agent is still working for).
  // ...and stepping back from a live session (peek) opens the TASK stage: the point of the step was
  // to read what the task is and where it came from, and that lives on the task card, not folded
  // to a strip under a heading that says the agent is working.
  const emailsWaiting = waitingEmails(detail?.checklist, detail?.reviews);
  const owesEmails = (detail?.checklist || []).some((i) => i.out && !i.done);
  // A RUN OF STEPS WITH NO AGENT STEP (workflows.of_task by_code): code ran it, so there is no Agent work to open - the steps are on
  // the task, under where it came from. A session that did start (an older run, a hand-started agent) still shows.
  const codeRun = !!fromWorkflow?.byCode && !term?.alive && !generalStarted && !detail?.transcript && !report;
  // ...and Stop and save pressed here holds Close out open - writing, failed or drafted - so the draft replaces the pending block where
  // it stood, never a jump to whichever step the computed focus picks once the job is done
  const stage = sessionView ? "agent" : (openStage || (pressedHere || writeup ? "reply" : peek ? "task" : focusStage({
    kind: t?.Kind, task: taskState, agent: codeRun ? null : agentState, reply: replyState, hasSender: !!replyMessage,
    // what the agent is parked ON decides whether the proposal or the agent opens: an agent
    // waiting for approval is released by the very proposal sitting in stage 3
    proposal: proposals.length > 0, agentSub: term ? subState(term) : null, news: !!news,
    emails: emailsWaiting, record: hasRecord, out: wentOut(detail?.reviews),
  })));
  // the note a close was written with (server task.complete: "Closed out: ...") - Close out shows it under the close
  const closedNote = String([...(detail?.comments || [])].reverse().find((c) => /^Closed out: /.test(String(c.Body || "")))?.Body || "").replace(/^Closed out: /, "");
  // the news line is said once, at the top of the task stage; open, the agent step is just its record
  const storyAt = storyPlace(news ? null : story, { open: stage === "agent" && !sessionView, hasRecord });
  // A START THAT STOPPED ON "WHICH REPOSITORY?" (funnel.HELD_REPO): the chip says so and the pick resumes the start, whichever
  // chip you press (the owner, 2026-10-12: "if i don't fill it out it should warn me at least?")
  const heldRepo = String(t?.Tags || "").split(/[\s,]+/).includes("held:repo");
  const pickRepo = () => { setRepoPick(true); if (heldRepo) setResumeAfterRepo({ dispatch: true }); };
  // only a folded heading is a control: exactly one stage is open, so clicking the open one has
  // nothing to do and must not offer a chevron that does nothing.
  const stageProps = (name) => ({ folded: stage !== name, onToggle: stage === name ? null : () => setOpenStage(name) });
  const startCodingAgent = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("coding"); setErr(""); setStartFail(null);
    try {
      // the repository chosen in the panel is pinned first - the tag is the override the start obeys
      if (startRepo) await api.put(`/api/tasks/${id}/repo`, { repo: startRepo, ...(run.agent ? { agent: run.agent } : {}) });
      // ANOTHER AGENT WHILE ONE RUNS (Run another agent): the live one is paused first - its handover is filed for the next
      // session, no report and no reply draft - since the dispatch refuses a second worker on a task (409)
      if (term?.alive) { await api.post(`/api/tasks/${id}/pause`, {}); if (!stale(id)) setTerm(null); }
      // one shared dispatch for coding too (PW-216): the kind switch, the live-worker check (409), the unknown
      // agent (422) and the repository come from the same road the general button and the assistant use -
      // no Kind PATCH before a terminal, so a failed start never leaves a relabelled, unstarted task
      const data = await runOperation(api, "dispatch.prepare", id, { kind: "coding", agent: run.agent || null, brain: run.brain || null,
        model: run.model || null, instructions: withImages(run.instruction.trim(), runPics.paths) || null });
      if (!stale(id)) setTerm(data?.session || null);
      if (!stale(id)) {
        setRun((current) => ({ ...current, instruction: "" })); runPics.clear();
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
      } else { setErr(msg); setStartFail({ ...failOf(e), text: msg, again: startCodingAgent }); }
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  const startGeneralAgent = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("general"); setErr(""); setStartFail(null);
    try {
      // one shared dispatch whatever the task's kind was: it switches the kind, starts (or reuses) the
      // assistant session and records the live worker - a relabelled task is not a started one (PW-213)
      // profile, brain and model - whichever of them was chosen; blank means "as configured"
      const { data } = await api.post(`/api/tasks/${id}/dispatch`,
        { kind: "general", agent: run.agent || null, pick: run.pick || null, model: run.model || null,
          // what was typed in the box goes to it - this sent the pickers and dropped the words
          instruction: withImages(run.instruction.trim(), runPics.paths) || null });
      const outcome = outcomeOf(data);
      if (!stale(id)) setTerm(outcome.state === "started" || outcome.state === "existing" ? (data.session || null) : null);
      // where the code is, still to say: the same question the coding start asks - it came back quietly and nothing opened
      if (!stale(id) && outcome.state === "needs_repo") { setRepoPick(true); setResumeAfterRepo({ dispatch: true }); }
      if (!stale(id)) { setRun((current) => ({ ...current, instruction: "" })); runPics.clear(); setRestartOpen(false); }
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
    } catch (e) {
      if (!stale(id)) {
        const msg = e?.response?.data?.detail || "Could not start the agent - check that an AI is connected under Connections, then press it again.";
        setErr(msg); setStartFail({ ...failOf(e), text: msg, again: startGeneralAgent });
      }
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  // START AN AGENT ON A GOAL (the owner, 2026-10-12): the goal is up to its first step not done. That step becomes a task
  // of its own if it is not one yet (the goal's repository rides along), the regular agent starts on it through the one
  // dispatch door, and the step opens on the table so what the agent does is what you see.
  const startGoalStep = async () => {
    if (!selected || startingAgent) return;
    const id = selected;
    setStartingAgent("step"); setErr(""); setStartFail(null);
    try {
      const { data: got } = await api.get(`/api/tasks/${id}/steps`);
      const step = (got.steps || []).find((s) => !s.done);
      if (!step) { setErr("Every step is done - close the goal, or add a step."); return; }
      const child = step.tid || (await api.post(`/api/tasks/${id}/steps/${step.id}/start`)).data.taskId;
      // `via`: the press was made HERE, so a start that fails is left on the goal, where its line is read (server._pressed_on)
      const { data } = await api.post(`/api/tasks/${child}/dispatch`, { kind: "general", agent: run.agent || null, pick: run.pick || null, model: run.model || null, via: id });
      const outcome = outcomeOf(data);
      if (outcome.state === "needs_repo") setErr(`${outcome.text} - open the step and pick one.`);
      await Promise.all([loadDetail(id), loadTasks()]);
      onChanged?.();
      (onOpenTask || onSelect)?.(child);
    } catch (e) {
      // ...with its ways past it as buttons on the error, as the task's own start has: the sentence stood alone (the matrix's verify, 2026-10-20)
      if (!stale(id)) { const msg = e?.response?.data?.detail || "Could not start the agent on the next step"; setErr(msg); setStartFail({ ...failOf(e), text: msg, again: startGoalStep }); }
    } finally { if (!stale(id)) setStartingAgent(""); }
  };
  // CONTINUE SESSION is the rail's box here too (T14): one road (/continue-work) for a coding and a regular agent, and
  // what you type is the first thing it hears. The page had two older roads with no note (continue-session, resume).
  const [continueAt, setContinueAtRaw] = useState(null);
  // on the canvas Continue is a card IN the conversation (AssistantView listens), not a popover over the view
  const setContinueAt = (a) => {
    if (a) setRestartOpen(false);                 // one card under the conversation at a time
    if (a && canvas && t) { window.dispatchEvent(new CustomEvent("tq-continue", { detail: { task: t, ref: t.ref || `TQ-${String(t.TaskId).padStart(4, "0")}` } })); return; }
    setContinueAtRaw(a);
  };
  // CLOSE WITH A NOTE rides the same way: a card in the conversation on the canvas, a popover elsewhere, and the close is
  // this view's own Mark done (finish), so the walk puts the task down exactly as it does for the button
  const [noteAt, setNoteAtRaw] = useState(null);
  const closeWithNote = async (note) => { const failed = await finish("done", note); if (failed) throw new Error(failed); };
  const setNoteAt = (a) => {
    if (a) setRestartOpen(false);
    if (a && canvas && t) { window.dispatchEvent(new CustomEvent("tq-close-note", { detail: { task: t, ref: t.ref || `TQ-${String(t.TaskId).padStart(4, "0")}`, close: closeWithNote } })); return; }
    setNoteAtRaw(a);
  };
  const noteable = !!t && !term?.alive && !["done", "dropped"].includes(String(t?.Status || ""));
  const continued = () => {
    const id = selected;
    if (!stale(id)) setGeneralRevision((n) => n + 1);
    Promise.all([loadDetail(id), loadTasks()]).then(() => onChanged?.());
  };
  // THE BAR THE AGENT CARD ACTS THROUGH, built here so it can ride inside the heading beside the
  // chip - where the Task and Reply strips keep theirs. Group one is THIS session, group two is
  // another one, and exactly one move is filled. It is an element, not a component: the handlers
  // it calls are declared just above, and a component defined mid-render remounts on every keystroke.
  const agentBarRow = (
    <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
      {barContinue && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent} sx={primaryBtn}
        startIcon={startingAgent === "resume" ? <CircularProgress size={12} /> : <HistoryIcon sx={{ fontSize: 16 }} />}
        title={isGeneral
          ? "Reopens the saved provider conversation and continues from its existing context."
          : `Reopens ${detail?.resumable?.agent}'s own session in ${detail?.resumable?.cwd}. It still has what it read, changed and asked.`}
        onClick={(e) => setContinueAt(e.currentTarget)}>
        {startingAgent === "resume" ? "Continuing…" : labelOfRow("continue")}</Button>}
      {!isGeneral && <>
        {canContinue && <Divider orientation="vertical" flexItem sx={{ mx: 0.4, my: 0.6, borderColor: BORDER }} />}
        <Button size="small" variant={canContinue ? "outlined" : "contained"} disableElevation
          sx={canContinue ? barBtn : primaryBtn}
          startIcon={<RefreshIcon sx={{ fontSize: 16, color: canContinue ? "#6f8a6e" : undefined }} />}
          title="A fresh agent, with new instructions if you want. It gets what the last one saved, not its whole conversation."
          onClick={() => setRestartOpen(true)}>{labelOfRow("run-another")}</Button>
      </>}
    </Box>
  );
  // ON THE ASSISTANT CANVAS THE BUTTONS LEAVE THE CARD (layout B, 2026-09-30): the item registers its verbs and the ONE row above the chat
  // line draws them (ActionRow) - the decision first, the session's verbs next, the rest behind More, Next at the end. They are
  // THESE handlers, unchanged: the row calls the latest closure, so a press costs what the old button cost. The Tasks tab
  // (canvas=false) keeps its bars.
  const inRow = !!canvas;
  // AN AGENT WAITING ON YOU is answered in its own terminal - the owner talks to the coding CLI directly. Its question is never drawn
  // OVER the screen (the owner, 2026-10-19: "never get between a coder and their coding cli ... you have to click show details anyway
  // to move on"), and there is no "Answer it" on the row (owner-approved, 2026-10-20: "we don't need that button") - the pane is right
  // above it, and the button was the lit one over a finished agent whose reply waited on the owner's approval.
  const termBox = useRef(null);
  // THE AGENT'S CHAT OPENS PUSHED UP (the owner, 2026-10-18: "you can almost never see the full output text ... push it up higher
  // on screen"): on the canvas the folded Task strip scrolls above the view, so "2 Agent work" sits under the title and the chat
  // fills the rest (its box is sized for exactly that, below). Task is one scroll up, Close out one scroll down.
  const stepsBox = useRef(null), agentHead = useRef(null);
  // ON THE CANVAS THE CHAT'S OWN STRIP RIDES IN THIS STEP'S HEADING: a row for "Agent work" and a second for the agent's name, its
  // brain and Full screen took two lines off the answer (the owner, 2026-10-18: "make the agent space take up more space")
  const [chatTools, setChatTools] = useState(null);
  const agentUp = !!canvas && stage === "agent" && workspaceMode === "general" && !liveSession;
  useEffect(() => {
    // ...and back down when another step opens: Task opened from there kept the scroll, its own heading out of sight
    if (!agentUp) { if (canvas && stepsBox.current) stepsBox.current.scrollTop = 0; return undefined; }
    const f = requestAnimationFrame(() => {
      const s = stepsBox.current, h = agentHead.current;
      if (s && h) s.scrollTop += h.getBoundingClientRect().top - s.getBoundingClientRect().top;
    });
    return () => cancelAnimationFrame(f);
  }, [agentUp, t?.TaskId]);
  // THE ADVISOR ON THE TASKS TAB (U12): the canvas reads it for the item on its table; this view, standing alone, reads its own
  const [taskAdvice, setTaskAdvice] = useState(null);
  const readTaskAdvice = useCallback((id) => {
    if (!id) { setTaskAdvice(null); return; }
    api.get("/api/advice", { params: { key: `task:${id}` } })
      .then(({ data }) => { if (!stale(id)) setTaskAdvice(data?.verb && data.line ? data : null); })
      .catch(() => { if (!stale(id)) setTaskAdvice(null); });
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (canvas || !active) return; setTaskAdvice(null); readTaskAdvice(selected); }, [canvas, active, selected, readTaskAdvice]);
  useEffect(() => { if (!canvas && active && t?.UpdatedAt) readTaskAdvice(selected); }, [t?.UpdatedAt]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => (canvas || !active ? undefined
    : onLive("advice", (ev) => { if (adviceKeyFor(ev, `task:${selRef.current}`)) readTaskAdvice(selRef.current); })), [canvas, active, readTaskAdvice]);
  // ...and after every press on it: an act moves the item's revision, and the line judged before it must not stand (2026-10-19)
  useEffect(() => (canvas || !active ? undefined : onPressed(() => readTaskAdvice(selRef.current))), [canvas, active, readTaskAdvice]);
  const [remindAt, setRemindAt] = useState(null);
  const notDone = !!t && !["done", "dropped"].includes(t.Status);
  // THE CALENDAR'S ANSWERS (calwrite.py, server task_detail's `calendar`): an invite waiting on the owner is answered from the row -
  // Accept, Decline, Propose a new time - and a thread asking for a time offers Find a time. Each DRAFTS into Close out for the
  // owner's Send; a card that may not write says so on the error line with its sign-in as the way out (failures.py's fix).
  const calAsk = notDone && !liveSession ? detail?.calendar || null : null;
  const [slotAt, setSlotAt] = useState(null);           // { act, at } - Propose a new time / Find a time's free times
  const calAnswer = async (act, slot = null) => {
    if (!calAsk) return;
    setErr(""); setStartFail(null);
    try {
      const { data } = await api.post(`/api/messages/${calAsk.mid}/calendar`, { act, ...(slot || {}) });
      if (!data?.ok) { setErr(data?.say || "That could not be drafted."); setStartFail({ text: data?.say || "", fix: data?.fix || null, retry: false }); return; }
      setOpenStage("reply"); loadDetail(selected); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "That could not be drafted."); }
  };
  const calVerbs = !calAsk ? [] : calAsk.invite ? [
    { id: "accept_invite", group: "decide", tone: "s", label: btn("accept_invite"), run: () => calAnswer("accept"), title: btnHint("accept_invite") },
    { id: "decline_invite", group: "decide", tone: "s", label: btn("decline_invite"), run: () => calAnswer("decline"), title: btnHint("decline_invite") },
    { id: "propose_time", group: "decide", tone: "s", label: btn("propose_time"), run: (e, a) => setSlotAt({ act: "propose", at: a || e?.currentTarget || document.body }), title: btnHint("propose_time") },
  ] : [{ id: "find_time", group: "decide", tone: "s", label: btn("find_time"), run: (e, a) => setSlotAt({ act: "schedule", at: a || e?.currentTarget || document.body }), title: btnHint("find_time") }];
  // the task's own controls ride in the header strip only while a session hides the task card - and never on the canvas,
  // whose row holds them
  const headControls = sessionView && !inRow && notDone;
  const continueHere = !liveSession && notDone && (barContinue || (stage !== "agent" && canContinue));
  const sendGeneral = isGeneral && !generalStarted && notDone && !liveSession;
  const startHere = !liveSession && notDone && !continueHere && !sendGeneral && (stage !== "agent" || (agentBar && !isGeneral));
  const ranBefore = !!(report || detail?.transcript);
  // RUN ANOTHER AGENT, on the bar and for any task an agent has worked (the owner, 2026-10-05: "don't see run another agent under
  // more? it should be not in more"). It was offered only behind More, only on a coding task, only once its session had ended -
  // so a general task could never be handed to the coding agent from here. It opens the agent step; a live session is paused
  // (its handover kept for the next) when the new one starts (startCodingAgent).
  const runAnother = { id: "run-another", group: "agent", label: labelOfRow("run-another"),
    run: () => { if (canvas) window.dispatchEvent(new CustomEvent("tq-next-run")); else setOpenStage("agent"); setRestartOpen(true); },
    title: hintOfRow("run-another") };
  const changeVerbs = !notDone ? [] : [
    { id: "kind", group: "more", label: labelOfRow("kind"), run: (e, a) => setPick({ what: "kind", at: a || e?.currentTarget }), title: hintOfRow("kind") },
    { id: "priority", group: "more", label: labelOfRow("priority"), run: (e, a) => setPick({ what: "priority", at: a || e?.currentTarget }), title: hintOfRow("priority") },
    { id: "assign", group: "more", label: labelOfRow("assign"), run: (e, a) => setPick({ what: "assign", at: a || e?.currentTarget }), title: hintOfRow("assign") },
    // a repository is a coding tool's question: with none connected there is nothing to pick one for (B3)
    // ...and a start HELD for it is the row's own move, not a More item: "It needs a repository" sat over a row with nothing to press
    ...(heldRepo || (!isGeneral && canCode) ? [{ id: "repo", group: heldRepo ? "decide" : "more", tone: heldRepo ? "p" : undefined, label: btn("pick_repo", repoOf(t) ? "set" : null), run: pickRepo,
      title: heldRepo ? "Not started: it needs to know where the code is - it starts once you choose" : btnHint("pick_repo") }] : []),
  ];
  // ...and DARK while the agent is running (the owner, 2026-10-20): not over a turn that finished or a question - those are waiting
  const stopSave = { id: "save-end", group: "agent", lead: !pendingReview, fill: liveSession && agentState === AGENT.working && !pendingReview, label: labelOfRow("save-end"), disabled: !!wrapping, run: wrapUp, title: hintOfRow("save-end") };
  const rowVerbs = !t ? [] : !notDone
    ? [{ id: "reopen", group: "decide", tone: "s", label: labelOfRow("reopen"), run: reopen, title: hintOfRow("reopen") }]
    : [
      ...calVerbs,
      // ...an invite is answered by the calendar, not by an email back (calwrite.py)
      ...(replyMessage && !liveSession && !calAsk?.invite && (stage !== "reply" || !pendingReview) ? [{ id: "reply", group: "decide", tone: "p", label: openingReply ? "Drafting…" : replyPrimary,
        disabled: !!openingReply, run: () => (pendingReview ? setOpenStage("reply") : openReply(true)), title: hintOfRow("reply") }] : []),
      // done off the app - a call - closes with what came of it: the card opens in the conversation, under the item. It is Mark
      // done with words, so it registers with Mark done and the row stands it beside that (actionRow.rowOf)
      ...(noteable && !liveSession ? [{ id: "close-note", group: "more", label: labelOfRow("close-note"), run: (e, a) => setNoteAt(a || e?.currentTarget),
        title: hintOfRow("close-note") }] : []),
      ...(liveSession ? [
        // STOP AND SAVE LEADS A LIVE SESSION'S ROW (owner-approved, 2026-10-20) - working, or idle after its turn, or asking: it stands
        // where Answer it stood. A reply waiting on the owner's approval leads instead (its Send, under the draft), and this one stays
        // in the agent's group beside Review changes
        ...(!pendingReview ? [stopSave] : []),
        ...(liveCodingSession ? [{ id: "diff", group: "agent", label: labelOfRow("diff"), run: () => setDiffOpen(true), title: hintOfRow("diff") }] : []),
        ...(pendingReview ? [stopSave] : []),
        ...(notDone ? [runAnother] : []),
      ] : continueHere ? [{ id: "continue", group: "agent", lead: !pendingReview, label: startingAgent === "resume" ? "Continuing…" : labelOfRow("continue"), disabled: !!startingAgent,
        run: (e, a) => setContinueAt(a || e?.currentTarget), title: hintOfRow("continue") }]
      : sendGeneral ? [{ id: "send-general", group: "agent", lead: !pendingReview, label: startingAgent === "general" ? "Starting…" : labelOfRow("send-general"),
        disabled: !!startingAgent, run: startGeneralAgent,
        // ON THE BAR, not in the Agent work card (the owner, 2026-10-05: "send to agent on general task should be on bottom not inline");
        // the profile, brain and model pickers stay in that card for whoever wants to change them first
        title: hintOfRow("send-general") }]
      // ON A GOAL the agent starts on the step the goal is up to - the first box not done: its child, made if it has none - and
      // that step opens on the table (the owner, 2026-10-12: "it should start an agent on what it's up to")
      : startHere && t?.DoneWhen ? [{ id: "start-agent", group: "agent", lead: !pendingReview, label: startingAgent === "step" ? "Starting…" : labelOfRow("start-agent"),
        disabled: !!startingAgent, run: startGoalStep, title: hintOfRow("start-agent") }]
      // WITH NO CODING TOOL CONNECTED the general agent is simply THE agent (B3): Send to agent starts it at once - it opened the
      // coding form, whose coding session could not work on this computer
      : startHere && !canCode && !ranBefore ? [{ id: "start-agent", group: "agent", lead: !pendingReview, label: startingAgent === "general" ? "Starting…" : labelOfRow("start-agent"),
        disabled: !!startingAgent, run: startGeneralAgent, title: hintOfRow("start-agent") }]
      // it OPENS the step where the agent and its instructions are chosen - nothing starts until that step's own button
      : startHere ? [{ id: "start-agent", group: "agent", lead: !pendingReview, label: ranBefore ? labelOfRow("run-another") : labelOfRow("start-agent"),
        run: () => (stage === "agent" ? setRestartOpen(true) : setOpenStage("agent")), title: ranBefore ? hintOfRow("run-another") : hintOfRow("start-agent") }] : []),
      // MESSAGE SOMEONE - email or chat - whoever started the task (the owner, 2026-10-09): tell somebody it is done, the AI writes it, it waits in Close out
      ...(!liveSession ? [{ id: "email", group: "agent", label: labelOfRow("email"), run: () => setEmailOpen(true), title: hintOfRow("email") }] : []),
      ...(replyMessage && !liveSession ? [{ id: "ask-sender", group: "more", label: labelOfRow("ask-sender"), run: () => setAskSenderOpen(true), title: hintOfRow("ask-sender") }] : []),
      { id: "done", group: "more", label: finishing ? "Marking done…" : labelOfRow("done"), disabled: finishing, run: askFinish, title: markDoneHint, promote: !liveSession && !pendingReview, beside: liveSession, onCard: !!pendingReview && !liveSession },   // a live session has no primary;
      // ...nor a waiting draft: its Send, under the draft, is the move (2026-10-06), so Mark done stands outlined beside Next -
      // and so do Start an agent and Next (`onCard`): a second filled button on the bar pulled the eye off the draft
      // ONE VERB FOR IT, button and dialog (U13): "Dismiss" on the bar deleted the task behind a dialog that said Delete
      { id: "nat", group: "more", label: labelOfRow("nat"), run: notATask, title: NAT_TITLE },
      { id: "remind", group: "more", label: remindWaiting(t) ? `Back ${remindDay(t.RemindAt)}` : labelOfRow("remind"), run: (e, a) => setRemindAt(a || e?.currentTarget),
        title: hintOfRow("remind") },
      { id: "hand", group: "more", label: labelOfRow("hand"), run: () => setHandoff(true), title: hintOfRow("hand") },
      { id: "reshape", group: "more", label: labelOfRow("reshape"), run: () => setReshape(true), title: hintOfRow("reshape") },
      // ...whenever an agent has worked it and the bar's lead is not already the agent step (a paused general session had neither)
      ...(!liveSession && notDone && (ranBefore || generalStarted) && !startHere ? [runAnother] : []),
      // WHAT THE PILLS USED TO CHANGE, on the row now that the pills only read (section 1's redesign, 2026-10-16): the same PATCHes
      // and the same repository picker, each a menu at the row's button
      ...changeVerbs,
    ];
  useVerbs("task", rowVerbs, inRow && !!t, detail?.ref || "");
  // CONFIGURE THE NEXT RUN, IN LINE (the owner, 2026-10-05: "should be the bottom like continue session and it should replace the
  // continue session box"): on the canvas the agent step's form is a card under the conversation, in Continue's place - one card at
  // a time - and it closes when the agent starts (startCodingAgent / startGeneralAgent close restartOpen on success)
  // WITH NO CODING TOOL CONNECTED the form is the general agent's and nothing else (B3): no repository picker, no Start coding
  // session, no "Pick a repo first", no switch to a "non-coding" agent and back - there is only the one agent
  const generalOnly = handOff || !canCode;
  const nextRunForm = (
                    <Box sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      <Typography sx={{ color: INK, fontSize: 12.5, fontWeight: 600, mb: 0.75 }}>
                        {report || detail?.transcript || term?.alive || generalStarted ? labelOfRow("run-another") : labelOfRow("start-agent")}
                      </Typography>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
                        {/* coding asks ONE question (which CLI); a hand-off asks three - which profile,
                            which brain, which model - and all three reach the session. */}
                        <AgentPicker agents={agents} models={models} kinds={kinds} coding={!generalOnly}
                          agent={run.agent} model={run.model}
                          brains={brainList} brainModels={brainModels} brain={run.brain || ""}
                          generalBrains={generalBrains} pick={run.pick || ""} has={ownProfile}
                          onPick={(p) => setRun((r) => ({ ...r, pick: p }))}
                          onBrain={(b) => setRun((r) => ({ ...r, brain: b, model: "" }))}
                          onAgent={(a) => setRun((r) => ({ ...r, agent: a }))}
                          onModel={(m) => setRun((r) => ({ ...r, model: m }))} size={28} />
                        <Typography variant="caption" sx={{ color: FAINT }}>
                          It gets the task, its messages and files, and what was saved last time.
                        </Typography>
                      </Box>
                      <TextField fullWidth multiline minRows={2} maxRows={5} size="small" value={run.instruction}
                        onChange={(e) => { const v = e.target.value; setRun((r) => ({ ...r, instruction: v })); }}
                        placeholder={detail?.transcript ? "What should this new agent do next? - paste or drop a picture too" : "Anything else it should know (optional)"}
                        {...runPics.drop}
                        InputProps={{ endAdornment: (
                          <Box sx={{ display: "flex", alignSelf: "flex-start", gap: 0.25 }}>
                            <AttachImage pics={runPics} sx={{ width: 30, height: 30 }} />
                            <MicButton size={18} sx={{ width: 30, height: 30, p: 0, color: "#6e685f" }}
                              onText={(x) => setRun((cur) => ({ ...cur, instruction: cur.instruction ? `${cur.instruction} ${x}` : x }))} />
                          </Box>) }}
                        sx={{ mt: 0.85, bgcolor: "#fff", "& .MuiInputBase-root": { alignItems: "flex-start" } }} />
                      <ImageTray pics={runPics} sx={{ mt: 0.75 }} />
                      {!generalOnly && <RepoSelect taskId={selected} agent={run.agent} instruction={run.instruction}
                        value={startRepo} onChange={setStartRepo} />}
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>
                        {!generalOnly && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent || startRepo === "" || runPics.busy}
                          startIcon={startingAgent === "coding" ? <CircularProgress size={11} /> : <TerminalIcon sx={{ fontSize: 14 }} />}
                          onClick={startCodingAgent}>
                          {startingAgent === "coding" ? "Starting…" : btn("coding_agent")}
                        </Button>}
                        {/* HELD FOR A REPOSITORY it said nothing (the owner, 2026-10-01): it says why, with the picker beside it, and
                            the pick resumes this start - the same road a start that ran into the question takes */}
                        {!generalOnly && startRepo === "" && <>
                          <Typography variant="caption" sx={{ color: "#6b2733", fontWeight: 600 }}>{PICK_CODE} first</Typography>
                          <Button size="small" variant="outlined" sx={chipBtn} disabled={!!startingAgent}
                            startIcon={<AccountTreeIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                            title="Which checkout the session works in - the session starts once you pick"
                            onClick={() => { setRepoPick(true); setResumeAfterRepo({ dispatch: true }); }}>{PICK_CODE.toLowerCase()}</Button>
                        </>}
                        {/* it SWITCHES the row rather than dispatching on the spot: the pickers above
                            become the profile, brain and model, and the next press starts it */}
                        {!generalOnly && <Button size="small" variant="outlined" disabled={!!startingAgent}
                          startIcon={<TaskuaryMark size={13} />}
                          onClick={() => { setHandOff(true); setRun((r) => ({ ...r, agent: "", pick: "", model: "" })); }}>{choice("agent", "regular_agent")}</Button>}
                        {generalOnly && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent || runPics.busy}
                          startIcon={startingAgent === "general" ? <CircularProgress size={11} /> : <TaskuaryMark size={13} />}
                          onClick={startGeneralAgent}>
                          {startingAgent === "general" ? "Starting…" : btn("regular_agent")}
                        </Button>}
                        {handOff && canCode && <Button size="small" variant="text" disabled={!!startingAgent}
                          onClick={() => { setHandOff(false); setRun((r) => ({ ...r, agent: "", pick: "", model: "" })); }}>Back to coding</Button>}
                        {(restartOpen || report || detail?.transcript) && <Button size="small" variant="text"
                          onClick={() => setRestartOpen(false)}>Cancel</Button>}
                      </Box>
                    </Box>
  );
  const [nextRunSlot, setNextRunSlot] = useState(null);
  useEffect(() => {
    if (!(canvas && restartOpen)) { setNextRunSlot(null); return; }
    const el = document.querySelector("[data-tq-run-slot]");
    setNextRunSlot(el);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [canvas, restartOpen]);
  return (
    <>
      {/* ── detail ────────────────────────────────────────────────────── */}
      {/* ON THE CANVAS THE VIEW FITS ITS BOX EXACTLY (the owner, 2026-10-01: "check the issue with task view if it can draw on top of
          it next message. That should never happen"). Two causes, both measured by website/task_overflow_probe.mjs: `frame`'s padding
          and borders sat OUTSIDE a height of 100% (14px over), and that 100% was of a box with only a max-height - which a percentage
          cannot resolve against - so a long task grew to its whole content (34px over) and the next line of the chat landed on it.
          On the canvas the chain is flex columns that SHRINK to the box instead, and the task's own scroller takes what is left. */}
      <Box data-tq-task-page={selected || ""} sx={{ ...frame, ...(canvas ? { p: 0, bgcolor: "transparent", border: 0, boxShadow: "none" } : {}), flex: 1, minWidth: 0, height: canvas ? "auto" : "calc(100vh - 118px)", minHeight: canvas ? 0 : 420,
        ...(canvas ? { boxSizing: "border-box", flex: "1 1 auto", display: "flex", flexDirection: "column" }
                   : { display: { xs: selected ? "block" : "none", md: "block" } }) }}>
        <Box sx={{ ...frameInner, display: "flex", flexDirection: "column",
          ...(canvas ? { boxSizing: "border-box", flex: "1 1 auto", minHeight: 0 } : { height: "100%" }) }}>
          {/* this view's own errors - they were drawn over the list column when the two were one component */}
          {err && <Alert severity="error" onClose={() => { setErr(""); setStartFail(null); }} sx={{ mb: 1, flexShrink: 0 }}>{err}
            {startFail && startFail.text === err && <FailWays fail={startFail} onRetry={() => { const go = startFail.again; setErr(""); setStartFail(null); go?.(); }} />}</Alert>}
          {!t ? (
            // ...AND ON THE TABLE IT HOLDS THE VIEW'S ROOM (G8): a view with no pane is only as tall as what it draws (CanvasItem), so the
            // shell was 22px - the dead-end walk's SEEN "only 22px of the card on the table is in view" after Remove (CI, 2026-10-20) was a
            // next view still waiting for its read - and the view then grew to 400 under the owner's eyes. The canvas's own floor, 340
            <Box data-tq-task-loading={selected ? "" : undefined} sx={{ height: "100%", minHeight: canvas && selected ? 340 : undefined, display: "grid", placeItems: "center" }}>
              {/* ...and on the table it says WHICH item is coming (a rail row clicked cold draws its frame at the click - AssistantView surface) */}
              {selected ? <Box sx={{ display: "grid", justifyItems: "center", gap: 1 }}><CircularProgress size={20} />
                {canvas && !!title && <Typography data-tq-task-loading-title="" sx={{ fontSize: 13, color: DIM, textAlign: "center", px: 2 }}>{title}</Typography>}</Box>
                : <Empty>{"The task you open will show here — its messages, its session, its history."}</Empty>}
            </Box>
          ) : (
            <>
              {/* header strip: ONE LINE, and it is the Task card's heading too. It used to be a
                  tall block - id, title, dots, close, then "from email · created 10h ago by router"
                  - sitting directly above a second heading that said "Task · the job itself". The
                  provenance line moved into the card (Came from, under its messages), where you go
                  and look at it rather than read it every time. */}
              <Box sx={{ px: liveSession ? 1.5 : 1.75, py: liveSession ? 0.7 : 1,
                bgcolor: "#fff", borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
                {/* on a phone the strip WRAPS: ref and title keep the first line, the controls take the next - one line
                    pushed Next, Expand and the X off the right edge (the canvas redesign's phone pass, 2026-09-29) */}
                {/* ...only while there ARE controls to wrap. On the assistant's canvas there are none up here, and the strip still
                    wrapped: Expand and the X took a row of their own under a cut title (the 2026-10-07 design pass) */}
                <Box sx={{ display: "flex", gap: 0.9, rowGap: 0.5, alignItems: "center",
                  flexWrap: headControls ? { xs: "wrap", sm: "nowrap" } : "nowrap" }}>
                  {/* THE (1) IS THE TASK STEP'S NUMBER, so it sits on whichever line is that step's heading: up here while the
                      step is open (or a session hides it), on the folded Task strip once another step is open - it stood up
                      here beside a folded "Task" row that had none, and the count read 1 · Task · 2 · 3 */}
                  {/* ...and with the step open its heading is "1 Task" inside the card (section 1's redesign, 2026-10-16) - up here only
                      while a session hides the card */}
                  {sessionView && <Box sx={{ width: 18, height: 18, borderRadius: "50%", bgcolor: "#55697a", color: "#fff",
                    display: "grid", placeItems: "center", flexShrink: 0, fontSize: 9.5, fontWeight: 600 }}>1</Box>}
                  <Typography sx={{ color: "#41525f", fontVariantNumeric: "tabular-nums", flexShrink: 0,
                    letterSpacing: ".015em", fontWeight: 600, fontSize: 11.5 }}>{detail.ref}</Typography>
                  <Typography sx={{ color: INK, flex: 1, fontWeight: 600,
                    fontSize: liveSession ? 12.5 : 13,
                    minWidth: headControls ? { xs: 90, sm: 180 } : 0, flexBasis: headControls ? { xs: "calc(100% - 90px)", sm: "auto" } : "auto",
                    letterSpacing: "-.005em" }} noWrap>
                    {t.Title}
                  </Typography>
                  {/* the list row said this and the task page did not, so a held task looked merely open */}
                  {interruptedTask && <Chip size="small" label="agent stopped"
                    title="Taskuary closed while an agent was working this. Nothing restarts until you choose one."
                    sx={{ height: 17, fontSize: 9.5, bgcolor: "#eee7d6", color: "#7a5c1e", flexShrink: 0 }} />}
                  {/* A LIVE SESSION HIDES THE TASK CARD ENTIRELY (the gate is !term?.alive below), so
                      with the card goes every task control - and the owner wants the session to keep
                      the space (2026-09-16: "if agent in progress we want it small to give the most
                      space to the agent canvas"). The four controls ride up here instead: the same
                      four, in the same order, labels dropped to icons after the first. */}
                  {headControls && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, flexShrink: 0 }}>
                      <Button size="small" variant="contained" disableElevation startIcon={finishing ? <CircularProgress size={11} color="inherit" /> : <DoneAllIcon sx={{ fontSize: 13 }} />}
                        sx={{ fontSize: 10.5, minHeight: 24, py: 0, px: 1 }}
                        title={markDoneHint}
                        disabled={finishing} onClick={askFinish}>{finishing ? "Marking done…" : labelOfRow("done")}</Button>
                      <Tooltip title={`${labelOfRow("nat")}. ${NAT_TITLE}`}>
                        <IconButton size="small" sx={{ color: "#7a2f3c" }} onClick={notATask}>
                          <BlockIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                      <RemindMe task={t} compact onDone={reminded} onLeave={onLeave} onStay={onStay} live={liveSession} />
                      <Tooltip title={`${labelOfRow("hand")} - ${hintOfRow("hand")}`}>
                        <IconButton size="small" sx={{ color: "#55697a" }} onClick={() => setHandoff(true)}>
                          <ForwardToInboxIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                      <Tooltip title={`${labelOfRow("reshape")} - ${hintOfRow("reshape")}`}>
                        <IconButton size="small" sx={{ color: "#6f8a6e" }} onClick={() => setReshape(true)}>
                          <CallSplitIcon sx={{ fontSize: 15 }} /></IconButton>
                      </Tooltip>
                    </Box>
                  )}
                  <LifecycleChip kind="task" phase={taskState} compact sx={{ flexShrink: 0, display: { xs: "none", sm: "inline-flex" } }} />
                  {/* ON THE ASSISTANT CANVAS Expand gives the view the whole canvas - the pane keeps its size either way.
                      Next is NOT up here: it sits under the view, where the walk has always put it (CanvasItem) */}
                  {onExpand && (
                    <Tooltip title={expanded ? "Back to the conversation" : "Give this the whole canvas"}>
                      <IconButton size="small" data-tq-expand="" aria-label={expanded ? (backArrow ? "Back to the chat" : "Collapse to the conversation") : "Expand to the whole canvas"}
                        aria-pressed={expanded} onClick={onExpand} sx={{ color: "#41525f", flexShrink: 0 }}>
                        {/* a phone's full screen goes BACK to the chat - an arrow, the way every phone says it. The SAME size
                            as the icon it replaces: 2px more re-flowed the strip and shrank the pane, a grow on the way back */}
                        {expanded ? (backArrow ? <ArrowBackIcon sx={{ fontSize: 15 }} /> : <CloseFullscreenIcon sx={{ fontSize: 15 }} />) : <OpenInFullIcon sx={{ fontSize: 15 }} />}
                      </IconButton>
                    </Tooltip>
                  )}
                  {/* ONE X, TWO STEPS BACK. With the session filling the page, X first steps back to
                      the task behind it - the session keeps running; from the task, X goes to the list. */}
                  <Tooltip title={sessionView ? "Back to the task — the session keeps running" : "Close — back to the list (the task stays)"}>
                    <IconButton aria-label={sessionView ? "Back to task" : "Close task"} size="small" onClick={() => (sessionView ? setPeek(true) : dismiss())}><CloseIcon sx={{ fontSize: 15 }} /></IconButton>
                  </Tooltip>
                </Box>
                {workContext && <Typography variant="caption" sx={{ color: "#6b5f45", display: "block",
                  mt: 0.15, ml: 3.4, fontWeight: 600, fontSize: 10 }}>
                  {workContext}
                </Typography>}
                {/* TRIAGE DECIDED - what the task is, said once under its title as facts, never as controls (the owner, 2026-10-16: "why
                    are there dropdowns by the triage results? you can't change it"). A task nobody triaged shows its own facts, unlabelled.
                    Not over a session: that strip stays one line so the agent keeps the room. Nor over the agent's step on the canvas:
                    the facts are the Task step's, and the height is the agent's (the owner, 2026-10-18: "see more of the agent canvas"). */}
                {!sessionView && !(canvas && stage === "agent") && <Box data-tq-triage-facts="" sx={{ display: "flex", alignItems: "center", gap: 0.6, rowGap: 0.5, flexWrap: "wrap", mt: 0.8, minWidth: 0 }}>
                  {facts.workflow && <ChannelIcon channel="workflow" sx={{ fontSize: 15, mr: 0.1 }} />}
                  {facts.pills.filter((p) => !SAID.has(p.key) || p.tone === "alert").map((p) => { const { k, ...tone } = FACT_TONE[p.tone] || {}; return (
                    <Box key={p.key} component="span" data-tq-fact={p.key} sx={{ ...factPill, ...tone }}>
                      <Box component="span" sx={{ color: k || FAINT }}>{p.label}</Box>
                      <Box component="span" sx={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", ...(p.mono ? { ...mono, fontSize: 11 } : {}) }}>{p.value}</Box>
                    </Box>); })}
                  <Typography component="span" data-tq-sorted="" sx={{ fontSize: 12, color: DIM, minWidth: 0 }}>{sortedLine(facts, t?.Kind || "task")}</Typography>
                  {/* WHAT HAPPENS AT THE END, in a few words on the facts' own line; the sentence that explains it is the tooltip */}
                  {notDone && <>
                    <Box sx={{ width: "1px", height: 16, bgcolor: BORDER, mx: 0.5, display: { xs: "none", sm: "block" } }} />
                    <Typography variant="caption" sx={{ color: DIM }} title={completionLine(completionIsManual, owesEmails, !replyMessage)}>
                      {completionFact(completionIsManual, owesEmails, !replyMessage)}</Typography>
                  </>}
                </Box>}
              </Box>
              {/* a flex column so the terminal takes exactly what is left between the strip above and the
                  waiting room below - a fixed-height formula clipped its bottom line on shorter screens */}
              <Box ref={stepsBox} sx={{ px: liveSession ? 1 : 2, py: liveSession ? 0.65 : 1.5,
                overflowY: "auto", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
                {/* THE SESSION IS THE PAGE. Your CLI, in this task's repo, with the task in
                    its lap - you type into it like any other terminal. Everything below is
                    reference material about the same task, folded away. */}
                {/* the session just closed: its write-up takes the space the terminal had, so the
                    result of the work is the thing you are looking at */}
                {/* The checkout, and why. A wrong guess means an agent editing the wrong tree in
                    good faith, so it is stated on the page rather than buried in the prompt. */}
                {/* In the agent view the task card (and its Came from) is not drawn, and a report task's
                    whole substance is the report - so it is one click away here (the owner, 2026-09-30) */}
                {sessionView && t?.Source === "report" && sourceMessage?.BodyText && (
                  <Box sx={{ ...card, ...step, mb: 0, px: 1.5, py: 1.1, flexShrink: 0 }}>
                    <Box onClick={() => setReportOpen((v) => !v)} sx={{ display: "flex", alignItems: "center", gap: 0.85, cursor: "pointer" }}>
                      <Typography sx={{ ...label }}>The report</Typography>
                      <Typography noWrap sx={{ color: DIM, fontSize: 11.5, flex: 1, minWidth: 0 }}>
                        {sourceMessage.SourceName || sourceMessage.Subject} · {fmtDateTime(sourceMessage.SentAt)}</Typography>
                      <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, transition: "transform .15s", transform: reportOpen ? "rotate(180deg)" : "none" }} />
                    </Box>
                    {reportOpen && (
                      <Box sx={{ mt: 0.85, maxHeight: 420, overflowY: "auto", minWidth: 0, overflowWrap: "anywhere" }}>
                        {looksMd(sourceMessage.BodyText) ? <Md text={cleanText(sourceMessage.BodyText)} />
                          : <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{cleanText(sourceMessage.BodyText)}</Typography>}
                      </Box>
                    )}
                  </Box>
                )}
                {/* ...and a BATCH's items stay in view while its agent works through them: each result lands on its line as the
                    agent reports it, and the presses on a finished line are usable without leaving the session (batch.py) */}
                {sessionView && detail?.batch && (
                  <Box sx={{ ...card, ...step, mb: 0, px: 1.5, py: 1.1, flexShrink: 0 }}>
                    <Box onClick={() => setItemsOpen((v) => !v)} sx={{ display: "flex", alignItems: "center", gap: 0.85, cursor: "pointer" }}>
                      <Typography sx={{ ...label }}>The items</Typography>
                      <Typography noWrap sx={{ color: DIM, fontSize: 11.5, flex: 1, minWidth: 0 }}>{batchProgress(detail.batch)}</Typography>
                      <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, transition: "transform .15s", transform: itemsOpen ? "rotate(180deg)" : "none" }} />
                    </Box>
                    {itemsOpen && <Box sx={{ maxHeight: 360, overflowY: "auto", minWidth: 0 }}>
                      <BatchItems taskId={t?.TaskId} items={detail.batch} bare
                        onChanged={() => { loadDetail(t.TaskId); loadTasks(); onChanged?.(); }} /></Box>}
                  </Box>
                )}
                {!sessionView && (
                  <Box sx={{ ...card, ...step, borderTop: 0, mb: 0, px: 1.5, py: stage === "task" ? 1.5 : 1.1, flexShrink: 0 }}>
                    {/* FOLDED - the left half carries what the header cannot: how far the checklist got, and what the task is.
                        The whole strip reopens the task. */}
                    {stage !== "task" && (
                      <Box onClick={() => setOpenStage("task")}
                        sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, cursor: "pointer", flexWrap: { xs: "wrap", sm: "nowrap" },
                          opacity: 0.72, "&:hover": { opacity: 1 } }}>
                        {/* the SAME heading as Agent work and Close out under it - circle, title, then what it holds - where it
                            was a small-caps "Task" label with no number, beside a (1) still up in the header */}
                        <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: PALETTE.slate, color: "#fff",
                          display: "grid", placeItems: "center", flexShrink: 0, fontSize: 11.5, fontWeight: 600 }}>1</Box>
                        <Typography sx={{ color: INK, fontSize: 14, fontWeight: 600, lineHeight: 1.3, flexShrink: 0 }}>Task</Typography>
                        <Typography noWrap sx={{ color: DIM, fontSize: 12.5, flex: 1, minWidth: 0 }}>{foldedFacts}</Typography>
                        {/* no buttons on the strip: the Tasks tab's own bar under the view carries them, as the row does on the canvas */}
                        <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0, transform: "rotate(-90deg)" }} />
                      </Box>
                    )}
                    {stage === "task" && <Box data-tq-task-section="" sx={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 1.75 }}>
                    {/* SECTION 1, IN THE ORDER THE OWNER APPROVED (2026-10-16): the ask, what there is to do, where it came from - and no
                        buttons. "The buttons stay on bottom by the prompt box like always. No buttons there." On the canvas that is the row
                        over the chat line; on the Tasks tab, the view's own bar under the sections. */}
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: PALETTE.slate, color: "#fff",
                        display: "grid", placeItems: "center", flexShrink: 0, fontSize: 11.5, fontWeight: 600 }}>1</Box>
                      <Typography sx={{ color: INK, fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>Task</Typography>
                    </Box>
                    <Box sx={{ pl: { xs: 0, sm: 4.25 }, minWidth: 0, display: "flex", flexDirection: "column", gap: 2.75 }}>
                      {/* OPEN AGAIN, AND WHY (funnel.news_since_agent): the message that reopened it, said first - the agent's last
                          session is the record under Agent work, not the news (the owner, 2026-10-12). Where the Advisor's NEXT
                          strip stands under the canvas it says what to do, so this one goes (assistantView.css .advising) */}
                      {news && <Typography className="tq-news" sx={{ fontSize: 12.5, color: INK, fontWeight: 600 }}>Open again: {news.line}</Typography>}
                      {/* THE ASK - one line of what is wanted; the whole summary is the tooltip when the line cut it */}
                      {askText && <Part label="The ask" data-tq-ask="">
                        <Typography title={askText} sx={{ color: INK, fontSize: 14, lineHeight: 1.45, overflowWrap: "anywhere",
                          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{askText}</Typography>
                      </Part>}
                      {/* TO DO - the checklist triage drew from the ask (PW-075): boxes are progress on the list, never task completion -
                          closing the task stays the owner's separate decision. The WHOLE LINE is the target, not the 16px box: on a
                          manual task ticking these off IS the work (the owner, 2026-09-16). A batch lists its items, a goal its steps. */}
                      {/* a batch's items and a goal's steps are its to-do too, named the same way (the owner, 2026-10-16: "it's not 3 sections") */}
                      {detail?.batch && <Part label="To do" data-tq-todo=""><BatchItems taskId={t?.TaskId} items={detail.batch}
                        onChanged={() => { loadDetail(t.TaskId); loadTasks(); onChanged?.(); }} /></Part>}
                      {t?.DoneWhen && <Part label="Steps" data-tq-todo=""><GoalSteps task={t} onOpenTask={(tid) => (onOpenTask ? onOpenTask(tid) : onSelect?.(tid))}
                        onChanged={() => { loadDetail(t.TaskId); loadTasks(); onChanged?.(); }} /></Part>}
                      {!t?.DoneWhen && todo.length > 0 && (
                        <Part label="To do" sub={`${todo.filter((i) => i.done).length} of ${todo.length}`} subTitle={progressLine(todo)} data-tq-todo="">
                          {todo.map((i) => (
                            <Box key={i.id}>
                              <Box onClick={() => tickItem(i)}
                                sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.75, ml: -0.75, py: 0.15,
                                  borderRadius: 1, cursor: "pointer", "&:hover": { bgcolor: "#faf8f4" }, "&:hover [data-tq-todo-note-add]": { opacity: 1 } }}>
                                <Checkbox size="small" checked={!!i.done} onChange={() => {}} tabIndex={-1}
                                  sx={{ p: 0.25, pointerEvents: "none", color: "rgba(0,0,0,.54)", "&.Mui-checked": { color: "#6f8a6e" } }} />
                                <Typography variant="body2" sx={{ color: i.done ? FAINT : INK, textDecoration: i.done ? "line-through" : "none", lineHeight: 1.6 }}>
                                  {i.text}
                                </Typography>
                                {/* THE TO-DO'S NOTE (the owner, 2026-10-20): a quiet word on the row opens the field under it - the row itself still ticks */}
                                {noting !== i.id && !noteOf(i) && <Link component="button" type="button" underline="hover" data-tq-todo-note-add=""
                                  onClick={(e) => { e.stopPropagation(); setNoting(i.id); setNoteText(""); }}
                                  sx={{ ml: "auto", fontSize: 11.5, color: FAINT, opacity: 0, "&:focus-visible": { opacity: 1 } }}>note</Link>}
                              </Box>
                              {noting === i.id
                                ? <TextField autoFocus fullWidth size="small" placeholder="A note on this to-do" value={noteText} data-tq-todo-note-field=""
                                    onChange={(e) => setNoteText(e.target.value)} onBlur={() => putNote(i, noteText)}
                                    onKeyDown={(e) => noteKey(e, { save: () => putNote(i, noteText), cancel: () => setNoting(null) })}
                                    sx={{ ml: 3.5, width: "calc(100% - 28px)", mb: 0.4, "& .MuiInputBase-root": { fontSize: 12 } }} />
                                : noteOf(i) && <Typography variant="caption" data-tq-todo-note="" onClick={() => { setNoting(i.id); setNoteText(noteOf(i)); }}
                                    sx={{ display: "block", ml: 3.5, color: DIM, fontSize: 12, lineHeight: 1.45, cursor: "text", overflowWrap: "anywhere" }}>
                                    {noteOf(i)}</Typography>}
                            </Box>
                          ))}
                        </Part>
                      )}
                      {/* CAME FROM - the task's messages as the conversations they are: each one's first message and its latest two, with
                          how many are between and who wrote them. It replaces "Where this came from" and the stack of later messages under
                          the ask (the owner, 2026-10-16: "you will probably have to have a scroll if it goes really far back"). A row opens
                          its message in full under it, as the old disclosure did. */}
                      <Part label="Came from" sub={fromWorkflow && !sources.length ? "a workflow run" : cameFromLabel(sources).replace(/^Came from · /, "").replace(" in ", " · ")} data-tq-came-from="">
                        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap", "&:empty": { display: "none" } }}>
                          {!!(detail.attachments?.length || detail.links?.length) && <Chip size="small" icon={<AttachFileIcon sx={{ fontSize: 13 }} />}
                            label={filesLine(detail.attachments?.length || 0, detail.links?.length || 0)}
                            sx={{ height: 19, fontSize: 10, bgcolor: PANEL2 }} />}
                          {expands(sources) && <Link component="button" type="button" underline="hover" onClick={() => setShowAll((v) => !v)}
                            sx={{ ml: "auto", fontSize: 12 }}>{showAll ? "Show less" : `Show all ${sourceCount}`}</Link>}
                        </Box>
                        {/* ONE SENDER, ONE ITEM, SAID: ingest folds the same sender writing again about this onto one task; said once -
                            how many, and what they need now (concierge.repeats, counted by code) */}
                        {detail?.repeats?.line && <Typography variant="body2" sx={{ color: DIM, mt: 0.4, fontSize: 12.5, overflowWrap: "anywhere" }}>{detail.repeats.line}</Typography>}
                        {/* WHOSE WORDS: a stranger's task runs in its CLI's auto mode (origin.py) - said once, quietly, with the reason on
                            hover and the one owner action that changes it, a link. Nothing for the owner's or trusted work. */}
                        {strangerLine(detail) && (
                          <Typography variant="body2" sx={{ color: DIM, mt: 0.4, fontSize: 12.5 }}>
                            <Tooltip title={strangerLine(detail).why}><span>{strangerLine(detail).text}</span></Tooltip>
                            {" · "}
                            <Link component="button" underline="hover" sx={{ fontSize: 12.5, verticalAlign: "baseline" }}
                              onClick={async () => {
                                try { await runOperation(api, "task.trust", selected); loadDetail(selected); loadTasks(); onChanged?.(); }
                                catch (e) { setErr(`That didn't go through - ${opError(e, "Taskuary didn't answer")}. Press ${strangerLine(detail).trust} again.`); }
                              }}>
                              {strangerLine(detail).trust}
                            </Link>
                          </Typography>
                        )}
                        {/* ...and what its words read as trying to make an agent do: one line, before anyone presses Start */}
                        {strangerLine(detail)?.danger && (
                          <Typography variant="body2" sx={{ color: ALERT, mt: 0.3, fontSize: 12.5, overflowWrap: "anywhere" }}>
                            ⚠ Reads as an attempt to steer the agent: {strangerLine(detail).danger}
                          </Typography>
                        )}
                        {sources.length > 0 ? (
                          <Box ref={cameFromRef} sx={{ mt: 0.75, border: `1px solid ${BORDER}`, borderRadius: 1.25, bgcolor: "#fff", overflow: "hidden", scrollMarginTop: 8 }}>
                            {sources.map((g, gi) => (
                              <Box key={g.key} data-tq-conversation="" sx={{ px: { xs: 1, sm: 1.4 }, py: 1.1, borderTop: gi ? "1px solid #ece7e0" : 0, minWidth: 0 }}>
                                <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: { xs: "wrap", sm: "nowrap" } }}>
                                  <Box sx={{ width: 24, height: 24, borderRadius: 1, bgcolor: "#f1eee8", display: "grid", placeItems: "center", flexShrink: 0 }}>
                                    <ChannelIcon channel={g.channel} sx={{ fontSize: 14 }} /></Box>
                                  <Typography noWrap sx={{ color: INK, fontWeight: 600, fontSize: 13, flex: 1, minWidth: 0, flexBasis: { xs: "calc(100% - 40px)", sm: "auto" } }} title={g.title}>{g.title}</Typography>
                                  <Typography noWrap variant="caption" sx={{ color: DIM, fontSize: 11.5, flexShrink: 0, maxWidth: "100%", pl: { xs: 4, sm: 0 } }}>{groupMeta(g)}</Typography>
                                </Box>
                                {/* SHOW ALL DRAWS EACH CONVERSATION IN ITS OWN FORM: a chat as the back-and-forth it is - bubbles, yours on the right
                                    (the owner, 2026-10-16: "wasn't this supposed to be a chat back and forth if you hit show all?") - and an email
                                    thread as every row, each opening its letter. Each scrolls in its own box, so one long thread cannot bury the next. */}
                                <Box sx={{ pl: { xs: 0, sm: 4.25 }, mt: 0.5, minWidth: 0 }}>
                                  {showAll && isChat(g.channel) ? <ChatThread messages={g.msgs} maxHeight={THREAD_MAX} />
                                    : <Box sx={showAll ? { maxHeight: THREAD_MAX, overflowY: "auto", minWidth: 0 } : undefined}>
                                        <ConversationRows rows={previewRows(g, 2, showAll)} open={openMsg} onOpen={setOpenMsg}
                                          onExpand={() => setShowAll(true)} files={sourceFiles} fetchFor={fetchFor} /></Box>}
                                </Box>
                              </Box>
                            ))}
                            {/* WHAT TRIAGE DID, quietly, last: when, whose it made it - the route record leads with who now - and why; then
                                what joined it since. A task nobody triaged says where it came from and when it was made. */}
                            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", px: { xs: 1, sm: 1.4 }, py: 0.9, borderTop: "1px solid #ece7e0", bgcolor: "#faf8f5" }}>
                              <AltRouteIcon sx={{ fontSize: 15, color: ACCENT, mt: 0.25, flexShrink: 0 }} />
                              <Typography sx={{ fontSize: 12, color: DIM, minWidth: 0, overflowWrap: "anywhere" }} title={`${detail.ref} · ${made}`}>
                                {triaged.head
                                  ? <><Box component="span" sx={{ color: INK, fontWeight: 600 }}>Sorted{triaged.at ? ` · ${whenShort(triaged.at)}` : ""}</Box>{" "}
                                      {triaged.head}{triaged.why ? `: "${triaged.why}"` : ""}</>
                                  : <span>{detail.ref} · {made}</span>}
                                {triaged.later > 0 && ` · ${plural(triaged.later, "later message")} joined it`}
                              </Typography>
                            </Box>
                          </Box>
                        ) : fromWorkflow ? (
                          /* A WORKFLOW RUN has no message to show: where it came from is the workflow and what started it - its clock, your
                             Run now, the assistant, your phone (the owner, 2026-10-16: "what does it show triggered it in the task card?") */
                          <Box data-tq-workflow-origin="" sx={{ mt: 0.75, border: `1px solid ${BORDER}`, borderRadius: 1.25, bgcolor: "#fff", px: { xs: 1, sm: 1.4 }, py: 1.1,
                            display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: { xs: "wrap", sm: fromWorkflow.steps ? "wrap" : "nowrap" } }}>
                            <Box sx={{ width: 24, height: 24, borderRadius: 1, bgcolor: "#f1eee8", display: "grid", placeItems: "center", flexShrink: 0 }}>
                              <ChannelIcon channel="workflow" sx={{ fontSize: 14 }} /></Box>
                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Typography noWrap sx={{ color: INK, fontWeight: 600, fontSize: 13 }} title={fromWorkflow.title}>Workflow · {fromWorkflow.title}</Typography>
                              <Typography variant="caption" sx={{ color: DIM, fontSize: 11.5, display: "block" }} title={`${detail.ref} · ${made}`}>
                                {fromWorkflow.line} · {whenShort(t?.CreatedAt)}</Typography>
                            </Box>
                            {fromWorkflow.link && <Link href={fromWorkflow.link} underline="hover" sx={{ fontSize: 12, flexShrink: 0 }}>Open the workflow</Link>}
                            {fromWorkflow.steps && <Box data-tq-workflow-steps="" sx={{ flexBasis: "100%", borderTop: `1px solid ${BORDER}`, pt: 0.75, mt: 0.25, minWidth: 0 }}>
                              {/* a failed run's fix is one press from its task: the workflow opens with Fix with AI already asked */}
                              <RunSteps steps={fromWorkflow.steps} dense repairs={fromWorkflow.repairs}
                                onFix={fromWorkflow.sourceId != null && fromWorkflow.runId != null
                                  ? () => { openAppLink(`report=${fromWorkflow.sourceId}&fix=${fromWorkflow.runId}`); } : null} /></Box>}
                          </Box>
                        ) : <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.25 }}>{detail.ref} · {made}</Typography>}
                      </Part>
                    </Box>
                    </Box>}
                  </Box>
                )}
                {/* ONE SHORT LINE, LIVE OR NOT. A running session has always been a single strip -
                    heading, chip, controls - while the stopped card answered with a heading, a
                    sentence under it, and a row of buttons under that: three lines for the same
                    question (the owner, 2026-09-17: keep the stopped header as short as the
                    one a running agent gets). The bar rides IN the heading now, so
                    the sentence and the row that held it both go. */}
                {/* a queued start: what it waits for, or why it could not start - with Start now and Cancel (T10) */}
                {!liveSession && listRow?.State === "queued" && listRow?.Queued && <Box sx={{ mb: 1 }}>
                  <QueuedStart taskId={t.TaskId} queued={listRow.Queued} onChanged={() => { loadTasks(); loadDetail(t.TaskId); }} />
                </Box>}
                {!codeRun && <Box ref={agentHead} sx={{ ...card, ...step, mb: liveSession ? 0.55 : 0,
                  px: liveSession ? 1 : 1.5, py: liveSession ? 0.55 : stage === "agent" ? (agentBar ? 0.8 : 1.5) : 1.1,
                  flexShrink: 0,
                  display: liveSession ? "flex" : "block", alignItems: "center",
                  gap: liveSession ? 1 : 0, flexWrap: "wrap" }}>
                  <Box sx={{ minWidth: 0, flex: liveSession ? "0 1 auto" : "initial" }}>
                    {/* the agent by NAME, not by which binary is running: "Agent running · <CLI>
                        · <profile> (your CLI)" named a product and a profile (the owner, 2026-09-08) */}
                    {/* A LIVE SESSION IS NOT A WORKING ONE. This asked only whether a pty existed,
                        so the heading read "<agent> is working" directly above its own chip saying
                        "agent · needs you" - on an agent that had been parked on a question for an
                        hour (the owner, 2026-09-11, TQ-0499). agentState is the session's own word
                        (taskLifecycle.agentPhase); the heading now says what the chip says. */}
                    <WorkflowHeading number="2" title={!term?.alive ? "Agent work"
                      : answered ? `${agentName(t)} answered`
                      : agentState === AGENT.waiting ? says(subState(term), agentName(t))   /* asked, approval, stuck (T6) */
                        : `${agentName(t)} is working`}
                    chip={story && STORY_CHIP[story.kind] ? <StoryChip kind={story.kind} text={STORY_CHIP[story.kind]} />
                      : agentState ? <LifecycleChip kind="agent" phase={agentState} compact /> : null} tone={PALETTE.sage} {...stageProps("agent")}
                    tools={inRow && workspaceMode === "general" && (liveSession || stage === "agent")
                      ? <Box ref={setChatTools} sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }} /> : null}
                    /* folded, this heading carried NOTHING - it passed no action at all, so the one
                       card that can actually be picked back up was the one row you could not act on.
                       It gets the move that matches its state, the way the Task strip does. */
                    action={inRow ? null : stage === "agent" && agentBar ? agentBarRow :
                      stage !== "agent" && !term?.alive && !["done", "dropped"].includes(t.Status)
                      ? <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.35 }}>
                          {/* a regular agent's conversation is continued too - "Start an agent" read as starting over (T15) */}
                          {detail?.resumable || (isGeneral && generalStarted) ? (
                            <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                              sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                              startIcon={startingAgent === "resume" ? <CircularProgress size={11} /> : <HistoryIcon sx={{ fontSize: 14 }} />}
                              title={detail?.resumable ? `Reopens ${detail.resumable.agent}'s own session in ${detail.resumable.cwd}.` : "Picks its conversation back up."}
                              onClick={(e) => setContinueAt(e.currentTarget)}>{labelOfRow("continue")}</Button>
                          ) : (
                            <Button size="small" variant="contained" disableElevation
                              sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                              startIcon={<TerminalIcon sx={{ fontSize: 14 }} />}
                              title="Opens the agent step so you can choose the agent and add instructions."
                              onClick={() => setOpenStage("agent")}>
                              {report || detail?.transcript ? labelOfRow("run-another") : labelOfRow("start-agent")}</Button>
                          )}
                        </Box>
                      : null} />
                  </Box>
                  {/* folded with no record, the step says its one sentence; open with none, the story is the whole account (storyPlace) */}
                  {(storyAt === "line" || storyAt === "story") && <AgentStory story={story} compact={storyAt === "line"} />}
                  {/* ...folded over a record, its sentence and what happened - the draft it wrote opens below it (2026-09-22) */}
                  {storyAt === "summary" && <AgentRecord {...recordProps} story={story} folded />}
                  {stage === "agent" && <>
                  {term?.alive && !inRow && (
                    // on a phone the two buttons take their own row: sharing one with the heading, they
                    // stacked over the "agent · needs you" chip (2026-09-20)
                    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end",
                      gap: 0.35, flexWrap: "wrap", flex: { xs: "1 0 100%", sm: 1 }, minWidth: 0, mt: liveSession ? { xs: 0.5, sm: 0 } : 1 }}>
                      {/* A LIVE SESSION HAS NO PRIMARY. "Answer agent" / "Give new prompt" opened a
                          Dialog whose whole body was the SAME TellAgent that was then inline under
                          the terminal - a modal copy of a control on the page (the owner, 2026-09-16:
                          "answer agent really does nothing, it's just type into the prompt window").
                          While an agent is working the next move is typing, so nothing here is filled;
                          the notification stays on the chip and beside the waiting room. */}
                      {liveCodingSession && <Button size="small" variant="outlined" sx={liveCtl} startIcon={<DifferenceIcon sx={{ fontSize: 13 }} />}
                        title="A viewer of the agent's diff. Nothing is approved or committed here."
                        onClick={() => setDiffOpen(true)}>{labelOfRow("diff")}</Button>}
                      {/* ONE ENDING. Three buttons all ended the session and differed only in what they
                          wrote down - a result, a handover note, or nothing - and the labels buried the
                          half they shared (the owner, 2026-09-16: "save result vs end session vs stop
                          session???"). It writes the session up either way now: on a run that finished
                          that is its result, and on one that did not it is where it got to, which is
                          what the handover note was for.
                          Task completion stays separate (PW-217/218): this ends the AGENT. */}
                      <Button size="small" variant="outlined" sx={liveCtl} disabled={!!wrapping} startIcon={<DoneAllIcon sx={{ fontSize: 13 }} />}
                        title="Writes up what this session did, ends it, and drafts the reply to whoever asked. The task stays open until you complete it."
                        onClick={wrapUp}>{labelOfRow("save-end")}</Button>
                      {/* A STUCK AGENT (a rate limit, a token ceiling) had only the two moves above, and neither gets the work done:
                          the way on is another agent - startCodingAgent pauses this one and files its handover first */}
                      {!isGeneral && agentState === AGENT.waiting && subState(term) === "stalled" && (
                        <Button size="small" variant="contained" disableElevation sx={liveCtl} startIcon={<RefreshIcon sx={{ fontSize: 13 }} />}
                          title="Pauses this one (its notes are kept) and starts a fresh agent - you choose which."
                          onClick={() => setRestartOpen(true)}>{labelOfRow("run-another")}</Button>
                      )}
                    </Box>
                  )}
                  {/* WHAT THE AGENT DID AND THOUGHT, one card for every CLI and the general agent (AgentRecord): what happened,
                      its last message (named the reply only when the draft is in it), what it made, and every step behind one button. It was
                      two blocks (a saved answer with no report, or the report) reading two different stores. */}
                  {/* ...and a session that ENDED is this one block too - its state, what happened, More - where a "Session closed"
                      card under the step told the same run a second time, and the story above it a third (the owner, 2026-10-12) */}
                  {!sessionView && hasRecord && (
                    <Box sx={{ mt: 1.1, pt: 1.1, borderTop: `1px solid ${BORDER}`, "&:empty": { display: "none" } }}>
                      {/* a chat shows its pages under the answer that made them; a terminal's are kept here */}
                      <AgentRecord {...recordProps} story={storyAt === "record" ? story : null} inChat={workspaceMode === "general"} />
                      {diffRun && <Box sx={{ mt: 0.75 }}><DiffBlock text={diffRun.DiffText} /></Box>}
                    </Box>
                  )}
                  {(restartOpen || (!term?.alive && !liveRun && !isGeneral && !report && !detail?.transcript))
                    && !(canvas && restartOpen) && nextRunForm}
                  {isGeneral && !generalStarted && (
                    <Box sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      {/* the same three answers the hand-off asks - this door had none at all */}
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mb: 1 }}>
                        <AgentPicker agents={agents} models={models} kinds={kinds} agent={run.agent} model={run.model}
                          generalBrains={generalBrains} pick={run.pick || ""} has={ownProfile}
                          onPick={(p) => setRun((r) => ({ ...r, pick: p }))}
                          onAgent={(a) => setRun((r) => ({ ...r, agent: a }))}
                          onModel={(m) => setRun((r) => ({ ...r, model: m }))} size={28} />
                      </Box>
                      {/* on the canvas the button is the row's (rowVerbs: send-general); the pickers above are what it uses */}
                      {!inRow && <Button size="small" variant="contained" disableElevation disabled={!!startingAgent}
                        startIcon={startingAgent === "general" ? <CircularProgress size={11} /> : <TaskuaryMark size={13} />}
                        onClick={startGeneralAgent}>
                        {startingAgent === "general" ? "Starting…" : labelOfRow("send-general")}
                      </Button>}
                      <Typography variant="caption" sx={{ color: FAINT, ml: inRow ? 0 : 1 }}>
                        {inRow ? "Send to agent starts it with these choices, this task and its messages."
                          : "Starts the regular assistant with this task and its messages."}
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
                      {/* plain words on the facts (the audit, 2026-10-17): "role" and "brain" were the app's own vocabulary */}
                      {runRole && <Box sx={{ ...chipBtnStatic }} title="Which instructions this agent follows - set in Settings.">
                        <Box component="span" sx={{ color: FAINT, fontWeight: 600 }}>works as</Box>&nbsp;{runRole}</Box>}
                      {brainPill && <Box sx={{ ...chipBtnStatic }}
                        title={brainPill === detail?.ranOn?.brain ? "The AI that did this work. Which AI the agents use is set in Settings, not per task."
                          : "The AI that does the work. Which AI the agents use is set in Settings, not per task."}>
                        <Box component="span" sx={{ color: FAINT, fontWeight: 600 }}>AI</Box>&nbsp;{brainPill}</Box>}
                      {/* the repository pill only where a coding tool is connected (B3) */}
                      {!isGeneral && canCode && <Button size="small" variant="outlined" sx={chipBtn}
                        startIcon={<AccountTreeIcon sx={{ fontSize: 14, color: "#55697a" }} />}
                        title={heldRepo ? "Not started: it needs to know where the code is - it starts once you choose" : btnHint("pick_repo")}
                        onClick={pickRepo}>{repoOf(t) || PICK_CODE.toLowerCase()}</Button>}
                      {!isGeneral && canCode && heldRepo && !repoOf(t) && <Typography variant="caption" sx={{ color: "#6b2733", fontWeight: 600 }}>not started - {PICK_CODE.toLowerCase()}</Typography>}
                    </Box>
                  )}
                  </>}
                </Box>}
                {repoPick && (
                  <Box sx={{ ...card, mb: 1, bgcolor: PANEL2 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
                      <AccountTreeIcon sx={{ fontSize: 16, color: "#55697a" }} />
                      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13, flex: 1 }}>
                        Which code is this about?
                      </Typography>
                      <IconButton aria-label="Close repository picker" size="small" onClick={() => { setRepoPick(false); setResumeAfterRepo(null); }}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
                    </Box>
                    <RepoPicker taskId={selected} agent={term?.agent || run.agent}
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
                {/* ...while its session is live, or when you open Agent work yourself: drawn whenever the task had a chat, it
                    stayed on screen after End session with Close out folded under it, where a coding session's terminal goes
                    (the owner, 2026-10-13: "it should just move to the close out section when you close out agent run") */}
                {workspaceMode === "general" && (liveSession || stage === "agent") ? (
                  /* the chat is this task's session: it gets the room a terminal gets, not the
                     height of its own content squeezed between the cards above and below it. On the canvas that room is the
                     VIEW'S: the chat body is a size container (assistantView.css .tq-chat-body) and the view is 100cqh + 14px tall,
                     so the agent takes all of it under the title and its own heading (the Task strip is scrolled above - agentUp):
                     its input on screen, Close out one scroll below. A fixed 420px floor in a shorter view put the input and the last
                     lines out of sight. 78px = the title strip + this step's heading + 8px under the chat, less the 26px the view gained. */
                  <Box sx={{ flex: "1 1 0", minHeight: canvas ? "max(240px, calc(100cqh - 78px))" : { xs: 360, md: 420 }, mb: canvas ? 1 : 0,
                    display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                    <React.Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
                      <GeneralWorkspace key={`${t.TaskId}-${generalRevision}`} task={t} compact onSession={generalSession} onOpenReports={onGoReports}
                        toolsAt={canvas ? chatTools : null} />
                    </React.Suspense>
                  </Box>
                ) : workspaceMode === "wrapping" ? (
                  <ClosingCard mode={wrapping} />
                ) : writingUp === selected ? (
                  /* Stop and save's write-up runs on the server (writeup.py): the task stays usable, this line until the report lands */
                  <Typography variant="caption" data-tq-writing-up="" sx={{ color: "#6f8a6e", display: "block", mt: 0.5 }}>
                    Closing the session and writing up what is on screen — the agent is not asked anything.
                  </Typography>
                ) : workspaceMode === "live" && peek ? (
                  /* the session, folded to one line while the task behind it is being read */
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.8, borderRadius: 1.5,
                    border: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: 99, bgcolor: "#6f8a6e", flexShrink: 0 }} />
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 0, color: INK, fontSize: 12.5 }} noWrap>
                      {agentState === AGENT.waiting ? says(subState(term), agentName(t)) : `${agentName(t)} is working`} in its session — it keeps running while you read the task.
                    </Typography>
                    <Button size="small" variant="contained" disableElevation sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                      onClick={() => setPeek(false)}>Back to the agent</Button>
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
                    <Box ref={termBox} sx={{ flex: "1 1 0", minHeight: { xs: 360, md: 0 }, position: "relative",
                      display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
                      <TerminalPane sid={term.sid} height="100%" onExit={() => findTerm(selected)} />
                    </Box>
                    {/* pages the session published with Claude's Artifact tool, under the session that made them */}
                    <Box sx={{ mt: 0.75, flexShrink: 0, "&:empty": { display: "none" } }}>
                      <PublishedPages pages={(detail?.artifacts || []).filter(isPublished)} />
                    </Box>
                    {/* NO ANSWER BOX UNDER THE PANE (the owner, 2026-10-13: "we know it's waiting on us from the emoji and we will
                        respond in chat"): the asks box and the type-in-for-later line said again what the rail's mark and the
                        terminal already say. Answer in the terminal, or in the chat - the Assistant draws a question's options. */}
                    {wrapping && (
                      <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mt: 0.5 }}>
                        Closing the session and writing up what is on screen — the agent is not asked anything.
                      </Typography>
                    )}
                  </>
                ) : null}

                {!sessionView && <Box ref={closeOutRef} data-tq-closeout="" sx={{ ...card, ...step, mt: 0, p: 1.5, py: stage === "reply" ? 1.5 : 1.1, flexShrink: 0 }}>
                  {/* CLOSE OUT, not Reply (the owner, 2026-09-27): what finishes a task is not always a reply - a pull
                      request merges, an issue closes. The label only: the stage's key is still "reply" everywhere. */}
                  <WorkflowHeading number="3" title="Close out"
                    description={term?.alive
                      ? (replyMessage ? "Close-out controls return when the agent stops." : "No inbound sender is attached to this task.")
                      : closeoutRv
                        ? (replyMessage ? "Your reply to the sender and the last act on GitHub - approving them runs only that; Mark done closes the task." : "The last act on GitHub - approving it runs only that; Mark done closes the task.")
                      : ended && !pendingReview ? "It ended upstream, so no reply is owed. What already went out is below."
                      : replyMessage
                        ? (owesEmails ? "What goes back to the sender, and the emails this task owes. Sending never closes the task - Mark done does."
                          : pendingReview ? "What goes back to the sender." : "What goes back to the sender. Sending it never closes the task - Mark done does.")
                      : owesEmails
                        ? "The emails this task owes - each waits for your yes. Mark done closes the task."
                        : "Nobody sent this one, so there is nobody to answer. Work it, or write what you found on the task."}
                    chip={emailsWaiting ? <LifecycleChip kind="emails" phase={`${emailsWaiting} waiting`} compact />
                      : <LifecycleChip kind="reply" phase={replyMessage ? replyState : "not available"} compact />}
                    /* oxblood is the one colour that means "this is on you" - a draft or an email waiting for your yes. Every card
                       wore it on this step, whatever it held (the 2026-10-07 design pass) */
                    tone={pendingReview || emailsWaiting ? PALETTE.oxblood : PALETTE.oat} {...stageProps("reply")}
                    action={!inRow && stage !== "reply" && replyMessage
                      ? <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center", gap: 0.35 }}>
                          <Button size="small" variant="contained" disableElevation disabled={!!openingReply}
                            sx={{ fontSize: 11, minHeight: 26, py: 0, px: 1.25 }}
                            startIcon={openingReply ? <CircularProgress size={11} /> : <ForwardToInboxIcon sx={{ fontSize: 14 }} />}
                            onClick={() => (pendingReview ? setOpenStage("reply") : openReply(true))}>
                            {openingReply ? "Drafting…" : replyPrimary}</Button>
                          <Tooltip title={`${labelOfRow("ask-sender")} - ${hintOfRow("ask-sender")}`}>
                            <IconButton size="small" sx={{ color: "#8a3646" }} onClick={() => setAskSenderOpen(true)}>
                              <ChatBubbleOutlineIcon sx={{ fontSize: 15 }} /></IconButton>
                          </Tooltip>
                        </Box>
                      : null} />
                  {/* WHAT CLOSED IT, where it was closed (the owner, 2026-10-19: "i hit mark done on close out but agent work tab opened up
                      again - why is it not just staying in close out showing what closed out"): the close, when, and the note it was closed with */}
                  {stage === "reply" && t.Status === "done" && <Box data-tq-closed="" sx={{ mt: 1 }}>
                    <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>
                      ✓ {btn("close")}{t.ClosedAt ? ` ${ago(t.ClosedAt)}` : ""}</Typography>
                    {closedNote && <Typography variant="body2" sx={{ color: DIM, mt: 0.25, whiteSpace: "pre-wrap" }}>{closedNote}</Typography>}
                  </Box>}
                  {/* STOP AND SAVE'S WRITE-UP, where its draft will stand (writeupState.js): the job's own stage until the draft
                      replaces this block in place - or, if it stopped, that it did, with Try again and the reply button */}
                  {stage === "reply" && writeup && <WriteupBlock view={writeup} hasReply={!!replyMessage} onRetry={canWrap || pressedHere ? wrapUp : null}
                    onDraft={() => openReply(true)} draftLabel={replyPrimary} />}
                  {stage === "reply" && !writeup && ((pendingReview || proposals.length || replyMessage || owesEmails || ended || sentOutside.length) ? (
                    <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
                      {/* THE CONVERSATION OVER THE DRAFT (the owner, 2026-10-15: "add it to close out too"), CONDENSED: the latest lines of the
                          conversation being answered, newest first - the draft answers the top one - and the rest a click away in Task. The
                          full bubbles here and again in step 1 were one conversation drawn twice (the owner, 2026-10-16: "in close out you
                          have the full chat, it's too confusing. full chat should be in task (condensed and full). in close out chats
                          condensed version?"). An email task reads the same rows, so Close out reads one way for every channel. */}
                      {closeGroup && <Box data-tq-close-conversation="" sx={{ mb: 1.2, minWidth: 0, maxWidth: 900 }}>
                        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap", mb: 0.25, minWidth: 0 }}>
                          <Typography sx={{ ...label }}>The conversation</Typography>
                          <Link component="button" type="button" underline="hover" onClick={seeWholeConversation}
                            sx={{ ml: "auto", fontSize: 12 }}>the whole conversation is in Task</Link>
                        </Box>
                        <ConversationRows rows={latestRows(closeGroup, 4)} open={openMsg} onOpen={setOpenMsg} />
                      </Box>}
                      {/* THE INVITE, AND WHAT IT CLASHES WITH (calwrite.of_task), over the row's Accept / Decline / Propose a new time */}
                      {calAsk?.invite && <Typography data-tq-invite="" variant="body2" sx={{ mb: 1, color: INK }}>{calAsk.line}
                        {!!calAsk.clash && <Box component="span" sx={{ color: "#7a2f3c", fontWeight: 600 }}> - it {calAsk.clash}</Box>}</Typography>}
                      {/* the emails that close it (slots.py), where a task's close is decided - each with its own draft */}
                      <SlotList taskId={t?.TaskId} checklist={detail?.checklist || []} reviews={detail?.reviews || []}
                        onChanged={() => { loadDetail(selected); loadTasks(); onChanged?.(); }} />
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
                          {!pendingReview && !inRow && (
                            <Button size="small" variant="contained" disableElevation disabled={!!openingReply}
                              sx={primaryBtn}
                              startIcon={openingReply ? <CircularProgress size={12} /> : <ForwardToInboxIcon sx={{ fontSize: 16 }} />}
                              title="Drafts the reply here, from this task's own context. Nothing is sent until you approve it."
                              onClick={() => openReply(true)}>{openingReply ? "Drafting…" : replyPrimary}</Button>
                          )}
                          {!inRow && <Button size="small" variant="outlined" sx={barBtn}
                            startIcon={<ChatBubbleOutlineIcon sx={{ fontSize: 15, color: "#8a3646" }} />}
                            title="Drafts a question to the sender. It waits here for your approval; nothing is sent now."
                            onClick={() => setAskSenderOpen(true)}>{labelOfRow("ask-sender")}</Button>}
                          <Box sx={{ flex: 1, minWidth: 12 }} />
                          <Typography variant="caption" sx={{ color: FAINT, textAlign: "right", maxWidth: 320 }}>
                            {/* no More button: with these on the surface there is nothing left to hide */}
                            {pendingReview
                              ? (inRow ? "" : "Nothing is sent until you approve it.")
                              : sentReview
                              ? `Sent${sentReview.DecidedAt ? ` · ${fmtDateTime(sentReview.DecidedAt)}` : ""}. ${String(t?.Status || "") === "done" ? "The task closed with it." : "The task stays open while its agent is still working."}`
                              : inRow ? "" /* the chip already says "not drafted" */ : "A reply is optional. Starting or stopping an agent does not send one."}
                          </Typography>
                        </Box>
                      )}
                      {/* THE DECISION ITSELF, on the task that owns it - the same component the review
                          queue mounts, so two surfaces cannot say different things about one draft. */}
                      {pendingReview ? (
                        <ReviewDecision review={pendingReview} closeout={closeoutRv} toRow={inRow} onMarkDone={askFinish} onSent={sent} onRemind={(e, a) => setRemindAt(a || e?.currentTarget)}
                          onEmailInstead={() => setEmailOpen(true)}
                          onChanged={() => { loadDetail(selected); loadTasks(); onChanged?.(); }} />   /* the list's row moves too (T19) */
                      ) : (
                        <>
                          {/* WHAT ALREADY WENT OUT, before any envelope: the item ending upstream (the agent's merge) and what was sent
                              from outside a draft here. With neither, a merged pull request's Close out was a bare "To <sender>" over
                              nothing (the owner, 2026-10-12: "i hit read the draft and nothing is there anyway?") */}
                          {ended && (
                            <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mt: 1.1, minWidth: 0 }}>
                              <Typography sx={{ ...label, flexShrink: 0 }}>Ended</Typography>
                              <Typography variant="body2" sx={{ color: INK, flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{ended.text}</Typography>
                              {ended.at && <Typography variant="caption" sx={{ color: FAINT, flexShrink: 0 }}>{fmtDateTime(ended.at)}</Typography>}
                            </Box>
                          )}
                          {/* the thread's own drawing - who and WHEN first, a rule on the left, newest first - not a grey box with its
                              date pushed off the right edge (the owner, 2026-10-14: "you need time and date when each one was sent") */}
                          {sentApart.map((m) => (
                            <Box key={m.MessageId} sx={{ mt: 0.9, pl: 1, borderLeft: `2px solid ${BORDER}`, maxWidth: 900 }}>
                              <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>
                                Sent by you{m.SourceName ? ` · ${m.SourceName}` : ""}{m.SentAt ? ` · ${fmtDateTime(m.SentAt)}` : ""}
                              </Typography>
                              <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
                                display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                {cleanText(m.OwnText || m.BodyText)}</Typography>
                              {m.SourceLink && <Button size="small" sx={{ mt: 0.3, fontSize: 11, minHeight: 0, p: 0 }} href={m.SourceLink} target="_blank" rel="noreferrer">Open where it was sent</Button>}
                            </Box>
                          ))}
                          {/* THE ENVELOPE over what was sent, read from the same Deliver blob
                              (replyDelivery.js). Read-only: this one is history, not a decision. Only where there is a reply:
                              a task with nobody to answer read "To You" under its own emails (2026-10-09) - and only over a letter
                              once the item has ended, where it named a sender nothing is going to */}
                          {(replyMessage || sentReview) && (!ended || sentReview || unsentReview) && (
                          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mt: 1.1, minWidth: 0 }}>
                            <Typography sx={{ ...label, flexShrink: 0 }}>To</Typography>
                            <Typography variant="body2" noWrap sx={{ color: INK, fontWeight: 600 }}>
                              {replyContext(sentReview || sourceMessage)}
                            </Typography>
                          </Box>)}
                          {replyCc.length > 0 && (
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mt: 0.6, flexWrap: "wrap", minWidth: 0 }}>
                              <Typography sx={{ color: ACCENT2, fontSize: 9.5, fontWeight: 600, letterSpacing: "1.5px", flexShrink: 0 }}>CC</Typography>
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
                          {/* the words that LEFT: an edit before the send is the FinalText - the draft read "keep it active" over a
                              mail that had said something else (2026-10-13) */}
                          {(sentReview?.FinalText || sentReview?.DraftText) && (
                            <Box sx={{ mt: 0.9, pl: 1, borderLeft: `2px solid ${BORDER}`, maxWidth: 900 }}>
                              <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>
                                What was sent{sentReview.DecidedAt ? ` · ${fmtDateTime(sentReview.DecidedAt)}` : ""}</Typography>
                              <Typography variant="body2" sx={{ color: DIM, lineHeight: 1.55, whiteSpace: "pre-wrap",
                                overflowWrap: "anywhere", display: "-webkit-box", WebkitLineClamp: 4,
                                WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                {sentReview.FinalText || sentReview.DraftText}</Typography>
                            </Box>
                          )}
                          {/* the draft closed without sending stays readable here, the task done or not */}
                          {unsentReview && (
                            <Box sx={{ bgcolor: PANEL2, border: `1px dashed ${BORDER}`, borderRadius: 1.25,
                              px: 1.1, py: 0.85, mt: 0.9 }}>
                              <Typography sx={{ ...label, display: "block" }}>Not sent - closed without sending</Typography>
                              <Typography variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                                {unsentReview.DraftText}</Typography>
                              {/* ...and it can still go: the draft comes back to send, the task done or not (T11) */}
                              {hasCorrespondent(replyMessage) && (
                                <Button size="small" sx={{ mt: 0.75, fontSize: 11 }} onClick={() => {
                                  const id = selected;
                                  api.post(`/api/reviews/${unsentReview.ReviewId}/reopen`)
                                    .then(() => { if (!stale(id)) { loadDetail(id); setOpenStage("reply"); } })
                                    .catch((e) => { if (!stale(id)) setErr(e?.response?.data?.detail || "Could not bring the draft back"); });
                                }}>Bring it back to send</Button>
                              )}
                            </Box>
                          )}
                        </>
                      )}
                      {/* A PROPOSAL IS THE SAME KIND OF ASK, so it shares this section rather than
                          taking a fourth stage: lanes.json has one `approve` lane for a reply and an
                          action alike, and one lane on the rail is one section on the page. */}
                      {proposals.length > 0 && (
                        <Box sx={{ mt: 1.4, pt: 1.1, borderTop: `1px solid ${BORDER}` }}>
                          <Typography sx={{ ...label, display: "block", mb: 0.5 }}>
                            {proposals.length === 1 ? "Also waiting on you" : `Also waiting on you · ${proposals.length}`}
                          </Typography>
                          {proposals.map((p) => (
                            <ReviewDecision key={p.ReviewId} review={p} toRow={inRow && !pendingReview && proposals.length === 1}
                              onChanged={() => { loadDetail(selected); loadTasks(); onChanged?.(); }} />   /* the list's row moves too (T19) */
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

                {!sessionView && <Fold title={`Context & history · ${plural(taskMessages.length, "message")} · ${plural(detail.comments.length, "note")}`}>
                  <Typography sx={{ ...label, display: "block", mb: 0.65 }}>Messages</Typography>
                  {taskMessages.map((m) => {
                    const route = detail.routes.find((r) => r.MessageId === m.MessageId);
                    const mine = m.Status === "context" || m.Direction === "out";
                    return (
                      <Box key={m.MessageId} sx={{ display: "flex", justifyContent: mine ? "flex-end" : "flex-start", mb: 0.85 }}>
                      <Box sx={{ width: "fit-content", maxWidth: { xs: "96%", md: "84%" }, p: 1.15,
                        bgcolor: mine ? "#e9e3d8" : "#fff",
                        borderRadius: mine ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                        border: `1px solid ${mine ? "#d8d0c4" : BORDER}` }}>
                        <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexWrap: "wrap" }}>
                          <ChannelIcon channel={m.Channel} sx={{ color: FAINT }} />
                          <Chip size="small" label={m.ReviewSent ? "sent reply" : mine ? "your reply" : "inbound"}
                            sx={{ height: 17, fontSize: 9.5, fontWeight: 600,
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
                  <Typography sx={{ ...label, display: "block", mb: 0.35 }}>Notes & activity</Typography>
                  <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", tableLayout: "auto" }}>
                    <tbody>{detail.comments.map((c) => <CommentRow key={c.CommentId} c={c} />)}</tbody>
                  </Box>
                  {!detail.comments.length && <Typography variant="caption" sx={{ color: FAINT }}>No notes yet.</Typography>}
                  <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                    <TextField fullWidth placeholder="Add a note (humans only)" value={comment}
                      onChange={(e) => setComment(e.target.value)} onKeyDown={(e) => e.key === "Enter" && post()} />
                    <Button size="small" disabled={posting} onClick={post}>{posting ? "Posting…" : "Post"}</Button>
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
              {/* THE TASKS TAB'S BAR, AT THE FOOT (the owner, 2026-10-16: "the buttons stay on bottom by the prompt box like always. No
                  buttons there."). The canvas draws these as its row over the chat line (rowVerbs, ActionRow); the Tasks tab has no
                  row, so its view keeps the same moves here, under the sections, instead of inside the Task card. The two endings
                  first, then a rule, then the reroutes, then Change - what the task's pills used to set. While a session fills the page
                  the header carries them (headControls). */}
              {/* the Advisor's suggestion over the bar, said and not pressed: the buttons below stay as they are (U12) */}
              {!inRow && !sessionView && notDone && taskAdvice && (
                <Typography data-tq-task-advice="" role="status" sx={{ px: 1.75, py: 0.75, borderTop: `1px solid ${BORDER}`, bgcolor: "#fff",
                  fontSize: 12.5, color: DIM, flexShrink: 0, overflowWrap: "anywhere" }}>
                  <Box component="span" sx={{ color: INK, fontWeight: 600 }}>Suggested: {taskAdvice.label}</Box>
                  {" - "}{suggestion(taskAdvice.line, taskAdvice.label, taskAdvice.verb)}
                </Typography>
              )}
              {!inRow && !sessionView && (
                <Box data-tq-task-bar="" sx={{ display: "flex", alignItems: "center", gap: 0.8, rowGap: 0.6, flexWrap: "wrap", flexShrink: 0,
                  px: 1.75, py: 1, borderTop: `1px solid ${BORDER}`, bgcolor: "#fff" }}>
                  {notDone ? <>
                    <Button size="small" variant="contained" disableElevation startIcon={finishing ? <CircularProgress size={14} color="inherit" /> : <DoneAllIcon sx={{ fontSize: 16 }} />}
                      sx={primaryBtn}
                      title={markDoneHint}
                      disabled={finishing} onClick={askFinish}>{finishing ? "Marking done…" : labelOfRow("done")}</Button>
                    <Button size="small" variant="outlined" startIcon={<BlockIcon sx={{ fontSize: 15 }} />}
                      sx={{ ...barBtn, color: "#7a2f3c", borderColor: "#e0c6cb" }}
                      title={NAT_TITLE}
                      onClick={notATask}>{labelOfRow("nat")}</Button>
                    <RemindMe task={t} sx={barBtn} onDone={reminded} onLeave={onLeave} onStay={onStay} live={liveSession} />
                    <Divider orientation="vertical" flexItem sx={{ mx: 0.4, my: 0.6, borderColor: BORDER }} />
                    <Button size="small" variant="outlined" sx={barBtn}
                      startIcon={<ForwardToInboxIcon sx={{ fontSize: 16, color: "#55697a" }} />}
                      title="Not ours to do — the AI writes the forward, you send it."
                      onClick={() => setHandoff(true)}>{labelOfRow("hand")}</Button>
                    <Button size="small" variant="outlined" sx={barBtn}
                      startIcon={<CallSplitIcon sx={{ fontSize: 16, color: "#6f8a6e" }} />}
                      title="Two jobs in here, or a duplicate? Break it in two, or fold it into the task it repeats."
                      onClick={() => setReshape(true)}>{labelOfRow("reshape")}</Button>
                    <Button size="small" variant="outlined" sx={barBtn} endIcon={<ExpandMoreIcon sx={{ fontSize: 16 }} />}
                      title={`Who does it, the priority${canCode ? ", who it is assigned to, or the repository" : " or who it is assigned to"}`}
                      onClick={(e) => setPick({ what: "menu", at: e.currentTarget })}>Change</Button>
                  </> : (
                    <Button size="small" variant="outlined" startIcon={<RefreshIcon sx={{ fontSize: 15 }} />}
                      title="Reopens the task only. No agent starts until you choose one."
                      onClick={reopen}>{labelOfRow("reopen")}</Button>
                  )}
                </Box>
              )}
            </>
          )}
        </Box>
      </Box>
      {/* THE MENUS THE PILLS WERE: the dropdowns' changes, now the task tools (change above), reached from the row (canvas) or Change (Tasks tab) */}
      {t && <Menu open={!!pick} anchorEl={pick?.at || null} onClose={() => setPick(null)}>
        {pick?.what === "menu" && [
          <MenuItem key="kind" sx={{ fontSize: 12.5 }} onClick={() => setPick({ ...pick, what: "kind" })}>Who does it · {kindLabel(t.Kind || "task")}</MenuItem>,
          <MenuItem key="priority" sx={{ fontSize: 12.5 }} onClick={() => setPick({ ...pick, what: "priority" })}>Priority · {t.Priority || "normal"}</MenuItem>,
          <MenuItem key="assign" sx={{ fontSize: 12.5 }} onClick={() => setPick({ ...pick, what: "assign" })}>Assigned to · {t.Assignee ? assigneeLabel(t.Assignee) : "nobody"}</MenuItem>,
          ...(!isGeneral && canCode ? [<MenuItem key="repo" sx={{ fontSize: 12.5 }} onClick={() => { setPick(null); pickRepo(); }}>Repository · {repoOf(t) || "pick a repo"}</MenuItem>] : []),
        ]}
        {pick?.what === "kind" && (KINDS.includes(t.Kind || "task") ? KIND_OPTIONS : [{ key: t.Kind, label: t.Kind, hint: "legacy task type" }, ...KIND_OPTIONS])
          .filter((o) => o.key !== "coding" || canCode || t.Kind === "coding").map((o) =>
          <MenuItem key={o.key} selected={o.key === (t.Kind || "task")} sx={{ py: 0.6 }} onClick={() => { setPick(null); if (o.key !== (t.Kind || "task")) change("task.set_kind", { kind: o.key }); }}>
            <ListItemText primary={o.label} secondary={o.hint} primaryTypographyProps={{ fontSize: 12 }} secondaryTypographyProps={{ fontSize: 10.5 }} />
          </MenuItem>)}
        {/* no Status here: status is DERIVED - Start, Mark done, Remind me and Reopen set it (T12) */}
        {pick?.what === "priority" && PRIORITIES.map((p) =>
          <MenuItem key={p} selected={p === (t.Priority || "normal")} sx={{ fontSize: 12 }} onClick={() => { setPick(null); if (p !== (t.Priority || "normal")) change("task.update", { priority: p }); }}>{p}</MenuItem>)}
        {pick?.what === "assign" && [
          ["", "unassigned"], ["owner", "you"], ...agents.map((name) => [agentAssignee(name), name]),
          ...(t.Assignee && t.Assignee !== "owner" && !assignedAgent(t.Assignee) ? [[t.Assignee, t.Assignee]] : []),
        ].map(([v, name]) =>
          <MenuItem key={v || "none"} selected={v === (t.Assignee || "")} sx={{ fontSize: 12 }} onClick={() => {
            setPick(null);
            if (v === (t.Assignee || "")) return;
            const worker = assignedAgent(v);
            change("task.update", { assignee: v || "none" });
            if (worker && agents.includes(worker)) setRun((r) => ({ ...r, agent: worker, model: "" }));
          }}>{assignedAgent(v) && <><TaskuaryMark size={12} />&nbsp; </>}{name}</MenuItem>)}
      </Menu>}
      {/* ── review the change: the widest drawer of the three, because code needs the room.
             Read-only by construction - it runs git diff and git status and nothing else, so
             opening it can never disturb what the agent is in the middle of. ── */}
      <Drawer anchor="right" open={!!diffOpen && !!t} onClose={() => setDiffOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 760 }, p: 2, bgcolor: PANEL2 } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <DifferenceIcon sx={{ fontSize: 18, color: "#6f8a6e" }} />
          <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14.5, flex: 1 }}>What has it changed?</Typography>
          {diff && !!diff.files?.length && (
            <Typography sx={{ ...mono, fontSize: 11.5, color: DIM }}>
              {plural(diff.files.length, "file")}
              <Box component="span" sx={{ color: "#47654a", ml: 1 }}>+{diff.added}</Box>
              <Box component="span" sx={{ color: "#6b2733", ml: 0.75 }}>−{diff.removed}</Box>
            </Typography>
          )}
          <Tooltip title="Ask git again — the agent may have written more since you opened this">
            <IconButton size="small" onClick={() => loadDiff(selected)}><RefreshIcon sx={{ fontSize: 16 }} /></IconButton>
          </Tooltip>
          <IconButton aria-label="Close changes" size="small" onClick={() => setDiffOpen(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {diff?.scope === "pr" ? `the pull request's own diff — ${diff.pr?.repo}#${diff.pr?.number}, what is being reviewed`
            : diffScope === "task" ? "what this task's agent changed" : "everything a push would carry, whoever wrote it"}
          {/* an agent told to "commit locally and stop" leaves a CLEAN tree - saying only
              "uncommitted work" over a finished job read as "it did nothing" */}
          {diffScope === "task" && diff?.commits?.length ? ` — ${plural(diff.commits.length, "commit")} of its own, unpushed` : ""}
          {diffScope === "checkout" && diff?.ahead ? ` — ${plural(diff.ahead, "commit")} ahead of ${diff.upstream}, plus anything uncommitted`
                       : diffScope === "checkout" && diff?.upstream ? ` — measured against ${diff.upstream}` : ""}
          {/* a shared checkout carries other tasks' work; the old drawer showed all of it as this
              task's - a database-only task wore two other agents' commits. The whole view is one
              click away, and says whose it is. */}
          <Box component="button" type="button" onClick={() => { const next = diffScope === "task" ? "checkout" : "task"; setDiffScope(next);
              api.get(`/api/tasks/${selected}/diff`, { params: { scope: next } }).then((r) => setDiff(r.data)).catch(() => {}); }}
            sx={{ ml: 1, color: "#55697a", cursor: "pointer", background: "none", border: 0, p: 0, font: "inherit", textAlign: "left", "&:hover": { textDecoration: "underline" } }}>
            {diff?.scope === "pr" ? "show the agent's checkout instead" : diffScope === "task" ? `show the whole checkout${diff?.checkout_files ? ` (${plural(diff.checkout_files, "file")})` : ""}` : (diff?.pr ? "back to the pull request's diff" : "back to this task's changes")}
          </Box>
        </Typography>
        {!diff ? <CircularProgress size={20} sx={{ m: 2 }} />
          : diff.why ? <Empty>{diff.why}</Empty>
            : diff.note && !diff.files?.length ? <Empty>{diff.note}</Empty>
            : <DiffFiles files={diff.files} cwd={diff.cwd} branch={diff.branch} />}
      </Drawer>

      {/* ── hand off: a right-hand drawer, so it cannot hide above a tall terminal ── */}
      {/* ...and "sending" is the hand-off put down at the press: the drawer goes with the task, the form stays mounted behind
          it so a send that fails brings back what was typed (2026-10-01) */}
      <Drawer anchor="right" open={handoff === true && !!t} onClose={() => setHandoff(false)} ModalProps={{ keepMounted: !!handoff }}
        PaperProps={{ sx: { width: { xs: "100%", sm: 460 }, p: 2, bgcolor: PANEL } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <ForwardToInboxIcon sx={{ fontSize: 18, color: "#55697a" }} />
          <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14.5, flex: 1 }}>Hand this to a person</Typography>
          <IconButton aria-label="Close handoff" size="small" onClick={() => setHandoff(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {t?.Title}
        </Typography>
        {handoff && <Handoff taskId={selected} onLeave={() => { setHandoff("sending"); onLeave?.(); }}
          onStay={(msg) => { setHandoff(true); onStay?.(msg); }} onSent={handedOff} />}
      </Drawer>

      {/* ── split / merge: the same right-hand drawer, because it is one question ── */}
      {/* ...and "merging" is this task folded away, put down at the press: the drawer goes with it, the form kept behind it so a
          fold that fails comes back with the reason (2026-10-01) */}
      <Drawer anchor="right" open={reshape === true && !!t} onClose={() => setReshape(false)} ModalProps={{ keepMounted: !!reshape }}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2, bgcolor: PANEL2 } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <CallSplitIcon sx={{ fontSize: 18, color: "#6f8a6e" }} />
          <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14.5, flex: 1 }}>Is this one job?</Typography>
          <IconButton aria-label="Close split or merge" size="small" onClick={() => setReshape(false)}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
        </Box>
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>
          {detail?.ref} · {t?.Title}
        </Typography>
        {reshape && <Reshape taskId={selected} taskRef={detail?.ref} onDone={reshaped} onLeave={(tid) => { if (tid === selected) { setReshape("merging"); onLeave?.(); } }}
          onStay={(tid, msg) => { if (tid === selected) { setReshape(true); onStay?.(msg); } }} />}
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
      {t && <EmailSomeone open={emailOpen} task={t} detail={detail} onClose={() => setEmailOpen(false)}
        onDrafted={() => { setEmailOpen(false); loadDetail(selected); loadTasks(); onChanged?.(); setOpenStage("reply"); }} />}
      {t && <ContinueBox task={t} anchor={continueAt} onClose={() => setContinueAt(null)} onDone={continued} />}
      {nextRunSlot && createPortal(<Box data-tq-run-card sx={{ border: "1px solid #d5d0c7", borderRadius: "12px", bgcolor: "#fffdfb", p: 1.5,
        "& > div": { mt: 0, pt: 0, borderTop: 0 } }}>{nextRunForm}</Box>, nextRunSlot)}
      {t && <CloseNote anchor={noteAt} taskRef={t.ref || ""} onClose={() => setNoteAtRaw(null)} onSubmit={closeWithNote} />}
      {t && inRow && <RemindPicker task={t} anchor={remindAt} onClose={() => setRemindAt(null)} onDone={reminded} onLeave={onLeave} onStay={onStay} live={liveSession} />}
      {calAsk && slotAt && <SlotPicker mid={calAsk.mid} act={slotAt.act} anchor={slotAt.at} onClose={() => setSlotAt(null)}
        onRefused={(data) => { setErr(data?.say || ""); setStartFail({ text: data?.say || "", fix: data?.fix || null, retry: false }); }}
        onPick={(slot) => calAnswer(slotAt.act, slot)} />}
    </>
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
        <Typography variant="caption" sx={{ ...mono, fontWeight: 600, fontSize: 10.5,
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
    <Box component="summary" sx={{ cursor: "pointer", color: FAINT, fontSize: 12, fontWeight: 600, py: 0.6, "&:hover": { color: INK } }}>{title}</Box>
    <Box sx={{ mt: 0.5 }}>{children}</Box>
  </Box>
);

// ONE ROW ON A DESKTOP, TWO ON A PHONE. The bar is flexShrink: 0 so it never loses a button, which
// at 390px meant it kept its width by sitting ON the title ("A… w…" under the continue button,
// the save button cut off at the card's edge, 2026-09-18). Below sm the bar takes the whole next line.
const WorkflowHeading = ({ number, title, description, chip, tone, folded, onToggle, action, tools }) => (
  <Box onClick={onToggle} sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexWrap: { xs: "wrap", sm: "nowrap" },
    cursor: onToggle ? "pointer" : "default", opacity: folded ? 0.72 : 1,
    "&:hover": onToggle ? { opacity: 1 } : undefined }}>
    <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: tone, color: "#fff",
      display: "grid", placeItems: "center", flexShrink: 0, fontSize: 11.5, fontWeight: 600 }}>
      {number}
    </Box>
    <Box sx={{ minWidth: 0, flex: 1 }}>
      <Typography sx={{ color: INK, fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{title}</Typography>
      {description && !folded && <Typography sx={{ color: FAINT, fontSize: 12, display: "block", lineHeight: 1.4 }}>{description}</Typography>}
    </Box>
    {/* the one action a stage cannot afford to hide when it folds. Its click is its own, not the fold's. */}
    {action && <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", flexShrink: 0, flexBasis: { xs: "100%", sm: "auto" }, order: { xs: 9, sm: 0 } }}>{action}</Box>}
    {tools && <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", flexShrink: 1, minWidth: 0 }}>{tools}</Box>}
    {chip}
    {onToggle && <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0,
      transform: folded ? "rotate(-90deg)" : "none", transition: "transform .15s" }} />}
  </Box>
);
