import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { says, subState } from "./laneSays.js";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive, ThreadPrimitive, useAuiState, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, Chip, CircularProgress, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/ArrowUpward";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DoneRoundedIcon from "@mui/icons-material/DoneRounded";
import AddCommentOutlinedIcon from "@mui/icons-material/AddCommentOutlined";
import api from "./api.js";
import { howToOpen } from "./bugReportOpen.js";
import { streamAssistant } from "./assistantStream.js";
import { stepsOf } from "./agentSteps.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { wantsAsk, wantsBrowser, withoutAsk } from "./newTask.js";
import { FULL_SX, useFullScreen } from "./fullScreen.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, workOf, doingNow, trailText, turnStart, elapsedText } from "./agentWork.js";
import { instructionsHint } from "./kinds.js";
import { assignedAgent } from "./agentIdentity.js";
import { Md } from "./md.jsx";
import { draftState } from "./sendState.js";
import PublishedPages from "./PublishedPages.jsx";
import { placeShown } from "./shownPages.js";
import { outputRefs, outputRow, uncited } from "./taskOutputs.js";
import { SessionPane } from "./TerminalView.jsx";
import { heldOn, isTurn, TURN_BACK } from "./browserSplit.js";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import { level } from "./priority.js";
import "./generalWorkspace.css";
import { MicButton, ModelSelect, TaskuaryMark } from "./ui.jsx";
import { hint as btnHint, label as btn } from "./buttons.js";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { placeName } from "./words.js";
import { starting as startingLine } from "./laneSays.js";
import { plural } from "./timeWords.js";
import { openAppLink } from "./appLinks.js";
import ConnectAi from "./ConnectAi.jsx";
import { withoutAsked } from "./askOnce.js";
import ReviewDecision from "./ReviewDecision.jsx";

const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();
const initial = (messages) => (messages || []).map((m) => ({
  ...m,
  createdAt: m.createdAt ? new Date(String(m.createdAt).replace(" ", "T") + (String(m.createdAt).includes("Z") ? "" : "Z")) : undefined,
}));

// ONE PART carries the turn's working: the steps every backend maps into (agentSteps.js), drawn in the order they happened - its own
// words, then a plain line per thing it did - above the answer. It was a row per raw tool call and then an "Agent progress" box saying
// the same commands again (the owner, 2026-10-21: "make the output on the general agent canvas more readable, not some greps and gets").
const stepsPart = (trace, opts) => { const steps = stepsOf(trace, opts); return steps.length ? [{ type: "data", name: "agent_steps", data: { steps } }] : []; };

// assistant-ui owns the response being streamed in the currently mounted pane. The task's
// session owns it when this pane is not mounted. Rehydrate that same tool/progress trace when a
// user switches back, and attach it to the filed answer once the run is complete.
export const messagesWithTrace = (messages, session, keepStart = true) => {
  const out = (messages || []).map((m) => ({ ...m, content: [...(m.content || [])] }));
  const trace = session?.trace;
  if (!stepsOf(trace, { keepStart }).length) return out;
  if (session?.busy) {
    out.push({ id: `live-${session.sid}-${session.trace_revision || 0}`, role: "assistant", content: stepsPart(trace, { keepStart }) });
    return out;
  }
  // The trail belongs to the NEWEST turn. When that turn filed an answer the trail is its
  // working, and rides above it as it always has. When it died it filed nothing - and the trail
  // was folded backwards into some older answer, or, on a first question, into nothing at all:
  // the chat showed the question, no reply, and no reason, over a task still chipped "agent
  // working" (TQ-0496 - codex exited 1 refusing the model it was configured with). A turn's
  // last word is its record when there is no other.
  const tail = out[out.length - 1];
  if (tail?.role === "assistant") tail.content = [...stepsPart(trace, { keepStart, answer: textOf(tail) }), ...tail.content];
  else out.push({ id: `trace-${session.sid}-${session.trace_revision || 0}`, role: "assistant", content: stepsPart(trace, { keepStart }) });
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
const AgentBand = ({ name, provider, work, since, starting = "" }) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const doing = doingNow(work), trail = trailText(work);
  // STARTED, NOTHING SAID YET: one line - "Starting the researcher on Codex…" - and its clock, never a tall empty pane with a spinner at
  // its foot while the CLI comes up (the owner, 2026-10-21: "it stayed like that for a while")
  if (starting && !work.steps.length) return (
    <div className="tq-aui-band" role="status" aria-live="polite" data-tq-starting-line="">
      <div className="tq-aui-band-head">
        <span className="tq-aui-band-dot" /><span>{starting}</span>
        <em>{since ? elapsedText(now - since) : ""}</em>
      </div>
    </div>
  );
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
          <div>{plural(work.sources.length, "source")} —{" "}
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

// A FILE THE ANSWER NAMES IS A FILE YOU CAN OPEN (taskOutputs.js): Codex's citation marker, a link or a path into this task's
// outputs folder comes out of the words and sits under them with Preview and Download. A Codex answer printed the raw marker, and
// asked to send the workbook it wrote a link to an /outputs/ address the server never had - a 404 (outputs.py).
const OutputsCtx = React.createContext(null);
const AssistantText = ({ text }) => {
  const at = React.useContext(OutputsCtx);
  const { text: said, files } = at ? outputRefs(text, at.tid) : { text, files: [] };
  return <>
    {!!said && <Md text={said} />}
    {!!files.length && <PublishedPages pages={files.map((f) => outputRow(at.tid, f, at.listed))} />}
  </>;
};
const UserMessage = () => (
  <MessagePrimitive.Root className="tq-aui-message tq-aui-user">
    <div className="tq-aui-role">you</div>
    <div className="tq-aui-user-bubble"><MessagePrimitive.Parts /></div>
  </MessagePrimitive.Root>
);
// what each answer published or showed, by the answer's id (the server's `after`): drawn under it, open - the agent chose it
const ShownCtx = React.createContext({});
const AssistantMessage = () => {
  const shown = React.useContext(ShownCtx)[useAuiState((s) => s.message.id)];
  return (
    <MessagePrimitive.Root className="tq-aui-message tq-aui-agent">
      <div className="tq-aui-role">{React.useContext(AgentNameCtx)}</div>
      <div className="tq-aui-agent-body">
        <MessagePrimitive.Parts components={{ Text: AssistantText, data: { by_name: { agent_steps: AgentSteps } } }} />
        {!!shown?.length && <PublishedPages pages={shown} open />}
      </div>
    </MessagePrimitive.Root>
  );
};

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
      if ((proposal?.action === "write_playbook" || proposal?.action === "amend_playbook") && proposal.text) return proposal.text;
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
  const caps = useCapabilities();                   // a draft's Send asks its channel here (capabilities.js) and its row

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
    openAppLink(`task=${tid}`);
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
        ? (r.Kind === "action" ? "Action completed." : `Sent to ${reviewTarget(r)}.`) + (r.TaskId ? ` The task stays open until you ${btn("close")}.` : "")
        : verb === "reject" ? "Action dismissed; nothing was run." : "Marked done; no reply was sent.";
      setEdits((old) => { const next = { ...old }; delete next[r.ReviewId]; return next; });
      await refresh(message);
    } catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  };
  const redraft = async (r) => {
    const key = `review-${r.ReviewId}-redraft`; setBusy(key); setError(""); setReceipt("");
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/draft`);
      setReviews((old) => old.map((x) => x.ReviewId === r.ReviewId ? { ...x, DraftText: data.draft, DraftNeeds: data.needs || null } : x));
      setEdits((old) => { const next = { ...old }; delete next[r.ReviewId]; return next; });
      setReceipt(data.needs ? draftState({ DraftNeeds: data.needs }).line : "Draft refreshed. Review the text, then use the action button when it is right.");
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
              onClick={() => decide(review, "approve")}>{busy ? "Working…" : btn("approve", "action")}</Button>
            <Button size="small" variant="outlined" color="error" disabled={!!busy} onClick={() => decide(review, "reject")}>Dismiss</Button>
          </> : <>
            {!draftCanSend(caps, review) ? null : (
              <Button size="small" variant="contained" disabled={!!busy || !(edits[review.ReviewId] ?? reviewDraft(review)).trim()}
                startIcon={<SendRoundedIcon />} onClick={() => decide(review, "approve")}>
                {busy.includes("approve") ? "Sending…" : btn("approve")}
              </Button>
            )}
            <Button size="small" variant="outlined" disabled={!!busy} startIcon={<RefreshRoundedIcon />}
              onClick={() => redraft(review)}>{busy.includes("redraft") ? "Drafting…" : review.DraftText ? btn("redraft") : btn("redraft", "none")}</Button>
            <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "#867f74", borderColor: "#d6cec1" }} title={`${btnHint("close")} - this draft is not sent`} onClick={() => decide(review, "no_reply")}>{btn("close")}</Button>
          </>}
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={() => onNavigate?.("Assistant")}>All that needs you</Button>
        </div>
      </>}
      {focusedTask && <>
        <div className="tq-dock-action-head">
          <div><b>{focusedTask.ref || `TQ-${String(focusedTask.TaskId).padStart(4, "0")}`} · {focusedTask.Title}</b>
            <span>{focusedTask.Status} · {level(focusedTask.Priority)} priority</span></div>
        </div>
        <div className="tq-dock-action-buttons">
          <Button size="small" variant="contained" onClick={() => openTask(focusedTask.TaskId)}>Open task</Button>
          <Button size="small" variant="outlined" disabled={!!busy} startIcon={<DoneRoundedIcon />}
            title={btnHint("close")} onClick={() => settleTask(focusedTask, "done")}>{busy.includes("done") ? "Marking done…" : btn("close")}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "#867f74", borderColor: "#d6cec1" }}
            onClick={() => settleTask(focusedTask, "dropped")}>Dismiss</Button>
        </div>
      </>}
    </div>
  );
}

// WHAT THE AGENT ASKED, AND THE BOX THAT ANSWERS IT (the UI audit's W6): the question in its own words, the answers it named as one
// press each, and a box for anything else. `onAnswer(text)` delivers it - a reply in this conversation, or the worker's own answer road -
// and throws with the reason when it could not; the card stays with the words still in it.
// A SIGN-IN it waits on (request id `signin:<site>`, signin.py) also offers the one-time fill page: Taskuary types it into the browser,
// the agent never sees it. Taking over the browser beside it and pressing Signed in is the other way, as before.
export function AgentAsks({ asking, name, onAnswer, taskId }) {
  const [text, setText] = useState(""), [going, setGoing] = useState(false), [err, setErr] = useState("");
  const site = String(asking.request_id || "").startsWith("signin:") ? asking.request_id.slice(7) : "";
  // ...and its Signed in is a press on EVERY agent's ask (2026-10-25): a terminal CLI's had only the box and a line saying to type it.
  // The server tells either kind the same words (signin.signed_in), never a chooser's number.
  const choices = site && !(asking.choices || []).includes("Signed in") ? [...(asking.choices || []), "Signed in"] : asking.choices || [];
  const fillPage = async () => {
    setErr("");
    try {
      const app = howToOpen(window) === "app";
      const { data } = await api.post(`/api/tasks/${taskId}/signin/link${app ? "?open=1" : ""}`);
      if (!app) window.open(data.url, "_blank", "noopener");
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { setText(""); setErr(""); setGoing(false); }, [asking?.request_id]);
  const send = async (words) => {
    const w = String(words || "").trim();
    if (!w || going) return;
    setGoing(true); setErr("");
    try { await onAnswer?.(w); setText(""); } catch (e) { setErr(errText(e)); } finally { setGoing(false); }
  };
  return (
    <div className="tq-aui-asking" data-tq-asking={asking.request_id}>
      <b>{says(subState({ request: asking }), name)}</b>
      <span className="tq-aui-asking-q">{asking.text}</span>
      {/* WHAT EACH WAY DOES, said on the card (2026-10-25): "Sign in to X ... Type your answer" read as "type the password here", and
          the agent-never-sees-it line lived only in a hover. Words only - the presses are the ones it had. */}
      {site && <span className="tq-aui-asking-hint" data-tq-signin-hint="">
        {taskId ? "Sign in here opens a page Taskuary types from - the agent never sees it. " : ""}
        Or sign in yourself in the browser, then press Signed in.</span>}
      {(!!choices.length || (site && taskId)) && <div className="tq-aui-asking-choices">
        {site && taskId && <Button size="small" variant="outlined" onClick={fillPage}
          title={`A one-time page to type the ${site} sign-in - Taskuary fills it into the browser and the agent never sees it`}>Sign in here</Button>}
        {choices.map((c) => <Button key={c} size="small" variant="outlined" disabled={going} onClick={() => send(c)}>{c}</Button>)}
      </div>}
      <form className="tq-aui-asking-box" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <TextField size="small" fullWidth value={text} disabled={going} onChange={(e) => setText(e.target.value)}
          placeholder={site ? "Message the agent - never your password" : "Type your answer"} inputProps={{ "aria-label": `Your answer to ${name}` }} />
        <Button type="submit" size="small" variant="contained" disableElevation disabled={going || !text.trim()}>{going ? "Sending…" : "Answer"}</Button>
      </form>
      {err && <span className="tq-aui-asking-err" role="alert">{err}</span>}
    </div>
  );
}

function AssistantThread({ task, messages, published, onAsked, onStop, selectionRef, attachmentsRef, onSent, onStarted, onClearAttachments, onAttach,
  dock = false, dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  serverBusy = false, provider, name = "Taskuary", work, since, revision = 0, asking, onAnswer, drafts = [], acts = [], onDraftDecided, starting = "", noComposer = false,
  onEnded }) {
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
      const events = [];
      const content = (reply) => [...stepsPart(events, { answer: reply || "" }), ...(reply ? [{ type: "text", text: reply }] : [])];
      // A run that fails has to SAY so, here, under the question. Thrown out of the adapter it
      // is swallowed: the owner sees their own message and nothing after it, which is
      // indistinguishable from an agent that is still thinking (the wall, 2026-08-31). The
      // reasons are all things a person can act on - the session ended, another one holds this
      // task, it is still answering the last question, no AI is connected - so they are shown.
      try {
      for await (const event of streamAssistant(task.TaskId, body, abortSignal)) {
        if (event.type === "start") {
          onStarted?.(event.session);
          events.push(event);
          yield { content: content() };
        } else if (["tool_call", "tool_result", "progress", "live"].includes(event.type)) {
          // Custom/Gemini/Aider CLIs may only provide line-oriented stdout. It is still live
          // work and must not leave a blank pane merely because it lacks Claude/Codex JSON (agentSteps.stepsOf).
          events.push(event);
          yield { content: content() };
        } else if (event.type === "error") {
          // ...and the page is told the turn is over: the session the stream's `start` handed it stayed "Agent is working", with Stop
          // and save, over a CLI that had died mid-turn - and nothing polls a session the server no longer has (the agents walk, 2026-10-26)
          onEnded?.();
          yield { content: content(`⚠ ${event.error || "The agent stopped without an answer."}`) };
          return;
        } else if (event.type === "done") {
          onClearAttachments(); onSent(event.payload);
          yield { content: content(event.reply) };
        }
      }
      } catch (e) {
        if (abortSignal?.aborted) return;              // the owner pressed stop; that is not an error
        onEnded?.();
        yield { content: content(`⚠ ${e?.message || "The assistant could not answer."}`) };
      } finally {
        onBusyChange?.(false);
      }
    },
  }), [attachmentsRef, onBusyChange, onClearAttachments, onEnded, onSent, onStarted, selectionRef, task.TaskId]);
  const runtime = useLocalRuntime(modelAdapter, { initialMessages: initial(messages) });
  /* WHAT ARRIVED WHILE YOU WERE TYPING goes into the thread that is already standing. This used to
     be a key bump, which remounts - and the draft lives in the composer INSIDE this runtime, so the
     2.5s busy poll emptied the box under the owner's fingers every time the agent took another step
     (the owner, 2026-09-14). reset() swaps the messages in place and never touches the composer. */
  const shown = useRef(messages);
  shown.current = messages;
  const applied = useRef(revision);
  useEffect(() => {
    if (applied.current === revision) return;
    applied.current = revision;
    // this pane's own stream is the live truth while it runs; its `done` files the server's copy
    if (runtime.thread.getState().isRunning) return;
    runtime.thread.reset(initial(shown.current));
  }, [revision, runtime]);
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

  // ONE PLACE says what it is doing. Once its steps stream into the thread above, the band repeated the newest of them word for word
  // beneath (the owner, 2026-10-14: "no need while it's working to tell you what it's doing in 2 places") - so it keeps only the
  // dots that say it is alive. The band is for the wait with nothing on screen yet, where an API brain looked frozen (2026-09-07).
  /* OPENED, it shows the newest answer from its first line. Pinned to the bottom, the cards under the answer (its question, the
     report offer) and the input took the room, and a short view showed the answer's last paragraph only: "I can't see any of the
     agent output without scrolling" (the owner, 2026-10-18). Only at rest and only once - a run that is writing keeps following. */
  const viewport = useRef(null), placed = useRef(false), said = !!messages?.length;
  useEffect(() => {
    if (dock || placed.current || !said || serverBusy) return;
    // the library pins to the bottom again whenever the answer lays out, and on a busy machine that lands after any one try - so it is
    // placed a few times over the first seconds, and never again once the owner scrolls or types themselves
    const v = viewport.current, mine = () => { placed.current = true; };
    const place = (final) => {
      const last = [...(v?.querySelectorAll(".tq-aui-agent") || [])].pop();
      if (placed.current || !v || !last || runtime.thread.getState().isRunning) return;
      const off = last.getBoundingClientRect().top - v.getBoundingClientRect().top - 8;
      if (off < 0) v.scrollTop += off;
      if (final) placed.current = true;
    };
    const ids = [350, 900, 1800].map((ms, i, all) => setTimeout(() => place(i === all.length - 1), ms));
    const own = ["wheel", "touchstart", "keydown"];
    own.forEach((e) => v?.addEventListener(e, mine, { passive: true }));
    return () => { ids.forEach(clearTimeout); own.forEach((e) => v?.removeEventListener(e, mine)); };
  }, [dock, said, serverBusy, runtime]);
  const closedChat = !dock && ["done", "dropped"].includes(String(task?.Status || ""));
  const atWork = dock || work?.steps?.length ? <Thinking provider={dock ? provider : name} />
    : <AgentBand name={name} provider={provider} work={work} since={since} starting={starting} />;
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="tq-aui-thread">
        <ThreadPrimitive.Viewport ref={viewport} className="tq-aui-viewport">
          {!messages?.length && !starting && (
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
            {atWork}
          </ThreadPrimitive.If>
          {/* Only once it has stopped typing. An offer to "run this again, daily" hanging under a
              half-written answer is an offer to schedule something nobody has read yet - and it
              sat there through every tool call, which is where the eye goes while waiting. */}
          <ThreadPrimitive.If running={false}>
          {/* the answer is being written somewhere else - another tab, or this pane before it was
              reopened - and the poll is what tells us so */}
          {serverBusy && atWork}
          {dock && <DockActions messages={messages} expanded={dockExpanded} onNavigate={onDockNavigate} onChanged={onDockChanged} />}
          {/* THE QUESTION IS ON THE AGENT'S OWN CANVAS, with its answer box (owner-approved, the UI audit's W6, 2026-10-21): the
              card said "Agent asked you something" over a pane that never showed what - the question lived only in the rail row's
              hover. It was taken out on 2026-10-19 as a repeat of the answer above; an agent asking from a terminal has no answer
              above at all, and an answer needs a box beside the question it answers. */}
          {!dock && asking && <AgentAsks asking={asking} name={name} onAnswer={onAnswer} taskId={task.TaskId} />}
          {!dock && <PublishedPages pages={published} deliver />}
          {/* not while it waits on your call: a run that stopped to ask is not one to schedule yet, and the offer took the room
              the answer needed */}
          {/* A PLAYBOOK DRAFTED HERE IS APPROVED HERE (the owner, 2026-10-21): Close out, where it also waits, is hidden while the
              conversation is live - Approve was reachable only after a Stop and save nothing said to press */}
          {!dock && !!drafts?.length && (
            <Box data-tq-playbook-drafts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>
                Approve saves this playbook to Reports → Playbooks, and triage starts matching new mail against its when line. Nothing is sent to anyone.</Typography>
              {drafts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}
            </Box>
          )}
          {/* ...AND A BROWSER ACT HELD HERE IS APPROVED HERE (2026-10-25): its card waited in the hidden Close out, and Stop and save, the
              only road to it, closed the very browser Approve runs in. The same card, where the owner already looks. */}
          {!dock && !!acts?.length && (
            <Box data-tq-browser-acts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>
                The agent's browser waits for your yes. Approve runs exactly this in its browser; Dismiss tells the agent it was not done.</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}
            </Box>
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
            {/* A CLOSED task's conversation is read, not typed into: a message started a live session on a done task, which
                then read "waiting on you" under a bar offering only Reopen (the owner, 2026-10-14). The server refuses it too. */}
            {/* ...and ONE DOOR: while the conversation is open the box is how it goes on (no Continue on the bar, 2026-09-29), but once its
                run has ENDED the bar offers Continue - and a box beside it read as a second way in (the owner, 2026-10-26: "before I hit
                continue it has a space to type into the agent? coding agents don't have that"). `noComposer` is that Continue (TaskPage). */}
            {closedChat ? <div className="tq-aui-hint" role="status" style={{ padding: "10px 4px" }}>
              This task is closed. Press {btn("reopen")}, then {btn("continue")}, to pick the conversation back up.</div> : noComposer ? null : <>
            <ComposerPrimitive.Root className="tq-aui-composer">
              <IconButton size="small" onClick={onAttach} title="Attach an image" className="tq-aui-attach">
                <AttachFileIcon sx={{ fontSize: 18 }} />
              </IconButton>
              <ComposerPrimitive.Input
                className="tq-aui-input"
                placeholder={working ? "Add something for it to pick up…"
                  : dock ? "Tell Taskuary what to do next…" : "Tell the assistant what to do next…"}
              />
              {/* the one mic, dictating into the box - every other composer had it and this one did not (the owner,
                  2026-09-29: "where is mic to ask it question?") */}
              <MicButton size={18} sx={{ color: "#6b5f45", p: 0.5 }} onText={(t) => {
                const c = runtime.thread.composer, was = c.getState().text;
                c.setText(was.trim() ? `${was.trimEnd()} ${t}` : t);
              }} />
              {/* stopping is an ACT: closing this page is not one. The button tells the server
                  to stop the run; abandoning the tab just detaches from it (server.py). */}
              <ComposerPrimitive.Cancel className="tq-aui-cancel" aria-label="Stop response"
                onClick={onStop}><CloseIcon fontSize="small" /></ComposerPrimitive.Cancel>
              <ComposerPrimitive.Send className="tq-aui-send" aria-label="Send"><SendIcon fontSize="small" /></ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
            <div className="tq-aui-hint">Enter sends · Shift+Enter adds a line · paste or attach an image</div></>}
          </div>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export function GeneralWorkspace({ task, onSession, onAnswered, compact = false, dock = false, toolsAt = null,
  dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  onDockNewChat, noAiSaid = false, noTools = false, noComposer = false, liveSid = "", reread = 0 }) {
  const [data, setData] = useState(null);
  const [connectorId, setConnectorId] = useState("");
  const [model, setModel] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [revision, setRevision] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [ownPrompt, setOwnPrompt] = useState(null);
  const [answered, setAnswered] = useState("");          // the question this card answered (AgentAsks)
  // the browser view is on screen: what waits on it is drawn there (SessionPane.onView). Not set*-named: the scope check (scope.test)
  // reads this file's JSX apostrophes as strings and loses the declaration
  const [viewShown, viewShownIs] = useState(false);
  // the whole window, where it stands - the dock is exempt, it has its own expand
  const { full, toggle: toggleFull } = useFullScreen();
  const [newChatBusy, setNewChatBusy] = useState(false);
  const [confirmNewChat, setConfirmNewChat] = useState(false);
  // a turn this pane is streaming itself: `data.session` is not re-read during it, so it alone says the agent is not idle (SessionPane)
  const [streaming, setStreaming] = useState(false);
  const threadBusy = useCallback((b) => { setStreaming(b); onBusyChange?.(b); }, [onBusyChange]);
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
    // A LIVE session's own pick outranks whatever the picker opened on. A walk's brain is chosen by
    // the server (general.walk_pick), so a strip frozen on the mount-time default both misnamed the
    // agent that was working - "Azure OpenAI (API)" over codex driving the browser - and is what the
    // owner's next message would have been sent to (the owner, 2026-09-14).
    const live = !!payload?.session?.pick;
    if (provider) {
      setConnectorId((old) => (live || !old ? String(provider.id) : old));
      setModel((old) => (live || !old ? (payload?.session?.model || provider.model || "") : old));
    }
    onSession?.(payload?.session || null);
    onBusyChange?.(!!payload?.session?.busy);
  }, [onBusyChange, onSession]);

  useEffect(() => {
    let live = true;
    setData(null); setError(""); setAttachments([]); setNewChatBusy(false); setConfirmNewChat(false);
    // Looking at a general task is not sending it to an agent. Load saved state only; the first
    // actual message (or an explicit Send to agent action) starts the regular agent.
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => live && accept(r.data)).catch((e) => live && setError(errText(e)));
    return () => { live = false; };
  }, [accept, task.TaskId]);

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
  /* THE SESSION IS KNOWN AT THE START OF THE TURN, not its end. The stream's first event carries it
     (server.assistant_stream puts `start` before the prompt is sent), and nothing read it: the pane
     learned its session only from `done`, so a browser that opened ten seconds into a first turn was
     first painted a minute later, when the answer landed (the 2026-10-02 pane pass). Taking it here
     mounts the browser beside the conversation while the agent is still driving it. Only into a pane
     with no session yet - an existing one is already polled and is the fresher copy. */
  const started = useCallback((s) => {
    if (!s?.sid) return;
    setData((d) => (d && !d.session ? { ...d, session: s } : d));
    onSession?.(s);
  }, [onSession]);
  const stopRun = useCallback(() => {
    api.post(`/api/tasks/${task.TaskId}/assistant/cancel`).catch(() => {});
  }, [task.TaskId]);

  /* An answer written while you were somewhere else. The run no longer dies when this pane
     goes away, so when it comes back the conversation may be mid-sentence - or already have
     the reply, filed on the task. Poll while it is busy and show it the moment it lands;
     a revision bump hands them to the thread that is already standing (never a remount - see AssistantThread). */
  // Work in flight on this task that this pane is not driving: an answer being written in another
  // tab - and the one that read as a dead pane, a walk whose session the server is still opening in
  // the background (server._walk_opens). Mount's snapshot lands inside that gap, so a poll gated on
  // the session alone never started at all: no question, no band, no browser beside the conversation
  // for the whole first answer (the owner, 2026-09-14: "it looked like it did not start").
  const busy = !!data?.session?.busy || !!data?.starting;
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
        // ...and the page's copy too: it held the session the turn STARTED with, so its heading said "is working" under the
        // finished answer (2026-10-15)
        onSession?.(fresh.session || null);
        if (grew || traceChanged) setRevision((k) => k + 1);
      } catch { /* it will still be there next tick */ }
    }, 2500);
    return () => { live = false; clearInterval(timer); };
  }, [busy, task.TaskId, data?.messages, onSession]);
  // ...and what a read brings is handed to the standing thread (a revision bump), as the poll does: taken into `data` alone, the owner's
  // Continue note waited for the next poll to show (the owner, 0.3.9.51: "I did Continue, filled it out and nothing happened")
  const refresh = useCallback(() => {
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => { accept(r.data); setRevision((k) => k + 1); }).catch(() => {});
  }, [accept, task.TaskId]);
  // A SESSION ANOTHER DOOR STARTED (`liveSid`, the page's live one): the canvas's Continue card, the Assistant, the phone. The page
  // adopted it, but this conversation had loaded before it existed and polls only while it knows of a turn, so a Continue with a note
  // showed the old turns under an agent that had already asked its question (the agents walk, 2026-10-26). Read again when they differ.
  const loaded = !!data, knownSid = data?.session?.sid || "";
  useEffect(() => { if (loaded && liveSid && knownSid !== liveSid) refresh(); }, [loaded, liveSid, knownSid, refresh]);
  // ...and at once when that door says it answered (`reread`, bumped by the page): the note is on the conversation by then, and the
  // session it starts is seconds away
  useEffect(() => { if (loaded && reread) refresh(); }, [reread]);  // eslint-disable-line react-hooks/exhaustive-deps
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
  // ...the question the answer box below shows is said there only (askOnce.js)
  const shownMessages = withoutAsked(messagesWithTrace(data?.messages, session, dock),
    !dock && data?.asking && data.asking.request_id !== answered ? data.asking : null);
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
  // STARTED AND SILENT: the agent is on its way and has filed nothing - the pane is that one line high, not the room an answer gets
  const quiet = !dock && busy && !(data?.messages || []).some((m) => m.role === "assistant");
  const starting = quiet ? startingLine(name, session?.provider || pickedLabel) : "";
  // the chat IS the workspace, running or not - a session only decides whether a browser sits
  // beside it. It used to be one of four bodies behind a switcher (a fake terminal of the same
  // conversation, a browser button, a numbers panel); a general agent is a chat the way a coding
  // agent is a terminal, so there is nothing to switch (the owner, 2026-09-22).
  // ...gone from the card the moment it is answered: the snapshot carries it until the agent's next word lands
  const asking = data?.asking && data.asking.request_id !== answered ? data.asking : null;
  // THE ANSWER GOES WHERE THE QUESTION CAME FROM: this conversation's own agent takes it as its next message, streamed here as any
  // other (its new turn overtakes the question - workerstate.open_requests); an agent asking from a terminal on this task gets it
  // through the worker's answer road (workerstate.answer), and the card's state clears with the `answered` it records
  const answerAsk = async (text) => {
    const req = asking;
    if (session?.sid && String(req.sid) === String(session.sid)) { setOwnPrompt({ id: `ask:${req.request_id}`, text }); setAnswered(req.request_id); return; }
    await api.post(`/api/tasks/${task.TaskId}/worker/answer`, { request_id: req.request_id, text });
    setAnswered(req.request_id); onAnswered?.();
  };
  /* WHAT WAITS ON THE BROWSER IS ON THE BROWSER (the owner, 2026-10-28: "it should show up as a BROWSER inside the agent canvas ... so it
     flows better to go back and continue"). A held act of this session's browser shows its Approve / Dismiss on the view, and the
     agent's hand-over of the page ("your turn") its Done - both into this same conversation. Off screen (a phone's chip), their cards. */
  const viewActs = (data?.browserActs || []).map((r) => heldOn(r, session?.sid)).filter(Boolean);
  const turn = asking && isTurn(asking) ? asking : null;
  const actsHere = viewShown ? (data?.browserActs || []).filter((r) => !heldOn(r, session?.sid)) : data?.browserActs || [];
  // Approve runs the act and tells the agent on a thread of its own (browsergate._tell): its next turn starts a moment after the press
  const decidedOnView = () => { refresh(); setTimeout(refresh, 2000); };
  const handBack = () => answerAsk(TURN_BACK);
  const promptUsed = (id) => { if (ownPrompt?.id === id) setOwnPrompt(null); else onPromptUsed?.(id); };
  const placed = placeShown(data?.published, shownMessages);     // no hook: this sits below the loading return
  const thread = (
    <AgentNameCtx.Provider value={name}><ShownCtx.Provider value={placed.by}>
    <OutputsCtx.Provider value={dock ? null : { tid: task.TaskId, listed: data?.outputs }}>
      {/* ...and every other file in the task's outputs folder - one no answer names - at the foot, with what it published or showed */}
      <AssistantThread key={task.TaskId} revision={revision} task={task} messages={shownMessages}
        published={dock ? placed.foot : [...placed.foot, ...uncited(data?.outputs, shownMessages.filter((m) => m.role === "assistant").map(textOf), task.TaskId)]}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onStarted={started} onEnded={refresh} onClearAttachments={clearAttachments}
        onAttach={() => fileRef.current?.click()}
        dock={dock} dockExpanded={dockExpanded} prompt={ownPrompt || prompt} onPromptUsed={promptUsed}
        asking={turn && viewShown ? null : asking} onAnswer={answerAsk} noComposer={noComposer}
        onBusyChange={threadBusy} onDockNavigate={onDockNavigate} onDockChanged={onDockChanged}
        serverBusy={busy} provider={session?.provider || pickedLabel} name={name} work={work} since={since}
        drafts={data?.playbookDrafts || []} acts={actsHere} onDraftDecided={refresh} starting={starting} />
    </OutputsCtx.Provider>
    </ShownCtx.Provider></AgentNameCtx.Provider>
  );
  const tools = (<>
    <Select size="small" value={connectorId} displayEmpty onChange={(e) => {
      const provider = data?.providers?.find((p) => String(p.id) === String(e.target.value));
      updateProvider(e.target.value, provider?.model || "");
    }}
      sx={{ height: 27, fontSize: 11.5, minWidth: 96, maxWidth: 220, bgcolor: PANEL2, flexShrink: 1 }}>
      {!data?.providers?.length && <MenuItem value="">No agent connected</MenuItem>}
      {(data?.providers || []).map((p) => <MenuItem key={p.id} value={String(p.id)}>{p.label}</MenuItem>)}
    </Select>
    <TextField size="small" value={model} placeholder="provider default" onChange={(e) => setModel(e.target.value)}
      onBlur={() => connectorId && updateProvider(connectorId, model)} sx={{ width: 150, flexShrink: 0, "& input": { py: 0.55, fontSize: 11.5 } }} />
    <Button size="small" onClick={toggleFull} sx={{ minWidth: 0, fontSize: 11, flexShrink: 0 }}
      title={full ? "Back to the page (Esc)" : "Give this conversation and its browser the whole window"}
      startIcon={full ? <CloseFullscreenIcon sx={{ fontSize: 13 }} /> : <OpenInFullIcon sx={{ fontSize: 13 }} />}>
      {full ? "Exit full screen" : "Full screen"}
    </Button>
  </>);
  return (
    <Box className={dock ? `tq-aui-dock${dockExpanded ? " tq-aui-dock-expanded" : ""}` : undefined} onPaste={pasted} data-tq-starting={quiet ? "" : undefined} sx={{ border: dock ? 0 : `1px solid ${BORDER}`, borderRadius: dock ? 0 : 1.75, overflow: "hidden", bgcolor: PANEL2,
      minHeight: 0, display: "flex", flexDirection: "column",
      ...(compact ? { height: quiet ? "auto" : "100%" } : { flex: quiet ? "0 0 auto" : "1 1 auto" }),
      ...(full && !dock ? FULL_SX : null) }}>
      {/* the strip wraps when its box is narrow - a phone, or a half-width Wall pane; scrolled sideways it hid its buttons entirely.
          On the canvas the task's own step heading holds it (toolsAt) and the answer gets the line - until Full screen, which
          leaves that heading behind */}
      {/* ...and none at all on a card whose session is not live (`noTools`, the owner 2026-10-25): a failed or closed agent's heading carried
          the agent picker, "provider default" and Full screen for a chat nothing is running in - the bar's Run another agent starts one */}
      {/* ...in a fragment: a portal straight under a Box failed its `children` check, a console error on every live agent (2026-10-26) */}
      {!dock && !noTools && toolsAt && !full && <>{createPortal(tools, toolsAt)}</>}
      {!dock && !noTools && !(toolsAt && !full) && <Box sx={{ minHeight: 39, px: 1.25, py: { xs: 0.5, md: 0 }, display: "flex", alignItems: "center", gap: 0.8, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL,
        flexWrap: "wrap", flexShrink: 0 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: 99, bgcolor: session?.alive ? "#78a17b" : "#c7a258" }} />
        {/* the strip named the window after the concierge; it belongs to the agent working in it */}
        <Typography noWrap sx={{ ...mono, fontSize: 10.5, letterSpacing: ".13em", textTransform: "uppercase", color: DIM, flexShrink: 0 }}
          title={instructionsHint(assignedAgent(task?.Assignee)) || undefined}>{name}</Typography>
        <Box sx={{ flex: 1, minWidth: 8 }} />
        {tools}
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
        {/* the CLI's own model list, the same one every other picker reads now - typing the name
            of a model that no longer exists was the only way to choose one here (2026-09-18) */}
        <ModelSelect model={model} size={26} empty="default model" menuProps={{ sx: { zIndex: 1600 } }}
          info={{ models: (data?.providers || []).find((p) => String(p.id) === String(connectorId))?.models }}
          onModel={(m) => { setModel(m); if (connectorId) updateProvider(connectorId, m); }}
          sx={{ minWidth: 118, maxWidth: 190, fontSize: 10.5, bgcolor: PANEL2 }} />
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
            <Typography sx={{ color: INK, fontSize: 11.5, fontWeight: 600 }}>Start a new chat?</Typography>
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
      {dock && busy && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.5, bgcolor: PANEL2,
          borderBottom: `1px solid ${BORDER}` }}>
          <CircularProgress size={11} />
          <Typography variant="caption" sx={{ color: DIM }}>
            still working on your last message — it keeps going whether or not this is open
          </Typography>
        </Box>
      )}
      {/* "Connections → AI", as the chat says it (concierge.py, no AI connected): the AI CLI agents page's own name is a word the owner never reads
          (words.json jargon), and the walk read it here on a box with no AI (WORDS, 2026-10-20) */}
      {/* ...with the button that does it (owner-approved, 2026-10-21): every "no AI" line carries Connect an AI */}
      {/* ...but not where it is already said or no longer matters (`noAiSaid`, the owner 2026-10-25): a closed task, or a failure whose own
          line is that no AI is connected - the banner was the same fact a third time under it */}
      {!data?.providers?.length && !noAiSaid && <Alert severity="info" data-tq-no-ai="" sx={{ borderRadius: 0, py: 0, alignItems: "center" }}
        action={<ConnectAi variant="outlined" />}>No AI is connected, so this work cannot run yet - connect one under {placeName("ai")}.</Alert>}
      {session?.resume_notice && <Typography sx={{ px: 1.5, py: 0.5, fontSize: 12, color: FAINT }}>{session.resume_notice}</Typography>}
      {/* A SECOND AGENT'S CONVERSATION IS ITS OWN (Run another agent, general.new_run): the earlier agent's stays on the task, folded
          above it and read only - the thread below is the new one's, never the old one picked back up */}
      {!dock && !!data?.earlier?.length && <Box component="details" data-tq-earlier-run="" sx={{ px: 1.5, py: 0.4, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <Box component="summary" sx={{ cursor: "pointer", color: FAINT, fontSize: 12, fontWeight: 600, "&:hover": { color: INK } }}>
          The earlier agent's conversation · {plural(data.earlier.length, "message")}</Box>
        <Box sx={{ maxHeight: 260, overflow: "auto", py: 0.5, fontSize: 12.5, color: INK }}>
          {data.earlier.map((m) => <Box key={m.id} sx={{ py: 0.4 }}>
            <Box component="span" sx={{ color: FAINT, fontWeight: 600, fontSize: 11 }}>{m.role === "user" ? "You" : name}</Box>
            <Md text={textOf(m)} /></Box>)}
        </Box>
      </Box>}
      <input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple onChange={(e) => upload(e.target.files)} />
      {uploading && <Box sx={{ px: 1, py: 0.5, color: FAINT, fontSize: 11 }}>Attaching image…</Box>}
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {/* ALWAYS inside the pane, session or not: a session that arrives mid-turn (`started`) must not
            change the tree around the thread, or the answer streaming into it is remounted away
            ...and no sid on a card whose session is not live (`noTools`): its browser was asked for every 3 s under a stopped, saved
            or failed agent's Result, for as long as it stayed open (the agents walk, 2026-10-26) */}
        <SessionPane sid={(!noTools && session?.sid) || null} height="100%" yourTurn={!!asking} idle={!busy && !streaming}
          stack={!dock} taskId={dock ? null : task.TaskId} held={viewActs} turn={turn} onHandBack={handBack} onDecided={decidedOnView}
          onView={viewShownIs} expectBrowser={wantsBrowser(task)}>{thread}</SessionPane>
      </Box>
    </Box>
  );
}

export default GeneralWorkspace;
