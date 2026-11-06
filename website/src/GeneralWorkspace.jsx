import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { says, subState } from "./laneSays.js";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive, ThreadPrimitive, useAuiState, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, CircularProgress, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
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
import { onLive, touches } from "./live.js";
import { AttachChip, IMAGE_TYPES, MAX_IMAGES, savePromptFile } from "./promptImages.jsx";
import { heldLine, notShown, stillHeld } from "./heldLines.js";
import { howToOpen } from "./bugReportOpen.js";
import { streamAssistant } from "./assistantStream.js";
import { isWork, stepsOf } from "./agentSteps.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { wantsAsk, withoutAsk } from "./newTask.js";
import { FULL_SX, useFullScreen } from "./fullScreen.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, workOf, doingNow, turnStart, elapsedText, turnStamp, turnBegan } from "./agentWork.js";
import { AGENT_TURN, MESSAGE, instructionsHint } from "./kinds.js";
import { assignedAgent } from "./agentIdentity.js";
import { LinkPopups, Md } from "./md.jsx";
import { draftState } from "./sendState.js";
import PublishedPages, { FileDialog } from "./PublishedPages.jsx";
import { placeShown } from "./shownPages.js";
import { outputRefs, outputRow, shownOnce, turnFiles, uncited } from "./taskOutputs.js";
import TurnFiles from "./TurnFiles.jsx";
import ActionCard from "./ActionCard.jsx";
import CopyCorner from "./CopyCorner.jsx";
import { SessionPane } from "./TerminalView.jsx";
import ThreadReading from "./ThreadReading.jsx";
import { heldOn, isTurn, needsOwner, TURN_BACK, waitsOnPage } from "./browserSplit.js";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import { level } from "./priority.js";
import "./generalWorkspace.css";
import { ModelSelect, TaskuaryMark } from "./ui.jsx";
import { hint as btnHint, label as btn } from "./buttons.js";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { placeName } from "./words.js";
import { starting as startingLine } from "./laneSays.js";
import { plural } from "./timeWords.js";
import { openAppLink } from "./appLinks.js";
import ConnectAi from "./ConnectAi.jsx";
import { withoutAsked } from "./askOnce.js";
import ReviewDecision from "./ReviewDecision.jsx";
import { heldActsLine } from "./reviewProposal.js";
import BriefLine from "./BriefLine.jsx";
import AgentSummary, { OneBox } from "./AgentSummary.jsx";
import { answerShown, foldedSummaries, lastAnswerSummed } from "./agentSummary.js";
import { asUtc, dayLabel, fmtTime12 } from "./dates.js";
import { readingOf } from "./threadReading.js";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import TelegramIcon from "@mui/icons-material/Telegram";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import KeyIcon from "@mui/icons-material/VpnKeyOutlined";
import AlarmIcon from "@mui/icons-material/AccessTime";

const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();
// the brief an agent was started on is Taskuary's, not the owner's (general.BRIEF_ACTOR): carried to UserMessage on the message's metadata
// ...and a turn's summary (general.shown_history) to AssistantMessage the same way - the runtime keeps metadata and drops anything else
const initial = (messages) => {
  const folded = foldedSummaries(messages);
  return (messages || []).map((m) => {
    const custom = { ...(m.brief ? { brief: true, mail: m.mail || [] } : {}), ...(m.summary ? { summary: m.summary, folded: folded.has(m.id), drafts: m.drafts_then || null } : {}),
      ...(m.since ? { since: m.since } : {}) };
    return { ...m, ...(Object.keys(custom).length ? { metadata: { custom } } : {}),
      // ...a stamp is the SERVER'S LOCAL time (dates.js, store.norm_stamp), read through asUtc with the zone setting - read as UTC, every
      // answer said 7:32 AM for 12:32 PM (the owner, 2026-11-05: "time is wrong. we have settings for time zone")
      createdAt: m.createdAt ? (String(m.createdAt).includes("Z") ? new Date(m.createdAt) : asUtc(m.createdAt)) : undefined };
  });
};

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
    // ...with the turn's own start (general.info `turn_started`): its id is new at every step, and so was the time the runtime gave it
    out.push({ id: `live-${session.sid}-${session.trace_revision || 0}`, role: "assistant", content: stepsPart(trace, { keepStart }),
      ...(session.turn_started ? { since: session.turn_started * 1000 } : {}) });
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
  const [now, setNow] = useState(() => Date.now()), [shown] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const doing = doingNow(work);
  // STARTED, NOTHING SAID YET: one line - "Starting the researcher on Codex…" - and its clock, never a tall empty pane with a spinner at
  // its foot while the CLI comes up (the owner, 2026-10-21: "it stayed like that for a while")
  // ...the same quiet line as "Working on this…", no box around it (the owner, 2026-11-05: no boxes), and its clock from no earlier than this
  // line came up: a turn carried on by new mail has no input of its own yet, and it counted from the one before - "62m 16s" at its start
  if (starting && !work.steps.length) return (
    <div className="tq-aui-working" role="status" aria-live="polite" data-tq-starting-line="">
      <span className="tq-aui-band-dot" /><span>{starting}</span>
      <em>{elapsedText(now - Math.max(since || 0, shown))}</em>
    </div>
  );
  // ...and then ONE QUIET LINE (the closeout-in-chat spec, 2026-11-04): "Working on this…" and its clock. The band said who, what now, which
  // step, a meter and its sources - live lines scrolling past while the owner waits; the steps fold under this line (WorkSteps) instead
  return (
    <div className="tq-aui-working" role="status" aria-live="polite" data-tq-working="" title={doing || undefined}>
      <span className="tq-aui-band-dot" /><span>Working on this…</span>
      <em>{since ? elapsedText(now - since) : provider || name || ""}</em>
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
// ...and a file NAMED in the words - `Report.csv` - opens over the chat at a press (FileDialog): the names are marked once drawn
const nameOf = (s) => String(s || "").trim().replace(/^.*[\\/]/, "");
export const isOutputsFolder = (s, tid) => new RegExp(`outputs[\\\\/]TQ-0*${Number(tid)}[\\\\/]?$`, "i").test(String(s || "").trim());
const AssistantText = ({ text }) => {
  const at = React.useContext(OutputsCtx), shown = React.useContext(ShownCtx)[useAuiState((s) => s.message.id)];
  const box = React.useRef(null), [viewing, setViewing] = useState(null);
  const listed = at?.listed || [];
  const fileNamed = (el) => { const n = nameOf(el?.textContent); return n ? listed.find((f) => f.name === n || nameOf(f.path) === n) : null; };
  useEffect(() => {
    box.current?.querySelectorAll("code").forEach((c) => {
      if (fileNamed(c)) c.setAttribute("data-tq-file-link", ""); else c.removeAttribute("data-tq-file-link");
      // ...and THIS TASK'S OUTPUTS FOLDER, named as a path, opens on this computer at a press (the owner, 2026-11-06: "can this be a link so
      // i can open it on my machine?") - the server opens the folder it knows, never a path the page sends
      if (at?.tid && isOutputsFolder(c.textContent, at.tid)) c.setAttribute("data-tq-folder-link", ""); else c.removeAttribute("data-tq-folder-link");
    });
  });
  const open = (e) => {
    const d = e.target.closest?.("code[data-tq-folder-link]");
    if (d) { e.preventDefault(); api.post(`/api/task-outputs/${at.tid}/open`).catch(() => {}); return; }
    const c = e.target.closest?.("code[data-tq-file-link]"), f = c && fileNamed(c); if (f) { e.preventDefault(); setViewing(f); } };
  // an answer that was only its summary block is filed as the summary's "did" (general._file): said once, under What I did
  const did = useAuiState((s) => String(s.message.metadata?.custom?.summary?.did || "").trim());
  const { text: said, files } = at ? outputRefs(text, at.tid, at.listed) : { text, files: [] }, { isShown } = shownOnce(files, shown);
  const chat = React.useContext(ChatCtx);
  if (did && String(text || "").trim() === did && !files.length) return null;
  return <>
    {!!said && <div ref={box} onClick={open}><LinkPopups><Md text={said} /></LinkPopups></div>}
    {/* ...in a chat the turn draws the files it made itself, once, inline (TurnFiles) */}
    {!chat && files.map((f) => <PublishedPages key={f} pages={[outputRow(at.tid, f, at.listed)]} open={isShown(f)} />)}
    <FileDialog file={viewing} onClose={() => setViewing(null)} />
  </>;
};
// WHAT CAME IN IS SAID IN ITS SENDER'S WORDS (general.shown_history; the overnight run, 2026-11-03): the mail that carried this turn on, each
// under who sent it, over Taskuary's folded instructions - the second mail of a thread was readable only inside them
const CameIn = ({ mail }) => mail.map((x, i) => (
  <div key={i} className="tq-aui-mail" data-tq-chat-mail="">
    <div className="tq-aui-role">{x.who}</div>
    <div className="tq-aui-mail-bubble">{x.words}</div>
  </div>));
// WHERE THE CHAT IS THE TASK'S HOME (taskLayout.chatHome) it is one stream, oldest to newest (the owner, 2026-11-04: "it should be one chat as
// a agent thinking"): triage's reading opens it, Taskuary's instructions are not drawn, and the mail that woke a turn is a timestamped line
// over the turn it woke - "↓ 2:14 PM · Ray Colton wrote again: …" - its words whole on hover. A brief with no mail (the first) says nothing
const ChatCtx = React.createContext(false);

const when = (at) => {
  if (at instanceof Date) { const y = at.getFullYear(), p = (n) => String(n).padStart(2, "0");
    at = `${y}-${p(at.getMonth() + 1)}-${p(at.getDate())} ${p(at.getHours())}:${p(at.getMinutes())}:${p(at.getSeconds())}`; }
  const d = dayLabel(at); return [d && d !== "Today" ? d : "", fmtTime12(at)].filter(Boolean).join(" ");
};
// IT IS A CHAT (the owner, 2026-11-05: "show the taskuary stuff on left. the inputs on right meaning little email logo like the rail ... that
// shows trigger says something emails came in from x and was sent to agent.. then as new one comes in another one on right side"): each mail that
// started or woke a turn is a prompt on the RIGHT - its channel's mark, who, when - with the answer it woke under it on the left. The owner's own
// reply sent outside Taskuary draws nothing of its own ("not bubbles"): the re-think under it says what it saw
const CHANNEL_WORD = { email: "Email", whatsapp: "WhatsApp message", teams: "Teams message", slack: "Slack message", telegram: "Telegram message", sms: "Text" };
const ChannelMark = ({ channel }) => {
  const c = String(channel || "").toLowerCase();
  const Icon = c === "whatsapp" ? WhatsAppIcon : c === "telegram" ? TelegramIcon : c === "email" || !c ? MailOutlineIcon : ChatBubbleOutlineIcon;
  return <Icon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />;
};
// ...and a burst from one sender reads as one: the next message of the same person on the same channel carries its time alone (the owner's
// four WhatsApp messages in a minute, 2026-11-05: the same "WhatsApp message from … · sent to Taskuary" over each)
// ...icon, who and when - no "sent to Taskuary" (the owner, 2026-11-05: every input goes to it; the words said nothing)
const sameAs = (a, b) => !!a && !!b && a.who === b.who && String(a.channel || "") === String(b.channel || "");
// ...and in the same minute as the one before, no head at all: "6:22 PM" over three lines in a row said nothing (the scenario run, 2026-11-06)
const Arrived = ({ mail }) => mail.filter((x) => !x.own).map((x, i, all) => {
  const more = sameAs(all[i - 1], x), stamp = x.at ? when(x.at) : "", again = more && stamp === (all[i - 1].at ? when(all[i - 1].at) : "");
  return <div key={i} className={`tq-aui-arrived${more ? " tq-aui-arrived-more" : ""}`} data-tq-chat-arrived="">
    {!again && <span className="tq-aui-arrived-head">{more ? stamp : <><ChannelMark channel={x.channel} />
      {[`${CHANNEL_WORD[String(x.channel || "").toLowerCase()] || "Message"} from ${x.who || "someone"}`, stamp].filter(Boolean).join(" · ")}</>}</span>}
    <span className="tq-aui-arrived-words" dir="auto" title={x.words}>{x.words}</span>
  </div>;
});
// what a check-back come due asked to verify, from Taskuary's own line (checkback.TURN) - '' for any other brief
export const checkBackDue = (w) => (/^TASKUARY: the check-back you set on this task is due - ([\s\S]*?)\. Check it now/.exec(String(w || "").trim()) || [])[1] || "";
const UserMessage = () => {
  const brief = useAuiState((s) => !!s.message.metadata?.custom?.brief), mail = useAuiState((s) => s.message.metadata?.custom?.mail), chat = React.useContext(ChatCtx);
  const at = useAuiState((s) => s.message.createdAt);
  // ...a brief with no mail but a SHORT line of its own is a trigger of Taskuary's ("Signed in to the site") - on the right, with the time;
  // a long one is Taskuary's instructions to the agent, never drawn - nor one carrying only the owner's own reply: a short brief over it drew
  // Taskuary's own "THE THREAD CHANGED: …" as a trigger on the right (the scenario run, 2026-11-06)
  const words = useAuiState((s) => textOf(s.message));
  const prev = useAuiState((s) => { const ms = s.thread.messages, i = ms.findIndex((m) => m.id === s.message.id), p = ms[i - 1];
    return p?.role === "user" && !p.metadata?.custom?.brief ? (p.createdAt ? when(new Date(p.createdAt)) : "") : null; });
  // ...and a CHECK-BACK come due is the input of the turn it wakes (checkback.TURN): its own "what", under a clock - long, it was Taskuary's
  // instructions and drew nothing, and the turn stood with no input over it, read as a second agent (the scenario run, 2026-11-06)
  const due = brief && chat ? checkBackDue(words) : "";
  if (due) return <MessagePrimitive.Root className="tq-aui-message tq-aui-brief"><div className="tq-aui-arrived" data-tq-chat-trigger="check-back">
    <span className="tq-aui-arrived-head"><AlarmIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />{["Check-back due", at && when(new Date(at))].filter(Boolean).join(" · ")}</span>
    <span className="tq-aui-arrived-words" dir="auto">{due}</span></div></MessagePrimitive.Root>;
  if (brief && chat) return mail?.some((x) => !x.own) ? <MessagePrimitive.Root className="tq-aui-message tq-aui-brief"><Arrived mail={mail} /></MessagePrimitive.Root>
    : !mail?.length && words && words.length <= 140 ? <MessagePrimitive.Root className="tq-aui-message tq-aui-brief"><div className="tq-aui-arrived" data-tq-chat-trigger="">
      <span className="tq-aui-arrived-head"><KeyIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />{at ? when(new Date(at)) : ""}</span>
      <span className="tq-aui-arrived-words">{words}</span></div></MessagePrimitive.Root> : null;
  // ...and what the owner types is theirs on the right, under their mark and the time ("if user interjects it will show user logo")
  // ...three lines typed in a row read as one, as a sender's burst does (Arrived): the head once, then a new minute's time alone, a same minute nothing
  const stamp = at ? when(new Date(at)) : "";
  if (chat) return (
    <MessagePrimitive.Root className={`tq-aui-message tq-aui-user${prev !== null ? " tq-aui-user-more" : ""}`}>
      {prev === null ? <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />You{stamp ? ` · ${stamp}` : ""}</div>
        : stamp && stamp !== prev ? <div className="tq-aui-user-head">{stamp}</div> : null}
      <div className="tq-aui-user-bubble" dir="auto"><MessagePrimitive.Parts /></div>
    </MessagePrimitive.Root>);
  return brief ? (
    <MessagePrimitive.Root className="tq-aui-message tq-aui-brief">
      <CameIn mail={mail || []} />
      <BriefLine><MessagePrimitive.Parts /></BriefLine>
    </MessagePrimitive.Root>
  ) : (
    <MessagePrimitive.Root className="tq-aui-message tq-aui-user">
      <div className="tq-aui-role">you</div>
      <div className="tq-aui-user-bubble"><MessagePrimitive.Parts /></div>
    </MessagePrimitive.Root>
  );
};
// what each answer published or showed, by the answer's id (the server's `after`): drawn under it, open - the agent chose it
const ShownCtx = React.createContext({});
// what a turn's Next steps count against (agentSummary.nextSteps): the task's reviews and checklist. Null in the dock, which has no turns
// of an agent's to sum up and draws its steps as ever
const WorkCtx = React.createContext(null);
// a turn still running is ONE LINE, "Working on this…", its steps folded under it (the closeout-in-chat spec, 2026-11-04); a turn that
// ended in its summary keeps them folded above it. A turn with no summary - older ones, a CLI that wrote none, one that died - as ever
const live = (m) => m?.status?.type === "running" || String(m?.id || "").startsWith("live-");
// ...and a fold the owner opened stays open: the server's live message is `live-<sid>-<trace revision>` - a new id at every step - and the pane
// itself mounts again when the owner comes back to the task. Kept by the turn, never by the message's id or the DOM
const OPEN_FOLDS = new Set();
const LIVE_SHOWN = 6;
const foldKey = (id) => String(id || "").replace(/^(live-.+)-\d+$/, "$1");
const WorkSteps = ({ data }) => {
  const at = React.useContext(WorkCtx), now = useAuiState((s) => live(s.message)), ended = useAuiState((s) => !!s.message.metadata?.custom?.summary);
  const key = foldKey(useAuiState((s) => s.message.id)), [open, setOpen] = useState(() => OPEN_FOLDS.has(key));
  useEffect(() => { setOpen(OPEN_FOLDS.has(key)); }, [key]);
  // ...AND A TURN THAT ENDED HAS NOTHING STILL AT WORK (the owner, 2026-11-05: a step kept its spinner under the answer): a call that never got
  // its result before the answer was filed is drawn done, never circling
  if (!now && (data?.steps || []).some((s) => s.status === "running")) data = { ...data, steps: data.steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s)) };
  const chat = React.useContext(ChatCtx), keepOut = !chat;
  // ...and in a chat a step is never "failed" (below) - a turn that ended with no summary too: its "failed" stood under a plain answer
  if (!at || (!now && !ended)) return <AgentSteps data={chat ? { ...data, steps: (data?.steps || []).map((s) => (s.status === "error" || s.status === "recovered" ? { ...s, status: "done" } : s)) } : data} />;
  // a failure is never folded away: it is its own line under the fold (a retried one that worked is "recovered", and folds with the rest)
  // ...where the chat is home and the turn ENDED in its summary, a step that failed on the way is part of the way, folded with the rest (the
  // owner, 2026-11-05: "what are all those failures?") - only a turn that failed keeps its failures out
  // ...IN A CHAT A STEP IS NEVER "FAILED" (the owner, 2026-11-05: "it's just a internal thought failure, for the user the task is getting done.
  // failure means nothing"): working or ended, every step rides the one fold as a plain step - a TURN that failed says so in its own words
  const all = data?.steps || [], bad = keepOut ? all.filter((s) => s.kind === "error" || s.status === "error") : [], n = all.filter(isWork).length;
  const toggle = (e) => { const o = e.currentTarget.open; if (o) OPEN_FOLDS.add(key); else OPEN_FOLDS.delete(key); setOpen(o); };
  const calm = chat ? all.map((s) => (s.status === "error" || s.status === "recovered" ? { ...s, status: "done" } : s)) : all;
  // WHILE IT RUNS ITS STEPS ARE OPEN (the owner, 2026-11-05: "it has to show what it's working on a little more than this like pulling from url's
  // etc.. look how other chat libraries show intermediately the tool calls"): a quiet line a step, the newest at the foot with its spinner, the
  // last LIVE_SHOWN of them - those before fold into "N earlier steps". Once it has answered they fold into one "N steps" line, as ever
  if (now) { const cut = Math.max(0, calm.length - LIVE_SHOWN);
    return <div className="tq-aui-live-steps" data-tq-live-steps="" role="status" aria-live="polite">
      {!!cut && <details className="tq-aui-live-earlier"><summary>{plural(cut, "earlier step")}</summary><AgentSteps data={{ steps: calm.slice(0, cut) }} /></details>}
      <AgentSteps data={{ steps: calm.slice(cut) }} />
    </div>; }
  return <>
    <details className="tq-aui-working-fold" open={open} onToggle={toggle}>
      <summary>{n ? plural(n, "step") : "Along the way"}</summary>
      <AgentSteps data={{ steps: calm.filter((s) => !bad.includes(s)) }} />
    </details>
    {!!bad.length && <AgentSteps data={{ steps: bad }} />}
  </>;
};
// ...and with none of its steps on screen yet, the line stands alone (AgentBand)
// ...its clock from the turn's own start: the server's `turn_started` when it has said it (`since`), and never before the newest input in the chat - the line just
// typed is in the thread before the server's history has it, and the clock read the owner's line before that one, "249m 53s" over a turn
// three seconds old (the scenario run, 2026-11-06)
const AtWork = ({ since, began, ...props }) => {
  const folded = useAuiState((s) => { const m = s.thread.messages.at(-1);
    return m?.role === "assistant" && live(m) && (m.content || []).some((p) => p.type === "data" && p.name === "agent_steps"); });
  const typed = useAuiState((s) => turnBegan(s.thread.messages.filter((m) => m.role === "user").map((m) => m.createdAt)));
  // ...the server's own start wins when it has said it: a mail that joined mid-turn is newer than the turn and set its clock back to 0s
  return folded ? null : <AgentBand {...props} since={began || Math.max(since || 0, typed || 0) || null} />;
};
const Nothing = () => null;
// WHEN EACH TURN ANSWERED AND HOW LONG IT RAN (the owner, 2026-11-05: "we need a time and how long each taskuary thing ran and timestamp"): over
// each answer in a chat task, its time and the time from what it answered (the message before it) to the answer
// ...and WHILE IT RUNS, ONE CLOCK (the owner, 2026-11-06): "Working on this… 3s" under it - the head's own "working 0:03" was a second one
const RanFor = () => {
  const at = useAuiState((s) => s.message.createdAt), id = useAuiState((s) => s.message.id);
  const before = useAuiState((s) => { const ms = s.thread.messages, i = ms.findIndex((m) => m.id === id); return i > 0 ? turnBegan(ms.slice(0, i).map((m) => m.createdAt)) : null; });
  // ...a turn still running has not "ran" anything yet: its stamp read "ran 0s" over "Working on this…" (the chat-model stress run, 2026-11-05)
  // ...and the live message is drawn anew at every step, so its own time is the latest step's: the turn began at the server's `since`, else
  // at the line it answers
  const running = useAuiState((s) => live(s.message)), since = useAuiState((s) => s.message.metadata?.custom?.since);
  const start = running ? since || before : before, t = running && start ? new Date(start) : at ? new Date(at) : null;
  if (!t || Number.isNaN(+t)) return null;
  const ran = running ? "" : turnStamp({ start: before, end: t });
  return <span data-tq-ran="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>
    · {when(t)}{ran ? ` · ${ran}` : ""}</span>;
};
const AssistantMessage = () => {
  const shown = React.useContext(ShownCtx)[useAuiState((s) => s.message.id)], at = React.useContext(OutputsCtx), work = React.useContext(WorkCtx);
  const words = useAuiState((s) => textOf(s.message)), custom = useAuiState((s) => s.message.metadata?.custom), chat = React.useContext(ChatCtx);
  // the turn is the chat's last entry AND has answered: it carries its card - a turn still at work never takes the one before it's draft (the owner,
  // 2026-11-05: "email draft is being shown below the new prompt ... it's connected to the prior agent taskuary thing")
  const newest = useAuiState((s) => s.thread.messages.at(-1)?.id === s.message.id && !live(s.message));
  // the newest turn that ANSWERED (a summary, not at work): its draft stays on it when something newer comes
  const lastAnswered = useAuiState((s) => [...s.thread.messages].reverse().find((m) => m.role === "assistant" && !live(m) && m.metadata?.custom?.summary)?.id === s.message.id);
  // WHAT THIS TURN MADE AND SET UP, IN IT (the owner, 2026-11-05): in a chat, the files it made inline, and an act it proposed drawn as its
  // connector declares it (a post as the post, ActionCard) under its Next steps - live on the newest turn, read-only (gone, or not) before
  const id = useAuiState((s) => s.message.id);
  const posts = work && chat ? (work.cards || []).filter((p) => p.after === id) : [];
  const made = at && chat ? turnFiles({ listed: at.listed, id, words, did: custom?.summary?.did, tid: at.tid,
    skip: (work?.cards || []).map((p) => p.post?.image).filter(Boolean) }) : [];
  const madeNames = new Set(made.map((f) => f.name));
  const lead = posts.length ? posts.map((p) => <ActionCard key={p.ReviewId} row={p} tid={at?.tid} live={newest} onChanged={work.refresh} />) : null;
  const files = made.length ? <TurnFiles files={made} /> : null;
  const { rest: shownRest } = shownOnce(at ? outputRefs(words, at.tid, at.listed).files : [], shown);
  // ...nor a picture its post card already carries (the owner saw the chart twice: shown by the turn, and on the post)
  const postPics = new Set(posts.map((p) => String(p.post?.image || "").split(/[\\/]/).pop()).filter(Boolean));
  const rest = chat ? shownRest.filter((p) => !madeNames.has(p.name) && !postPics.has(String(p.name || "").split(/[\\/]/).pop())) : shownRest;
  const running = useAuiState((s) => live(s.message));
  // ...and it copies at its corner (the owner, 2026-11-05): what the turn says - its words, else its summary's parts
  const said = custom?.summary && !answerShown(custom.summary, words)
    ? [custom.summary.about, custom.summary.did].map((x) => String(x || "").trim()).filter(Boolean).join("\n\n") : words;
  return (
    <MessagePrimitive.Root className={`tq-aui-message tq-aui-agent${chat && said ? " tq-copy-host" : ""}`}>
      {chat && !!said && !running && <CopyCorner text={said} label="Copy this answer" />}
      <div className="tq-aui-role">{React.useContext(AgentNameCtx)}{React.useContext(ChatCtx) && <RanFor />}</div>
      <div className="tq-aui-agent-body">
        {/* ...where the chat is home, a turn that ended in its summary IS that summary: the agent's own prose above it said the same at
            length (the owner, 2026-11-05: "short text as possible") */}
        {/* ...but never when the words ARE the answer - the agent says so in its summary (agentSummary.answerShown; the owner, 2026-11-05:
            "it should say where the link is. this is just patting itself on the back and not showing the link") */}
        <MessagePrimitive.Parts components={{ Text: chat && custom?.summary && !answerShown(custom.summary, words) ? Nothing : AssistantText, data: { by_name: { agent_steps: WorkSteps } } }} />
        {!!rest.length && <PublishedPages pages={rest} open />}
        {!custom?.summary && files}
        {!custom?.summary && lead && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
          <Typography component="span" sx={{ display: "block", color: "#292824", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>Next steps</Typography>{lead}</Box>}
        {/* ...and where the chat is the task's home, the newest one's Next steps holds the draft cards (`next`, Task 4.2) */}
        {work && !custom?.summary && newest && work.next && chat && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
          <Typography component="span" sx={{ display: "block", color: "#292824", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>Next steps</Typography>{work.next}</Box>}
        {work && custom?.summary && <AgentSummary summary={custom.summary} folded={!!custom.folded} reviews={work.reviews} checklist={work.checklist}
          acts={work.acts} next={custom.folded ? null : work.next} lastAnswered={lastAnswered} kept={custom.drafts} lead={lead} made={files} />}
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

// WHAT THE AGENT ASKED (the UI audit's W6): the question in its own words, and a press for each answer its CLI's own question tool or
// on-screen chooser offered - a general agent's question is plain words and carries none (the owner, 2026-11-03: chips only for those
// two; general.py records its ask with no choices), plus Taskuary's own Signed in and Done. ONE BOX TYPES AN ANSWER (the owner, 2026-11-03: "i hate this
// double ui. we don't need question box if we have way to answer on the bottom"): the card's own field and Answer button went - what is
// typed in the composer while a question is open is its answer (AssistantThread's answerTyped). `onAnswer(text)` delivers either - a
// reply in this conversation, or the worker's own answer road - and throws with the reason when it could not.
// A SIGN-IN it waits on (request id `signin:<site>`, signin.py) is NO CARD (the owner, 2026-11-03: "remove that stupid box again as we did
// with the questions ... just have the question and link to fill it out securely"): the question as a line of the conversation, and a
// link to the one-time fill page (Taskuary types it, the agent never sees it). Signing in on the page beside it needs no press: Taskuary
// sees the page go past the sign-in (signin.watch), and "done" typed in the box below says so too.
export function AgentAsks({ asking, name, onAnswer, taskId }) {
  const [going, setGoing] = useState(false), [err, setErr] = useState("");
  const site = String(asking.request_id || "").startsWith("signin:") ? asking.request_id.slice(7) : "";
  const choices = site ? [] : asking.choices || [];
  const fillPage = async (e) => {
    e?.preventDefault?.();
    setErr("");
    try {
      const app = howToOpen(window) === "app";
      const { data } = await api.post(`/api/tasks/${taskId}/signin/link${app ? "?open=1" : ""}`);
      if (!app) window.open(data.url, "_blank", "noopener");
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { setErr(""); setGoing(false); }, [asking?.request_id]);
  const send = async (w) => {
    if (going) return;
    setGoing(true); setErr("");
    try { await onAnswer?.(w); } catch (e) { setErr(errText(e)); } finally { setGoing(false); }
  };
  if (site) return (
    <p className="tq-aui-signin" data-tq-asking={asking.request_id} data-tq-signin-ask={site}>
      {String(asking.text || `Sign in to ${site} to continue`).replace(/\.?\s*$/, "")}
      {taskId ? <> - <a href="#" onClick={fillPage} data-tq-signin-link=""
        title={`A one-time page to type the ${site} sign-in - Taskuary types it into the browser and the agent never sees it`}>fill it in securely</a>
        , or sign in on the page.</> : ", on the page."}
      {err && <span className="tq-aui-asking-err" role="alert"> {err}</span>}
    </p>
  );
  // A QUESTION IS SAID IN PLAIN WORDS (the closeout-in-chat spec, 2026-11-04): the agent's own sentence, a line of the conversation - not
  // a card headed "Taskuary asked you something". An approval or a stuck turn keeps its lead: its words are a command, not a question
  const plain = subState({ request: asking }) === "asking" && String(asking.text || "").trim();
  return (
    <div className={plain ? "tq-aui-asked" : "tq-aui-asking"} data-tq-asking={asking.request_id}>
      {plain ? <p className="tq-aui-asked-q">{plain}</p> : <>
        <b>{says(subState({ request: asking }), name)}</b>
        <span className="tq-aui-asking-q">{asking.text}</span></>}
      {!!choices.length && <div className="tq-aui-asking-choices">
        {choices.map((c) => <Button key={c} size="small" variant="outlined" disabled={going} onClick={() => send(c)}>{c}</Button>)}
      </div>}
      {err && <span className="tq-aui-asking-err" role="alert">{err}</span>}
    </div>
  );
}

function AssistantThread({ task, messages, published, onAsked, onStop, selectionRef, attachmentsRef, onSent, onStarted, onClearAttachments, onAttach, onAttachBack,
  dock = false, dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  serverBusy = false, provider, name = "Taskuary", work, since, began = null, revision = 0, asking, onAnswer, drafts = [], acts = [], onDraftDecided, starting = "", noComposer = false,
  onEnded, approve = null, chat = false, reading = null, came = null, noAi = null, closedLine = "", tail = null }) {
  // "working" is only ever true on a WORK window. In the dock nothing below changes at all: the
  // dock is the assistant that helps you run Taskuary, not an agent doing a job (the owner,
  // 2026-09-08: "make sure the ux doesnt change or the general assistants").
  const working = !dock && !!serverBusy;
  // ...where the chat has no summary yet, what Close out held (`next`) stands under the thread on its own - a draft is never without its one place
  const nextAt = React.useContext(WorkCtx), summed = lastAnswerSummed(messages);
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
      // THE FILES LEAVE THE BOX WITH THE SEND (the owner, 2026-11-06: two pictures sent, their chips still in the box): let go at the server's
      // first word back - the send accepted - never at the turn's end, minutes on; a send refused keeps them. Only these: one added meanwhile stays
      const sentFiles = attachmentsRef.current.map((a) => a.path);
      let gone = !sentFiles.length;
      const took = () => { if (!gone) { gone = true; onClearAttachments(sentFiles); } };
      const events = [];
      // ..."Started Claude Code (on this computer)" only on the conversation's first turn: it opened every follow-up the owner typed
      // (the desktop stress test, 2026-11-03)
      const keepStart = !runMessages.some((m) => m.role === "assistant");
      const content = (reply) => [...stepsPart(events, { answer: reply || "", keepStart }), ...(reply ? [{ type: "text", text: reply }] : [])];
      // A run that fails has to SAY so, here, under the question. Thrown out of the adapter it
      // is swallowed: the owner sees their own message and nothing after it, which is
      // indistinguishable from an agent that is still thinking (the wall, 2026-08-31). The
      // reasons are all things a person can act on - the session ended, another one holds this
      // task, it is still answering the last question, no AI is connected - so they are shown.
      try {
      for await (const event of streamAssistant(task.TaskId, body, abortSignal)) {
        if (event.type !== "error") took();
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
          onSent(event.payload);
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
    if (applied.current === revision) return undefined;
    // this pane's own stream is the live truth while it runs; its `done` files the server's copy - taken the moment the run ends: kept, the
    // turn this pane streamed wore the runtime's own stamp, made as it began, and read "ran 0s" over an answer that took minutes (the owner,
    // 2026-11-05)
    if (!runtime.thread.getState().isRunning) { applied.current = revision; runtime.thread.reset(initial(shown.current)); return undefined; }
    const off = runtime.thread.subscribe(() => {
      if (runtime.thread.getState().isRunning || applied.current === revision) return;
      applied.current = revision; off(); runtime.thread.reset(initial(shown.current));
    });
    return off;
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
  // ...where the chat is home a closed task keeps its box: what is typed reopens it and carries on (server._refuse_closed_chat, 2026-11-05)
  const closedChat = !dock && !chat && ["done", "dropped"].includes(String(task?.Status || ""));
  /* WHILE A QUESTION IS OPEN THE COMPOSER ANSWERS IT (the owner, 2026-11-03: the card had a box of its own, and the answer was typed here
     anyway): its words take the road the card's Answer took (onAnswer) - this conversation's next message, or the asking terminal's answer -
     so the card and the "waiting on you" chip clear the same way. A typed answer to a multiple-choice question goes as typed. */
  const [askErr, setAskErr] = useState(""), answering = useRef(false);
  useEffect(() => { setAskErr(""); }, [asking?.request_id]);
  const answerTyped = (e) => {
    if (dock || !asking) return;
    e.preventDefault();
    const c = runtime.thread.composer, w = c.getState().text.trim();
    if (!w || answering.current) return;
    answering.current = true; setAskErr(""); c.setText("");
    // ...drawn at once at the foot as the owner's (the owner, 2026-11-05: "send it messages and it did not appear right away")
    // ...and drawn ONCE: where the answer goes into this thread (answerAsk's own-session road) the thread draws it, and notShown keeps the held copy away
    const id = `held-${Date.now()}`, after = (messages || []).filter((m) => m?.role === "user").length;
    setHeld((h) => [...h, { id, text: w, after, drawn: mineDrawn.length }]);
    Promise.resolve(onAnswer?.(w)).catch((x) => { setHeld((h) => h.filter((l) => l.id !== id)); c.setText(w); setAskErr(errText(x)); })
      .finally(() => { answering.current = false; });
  };
  /* TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): Enter while the turn runs put a newline in the box and the line never left -
     under a placeholder that says "Add something for it to pick up". The line is held: drawn at once as the owner's, and sent to the same
     session, which takes it as its next turn (send_prompt waits its turn). The thread's own copy replaces it once the server has it. */
  const [held, setHeld] = useState([]);
  useEffect(() => { setHeld((h) => (h.length ? stillHeld(h, messages) : h)); }, [messages]);
  // the owner's lines the thread on screen draws - its own appends too, which the server's copy has not caught up with (heldLines.notShown)
  const [mineDrawn, setMineDrawn] = useState([]);
  useEffect(() => {
    const read = () => { const ms = runtime.thread.getState().messages.filter((m) => m.role === "user");
      setMineDrawn((was) => (was.length === ms.length && was.every((m, i) => m === ms[i]) ? was : ms)); };
    read(); return runtime.thread.subscribe(read);
  }, [runtime]);
  const holdLine = (e) => {
    if (dock || asking) return;
    const c = runtime.thread.composer, w = heldLine(e, c.getState().text, runtime.thread.getState().isRunning);
    if (!w) return;
    e.preventDefault(); c.setText("");
    const id = `held-${Date.now()}-${Math.random()}`, after = (messages || []).filter((m) => m?.role === "user").length;
    // ...WITH THE BOX'S FILES: a line held mid-turn went without them, and they sat on in the box (the owner, 2026-11-06) - put back if it did not go
    const files = [...attachmentsRef.current];
    if (files.length) onClearAttachments(files.map((a) => a.path));
    setHeld((h) => [...h, { id, text: w, after, drawn: mineDrawn.length }]);
    api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text: w, attachments: files.map((a) => a.path) }, { timeout: 0 })
      .catch((x) => { setHeld((h) => h.map((l) => (l.id === id ? { ...l, err: errText(x) } : l))); if (files.length) onAttachBack(files); });
  };
  const askWords = dock || !asking ? "" : String(asking.request_id || "").startsWith("signin:") ? "Message the agent - never your password" : "Answer the agent's question…";
  const atWork = dock ? <Thinking provider={provider} /> : <AtWork name={name} provider={provider} work={work} since={since} began={began} starting={starting} />;
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className={chat ? "tq-aui-thread tq-aui-chat" : "tq-aui-thread"}>
        <ThreadPrimitive.Viewport ref={viewport} className="tq-aui-viewport">
          {/* ...where the chat is home, the ask as triage read it is its first line (ChatCtx) */}
          {chat && !messages?.length && reading}
          {!messages?.length && !starting && !(chat && reading) && (
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
          {/* the answer is being written somewhere else - another tab, or this pane before it was
              reopened - and the poll is what tells us so */}
          <ThreadPrimitive.If running={false}>{serverBusy && atWork}</ThreadPrimitive.If>
          {/* ...and the lines typed while it works come UNDER its "Working on this…": over it, they stood between the turn's name and its
              clock, an empty head with the owner's words below it (the scenario run, 2026-11-06) */}
          {notShown(held, mineDrawn).map((l) => <div key={l.id} className="tq-aui-message tq-aui-user" data-tq-held="">
            <div className="tq-aui-role">you</div><div className="tq-aui-user-bubble" dir="auto">{l.text}</div>
            {l.err && <div className="tq-aui-hint" role="alert">{l.err}</div>}</div>)}
          {/* Only once it has stopped typing. An offer to "run this again, daily" hanging under a
              half-written answer is an offer to schedule something nobody has read yet - and it
              sat there through every tool call, which is where the eye goes while waiting. */}
          <ThreadPrimitive.If running={false}>
          {dock && <DockActions messages={messages} expanded={dockExpanded} onNavigate={onDockNavigate} onChanged={onDockChanged} />}
          {/* THE QUESTION IS ON THE AGENT'S OWN CANVAS (owner-approved, the UI audit's W6, 2026-10-21): the
              card said "Agent asked you something" over a pane that never showed what - the question lived only in the rail row's
              hover. It was taken out on 2026-10-19 as a repeat of the answer above; an agent asking from a terminal has no answer
              above at all. Its answer is typed in the composer below (2026-11-03), its own presses on the card. */}
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
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{heldActsLine(acts)}</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}
            </Box>
          )}
          </ThreadPrimitive.If>
          {/* ...a chat no turn has summed up yet: what Close out held, under the thread (Task 4.2) */}
          {/* ...a section of the chat like the rest (the owner, 2026-11-05: "still see line of next steps"): a bold head, no rule over it */}
          {/* ...and in a chat no answer carries it yet (a reply triage drafted, no agent run - the owner, 2026-11-06): the draft under the ask */}
          {!dock && nextAt?.next && !summed && !working && (!chat || messages?.at(-1)?.role !== "assistant") && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
            <Typography component="span" sx={{ display: "block", color: "#292824", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>Suggested reply</Typography>{nextAt.next}</Box>}
          {/* THE AGENT'S DRAFT IS SAID WHERE ITS QUESTIONS ARE ASKED (the owner, 2026-11-02): the task page's notice of it (AgentDraftNotice),
              whose press opens Close out at it - working or not, since the agent saves it mid-turn */}
          {!dock && approve}
          {/* ...AND HOW IT CLOSED, the stream's last line (the owner, 2026-11-06): a closed task is the same chat, its close said in it */}
          {!dock && closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
          {/* ...and under it all, folded, what AI the task used (AiUsed.jsx; the owner, 2026-11-06: "hidden you can open and see it") */}
          {!dock && tail}
        </ThreadPrimitive.Viewport>
          <div className="tq-aui-footer">
            {/* NO AI: one small line over the box, its Connect an AI beside it (the owner, 2026-11-06) - the box stays the box */}
            {!dock && noAi}
            {/* A CLOSED task's conversation is read, not typed into: a message started a live session on a done task, which
                then read "waiting on you" under a bar offering only Reopen (the owner, 2026-10-14). The server refuses it too. */}
            {/* ...and ONE DOOR: while the conversation is open the box is how it goes on (no Continue on the bar, 2026-09-29), but once its
                run has ENDED the bar offers Continue - and a box beside it read as a second way in (the owner, 2026-10-26: "before I hit
                continue it has a space to type into the agent? coding agents don't have that"). `noComposer` is that Continue (TaskPage). */}
            {closedChat ? <div className="tq-aui-hint" role="status" style={{ padding: "10px 4px" }}>
              {/* ...where the chat is home the box below IS Continue: Reopen alone brings it back */}
              This task is closed. Press {btn("reopen")}{chat ? "" : <>, then {btn("continue")},</>} to pick the conversation back up.</div> : noComposer ? null : <>
            {/* THE ONE BOX (AgentSummary.OneBox): paperclip, chips, words, mic, stop, Send - the same component as every other box, assistant-ui's
                composer its root, input and Send. Its files inside it, the one attachment look in one line (the owner, 2026-11-05), and WHERE IT CAME
                FROM a chip at its left (2026-11-06: "keep the prompt box thin... put the from you in the left side of the prompt box") - a press opens it */}
            <OneBox root={ComposerPrimitive.Root} rootProps={{ onSubmit: answerTyped }} onFiles={onAttach}
              chips={attachmentsRef.current.length || came ? <>
                {came && <AttachChip data-tq-came-chip="" name={came.label} title={came.title || came.label} icon={came.icon || false} onClick={came.onOpen}
                  sx={{ cursor: came.onOpen ? "pointer" : "default" }} />}
                {attachmentsRef.current.map((a) => <AttachChip key={a.path} data-tq-file-chip={a.name} name={a.name} onRemove={() => onClearAttachments(a.path)} />)}</> : null}
              /* ...by the name the pane shows (kinds.json `shown`): an analyst's box said "the assistant" (the email walk, 2026-10-29) */
              input={<ComposerPrimitive.Input className="tq-aui-input" onKeyDown={holdLine} placeholder={askWords || (dock ? "Tell Taskuary what to do next…" : MESSAGE)} />}
              onMic={(t) => { const c = runtime.thread.composer, was = c.getState().text; c.setText(was.trim() ? `${was.trimEnd()} ${t}` : t); }}
              /* stopping is an ACT: closing this page is not one. The button tells the server to stop the run; abandoning the tab just detaches
                 from it (server.py) - and A TURN THIS PANE DID NOT START has the same stop (the owner, 2026-11-05): a turn woken by new mail, or one
                 running when the page was opened, runs on the server, and the runtime's Cancel stays hidden */
              extra={<><ComposerPrimitive.Cancel className="tq-aui-cancel" aria-label="Stop response" onClick={onStop}><CloseIcon fontSize="small" /></ComposerPrimitive.Cancel>
                {working && <ThreadPrimitive.If running={false}><button type="button" className="tq-aui-cancel" data-tq-stop-turn="" aria-label="Stop response"
                  title="Stops this turn - the chat stays, and what you type next carries on" onClick={onStop}><CloseIcon fontSize="small" /></button></ThreadPrimitive.If>}</>}
              send={<ComposerPrimitive.Send className="tq-aui-send" aria-label={!dock && asking ? "Send your answer" : "Send"} onClick={answerTyped}><SendIcon fontSize="small" /></ComposerPrimitive.Send>} />
            {askErr && <div className="tq-aui-asking-err" role="alert" style={{ padding: "4px 4px 0" }}>{askErr}</div>}
            <div className="tq-aui-hint">Enter sends · Shift+Enter adds a line · paste, drop or attach a file</div></>}
          </div>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export function GeneralWorkspace({ task, onSession, onAnswered, compact = false, dock = false, toolsAt = null,
  dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  onDockNewChat, noAiSaid = false, noTools = false, noComposer = false, liveSid = "", reread = 0, approve = null, mails = [], reviews = [],
  checklist = null, opening = false, next = null, chat = false, came = null, closedLine = "", tail = null }) {
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
  // ...ANY FILE, not pictures only (the owner, 2026-11-05: "does drop in the prompt box attach it in all prompt boxes?"): a picture keeps the
  // task's own image road, anything else the prompt's file road (promptImages.savePromptFile) - the agent reads either from its path
  const upload = async (files) => {
    const list = [...(files || [])];
    if (!list.length) return;
    setUploading(true); setError("");
    try {
      const added = [];
      for (const file of list.slice(0, MAX_IMAGES)) {
        if (!IMAGE_TYPES.test(file.type)) { const got = await savePromptFile(file); added.push({ name: got.name, path: got.path }); continue; }
        const r = await api.post(`/api/tasks/${task.TaskId}/waitroom/image`, file, { headers: { "Content-Type": file.type } });
        added.push({ name: file.name || "pasted image", path: r.data.path });
      }
      setAttachments((old) => [...old, ...added]);
    } catch (e) { setError(errText(e)); }
    finally { setUploading(false); }
  };
  // one path (a chip's x), or the paths a send took - never the whole box, so a file added since stays
  const clearAttachments = useCallback((paths) => setAttachments((old) => (paths == null ? [] : old.filter((a) => ![paths].flat().includes(a.path)))), []);
  const attachBack = useCallback((files) => setAttachments((old) => [...files.filter((f) => !old.some((a) => a.path === f.path)), ...old]), []);
  const sent = useCallback((payload) => { accept(payload); setRevision((k) => k + 1); }, [accept]);
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
  /* On screen, the agent's CLI stays open: the server reaps one nobody touches for 30 minutes, and this is the touch. Nothing starts here. */
  useEffect(() => {
    const seen = () => { if (!document.hidden) api.post(`/api/tasks/${task.TaskId}/assistant/seen`).catch(() => {}); };
    seen(); const t = setInterval(seen, 60000);
    return () => clearInterval(t);
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
  // ...and the moment the PAGE learns a start is under way (`opening`, the task's own read of general.OPENING): this pane may have loaded
  // before it, idle, and polled nothing - "Starting…" waited ~10 s for something else to read it again (the owner, 2026-11-04)
  const busy = !!data?.session?.busy || !!data?.starting || (!dock && opening);
  // ...and whether this turn has drawn anything yet: its trace holds more than what Taskuary itself writes as a turn opens - the `start`,
  // the prompt it sent and the CLI's launch line (server's run-tail reads them the same way: ours, not news)
  const drawn = (data?.session?.trace || []).some((e) => e?.type && !["start", "prompt"].includes(e.type) && !(e.type === "tool" && e.name === "cli"));
  /* ...AND WHILE IT WAITS ON THE PAGE - a sign-in or a hand-over - which Taskuary itself can answer: the saved sign-in typed, the fill page
     sent, the owner signing in on the page (signin.watch). None of those is this pane's own send, so nothing read again: the question and
     "your turn - type" stood over a page already signed in, the agent's next answer and its held click unseen until a reload (the
     browser-agent walk, 2026-11-04). */
  const onPage = waitsOnPage(data?.asking || null);
  useEffect(() => {
    if (!busy && !onPage) return undefined;
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
        // (a read made only because it waits on the page tells the page of a session only when there is one: an agent asking from a
        // terminal has none here, and a null swapped the task's agent view out from under its question)
        if (busy || fresh.session) onSession?.(fresh.session || null);
        if (grew || traceChanged) setRevision((k) => k + 1);
      } catch { /* it will still be there next tick */ }
    }, drawn ? 2500 : 1000);      // a start that has drawn nothing yet is read every second: its first word gives the room at once
    return () => { live = false; clearInterval(timer); };
  }, [busy, onPage, drawn, task.TaskId, data?.messages, onSession]);
  // ...and what a read brings is handed to the standing thread (a revision bump), as the poll does: taken into `data` alone, the owner's
  // Continue note waited for the next poll to show (the owner, 0.3.9.51: "I did Continue, filled it out and nothing happened")
  const refresh = useCallback(() => {
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => { accept(r.data); setRevision((k) => k + 1); }).catch(() => {});
  }, [accept, task.TaskId]);
  // A SESSION ANOTHER DOOR STARTED (`liveSid`, the page's live one): the canvas's Continue card, the Assistant, the phone. The page
  // adopted it, but this conversation had loaded before it existed and polls only while it knows of a turn, so a Continue with a note
  // showed the old turns under an agent that had already asked its question (the agents walk, 2026-10-26). Read again when they differ.
  // ...but a turn that FAILED is read without handing the read to the thread: the bump swapped in the server's copy, which has neither
  // the reason nor - when it failed before the agent took it - the owner's own words, so a refused send left nothing on screen (the owner,
  // 2026-11-02: "the text goes no where"). The page still learns the session is down (accept -> onSession); the thread keeps both.
  const failed = useCallback(() => {
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => accept(r.data)).catch(() => {});
  }, [accept, task.TaskId]);
  const loaded = !!data, knownSid = data?.session?.sid || "";
  useEffect(() => { if (loaded && liveSid && knownSid !== liveSid) refresh(); }, [loaded, liveSid, knownSid, refresh]);
  // ...and at once when that door says it answered (`reread`, bumped by the page): the note is on the conversation by then, and the
  // session it starts is seconds away
  useEffect(() => { if (loaded && reread) refresh(); }, [reread]);  // eslint-disable-line react-hooks/exhaustive-deps
  // ...and when the page learns a start is under way: the session it opens is read now, not a poll later
  useEffect(() => { if (loaded && opening && !dock) refresh(); }, [opening]);  // eslint-disable-line react-hooks/exhaustive-deps
  // ...and when the task itself moves (`task-changed`: a mail joined, a turn began - workerstate.record): a turn the SERVER woke on a live,
  // idle session - new mail, a check-back - was never read, as nothing polls an idle pane, and the open chat sat on its first answer while
  // three more turns ran under it (the scenario run, 2026-11-06). Read once then; a turn found at work is the poll's from there. Never over
  // a turn this pane streams itself, whose own copy is the one on screen
  const quietRef = useRef(false); quietRef.current = loaded && !busy && !streaming && !dock;
  useEffect(() => onLive("task-changed", (ev) => { if (quietRef.current && touches(ev, task.TaskId)) refresh(); }), [task.TaskId, refresh]);
  const pasted = (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); upload(files); }
  };
  const dropped = (e) => { const files = [...(e.dataTransfer?.files || [])]; if (files.length) { e.preventDefault(); upload(files); } };
  const dragging = (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); };
  const startNewChat = async () => {
    if (!onDockNewChat || busy || newChatBusy || !shownMessages.length) return;
    setConfirmNewChat(false); setNewChatBusy(true); setError("");
    try { await onDockNewChat(); }
    catch (e) { setError(errText(e)); setNewChatBusy(false); }
  };

  // ...AND ONCE IT IS UP FOR THE OWNER IT STAYS UP until the agent answers again (the owner, 2026-11-05, signing in to a site in two steps: "I put
  // in username then hit next the box disappeared then reopened to put in password. You can leave it open until auth is done"): between a
  // sign-in's pages there is a moment with no ask open, and the page went away under them
  const needRaw = needsOwner(data?.asking && data.asking.request_id !== answered ? data.asking : null,
      (data?.browserActs || []).map((r) => heldOn(r, data?.session?.sid)).filter(Boolean)), answers = (data?.messages || []).filter((m) => m?.role === "assistant").length;
  const [needHeld, setNeedHeld] = useState(null);
  useEffect(() => { if (needRaw) setNeedHeld(answers); }, [needRaw]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (needHeld != null && !needRaw && (answers > needHeld || !data?.session?.sid)) setNeedHeld(null); }, [answers, needRaw, needHeld, data?.session?.sid]);
  const needNow = needRaw || needHeld != null;

  // ...a start the page already knows of says so before the conversation's first read lands, never a 520px spinner over nothing
  if (!data && !error) return !dock && opening
    ? <Box data-tq-starting="" sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.75, overflow: "hidden", bgcolor: PANEL2, px: 1.5, pt: 1.5, ...(compact ? { height: "auto" } : { flex: "0 0 auto" }) }}>
        <AgentBand name={agentName(task)} work={workOf([])} starting={startingLine(agentName(task))} /></Box>
    : <Box sx={{ height: 520, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>;
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
  const since = turnStart(shownMessages), began = session?.busy && session?.turn_started ? session.turn_started * 1000 : null;
  // name the backend that is thinking. The session's own provider is the truth once it has one; on
  // a first turn there is no session yet, so fall back to the one the picker is showing.
  const pickedLabel = (data?.providers || []).find((p) => String(p.id) === String(connectorId))?.label;
  // STARTED AND SILENT: the agent is on its way and has filed nothing - the pane is that one line high, not the room an answer gets
  const quiet = !dock && busy && !(data?.messages || []).some((m) => m.role === "assistant");
  // ...and a start onto a conversation that has answered before (Continue, a carried-on turn): the same line until this turn draws its
  // first output, under the turns already there - never "is working" over a session that has not come up yet (2026-11-04)
  const starting = quiet || (!dock && (data?.starting || opening) && !drawn) ? startingLine(name, session?.provider || pickedLabel) : "";
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
  // the task's checklist where the page has not handed it in: the row carries it (store.list_tasks selects t.*)
  const steps = checklist || (() => { try { const a = JSON.parse(task?.Checklist || "[]"); return Array.isArray(a) ? a : []; } catch { return []; } })();
  const thread = (
    <ChatCtx.Provider value={chat && !dock}><AgentNameCtx.Provider value={dock ? name : AGENT_TURN}><ShownCtx.Provider value={placed.by}>
    <WorkCtx.Provider value={dock ? null : { reviews, checklist: steps, acts: [...(data?.browserActs || []), ...(data?.playbookDrafts || [])], next,
      cards: data?.cards || [], refresh }}>
    <OutputsCtx.Provider value={dock ? null : { tid: task.TaskId, listed: data?.outputs }}>
      {/* ...and every other file in the task's outputs folder - one no answer names - at the foot, with what it published or showed */}
      <AssistantThread key={task.TaskId} revision={revision} task={task} messages={shownMessages}
        published={dock ? placed.foot : [...placed.foot, ...uncited(data?.outputs, shownMessages.filter((m) => m.role === "assistant").map(textOf), task.TaskId)
          // ...a file its turn draws, or a post's own picture, is not one more row at the foot of a chat
          .filter((r) => !(chat && (shownMessages.some((m) => m.id === r.after) || (data?.cards || []).some((p) => p.post?.image === r.path))))]}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onStarted={started} onEnded={failed} onClearAttachments={clearAttachments} onAttachBack={attachBack}
        onAttach={upload}
        dock={dock} dockExpanded={dockExpanded} prompt={ownPrompt || prompt} onPromptUsed={promptUsed}
        asking={turn && viewShown ? null : asking} onAnswer={answerAsk} noComposer={noComposer} approve={approve}
        onBusyChange={threadBusy} onDockNavigate={onDockNavigate} onDockChanged={onDockChanged}
        serverBusy={busy} provider={session?.provider || pickedLabel} name={name} work={work} since={since} began={began}
        drafts={data?.playbookDrafts || []} acts={actsHere} onDraftDecided={refresh} starting={starting}
        chat={chat && !dock} reading={chat && !dock && readingOf(data?.thread || task?.ThreadJson)?.asking
          ? <div className="tq-aui-ask" data-tq-chat-ask="">{readingOf(data?.thread || task?.ThreadJson).asking}</div> : null}
        came={chat && !dock ? came : null} closedLine={chat && !dock ? closedLine : ""} tail={chat && !dock ? tail : null}
        noAi={chat && !dock && !data?.providers?.length && !noAiSaid && !data?.demo
          ? <div className="tq-aui-noai" data-tq-no-ai="">No AI is connected yet - what you type waits for one. <ConnectAi size="small" variant="text" /></div> : null} />
    </OutputsCtx.Provider>
    </WorkCtx.Provider>
    </ShownCtx.Provider></AgentNameCtx.Provider></ChatCtx.Provider>
  );
  /* CHIP-SIZED, AND THEY GIVE WAY (the owner, 2026-11-03, Agent beside Close out: "this ui looks weird when split? make the model choice
     smaller"): a 220px brain picker and a 150px model box that never shrank sat on the heading's title - "Tasku… / answ…" - in a ~500px
     half. Each is a small chip now that ends in … before the title does, the model the CLI's own list (as the dock's) where it has one,
     and Full screen keeps its icon alone where its word has no room (TaskPage's agent heading) */
  const brainNow = (data?.providers || []).find((p) => String(p.id) === String(connectorId));
  const chipSx = { height: 24, fontSize: 11, bgcolor: PANEL2, minWidth: 64, flexShrink: 1, "& .MuiSelect-select": { py: 0, pl: 1, pr: "22px !important" },
    "& .MuiSelect-icon": { fontSize: 17, right: 2 } };
  const tools = (<>
    <Select size="small" value={connectorId} displayEmpty inputProps={{ "aria-label": "Agent" }} title={brainNow?.label || undefined} onChange={(e) => {
      const provider = data?.providers?.find((p) => String(p.id) === String(e.target.value));
      updateProvider(e.target.value, provider?.model || "");
    }}
      sx={{ ...chipSx, maxWidth: 150 }}>
      {!data?.providers?.length && <MenuItem value="">No agent connected</MenuItem>}
      {(data?.providers || []).map((p) => <MenuItem key={p.id} value={String(p.id)}>{p.label}</MenuItem>)}
    </Select>
    {brainNow?.models?.length
      ? <ModelSelect model={model} size={24} empty="provider default" info={{ models: brainNow.models }} sx={{ ...chipSx, maxWidth: 120 }}
          onModel={(m) => { setModel(m); if (connectorId) updateProvider(connectorId, m); }} />
      : <TextField size="small" value={model} placeholder="provider default" inputProps={{ "aria-label": "Model" }} onChange={(e) => setModel(e.target.value)}
          onBlur={() => connectorId && updateProvider(connectorId, model)}
          sx={{ width: 110, minWidth: 64, flexShrink: 1, "& .MuiInputBase-root": { height: 24, bgcolor: PANEL2 }, "& input": { py: 0, px: 1, fontSize: 11, textOverflow: "ellipsis" } }} />}
    <Button size="small" onClick={toggleFull} aria-label={full ? "Exit full screen" : "Full screen"} sx={{ minWidth: 0, fontSize: 11, flexShrink: 0, whiteSpace: "nowrap" }}
      title={full ? "Back to the page (Esc)" : "Give this conversation and its browser the whole window"}
      startIcon={full ? <CloseFullscreenIcon sx={{ fontSize: 13 }} /> : <OpenInFullIcon sx={{ fontSize: 13 }} />}>
      <span data-tq-full-word="">{full ? "Exit full screen" : "Full screen"}</span>
    </Button>
  </>);
  return (
    <Box className={dock ? `tq-aui-dock${dockExpanded ? " tq-aui-dock-expanded" : ""}` : undefined} onPaste={pasted} onDrop={dropped} onDragOver={dragging} data-tq-starting={quiet ? "" : undefined} sx={{ border: dock ? 0 : `1px solid ${BORDER}`, borderRadius: dock ? 0 : 1.75, overflow: "hidden", bgcolor: PANEL2,
      minHeight: 0, display: "flex", flexDirection: "column",
      ...(compact ? { height: quiet ? "auto" : "100%" } : { flex: quiet ? "0 0 auto" : "1 1 auto" }),
      ...(full && !dock ? FULL_SX : null) }}>
      {/* the strip wraps when its box is narrow - a phone, or a half-width Wall pane; scrolled sideways it hid its buttons entirely.
          On the canvas the task's own step heading holds it (toolsAt) and the answer gets the line - until Full screen, which
          leaves that heading behind */}
      {/* ...and none at all on a card whose session is not live (`noTools`, the owner 2026-10-25): a failed or closed agent's heading carried
          the agent picker, "provider default" and Full screen for a chat nothing is running in - the bar's Run another agent starts one */}
      {/* ...in a fragment: a portal straight under a Box failed its `children` check, a console error on every live agent (2026-10-26) */}
      {/* ...and none in a chat task's chat (the owner's ruling, 2026-11-05: "remove as much as possible ui components in the chat unless it's
          actions"): the agent picker, "provider default" and Full screen are settings, not a step of the task - the chat is the ask, the work, the reply */}
      {!dock && !noTools && !chat && toolsAt && !full && <>{createPortal(tools, toolsAt)}</>}
      {!dock && !noTools && !chat && !(toolsAt && !full) && <Box sx={{ minHeight: 39, px: 1.25, py: { xs: 0.5, md: 0 }, display: "flex", alignItems: "center", gap: 0.8, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL,
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
      {/* ...nor in the demo, whose turns were written in advance and whose box answers that it is the demo (server._demo_turn) */}
      {!chat && !data?.providers?.length && !noAiSaid && !data?.demo && <Alert severity="info" data-tq-no-ai="" sx={{ borderRadius: 0, py: 0, alignItems: "center" }}
        action={<ConnectAi variant="outlined" />}>No AI is connected, so this work cannot run yet - connect one under {placeName("ai")}.</Alert>}
      {/* ...never in a chat task (the owner, 2026-11-05: no banners): a conversation picked back up reads as the same conversation */}
      {session?.resume_notice && !(chat && !dock) && <Typography sx={{ px: 1.5, py: 0.5, fontSize: 12, color: FAINT }}>{session.resume_notice}</Typography>}
      {/* A SECOND AGENT'S CONVERSATION IS ITS OWN (Run another agent, general.new_run): the earlier agent's stays on the task, folded
          above it and read only - the thread below is the new one's, never the old one picked back up */}
      {!dock && !!data?.earlier?.length && <Box component="details" data-tq-earlier-run="" sx={{ px: 1.5, py: 0.4, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <Box component="summary" sx={{ cursor: "pointer", color: FAINT, fontSize: 12, fontWeight: 600, "&:hover": { color: INK } }}>
          The earlier agent's conversation · {plural(data.earlier.length, "message")}</Box>
        <Box sx={{ maxHeight: 260, overflow: "auto", py: 0.5, fontSize: 12.5, color: INK }}>
          {data.earlier.map((m) => <Box key={m.id} sx={{ py: 0.4 }}>
            {m.brief ? <BriefLine text={textOf(m)} /> : <>
              <Box component="span" sx={{ color: FAINT, fontWeight: 600, fontSize: 11 }}>{m.role === "user" ? "You" : name}</Box>
              <Md text={textOf(m)} /></>}</Box>)}
        </Box>
      </Box>}
      {uploading && <Box sx={{ px: 1, py: 0.5, color: FAINT, fontSize: 11 }}>Attaching…</Box>}
      {!dock && !chat && <ThreadReading reading={data?.thread} mails={mails} variant="chat" />}
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {/* ALWAYS inside the pane, session or not: a session that arrives mid-turn (`started`) must not
            change the tree around the thread, or the answer streaming into it is remounted away
            ...and no sid on a card whose session is not live (`noTools`): its browser was asked for every 3 s under a stopped, saved
            or failed agent's Result, for as long as it stayed open (the agents walk, 2026-10-26) */}
        <SessionPane sid={(!noTools && session?.sid) || null} height="100%" yourTurn={waitsOnPage(asking)} idle={!busy && !streaming}
          stack={!dock} taskId={dock ? null : task.TaskId} held={viewActs} turn={turn} onHandBack={handBack} onDecided={decidedOnView}
          onView={viewShownIs} quiet={chat && !dock} need={needNow}>{thread}</SessionPane>
      </Box>
    </Box>
  );
}

export default GeneralWorkspace;
