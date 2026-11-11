import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { coalesced, pollCalming } from "./visible.js";
import { createPortal } from "react-dom";
import { says, subState } from "./laneSays.js";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive, ThreadPrimitive, useAuiState, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, CircularProgress, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import CallMergeIcon from "@mui/icons-material/CallMerge";
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
import { heldLine, notShown, stillHeld, waitingShown } from "./heldLines.js";
import { keepUnsent, unsent } from "./unsent.js";
import { endTop, stickToEnd } from "./stickEnd.js";
import { howToOpen } from "./bugReportOpen.js";
import { streamAssistant } from "./assistantStream.js";
import { baseName, isWork } from "./agentSteps.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { PARTS, chatRows, chatSource, checkBackDue, compactingNow, continues, eventOf, eventsOf, hasParts, linkWords, partsMessage, rowMessages, turnOfStep, turnParts, workCount } from "./chatStream.js";
export { checkBackDue };
import { detailFor, useOwnDetail } from "./chatDetail.js";
import { useChatDefaults } from "./DetailSlider.jsx";
import { PermissionCards } from "./AgentChannels.jsx";
import { teammateLine } from "./agentChannels.js";
import { Hunk } from "./DiffView.jsx";
import { withImages } from "./promptImages.jsx";
import WriteIcon from "@mui/icons-material/EditNoteRounded";
import ViewSpec, { PlanRow } from "./ViewSpec.jsx";
import { wantsAsk, withoutAsk } from "./newTask.js";
import { FULL_SX, useFullScreen } from "./fullScreen.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, workOf, doingNow, turnStart, elapsedText, turnStamp, turnBegan, turnFrom } from "./agentWork.js";
import { AGENT_TURN, MESSAGE, instructionsHint } from "./kinds.js";
import { assignedAgent } from "./agentIdentity.js";
import { LinkPopups, LocalFiles, Md } from "./md.jsx";
import { draftState } from "./sendState.js";
import { failLine, press } from "./press.js";
import PublishedPages, { FileDialog } from "./PublishedPages.jsx";
import { Attachments } from "./Attachments.jsx";
import { placeShown } from "./shownPages.js";
import { forTurn, outputRefs, outputRow, shownOnce, turnFiles, uncited } from "./taskOutputs.js";
import TurnFiles from "./TurnFiles.jsx";
import ActionCard from "./ActionCard.jsx";
import CopyCorner from "./CopyCorner.jsx";
import { SessionPane, TerminalPane } from "./TerminalView.jsx";
import ThreadReading from "./ThreadReading.jsx";
import { heldOn, isTurn, needsOwner, waitsOnPage } from "./browserSplit.js";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, label as LABEL, mono } from "./theme.jsx";
import { level } from "./priority.js";
import "./generalWorkspace.css";
import "./agentStepRows.css";
import { ModelSelect, TaskuaryMark } from "./ui.jsx";
import { hint as btnHint, label as btn } from "./buttons.js";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { placeName } from "./words.js";
import { starting as startingLine } from "./laneSays.js";
import { bare, live, pendingTurn, sentNow, settled, turnOver } from "./pendingTurn.js";
import { plural } from "./timeWords.js";
import { openAppLink } from "./appLinks.js";
import ConnectAi from "./ConnectAi.jsx";
import { withoutAsked } from "./askOnce.js";
import ReviewDecision from "./ReviewDecision.jsx";
import { askNote, heldActsLine, proposalFrom, reviewText } from "./reviewProposal.js";
import BriefLine from "./BriefLine.jsx";
import AgentSummary, { OneBox } from "./AgentSummary.jsx";
import { PassedCtx } from "./passedCtx.js";
import { draftHome, draftPassed, turnAnswered, foldedSummaries, freshNext, hasReply, lastAnswerSummed, placeCards, turnOf, withTurns } from "./agentSummary.js";
import { asUtc, dayLabel, fmtTime12 } from "./dates.js";
import { readingOf } from "./threadReading.js";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import TelegramIcon from "@mui/icons-material/Telegram";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";

const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();
// the brief an agent was started on is Taskuary's, not the owner's (general.BRIEF_ACTOR): carried to UserMessage on the message's metadata
// ...and a turn's summary (general.shown_history) to AssistantMessage the same way - the runtime keeps metadata and drops anything else
const initial = (messages) => {
  const folded = foldedSummaries(messages);
  return (messages || []).map((m) => {
    const custom = { ...(m.brief ? { brief: true, mail: m.mail || [], ...(m.fold ? { fold: m.fold } : {}) } : {}), ...(m.summary ? { summary: m.summary, folded: folded.has(m.id), drafts: m.drafts_then || null } : {}),
      ...(m.since ? { since: m.since } : {}), ...(m.press ? { press: true, ...(m.result ? { result: m.result } : {}) } : {}),   // a press of the owner's (general.press_lines): their line, no turn
      ...(m.line ? { line: m.line } : {}),
      // ...and when a coding turn's last step came (chatStream.rowMessages `ended`): its time is its first step's, a general answer's its end
      ...(m.ended ? { ended: m.ended } : {}) };          // the name the page that sent it gave it (heldLines.lineOf)
    return { ...m, ...(Object.keys(custom).length ? { metadata: { custom } } : {}),
      // ...a stamp is the SERVER'S LOCAL time (dates.js, store.norm_stamp), read through asUtc with the zone setting - read as UTC, every
      // answer said 7:32 AM for 12:32 PM (the owner, 2026-11-05: "time is wrong. we have settings for time zone")
      createdAt: m.createdAt ? (String(m.createdAt).includes("Z") ? new Date(m.createdAt) : asUtc(m.createdAt)) : undefined };
  });
};

// ONE PART carries the turn's working: its parts (chatStream.turnParts - the one mapper a coding session's steps feed too), drawn in the order
// they happened - its words, a line per thing it did, each edit with its diff, its plan - above the answer. It was a row per raw tool call and
// then an "Agent progress" box saying the same commands again (the owner, 2026-10-21: "make the output on the general agent canvas more
// readable, not some greps and gets").
const stepsPart = (trace, opts) => partsMessage(turnParts(trace, opts));

// assistant-ui owns the response being streamed in the currently mounted pane. The task's
// session owns it when this pane is not mounted. Rehydrate that same tool/progress trace when a
// user switches back, and attach it to the filed answer once the run is complete.
export const messagesWithTrace = (messages, session, keepStart = true) => {
  const out = (messages || []).map((m) => ({ ...m, content: [...(m.content || [])] }));
  const trace = session?.trace;
  if (!turnParts(trace, { keepStart }).length) return out;
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
  // ...the newest TURN, above any press made since: a stopped turn's trail stood under "You stopped the agent" (the side-by-side walk, 2026-11-11)
  const at = out.findLastIndex((m) => !m.press), tail = out[at];
  if (tail?.role === "assistant") tail.content = [...stepsPart(trace, { keepStart, answer: textOf(tail) }), ...tail.content];
  else out.splice(at + 1, 0, { id: `trace-${session.sid}-${session.trace_revision || 0}`, role: "assistant", content: stepsPart(trace, { keepStart }) });
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
// ...NO WORDS, ONLY THE SPIN (the owner, 2026-11-10: "don't want the working... thing. we should never see that ever. it should show agent and
// time and how long it's running rightg away. under it it can spin like normal"): the turn's head says who, when and how long (RunClock); under
// it, while it has said nothing more, the dots the stream always had - starting or at work alike, never a line of words of their own
const AgentBand = ({ name, provider, work, starting = "" }) => {
  const doing = doingNow(work);
  return <div className="tq-aui-thinking" role="status" aria-label={`${provider || name || "The agent"} is at work`} title={doing || undefined}
    data-tq-working="" {...(starting && !work.steps.length ? { "data-tq-starting-line": "" } : {})}><i /><i /><i /></div>;
};
// THE TURN'S HEAD, FROM THE PRESS: its time and how long it has run, counting - the same element before the agent's first word and after it
// ...and the ONE way to stop an agent mid-run, on the turn it stops (the owner, 2026-11-10: "we should have x button for agent to stop in middle
// of the work"): the chat's own stop road (onStop), nothing else
const StopCtx = React.createContext(null);
const RunClock = ({ start }) => {
  const [now, setNow] = useState(() => Date.now()), stop = React.useContext(StopCtx);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  return <span data-tq-ran="" data-tq-run-clock="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>
    · {when(new Date(start))} · ran {elapsedText(Math.max(0, now - start))}
    {stop && <IconButton size="small" data-tq-stop-run="" aria-label="Stop the agent" title="Stops this turn - the chat stays, and what you type next carries on"
      onClick={stop} sx={{ ml: 0.5, p: 0.25, verticalAlign: "-3px" }}><CloseIcon sx={{ fontSize: 13 }} /></IconButton>}</span>;
};

// ...and WHILE THE CLI COMPACTS ITS CONTEXT, that line says so (chatStream.compactingNow; the owner, 2026-11-10: "while it's going on show
// compacting like claude code does"), its clock the turn's
const CompactingBand = ({ since }) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  return <div className="tq-aui-working" role="status" aria-live="polite" data-tq-working="compacting">
    <span className="tq-aui-band-dot" /><span>Compacting…</span>{!!since && <em>{elapsedText(now - since)}</em>}</div>;
};

// The speaker of the agent's turns. In the dock this IS Taskuary's assistant; on a work window it
// is the agent named on the task, and calling it "Taskuary" there was the fourth place one window
// wore the concierge's name.
const AgentNameCtx = React.createContext("Taskuary");

// A FILE THE ANSWER NAMES IS A FILE YOU CAN OPEN (taskOutputs.js): Codex's citation marker, a link or a path into this task's
// outputs folder comes out of the words and sits under them with Preview and Download. A Codex answer printed the raw marker, and
// asked to send the workbook it wrote a link to an /outputs/ address the server never had - a 404 (outputs.py).
const OutputsCtx = React.createContext(null);
// ...each turn's own: the version of a file IT made, where a later turn changed it (taskOutputs.forTurn, the owner 2026-11-07)
const useTurnOutputs = (id) => { const at = React.useContext(OutputsCtx); return at && { ...at, listed: forTurn(at.listed, at.versions, id) }; };
// ...and a file NAMED in the words - `Report.csv` - opens over the chat at a press (FileDialog): the names are marked once drawn
const nameOf = (s) => String(s || "").trim().replace(/^.*[\\/]/, "");
export const isOutputsFolder = (s, tid) => new RegExp(`outputs[\\\\/]TQ-0*${Number(tid)}[\\\\/]?$`, "i").test(String(s || "").trim());
const AssistantText = ({ text }) => <SaidText text={text} mid={useAuiState((s) => s.message.id)} />;
const SaidText = ({ text, mid }) => {
  const at = useTurnOutputs(mid), shown = React.useContext(ShownCtx)[mid];
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
  // an answer that was only its summary block is filed as the summary's "did" (general._file): the words are the turn, so they are drawn
  // here and the summary's prose stays out (AgentSummary `answered`) - hiding them here too left the turn empty (2026-11-08 render)
  const { text: said, files } = at ? outputRefs(text, at.tid, at.listed) : { text, files: [] }, { isShown } = shownOnce(files, shown);
  const chat = React.useContext(ChatCtx);
  return <>
    {!!said && <div ref={box} onClick={open} data-tq-said=""><LinkPopups><Md text={said} /></LinkPopups></div>}
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
    <div className="tq-aui-mail-bubble">{mailWords(x)}<CameWith x={x} /></div>
  </div>));
// ...AND WHAT CAME WITH IT (the owner, 2026-11-08: a screenshot and a voice note came in on WhatsApp, and the chat showed only the words): the
// message's own files under its words, by the panel's one Attachments - a picture drawn small (a click opens it whole), a voice note a player
// over its transcript (the words), any other file a chip that opens. Every channel's bubble alike (general.mail_row `mid`, `files`)
const CameWith = ({ x }) => x.files > 0 && x.mid ? <div className="tq-aui-arrived-files" data-tq-chat-files={x.files}><Attachments messageId={x.mid} dense /></div> : null;
// ...a picture with no words came in as "(no text - see the attachment)": with the picture drawn under it, the words say nothing
const mailWords = (x) => x.files > 0 && /^\(no text - see the attachments?\)$/.test(String(x.words || "").trim()) ? "" : x.words;
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
// reply sent outside Taskuary is no prompt: it stands on the left among the lines it answers (Arrived, 2026-11-08)
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
// ...THE OWNER'S OWN REPLY, sent from their phone between the other side's lines, stands among them in time order (the owner, 2026-11-08: "it
// should be left side thing but written as you responded"): on the LEFT, "You · on WhatsApp · 5:20 PM" - their answer on the thread, never a
// prompt to the agent (channels.ingest_own_message wakes no turn; the next one hears it)
const ON_WORD = { email: "by email", whatsapp: "on WhatsApp", teams: "on Teams", slack: "on Slack", telegram: "on Telegram", sms: "by text" };
const headOf = (x) => x.own ? ["You", ON_WORD[String(x.channel || "").toLowerCase()] || "outside Taskuary"]
  : [`${CHANNEL_WORD[String(x.channel || "").toLowerCase()] || "Message"} from ${x.who || "someone"}`];
// the subject when it says something the words do not: not over a chat line (none), not the same as the line before's, not the words themselves
export const subjectOf = (x, prev) => { const sub = String(x?.subject || "").trim(), bare = (v) => String(v || "").replace(/^\s*((re|fw|fwd)\s*:\s*)+/i, "").trim().toLowerCase();
  return !sub || x.own || bare(sub) === bare(prev?.subject) || bare(sub) === bare(x.words) ? "" : sub; };
const Arrived = ({ mail, prev = null }) => mail.map((x, i0, list) => {
  const all = prev ? [prev, ...list] : list, i = i0 + (prev ? 1 : 0);
  const more = sameAs(all[i - 1], x), stamp = x.at ? when(x.at) : "", again = more && stamp === (all[i - 1].at ? when(all[i - 1].at) : "");
  return <div key={i0} className={`tq-aui-arrived${more ? " tq-aui-arrived-more" : ""}${x.own ? " tq-aui-arrived-own" : ""}`} data-tq-chat-arrived={x.own ? "own" : ""}>
    {!again && <span className="tq-aui-arrived-head">{more ? stamp : <><ChannelMark channel={x.channel} />
      {[...headOf(x), stamp].filter(Boolean).join(" · ")}</>}</span>}
    {/* ...a mail's subject over its words, once a run (the owner, 2026-11-09: "you can't see anything about the email") - the words are the
        sender's NEW ones, the stamp and the quoted chain left out on the server (general.mail_row) */}
    {!!subjectOf(x, all[i - 1]) && <span className="tq-aui-arrived-subject" dir="auto">{x.subject}</span>}
    {!!mailWords(x) && <span className="tq-aui-arrived-words" dir="auto" title={x.words}>{mailWords(x)}</span>}
    <CameWith x={x} />
  </div>;
});
// a press's event line: its words without the closing stop, then the time - "You changed its workstream · 3:12 PM"
export const pressLine = (words, stamp) => [String(words || "").trim().replace(/\.$/, ""), stamp].filter(Boolean).join(" · ");
// what a check-back come due asked to verify, from Taskuary's own line (checkback.TURN) - '' for any other brief
const UserMessage = () => {
  const brief = useAuiState((s) => !!s.message.metadata?.custom?.brief), mail = useAuiState((s) => s.message.metadata?.custom?.mail), chat = React.useContext(ChatCtx);
  const fold = useAuiState((s) => s.message.metadata?.custom?.fold || "");
  const at = useAuiState((s) => s.message.createdAt), line = useAuiState((s) => s.message.id);
  // ...a brief with no mail but a SHORT line of its own is Taskuary's trigger ("Signed in to the site") - an event line (eventOf); a long one is
  // Taskuary's instructions to the agent, never drawn - nor one carrying only the owner's own reply (the scenario run, 2026-11-06)
  const words = useAuiState((s) => textOf(s.message));
  const prev = useAuiState((s) => { const ms = s.thread.messages, i = ms.findIndex((m) => m.id === s.message.id), p = ms[i - 1];
    return p?.role === "user" && !p.metadata?.custom?.brief && !p.metadata?.custom?.press ? (p.createdAt ? when(new Date(p.createdAt)) : "") : null; });
  // A PRESS IS AN EVENT, NOT A LINE TYPED (the owner, 2026-11-09: "You changed its workstream." stood in a bubble under "You" as if typed):
  // a quiet line like the close's own (tq-aui-closed) - the agent still hears it with the owner's next line (general.owner_did)
  const press = useAuiState((s) => !!s.message.metadata?.custom?.press), result = useAuiState((s) => s.message.metadata?.custom?.result);
  const stampOf = at ? when(new Date(at)) : "";
  // ...an APPROVED STEP'S LINE IS ITS RESULT (the owner, 2026-11-09: "once i approve it should say sent"): its link, the command folded under it
  if (press) return <MessagePrimitive.Root className="tq-aui-message tq-aui-press" data-tq-chat-press="">
    <div className="tq-aui-press-line">{pressLine(words, stampOf)}
      {result?.url && <> · <a href={result.url} target="_blank" rel="noreferrer" data-tq-press-link="">{linkWords(result.url)}</a></>}
      {result?.command && <details className="tq-aui-press-cmd"><summary>Show the command</summary><code>{result.command}</code></details>}</div>
  </MessagePrimitive.Root>;
  // ...a FOLD is an INPUT (the owner, 2026-11-09: "merging in a task is a new input of course"): "Folded in TQ-12: <title>" on the right, the
  // mail it brought under it - another task's work arriving on this one, like a message on its thread
  if (brief && chat && fold) return <MessagePrimitive.Root className="tq-aui-message tq-aui-brief"><div className="tq-aui-arrived" data-tq-chat-trigger="fold">
    <span className="tq-aui-arrived-head"><CallMergeIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />{[fold, at && when(new Date(at))].filter(Boolean).join(" · ")}</span></div>
    {!!mail?.length && <Arrived mail={mail} />}</MessagePrimitive.Root>;
  // ...and what TASKUARY says woke the agent - a sign-in, a check-back come due - is an event, never an input: an input is what the owner typed,
  // what came in on the task's thread, or a task folded in (the owner, 2026-11-09)
  const event = brief && chat ? eventOf(words, fold, mail) : "";
  if (event) return <MessagePrimitive.Root className="tq-aui-message tq-aui-press" data-tq-chat-press="" data-tq-chat-trigger={checkBackDue(words) ? "check-back" : ""}>
    <div className="tq-aui-press-line">{pressLine(event, stampOf)}</div>{!!mail?.length && <Arrived mail={mail} />}</MessagePrimitive.Root>;
  if (brief && chat) return mail?.length ? <><MessagePrimitive.Root className="tq-aui-message tq-aui-brief"><Arrived mail={mail} /></MessagePrimitive.Root><RowCards id={line} /></> : null;
  // ...and what the owner types is theirs on the right, under their mark and the time ("if user interjects it will show user logo")
  // ...three lines typed in a row read as one, as a sender's burst does (Arrived): the head once, then a new minute's time alone, a same minute nothing
  const stamp = at ? when(new Date(at)) : "";
  // ...a teammate's line from a bound chat (agentchannels.py) is theirs, named and marked, never "You"
  const mate = chat ? teammateLine(words) : null;
  if (mate) return <MessagePrimitive.Root className="tq-aui-message tq-aui-user" data-tq-teammate={mate.who}>
    <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />{mate.who} (teammate) · {mate.via}{stamp ? ` · ${stamp}` : ""}</div>
    <div className="tq-aui-user-bubble" dir="auto">{mate.text}</div></MessagePrimitive.Root>;
  if (chat) return (<>
    <MessagePrimitive.Root className={`tq-aui-message tq-aui-user${prev !== null ? " tq-aui-user-more" : ""}`} data-tq-chat-line={line}>
      {prev === null ? <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />You{stamp ? ` · ${stamp}` : ""}</div>
        : stamp && stamp !== prev ? <div className="tq-aui-user-head">{stamp}</div> : null}
      <div className="tq-aui-user-bubble" dir="auto"><MessagePrimitive.Parts /></div>
    </MessagePrimitive.Root><RowCards id={line} /></>);
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
// THE BRANCH'S LANDING IS A CARD OF THE TURN THAT MADE IT (the owner, 2026-11-08): pinned at the chat's foot it stood under everything, whichever
// turn did the work - {after: the turn's message id, node} (turnOf, as landing.js landingTurn reads it)
const LandingCtx = React.createContext(null);
// ...AND SO IS EVERY PRESSED CARD (the owner, 2026-11-09: "leave the card in the turn with the pressed button"): a held steps' card approved, a
// reply sent - each in the turn that set it up, whatever came after: [{key, after, node}] (TaskPage turnCards, placed by turnOf)
const TurnCardsCtx = React.createContext([]);
// ...AND SO IS EVERY CARD THAT STILL WAITS (the spine audit, 2026-11-09): a held step, a browser act, a drafted playbook - each in the turn that
// raised it, under one "Waiting on you". They rode one block under whichever turn was newest, and an act or a playbook stood a second time at
// the chat's foot with a second Approve. `also`: something else waits over them in the same place. Marked as waiting for the agent room's
// rest, which keeps a chat that holds one on screen (data-tq-waits, TaskPage's :has)
const TurnAsks = ({ cards, also = false, sx = null }) => !cards.length ? null : (
  <Box data-tq-turn-asks="" data-tq-waits="" sx={{ mt: 1.25, ...sx }}>
    <Typography sx={{ ...LABEL, display: "block", mb: 0.5 }}>{`${also ? "Also waiting on you" : "Waiting on you"}${cards.length > 1 ? ` · ${cards.length}` : ""}`}</Typography>
    {cards.map((c) => <React.Fragment key={c.key}>
      {!!c.note && <Typography variant="caption" sx={{ display: "block", color: DIM, mt: 1, mb: 0.5 }}>{c.note}</Typography>}{c.node}</React.Fragment>)}
  </Box>);
// what a turn's Next steps count against (agentSummary.nextSteps): the task's reviews and checklist. Null in the dock, which has no turns
// of an agent's to sum up and draws its steps as ever
// THE OWNER'S LINES NOT IN THE THREAD YET, read from the SAME snapshot of the thread the messages are drawn from (heldLines): read from a copy the
// page kept of it, a line the agent took was let go a commit before the thread drew it, and in a coding chat it vanished for a frame (the
// recorded walk, 2026-11-10)
// ...and the turn they asked for knows from that same snapshot whether it stands under them at the foot or under the thread (PendingTurn `feed`)
const useFoot = ({ waiting, held, messages }) => {
  const thread = useAuiState((s) => s.thread.messages), mine = (thread || []).filter((m) => m.role === "user");
  // ...the server's copy of a line stands in for the page's own wherever the page no longer draws its own: a coding line is known by its words and
  // by counting, and another of his lines arriving first took it away while the server still said it waited (the recorded walk, 2026-11-10)
  const shown = notShown(held, mine);
  return [...waitingShown(waiting, shown, mine, messages).map((w) => ({ id: `waiting-${w.id}`, text: w.text, at: w.at })), ...shown];
};
// ...what stands only while one of his lines waits at the foot, or only while none does (read inside the runtime, as useFoot must be)
const WhileLines = ({ feed, waits, children }) => ((useFoot(feed).length > 0) === waits ? children : null);
const FootLines = ({ waiting, held, messages, hint }) => {
  const lines = useFoot({ waiting, held, messages });
  return lines.map((l) =>
    <div key={l.id} className="tq-aui-message tq-aui-user" data-tq-held="">
    {/* ...under the owner's own head, as every line of theirs is - "you" in grey read as somebody else's (the product audit, 2026-11-08) */}
    <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />You{l.at ? ` · ${when(l.at)}` : ""}</div>
    <div className="tq-aui-user-bubble" dir="auto">{l.text}</div>
    {l.err ? <div className="tq-aui-hint" role="alert">{l.err}</div> : hint && <div className="tq-aui-hint" data-tq-waiting="">Waiting for the agent</div>}</div>);
};
const WorkCtx = React.createContext(null);
// ...when the owner last pressed a line on this page (ms): a line held while a turn works is in no thread yet, and the draft it passes greys at once
const PressedCtx = React.createContext(0);
// THE WAITING DRAFT'S PLACE AND STATE (agentSummary.draftHome, draftPassed; the owner, 2026-11-10: "The second you write ptompt on email action it
// should go gray and then it should generate new email action box under it with new email.."): it stands where it was written - the turn that
// wrote it, else the row it came after - and once he has prompted past it, it is greyed there, never carried down under his line
const useDraft = () => {
  const work = React.useContext(WorkCtx), pressed = React.useContext(PressedCtx);
  const home = useAuiState((s) => (work ? draftHome(work.reviews, s.thread.messages) : null));
  const passed = useAuiState((s) => (work ? draftPassed(work.reviews, s.thread.messages, pressed) : false));
  return { work, home, next: work?.next ? (passed ? <PassedCtx.Provider value>{work.next}</PassedCtx.Provider> : work.next) : null };
};
// ...under a row that is not an answer - the mail come in, a line of his: the draft that stands there, and the cards placed there by time
const RowCards = ({ id }) => {
  const { work, home, next } = useDraft(), chat = React.useContext(ChatCtx), cards = React.useContext(TurnCardsCtx).filter((c) => c.after === id);
  // ...a replaced draft's record under the same head the draft had (ReplacedDraft): replaced, nothing on the page moves
  const here = chat && home === id && next, records = cards.filter((c) => c.record), rest = cards.filter((c) => !c.record);
  // ...and a page shown by a turn that never answered (stopped, failed): under the line that began it, the server's `after`
  const shown = React.useContext(ShownCtx)[id] || [];
  if (!here && !cards.length && !shown.length) return null;
  const head = (words) => <Typography component="span" sx={{ display: "block", color: "var(--tq-text, #292824)", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>{words}</Typography>;
  return <div className="tq-aui-message tq-aui-agent" data-tq-row-cards={id}><div className="tq-aui-agent-body">
    {(here || !!records.length) && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
      {head(here && !hasReply(work.reviews) ? "Next steps" : "Suggested reply")}
      {records.map((c) => <React.Fragment key={c.key}>{c.node}</React.Fragment>)}{here && next}</Box>}
    {rest.map((c) => <React.Fragment key={c.key}>{c.node}</React.Fragment>)}{!!shown.length && <PublishedPages pages={shown} open />}</div></div>;
};
// a turn still running is ONE LINE, "Working on this…", its steps folded under it (the closeout-in-chat spec, 2026-11-04); a turn that
// ended in its summary keeps them folded above it. A turn with no summary - older ones, a CLI that wrote none, one that died - as ever
// (pendingTurn.live)
// ...and a fold the owner opened stays open: the server's live message is `live-<sid>-<trace revision>` - a new id at every step - and the pane
// itself mounts again when the owner comes back to the task. Kept by the turn, never by the message's id or the DOM
const OPEN_FOLDS = new Set();
const LIVE_SHOWN = 6;
const foldKey = (id) => String(id || "").replace(/^(live-.+)-\d+$/, "$1");
// HOW MUCH OF THE WORK IS DRAWN (chatDetail.js): "summary", "steps" or "everything" - the task's own, else its kind's default from Settings
const LevelCtx = React.createContext("steps");
// AN EDIT IS A ROW THAT OPENS ON ITS DIFF: "Edited budget.py (+12 −3)", the code with its line numbers under it
const EditRow = ({ p }) => (
  <details className="tq-aui-step tq-aui-step-edit tq-cc-edit" data-tq-edit={baseName(p.file)}>
    <summary><WriteIcon aria-hidden className="tq-aui-step-icon" /><span>{p.summary}</span></summary>
    <div className="tq-cc-diff">{p.hunks.length ? p.hunks.map((h, i) => <Hunk key={i} h={h} path={p.file} />)
      : <div className="tq-dv-empty">Its log keeps no diff for this one.</div>}</div>
  </details>);
// ...a fold the owner opened stays open across the live turn's new ids (OPEN_FOLDS)
const Fold = ({ k, label, quiet = false, children }) => {
  const [open, setOpen] = useState(() => OPEN_FOLDS.has(k));
  useEffect(() => { setOpen(OPEN_FOLDS.has(k)); }, [k]);
  const toggle = (e) => { const o = e.currentTarget.open; if (o) OPEN_FOLDS.add(k); else OPEN_FOLDS.delete(k); setOpen(o); };
  return <details className="tq-aui-working-fold" data-tq-steps-fold={quiet ? "summary" : ""} open={open} onToggle={toggle}><summary>{label}</summary>{children}</details>;
};
// WHILE IT RUNS ITS STEPS ARE OPEN (the owner, 2026-11-05: "it has to show what it's working on a little more than this like pulling from url's
// etc.. look how other chat libraries show intermediately the tool calls"): a quiet line a step, the newest at the foot with its spinner, the
// last LIVE_SHOWN of them - those before fold into "N earlier steps"
const LiveSteps = ({ steps }) => { const cut = Math.max(0, steps.length - LIVE_SHOWN);
  return <div className="tq-aui-live-steps" data-tq-live-steps="" role="status" aria-live="polite">
    {!!cut && <details className="tq-aui-live-earlier"><summary>{plural(cut, "earlier step")}</summary><AgentSteps data={{ steps: steps.slice(0, cut) }} /></details>}
    <AgentSteps data={{ steps: steps.slice(cut) }} /></div>; };
// ONE RULE FOR EVERY FOLD OF A TURN'S WORK: it is drawn round steps of work. One with none in it - only Taskuary's own notes, as a turn the app
// started holds before its first step - read "Along the way ▸" over nothing he could see (the overnight walk, 2026-11-11): its notes stand open
const WorkFold = ({ k, quiet = false, parts, draw }) => { const n = workCount(parts);
  return n ? <Fold k={k} quiet={quiet} label={plural(n, "step")}>{parts.map((p, i) => draw(p, i, "everything"))}</Fold>
    : <>{parts.filter((p) => p.type !== "said").map((p, i) => draw(p, i, "everything"))}</>; };
const TurnWork = ({ data }) => <TurnWorkView data={data} now={useAuiState((s) => live(s.message))} ended={useAuiState((s) => !!s.message.metadata?.custom?.summary)}
  k={useAuiState((s) => s.message.id)} />;
const TurnWorkView = ({ data, now, ended, k }) => {
  const at = React.useContext(WorkCtx);
  const key = foldKey(k), level = React.useContext(LevelCtx), chat = React.useContext(ChatCtx);
  // ...AND A TURN THAT ENDED HAS NOTHING STILL AT WORK (the owner, 2026-11-05: a step kept its spinner under the answer): a call that never got
  // its result before the answer was filed is drawn done, never circling. IN A CHAT A STEP IS NEVER "FAILED" (the owner, 2026-11-05: "it's just a
  // internal thought failure, for the user the task is getting done. failure means nothing") - a TURN that failed says so in its own words
  const calm = (st) => (!now && st.status === "running" ? { ...st, status: "done", alongside: false }
    : chat && (st.status === "error" || st.status === "recovered") ? { ...st, status: "done" } : st);
  const parts = (data?.parts || (data?.steps ? [{ type: "work", id: "p0", steps: data.steps }] : []))
    .map((p) => (p.type === "work" ? { ...p, steps: p.steps.map(calm) } : p));
  // ...where nothing sums a turn up (the dock), its trail as ever: one line a step, its edits among them
  if (!at) return <AgentSteps data={{ steps: parts.flatMap((p) => (p.type === "work" ? p.steps : p.type === "said" ? [{ id: p.id, kind: "said", summary: p.text }]
    : p.type === "edit" ? [{ id: p.id, kind: "edit", summary: p.summary, status: "done" }] : [])) }} />;
  const last = parts.length - 1;
  const draw = (p, i, lvl) => p.type === "said" ? <Md key={p.id} text={p.text} /> : p.type === "edit" ? <EditRow key={p.id} p={p} />
    : p.type === "plan" ? <PlanRow key={p.id} p={p} />
    : p.type === "view" ? <ViewSpec key={p.id} spec={p.spec} raw={p.raw} />
    // ...a file the agent showed (show `files`) is drawn by its kept copy, placed in its turn by the server for both chats (ShownCtx), never twice
    : p.type === "files" ? null
    : lvl === "everything" ? <AgentSteps key={p.id} data={{ steps: p.steps }} />
    // IN THE ORDER IT HAPPENED (the owner, 2026-11-06: "never write above what was written already"): a group with a call still running stays
    // open with its spinner, and what the agent says after it draws below it
    : now && (i === last || p.steps.some((x) => x.status === "running")) ? <LiveSteps key={p.id} steps={p.steps} />
    : <WorkFold key={p.id} k={`${key}:${p.id}`} parts={[p]} draw={draw} />;
  // SUMMARY: the agent's words, in order; every step, edit and plan behind one quiet "n steps" line over them that opens on them all. A turn its
  // summary sums up folds whole - its summary says the words
  if (level === "summary") {
    // ...and a view the agent showed is what it chose to put in front of the owner: never folded away
    const out = (p) => p.type === "view" || p.type === "files" || (!ended && p.type === "said"), said = parts.filter(out), rest = parts.filter((p) => !out(p));
    return <>{rest.some((p) => p.type !== "said") && <WorkFold k={`${key}:all`} quiet parts={rest} draw={draw} />}
      {said.map((p, i) => draw(p, i, "everything"))}</>;
  }
  return <>{parts.map((p, i) => draw(p, i, level))}</>;
};
// ...and with none of its steps on screen yet, the line stands alone (AgentBand)
// ...its clock from the turn's own start: the server's `turn_started` when it has said it (`since`), and never before the newest input in the chat - the line just
// typed is in the thread before the server's history has it, and the clock read the owner's line before that one, "249m 53s" over a turn
// three seconds old (the scenario run, 2026-11-06)
const AtWork = ({ since, began, compacting = false, ...props }) => {
  const folded = useAuiState((s) => { const m = s.thread.messages.at(-1);
    return m?.role === "assistant" && live(m) && (m.content || []).some((p) => p.type === "data" && (p.name === PARTS || p.name === "agent_steps")); });
  // ...at Summary the live turn's steps are folded away: its "Working on this…" line stays
  const level = React.useContext(LevelCtx);
  const typed = useAuiState((s) => turnBegan(s.thread.messages.filter((m) => m.role === "user").map((m) => m.createdAt)));
  // ...the server's own start wins when it has said it: a mail that joined mid-turn is newer than the turn and set its clock back to 0s
  // ...a compaction under way says so whatever is drawn above it: the live steps' last line is the step before it, done
  if (compacting) return <CompactingBand since={began || Math.max(since || 0, typed || 0) || null} />;
  return folded && level !== "summary" ? null : <AgentBand {...props} since={began || Math.max(since || 0, typed || 0) || null} />;
};
// THE AGENT'S TURN BEFORE THE THREAD HAS IT (pendingTurn.js, the owner 2026-11-09): its head - "Agent · 2:05 PM" - and its line, drawn from the
// press; a turn the thread draws takes the same spot at the same render (both read the thread's state). Where the thread already draws the live
// turn, only the line under it, as ever
// ...`foot`: the turn answers a line held at the chat's foot (an answer sent on the server's road), so its row stands under that line
const PendingTurn = ({ busy, sent, at, began = null, foot = false, feed, held = false, children }) => {
  const atFoot = useFoot(feed).length > 0;
  const thread = useAuiState((s) => s.thread.messages);
  const due = pendingTurn(thread, { busy, sent, began, held });
  // ...its clock from the EARLIEST start it has been told while it stands, never a later one (the owner, 2026-11-10: from the press, never
  // restarting): a coding turn's server start moved from the press to the adapter's turn as it came up, and "ran 9s" read "ran 2s"
  const first = React.useRef(null), told = +new Date(sent?.at || at || NaN);
  if (!due) first.current = null;
  else first.current = Math.min(first.current ?? Date.now(), Number.isFinite(told) ? told : Infinity);
  if (!due) return busy && !foot && !turnOver(thread, { sent, began }) ? children : null;   // ...nor its spin, the turn over
  if (foot !== atFoot) return null;
  return <TurnHead start={first.current}>{children}</TurnHead>;
};
// THE HEAD OF A TURN NOT IN THE THREAD: the agent's name and its running clock over its working - a turn a press asked for (PendingTurn), and the
// turn at work under a line typed while it works (the side-by-side walk, 2026-11-11: a general chat drew only its dots there, a coding chat this head)
const TurnHead = ({ start, children }) => <div className="tq-aui-message tq-aui-agent" data-tq-pending-turn="">
  <div className="tq-aui-role">{React.useContext(AgentNameCtx)}<RunClock start={start} /></div>
  <div className="tq-aui-agent-body">{children}</div></div>;
// ...the turn at work's own: counted from where that turn began (RanFor's start for it), never from a later press
const AtWorkHead = ({ or, children }) => {
  const start = useAuiState((s) => { const ms = s.thread.messages, i = ms.findLastIndex((m) => m.role === "assistant" && live(m));
    return i < 0 ? null : turnFrom(ms[i].metadata?.custom?.since, turnBegan(ms.slice(0, i).map((m) => m.createdAt))); });
  return <TurnHead start={start ?? or}>{children}</TurnHead>;
};
// ...and the turn this pane streams, while it has drawn nothing (pendingTurn.bare): the same head, as a coding chat's turn before its first step
const BareHead = ({ or, children }) => (useAuiState((s) => bare(s.thread.messages.at(-1))) ? <AtWorkHead or={or}>{children}</AtWorkHead> : children);
// WHEN EACH TURN ANSWERED AND HOW LONG IT RAN (the owner, 2026-11-05: "we need a time and how long each taskuary thing ran and timestamp"): over
// each answer in a chat task, its time and the time from what it answered (the message before it) to the answer
// ...and WHILE IT RUNS, ONE CLOCK (the owner, 2026-11-06): "Working on this… 3s" under it - the head's own "working 0:03" was a second one
const RanFor = () => {
  const at = useAuiState((s) => s.message.createdAt), id = useAuiState((s) => s.message.id);
  const before = useAuiState((s) => { const ms = s.thread.messages, i = ms.findIndex((m) => m.id === id); return i > 0 ? turnBegan(ms.slice(0, i).map((m) => m.createdAt)) : null; });
  // ...a turn still running has not "ran" anything yet: its stamp read "ran 0s" over "Working on this…" (the chat-model stress run, 2026-11-05)
  // ...and the live message is drawn anew at every step, so its own time is the latest step's: the turn began at the server's `since`, else
  // at the line it answers
  const isLive = useAuiState((s) => live(s.message)), since = useAuiState((s) => s.message.metadata?.custom?.since), ended = useAuiState((s) => s.message.metadata?.custom?.ended);
  // ...and ONCE HE HAS TYPED AFTER IT, it is not his screen's running turn (the 0.3.11.40 release run: a turn finishing its stream as he pressed
  // drew its clock and x over the line he had just typed) - the turn his line asks for runs under it (PendingTurn, atWork below FootLines)
  const pressed = React.useContext(PressedCtx), began = isLive ? turnFrom(since, before) : null, running = isLive && !(pressed > (began ?? Infinity));
  const start = running ? began : before, t = running && start ? new Date(start) : ended ? asUtc(ended) : at ? new Date(at) : null;
  if (!t || Number.isNaN(+t)) return null;
  if (running) return <RunClock start={+t} />;
  // ...and one his line passed while it still works has not ended: no "ran", which read "ran 0s" over a turn at work (the side-by-side walk)
  const ran = isLive ? "" : turnStamp({ start: before, end: t });
  return <span data-tq-ran="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>
    · {when(t)}{ran ? ` · ${ran}` : ""}</span>;
};
const AssistantMessage = () => {
  const id = useAuiState((s) => s.message.id), shown = React.useContext(ShownCtx)[id], at = useTurnOutputs(id), work = React.useContext(WorkCtx);
  const landing = React.useContext(LandingCtx), mine = React.useContext(TurnCardsCtx).filter((c) => c.after === id), pressed = mine.filter((c) => !c.waits);
  const words = useAuiState((s) => textOf(s.message)), custom = useAuiState((s) => s.message.metadata?.custom), chat = React.useContext(ChatCtx);
  // the turn is the chat's last entry AND has answered: it carries its card - a turn still at work never takes the one before it's draft (the owner,
  // 2026-11-05: "email draft is being shown below the new prompt ... it's connected to the prior agent taskuary thing")
  const newest = useAuiState((s) => s.thread.messages.at(-1)?.id === s.message.id && !live(s.message));
  // the newest turn that ANSWERED (a summary, not at work): its draft stays on it when something newer comes
  const lastAnswered = useAuiState((s) => [...s.thread.messages].reverse().find((m) => m.role === "assistant" && !live(m) && m.metadata?.custom?.summary)?.id === s.message.id);
  // ...the draft card sits where it was written (useDraft), never on whichever turn is newest; no draft waiting: the newest holds the cards
  const { home, next } = useDraft(), holds = home ? home === id : newest;
  // WHAT THIS TURN MADE AND SET UP, IN IT (the owner, 2026-11-05): in a chat, the files it made inline, and an act it proposed drawn as its
  // connector declares it (a post as the post, ActionCard) under its Next steps - live while it waits (a line typed after it left it "not sent", unsendable), read-only once answered
  const posts = work && chat ? (work.cards || []).filter((p) => p.after === id) : [];
  const made = at && chat ? turnFiles({ listed: at.listed, id, words, did: custom?.summary?.did, tid: at.tid,
    skip: (work?.cards || []).map((p) => p.post?.image).filter(Boolean) }) : [];
  const madeNames = new Set(made.map((f) => f.name));
  const lead = posts.length ? posts.map((p) => <ActionCard key={p.ReviewId} row={p} tid={at?.tid} onChanged={work.refresh} />) : null;
  const files = made.length ? <TurnFiles files={made} /> : null;
  const { rest: shownRest } = shownOnce(at ? outputRefs(words, at.tid, at.listed).files : [], shown);
  // ...nor a picture its post card already carries (the owner saw the chart twice: shown by the turn, and on the post)
  const postPics = new Set(posts.map((p) => String(p.post?.image || "").split(/[\\/]/).pop()).filter(Boolean));
  const rest = chat ? shownRest.filter((p) => !madeNames.has(p.name) && !postPics.has(String(p.name || "").split(/[\\/]/).pop())) : shownRest;
  const running = useAuiState((s) => live(s.message));
  // ...A TURN AFTER A PRESS IS THE SAME TURN GOING ON (the owner, 2026-11-09: "a button click is not a new prompt"): no head of its own
  const agentName = React.useContext(AgentNameCtx);
  const more = useAuiState((s) => chat && continues(s.thread.messages, s.thread.messages.findIndex((m) => m.id === s.message.id)));
  // ...and it copies at its corner (the owner, 2026-11-05): what the turn says - its words, else its summary's parts
  // ...and ONE OF THE TWO, never both (the owner, 2026-11-08: "never show anything twice in a turn"): the agent's own words are the turn, and its
  // summary's prose is drawn only for a turn with none (a work-only run) - what it set up as cards stays under the words either way
  const answered = turnAnswered(words);
  const said = custom?.summary && !answered
    ? [custom.summary.about, custom.summary.did].map((x) => String(x || "").trim()).filter(Boolean).join("\n\n") : words;
  // ...a turn that has drawn nothing yet is no row of its own: its head stands under his newest line (BareHead), never an empty one over it
  const empty = useAuiState((s) => chat && bare(s.message));
  if (empty) return null;
  return (
    <MessagePrimitive.Root className={`tq-aui-message tq-aui-agent${chat && said ? " tq-copy-host" : ""}${more ? " tq-aui-agent-more" : ""}`} data-tq-chat-line={id}
      data-tq-turn-goes-on={more ? "" : undefined}>
      {chat && !!said && !running && <CopyCorner text={said} label="Copy this answer" />}
      {!more && <div className="tq-aui-role">{agentName}{chat && <RanFor />}</div>}
      <div className="tq-aui-agent-body">
        {/* THE AGENT'S WORDS ARE THE TURN (the owner, 2026-11-08: "never show anything twice in a turn"): drawn whenever it said any, and its
            summary's prose then stays out (AgentSummary `answered`) - it was drawn under the words, saying them again */}
        <MessagePrimitive.Parts components={{ Text: AssistantText, data: { by_name: { [PARTS]: TurnWork, agent_steps: TurnWork } } }} />
        {!!rest.length && <PublishedPages pages={rest} open />}
        {!custom?.summary && files}
        {!custom?.summary && lead && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
          <Typography component="span" sx={{ display: "block", color: "var(--tq-text, #292824)", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>Next steps</Typography>{lead}</Box>}
        {/* ...and where the chat is the task's home, the newest one's Next steps holds the draft cards (`next`, Task 4.2) */}
        {work && !custom?.summary && holds && next && chat && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
          <Typography component="span" sx={{ display: "block", color: "var(--tq-text, #292824)", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>Next steps</Typography>{next}</Box>}
        {work && custom?.summary && <AgentSummary summary={custom.summary} folded={!!custom.folded && !(home && holds)} reviews={work.reviews} checklist={work.checklist}
          acts={work.acts} next={(home ? !holds : custom.folded) ? null : next} lastAnswered={lastAnswered} kept={custom.drafts} lead={lead} made={files} turnId={id} answered={answered} />}
        {pressed.map((c) => <React.Fragment key={c.key}>{c.node}</React.Fragment>)}
        <TurnAsks cards={mine.filter((c) => c.waits)} also={holds && !!next && mine.some((c) => c.also)} />
        {landing?.after === id && landing.node}
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
      // AN ACT'S BOX SHOWS ITS WORDS, as every other card of it does (reviewText) - it showed the proposal's JSON, and sent that back. It goes
      // as proposed unless they changed the words
      const shown = reviewText(r), typed = edits[r.ReviewId];
      const finalText = r.Kind === "action" ? (typed != null && typed !== shown ? typed : null) : typed ?? shown;
      // ...the one press (press.js): one decided in another window is read again, with no "Sent" over it; no answer in time is not a failure
      const o = await press(api, r.ReviewId, { verb, final_text: verb === "approve" ? finalText : null }, r.Kind === "action" ? 2 : 1);
      if (o.kind === "already") return void await refresh("");
      if (o.kind === "error") throw o.thrown;
      if (o.kind !== "ok") { setError(failLine(o)); if (o.kind === "unknown") await load(); return; }
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
          value={edits[review.ReviewId] ?? reviewText(review)}
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
              <Button size="small" variant="contained" disabled={!!busy || !(edits[review.ReviewId] ?? reviewText(review)).trim()}
                startIcon={<SendRoundedIcon />} onClick={() => decide(review, "approve")}>
                {busy.includes("approve") ? "Sending…" : btn("approve")}
              </Button>
            )}
            <Button size="small" variant="outlined" disabled={!!busy} startIcon={<RefreshRoundedIcon />}
              onClick={() => redraft(review)}>{busy.includes("redraft") ? "Drafting…" : review.DraftText ? btn("redraft") : btn("redraft", "none")}</Button>
            <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "var(--tq-warning, #867f74)", borderColor: "var(--tq-border, #d6cec1)" }} title={`${btnHint("close")} - this draft is not sent`} onClick={() => decide(review, "no_reply")}>{btn("close")}</Button>
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
          <Button size="small" variant="outlined" disabled={!!busy} sx={{ color: "var(--tq-warning, #867f74)", borderColor: "var(--tq-border, #d6cec1)" }}
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
  // a card headed "Taskuary asked you something". NOTHING THE AGENT ASKS IS A BOX (the owner, 2026-11-11: "Stop making popups for approvals.
  // just ask" - "only actions should have boxes"): a request for leave or a stuck turn used to keep a boxed lead ("Agent needs your
  // approval") over its words; it is a line of the chat as a question is, its buttons under it where it has any
  const plain = String(asking.text || "").trim() || says(subState({ request: asking }), name);
  return (
    <div className="tq-aui-asked" data-tq-asking={asking.request_id}>
      <p className="tq-aui-asked-q">{plain}</p>
      {!!choices.length && <div className="tq-aui-asking-choices">
        {choices.map((c) => <Button key={c} size="small" variant="outlined" disabled={going} onClick={() => send(c)}>{c}</Button>)}
      </div>}
      {err && <span className="tq-aui-asking-err" role="alert">{err}</span>}
    </div>
  );
}

// the arrow of a box whose turn is running: live over words (or a file), and its press holds the line (holdText) - what Enter does there
// ── THE CONVERSATION: ONE LIST, DRAWN AS IT STANDS (the owner, 2026-11-11: "this needs a rebuild with one pass robust code, with shared code for
// general and coding agents") ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
// The server owns the list (conversation.py): what came in, his lines, his presses, the agent's turns - each where the agent heard it - and
// what still waits for the agent, apart. This draws it: one row per item, keyed by the item's own name, whatever agent works the task and
// whatever road it runs on. Nothing here decides an order, a place for a card, or whether a line was heard.
export function useConversation(tid, on) {
  const [list, setList] = useState(null), rev = useRef("");
  const load = useCallback(() => (on ? api.get(`/api/tasks/${tid}/conversation`, { params: { rev: rev.current } }).then(({ data: d }) => {
    if (!d || d.same) return false;
    rev.current = d.rev; setList(d); return true;
  }).catch(() => false) : Promise.resolve(false)), [tid, on]);
  useEffect(() => { rev.current = ""; setList(null); load(); }, [load]);
  const going = !!list?.working;
  // ...a turn at work is read as it goes; at rest the server's own poke (task-changed) brings what is new, and a slow look backs it up
  useEffect(() => { if (!on) return undefined; const t = setInterval(load, going ? 600 : 5000); return () => clearInterval(t); }, [on, going, load]);
  useEffect(() => (on ? onLive("task-changed", (ev) => { if (touches(ev, tid)) load(); }) : undefined), [on, tid, load]);
  return { list, load };
}
const INPUTS = ["line", "arrival", "press", "note"];
const TurnTime = ({ t }) => {
  const end = t.ended ? new Date(t.ended * 1000) : t.at ? new Date(String(t.at).replace(" ", "T")) : null;
  if (!end || Number.isNaN(+end)) return null;
  const ran = t.started && t.ended ? turnStamp({ start: t.started * 1000, end }) : "";
  return <span data-tq-ran="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>· {when(end)}{ran ? ` · ${ran}` : ""}</span>;
};
const ConvTurn = ({ t, more, cards, name }) => {
  const live = t.state === "working" || t.state === "starting";
  const parts = useMemo(() => turnParts(eventsOf(t.steps || [], live), { answer: t.text || "" }), [t.steps, t.text, live]);
  const key = t.answer || t.id, at = useTurnOutputs(key), shown = React.useContext(ShownCtx)[key];
  const sum = t.summary, words = t.text || (sum ? [sum.about, sum.did].map((x) => String(x || "").trim()).filter(Boolean).join("\n\n") : "");
  const made = at ? turnFiles({ listed: at.listed, id: key, words, did: sum?.did, tid: at.tid, skip: [] }) : [];
  const names = new Set(made.map((f) => f.name));
  const rest = shownOnce(at ? outputRefs(words, at.tid, at.listed).files : [], shown).rest.filter((p) => !names.has(p.name));
  const quiet = !live && !hasParts(parts) && !words && !t.fail && !cards?.length && !made.length && !rest.length;
  if (quiet) return null;
  return <div className={`tq-aui-message tq-aui-agent${words && !live ? " tq-copy-host" : ""}${more ? " tq-aui-agent-more" : ""}`} data-tq-item={t.id} data-tq-chat-line={key} data-tq-turn={t.state}>
    {!!words && !live && <CopyCorner text={words} label="Copy this answer" />}
    {!more && <div className="tq-aui-role">{name}{live ? <RunClock start={(t.started || Date.now() / 1000) * 1000} /> : <TurnTime t={t} />}</div>}
    <div className="tq-aui-agent-body">
      <TurnWorkView data={{ parts }} now={live} ended={!!t.text && !live} k={t.id} />
      {!!words && <SaidText text={words} mid={key} />}
      {live && <div className="tq-aui-thinking" role="status" aria-label="The agent is at work" data-tq-working="" {...(t.state === "starting" ? { "data-tq-starting-line": "" } : {})}><i /><i /><i /></div>}
      {t.state === "failed" && !!t.fail && <div className="tq-aui-hint" role="alert" data-tq-turn-failed="">⚠ {t.fail}</div>}
      {!!rest.length && <PublishedPages pages={rest} open />}
      {!!made.length && <TurnFiles files={made} />}
      {!!cards?.length && <div data-tq-turn-cards="">{cards}</div>}
    </div></div>;
};
const ConvLine = ({ x, more, waits = false }) => {
  const stamp = x.at ? when(x.at instanceof Date ? x.at : String(x.at)) : "";
  return <div className={`tq-aui-message tq-aui-user${more ? " tq-aui-user-more" : ""}`} data-tq-item={x.id} data-tq-chat-line={x.id} {...(waits ? { "data-tq-held": "" } : {})}>
    {!more && <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />You{stamp ? ` · ${stamp}` : ""}</div>}
    <div className="tq-aui-user-bubble" dir="auto">{x.text}</div>
    {!!x.err && <div className="tq-aui-hint" role="alert">{x.err}</div>}</div>;
};
/* `items`: the server's list, with this page's own lines the server has not answered for yet (`mine`) already merged in by their names.
   `nodes`: the cards the page draws, by the review each is of ([{key, rid, node}]); `next`: the reply that waits, at the card it is. */
function Conversation({ items, nodes = [], posts = [], next = null, nextRid = null, landing = null, name, tid, onChanged }) {
  const used = new Set();
  const draw = (cs) => (cs || []).flatMap((c) => {
    const got = nodes.filter((n) => n.rid === c.review && !used.has(n.key)), post = posts.find((p) => p.ReviewId === c.review);
    got.forEach((n) => used.add(n.key));
    return [...got.map((n) => <React.Fragment key={n.key}>{n.node}</React.Fragment>),
      ...(post && !used.has(`post:${c.review}`) && used.add(`post:${c.review}`) ? [<ActionCard key={`post:${c.review}`} row={post} tid={tid} onChanged={onChanged} />] : []),
      ...(next && c.review === nextRid && !used.has("next") && used.add("next") ? [<Box key="next" data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>{next}</Box>] : [])];
  });
  const rows = items.map((x, i) => {
    const prev = items[i - 1];
    if (x.kind === "turn") return <ConvTurn key={x.id} t={x} more={prev?.kind === "turn"} cards={draw(x.cards)} name={name} />;
    if (x.kind === "line") return <ConvLine key={x.id} x={x} more={prev?.kind === "line"} />;
    if (x.kind === "arrival") return <div key={x.id} className="tq-aui-message tq-aui-brief" data-tq-item={x.id}><Arrived mail={[x]} prev={prev?.kind === "arrival" ? prev : null} /></div>;
    if (x.kind === "card") { const got = draw([x]); return got.length ? <div key={x.id} className="tq-aui-message tq-aui-agent" data-tq-item={x.id} data-tq-row-cards=""><div className="tq-aui-agent-body">{got}</div></div> : null; }
    return <div key={x.id} className={`tq-aui-message tq-aui-press${prev && (prev.kind === "press" || prev.kind === "note") ? " tq-aui-press-more" : ""}`} data-tq-item={x.id} data-tq-chat-press="">
      <div className="tq-aui-press-line">{pressLine(x.text, x.at ? when(String(x.at)) : "")}</div></div>;
  });
  // ...a card the list places nowhere (made this instant, the list a read behind) is never lost: under everything, until the list names its turn
  const loose = nodes.filter((n) => !used.has(n.key));
  return <>{rows}
    {!!loose.length && <div className="tq-aui-message tq-aui-agent" data-tq-row-cards="loose"><div className="tq-aui-agent-body">{loose.map((n) => <React.Fragment key={n.key}>{n.node}</React.Fragment>)}</div></div>}
    {next && !used.has("next") && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>{next}</Box>}
    {landing}</>;
}
/* WHAT WAITS FOR THE AGENT, BY THE BOX: accepted, not yet handed over - never in the conversation until it is (the heard rule) */
const PendingStrip = ({ items }) => (!items.length ? null : <div className="tq-conv-pending" data-tq-pending="" role="status">
  <div className="tq-conv-pending-head">Waiting for the agent{items.length > 1 ? ` · ${items.length}` : ""}</div>
  {items.map((x) => <div key={x.id} className={`tq-conv-pending-row${x.err ? " tq-conv-pending-err" : ""}`} data-tq-pending-item={x.id} data-tq-held="" dir="auto" title={x.text || x.words || ""}>
    <span className="tq-conv-pending-who">{x.kind === "line" ? "You" : x.kind === "arrival" ? (x.own ? "You, outside" : x.who || "Someone") : ""}</span>
    <span className="tq-conv-pending-words">{x.err ? `${x.text} - ${x.err}` : x.text || x.words || ""}</span></div>)}
</div>);
/* this page's own lines and the server's list as one: a line it sent is drawn at once - in the conversation when the agent was at rest (it is
   heard as it is sent, its turn under it), by the box when a turn was at work - and the server's copy takes over by the same name */
const withMine = (list, mine) => {
  const items = list?.items || [], pending = list?.pending || [], known = new Set([...items, ...pending].map((x) => x.id));
  const own = mine.filter((l) => !known.has(l.id));
  const rest = own.filter((l) => l.rest && !l.err), wait = own.filter((l) => !l.rest || l.err);
  const tail = rest.length && !list?.working ? [{ id: `t:${rest.at(-1).id}:0`, kind: "turn", state: "starting", steps: [], text: "", cards: [], started: +rest.at(-1).at / 1000 }] : [];
  return { items: [...items, ...rest, ...tail], pending: [...pending, ...wait] };
};

function HeldSend({ composer, files, onHold }) {
  const [text, setText] = useState(() => composer.getState().text);
  useEffect(() => { const read = () => setText(composer.getState().text); read(); return composer.subscribe(read); }, [composer]);
  return <button type="button" className="tq-aui-send" data-tq-held-send="" aria-label="Send" disabled={!text.trim() && !files} onClick={onHold}><SendIcon fontSize="small" /></button>;
}

function AssistantThread({ task, messages, published, onAsked, onStop, selectionRef, attachmentsRef, onSent, onStarted, onClearAttachments, onAttach, onAttachBack,
  dock = false, dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  serverBusy = false, provider, name = "Taskuary", work, since, began = null, revision = 0, asking, onAnswer, drafts = [], acts = [], onDraftDecided, starting = "", noComposer = false, waiting = [], box = "",
  onEnded, chat = false, reading = null, came = null, noAi = null, closedLine = "", road = null, cards = null, landing = null, turnCards = null, turns = null, queued = null, heldStart = null, hint = "", placeholder = "",
  empty = "", stopShown = false, seed = null, compacting = false, list = null, reloadList = null }) {
  // A TASK'S CHAT DRAWS THE SERVER'S LIST (Conversation); the Assistant's own dock keeps its streamed thread
  const conv = !dock, turnName = React.useContext(AgentNameCtx);
  const [mine, setMine] = useState([]), merged = useMemo(() => withMine(list, mine), [list, mine]);
  useEffect(() => { if (!list) return; const known = new Set([...list.items, ...list.pending].map((x) => x.id));
    setMine((m) => (m.some((l) => known.has(l.id) && !l.err) ? m.filter((l) => !known.has(l.id) || l.err) : m)); }, [list]);
  const stick = useRef(true), inner = useRef(null), listNow = useRef(list); listNow.current = list;
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
      // (the desktop stress test, 2026-11-03) - and in the dock only, as the server's copy keeps it (messagesWithTrace): in a task's chat
      // the head and its starting line say it, and the note alone drew an empty "Along the way ▸" (the side-by-side walk, 2026-11-11)
      const keepStart = dock && !runMessages.some((m) => m.role === "assistant");
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
        } else if (event.type === "error" && event.code === "stopped") {
          // ...stopped by his x: no failure - the server's copy, with his press's line (general.stop_turn), as a coding chat draws it
          onSent(event.payload);
          return;
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
  }), [attachmentsRef, dock, onBusyChange, onClearAttachments, onEnded, onSent, onStarted, selectionRef, task.TaskId]);
  const runtime = useLocalRuntime(modelAdapter, { initialMessages: initial(messages) });
  /* ONE ROAD FOR A LINE HE SENDS, whatever the agent is and whatever it is doing: named here, drawn at once, posted with that name - the
     server's list answers for it from then on (general.take_line: heard now by an agent at rest, kept for one at work) */
  const sendLine = useCallback((given) => {
    const c = runtime.thread.composer, w = String(given ?? c.getState().text).trim(), files = [...attachmentsRef.current];
    if (!w && !files.length) return;
    if (given == null) c.setText("");
    if (files.length) onClearAttachments(files.map((a) => a.path));
    const id = `l${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`, sel = selectionRef.current || {};
    setMine((m) => [...m, { id, kind: "line", text: w || withImages("", files.map((a) => a.path)), at: new Date(), rest: !listNow.current?.working }]);
    stick.current = true;
    api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text: w, attachments: files.map((a) => a.path), line_id: id, pick: sel.connectorId || null, model: sel.model || null }, { timeout: 0 })
      .then((r) => { if (road) road(); else if (r.data?.messages) onSent?.(r.data); reloadList?.(); })
      .catch((x) => { setMine((m) => m.map((l) => (l.id === id ? { ...l, err: errText(x) } : l))); if (files.length) onAttachBack(files); reloadList?.(); });
    setTimeout(() => reloadList?.(), 120);
  }, [runtime, attachmentsRef, selectionRef, onClearAttachments, onAttachBack, onSent, road, reloadList, task.TaskId]);
  // ...at its end, and held there while he has not moved away from it: what is new draws under what he was reading, never over it
  useEffect(() => {
    const v = viewport.current, el = inner.current;
    if (!conv || !v || !el) return undefined;
    const on = () => { stick.current = v.scrollHeight - v.scrollTop - v.clientHeight < 56; };
    const ro = new ResizeObserver(() => { if (stick.current) v.scrollTop = v.scrollHeight; });
    v.addEventListener("scroll", on, { passive: true }); ro.observe(el);
    return () => { v.removeEventListener("scroll", on); ro.disconnect(); };
  }, [conv, !!list]);   // eslint-disable-line react-hooks/exhaustive-deps
  React.useLayoutEffect(() => { const v = viewport.current; if (conv && v && stick.current) v.scrollTop = v.scrollHeight; }, [conv, merged]);
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
    if (conv) sendLine(prompt.text); else runtime.thread.append(prompt.text);
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
    if (asked.current || road || messages?.length || !text || !wantsAsk(task)) return;
    asked.current = true;
    onAsked?.();
    if (conv) sendLine(text); else runtime.thread.append(text);
  }, [task, messages, runtime, onAsked]);

  // ONE PLACE says what it is doing. Once its steps stream into the thread above, the band repeated the newest of them word for word
  // beneath (the owner, 2026-10-14: "no need while it's working to tell you what it's doing in 2 places") - so it keeps only the
  // dots that say it is alive. The band is for the wait with nothing on screen yet, where an API brain looked frozen (2026-09-07).
  /* OPENED, IT IS AT ITS END (stickEnd.js, the owner, 2026-11-09): held there while the transcript draws in, until the owner moves in it - and
     at rest the newest answer shows from its first line when it is taller than the view (2026-10-18). Placed once at the newest turn's top,
     a coding turn opened at the top of its steps, the middle of the transcript. */
  const viewport = useRef(null), said = !!messages?.length, busyNow = useRef(false);
  busyNow.current = !!serverBusy;
  useEffect(() => {
    if (dock || conv || !said) return undefined;
    const answer = (v) => [...([...v.querySelectorAll(".tq-aui-agent")].pop()?.querySelectorAll("[data-tq-said]") || [])].pop();
    return stickToEnd(viewport.current, (v) => endTop(v, busyNow.current || runtime.thread.getState().isRunning ? null : answer(v)));
  }, [dock, said, runtime]);
  // ...where the chat is home a closed task keeps its box: what is typed reopens it and carries on (server._refuse_closed_chat, 2026-11-05)
  const closedChat = !dock && !chat && ["done", "dropped"].includes(String(task?.Status || ""));
  /* WHILE A QUESTION IS OPEN THE COMPOSER ANSWERS IT (the owner, 2026-11-03: the card had a box of its own, and the answer was typed here
     anyway): its words take the road the card's Answer took (onAnswer) - this conversation's next message, or the asking terminal's answer -
     so the card and the "waiting on you" chip clear the same way. A typed answer to a multiple-choice question goes as typed. */
  const [askErr, setAskErr] = useState(""), answering = useRef(false);
  useEffect(() => { setAskErr(""); }, [asking?.request_id]);
  const answerTyped = (e) => {
    if (conv) { e.preventDefault(); sendLine(); return; }
    // ...a source with its own road (a coding CLI: typed into it, or its session picked back up) takes every line as a held one
    if (!dock && !asking && road) { e.preventDefault(); const c = runtime.thread.composer; holdText(c.getState().text.trim(), c); return; }
    if (dock || !asking) return;
    e.preventDefault();
    const c = runtime.thread.composer, w = c.getState().text.trim();
    if (!w || answering.current) return;
    answering.current = true; setAskErr(""); c.setText("");
    // ...drawn at once at the foot as the owner's (the owner, 2026-11-05: "send it messages and it did not appear right away")
    // ...and drawn ONCE: where the answer goes into this thread (answerAsk's own-session road) the thread draws it, and notShown keeps the held copy away
    const id = `held-${Date.now()}`, after = (messages || []).filter((m) => m?.role === "user").length;
    setHeld((h) => [...h, { id, text: w, after, drawn: mineDrawn.length }]);
    // ...and the agent's turn under it, from the press - never after the request's round trip (the owner, 2026-11-09)
    setSent(sentNow(runtime.thread.getState().messages));
    Promise.resolve(onAnswer?.(w)).catch((x) => { setHeld((h) => h.filter((l) => l.id !== id)); setSent(null); c.setText(w); setAskErr(errText(x)); })
      .finally(() => { answering.current = false; });
  };
  /* TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): Enter while the turn runs put a newline in the box and the line never left -
     under a placeholder that says "Add something for it to pick up". The line is held: drawn at once as the owner's, and sent to the same
     session, which takes it as its next turn (send_prompt waits its turn). The thread's own copy replaces it once the server has it. */
  const [held, setHeld] = useState([]);
  // THE TURN A PRESS ASKED FOR (pendingTurn.js): kept before the request goes, let go once the thread has a turn after it, or once the agent it
  // woke has been at work and stopped - a terminal's agent answers on its own screen, never in this thread
  const [sent, setSent] = useState(null), wasBusy = useRef(false);
  useEffect(() => {
    if (!sent) return undefined;
    const read = () => { if (settled(runtime.thread.getState().messages, sent)) setSent(null); };
    read(); return runtime.thread.subscribe(read);
  }, [sent, runtime]);
  // ...a turn already at work when the line went (a line typed mid-turn) is not the one it asked for: only its end, then a turn started since, counts
  useEffect(() => { if (!sent) { wasBusy.current = false; return; }
    if (!serverBusy && sent.busy) setSent((x) => (x ? { ...x, busy: false } : x));
    else if (serverBusy && !sent.busy) wasBusy.current = true; else if (!serverBusy && wasBusy.current) setSent(null); }, [sent, serverBusy]);
  // ...and a press nothing ever took up stops claiming the agent is coming
  useEffect(() => { if (!sent) return undefined; const t = setTimeout(() => { if (!wasBusy.current && !sent.busy) setSent(null); }, 30000); return () => clearTimeout(t); }, [sent]);
  // WHAT A RESTART PUT BACK IN THE BOX (general.to_box, the owner 2026-11-07): lines no turn took are the owner's again to send, change or
  // clear - never sent for them. Into an empty box, once per text; sending anything from the box ends the offer (general.box_sent)
  const boxed = useRef("");
  useEffect(() => {
    const c = runtime.thread.composer;
    if (!box || boxed.current === box || c.getState().text) return;
    boxed.current = box; c.setText(box);
  }, [box, runtime]);
  // ...and WHAT A CONTINUE LIT FOR THIS TASK SAID (TaskPage `intoChat`): its note, into an empty box, once per press - never over the owner's words
  const seeded = useRef(null);
  useEffect(() => {
    const c = runtime.thread.composer;
    if (!seed || seeded.current === seed.id) return;
    seeded.current = seed.id;
    if (seed.text && !c.getState().text) c.setText(seed.text);
  }, [seed, runtime]);
  // the owner's lines the thread on screen draws - its own appends too, which the server's copy has not caught up with (heldLines.notShown)
  const [mineDrawn, setMineDrawn] = useState([]);
  useEffect(() => {
    const read = () => { const ms = runtime.thread.getState().messages.filter((m) => m.role === "user");
      setMineDrawn((was) => (was.length === ms.length && was.every((m, i) => m === ms[i]) ? was : ms)); };
    read(); return runtime.thread.subscribe(read);
  }, [runtime]);
  // ...and a held line is let go once THAT thread draws it - by the payload alone it went a render before the thread drew it, and in a coding chat
  // his line vanished for a frame the moment the agent took it (the recorded walk, 2026-11-10)
  useEffect(() => { setHeld((h) => (h.length ? stillHeld(h, mineDrawn, "drawn") : h)); }, [mineDrawn]);
  // WHAT IS TYPED AND NOT SENT is this task's, and outlives a reload and this pane drawn afresh (unsent.js): put back into an empty box, kept
  // as it is typed, gone once the box is empty - sent, held or wiped
  useEffect(() => {
    if (dock) return undefined;
    const c = runtime.thread.composer, id = task.TaskId;
    if (!c.getState().text && unsent(id)) c.setText(unsent(id));
    return c.subscribe(() => keepUnsent(id, c.getState().text));
  }, [runtime, dock, task.TaskId]);
  const holdLine = (e) => {
    if (conv) { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) { e.preventDefault(); sendLine(); } return; }
    if (dock || asking) return;
    const c = runtime.thread.composer, w = heldLine(e, c.getState().text, !!road || runtime.thread.getState().isRunning);
    if (!w) return;
    e.preventDefault(); holdText(w, c);
  };
  const holdText = (w, c) => {
    if (!w && !attachmentsRef.current.length) return;
    c.setText("");
    const id = `held-${Date.now()}-${Math.random()}`, after = (messages || []).filter((m) => m?.role === "user").length;
    // ...WITH THE BOX'S FILES: a line held mid-turn went without them, and they sat on in the box (the owner, 2026-11-06) - put back if it did not go
    const files = [...attachmentsRef.current];
    if (files.length) onClearAttachments(files.map((a) => a.path));
    // ...sent UNDER ITS NAME where the road is the chat's own: the conversation has this line when it has the name, whatever else arrived (heldLines.lineOf)
    setHeld((h) => [...h, { id, text: w || withImages("", files.map((a) => a.path)), after, drawn: mineDrawn.length, named: !road }]);
    // ...AND THE AGENT'S TURN UNDER IT FROM THE PRESS, ON EVERY ROAD (the owner, 2026-11-10: "NOthing should ever show above a new promt and the agnt
    // thing should show right away working"): only an answer to its question set it, so a line typed to a coding agent at rest stood under the
    // working line the server drew a beat later, and through a start of ten seconds and more nothing said it was being worked on
    setSent(sentNow(runtime.thread.getState().messages, Date.now(), busyNow.current));
    // ...ONE ROAD ON THE SERVER TOO, whatever agent works the task (general.take_line, the owner 2026-11-10): kept, at work, then handed on
    api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text: w, attachments: files.map((a) => a.path), line_id: id }, { timeout: 0 })
      .then(() => road?.())
      .catch((x) => { setHeld((h) => h.map((l) => (l.id === id ? { ...l, err: errText(x) } : l))); if (files.length) onAttachBack(files); });
  };
  const sendArrow = <ComposerPrimitive.Send className="tq-aui-send" aria-label={!dock && asking ? "Send your answer" : "Send"} onClick={answerTyped}><SendIcon fontSize="small" /></ComposerPrimitive.Send>;
  const [landState, setLandState] = useState(null);
  const landAt = landing ? turnOf(messages, landState?.at || "") : null;
  const landNode = landing ? React.cloneElement(landing, { onState: setLandState }) : null;
  // ...the reply that waits stands at its own card - and once it went, where it stood: the newest reply of the task, waiting or not
  const replies = [...(nextAt?.reviews || [])].reverse().filter((r) => ["draft_reply", "draft"].includes(r.Kind));
  const nextRid = (replies.find((r) => r.Status === "pending") || replies[0])?.ReviewId ?? null;
  const placed = React.useMemo(() => placeCards(turnCards, messages, turns), [turnCards, messages, turns]);
  // ...the chat's cards stand at the foot (no turn has summed it up, none holds the draft): what waits beside them there is "Also"
  const footNext = !dock && nextAt?.next && freshNext(nextAt.reviews) && !summed && !working && !draftHome(nextAt.reviews, messages) && (!chat || messages?.at(-1)?.role !== "assistant");
  const askWords = dock || !asking ? "" : String(asking.request_id || "").startsWith("signin:") ? "Message the agent - never your password" : "Answer the agent's question…";
  const atWork = dock ? <Thinking provider={provider} /> : <AtWork name={name} provider={provider} work={work} since={since} began={began} starting={starting} compacting={compacting} />;
  // ...a turn a press asked for counts from the press, and says it is starting until the agent is at work
  const sentWork = sent && !dock ? <AtWork name={name} provider={provider} work={work} since={sent.at} began={serverBusy ? began : null} compacting={compacting}
    starting={serverBusy ? starting : starting || startingLine(name, provider)} /> : atWork;
  const pressedAt = Math.max(sent?.at || 0, ...held.map((l) => +String(l.id).split("-")[1] || 0));
  // ...the turn a line asked for stands UNDER that line, wherever the line is drawn - never over it (the owner, 2026-11-10): both read the one
  // snapshot of the thread (useFoot)
  const feed = { waiting, held, messages };
  return (
    <AssistantRuntimeProvider runtime={runtime}><LandingCtx.Provider value={landAt && !dock ? { after: landAt, node: landNode } : null}><TurnCardsCtx.Provider value={dock ? [] : placed}><StopCtx.Provider value={dock ? null : onStop}><PressedCtx.Provider value={pressedAt}>
      <ThreadPrimitive.Root className={chat ? "tq-aui-thread tq-aui-chat" : "tq-aui-thread"}>
        <ThreadPrimitive.Viewport ref={viewport} className="tq-aui-viewport" autoScroll={!conv}>
          {conv ? <div ref={inner} className="tq-conv" data-tq-conv={list ? "loaded" : ""}>
            {chat && !!list && !merged.items.length && reading}
            {!!list && !merged.items.length && !!empty && <div className="tq-aui-hint" style={{ margin: "8px 0 16px" }}>{empty}</div>}
            {!!list && !merged.items.length && !empty && !(chat && reading) && <div className="tq-aui-welcome"><TaskuaryMark size={22} /><div>
              <div className="tq-aui-welcome-title">Work on this with your assistant</div>
              <div className="tq-aui-welcome-copy">Research, plan, write, analyze, or coordinate. This conversation stays on the task.</div></div></div>}
            <Conversation items={merged.items} nodes={turnCards || []} posts={nextAt?.cards || []} next={nextAt?.next || null} nextRid={nextRid}
              landing={landNode} name={turnName} tid={task.TaskId} onChanged={nextAt?.refresh} />
            {cards}
            {asking && <AgentAsks asking={asking} name={name} onAnswer={onAnswer} taskId={task.TaskId} />}
            <PublishedPages pages={published} deliver />
            {!turnCards && !!drafts?.length && <Box data-tq-playbook-drafts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{askNote(drafts[0])}</Typography>
              {drafts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {!turnCards && !!acts?.length && <Box data-tq-browser-acts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{heldActsLine(acts)}</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {heldStart}
            {queued && <div className="tq-aui-message tq-aui-agent" data-tq-queued-turn=""><div className="tq-aui-role">{AGENT_TURN}</div><div className="tq-aui-agent-body">{queued}</div></div>}
            {closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
          </div> : <>
          {/* ...where the chat is home, the ask as triage read it is its first line (ChatCtx) */}
          {chat && !messages?.length && reading}
          {/* ...a source that says what an empty chat means (no coding session yet) says so under the reading */}
          {!messages?.length && !starting && empty && <div className="tq-aui-hint" style={{ margin: "8px 0 16px" }}>{empty}</div>}
          {!messages?.length && !starting && !empty && !(chat && reading) && (
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
            <WhileLines feed={feed} waits={false}>{chat ? <BareHead or={pressedAt}>{atWork}</BareHead> : atWork}</WhileLines>
          </ThreadPrimitive.If>
          {/* the answer is being written somewhere else - another tab, or this pane before it was
              reopened - and the poll is what tells us so */}
          {/* ...drawn as the agent's turn, its head and its line, until the thread draws that turn itself (PendingTurn) */}
          <ThreadPrimitive.If running={false}>{dock ? serverBusy && atWork
            : <PendingTurn busy={serverBusy} sent={sent} at={began || since} began={began} feed={feed} held={!!heldStart}>{sentWork}</PendingTurn>}</ThreadPrimitive.If>
          {/* WHAT THE SOURCE WAITS ON THE OWNER FOR, while it works too (`cards`): a coding agent's permission cards, its screen while it asks */}
          {!dock && cards}
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
          {/* ...where the page places the task's cards itself (`turnCards`, the task's chat) each is drawn ONCE, in its turn: these two boxes drew a
              playbook and a held act a second time, with a second Approve (the spine audit, 2026-11-09). A walk's chat, a journey's: here still */}
          {!dock && !turnCards && !!drafts?.length && (
            <Box data-tq-playbook-drafts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{askNote(drafts[0])}</Typography>
              {drafts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}
            </Box>
          )}
          {/* ...AND A BROWSER ACT HELD HERE IS APPROVED HERE (2026-10-25): its card waited in the hidden Close out, and Stop and save, the
              only road to it, closed the very browser Approve runs in. The same card, where the owner already looks. */}
          {!dock && !turnCards && !!acts?.length && (
            <Box data-tq-browser-acts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{heldActsLine(acts)}</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}
            </Box>
          )}
          </ThreadPrimitive.If>
          {/* ...LAST, under everything the turn has drawn - its files and cards too: a PDF the turn made stood under the line typed after it
              (the product audit, 2026-11-08) */}
          {/* ...the SERVER'S copy first (`waiting`, kept the moment each was sent - on every screen, through a reload or a restart), each at the
              time it was typed, then this screen's own not yet kept; all of them waiting for the agent until a turn takes them (2026-11-07) */}
          <FootLines waiting={waiting} held={held} messages={messages} hint={!(sent || serverBusy)} />
          {/* ...and a turn at work while one of his lines waits draws its working UNDER that line: nothing above a new prompt (the owner, 2026-11-10) */}
          <ThreadPrimitive.If running><WhileLines feed={feed} waits>{dock ? atWork : <AtWorkHead or={pressedAt}>{atWork}</AtWorkHead>}</WhileLines></ThreadPrimitive.If>
          {/* ...and the turn its answer asked for, under it (PendingTurn `foot`) */}
          <ThreadPrimitive.If running={false}><PendingTurn busy={serverBusy} sent={sent} began={began} foot feed={feed} held={!!heldStart}>{sentWork}</PendingTurn></ThreadPrimitive.If>
          {/* ...a chat no turn has summed up yet: its cards (TaskPage's chatCards), under the thread */}
          {/* ...a section of the chat like the rest (the owner, 2026-11-05: "still see line of next steps"): a bold head, no rule over it */}
          {/* ...and in a chat no answer carries it yet (a reply triage drafted, no agent run - the owner, 2026-11-06): the draft under the ask */}
          {footNext && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>
            <Typography component="span" sx={{ display: "block", color: "var(--tq-text, #292824)", fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 }}>{hasReply(nextAt.reviews) ? "Suggested reply" : "Next steps"}</Typography>{nextAt.next}</Box>}
          {/* ...the branch's landing, where the task works in a checkout (landing.has_checkout): in its turn (LandingCtx), here only before any */}
          {!dock && !landAt && landNode}
          {/* ...NO "WAITING ON YOU" BOX AT THE FOOT (the owner, 2026-11-10: "it's just a row in the chat"): a card stands in the turn that raised
              it (placeCards); only a chat with no agent turn at all draws one here, as its one row */}
          {!dock && placed.filter((c) => !c.after).map((c) => <React.Fragment key={c.key}>{c.node}</React.Fragment>)}
          {/* ...A START HELD FOR A NEW SENDER says so under what came in, with its Run anyway (HeldStart, the owner, 2026-11-09) */}
          {!dock && heldStart}
          {/* ...A START WAITING FOR A SLOT is the agent's own line in the chat, not a strip over it (the owner, 2026-11-08) */}
          {!dock && queued && <div className="tq-aui-message tq-aui-agent" data-tq-queued-turn="">
            <div className="tq-aui-role">{AGENT_TURN}</div><div className="tq-aui-agent-body">{queued}</div></div>}
          {/* ...AND HOW IT CLOSED, the stream's last line (the owner, 2026-11-06): a closed task is the same chat, its close said in it */}
          {!dock && closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
          </>}
        </ThreadPrimitive.Viewport>
          <div className="tq-aui-footer">
            {conv && <PendingStrip items={merged.pending} />}
            {/* NO AI: one small line over the box, its Connect an AI beside it (the owner, 2026-11-06) - the box stays the box */}
            {!dock && noAi}
            {/* A CLOSED task's conversation is read, not typed into: a message started a live session on a done task, which
                then read "waiting on you" under a bar offering only Reopen (the owner, 2026-10-14). The server refuses it too. */}
            {/* ...and ONE DOOR: while the conversation is open the box is how it goes on (no Continue on the bar, 2026-09-29), but once its
                run has ENDED the bar offers Continue - and a box beside it read as a second way in (the owner, 2026-10-26: "before I hit
                continue it has a space to type into the agent? coding agents don't have that"). `noComposer` is that Continue (TaskPage). */}
            {/* ...but a CHAT task is typed into to go on, closed or not (server._refuse_closed_chat): no Continue is there, so none is named
                (the owner, 2026-11-07) - the box stays, under "Type to reopen it". A coding source keeps Reopen, then Continue */}
            {closedChat && road ? <div className="tq-aui-hint" role="status" style={{ padding: "10px 4px" }}>
              This task is closed. Press {btn("reopen")}, then {btn("continue")}, to pick the conversation back up.</div> : noComposer ? null : <>
            {closedChat && <div className="tq-aui-hint" role="status" data-tq-closed-type="" style={{ padding: "6px 4px 0" }}>This task is closed. Type to reopen it.</div>}
            {/* THE ONE BOX (AgentSummary.OneBox): paperclip, chips, words, mic, stop, Send - the same component as every other box, assistant-ui's
                composer its root, input and Send. Its files inside it, the one attachment look in one line (the owner, 2026-11-05), and WHERE IT CAME
                FROM a chip at its left (2026-11-06: "keep the prompt box thin... put the from you in the left side of the prompt box") - a press opens it */}
            <OneBox root={ComposerPrimitive.Root} rootProps={{ onSubmit: answerTyped }} onFiles={onAttach}
              chips={attachmentsRef.current.length || came ? <>
                {came && <AttachChip data-tq-came-chip="" name={came.label} title={came.title || came.label} icon={came.icon || false} onClick={came.onOpen}
                  sx={{ cursor: came.onOpen ? "pointer" : "default" }} />}
                {attachmentsRef.current.map((a) => <AttachChip key={a.path} data-tq-file-chip={a.name} name={a.name} onRemove={() => onClearAttachments(a.path)} />)}</> : null}
              /* ...by the name the pane shows (kinds.json `shown`): an analyst's box said "the assistant" (the email walk, 2026-10-29) */
              input={<ComposerPrimitive.Input className="tq-aui-input" onKeyDown={holdLine} placeholder={askWords || placeholder || (dock ? "Tell Taskuary what to do next…" : MESSAGE)} />}
              onMic={(t) => { const c = runtime.thread.composer, was = c.getState().text; c.setText(was.trim() ? `${was.trimEnd()} ${t}` : t); }}
              /* stopping is an ACT: closing this page is not one. The button tells the server to stop the run; abandoning the tab just detaches
                 from it (server.py) - and A TURN THIS PANE DID NOT START has the same stop (the owner, 2026-11-05): a turn woken by new mail, or one
                 running when the page was opened, runs on the server, and the runtime's Cancel stays hidden
                 ...ONLY IN THE DOCK, which draws no turn head: a task's chat stops on the x of its running turn alone (the owner, 2026-11-10:
                 "we should have x button for agent to stop in middle of the work" - one stop, not a second one in the box) */
              extra={dock && <><ComposerPrimitive.Cancel className="tq-aui-cancel" aria-label="Stop response" onClick={onStop}><CloseIcon fontSize="small" /></ComposerPrimitive.Cancel>
                {(road ? stopShown : working) && <ThreadPrimitive.If running={false}><button type="button" className="tq-aui-cancel" data-tq-stop-turn="" aria-label="Stop response"
                  title="Stops this turn - the chat stays, and what you type next carries on" onClick={onStop}><CloseIcon fontSize="small" /></button></ThreadPrimitive.If>}</>}
              /* THE ARROW WHILE IT WORKS (the owner, 2026-11-10: "Arrow works too"): the runtime's Send is off for as long as a turn this pane
                 streams runs, so the arrow stood grey over typed words that Enter would have sent. While it runs the arrow is the held line's */
              send={conv ? <button type="button" className="tq-aui-send" aria-label="Send" data-tq-send="" onClick={() => sendLine()}><SendIcon fontSize="small" /></button>
                : dock || asking ? sendArrow : <><ThreadPrimitive.If running={false}>{sendArrow}</ThreadPrimitive.If>
                <ThreadPrimitive.If running><HeldSend composer={runtime.thread.composer} files={attachmentsRef.current.length}
                  onHold={() => { const c = runtime.thread.composer; holdText(c.getState().text.trim(), c); }} /></ThreadPrimitive.If></>} />
            {askErr && <div className="tq-aui-asking-err" role="alert" style={{ padding: "4px 4px 0" }}>{askErr}</div>}
            <div className="tq-aui-hint">{hint || "Enter sends · Shift+Enter adds a line · paste, drop or attach a file"}</div></>}
          </div>
      </ThreadPrimitive.Root>
    </PressedCtx.Provider></StopCtx.Provider></TurnCardsCtx.Provider></LandingCtx.Provider></AssistantRuntimeProvider>
  );
}

// A CODING SESSION AS THIS CHAT'S SOURCE (codingchat.py): every session's steps or ACP updates, the mail that came in, the live CLI and what it
// waits on the owner for - read again while a CLI runs, when the task moves, and when the page's own session (`term`) changes
function useCodingChat(tid, on, term, cuts = []) {
  const [got, setGot] = useState(null);
  // ...each read that brought something new counted (`moves`), so the poll below calms while the chat stands still (pollCalming)
  const last = useRef(""), moves = useRef(0);
  const load = useCallback(() => (on ? api.get(`/api/tasks/${tid}/coding-chat`).then(({ data: d }) => {
    const seen = JSON.stringify(d?.data || null);
    if (seen !== last.current) { last.current = seen; moves.current += 1; }
    setGot(d?.data || null);
  }).catch(() => {}) : Promise.resolve()), [tid, on]);
  useEffect(() => { setGot(null); load(); }, [load]);
  // the page's own session is the first word that a CLI runs: the read follows it
  const pageLive = on && term?.alive && term.mode !== "assistant" && term.taskId === tid ? term : null;
  const live = got?.live || (pageLive ? { sid: pageLive.sid, cli: pageLive.cli, asking: false, working: !pageLive.waiting } : null);
  useEffect(() => { load(); }, [pageLive?.sid, pageLive?.alive, load]);
  // ...every 2.5 s while a CLI runs, stretching to 10 s while reads bring nothing new (2026-11-09: at up to 1.7 s a read on a busy home,
  // the same answer nearly every time); a new step, or a task-changed poke (read at once below), brings it back to 2.5 s
  // ...and while a start is in flight for a line, before any CLI is up (`working`): every second, so its first word shows at once
  const going = !!live || !!got?.working;
  useEffect(() => (going ? pollCalming(true, async () => { const was = moves.current; await load(); return moves.current !== was; }, got?.working && !live ? 1000 : 2500, 10000, false)
    : undefined), [going, !!live, load]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...and a task-changed poke reads it too - a burst of them (a busy agent's hooks) once per 2.5 s, never two reads at a time (coalesced)
  useEffect(() => {
    if (!on) return undefined;
    const [wake, stop] = coalesced(load, 2500), off = onLive("task-changed", (ev) => { if (touches(ev, tid)) wake(); });
    return () => { off(); stop(); };
  }, [on, tid, load]);
  const cutKey = cuts.join("|"), compacting = useMemo(() => !!got && compactingNow(got), [got]);
  const rows = useMemo(() => (got ? chatRows({ ...got, cuts }) : []), [got, cutKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  return { got, live, rows, load, compacting };
}
// ...the two sources in one stream, in the order things happened (a turn still at work, with no time of its own yet, at the foot)
const byTime = (ms) => ms.map((m, i) => [String(m.createdAt || "9999").replace("T", " "), i, m]).sort((a, b) => a[0].localeCompare(b[0]) || a[1] - b[1]).map((x) => x[2]);

export function GeneralWorkspace({ task, onSession, onAnswered, compact = false, dock = false, toolsAt = null,
  dockExpanded = false, prompt, onPromptUsed, onBusyChange, onDockNavigate, onDockChanged,
  onDockNewChat, noAiSaid = false, noTools = false, noComposer = false, liveSid = "", reread = 0, mails = [], reviews = [],
  checklist = null, opening = false, next = null, chat = false, came = null, closedLine = "", term = null, landing = null, turnCards = null, queued = null, heldStart = null, onChanged, seed = null }) {
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
  // ONE CHAT, WHATEVER THE SOURCE (chatStream.chatSource): a coding task's sessions, or the general agent's conversation - and how much of the
  // work it draws (chatDetail.js): this task's own choice, else its kind's default from Settings. Off a task's own chat (the dock, the Wall), as ever
  const source = dock ? "general" : chatSource(task, term), coding = source === "coding";
  const conv = useConversation(task.TaskId, !dock);
  const cc = useCodingChat(task.TaskId, coding, term, (chat && !dock ? turnCards || [] : []).map((c) => c.at)), defaults = useChatDefaults(), own = useOwnDetail(task.TaskId);
  const level = chat && !dock ? detailFor({ source, settings: defaults, own }) : "steps";
  useEffect(() => { if (cc.got) setRevision((k) => k + 1); }, [cc.got]);
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
    if (coding) { setData({ messages: [] }); return () => { live = false; }; }
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => live && accept(r.data)).catch((e) => live && setError(errText(e)));
    return () => { live = false; };
  }, [accept, task.TaskId, coding]);

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
    if (coding) api.post(`/api/tasks/${task.TaskId}/agent/cancel`).then(() => setTimeout(cc.load, 600)).catch((x) => setError(errText(x)));
    else api.post(`/api/tasks/${task.TaskId}/assistant/cancel`).catch(() => {});
  }, [task.TaskId, coding, cc.load]);
  /* On screen, the agent's CLI stays open: the server reaps one nobody touches for 30 minutes, and this is the touch. Nothing starts here. */
  useEffect(() => {
    if (coding) return undefined;
    const seen = () => { if (!document.hidden) api.post(`/api/tasks/${task.TaskId}/assistant/seen`).catch(() => {}); };
    seen(); const t = setInterval(seen, 60000);
    return () => clearInterval(t);
  }, [task.TaskId, coding]);

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
  // ...`working`: the one fact both chats' payloads carry (general.line_state) - a start in flight for a line, or a turn at work
  const busy = !!data?.working || !!data?.session?.busy || !!data?.starting || (!dock && opening);
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
    if (coding) { cc.load(); return; }           // a coding source reads its own sessions (useCodingChat)
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => { accept(r.data); setRevision((k) => k + 1); }).catch(() => {});
  }, [accept, task.TaskId, coding, cc.load]);
  // A SESSION ANOTHER DOOR STARTED (`liveSid`, the page's live one): the canvas's Continue card, the Assistant, the phone. The page
  // adopted it, but this conversation had loaded before it existed and polls only while it knows of a turn, so a Continue with a note
  // showed the old turns under an agent that had already asked its question (the agents walk, 2026-10-26). Read again when they differ.
  // ...but a turn that FAILED is read without handing the read to the thread: the bump swapped in the server's copy, which has neither
  // the reason nor - when it failed before the agent took it - the owner's own words, so a refused send left nothing on screen (the owner,
  // 2026-11-02: "the text goes no where"). The page still learns the session is down (accept -> onSession); the thread keeps both.
  // ...and the task read again with it: the page's own "starting" stood on the stale task, its running head over a start that was refused and
  // its hold said under it (the recorded walk, 2026-11-10: "AGENT · ran 50s" over "Waiting for you ... Trust them")
  // ...unless the server's copy SAYS the failure (general.with_failure: his line, then the reason): then it is handed over. A poll's read taken
  // while the turn ran is applied as the run ends - its copy from before the failure wiped the turn's own "⚠", and his line stood alone under a
  // head spinning for a minute over an agent long dead (the overnight walk, 2026-11-11)
  const failed = useCallback(() => {
    if (coding) return;
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => { accept(r.data); if (r.data?.messages?.at(-1)?.failed) setRevision((k) => k + 1); }).catch(() => {});
    onChanged?.();
  }, [accept, task.TaskId, coding, onChanged]);
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
  // ...what the agent asks, by the one read both payloads carry (taskstate.asking): gone from the card the moment it is answered
  const ask = (coding ? cc.got : data)?.asking, asking = ask && ask.request_id !== answered ? ask : null;
  const needRaw = needsOwner(asking,
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
  const shownMessages = withoutAsked((() => { const general = messagesWithTrace(data?.messages, session, dock);
    // ...a coding turn at work is stamped from its own first step (`since`), never from the mail above it - or from the press that began it, the
    // earlier (general.line_state `turnStarted`): its first step comes once the adapter is up, and the head read "ran 2s" after "ran 9s"
    const pressed = cc.got?.turnStarted ? cc.got.turnStarted * 1000 : null;
    const turns = rowMessages(cc.rows).map((m) => (String(m.id).startsWith("live-") && m.createdAt ? { ...m, since: turnFrom(+asUtc(m.createdAt) || null, pressed) || undefined } : m));
    // ...and each press a quiet line at its time, the general chat's own (general.press_lines: the coding payload's `presses`)
    return coding ? byTime([...general, ...turns, ...(cc.got?.presses || [])]) : general; })(), dock ? null : asking);
  // ...and what typing does there: into the running CLI as its next line, or the session picked back up with these words leading - the files
  // named to the CLI by their paths after the words (promptImages.withImages), as every coding CLI reads a file
  // ...and what a coding source reads once a line is in: its own sessions (the line itself goes the one road, holdText)
  const road = coding ? () => { onChanged?.(); cc.load(); } : null;
  // ...its screen is a card only on the pty road, and only while it asks (codingchat.live_of `asking`); over ACP Stop ends the turn
  const acp = cc.live?.transport === "acp", screenAsks = coding && !!cc.live?.asking && !acp && !!cc.live?.sid, perms = coding ? cc.got?.permissions || [] : [];
  const codingBusy = coding && (!!cc.got?.working || !!cc.live?.working) && !screenAsks && !perms.length;
  const codingCards = coding ? <>
    {/* WHAT THE AGENT WAITS ON THE OWNER'S PRESS FOR (permissions.py): one card each, answered here or on a bound chat */}
    <PermissionCards taskId={task.TaskId} items={perms} onAnswered={cc.load} />
    {/* THE AGENT'S SCREEN, WHILE IT ASKS: the live terminal in the stream, answered there; gone once it stops asking */}
    {screenAsks && <div className="tq-cc-screen" data-tq-chat-screen="" role="group" aria-label="The agent's screen is asking something">
      <div className="tq-cc-screen-head">The agent's screen is asking something</div>
      <TerminalPane sid={cc.live.sid} height="300px" onExit={cc.load} /></div>}</> : null;
  const closedTask = ["done", "dropped"].includes(String(task.Status || ""));
  // WHO is on this task, what its turn has done so far, and when the turn began - all three read
  // off what this pane already has (agentWork.js). The dock is exempt: it IS the assistant.
  // Plain calls, NOT useMemo: this sits after the early return for "no data yet", so a hook here
  // runs on some renders and not others - which is React #310, and it blanked the whole view.
  const name = dock ? "Taskuary" : agentName(task);
  const work = workOf(session?.trace);
  // ...a coding turn at work counts from its own start, as a general one from the server's `turn_started`: the live session's `turnStarted`
  // (codingchat.live_of), else its first step - never the owner's last line drawn, two days back under a resumed session ("2947m 55s", 2026-11-08)
  const codingAt = coding ? shownMessages.find((m) => String(m.id).startsWith("live-"))?.createdAt : null;
  // ...and its clock, from the press where a press began it (general.line_state `turnStarted`), the same read for both
  const turnAt = (coding ? cc.got : data)?.turnStarted;
  const since = turnStart(shownMessages), began = turnAt ? turnAt * 1000 : session?.busy && session?.turn_started ? session.turn_started * 1000
    : coding && cc.live?.working && cc.live?.turnStarted ? cc.live.turnStarted * 1000 : codingAt ? +asUtc(codingAt) || null : null;
  // name the backend that is thinking. The session's own provider is the truth once it has one; on
  // a first turn there is no session yet, so fall back to the one the picker is showing.
  const pickedLabel = (data?.providers || []).find((p) => String(p.id) === String(connectorId))?.label;
  // STARTED AND SILENT: the agent is on its way and has filed nothing - the pane is that one line high, not the room an answer gets
  // ...and only while this turn has drawn nothing: a page opened four minutes into a first turn read "Starting… 3s" over its steps (2026-11-07)
  const quiet = !dock && busy && !drawn && !(data?.messages || []).some((m) => m.role === "assistant");
  // ...and a start onto a conversation that has answered before (Continue, a carried-on turn): the same line until this turn draws its
  // first output, under the turns already there - never "is working" over a session that has not come up yet (2026-11-04)
  const starting = quiet || (!dock && (data?.starting || opening) && !drawn) ? startingLine(name, session?.provider || pickedLabel) : "";
  // the chat IS the workspace, running or not - a session only decides whether a browser sits
  // beside it. It used to be one of four bodies behind a switcher (a fake terminal of the same
  // conversation, a browser button, a numbers panel); a general agent is a chat the way a coding
  // agent is a terminal, so there is nothing to switch (the owner, 2026-09-22).
  // THE ANSWER GOES WHERE THE QUESTION CAME FROM: this conversation's own agent takes it as its next message, streamed here as any
  // other (its new turn overtakes the question - workerstate.open_requests); an agent asking from a terminal on this task gets it
  // through the worker's answer road (workerstate.answer), and the card's state clears with the `answered` it records
  const answerAsk = async (text) => {
    const req = asking;
    if (isTurn(req) && (req.choices || []).includes(text)) return handBack();      // the Done of a step on the page: a press wherever it is drawn
    // ...and a chat agent's question kept after its process idled out (`resting`): the answer is its next turn, which starts it again
    if (req.resting || (session?.sid && String(req.sid) === String(session.sid))) { setOwnPrompt({ id: `ask:${req.request_id}`, text }); setAnswered(req.request_id); return; }
    // ...and a coding agent's as any line typed to it (general.take_line): its next turn takes the line, and that closes the question
    if (road && req.kind !== "approval_needed") { await api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text }, { timeout: 0 }); setAnswered(req.request_id); road(); return; }
    // ...words that are no answer to a request's buttons are his next line (workerstate.LINE): the request stays lit
    const { data: got } = await api.post(`/api/tasks/${task.TaskId}/worker/answer`, { request_id: req.request_id, text });
    if (got?.state !== "line") setAnswered(req.request_id);
    onAnswered?.(); road?.();
  };
  /* WHAT WAITS ON THE BROWSER IS ON THE BROWSER (the owner, 2026-10-28: "it should show up as a BROWSER inside the agent canvas ... so it
     flows better to go back and continue"). A held act of this session's browser shows its Approve / Dismiss on the view, and the
     agent's hand-over of the page ("your turn") its Done - both into this same conversation. Off screen (a phone's chip), their cards. */
  const viewActs = (data?.browserActs || []).map((r) => heldOn(r, session?.sid)).filter(Boolean);
  const turn = asking && isTurn(asking) ? asking : null;
  // ...a held SHELL step is the task page's card in Next steps, one card for the turn (HeldSteps) - it was drawn here a second time, per step
  const actsHere = (viewShown ? (data?.browserActs || []).filter((r) => !heldOn(r, session?.sid)) : data?.browserActs || []).filter((r) => proposalFrom(r)?.action !== "shell_act");
  // Approve runs the act and tells the agent on a thread of its own (browsergate._tell): its next turn starts a moment after the press
  const decidedOnView = () => { refresh(); setTimeout(refresh, 2000); };
  // THE VIEW'S DONE IS THEIR PRESS (the spine audit, 2026-11-09): it went in as words typed in their name - a bubble they never wrote. The
  // server closes the hand-over and tells the agent itself (workerstate.answer `press`, browsergate.done); the chat reads one quiet line
  const handBack = async () => {
    const req = asking;
    try { await api.post(`/api/tasks/${task.TaskId}/worker/answer`, { request_id: req.request_id, text: "", press: true }); }
    catch (e) { if (e?.response?.status !== 409) throw e; }      // closed already: the page moved on first, and the agent was told that
    setAnswered(req.request_id); onAnswered?.(); decidedOnView();
  };
  const promptUsed = (id) => { if (ownPrompt?.id === id) setOwnPrompt(null); else onPromptUsed?.(id); };
  // ...the turn each card and page stands in, as the server names it - a general answer's id, a coding turn by its step (chatStream.turnOfStep)
  const src = coding ? cc.got : data, named = coding ? turnOfStep(shownMessages) : (x) => x;
  const placed = placeShown((src?.published || []).map((p) => ({ ...p, after: named(p.after) })), shownMessages);     // no hook: below the loading return
  const cardTurns = src?.turns && Object.fromEntries(Object.entries(src.turns).map(([k, v]) => [k, named(v)]));
  // the task's checklist where the page has not handed it in: the row carries it (store.list_tasks selects t.*)
  const steps = checklist || (() => { try { const a = JSON.parse(task?.Checklist || "[]"); return Array.isArray(a) ? a : []; } catch { return []; } })();
  const thread = (
    <LevelCtx.Provider value={level}><ChatCtx.Provider value={chat && !dock}><AgentNameCtx.Provider value={dock ? name : AGENT_TURN}><ShownCtx.Provider value={placed.by}>
    <WorkCtx.Provider value={dock ? null : { reviews: withTurns(reviews, (src?.drafts || []).map((d) => ({ ...d, turn: named(d.turn) }))), checklist: steps, acts: [...(data?.browserActs || []), ...(data?.playbookDrafts || [])], next,
      cards: data?.cards || [], refresh }}>
    <OutputsCtx.Provider value={dock ? null : { tid: task.TaskId, listed: data?.outputs, versions: data?.turnOutputs }}>
    <LocalFiles.Provider value={dock ? null : { tid: task.TaskId }}>
      {/* ...and every other file in the task's outputs folder - one no answer names - at the foot, with what it published or showed */}
      <AssistantThread key={task.TaskId} revision={revision} task={task} messages={shownMessages} list={conv.list} reloadList={conv.load}
        published={dock ? placed.foot : [...placed.foot, ...uncited(data?.outputs, shownMessages.filter((m) => m.role === "assistant").map(textOf), task.TaskId)
          // ...a file its turn draws, or a post's own picture, is not one more row at the foot of a chat
          .filter((r) => !(chat && (shownMessages.some((m) => m.id === r.after) || (data?.cards || []).some((p) => p.post?.image === r.path))))]}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onStarted={started} onEnded={failed} onClearAttachments={clearAttachments} onAttachBack={attachBack}
        onAttach={upload}
        dock={dock} dockExpanded={dockExpanded} prompt={ownPrompt || prompt} onPromptUsed={promptUsed}
        asking={turn && viewShown ? null : asking} onAnswer={answerAsk} noComposer={noComposer}
        onBusyChange={threadBusy} onDockNavigate={onDockNavigate} onDockChanged={onDockChanged}
        serverBusy={busy || codingBusy} provider={coding ? cc.live?.cli || "" : session?.provider || pickedLabel} name={name} work={work} since={since} began={began} compacting={codingBusy && cc.compacting}
        drafts={data?.playbookDrafts || []} acts={actsHere} onDraftDecided={refresh} starting={starting} waiting={(coding ? cc.got?.waiting : data?.waiting) || []} box={data?.box || ""} seed={seed}
        chat={chat && !dock} reading={chat && !dock && readingOf(data?.thread || task?.ThreadJson)?.asking
          ? <div className="tq-aui-ask" data-tq-chat-ask="">{readingOf(data?.thread || task?.ThreadJson).asking}</div> : null}
        came={chat && !dock ? came : null} closedLine={chat && !dock ? closedLine : ""} queued={chat && !dock ? queued : null} heldStart={chat && !dock ? heldStart : null}
        road={road} cards={codingCards} landing={chat && !dock ? landing : null} turnCards={chat && !dock ? turnCards : null} turns={cardTurns} stopShown={coding && acp && !!cc.live?.working}
        placeholder={coding ? (closedTask ? "Write to pick it back up…" : cc.live || !cc.got?.sessions?.length ? MESSAGE : "Write to pick the session back up…") : ""}
        hint={!coding ? "" : acp ? (cc.live.working ? "Enter sends it when this turn ends · Shift+Enter adds a line" : "Enter sends it to the agent · Shift+Enter adds a line")
          : cc.live ? "Enter types it into the running agent · Shift+Enter adds a line" : "Enter picks the session back up with what you wrote · Shift+Enter adds a line"}
        empty={coding && cc.got ? (cc.live ? "The agent is starting - its turns show here as it works." : "No session has run on this task yet - write below to start one.") : ""}
        noAi={!coding && chat && !dock && !data?.providers?.length && !noAiSaid && !data?.demo
          ? <div className="tq-aui-noai" data-tq-no-ai="">No AI is connected yet - what you type waits for one. <ConnectAi size="small" variant="text" /></div> : null} />
    </LocalFiles.Provider>
    </OutputsCtx.Provider>
    </WorkCtx.Provider>
    </ShownCtx.Provider></AgentNameCtx.Provider></ChatCtx.Provider></LevelCtx.Provider>
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
          px: 1.15, py: 0.8, flexWrap: "wrap", bgcolor: "var(--tq-panel, #f8f5ee)", borderBottom: `1px solid ${BORDER}` }}>
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
