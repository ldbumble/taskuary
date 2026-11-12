import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { says, subState } from "./laneSays.js";
import {
  AssistantRuntimeProvider, ComposerPrimitive, ThreadPrimitive, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, CircularProgress, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/ArrowUpward";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import api from "./api.js";
import { onLive, touches } from "./live.js";
import { AttachChip, IMAGE_TYPES, MAX_IMAGES, savePromptFile } from "./promptImages.jsx";
import { keepUnsent, unsent } from "./unsent.js";
import { howToOpen } from "./bugReportOpen.js";
import { baseName } from "./agentSteps.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { chatSource, checkBackDue,  eventsOf, hasParts,  partsMessage, turnParts, workCount } from "./chatStream.js";
export { checkBackDue };
import { detailFor, useOwnDetail } from "./chatDetail.js";
import { useChatDefaults } from "./DetailSlider.jsx";
import { PermissionCards } from "./AgentChannels.jsx";
import { Hunk } from "./DiffView.jsx";
import { withImages } from "./promptImages.jsx";
import WriteIcon from "@mui/icons-material/EditNoteRounded";
import ViewSpec, { PlanRow } from "./ViewSpec.jsx";
import { wantsAsk, withoutAsk } from "./newTask.js";
import { FULL_SX, useFullScreen } from "./fullScreen.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, workOf, doingNow,  elapsedText, turnStamp } from "./agentWork.js";
import { AGENT_TURN, MESSAGE, instructionsHint } from "./kinds.js";
import { assignedAgent } from "./agentIdentity.js";
import { LinkPopups, LocalFiles, Md } from "./md.jsx";
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
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import "./generalWorkspace.css";
import "./agentStepRows.css";
import { ModelSelect, TaskuaryMark } from "./ui.jsx";
import { label as btn } from "./buttons.js";
import { placeName } from "./words.js";
import { starting as startingLine } from "./laneSays.js";
import { plural } from "./timeWords.js";
import ConnectAi from "./ConnectAi.jsx";
import ReviewDecision from "./ReviewDecision.jsx";
import { askNote, heldActsLine, proposalFrom } from "./reviewProposal.js";
import BriefLine from "./BriefLine.jsx";
import { OneBox } from "./AgentSummary.jsx";
import HeldStart from "./HeldStart.jsx";
import { dayLabel, fmtTime12 } from "./dates.js";
import { readingOf } from "./threadReading.js";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import TelegramIcon from "@mui/icons-material/Telegram";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";

const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();

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
/* WHAT CAME IN READS IN PLACE (the owner, 2026-11-11: "you should be able to hit expand and read the whole email"): a few lines, and - only
   where they are cut - one toggle that opens the whole message where it stands, whatever channel it came on */
const ArrivedWords = ({ words }) => {
  const el = useRef(null), [open, setOpen] = useState(false), [cut, setCut] = useState(false);
  React.useLayoutEffect(() => { const e = el.current; if (e && !open) setCut(e.scrollHeight > e.clientHeight + 1); }, [words, open]);
  return <><span ref={el} className={`tq-aui-arrived-words${open ? " tq-aui-arrived-open" : ""}`} dir="auto">{words}</span>
    {(cut || open) && <button type="button" className="tq-aui-arrived-more-btn" data-tq-arrived-expand="" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "Show less" : "Show all"}</button>}</>;
};
const Arrived = ({ mail, prev = null }) => mail.map((x, i0, list) => {
  const all = prev ? [prev, ...list] : list, i = i0 + (prev ? 1 : 0);
  const more = sameAs(all[i - 1], x), stamp = x.at ? when(x.at) : "", again = more && stamp === (all[i - 1].at ? when(all[i - 1].at) : "");
  return <div key={i0} className={`tq-aui-arrived${more ? " tq-aui-arrived-more" : ""}${x.own ? " tq-aui-arrived-own" : ""}`} data-tq-chat-arrived={x.own ? "own" : ""}>
    {!again && <span className="tq-aui-arrived-head">{more ? stamp : <><ChannelMark channel={x.channel} />
      {[...headOf(x), stamp].filter(Boolean).join(" · ")}</>}</span>}
    {/* ...a mail's subject over its words, once a run (the owner, 2026-11-09: "you can't see anything about the email") - the words are the
        sender's NEW ones, the stamp and the quoted chain left out on the server (general.mail_row) */}
    {!!subjectOf(x, all[i - 1]) && <span className="tq-aui-arrived-subject" dir="auto">{x.subject}</span>}
    {!!mailWords(x) && <ArrivedWords words={mailWords(x)} />}
    <CameWith x={x} />
  </div>;
});
// a press's event line: its words without the closing stop, then the time - "You changed its workstream · 3:12 PM"
export const pressLine = (words, stamp) => [String(words || "").trim().replace(/\.$/, ""), stamp].filter(Boolean).join(" · ");
// what each answer published or showed, by the answer's id (the server's `after`): drawn under it, open - the agent chose it
const ShownCtx = React.createContext({});
const WorkCtx = React.createContext(null);
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
      {/* ...a step that is his alone on the page - the code a site asks after the saved sign-in (signin.CODE_ASK) - is its own line, whole */}
      {asking.text && asking.text !== `Sign in to ${site} to continue` ? "." : taskId ? <> - <a href="#" onClick={fillPage} data-tq-signin-link=""
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
  // ...AND SAID ONCE: a question its turn's own answer ends in (the list's `said`, conversation.items) stands there, above its card - it was
  // drawn a second time under the card. Only its buttons, where it has any, are drawn here
  if (asking.said && !choices.length && !err) return null;
  return (
    <div className="tq-aui-asked" data-tq-asking={asking.request_id}>
      {!asking.said && <p className="tq-aui-asked-q">{plain}</p>}
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
// ...the list last read of each task: a chat drawn again (the pane remounts when its session starts) draws what it held at once, never a blank beat
const LISTS = new Map();
export function useConversation(tid, on) {
  const [list, setList] = useState(() => LISTS.get(tid) || null), rev = useRef(LISTS.get(tid)?.rev || "");
  // ...READS LAND IN THE ORDER THEY WERE ASKED (the recorded walk, 2026-11-11: on a loaded machine an older read came back after a newer one -
  // his line vanished, the chat read "at rest" over a turn at work, and his next line was drawn as heard): one that a later read overtook is dropped
  const asked = useRef(0), shown = useRef(0);
  const load = useCallback(() => { const n = ++asked.current; return (on ? api.get(`/api/tasks/${tid}/conversation`, { params: { rev: rev.current } }).then(({ data: d }) => {
    if (n < shown.current) return false;
    shown.current = n;
    if (!d || d.same) return false;
    rev.current = d.rev; LISTS.set(tid, d); setList(d); return true;
  }).catch(() => false) : Promise.resolve(false)); }, [tid, on]);
  useEffect(() => { rev.current = LISTS.get(tid)?.rev || ""; setList(LISTS.get(tid) || null); load(); }, [load]);   // eslint-disable-line react-hooks/exhaustive-deps
  const going = !!list?.working;
  // ...a turn at work is read as it goes; at rest the server's own poke (task-changed) brings what is new, and a slow look backs it up
  useEffect(() => { if (!on) return undefined; const t = setInterval(load, going ? 600 : 5000); return () => clearInterval(t); }, [on, going, load]);
  useEffect(() => (on ? onLive("task-changed", (ev) => { if (touches(ev, tid)) load(); }) : undefined), [on, tid, load]);
  return { list, load };
}
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
  // ...WHILE THE CLI COMPACTS ITS CONTEXT the turn at work says so (the owner, 2026-11-10: "show compacting like claude code does"): its newest
  // step is the compaction, not yet over
  const compacting = live && ((x) => x?.k === "compact" && !!x.status && !["completed", "failed", "cancelled"].includes(x.status))((t.steps || []).at(-1));
  if (quiet) return null;
  return <div className={`tq-aui-message tq-aui-agent${words && !live ? " tq-copy-host" : ""}${more ? " tq-aui-agent-more" : ""}`} data-tq-item={t.id} data-tq-chat-line={key} data-tq-turn={t.state}>
    {!!words && !live && <CopyCorner text={words} label="Copy this answer" />}
    {!more && <div className="tq-aui-role">{name}{live ? <RunClock start={(t.started || Date.now() / 1000) * 1000} /> : <TurnTime t={t} />}</div>}
    <div className="tq-aui-agent-body">
      <TurnWorkView data={{ parts }} now={live} ended={!!t.text && !live} k={t.id} />
      {!!words && <SaidText text={words} mid={key} />}
      {live && <div className="tq-aui-thinking" role="status" aria-label="The agent is at work" data-tq-working="" {...(t.state === "starting" ? { "data-tq-starting-line": "" } : {})}><i /><i /><i />{compacting && <span data-tq-compacting="" style={{ marginLeft: 8, fontSize: 12.5 }}>Compacting…</span>}</div>}
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
/* AN ACTION WHERE IT STOOD, once it is no longer the one to press there: a draft a later turn rewrote, or one the agent's latest turn kept -
   which stands under that turn, right above the box. Greyed, nothing to press */
const PAST = { kept: (c) => `${/draft/.test(c.what || "") ? "This draft" : "This action"} stands below, under a later answer`, superseded: () => "Earlier draft - rewritten below" };
const PastCard = ({ c }) => <div className="tq-conv-past" data-tq-past-card={c.status} role="note">
  <div className="tq-conv-past-head">{PAST[c.status](c)}</div>
  {!!c.was?.text && <div className="tq-conv-past-words" dir="auto">{c.was.text}</div>}</div>;
/* `items`: the server's list, with this page's own lines the server has not answered for yet (`mine`) already merged in by their names.
   `nodes`: the cards the page draws, by the review each is of ([{key, rid, node}]); `next`: the reply that waits, at the card it is. */
function Conversation({ items, nodes = [], posts = [], next = null, nextRid = null, landing = null, name, tid, onChanged }) {
  const used = new Set();
  const draw = (cs) => (cs || []).flatMap((c) => {
    if (PAST[c.status]) return [<PastCard key={c.id} c={c} />];
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


function AssistantThread({ task, published, onAsked, onStop, selectionRef, attachmentsRef, onSent, onClearAttachments, onAttach, onAttachBack,
  prompt, onPromptUsed, name = "Taskuary", asking, onAnswer, drafts = [], acts = [], onDraftDecided, noComposer = false,
  chat = false, reading = null, came = null, noAi = null, closedLine = "", road = null, cards = null, landing = null, turnCards = null, queued = null, hold = null, onTrusted, hint = "", placeholder = "",
  empty = "", seed = null, list = null, reloadList = null }) {
  // A TASK'S CHAT DRAWS THE SERVER'S LIST (Conversation) - whatever agent works it; this holds the box, what it sent, and the view's end
  const turnName = React.useContext(AgentNameCtx);
  const [mine, setMine] = useState([]), merged = useMemo(() => withMine(list, mine), [list, mine]);
  useEffect(() => { if (!list) return; const known = new Set([...list.items, ...list.pending].map((x) => x.id));
    setMine((m) => (m.some((l) => known.has(l.id) && !l.err) ? m.filter((l) => !known.has(l.id) || l.err) : m)); }, [list]);
  const stick = useRef(true), inner = useRef(null), viewport = useRef(null), listNow = useRef(list); listNow.current = list;
  const nextAt = React.useContext(WorkCtx);
  // ...the box is assistant-ui's composer (its text, its Enter, its files): the runtime under it answers nothing - a line goes by sendLine
  const runtime = useLocalRuntime(useMemo(() => ({ async *run() { /* the server's list is the conversation */ } }), []));
  /* ONE ROAD FOR A LINE HE SENDS, whatever the agent is and whatever it is doing: named here, drawn at once, posted with that name - the
     server's list answers for it from then on (general.take_line: heard now by an agent at rest, kept for one at work) */
  const sendLine = useCallback((given) => {
    const c = runtime.thread.composer, w = String(given ?? c.getState().text).trim(), files = [...attachmentsRef.current];
    if (!w && !files.length) return;
    if (given == null) c.setText("");
    if (files.length) onClearAttachments(files.map((a) => a.path));
    const id = `l${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`, sel = selectionRef.current || {};
    setMine((m) => [...m, { id, kind: "line", text: w || withImages("", files.map((a) => a.path)), at: new Date(), rest: !listNow.current?.working && !listNow.current?.hold }]);      // ...on an untrusted sender's task it waits by the box at once (the list's `hold`)
    stick.current = true;
    api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text: w, attachments: files.map((a) => a.path), line_id: id, pick: sel.connectorId || null, model: sel.model || null }, { timeout: 0 })
      .then((r) => { if (road) road(); else if (r.data?.messages) onSent?.(r.data); reloadList?.(); })
      .catch((x) => { setMine((m) => m.map((l) => (l.id === id ? { ...l, err: errText(x) } : l))); if (files.length) onAttachBack(files); reloadList?.(); });
    setTimeout(() => reloadList?.(), 120);
  }, [runtime, attachmentsRef, selectionRef, onClearAttachments, onAttachBack, onSent, road, reloadList, task.TaskId]);
  // ...at its end, and held there while he has not moved away from it: what is new draws under what he was reading, never over it
  useEffect(() => {
    const v = viewport.current, el = inner.current;
    if (!v || !el) return undefined;
    const on = () => { stick.current = v.scrollHeight - v.scrollTop - v.clientHeight < 56; };
    const ro = new ResizeObserver(() => { if (stick.current) v.scrollTop = v.scrollHeight; });
    v.addEventListener("scroll", on, { passive: true }); ro.observe(el);
    return () => { v.removeEventListener("scroll", on); ro.disconnect(); };
  }, [!!list]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...after EVERY draw, not only the list's: a card's own words (the page's node) grow the chat too
  React.useLayoutEffect(() => { const v = viewport.current; if (v && stick.current && v.scrollTop + v.clientHeight < v.scrollHeight) v.scrollTop = v.scrollHeight; });
  // WORDS ANOTHER DOOR HANDS THIS CHAT (`prompt`: an answer picked on the question's card): his next line, once
  const prompted = useRef(null);
  useEffect(() => {
    if (!prompt?.text || prompted.current === prompt.id) return;
    prompted.current = prompt.id;
    sendLine(prompt.text);
    onPromptUsed?.(prompt.id);
  }, [onPromptUsed, prompt, sendLine]);
  /* "New task for the agent" with no repository: the prompt the owner typed is the first thing said here, so they watch the answer arrive
     instead of finding a task with their own words sitting in it, unanswered. Read off the TASK (newTask.js: the ask tag), only into a chat
     that has nothing yet, and only once - the tag is stripped as it is asked, so a reload never re-asks. */
  const asked = useRef(false);
  useEffect(() => {
    const text = String(task.Summary || "").trim();
    if (asked.current || road || !list || list.items.some((x) => x.kind === "turn" || x.kind === "line") || !text || !wantsAsk(task)) return;
    asked.current = true;
    onAsked?.();
    sendLine(text);
  }, [task, list, onAsked, road, sendLine]);
  // ...a coding source keeps Reopen, then Continue, over a closed task (a chat task is typed into to go on, closed or not)
  const closedChat = !chat && ["done", "dropped"].includes(String(task?.Status || ""));
  // ...and WHAT A CONTINUE LIT FOR THIS TASK SAID (TaskPage `intoChat`): its note, into an empty box, once per press - never over the owner's words
  const seeded = useRef(null);
  useEffect(() => {
    const c = runtime.thread.composer;
    if (!seed || seeded.current === seed.id) return;
    seeded.current = seed.id;
    if (seed.text && !c.getState().text) c.setText(seed.text);
  }, [seed, runtime]);
  // WHAT IS TYPED AND NOT SENT is this task's, and outlives a reload and this pane drawn afresh (unsent.js): put back into an empty box, kept
  // as it is typed, gone once the box is empty - sent or wiped
  useEffect(() => {
    const c = runtime.thread.composer, id = task.TaskId;
    if (!c.getState().text && unsent(id)) c.setText(unsent(id));
    return c.subscribe(() => keepUnsent(id, c.getState().text));
  }, [runtime, task.TaskId]);
  const onKey = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) { e.preventDefault(); sendLine(); } };
  const landNode = landing ? React.cloneElement(landing, { onState: () => {} }) : null;
  // ...the reply that waits stands at its own card - and once it went, where it stood: the newest reply of the task, waiting or not
  // ...by its number, never by the order the page happened to hold them in: the newest was read as the oldest, and the card he had just
  // pressed Send on went to the first draft's turn, screens above (the recorded walk, 2026-11-11)
  const replies = (nextAt?.reviews || []).filter((r) => ["draft_reply", "draft"].includes(r.Kind)).sort((a, b) => b.ReviewId - a.ReviewId);
  const nextRid = (replies.find((r) => r.Status === "pending") || replies[0])?.ReviewId ?? null;
  const askWords = !asking ? "" : String(asking.request_id || "").startsWith("signin:") ? "Message the agent - never your password" : "Answer the agent's question…";
  return (
    <AssistantRuntimeProvider runtime={runtime}><StopCtx.Provider value={onStop}>
      <ThreadPrimitive.Root className={chat ? "tq-aui-thread tq-aui-chat" : "tq-aui-thread"}>
        <ThreadPrimitive.Viewport ref={viewport} className="tq-aui-viewport" autoScroll={false}>
          <div ref={inner} className="tq-conv" data-tq-conv={list ? "loaded" : ""}>
            {chat && !!list && !merged.items.length && reading}
            {!!list && !merged.items.length && !!empty && <div className="tq-aui-hint" style={{ margin: "8px 0 16px" }}>{empty}</div>}
            {!!list && !merged.items.length && !empty && !(chat && reading) && <div className="tq-aui-welcome"><TaskuaryMark size={22} /><div>
              <div className="tq-aui-welcome-title">Work on this with your assistant</div>
              <div className="tq-aui-welcome-copy">Research, plan, write, analyze, or coordinate. This conversation stays on the task.</div></div></div>}
            <Conversation items={merged.items} nodes={turnCards || []} posts={nextAt?.cards || []} next={nextAt?.next || null} nextRid={nextRid}
              landing={landNode} name={turnName} tid={task.TaskId} onChanged={nextAt?.refresh} />
            {/* WHAT THE SOURCE WAITS ON THE OWNER FOR, while it works too (`cards`): a coding agent's permission cards, its screen while it asks */}
            {cards}
            {asking && <AgentAsks asking={asking} name={name} onAnswer={onAnswer} taskId={task.TaskId} />}
            <PublishedPages pages={published} deliver />
            {/* ...a chat whose page places no cards itself (a walk's, a journey's): a drafted playbook and a held act are approved here */}
            {!turnCards && !!drafts?.length && <Box data-tq-playbook-drafts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{askNote(drafts[0])}</Typography>
              {drafts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {!turnCards && !!acts?.length && <Box data-tq-browser-acts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{heldActsLine(acts)}</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {/* AN UNTRUSTED SENDER'S TASK: one plain line why no agent works on it, and its one action (the list's `hold`, origin.hold) */}
            {hold && <HeldStart taskId={task.TaskId} hold={hold} onChanged={onTrusted} />}
            {queued && <div className="tq-aui-message tq-aui-agent" data-tq-queued-turn=""><div className="tq-aui-role">{AGENT_TURN}</div><div className="tq-aui-agent-body">{queued}</div></div>}
            {closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
          </div>
        </ThreadPrimitive.Viewport>
          <div className="tq-aui-footer">
            <PendingStrip items={merged.pending} />
            {/* NO AI: one small line over the box, its Connect an AI beside it (the owner, 2026-11-06) - the box stays the box */}
            {noAi}
            {/* ONE DOOR: while the conversation is open the box is how it goes on, but once a coding run has ENDED on a closed task the bar
                offers Reopen, then Continue (`noComposer` is that Continue, TaskPage). A CHAT task is typed into to go on, closed or not
                (server._refuse_closed_chat): the box stays, under "Type to reopen it" */}
            {closedChat && road ? <div className="tq-aui-hint" role="status" style={{ padding: "10px 4px" }}>
              This task is closed. Press {btn("reopen")}, then {btn("continue")}, to pick the conversation back up.</div> : noComposer ? null : <>
            {closedChat && <div className="tq-aui-hint" role="status" data-tq-closed-type="" style={{ padding: "6px 4px 0" }}>This task is closed. Type to reopen it.</div>}
            {/* THE ONE BOX (AgentSummary.OneBox): paperclip, chips, words, mic, Send - the same component as every other box, assistant-ui's
                composer its root and input. Its files inside it, the one attachment look in one line (the owner, 2026-11-05), and WHERE IT CAME
                FROM a chip at its left (2026-11-06) - a press opens it. A turn at work stops on the x of its own head, never in the box */}
            <OneBox root={ComposerPrimitive.Root} rootProps={{ onSubmit: (e) => { e.preventDefault(); sendLine(); } }} onFiles={onAttach}
              chips={attachmentsRef.current.length || came ? <>
                {came && <AttachChip data-tq-came-chip="" name={came.label} title={came.title || came.label} icon={came.icon || false} onClick={came.onOpen}
                  sx={{ cursor: came.onOpen ? "pointer" : "default" }} />}
                {attachmentsRef.current.map((a) => <AttachChip key={a.path} data-tq-file-chip={a.name} name={a.name} onRemove={() => onClearAttachments(a.path)} />)}</> : null}
              input={<ComposerPrimitive.Input className="tq-aui-input" onKeyDown={onKey} placeholder={askWords || placeholder || MESSAGE} />}
              onMic={(t) => { const c = runtime.thread.composer, was = c.getState().text; c.setText(was.trim() ? `${was.trimEnd()} ${t}` : t); }}
              send={<button type="button" className="tq-aui-send" aria-label="Send" data-tq-send="" onClick={() => sendLine()}><SendIcon fontSize="small" /></button>} />
            <div className="tq-aui-hint">{hint || "Enter sends · Shift+Enter adds a line · paste, drop or attach a file"}</div></>}
          </div>
      </ThreadPrimitive.Root>
    </StopCtx.Provider></AssistantRuntimeProvider>
  );
}

export function GeneralWorkspace({ task, onSession, onAnswered, compact = false, toolsAt = null,
  prompt, onPromptUsed, noAiSaid = false, noTools = false, noComposer = false, liveSid = "", reread = 0, mails = [], reviews = [],
  checklist = null, opening = false, next = null, chat = false, came = null, closedLine = "", term = null, landing = null, turnCards = null, queued = null, onChanged, seed = null }) {
  const [data, setData] = useState(null);
  const [connectorId, setConnectorId] = useState("");
  const [model, setModel] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [ownPrompt, setOwnPrompt] = useState(null);
  const [answered, setAnswered] = useState("");          // the question this card answered (AgentAsks)
  // the browser view is on screen: what waits on it is drawn there (SessionPane.onView). Not set*-named: the scope check (scope.test)
  // reads this file's JSX apostrophes as strings and loses the declaration
  const [viewShown, viewShownIs] = useState(false);
  // the whole window, where it stands
  const { full, toggle: toggleFull } = useFullScreen();
  const selectionRef = useRef({ connectorId: "", model: "" });
  const attachmentsRef = useRef([]);
  selectionRef.current = { connectorId, model };
  // ONE CHAT, WHATEVER THE SOURCE (chatStream.chatSource): a coding task's sessions, or the general agent's conversation - and how much of the
  // work it draws (chatDetail.js): this task's own choice, else its kind's default from Settings. Off a task's own chat (the Wall), as ever
  const source = chatSource(task, term), coding = source === "coding";
  const conv = useConversation(task.TaskId, true);
  // ..."WORKING" IS ONE FACT ON THE WHOLE PAGE (the recorded walk, 2026-11-11: the chat stood finished under a header that still read "agent
  // working"): the moment the list's own word on it changes, the task's header and its row are read again
  const convWorks = !!conv.list?.working, answeredRef = useRef(onAnswered); answeredRef.current = onAnswered;
  useEffect(() => { if (conv.list) answeredRef.current?.(); }, [convWorks]);   // eslint-disable-line react-hooks/exhaustive-deps
  const defaults = useChatDefaults(), own = useOwnDetail(task.TaskId);
  const level = chat ? detailFor({ source, settings: defaults, own }) : "steps";
  // ...and the CLI that runs, what it asks and what it waits on his press for: the list's own (conversation.items `live`, `asking`, `permissions`)
  const cli = coding ? conv.list?.live || null : null;
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
  }, [onSession]);

  useEffect(() => {
    let live = true;
    setData(null); setError(""); setAttachments([]);
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
  const sent = accept;
  const stopRun = useCallback(() => {
    if (coding) api.post(`/api/tasks/${task.TaskId}/agent/cancel`).then(() => setTimeout(conv.load, 600)).catch((x) => setError(errText(x)));
    else api.post(`/api/tasks/${task.TaskId}/assistant/cancel`).catch(() => {});
  }, [task.TaskId, coding, conv.load]);
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
  // ...`working`: the list's one fact (general.working) - a start in flight for a line, or a turn at work
  const busy = !!conv.list?.working || !!data?.starting || opening;
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
        setData(fresh);
        // ...and the page's copy too: it held the session the turn STARTED with, so its heading said "is working" under the
        // finished answer (2026-10-15)
        // (a read made only because it waits on the page tells the page of a session only when there is one: an agent asking from a
        // terminal has none here, and a null swapped the task's agent view out from under its question)
        if (busy || fresh.session) onSession?.(fresh.session || null);
      } catch { /* it will still be there next tick */ }
    }, drawn ? 2500 : 1000);      // a start that has drawn nothing yet is read every second: its first word gives the room at once
    return () => { live = false; clearInterval(timer); };
  }, [busy, onPage, drawn, task.TaskId, onSession]);
  // ...and what a read brings is handed to the standing thread (a revision bump), as the poll does: taken into `data` alone, the owner's
  // Continue note waited for the next poll to show (the owner, 0.3.9.51: "I did Continue, filled it out and nothing happened")
  const refresh = useCallback(() => {
    conv.load();
    if (coding) return;
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => accept(r.data)).catch(() => {});
  }, [accept, task.TaskId, coding, conv.load]);
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
  const loaded = !!data, knownSid = data?.session?.sid || "";
  useEffect(() => { if (loaded && liveSid && knownSid !== liveSid) refresh(); }, [loaded, liveSid, knownSid, refresh]);
  // ...and at once when that door says it answered (`reread`, bumped by the page): the note is on the conversation by then, and the
  // session it starts is seconds away
  useEffect(() => { if (loaded && reread) refresh(); }, [reread]);  // eslint-disable-line react-hooks/exhaustive-deps
  // ...and when the page learns a start is under way: the session it opens is read now, not a poll later
  useEffect(() => { if (loaded && opening) refresh(); }, [opening]);  // eslint-disable-line react-hooks/exhaustive-deps
  // ...and when the task itself moves (`task-changed`: a mail joined, a turn began - workerstate.record): a turn the SERVER woke on a live,
  // idle session - new mail, a check-back - was never read, as nothing polls an idle pane, and the open chat sat on its first answer while
  // three more turns ran under it (the scenario run, 2026-11-06). Read once then; a turn found at work is the poll's from there. Never over
  // a turn this pane streams itself, whose own copy is the one on screen
  const quietRef = useRef(false); quietRef.current = loaded && !busy;
  useEffect(() => onLive("task-changed", (ev) => { if (quietRef.current && touches(ev, task.TaskId)) refresh(); }), [task.TaskId, refresh]);
  const pasted = (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); upload(files); }
  };
  const dropped = (e) => { const files = [...(e.dataTransfer?.files || [])]; if (files.length) { e.preventDefault(); upload(files); } };
  const dragging = (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); };

  // ...AND ONCE IT IS UP FOR THE OWNER IT STAYS UP until the agent answers again (the owner, 2026-11-05, signing in to a site in two steps: "I put
  // in username then hit next the box disappeared then reopened to put in password. You can leave it open until auth is done"): between a
  // sign-in's pages there is a moment with no ask open, and the page went away under them
  // ...what the agent asks, by the one read both payloads carry (taskstate.asking): gone from the card the moment it is answered
  const ask = (conv.list || data)?.asking, asking = ask && ask.request_id !== answered ? ask : null;
  const needRaw = needsOwner(asking,
      (data?.browserActs || []).map((r) => heldOn(r, data?.session?.sid)).filter(Boolean)), answers = (conv.list?.items || []).filter((x) => x.kind === "turn" && x.state !== "working" && x.state !== "starting").length;
  const [needHeld, setNeedHeld] = useState(null);
  useEffect(() => { if (needRaw) setNeedHeld(answers); }, [needRaw]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...or is AT WORK again: his part is done the moment it goes on (the owner, 2026-11-11: "seamlessly hand off once login is in to go back to
  // normal chat") - a sign-in's ask stays open through every page of it (signin.watch), so the gap this hold covers is never a turn at work
  useEffect(() => { if (needHeld != null && !needRaw && (answers > needHeld || busy || !data?.session?.sid)) setNeedHeld(null); }, [answers, needRaw, needHeld, busy, data?.session?.sid]);
  const needNow = needRaw || needHeld != null;

  // ...a start the page already knows of says so before the conversation's first read lands, never a 520px spinner over nothing
  if (!data && !error) return opening
    ? <Box data-tq-starting="" sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.75, overflow: "hidden", bgcolor: PANEL2, px: 1.5, pt: 1.5, ...(compact ? { height: "auto" } : { flex: "0 0 auto" }) }}>
        <AgentBand name={agentName(task)} work={workOf([])} starting={startingLine(agentName(task))} /></Box>
    : <Box sx={{ height: 520, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>;
  const session = data?.session;
  // ...the agent's turns, as the list holds them: what each said, by the name the page keys a turn by
  const turnsNow = (conv.list?.items || []).filter((x) => x.kind === "turn");
  // ...and what typing does there: into the running CLI as its next line, or the session picked back up with these words leading - the files
  // named to the CLI by their paths after the words (promptImages.withImages), as every coding CLI reads a file
  // ...and what a coding source reads once a line is in: its own sessions (the line itself goes the one road, holdText)
  const road = coding ? () => { onChanged?.(); conv.load(); } : null;
  // ...its screen is a card only on the pty road, and only while it asks (codingchat.live_of `asking`); over ACP Stop ends the turn
  const acp = cli?.transport === "acp", screenAsks = coding && !!cli?.asking && !acp && !!cli?.sid, perms = coding ? conv.list?.permissions || [] : [];
  const codingCards = coding ? <>
    {/* WHAT THE AGENT WAITS ON THE OWNER'S PRESS FOR (permissions.py): one card each, answered here or on a bound chat */}
    <PermissionCards taskId={task.TaskId} items={perms} onAnswered={conv.load} />
    {/* THE AGENT'S SCREEN, WHILE IT ASKS: the live terminal in the stream, answered there; gone once it stops asking */}
    {screenAsks && <div className="tq-cc-screen" data-tq-chat-screen="" role="group" aria-label="The agent's screen is asking something">
      <div className="tq-cc-screen-head">The agent's screen is asking something</div>
      <TerminalPane sid={cli.sid} height="300px" onExit={conv.load} /></div>}</> : null;
  const closedTask = ["done", "dropped"].includes(String(task.Status || ""));
  // WHO is on this task, what its turn has done so far, and when the turn began - all three read
  // off what this pane already has (agentWork.js).
  // Plain calls, NOT useMemo: this sits after the early return for "no data yet", so a hook here
  // runs on some renders and not others - which is React #310, and it blanked the whole view.
  const name = agentName(task);
  // STARTED AND SILENT: the agent is on its way and has filed nothing - the pane is that one line high, not the room an answer gets
  // ...and only while this turn has drawn nothing: a page opened four minutes into a first turn read "Starting… 3s" over its steps (2026-11-07)
  // ...read off the one list, as the chat itself is: the moment a turn has said or done anything the room is its answer's
  const quiet = busy && !drawn && !turnsNow.some((x) => x.text || x.steps?.length);
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
  // ...each page in the turn that made it, as the list names it (conversation.items `published`)
  const turnKeys = turnsNow.map((x) => ({ id: x.answer || x.id }));
  const placed = placeShown(conv.list?.published, turnKeys);     // no hook: below the loading return
  // the task's checklist where the page has not handed it in: the row carries it (store.list_tasks selects t.*)
  const steps = checklist || (() => { try { const a = JSON.parse(task?.Checklist || "[]"); return Array.isArray(a) ? a : []; } catch { return []; } })();
  const thread = (
    <LevelCtx.Provider value={level}><ChatCtx.Provider value={chat}><AgentNameCtx.Provider value={AGENT_TURN}><ShownCtx.Provider value={placed.by}>
    <WorkCtx.Provider value={{ reviews, checklist: steps, acts: [...(data?.browserActs || []), ...(data?.playbookDrafts || [])], next,
      cards: data?.cards || [], refresh }}>
    <OutputsCtx.Provider value={{ tid: task.TaskId, listed: data?.outputs, versions: data?.turnOutputs }}>
    <LocalFiles.Provider value={{ tid: task.TaskId }}>
      {/* ...and every other file in the task's outputs folder - one no answer names - at the foot, with what it published or showed */}
      <AssistantThread key={task.TaskId} task={task} list={conv.list} reloadList={conv.load}
        published={[...placed.foot, ...uncited(data?.outputs, turnsNow.map((x) => x.text || ""), task.TaskId)
          // ...a file its turn draws, or a post's own picture, is not one more row at the foot of a chat
          .filter((r) => !(chat && (turnKeys.some((m) => m.id === r.after) || (data?.cards || []).some((p) => p.post?.image === r.path))))]}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onClearAttachments={clearAttachments} onAttachBack={attachBack}
        onAttach={upload}
        prompt={ownPrompt || prompt} onPromptUsed={promptUsed}
        asking={turn && viewShown ? null : asking} onAnswer={answerAsk} noComposer={noComposer}
        name={name}
        drafts={data?.playbookDrafts || []} acts={actsHere} onDraftDecided={refresh} seed={seed}
        chat={chat} reading={chat && readingOf(data?.thread || task?.ThreadJson)?.asking
          ? <div className="tq-aui-ask" data-tq-chat-ask="">{readingOf(data?.thread || task?.ThreadJson).asking}</div> : null}
        came={chat ? came : null} closedLine={chat ? closedLine : ""} queued={chat ? queued : null} hold={conv.list?.hold || null} onTrusted={() => { conv.load(); onAnswered?.(); onChanged?.(); }}
        road={road} cards={codingCards} landing={chat ? landing : null} turnCards={chat ? turnCards : null}
        placeholder={coding ? (closedTask ? "Write to pick it back up…" : cli || !conv.list?.ran ? MESSAGE : "Write to pick the session back up…") : ""}
        hint={!coding ? "" : acp ? (cli.working ? "Enter sends it when this turn ends · Shift+Enter adds a line" : "Enter sends it to the agent · Shift+Enter adds a line")
          : cli ? "Enter types it into the running agent · Shift+Enter adds a line" : "Enter picks the session back up with what you wrote · Shift+Enter adds a line"}
        empty={coding && conv.list ? (cli ? "The agent is starting - its turns show here as it works." : "No session has run on this task yet - write below to start one.") : ""}
        noAi={!coding && chat && !data?.providers?.length && !noAiSaid && !data?.demo
          ? <div className="tq-aui-noai" data-tq-no-ai="">No AI is connected yet - what you type waits for one. <ConnectAi size="small" variant="text" /></div> : null} />
    </LocalFiles.Provider>
    </OutputsCtx.Provider>
    </WorkCtx.Provider>
    </ShownCtx.Provider></AgentNameCtx.Provider></ChatCtx.Provider></LevelCtx.Provider>
  );
  /* CHIP-SIZED, AND THEY GIVE WAY (the owner, 2026-11-03, Agent beside Close out: "this ui looks weird when split? make the model choice
     smaller"): a 220px brain picker and a 150px model box that never shrank sat on the heading's title - "Tasku… / answ…" - in a ~500px
     half. Each is a small chip now that ends in … before the title does, the model the CLI's own list where it has one,
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
    <Box onPaste={pasted} onDrop={dropped} onDragOver={dragging} data-tq-starting={quiet ? "" : undefined} sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.75, overflow: "hidden", bgcolor: PANEL2,
      minHeight: 0, display: "flex", flexDirection: "column",
      ...(compact ? { height: quiet ? "auto" : "100%" } : { flex: quiet ? "0 0 auto" : "1 1 auto" }),
      ...(full ? FULL_SX : null) }}>
      {/* the strip wraps when its box is narrow - a phone, or a half-width Wall pane; scrolled sideways it hid its buttons entirely.
          On the canvas the task's own step heading holds it (toolsAt) and the answer gets the line - until Full screen, which
          leaves that heading behind */}
      {/* ...and none at all on a card whose session is not live (`noTools`, the owner 2026-10-25): a failed or closed agent's heading carried
          the agent picker, "provider default" and Full screen for a chat nothing is running in - the bar's Run another agent starts one */}
      {/* ...in a fragment: a portal straight under a Box failed its `children` check, a console error on every live agent (2026-10-26) */}
      {/* ...and none in a chat task's chat (the owner's ruling, 2026-11-05: "remove as much as possible ui components in the chat unless it's
          actions"): the agent picker, "provider default" and Full screen are settings, not a step of the task - the chat is the ask, the work, the reply */}
      {!noTools && !chat && toolsAt && !full && <>{createPortal(tools, toolsAt)}</>}
      {!noTools && !chat && !(toolsAt && !full) && <Box sx={{ minHeight: 39, px: 1.25, py: { xs: 0.5, md: 0 }, display: "flex", alignItems: "center", gap: 0.8, borderBottom: `1px solid ${BORDER}`, bgcolor: PANEL,
        flexWrap: "wrap", flexShrink: 0 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: 99, bgcolor: session?.alive ? "#78a17b" : "#c7a258" }} />
        {/* the strip named the window after the concierge; it belongs to the agent working in it */}
        <Typography noWrap sx={{ ...mono, fontSize: 10.5, letterSpacing: ".13em", textTransform: "uppercase", color: DIM, flexShrink: 0 }}
          title={instructionsHint(assignedAgent(task?.Assignee)) || undefined}>{name}</Typography>
        <Box sx={{ flex: 1, minWidth: 8 }} />
        {tools}
      </Box>}
      {error && <Alert severity="error" sx={{ borderRadius: 0, py: 0 }}>{error}</Alert>}
      {/* "Connections → AI", as the chat says it (concierge.py, no AI connected): the AI CLI agents page's own name is a word the owner never reads
          (words.json jargon), and the walk read it here on a box with no AI (WORDS, 2026-10-20) */}
      {/* ...with the button that does it (owner-approved, 2026-10-21): every "no AI" line carries Connect an AI */}
      {/* ...but not where it is already said or no longer matters (`noAiSaid`, the owner 2026-10-25): a closed task, or a failure whose own
          line is that no AI is connected - the banner was the same fact a third time under it */}
      {/* ...nor in the demo, whose turns were written in advance and whose box answers that it is the demo (server._demo_turn) */}
      {!chat && !data?.providers?.length && !noAiSaid && !data?.demo && <Alert severity="info" data-tq-no-ai="" sx={{ borderRadius: 0, py: 0, alignItems: "center" }}
        action={<ConnectAi variant="outlined" />}>No AI is connected, so this work cannot run yet - connect one under {placeName("ai")}.</Alert>}
      {/* ...never in a chat task (the owner, 2026-11-05: no banners): a conversation picked back up reads as the same conversation */}
      {session?.resume_notice && !chat && <Typography sx={{ px: 1.5, py: 0.5, fontSize: 12, color: FAINT }}>{session.resume_notice}</Typography>}
      {/* A SECOND AGENT'S CONVERSATION IS ITS OWN (Run another agent, general.new_run): the earlier agent's stays on the task, folded
          above it and read only - the thread below is the new one's, never the old one picked back up */}
      {!!data?.earlier?.length && <Box component="details" data-tq-earlier-run="" sx={{ px: 1.5, py: 0.4, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
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
      {!chat && <ThreadReading reading={data?.thread} mails={mails} variant="chat" />}
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {/* ALWAYS inside the pane, session or not: a session that arrives mid-turn (`started`) must not
            change the tree around the thread, or the answer streaming into it is remounted away
            ...and no sid on a card whose session is not live (`noTools`): its browser was asked for every 3 s under a stopped, saved
            or failed agent's Result, for as long as it stayed open (the agents walk, 2026-10-26) */}
        <SessionPane sid={(!noTools && session?.sid) || null} height="100%" yourTurn={waitsOnPage(asking)} idle={!busy}
          stack taskId={task.TaskId} held={viewActs} turn={turn} onHandBack={handBack} onDecided={decidedOnView}
          onView={viewShownIs} quiet={chat} need={needNow}>{thread}</SessionPane>
      </Box>
    </Box>
  );
}

export default GeneralWorkspace;
