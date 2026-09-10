import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive, ThreadPrimitive, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, Chip, CircularProgress, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/ArrowUpward";
import EventRepeatIcon from "@mui/icons-material/EventRepeat";
import TerminalIcon from "@mui/icons-material/Terminal";
import ViewDayIcon from "@mui/icons-material/ViewDay";
import FunctionsIcon from "@mui/icons-material/Functions";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DoneRoundedIcon from "@mui/icons-material/DoneRounded";
import AddCommentOutlinedIcon from "@mui/icons-material/AddCommentOutlined";
import api from "./api.js";
import { streamAssistant, toolTarget } from "./assistantStream.js";
import { wantsAsk, wantsBrowser, withoutAsk } from "./newTask.js";
import { paneFor } from "./generalPane.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, workOf, doingNow, trailText, turnStart, elapsedText } from "./agentWork.js";
import { Md } from "./md.jsx";
import { SessionPane, TerminalPane } from "./TerminalView.jsx";
import SemanticPanel from "./SemanticPanel.jsx";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import "./generalWorkspace.css";
import { TaskuaryMark } from "./ui.jsx";

const savedView = () => localStorage.getItem("taskuary_general_view") || "assistant";
const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();
const initial = (messages) => (messages || []).map((m) => ({
  ...m,
  createdAt: m.createdAt ? new Date(String(m.createdAt).replace(" ", "T") + (String(m.createdAt).includes("Z") ? "" : "Z")) : undefined,
}));

const traceParts = (events, keepStart = true) => {
  const tools = new Map();
  const progress = [];
  let structured = false;
  for (const event of events || []) {
    if (event.type === "tool_call") {
      structured = true;
      const id = event.detail?.tool_call_id || `${event.name}-${tools.size}`;
      const args = event.detail?.args || {};
      tools.set(id, { type: "tool-call", toolCallId: id, toolName: event.name || "tool", args,
        argsText: JSON.stringify(args) });
    } else if (event.type === "tool_result") {
      const id = event.detail?.tool_call_id || event.name;
      const old = tools.get(id);
      if (old) tools.set(id, { ...old, result: { output: event.detail?.result || "" },
        isError: !!event.detail?.is_error });
    } else if (event.type === "start") {
      // "Agent progress: Started Claude Code · coder (your CLI)" is the header's own words in a box
      // labelled progress, and on a work window the band states who started and when (the owner's
      // screenshots, 2026-09-08). The dock has no band, so it keeps the line.
      if (keepStart) progress.push(`Started ${event.session?.provider || "the selected agent"}`);
    } else if (event.type === "progress" && event.detail) {
      structured = true; progress.push(String(event.detail));
    } else if (event.type === "live" && !structured && event.detail) {
      progress.push(String(event.detail));
    } else if (event.type === "error") {
      progress.push(`⚠ ${event.detail?.result || "The assistant could not answer."}`);
    }
  }
  return [...tools.values(), ...(progress.length ? [{ type: "reasoning", text: progress.join("\n\n") }] : [])];
};

// assistant-ui owns the response being streamed in the currently mounted pane. The task's
// session owns it when this pane is not mounted. Rehydrate that same tool/progress trace when a
// user switches back, and attach it to the filed answer once the run is complete.
export const messagesWithTrace = (messages, session, keepStart = true) => {
  const out = (messages || []).map((m) => ({ ...m, content: [...(m.content || [])] }));
  const parts = traceParts(session?.trace, keepStart);
  if (!parts.length) return out;
  if (session?.busy) {
    out.push({ id: `live-${session.sid}-${session.trace_revision || 0}`, role: "assistant", content: parts });
    return out;
  }
  for (let i = out.length - 1; i >= 0; i -= 1) {
    if (out[i].role === "assistant") { out[i].content = [...parts, ...out[i].content]; break; }
  }
  return out;
};

// SOMETHING IS HAPPENING. An API brain can think for a minute with nothing to stream, so a
// progress card reading "Started Azure OpenAI (API)" and then sitting still looks frozen (owner,
// 2026-09-07). The same dots whichever backend answers - an API connector or a CLI agent - and
// they show for a turn this pane is streaming as well as one that is running without it.
const Thinking = ({ provider }) => (
  <div className="tq-aui-thinking" role="status" aria-live="polite">
    <i /><i /><i />
    <span>{provider ? `${provider} is working…` : "Working on it…"}</span>
  </div>
);

// AN AGENT AT WORK, in one band. The machinery was all there - a CLI brain really does emit its
// tool calls, and the window really did draw them - but it drew eight identical grey rows each
// ending in the word COMPLETE, a box labelled "Agent progress" holding the start line and a model
// id, and put the only live signal in the smallest type on the page, underneath everything. It
// reported mechanism; it never said who was working, how far in, how long, or what it had got
// (the owner, 2026-09-08: "It doesn't look like an agent that got you").
//
// Four facts, said once, above the trail. Nothing here is new information - the trace and the task
// already carried all of it (agentWork.js).
const AgentBand = ({ name, provider, work, since }) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const doing = doingNow(work), trail = trailText(work);
  return (
    <div className="tq-aui-band" role="status" aria-live="polite">
      <div className="tq-aui-band-head">
        <span className="tq-aui-band-dot" />
        <b>{name}</b><span>is working</span>
        <em>{since ? elapsedText(now - since) : provider || ""}</em>
      </div>
      <div className="tq-aui-band-now">
        {doing || (provider ? `${provider} is thinking…` : "Thinking…")}
        {work.steps.length > 1 && <span className="tq-aui-band-step"> — step {work.steps.length}</span>}
      </div>
      {/* one segment per step it has actually taken. No total: the agent never declares a plan, and
          a made-up denominator is a confident number that is wrong. */}
      {work.steps.length > 0 && (
        <div className="tq-aui-band-meter">
          {work.steps.map((st) => <span key={st.id} className={st.done ? "" : "on"} />)}
        </div>
      )}
      {trail && <div className="tq-aui-band-trail">✓ {trail}</div>}
      {/* ...and the one that answers "has it got hold of this?": not that it called eight tools,
          but that it is holding real sources on the right subject, before it has finished. */}
      {!!work.sources.length && (
        <div className="tq-aui-band-so">
          <span>what it has so far</span>
          <div>{work.sources.length} source{work.sources.length === 1 ? "" : "s"} —{" "}
            {work.sources.map((src) => <em key={src}>{src}</em>)}</div>
        </div>
      )}
    </div>
  );
};

// The speaker of the agent's turns. In the dock this IS Taskuary's assistant; on a work window it
// is the agent named on the task, and calling it "Taskuary" there was the fourth place one window
// wore the concierge's name.
const AgentNameCtx = React.createContext("Taskuary");

const AssistantText = ({ text }) => <Md text={text} />;
const AssistantReasoning = ({ text }) => text ? (
  <details className="tq-aui-progress" open>
    <summary>Agent progress</summary>
    <div>{text}</div>
  </details>
) : null;
const AssistantTool = ({ toolName, args, result, isError }) => {
  const state = isError ? "error" : result === undefined ? "running" : "complete";
  const target = toolTarget(args);
  return (
    <details className={`tq-aui-tool tq-aui-tool-${state}`}>
      <summary><span className="tq-aui-tool-dot" /> <b>{toolName}</b>{target && <span>{target}</span>}<em>{state}</em></summary>
      <pre>{JSON.stringify({ input: args, ...(result?.output ? { output: result.output } : {}) }, null, 2)}</pre>
    </details>
  );
};
const UserMessage = () => (
  <MessagePrimitive.Root className="tq-aui-message tq-aui-user">
    <div className="tq-aui-role">you</div>
    <div className="tq-aui-user-bubble"><MessagePrimitive.Parts /></div>
  </MessagePrimitive.Root>
);
const AssistantMessage = () => (
  <MessagePrimitive.Root className="tq-aui-message tq-aui-agent">
    <div className="tq-aui-role">{React.useContext(AgentNameCtx)}</div>
    <div className="tq-aui-agent-body">
      <MessagePrimitive.Parts components={{ Text: AssistantText, Reasoning: AssistantReasoning,
        tools: { Fallback: AssistantTool } }} />
    </div>
  </MessagePrimitive.Root>
);

const mentioned = (messages, kind) => {
  const text = (messages || []).slice(-6).map(textOf).filter(Boolean).join("\n");
  const pattern = kind === "review" ? /\brv(\d+)\b/gi : /(?:#task=|\bTQ-0*)(\d+)\b/gi;
  const hits = [...text.matchAll(pattern)];
  return hits.length ? Number(hits[hits.length - 1][1]) : null;
};

const reviewTarget = (r) => r.FromName && r.FromEmail ? `${r.FromName} <${r.FromEmail}>`
  : r.FromName || r.FromEmail || r.ConversationId || "this conversation";
const reviewDraft = (r) => {
  if (r.Kind === "action") {
    try {
      const proposal = JSON.parse(r.DraftText || "");
      if (proposal?.action === "write_playbook" && proposal.text) return proposal.text;
    } catch { /* ordinary reply text */ }
  }
  return r.DraftText || "";
};

export function DockActions({ messages, expanded = false, onNavigate, onChanged }) {
  const [reviews, setReviews] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [edits, setEdits] = useState({});
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");

  const load = useCallback(async () => {
    try {
      const [rv, ts] = await Promise.all([
        api.get("/api/reviews", { params: { status: "pending" } }),
        api.get("/api/tasks", { params: { active: 1 } }),
      ]);
      setReviews(rv.data.data || []);
      setTasks((ts.data.data || []).filter((t) => !["done", "dropped"].includes(t.Status)));
      setError("");
    } catch (e) { setError(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load, messages?.length]);

  const reviewId = mentioned(messages, "review");
  const taskId = mentioned(messages, "task");
  const ordered = useMemo(() => {
    const focus = reviews.find((r) => r.ReviewId === reviewId)
      || reviews.find((r) => taskId && r.TaskId === taskId);
    return focus ? [focus, ...reviews.filter((r) => r.ReviewId !== focus.ReviewId)] : reviews;
  }, [reviewId, reviews, taskId]);
  useEffect(() => { setCursor(0); }, [reviewId, taskId]);
  const focusedTask = taskId && !ordered.some((r) => r.TaskId === taskId)
    ? tasks.find((t) => t.TaskId === taskId) : null;
  const review = focusedTask ? null : ordered[cursor % Math.max(1, ordered.length)];

  const openTask = (tid) => {
    if (!tid) return;
    window.location.hash = `task=${tid}`;
    onNavigate?.("Tasks");
  };
  const refresh = async (message) => {
    setReceipt(message); setCursor(0); await load(); onChanged?.();
  };
  const decide = async (r, verb) => {
    const key = `review-${r.ReviewId}-${verb}`; setBusy(key); setError(""); setReceipt("");
    try {
      const finalText = edits[r.ReviewId] ?? reviewDraft(r);
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/decide`, {
        verb, final_text: verb === "approve" ? finalText : null, note: null,
      });
      if (data.send_error) throw new Error(data.send_error);
      const message = verb === "approve"
        ? (r.Kind === "action" ? "Action completed." : `Sent to ${reviewTarget(r)}.`)
        : verb === "reject" ? "Action dismissed; nothing was run." : "Dismissed; no reply was sent.";
      setEdits((old) => { const next = { ...old }; delete next[r.ReviewId]; return next; });
      await refresh(message);
    } catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  };
  const redraft = async (r) => {
    const key = `review-${r.ReviewId}-redraft`; setBusy(key); setError(""); setReceipt("");
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/draft`);
      setReviews((old) => old.map((x) => x.ReviewId === r.ReviewId ? { ...x, DraftText: data.draft } : x));
      setEdits((old) => { const next = { ...old }; delete next[r.ReviewId]; return next; });
      setReceipt("Draft refreshed. Review the text, then use the action button when it is right.");
    } catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  };
  const settleTask = async (t, status) => {
    const key = `task-${t.TaskId}-${status}`; setBusy(key); setError(""); setReceipt("");
    try {
      await api.patch(`/api/tasks/${t.TaskId}`, { Status: status });
      await refresh(status === "done" ? `${t.ref || `TQ-${String(t.TaskId).padStart(4, "0")}`} completed.`
        : `${t.ref || `TQ-${String(t.TaskId).padStart(4, "0")}`} dismissed.`);
    } catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  };

  if (!review && !focusedTask && !receipt && !error) return null;
  return (
    <div className={`tq-dock-actions${expanded ? " tq-dock-actions-expanded" : ""}`}>
      <div className="tq-dock-action-kicker">
        <span>Action</span>
        {!!ordered.length && !focusedTask && <em>{cursor + 1} of {ordered.length}</em>}
        <div className="tq-dock-action-nav">
          {ordered.length > 1 && !focusedTask && <>
            <IconButton size="small" aria-label="Previous action" onClick={() => setCursor((n) => (n - 1 + ordered.length) % ordered.length)}><ChevronLeftIcon /></IconButton>
            <IconButton size="small" aria-label="Next action" onClick={() => setCursor((n) => (n + 1) % ordered.length)}><ChevronRightIcon /></IconButton>
          </>}
        </div>
      </div>
      {error && <Alert severity="error" onClose={() => setError("")} sx={{ mb: 0.75, py: 0 }}>{error}</Alert>}
      {receipt && <Alert severity="success" onClose={() => setReceipt("")} sx={{ mb: review || focusedTask ? 0.75 : 0, py: 0 }}>{receipt}</Alert>}
      {review && <>
        <div className="tq-dock-action-head">
          <div>
            <b>{review.Subject || review.Title || (review.Kind === "action" ? "Proposed action" : "Reply ready")}</b>
            <span>{review.Kind === "action" ? "Review what will run" : `To ${reviewTarget(review)}`}</span>
          </div>
          {review.TaskId && <Button size="small" onClick={() => openTask(review.TaskId)}>Open task</Button>}
        </div>
        <TextField fullWidth multiline minRows={expanded ? 3 : 2} maxRows={expanded ? 10 : 5}
          value={edits[review.ReviewId] ?? reviewDraft(review)}
          onChange={(e) => setEdits((old) => ({ ...old, [review.ReviewId]: e.target.value }))}
          placeholder="No draft yet — choose Draft with AI"
          sx={{ mt: 0.75, "& textarea": { fontSize: 12.5, lineHeight: 1.48 } }} />
        <div className="tq-dock-action-buttons">
          {review.Kind === "action" ? <>
            <Button size="small" variant="contained" disabled={!!busy} startIcon={<DoneRoundedIcon />}
              onClick={() => decide(review, "approve")}>{busy ? "Working…" : "Run action"}</Button>
            <Button size="small" variant="outlined" color="error" disabled={!!busy} onClick={() => decide(review, "reject")}>Dismiss</Button>
          </> : <>
            {review.CanSend === false ? null : (
              <Button size="small" variant="contained" disabled={!!busy || !(edits[review.ReviewId] ?? reviewDraft(review)).trim()}
                startIcon={<SendRoundedIcon />} onClick={() => decide(review, "approve")}>
                {busy.includes("approve") ? "Sending…" : "Approve & send"}
              </Button>
            )}
            <Button size="small" variant="outlined" disabled={!!busy} startIcon={<RefreshRoundedIcon />}
              onClick={() => redraft(review)}>{busy.includes("redraft") ? "Drafting…" : review.DraftText ? "Redraft" : "Draft with AI"}</Button>
            <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "#867f74", borderColor: "#d6cec1" }} onClick={() => decide(review, "no_reply")}>Dismiss</Button>
          </>}
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={() => onNavigate?.("Review")}>All review</Button>
        </div>
      </>}
      {focusedTask && <>
        <div className="tq-dock-action-head">
          <div><b>{focusedTask.ref || `TQ-${String(focusedTask.TaskId).padStart(4, "0")}`} · {focusedTask.Title}</b>
            <span>{focusedTask.Status} · {focusedTask.Priority || "normal"} priority</span></div>
        </div>
        <div className="tq-dock-action-buttons">
          <Button size="small" variant="contained" onClick={() => openTask(focusedTask.TaskId)}>Open task</Button>
          <Button size="small" variant="outlined" disabled={!!busy} startIcon={<DoneRoundedIcon />}
            onClick={() => settleTask(focusedTask, "done")}>{busy.includes("done") ? "Completing…" : "Complete"}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "#867f74", borderColor: "#d6cec1" }}
            onClick={() => settleTask(focusedTask, "dropped")}>Dismiss</Button>
        </div>
      </>}
    </div>
  );
}

function AssistantThread({ task, messages, onAsked, onStop, selectionRef, attachmentsRef, onSent, onClearAttachments, onAttach, onReport, reportBusy,
  dock = false, dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  serverBusy = false, provider, name = "Taskuary", work, since }) {
  // "working" is only ever true on a WORK window. In the dock nothing below changes at all: the
  // dock is the assistant that helps you run Taskuary, not an agent doing a job (the owner,
  // 2026-09-08: "make sure the ux doesnt change or the general assistants").
  const working = !dock && !!serverBusy;
  const modelAdapter = useMemo(() => ({
    async *run({ messages: runMessages, abortSignal }) {
      onBusyChange?.(true);
      const prompt = textOf([...runMessages].reverse().find((m) => m.role === "user"));
      const selected = selectionRef.current;
      const body = {
        text: prompt,
        pick: selected.connectorId || null,
        model: selected.model || null,
        attachments: attachmentsRef.current.map((a) => a.path),
      };
      const tools = new Map();
      const progress = [];
      let structuredSeen = false;
      const content = (reply) => [
        ...tools.values(),
        ...(progress.length ? [{ type: "reasoning", text: progress.join("\n\n") }] : []),
        ...(reply ? [{ type: "text", text: reply }] : []),
      ];
      // A run that fails has to SAY so, here, under the question. Thrown out of the adapter it
      // is swallowed: the owner sees their own message and nothing after it, which is
      // indistinguishable from an agent that is still thinking (the wall, 2026-08-31). The
      // reasons are all things a person can act on - the session ended, another one holds this
      // task, it is still answering the last question, no AI is connected - so they are shown.
      try {
      for await (const event of streamAssistant(task.TaskId, body, abortSignal)) {
        if (event.type === "tool_call") {
          structuredSeen = true;
          const id = event.detail?.tool_call_id || `${event.name}-${tools.size}`;
          const args = event.detail?.args || {};
          tools.set(id, { type: "tool-call", toolCallId: id, toolName: event.name || "tool", args,
            argsText: JSON.stringify(args) });
          yield { content: content() };
        } else if (event.type === "tool_result") {
          const id = event.detail?.tool_call_id || event.name;
          const old = tools.get(id);
          if (old) tools.set(id, { ...old, result: { output: event.detail?.result || "" },
            isError: !!event.detail?.is_error });
          yield { content: content() };
        } else if (event.type === "start") {
          progress.push(`Started ${event.session?.provider || "the selected agent"}`);
          yield { content: content() };
        } else if (event.type === "progress" && event.detail) {
          structuredSeen = true;
          progress.push(String(event.detail));
          yield { content: content() };
        } else if (event.type === "live" && !structuredSeen && event.detail) {
          // Custom/Gemini/Aider CLIs may only provide line-oriented stdout. It is still live
          // work and must not leave a blank pane merely because it lacks Claude/Codex JSON.
          progress.push(String(event.detail));
          yield { content: content() };
        } else if (event.type === "error") {
          yield { content: content(`⚠ ${event.error || "The agent stopped without an answer."}`) };
          return;
        } else if (event.type === "done") {
          onClearAttachments(); onSent(event.payload);
          yield { content: content(event.reply) };
        }
      }
      } catch (e) {
        if (abortSignal?.aborted) return;              // the owner pressed stop; that is not an error
        yield { content: content(`⚠ ${e?.message || "The assistant could not answer."}`) };
      } finally {
        onBusyChange?.(false);
      }
    },
  }), [attachmentsRef, onBusyChange, onClearAttachments, onSent, selectionRef, task.TaskId]);
  const runtime = useLocalRuntime(modelAdapter, { initialMessages: initial(messages) });
  const prompted = useRef(null);
  useEffect(() => {
    if (!prompt?.text || prompted.current === prompt.id) return;
    prompted.current = prompt.id;
    runtime.thread.append(prompt.text);
    onPromptUsed?.(prompt.id);
  }, [onPromptUsed, prompt, runtime]);
  /* "New task for the agent" with no repository: the prompt the owner typed is the first thing
     said here, appended through the same streaming runtime as anything they type - so they watch
     the answer arrive instead of finding a task with their own words sitting in it, unanswered.

     The question is read off the TASK (newTask.js: the ask tag), never handed in as a prop: two
     earlier attempts passed it across the navigation and lost it to a re-render both times.
     Only into an EMPTY thread, and only once - the tag is stripped as it is asked, so a reload
     never re-asks and a chat opened an hour later still gets the question. */
  const asked = useRef(false);
  useEffect(() => {
    const text = String(task.Summary || '').trim();
    if (asked.current || messages?.length || !text || !wantsAsk(task)) return;
    asked.current = true;
    onAsked?.();
    runtime.thread.append(text);
  }, [task, messages, runtime, onAsked]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="tq-aui-thread">
        <ThreadPrimitive.Viewport className="tq-aui-viewport">
          {!messages?.length && (
            <div className="tq-aui-welcome">
              <TaskuaryMark size={22} />
              <div>
                <div className="tq-aui-welcome-title">{dock ? "What should we look at?" : "Work on this with your assistant"}</div>
                <div className="tq-aui-welcome-copy">{dock
                  ? "I can walk you through what arrived, what needs you, and what your agents finished."
                  : "Research, plan, write, analyze, or coordinate. This conversation stays on the task."}</div>
              </div>
            </div>
          )}
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
          <ThreadPrimitive.If running>
            {dock ? <Thinking provider={provider} />
                  : <AgentBand name={name} provider={provider} work={work} since={since} />}
          </ThreadPrimitive.If>
          {/* Only once it has stopped typing. An offer to "run this again, daily" hanging under a
              half-written answer is an offer to schedule something nobody has read yet - and it
              sat there through every tool call, which is where the eye goes while waiting. */}
          <ThreadPrimitive.If running={false}>
          {/* the answer is being written somewhere else - another tab, or this pane before it was
              reopened - and the poll is what tells us so */}
          {serverBusy && (dock ? <Thinking provider={provider} />
                                : <AgentBand name={name} provider={provider} work={work} since={since} />)}
          {dock && <DockActions messages={messages} expanded={dockExpanded} onNavigate={onDockNavigate} onChanged={onDockChanged} />}
          {!dock && !serverBusy && messages?.some((m) => m.role === "assistant") && (
            <div className="tq-aui-report-action">
              <div><b>Worth running again?</b><span>Creates a daily report from this workflow; adjust its cadence in Reports.</span></div>
              <Button size="small" variant="outlined" startIcon={<EventRepeatIcon sx={{ fontSize: 15 }} />}
                disabled={reportBusy} onClick={onReport}>{reportBusy ? "Creating…" : "Make recurring report"}</Button>
            </div>
          )}
          </ThreadPrimitive.If>
        </ThreadPrimitive.Viewport>
          <div className="tq-aui-footer">
            {!!attachmentsRef.current.length && (
              <div className="tq-aui-attachments">
                {attachmentsRef.current.map((a) => (
                  <Chip key={a.path} size="small" icon={<AttachFileIcon />} label={a.name}
                    onDelete={() => onClearAttachments(a.path)} />
                ))}
              </div>
            )}
            <ComposerPrimitive.Root className="tq-aui-composer">
              <IconButton size="small" onClick={onAttach} title="Attach an image" className="tq-aui-attach">
                <AttachFileIcon sx={{ fontSize: 18 }} />
              </IconButton>
              <ComposerPrimitive.Input
                className="tq-aui-input"
                placeholder={working ? "Add something for it to pick up…"
                  : dock ? "Tell Taskuary what to do next…" : "Tell the assistant what to do next…"}
              />
              {/* stopping is an ACT: closing this page is not one. The button tells the server
                  to stop the run; abandoning the tab just detaches from it (server.py). */}
              <ComposerPrimitive.Cancel className="tq-aui-cancel" aria-label="Stop response"
                onClick={onStop}><CloseIcon fontSize="small" /></ComposerPrimitive.Cancel>
              <ComposerPrimitive.Send className="tq-aui-send" aria-label="Send"><SendIcon fontSize="small" /></ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
            <div className="tq-aui-hint">Enter sends · Shift+Enter adds a line · paste or attach an image</div>
          </div>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export function GeneralWorkspace({ task, onSession, onOpenReports, compact = false, dock = false,
  dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  onDockNewChat }) {
  const [data, setData] = useState(null);
  const [view, setView] = useState(() => dock ? "assistant" : savedView());
  const [connectorId, setConnectorId] = useState("");
  const [model, setModel] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [threadKey, setThreadKey] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reportBusy, setReportBusy] = useState(false);
  const [newChatBusy, setNewChatBusy] = useState(false);
  const [confirmNewChat, setConfirmNewChat] = useState(false);
  const fileRef = useRef(null);
  const selectionRef = useRef({ connectorId: "", model: "" });
  const attachmentsRef = useRef([]);
  selectionRef.current = { connectorId, model };
  attachmentsRef.current = attachments;

  // asked once, and only once: the marker is cleared on the server as the question goes
  const dropAsk = useCallback(() => {
    api.patch(`/api/tasks/${task.TaskId}`, { Tags: withoutAsk(task.Tags) }).catch(() => {});
  }, [task.TaskId, task.Tags]);

  const accept = useCallback((payload) => {
    setData(payload);
    const provider = pickFor(payload);
    if (provider) {
      setConnectorId((old) => old || String(provider.id));
      setModel((old) => old || payload?.session?.model || provider.model || "");
    }
    onSession?.(payload?.session || null);
    onBusyChange?.(!!payload?.session?.busy);
  }, [onBusyChange, onSession]);

  useEffect(() => {
    let live = true;
    setData(null); setError(""); setNotice(""); setAttachments([]); setNewChatBusy(false); setConfirmNewChat(false);
    // Looking at a general task is not sending it to an agent. Load saved state only; the first
    // actual message (or an explicit Send to agent action) starts the regular agent.
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => live && accept(r.data)).catch((e) => live && setError(errText(e)));
    return () => { live = false; };
  }, [accept, task.TaskId]);

  const chooseView = async (next) => {
    localStorage.setItem("taskuary_general_view", next);
    if (next === "assistant" && view !== "assistant") {
      try {
        const r = await api.get(`/api/tasks/${task.TaskId}/assistant`);
        accept(r.data); setThreadKey((n) => n + 1);
      } catch (e) { setError(errText(e)); }
    }
    setView(next);
  };
  const updateProvider = async (nextId, nextModel = model) => {
    setConnectorId(String(nextId)); setModel(nextModel); setError("");
    try {
      const r = await api.post(`/api/tasks/${task.TaskId}/assistant/session`, { pick: nextId || null, model: nextModel || null });
      accept(r.data);
    } catch (e) { setError(errText(e)); }
  };
  const upload = async (files) => {
    const images = [...(files || [])].filter((f) => /^image\/(png|jpeg|gif|webp)$/.test(f.type));
    if (!images.length) return;
    setUploading(true); setError("");
    try {
      const added = [];
      for (const file of images) {
        const r = await api.post(`/api/tasks/${task.TaskId}/waitroom/image`, file, { headers: { "Content-Type": file.type } });
        added.push({ name: file.name || "pasted image", path: r.data.path });
      }
      setAttachments((old) => [...old, ...added]);
    } catch (e) { setError(errText(e)); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const clearAttachments = useCallback((path) => setAttachments((old) => path ? old.filter((a) => a.path !== path) : []), []);
  const sent = useCallback((payload) => accept(payload), [accept]);
  const stopRun = useCallback(() => {
    api.post(`/api/tasks/${task.TaskId}/assistant/cancel`).catch(() => {});
  }, [task.TaskId]);

  /* An answer written while you were somewhere else. The run no longer dies when this pane
     goes away, so when it comes back the conversation may be mid-sentence - or already have
     the reply, filed on the task. Poll while it is busy and show it the moment it lands;
     threadKey remounts the thread, which is how assistant-ui takes new initial messages. */
  const busy = !!data?.session?.busy;
  useEffect(() => {
    if (!busy) return undefined;
    let live = true;
    const timer = setInterval(async () => {
      try {
        const { data: fresh } = await api.get(`/api/tasks/${task.TaskId}/assistant`);
        if (!live) return;
        const grew = (fresh.messages || []).length !== (data?.messages || []).length;
        const traceChanged = fresh.session?.trace_revision !== data?.session?.trace_revision;
        setData(fresh);
        if (grew || traceChanged) setThreadKey((k) => k + 1);
      } catch { /* it will still be there next tick */ }
    }, 2500);
    return () => { live = false; clearInterval(timer); };
  }, [busy, task.TaskId, data?.messages]);
  const makeReport = async () => {
    setError(""); setNotice(""); setReportBusy(true);
    try {
      const { data: made } = await api.post(`/api/tasks/${task.TaskId}/assistant/report`, {
        pick: connectorId || null, model: model || null,
      });
      if (onOpenReports) onOpenReports(made.sourceId);
      else setNotice(`Created “${made.title}” in Reports.`);
    } catch (e) { setError(errText(e)); }
    finally { setReportBusy(false); }
  };
  const pasted = (e) => {
    const images = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (images.length) { e.preventDefault(); upload(images); }
  };
  const startNewChat = async () => {
    if (!onDockNewChat || busy || newChatBusy || !shownMessages.length) return;
    setConfirmNewChat(false); setNewChatBusy(true); setError("");
    try { await onDockNewChat(); }
    catch (e) { setError(errText(e)); setNewChatBusy(false); }
  };

  if (!data && !error) return <Box sx={{ height: 520, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>;
  const session = data?.session;
  const shownMessages = messagesWithTrace(data?.messages, session, dock);
  // WHO is on this task, what its turn has done so far, and when the turn began - all three read
  // off what this pane already has (agentWork.js). The dock is exempt: it IS the assistant.
  // Plain calls, NOT useMemo: this sits after the early return for "no data yet", so a hook here
  // runs on some renders and not others - which is React #310, and it blanked the whole view.
  const name = dock ? "Taskuary" : agentName(task);
  const work = workOf(session?.trace);
  const since = turnStart(shownMessages);
  // name the backend that is thinking. The session's own provider is the truth once it has one; on
  // a first turn there is no session yet, so fall back to the one the picker is showing.
  const pickedLabel = (data?.providers || []).find((p) => String(p.id) === String(connectorId))?.label;
  // the chat IS the workspace, running or not (generalPane.js) - a session only decides whether
  // there is a terminal to show beside it
  const pane = paneFor(view, !!session);
  const thread = (
    <AgentNameCtx.Provider value={name}>
      <AssistantThread key={`${task.TaskId}-${threadKey}`} task={task} messages={shownMessages}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onClearAttachments={clearAttachments}
        onAttach={() => fileRef.current?.click()} onReport={makeReport} reportBusy={reportBusy}
        dock={dock} dockExpanded={dockExpanded} prompt={prompt} onPromptUsed={onPromptUsed}
        onBusyChange={onBusyChange} onDockNavigate={onDockNavigate} onDockChanged={onDockChanged}
        serverBusy={busy} provider={session?.provider || pickedLabel} name={name} work={work} since={since} />
    </AgentNameCtx.Provider>
  );
  return (
    <Box className={dock ? `tq-aui-dock${dockExpanded ? " tq-aui-dock-expanded" : ""}` : undefined} onPaste={pasted} sx={{ border: dock ? 0 : `1px solid ${BORDER}`, borderRadius: dock ? 0 : 1.75, overflow: "hidden", bgcolor: PANEL2,
      minHeight: 0, display: "flex", flexDirection: "column",
      ...(compact ? { height: "100%" } : { flex: "1 1 auto" }) }}>
      {/* the strip wraps when its box is narrow - a phone, or a half-width Wall pane; scrolled sideways it hid the view buttons entirely */}
      {!dock && <Box sx={{ minHeight: 39, px: 1.25, py: { xs: 0.5, md: 0 }, display: "flex", alignItems: "center", gap: 0.8, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL,
        flexWrap: "wrap", flexShrink: 0 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: 99, bgcolor: session?.alive ? "#78a17b" : "#c7a258" }} />
        {/* the strip named the window after the concierge; it belongs to the agent working in it */}
        <Typography noWrap sx={{ ...mono, fontSize: 10.5, letterSpacing: ".13em", textTransform: "uppercase", color: DIM, flexShrink: 0 }}>{name}</Typography>
        <Box sx={{ flex: 1, minWidth: 8 }} />
        <Select size="small" value={connectorId} displayEmpty onChange={(e) => {
          const provider = data?.providers?.find((p) => String(p.id) === String(e.target.value));
          updateProvider(e.target.value, provider?.model || "");
        }}
          sx={{ height: 27, fontSize: 11.5, minWidth: 130, bgcolor: PANEL2, flexShrink: 0 }}>
          {!data?.providers?.length && <MenuItem value="">No agent connected</MenuItem>}
          {(data?.providers || []).map((p) => <MenuItem key={p.id} value={String(p.id)}>{p.label}</MenuItem>)}
        </Select>
        <TextField size="small" value={model} placeholder="provider default" onChange={(e) => setModel(e.target.value)}
          onBlur={() => connectorId && updateProvider(connectorId, model)} sx={{ width: 150, flexShrink: 0, "& input": { py: 0.55, fontSize: 11.5 } }} />
        <Button size="small" startIcon={<ViewDayIcon sx={{ fontSize: 14 }} />} variant={view === "assistant" ? "contained" : "text"}
          title="The conversation. What the assistant is doing shows here as it works."
          onClick={() => chooseView("assistant")} sx={{ minWidth: 0, fontSize: 11, flexShrink: 0 }}>Assistant</Button>
        <Button size="small" startIcon={<TerminalIcon sx={{ fontSize: 14 }} />} variant={view === "terminal" ? "contained" : "text"}
          title="The same conversation as raw session output - what the CLI actually printed."
          onClick={() => chooseView("terminal")} sx={{ minWidth: 0, fontSize: 11, flexShrink: 0 }}>Terminal</Button>
        {/* what it is ALLOWED to state as fact about our own numbers - the chat teaches it, this shows it */}
        <Button size="small" startIcon={<FunctionsIcon sx={{ fontSize: 14 }} />} variant={view === "numbers" ? "contained" : "text"}
          title="Certified numbers: the figures this assistant is allowed to state as fact about your own systems, because each was proved against numbers you already knew. Teach it one by asking for a figure it does not have yet."
          onClick={() => chooseView("numbers")} sx={{ minWidth: 0, fontSize: 11, flexShrink: 0 }}>Numbers</Button>
      </Box>}
      {dock && <Box sx={{ px: 1, py: 0.55, display: "flex", alignItems: "center", gap: 0.65,
        flexWrap: "wrap", bgcolor: PANEL, borderBottom: `1px solid ${BORDER}` }}>
        <Typography sx={{ ...mono, color: FAINT, fontSize: 9.5, textTransform: "uppercase" }}>AI</Typography>
        <Select size="small" value={connectorId} displayEmpty onChange={(e) => {
          const provider = data?.providers?.find((p) => String(p.id) === String(e.target.value));
          updateProvider(e.target.value, provider?.model || "");
        }} MenuProps={{ sx: { zIndex: 1600 } }}
          sx={{ height: 26, minWidth: 155, maxWidth: 225, flex: 1, fontSize: 10.5, bgcolor: PANEL2 }}>
          {!data?.providers?.length && <MenuItem value="">No AI connected</MenuItem>}
          {(data?.providers || []).map((p) => <MenuItem key={p.id} value={String(p.id)}>
            {p.label}{p.type === "cli" ? " · tool-capable" : " · fast"}
          </MenuItem>)}
        </Select>
        <TextField size="small" value={model} placeholder="default model" onChange={(e) => setModel(e.target.value)}
          onBlur={() => connectorId && updateProvider(connectorId, model)}
          sx={{ width: 118, "& input": { py: 0.5, fontSize: 10.5 } }} />
        <Button size="small" variant="outlined" startIcon={<AddCommentOutlinedIcon sx={{ fontSize: 14 }} />}
          disabled={busy || newChatBusy || !shownMessages.length} onClick={() => setConfirmNewChat(true)}
          title="Archive this conversation and start a fresh Taskuary chat"
          sx={{ minWidth: 0, px: 0.8, whiteSpace: "nowrap", textTransform: "none", fontSize: 10.5 }}>
          {newChatBusy ? "Starting…" : "New chat"}
        </Button>
      </Box>}
      {dock && confirmNewChat && (
        <Box role="group" aria-label="Confirm new chat" sx={{ display: "flex", alignItems: "center", gap: 0.75,
          px: 1.15, py: 0.8, flexWrap: "wrap", bgcolor: "#f8f5ee", borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ flex: 1, minWidth: 210 }}>
            <Typography sx={{ color: INK, fontSize: 11.5, fontWeight: 700 }}>Start a new chat?</Typography>
            <Typography sx={{ color: DIM, fontSize: 10.5 }}>
              This conversation is archived. Tasks, reviews, and action cards stay.
            </Typography>
          </Box>
          <Button size="small" onClick={() => setConfirmNewChat(false)}
            sx={{ textTransform: "none", fontSize: 10.5 }}>Keep this chat</Button>
          <Button size="small" variant="contained" disableElevation onClick={startNewChat}
            sx={{ textTransform: "none", fontSize: 10.5 }}>Start new chat</Button>
        </Box>
      )}
      {error && <Alert severity="error" sx={{ borderRadius: 0, py: 0 }}>{error}</Alert>}
      {notice && <Alert severity="success" onClose={() => setNotice("")} sx={{ borderRadius: 0, py: 0 }}>{notice}</Alert>}
      {dock && busy && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.5, bgcolor: PANEL2,
          borderBottom: `1px solid ${BORDER}` }}>
          <CircularProgress size={11} />
          <Typography variant="caption" sx={{ color: DIM }}>
            still working on your last message — it keeps going whether or not this is open
          </Typography>
        </Box>
      )}
      {!data?.providers?.length && <Alert severity="info" sx={{ borderRadius: 0, py: 0 }}>Add a CLI agent under Connections → AI CLI agents to run this work. API providers are optional.</Alert>}
      <input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple onChange={(e) => upload(e.target.files)} />
      {uploading && <Box sx={{ px: 1, py: 0.5, color: FAINT, fontSize: 11 }}>Attaching image…</Box>}
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {pane === "numbers" ? (
          <SemanticPanel />
        ) : pane === "terminal" ? (
          <TerminalPane sid={session.sid} height="100%" />
        ) : pane === "terminal-empty" ? (
          <Box sx={{ p: 2, color: FAINT, fontSize: 11.5 }}>
            Nothing has run on this task yet — ask something and the session's own output appears here.
          </Box>
        ) : session ? (
          <SessionPane sid={session.sid} height="100%" expectBrowser={wantsBrowser(task)}>{thread}</SessionPane>
        ) : thread}
      </Box>
    </Box>
  );
}

export default GeneralWorkspace;
