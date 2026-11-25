import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { landingTurn } from "./landing.js";
import { createPortal } from "react-dom";
import { says, subState } from "./laneSays.js";
import {
  AssistantRuntimeProvider, ComposerPrimitive, ThreadPrimitive, useLocalRuntime,
} from "@assistant-ui/react";
import { Alert, Box, Button, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/ArrowUpward";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import api from "./api.js";
import { SETUP_CHANGED } from "./wrote.js";
import { liveUp, onLive, touches } from "./live.js";
import { REST_LOOK_MS, changes, coalesced, restLook } from "./visible.js";
import { aheadChat, heldChat, heldConversation } from "./taskDetail.js";
import { AttachChip, fileChips, fileState, usePromptImages, useSendWhenUp } from "./promptImages.jsx";
import { holdUnsent } from "./unsent.js";
import { howToOpen } from "./bugReportOpen.js";
import { baseName } from "./agentSteps.js";
import { AgentSteps, PermitCtx } from "./AgentStepRows.jsx";
import { chatSource, checkBackDue, waitingShown, eventsOf, turnSteps, hasParts, isPastCard, standing, heldAtEnd, AT_END, anchorOf, anchorShift, openAt, OPEN_HOLD, shrinkHeld, SHRINK_HOLD, turnParts, workCount, folds, ranUnder, foldLine, paintable, withMine, waitingChips, workingLine, waitingOn, askTurn, onYouTurn, askedFirst, runsOf, patchSteps, askOn, asksOff } from "./chatStream.js";
import { stepLabel } from "./agentSteps.js";
export { checkBackDue };
import { detailFor, ownDetail, useOwnDetail } from "./chatDetail.js";
import { useChatDefaults } from "./DetailSlider.jsx";
import { AnsweredPermission, PermissionCards } from "./AgentChannels.jsx";
import { Hunk } from "./DiffView.jsx";
// ...a file he sent, by its own name: the upload's stamp (server.prompt_file) is not his, and neither is the folder
const fileName = (p) => String(p).split(/[\\/]/).pop().replace(/^\d{8}-\d{6}-[0-9a-f]{6}-/, "");
import { shared } from "./singleFlight.js";
import WriteIcon from "@mui/icons-material/EditNoteRounded";
import ViewSpec, { PlanRow } from "./ViewSpec.jsx";
import { wantsAsk, withoutAsk } from "./newTask.js";
import { FULL_SX, useFullScreen } from "./fullScreen.js";
import { pickFor } from "./assistantProvider.js";
import { agentName, turnStamp } from "./agentWork.js";
import { RunClock, StopCtx, turnStart, when } from "./RunClock.jsx";
import { AGENT_TURN, MESSAGE } from "./kinds.js";
import { LinkPopups, LocalFiles, Md } from "./md.jsx";
import PublishedPages, { FileDialog } from "./PublishedPages.jsx";
import { Attachments } from "./Attachments.jsx";
import { placeShown } from "./shownPages.js";
import { carried, forTurn, outputRefs, outputRow, placeMade, shownOnce, turnFiles } from "./taskOutputs.js";
import TurnFiles from "./TurnFiles.jsx";
import CopyCorner from "./CopyCorner.jsx";
import { SessionPane, TerminalPane } from "./TerminalView.jsx";
import ThreadReading from "./ThreadReading.jsx";
import { askPlaceholder, heldOn, isSignin, isTurn, pageBars, pressable, waitsOnPage } from "./browserSplit.js";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import "./generalWorkspace.css";
import "./agentStepRows.css";
import { ModelSelect, TaskuaryMark } from "./ui.jsx";
import { label as btn } from "./buttons.js";
import { placeName } from "./words.js";
import { plural } from "./timeWords.js";
import ConnectAi from "./ConnectAi.jsx";
import ReviewDecision, { ActReview, MoreCardsCtx } from "./ReviewDecision.jsx";
import { askNote, heldActsLine, proposalFrom } from "./reviewProposal.js";
import BriefLine from "./BriefLine.jsx";
import { OneBox } from "./AgentSummary.jsx";
import HeldStart from "./HeldStart.jsx";
import { readingOf } from "./threadReading.js";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import TelegramIcon from "@mui/icons-material/Telegram";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import BoltIcon from "@mui/icons-material/Bolt";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import Artifact from "./Artifact.jsx";

const errText = (e) => e?.response?.data?.detail || e?.message || "The assistant could not respond.";
const textOf = (message) => (message?.content || []).filter((p) => p.type === "text").map((p) => p.text).join("\n").trim();


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

// IT IS A CHAT (the owner, 2026-11-05: "show the taskuary stuff on left. the inputs on right meaning little email logo like the rail ... that
// shows trigger says something emails came in from x and was sent to agent.. then as new one comes in another one on right side"): each mail that
// started or woke a turn is a prompt on the RIGHT - its channel's mark, who, when - with the answer it woke under it on the left. The owner's own
// reply sent outside Taskuary is no prompt: it stands on the left among the lines it answers (Arrived, 2026-11-08)
const CHANNEL_WORD = { email: "Email", whatsapp: "WhatsApp message", teams: "Teams message", slack: "Slack message", telegram: "Telegram message", sms: "Text" };
const ChannelMark = ({ channel }) => {
  const c = String(channel || "").toLowerCase();
  const Icon = c === "whatsapp" ? WhatsAppIcon : c === "telegram" ? TelegramIcon : c === "email" || !c ? MailOutlineIcon
    : ["report", "dashboard", "routine"].includes(c) ? AssessmentOutlinedIcon : ChatBubbleOutlineIcon;
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
// ...and a start nobody typed - a routine's run, a report's - names itself: "From the routine Weekly post drafts" (conversation.started_by)
const headOf = (x) => x.head ? [x.head] : x.own ? ["You", ON_WORD[String(x.channel || "").toLowerCase()] || "outside Taskuary"]
  : [`${CHANNEL_WORD[String(x.channel || "").toLowerCase()] || "Message"} from ${x.who || "someone"}`];
// the subject when it says something the words do not: not over a chat line (none), not the same as the line before's, not the words themselves
export const subjectOf = (x, prev) => { const sub = String(x?.subject || "").trim(), bare = (v) => String(v || "").replace(/^\s*((re|fw|fwd)\s*:\s*)+/i, "").trim().toLowerCase();
  return !sub || x.own || bare(sub) === bare(prev?.subject) || bare(sub) === bare(x.words) ? "" : sub; };
/* WHAT CAME IN READS IN PLACE (the owner, 2026-11-11: "you should be able to hit expand and read the whole email"): a few lines, and - only
   where they are cut - one toggle that opens the whole message where it stands, whatever channel it came on */
export const ArrivedWords = ({ words }) => {
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
    {/* ...a notice kept from the agent says so on itself, in one line (origin.QUIET_LINE, the owner 2026-11-25) */}
    {!!x.kept && <span className="tq-aui-arrived-kept" data-tq-arrived-kept="">{x.kept}</span>}
  </div>;
});
// a press's event line: its words without the closing stop, then the time - "You changed its workstream · 3:12 PM"
export const pressLine = (words, stamp) => [String(words || "").trim().replace(/\.$/, ""), stamp].filter(Boolean).join(" · ");
// what each answer published or showed, by the answer's id (the server's `after`): drawn under it, open - the agent chose it
const ShownCtx = React.createContext({});
const WorkCtx = React.createContext(null);
// THE PERMISSIONS WAITING ON HIM, ON THE ROWS OF THEIR CALLS (the owner, 2026-11-23: "just permissions to push something" in the row): each by
// the call it names (permissions.pending `call`), answered by the same one press its card had - a press that landed keeps its spin until the
// list reads it answered; one answered first elsewhere (409) just reads the list
const PermitProvider = ({ taskId, perms, onAnswered, children }) => {
  const [busy, setBusy] = useState({}), [err, setErr] = useState({});
  const byCall = useMemo(() => new Map((perms || []).filter((p) => p.call).map((p) => [p.call, p])), [perms]);
  const answer = async (p, kind) => {
    setBusy((b) => ({ ...b, [p.id]: kind })); setErr((x) => ({ ...x, [p.id]: "" }));
    try { await api.post(`/api/tasks/${taskId}/permission`, { id: p.id, option: kind }); onAnswered?.(); }
    catch (e) {
      if (e?.response?.status === 409) { onAnswered?.(); return; }
      setErr((x) => ({ ...x, [p.id]: e?.response?.data?.detail || e?.message || "That answer did not reach the agent" })); setBusy(({ [p.id]: _, ...b }) => b);
    }
  };
  return <PermitCtx.Provider value={{ byCall, answer, busy, err }}>{children}</PermitCtx.Provider>;
};
// a turn still running is ONE LINE, "Working on this…", its steps folded under it (the closeout-in-chat spec, 2026-11-04); a turn that
// ended in its summary keeps them folded above it. A turn with no summary - older ones, a CLI that wrote none, one that died - as ever
// (pendingTurn.live)
// ...and a fold the owner opened stays open: the server's live message is `live-<sid>-<trace revision>` - a new id at every step - and the pane
// itself mounts again when the owner comes back to the task. Kept by the turn, never by the message's id or the DOM
const OPEN_FOLDS = new Set();
const foldKey = (id) => String(id || "").replace(/^(live-.+)-\d+$/, "$1");
// HOW MUCH OF THE WORK IS DRAWN (chatDetail.js): "summary", "steps" or "everything" - the task's own, else its kind's default from Settings
const LevelCtx = React.createContext("steps");
// AN EDIT IS A ROW THAT OPENS ON ITS DIFF: "Edited budget.py (+12 −3)", the code with its line numbers under it
// ...AND A FILE IT WROTE STANDS OPEN ON WHAT IT WROTE, as a terminal shows it (the owner, 2026-11-15): where the agent saved something and
// never showed it, opening the turn's steps is enough to read it - nothing it wrote is a row to hunt through. In a chat; a coding turn's
// rows stay shut, there the list of edits is the thing read
const EditRow = ({ p }) => { const chat = React.useContext(ChatCtx); return (
  <details className="tq-aui-step tq-aui-step-edit tq-cc-edit" data-tq-edit={baseName(p.file)} {...(chat && p.wrote && p.hunks.length ? { open: true, "data-tq-wrote": "" } : {})}>
    <summary><WriteIcon aria-hidden className="tq-aui-step-icon" /><span>{p.summary}</span></summary>
    <div className="tq-cc-diff">{p.hunks.length ? p.hunks.map((h, i) => <Hunk key={i} h={h} path={p.file} />)
      : <div className="tq-dv-empty">Its log keeps no diff for this one.</div>}</div>
  </details>); };
// ...a fold the owner opened stays open across the live turn's new ids (OPEN_FOLDS)
// ...and what reads it beside the fold (the working line, ConvTurn) hears it open and shut as the fold does
const FOLD_HEARD = new Set();
const useFoldOpen = (k) => {
  const [open, setOpen] = useState(() => OPEN_FOLDS.has(k));
  useEffect(() => { const heard = () => setOpen(OPEN_FOLDS.has(k)); heard(); FOLD_HEARD.add(heard); return () => { FOLD_HEARD.delete(heard); }; }, [k]);
  return open;
};
const Fold = ({ k, label, quiet = false, force = false, children }) => {
  const open = useFoldOpen(k) || force;
  // ...FROM HIS CLICK, in the render it causes (the judges' recording, 2026-11-18): heard from the native toggle, which fires a task later,
  // the working line on ACP followed the opened fold 75-90 ms late - "Editing budget.py" as a row and on the line under it. The click sets it;
  // the toggle only agrees (a fold opened another way)
  const set = (o) => { if (o === OPEN_FOLDS.has(k)) return; if (o) OPEN_FOLDS.add(k); else OPEN_FOLDS.delete(k); FOLD_HEARD.forEach((f) => f()); };
  return <details className="tq-aui-working-fold" data-tq-steps-fold={quiet ? "summary" : ""} open={open} onToggle={(e) => set(e.currentTarget.open)}>
    {/* ...its count a real button, named and pressable by keyboard (the UX walk, 2026-11-18: a click on "6 steps" found no button) */}
    <summary onClick={(e) => { e.preventDefault(); set(!OPEN_FOLDS.has(k)); }}><button type="button" className="tq-aui-fold-btn" aria-expanded={open}>{label}</button></summary>{children}</details>;
};
// ONE RULE FOR EVERY FOLD OF A TURN'S WORK: it is drawn round steps of work. One with none in it - only Taskuary's own notes, as a turn the app
// started holds before its first step - read "Along the way ▸" over nothing he could see (the overnight walk, 2026-11-11): its notes stand open
// ...and one holding a call that waits on his answer stands open while it waits: the ask is on that call's row (AgentStepRows PermitCtx)
const WorkFold = ({ k, quiet = false, parts, draw }) => { const n = workCount(parts), byCall = React.useContext(PermitCtx)?.byCall;
  const asked = parts.some((p) => (p.steps || []).some((st) => askOn(st, byCall)));
  return n ? <Fold k={k} quiet={quiet} force={asked} label={foldLine(parts)}>{parts.map((p, i) => draw(p, i, "everything"))}</Fold>
    : <>{parts.filter((p) => p.type !== "said").map((p, i) => draw(p, i, "everything"))}</>; };
const TurnWorkView = ({ data, now, k }) => {
  const at = React.useContext(WorkCtx);
  const outs = React.useContext(OutputsCtx), key = foldKey(k), level = levelOf(data?.level, React.useContext(LevelCtx)), chat = React.useContext(ChatCtx);
  // ...AND A TURN THAT ENDED HAS NOTHING STILL AT WORK (the owner, 2026-11-05: a step kept its spinner under the answer): a call that never got
  // its result before the answer was filed is drawn done, never circling. IN A CHAT A STEP IS NEVER "FAILED" (the owner, 2026-11-05: "it's just a
  // internal thought failure, for the user the task is getting done. failure means nothing") - a TURN that failed says so in its own words
  const calm = (st) => (!now && st.status === "running" ? { ...st, status: "done", alongside: false }
    : chat && (st.status === "error" || st.status === "recovered") ? { ...st, status: "done" } : st);
  // ...AND A TRY THE AGENT MADE GOOD IS FOLDED INTO THE TRY THAT WORKED (the real-Claude walk, 2026-11-19: a Write refused for a file not read
  // yet, then made, stood twice - its error the agent's to read, the owner's only the step that worked)
  const parts = (data?.parts || (data?.steps ? [{ type: "work", id: "p0", steps: data.steps }] : []))
    .map((p) => (p.type === "work" ? { ...p, steps: p.steps.filter((st) => !(chat && st.status === "recovered")).map(calm) } : p))
    .filter((p) => p.type !== "work" || p.steps.length);
  // ...where nothing sums a turn up (the dock), its trail as ever: one line a step, its edits among them
  if (!at) return <AgentSteps data={{ steps: parts.flatMap((p) => (p.type === "work" ? p.steps : p.type === "said" ? [{ id: p.id, kind: "said", summary: p.text }]
    : p.type === "edit" ? [{ id: p.id, kind: "edit", summary: p.summary, status: "done" }] : [])) }} />;
  const draw = (p, i, lvl) => p.type === "said" ? <Md key={p.id} text={p.text} /> : p.type === "edit" ? <EditRow key={p.id} p={p} />
    : p.type === "plan" ? <PlanRow key={p.id} p={p} />
    : p.type === "view" ? <ViewSpec key={p.id} spec={p.spec} taskId={outs?.tid} />
    // ...a file the agent showed (show `files`) is drawn by its kept copy, placed in its turn by the server for both chats (ShownCtx), never twice
    : p.type === "files" ? null
    : lvl === "everything" ? <AgentSteps key={p.id} data={{ steps: p.steps }} />
    : <WorkFold key={p.id} k={`${key}:${p.id}`} parts={[p]} draw={draw} />;
  // ONE LAYOUT, AT WORK AND FILED (the owner, 2026-11-23: "the live layout IS the finished layout" - words stay where they were said): the level
  // decides from the turn's first row and never again. SUMMARY: what it said and showed where it said it, each run of work between them behind
  // its own quiet "n steps" line that climbs as it works (the owner, 2026-11-17) and opens on every step at a press - keyed by its first part,
  // so the turn's end moves nothing. STEPS and EVERYTHING: every row as it comes
  if (level === "summary") return <>{runsOf(parts).map((r) => (r.fold ? <WorkFold key={r.id} k={`${key}:${r.id}`} quiet parts={r.parts} draw={draw} />
    : r.parts.map((p, i) => draw(p, i, "everything"))))}</>;
  return <>{parts.map((p, i) => draw(p, i, level))}</>;
};
// the level a turn is drawn at: its own once the server has applied it (chatlog.detailed), else the chat's - a turn at work reads the chat's
const levelOf = (own, given) => (own && own !== "live" ? own : given);




// WHAT THE AGENT ASKED (the UI audit's W6): the question in its own words, and a press for each answer it offered - its question tool's,
// an on-screen chooser's, or the choices it gave ask_owner (walk 13: written as prose, nothing to press) - plus Taskuary's own Signed in and Done. ONE BOX TYPES AN ANSWER (the owner, 2026-11-03: "i hate this
// double ui. we don't need question box if we have way to answer on the bottom"): the card's own field and Answer button went - what is
// typed in the composer while a question is open is its answer (AssistantThread's answerTyped). `onAnswer(text)` delivers either - a
// reply in this conversation, or the worker's own answer road - and throws with the reason when it could not.
// A SIGN-IN it waits on (request id `signin:<site>`, signin.py) is NO CARD (the owner, 2026-11-03: "remove that stupid box again as we did
// with the questions ... just have the question and link to fill it out securely"): the question as a line of the conversation, and a
// link to the one-time fill page (Taskuary types it, the agent never sees it). Signing in on the page beside it needs no press: Taskuary
// sees the page go past the sign-in (signin.watch), and "done" typed in the box below says so too.
export function AgentAsks({ asking, name, onAnswer, taskId }) {
  const [going, setGoing] = useState(false), [err, setErr] = useState("");
  const site = isSignin(asking) ? asking.site || "the site" : "";
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
// ...and one never read here draws the list that was asked for ahead with its task (taskDetail.prefetchTask: the row Next brings, a rail row
// under the pointer) on its first frame - the read on mount still follows, so what is held is only ever the first paint
const LISTS = new Map(), READS = new Map();      // READS: the read of each task's list on its way (singleFlight.shared)
// ...WHICHEVER WAS ASKED LAST (chatStream.newerList): the list this view last read, or the one read ahead as he came back
const listOf = (tid) => { const l = paintable(LISTS.get(tid), heldConversation(tid)); if (l) LISTS.set(tid, l); return l; };
// ...and what the chat stands on beside its list - the agent's state, its picks, what it holds (`/assistant`) - by the same rule: as last
// read here, else as asked ahead with the task; the read on mount follows and is the newest word
const CHATS = new Map();
const chatOf = (tid) => { if (!CHATS.has(tid)) { const h = heldChat(tid); if (h) CHATS.set(tid, h); } return CHATS.get(tid) || null; };
export function useConversation(tid, on) {
  const [list, setList] = useState(() => listOf(tid)), rev = useRef(LISTS.get(tid)?.rev || "");
  // ...READS LAND IN THE ORDER THEY WERE ASKED (the recorded walk, 2026-11-11: on a loaded machine an older read came back after a newer one -
  // his line vanished, the chat read "at rest" over a turn at work, and his next line was drawn as heard): one that a later read overtook is dropped
  const asked = useRef(0), shown = useRef(0);
  // ...ONE READ OF THE TASK'S LIST AT A TIME, whichever view or listener asks (singleFlight.shared): a read on its way is joined, never doubled
  const load = useCallback(() => { const n = ++asked.current, at = Date.now(); return (on ? shared(READS, tid, () => api.get(`/api/tasks/${tid}/conversation`, { params: { rev: rev.current, level: ownDetail(tid) || "" } })).then(({ data: d }) => {
    if (n < shown.current) return false;
    shown.current = n;
    if (d?.same && LISTS.get(tid)) LISTS.get(tid)._at = at;
    // ...a read another view asked that found the list unchanged: this view draws the list that view holds, where it is newer than its own
    if (d?.same && LISTS.get(tid)?.rev === d.rev) { const l = LISTS.get(tid); rev.current = l.rev; setList((cur) => (cur?.rev === l.rev ? cur : l)); }
    if (!d || d.same) return false;
    // ...nor a read asked before the one this view holds (one read ahead as he came back, landed first)
    if ((LISTS.get(tid)?._at || 0) > at) return false;
    d._at = at;
    // ...AND A CHAT THAT HAS DRAWN NEVER DRAWS EMPTY (recorded 2026-11-12 on the ACP sign-in walk: two seconds after the hand-back the whole chat
    // stood empty for a second, his ask and his press gone, then came back): a read with nothing in it over a list that has something is no
    // newer word on the conversation - nothing he typed or was told is ever taken back - and is not drawn
    if (!(d.items || []).length && (LISTS.get(tid)?.items || []).length) return false;
    rev.current = d.rev; LISTS.set(tid, d); setList(d); return true;
  }).catch(() => false) : Promise.resolve(false)); }, [tid, on]);
  useEffect(() => { const l = listOf(tid); rev.current = l?.rev || ""; setList(l); load(); }, [load]);   // eslint-disable-line react-hooks/exhaustive-deps
  const going = !!list?.working;
  // ...a turn at work is read as it moves: each step it records is pushed (run-tail - general.GeneralSession._moved, a pty's output, an ACP
  // step), read at most every 600 ms. At rest the server's own poke (task-changed) brings what is new. A slow look backs both up - every
  // tick while the socket is down; under it every 3 s at work and 30 s at rest (restLook: not every write a chat shows pokes - a comment
  // does not). Reading every 600 ms at work and 5 s at rest was ~100 and 12 builds a minute of the list (stress round, 2026-11-18)
  // ...AND THE ROWS IT PUSHED AS IT WROTE THEM ARE PATCHED IN AT ONCE (the owner, 2026-11-23: words stream into their row, Zed- and Obsidian-
  // style): each run-tail's rows (chatlog.pushed) go into the list in place, by their own ids, once per animation frame - never a jump each
  // 600 ms read; the read still follows, and finds the same rows
  const queued = useRef([]), frame = useRef(0);
  useEffect(() => () => { if (frame.current) cancelAnimationFrame(frame.current); }, []);
  const patch = useCallback((steps) => {
    queued.current.push(...steps);
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      const q = queued.current; queued.current = []; frame.current = 0;
      setList((cur) => { const next = patchSteps(cur, q, tid); if (next !== cur) LISTS.set(tid, next); return next; });
    });
  }, [tid]);
  useEffect(() => {
    if (!on) return undefined;
    let last = Date.now();
    const look = () => { last = Date.now(); return load(); };
    const [wake, stop] = coalesced(look, 600);
    const off = onLive("run-tail", (ev) => { if (!touches(ev, tid)) return; if (ev.steps?.length) patch(ev.steps); wake(); });
    const t = setInterval(() => { if (restLook({ socket: liveUp(), last, now: Date.now(), every: going ? 3000 : REST_LOOK_MS })) look(); }, going ? 600 : 5000);
    return () => { clearInterval(t); off(); stop(); };
  }, [on, going, load, tid, patch]);
  useEffect(() => (on ? onLive("task-changed", (ev) => { if (touches(ev, tid)) load(); }) : undefined), [on, tid, load]);
  // ...HOW MUCH OF THE WORK IT SHOWS IS THE SERVER'S TO APPLY (chatlog.detailed, the one place): the chat's own choice changed is read again
  useEffect(() => { const f = (e) => { if (String(e.detail?.tid) === String(tid)) load(); }; window.addEventListener("tq-chat-detail", f);
    return () => window.removeEventListener("tq-chat-detail", f); }, [tid, load]);
  return { list, load };
}
// A TURN'S HEAD SAYS ONE TIME, SET ONCE (design round 5, I3): when it began in the chat (the list's `at`, conversation.dated) - at work and done
// alike. It read its start while it worked and its END once done, and a turn begun at 4:57 was re-dated 5:12 under the owner's eyes
// ...a turn's time as the log keeps it: a stamp, or the epoch seconds a row put with no stamp of its own carries (walk 5: a follow-up turn
// showed no time - its `at` was 1795135... and read as no date), else when it began
const stampOf = (v) => { const d = typeof v === "number" ? new Date(v * 1000) : v ? new Date(String(v).replace(" ", "T")) : null; return d && !Number.isNaN(+d) ? d : null; };
export const turnAt = (t) => stampOf(t?.at) || stampOf(t?.started);
// ...and how long it ran: all of it, every turn drawn under this head (chatStream.ranUnder)
const TurnTime = ({ t, secs }) => {
  const at = turnAt(t);
  if (!at) return null;
  const ran = secs > 0 ? turnStamp({ start: at, end: +at + secs * 1000 }) : "";
  return <span data-tq-ran="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>· {when(at)}{ran ? ` · ${ran}` : ""}</span>;
};
const NONE = new Set();
// `later`: a turn after the chat's first - its agent starting again is the work going on, never "waiting for the agent" (workingLine)
const ConvTurn = ({ t, more, ran = 0, cards, name, ask = null, later = false, owes = false, newest = false, skip = NONE }) => {
  const live = t.state === "working" || t.state === "starting";
  const parts = useMemo(() => turnParts(eventsOf(turnSteps(t), live), { live }), [t.steps, t.fail, live]);
  const key = t.answer || t.id, at = useTurnOutputs(key), shown = React.useContext(ShownCtx)[key];
  const sum = t.summary, words = t.text || (sum ? [sum.about, sum.did].map((x) => String(x || "").trim()).filter(Boolean).join("\n\n") : "");
  const made = at ? turnFiles({ listed: at.listed, id: key, words, did: sum?.did, tid: at.tid, skip }) : [];
  const names = new Set(made.map((f) => f.name));
  const rest = shownOnce(at ? outputRefs(words, at.tid, at.listed).files : [], shown).rest.filter((p) => !names.has(p.name) && !skip.has(p.name));
  const quiet = !live && !hasParts(parts) && !words && !t.fail && !cards?.length && !made.length && !rest.length && !ask;
  // ...and never under the turn's own open question (the audit, 2026-11-15: "What is your plate number?" in its words, then "For you to do:
  // Tell me your plate number"): what it asks him IS what is left to him, said once. THE TURN'S OWN, KEPT (design round 5, I3): the list says
  // which turns say it (`on_you`, conversation.left_on_him), settled once - it never leaves a turn for the next one
  // ...AND WHAT IS LEFT ON HIM IS ITS BUTTON OR NOTHING (the owner, 2026-11-22: "For you to do:" prose goes) - the card, the bar or his box says it
  const again = React.useContext(AgainCtx), stopTries = React.useContext(StopTriesCtx);
  // ...WHILE THE CLI COMPACTS ITS CONTEXT the turn at work says so (the owner, 2026-11-10: "show compacting like claude code does"): its newest
  // step is the compaction, not yet over
  const compacting = live && ((x) => x?.k === "compact" && !!x.status && !["completed", "failed", "cancelled"].includes(x.status))((t.steps || []).at(-1));
  // ...`opening`: its agent's process really is starting (conversation.items) - said on any turn then, and only then
  // ...naming what no row in sight says: its rows stand open at a level that lists them, inside the newest fold he opened, and on the dock's
  // trail (no WorkCtx) always. What it is writing is its own row, streamed into it - never said again on this line
  const lastFold = runsOf(parts).findLast((r) => r.fold), level = levelOf(t.level, React.useContext(LevelCtx));
  const folded = useFoldOpen(lastFold ? `${foldKey(t.id)}:${lastFold.id}` : ""), work = React.useContext(WorkCtx), open = folded || !work || level !== "summary";
  const doing = live ? workingLine(parts, stepLabel, { starting: t.state === "starting" || !!t.opening, later: later && !t.opening, ask: React.useContext(WaitOnCtx), thinking: t.thinking || "", open }) : "";
  // ...and of its filed answer only what its streamed words did not already say (chatlog.read `tail`): nothing said twice, nothing moved
  const said = t.text && t.tail != null ? t.tail : words;
  if (quiet) return null;
  return <div className={`tq-aui-message tq-aui-agent${words && !live ? " tq-copy-host" : ""}${more ? " tq-aui-agent-more" : ""}`} data-tq-item={t.id} data-tq-chat-line={key} data-tq-turn={t.state}>
    {!!words && !live && <CopyCorner text={words} label="Copy this answer" />}
    {!more && <div className="tq-aui-role">{name}{live ? <RunClock start={turnStart(t)} at={turnAt(t)} /> : <TurnTime t={t} secs={ran} />}</div>}
    <div className="tq-aui-agent-body">
      <TurnWorkView data={{ parts, level: t.level }} now={live} k={t.id} />
      {/* ...WHAT IT MADE, WHERE IT STOOD WHILE IT WORKED (the API walk, 2026-11-20): under its work, above its words - an answer that comes at the
          turn's end was drawn over a picture already on screen, and the picture jumped down */}
      {!!rest.length && <PublishedPages pages={rest} open />}
      {!!made.length && <TurnFiles files={made} />}
      {!!said && <SaidText text={said} mid={key} />}
      {/* ...A TURN THAT COULD NOT FINISH, WORTH ANOTHER TRY (its summary's `retry`): one button, never "send any message on this task to try
          again" (the 2026-11-18 walks) - pressed, it is his line "Try again." and the agent goes on */}
      {owes && !live && sum?.retry && !!again && <div style={{ marginTop: 8 }}><AgainButton again={again} /></div>}
      {/* ...and THE NEWEST TURN THAT FAILED carries the same one button (the API walk, 2026-11-18: a provider's outage left "⚠ ... 429" and nothing
          to press) - each try that failed keeps its own dated line (general.say_failure); only the newest carries the button */}
      {t.state === "failed" && !!t.fail && <div className="tq-aui-note tq-aui-note-error" role="alert" data-tq-turn-failed="">⚠ {t.fail}
        {/* ...and while Taskuary tries it again by itself, its Cancel stands beside it - ONE line and one set of moves for the try, never a second
            "I couldn't start yet" line under it (the judge's look, 2026-11-20) */}
        {newest && !!again && <div style={{ marginTop: 8, display: "flex", gap: 8 }}><AgainButton again={again} />
          {!!stopTries && <button type="button" className="tq-chip" data-tq-turn-stop-tries="" onClick={stopTries}>Cancel</button>}</div>}</div>}
      {/* ...what this turn asked him, where it asked it (the list's `asking.turn`): above its card, never at the chat's foot */}
      {ask}
      {!!cards?.length && <div data-tq-turn-cards="">{cards}</div>}
      {/* ...what it left on him, at its FOOT, under its cards (design round 5, I3): said once they are pressed, it stood up over them - a line
          drawn in the middle of what was already there */}
      {/* ...and the dots say what is happening, or what we wait for, on every level: one quiet line that keeps its place (workingLine) -
          LAST in the turn, under what it has made and asked so far: a chat's newest word is at its foot (the owner, 2026-11-18) */}
      {live && <div className="tq-aui-thinking" role="status" aria-label="The agent is at work" data-tq-working="" {...(t.state === "starting" ? { "data-tq-starting-line": "" } : {})}><i /><i /><i />{compacting
        ? <span data-tq-compacting="" style={{ marginLeft: 8, fontSize: 12.5 }}>Compacting…</span>
        : doing ? <span className="tq-aui-working-line" data-tq-working-line="" title={doing}>{doing}</span> : null}</div>}
    </div></div>;
};
const RetryCtx = React.createContext(null);
const AgainCtx = React.createContext(null);
// the press, what it is doing, and why it did not go - on the button he pressed
const AgainButton = ({ again }) => <><button type="button" className="tq-chip primary" data-tq-turn-retry="" disabled={!!again.going} onClick={again.go}>
  {again.going ? "Trying again…" : btn("try_again")}</button>{again.err && <span data-tq-line-failed="" style={{ marginLeft: 8 }}>{again.err}</span>}</>;
const StopTriesCtx = React.createContext(null);
// the line a Try again press puts in his voice - the agent reads it as the go-ahead to try what failed once more
const WaitOnCtx = React.createContext("");
// ...AN ASK NOBODY TYPED (madeTask: the prompt a report, a dashboard or an Advisor look ran on) heads as what asked for it, marked automated, its
// whole prompt the line - its first lines, the rest one press away, as any long one (the owner, 2026-11-24)
const ConvLine = ({ x, more }) => {
  const stamp = x.at ? when(x.at instanceof Date ? x.at : String(x.at)) : "", retry = React.useContext(RetryCtx);
  return <div className={`tq-aui-message tq-aui-user${more ? " tq-aui-user-more" : ""}`} data-tq-item={x.id} data-tq-chat-line={x.id} data-tq-auto-line={x.auto ? "" : undefined}>
    {!more && <div className="tq-aui-user-head">{x.auto ? <><BoltIcon aria-hidden sx={{ fontSize: 13, verticalAlign: "-2px", mr: 0.4 }} />{x.auto}</>
      : <><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />You{stamp ? ` · ${stamp}` : ""}</>}</div>}
    {(!x.auto || !!x.text) && <div className="tq-aui-user-bubble" dir="auto">{(!!x.came || !!x.files?.length) && <div data-tq-line-came="" style={{ marginBottom: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
      {!!x.came && <AttachChip name={x.came} title={`Sent with ${x.came}`} />}
      {/* ...AND EVERY FILE HE SENT WITH IT (the owner, 2026-11-17: "the prompt box should show attachment of whatever goes into prompt"): a pill each,
          as on the box he typed it in - from the press (his own line, drawn at once) to the heard line (conversation's `files`) */}
      {(x.files || []).map((f) => <AttachChip key={f} name={fileName(f)} title={`Sent with ${fileName(f)}`} data-tq-line-file="" />)}</div>}{x.auto ? <ArrivedWords words={x.text} /> : x.text}</div>}
    {/* ...a send that failed: ONE plain line under his words, with the way past it - never glued into them */}
    {!!x.err && <div className="tq-aui-note tq-aui-note-error" role="alert" data-tq-line-failed="">{x.err}{retry && <> · <button type="button" className="tq-aui-arrived-more-btn"
      data-tq-try-again="" onClick={() => retry(x)}>{btn("try_again")}</button></>}</div>}</div>;
};
/* A DRAFT HE SAID NO TO says what he pressed, with its words, in its own place (answered cards stay greyed saying what was pressed) */
const NotSent = ({ c }) => <Artifact className="tq-conv-past" data-tq-past-card={c.status} data-tq-past-review={c.review} role="note">
  {/* ...a letter is not sent; a step he turned down (a read of a folder, a push) is a no, never a send (walk 5: "Not sent - you said don't send ·
      read the folder Users") */}
  <div className="tq-conv-past-head">{c.what === "action" ? "You said no to this" : "Not sent - you said don't send"}</div>
  {!!c.was?.text && <div className="tq-conv-past-words" dir="auto">{c.was.text}</div>}</Artifact>;
/* A CARD THE CHAT MOVED PAST IS THE CARD IT WAS, ITS BUTTONS GREYED (the owner, 2026-11-18: "don't need reason. just keep it with buttons but
   the buttons grayed out once you moved on"): rewritten by a later turn, set aside as he wrote again, or taken back by its agent - drawn in its
   own place from the words it had then (`was`), never moved, never gone, and no line saying why */
const wasCard = (c, rv) => <ReviewDecision key={c.id} past review={c.what !== "action" ? { ...(rv || { ReviewId: c.review, Kind: c.what }), DraftText: c.was.text }
  : rv || { ReviewId: c.review, Kind: "action", DraftText: JSON.stringify({ what: c.was.text }) }} />;
/* `items`: the server's list, with this page's own lines the server has not answered for yet (`mine`) already merged in by their names.
   `nodes`: the cards the page draws, by the review each is of ([{key, rid, node}]); `next`: the reply that waits, at the card it is. */
function Conversation({ items, nodes = [], posts = [], reviews = [], next = null, landing: landed = null, landAt, name, tid, onChanged, ask = null, askAt = "", queue = null }) {
  // ONE CARD AT A TIME (cardqueue.py): what waits behind the card that stands is drawn nowhere - the landing question too - and the card that
  // stands says, over itself, how many come and which is next ("1 of 2 · next: the email to Erin")
  const held = new Set(queue?.held || []), live = new Set(queue?.live || []), landing = held.has("land") ? null : landed;
  const qLine = () => (queue?.line && !used.has("queue") && used.add("queue") ? [<div key="queue" className="tq-aui-hint" data-tq-card-queue="" role="note">{queue.line}</div>] : []);
  // THE WORK'S CARD IS PART OF THE AGENT TURN THAT DID IT, or not drawn at all (the owner, 2026-11-13: "stop putting worked on master at the
  // bottom ... it's part of the agent turn or doesn't belong at all"): the turn its newest change came in (landing.landingTurn); until the card
  // has read its state it is mounted hidden, so it can say when
  const landIn = landAt ? landingTurn(items.filter((x) => x.kind === "turn").map((x) => ({ role: "assistant", id: x.id, createdAt: x.at })), landAt) : null;
  // ...every review the list places, in whatever state: a card is drawn where the list has it and nowhere else
  const used = new Set(), listed = new Set(items.flatMap((x) => (x.kind === "card" ? [x] : x.kind === "turn" ? x.cards || [] : [])).map((c) => c.review));
  const stands = standing(items), owes = onYouTurn(items, { askAt, landAt: landIn });
  // ...and what a card it draws carries - a post's picture, an email's attachment - is that card's alone, never a file of a turn again (carried)
  const owned = carried([...posts, ...reviews].filter((r) => listed.has(r.ReviewId)));
  const rv = (id) => reviews.find((r) => r.ReviewId === id);
  const draw = (cs) => (cs || []).flatMap((c) => {
    // ...a draft no longer to press carries what it said (`was`); one he said no to says so. Either takes its review's node with it only where
    // the review has no card of its own left in the list (chatStream.standing) - an earlier version is drawn from its own words beside it
    const past = isPastCard(c) || c.status === "passed", claim = () => nodes.forEach((n) => { if (n.rid === c.review) used.add(n.key); });
    if (isPastCard(c) && c.status === "rejected") { if (!stands.has(c.review)) claim(); return [<NotSent key={c.id} c={c} />]; }
    if (isPastCard(c) && stands.has(c.review)) return [wasCard(c, rv(c.review))];
    if (held.has(c.review) && !past) return [];
    const got = nodes.filter((n) => n.rid === c.review && !used.has(n.key)), post = posts.find((p) => p.ReviewId === c.review);
    got.forEach((n) => used.add(n.key));
    // ...a card moved past is its own card with `past`: greyed in its place, nothing to press
    if (past && !got.length && !post) return c.was ? [wasCard(c, rv(c.review))] : [];
    // ...ONE REVIEW IS ONE CARD: a post or a tracker comment an earlier build set aside has its settled card among the nodes, and was drawn
    // again under it as the act's own card reading "Not posted · dismissed" (the card round, 2026-11-12)
    const out = [...got.map((n) => <React.Fragment key={n.key}>{past ? React.cloneElement(n.node, { past: true }) : n.node}</React.Fragment>),
      ...(post && !got.length && !used.has(`post:${c.review}`) && used.add(`post:${c.review}`) ? [<ActReview key={`post:${c.review}`} row={post} tid={tid} onChanged={onChanged} past={past} />] : [])];
    return out.length && live.has(c.review) && c.status === "pending" ? [...qLine(), ...out] : out;
  });
  // A TURN'S CARDS, ITS LAST THING: what the log placed in it - a reply, a letter, an act - then the work's card
  const cardsOf = (x) => [...draw(x.cards),
    ...(x.id === landIn ? [...(live.has("land") ? qLine() : []), <React.Fragment key="landing">{landing}</React.Fragment>] : [])];
  const rows = items.map((x, i) => {
    const prev = items[i - 1];
    // ...A TURN AT WORK ALWAYS DRAWS ITS HEAD (2026-11-17: one that carried on after the agent's first message folded into the turn above - no
    // clock, no Stop x, and the head over it read that turn's "ran 27s"): only a finished turn after a turn folds into it
    // ...AND NEVER INTO ONE THAT FAILED (the Continue round, 2026-11-18): Try again's turn stands under the failure it is past, and folded, its head
    // went the moment it answered - its words left under the failure's head, with no time of their own
    if (x.kind === "turn") return <ConvTurn key={x.id} t={x} more={folds(prev, x)} ran={ranUnder(items, i)} name={name} ask={x.id === askAt ? ask : null}
      cards={cardsOf(x)} skip={owned} owes={x.id === owes} later={items.slice(0, i).some((y) => y.kind === "turn")} newest={!items.slice(i + 1).some((y) => y.kind === "turn")} />;
    if (x.kind === "line") return <ConvLine key={x.id} x={x} more={prev?.kind === "line"} />;
    if (x.kind === "arrival") return <div key={x.id} className="tq-aui-message tq-aui-brief" data-tq-item={x.id}><Arrived mail={[x]} prev={prev?.kind === "arrival" ? prev : null} /></div>;
    if (x.kind === "card") { const got = draw([x]); return got.length ? <div key={x.id} className="tq-aui-message tq-aui-agent" data-tq-item={x.id} data-tq-row-cards=""><div className="tq-aui-agent-body">{got}</div></div> : null; }
    // ...his answer to a permission request is its card, greyed where it stood - never a line in its place (2026-11-17)
    if (x.kind === "press" && x.perm) return <div key={x.id} className="tq-aui-message tq-aui-agent" data-tq-item={x.id}><div className="tq-aui-agent-body">
      <AnsweredPermission perm={x.perm} at={x.at ? when(String(x.at)) : ""} /></div></div>;
    return <div key={x.id} className={`tq-aui-message tq-aui-press${prev && (prev.kind === "press" || prev.kind === "note") ? " tq-aui-press-more" : ""}`} data-tq-item={x.id} data-tq-chat-press="">
      <div className="tq-aui-press-line">{pressLine(x.text, x.at ? when(String(x.at)) : "")}</div></div>;
  });
  return <MoreCardsCtx.Provider value={held.size > 0}>{rows}
    {/* ...EVERY CARD IS A ROW THE LOG PLACED (chatlog.advance - one road): under everything only the page's own block, a hand-off or a
        write-up he opened, never a card of the line */}
    {!!next && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 } }}>{next}</Box>}
    {!landIn && landing && <div hidden>{landing}</div>}</MoreCardsCtx.Provider>;
}
/* WHAT WAITS FOR THE AGENT, BY THE BOX: accepted, not yet handed over - never in the conversation until it is (the heard rule).
   ...A ROW IS NOT MARKED [data-tq-held] (seen 2026-11-11: with lines waiting, the task's card stood 8 px under the canvas's head): that name
   is the place a link asked the canvas to hold in the middle of its view (appLinks.focusPlace, AssistantView keepTable) - one waiting line
   and the canvas scrolled the whole task to centre it, as far as it would go */
/* WHAT WAITS FOR THE AGENT, OVER THE BOX (the owner, 2026-11-12, as Codex shows a queued message): HIS lines typed while a turn works, one
   slim row each on his side - the newest two, "+N more" over them - with Send now where the turn takes words mid-turn (the list's `now`) and a
   trash that takes it back. What came in waits as a count on its sender's chip (waitingChips), never a row here. Each in one place: here
   until the agent hears it, then in the chat where it heard it. */
const PendingStrip = ({ items, now = false, later = "", onRetry = null, onDrop = null, onNow = null }) => {
  const rows = items.filter((x) => x.kind !== "arrival"), shown = waitingShown(rows, 2), more = rows.length - shown.length;
  return !rows.length ? null : <div className="tq-conv-pending" data-tq-pending="" role="status" aria-label="Waiting for the agent">
  {/* ...and where this agent's road takes no words mid-turn, it says so once, over his lines (the list's `later`, conversation.LATER) */}
  {!!later && <div className="tq-conv-pending-more" data-tq-pending-later="">{later}</div>}
  {more > 0 && <div className="tq-conv-pending-more" data-tq-pending-more="" data-tq-pending-ids={rows.filter((x) => !shown.includes(x)).map((x) => x.id).join(" ")}>+{more} more</div>}
  {shown.map((x) => <div key={x.id} className="tq-conv-pending-row" data-tq-pending-item={x.id} dir="auto" title={[x.text || x.words, ...(x.files || []).map(fileName)].filter(Boolean).join(" · ")}>
    {/* ...WITH A PILL FOR EACH FILE HE SENT WITH IT, as his heard line has (the attach stress round, 2026-11-18): waiting here it drew its words
        alone, and a picture sent alone was an empty row with a trash can */}
    {(x.files || []).map((f) => <AttachChip key={f} name={fileName(f)} title={`Sent with ${fileName(f)}`} data-tq-line-file="" />)}
    <span className="tq-conv-pending-words">{x.text || x.words || ""}</span>
    {x.kind === "line" && now && onNow && <button type="button" className="tq-conv-pending-act" data-tq-send-now="" onClick={() => onNow(x)}>Send now</button>}
    {x.kind === "line" && onDrop && <button type="button" className="tq-conv-pending-act" aria-label="Take it back" title="Take it back - it never reaches the agent"
      data-tq-drop-line="" onClick={() => onDrop(x)}><DeleteOutlineIcon sx={{ fontSize: 15 }} /></button>}</div>)}
  {/* ...a send that failed says so in its own plain line, never inside his words (the owner's live task, 2026-11-12) */}
  {shown.filter((x) => x.err).map((x) => <div key={`e-${x.id}`} className="tq-aui-note tq-aui-note-error" role="alert" data-tq-line-failed="">{x.err}{onRetry && <> · <button type="button"
    className="tq-aui-arrived-more-btn" data-tq-try-again="" onClick={() => onRetry(x)}>{btn("try_again")}</button></>}</div>)}
</div>; };

function AssistantThread({ task, onAsked, onStop, selectionRef, attachmentsRef, onSent, onClearAttachments, onAttach, onAttachBack, pics = null,
  prompt, onPromptUsed, name = "Taskuary", asking, onAnswer, drafts = [], acts = [], onDraftDecided, noComposer = false,
  chat = false, reading = null, came = null, noAi = null, closedLine = "", road = null, cards = null, landing = null, turnCards = null, queued = null, stopTries = null, hold = null, trustOnRow = false, idle = "", onTrusted, hint = "", placeholder = "",
  empty = "", seed = null, list = null, reloadList = null, start = null }) {
  // A TASK'S CHAT DRAWS THE SERVER'S LIST (Conversation) - whatever agent works it; this holds the box, what it sent, and the view's end
  const turnName = React.useContext(AgentNameCtx);
  const [mine, setMine] = useState([]), merged = useMemo(() => withMine(list, mine), [list, mine]);
  // ...let go of a line he sent only once the server's copy carries its words (chatStream.withMine `said`): placed before it is filed, it has none
  useEffect(() => { if (!list) return; const known = new Set([...list.items, ...list.pending].filter((x) => x.kind !== "line" || String(x.text || "").trim() || (x.files || []).length).map((x) => x.id));
    setMine((m) => (m.some((l) => known.has(l.id) && !l.err) ? m.filter((l) => !known.has(l.id) || l.err) : m)); }, [list]);
  const stick = useRef(true), opening = useRef(false), inner = useRef(null), viewport = useRef(null), listNow = useRef(list); listNow.current = list;
  const nextAt = React.useContext(WorkCtx);
  // ...the box is assistant-ui's composer (its text, its Enter, its files): the runtime under it answers nothing - a line goes by sendLine
  const runtime = useLocalRuntime(useMemo(() => ({ async *run() { /* the server's list is the conversation */ } }), []));
  /* ONE ROAD FOR A LINE HE SENDS, whatever the agent is and whatever it is doing: named here, drawn at once, posted with that name - the
     server's list answers for it from then on (general.take_line: heard now by an agent at rest, kept for one at work) */
  // ...THE BOX'S FILES GO WITH THE LINE TYPED IN IT, ONCE (the Hydrogen walk, 2026-11-19: a file's chip stayed in the box after its line went and
  // rode on his next two lines, Try again among them): a line the page sends itself (`given`: Try again) takes none, and a send empties the box
  const sendLine = useCallback((given, boxFiles = given == null) => {
    const c = runtime.thread.composer, w = String(given ?? c.getState().text).trim(), files = boxFiles ? [...attachmentsRef.current] : [];
    if (!w && !files.length) return;
    if (given == null) c.setText("");
    if (files.length) onClearAttachments(null);
    const id = `l${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`, sel = selectionRef.current || {};
    setMine((m) => [...m, { id, kind: "line", text: w, files: files.map((a) => a.path), at: new Date(), rest: !listNow.current?.working && !listNow.current?.hold && !listNow.current?.permissions?.length }]);      // ...on an untrusted sender's task it waits by the box at once (the list's `hold`), and under a step that waits on his Allow (`permissions`)
    stick.current = true; opening.current = false;
    // ...on an item Taskuary made (`start`, madeTask) the line starts its agent: the item its Came from, his words the ask (AssistantView.startOnItem)
    (start ? start({ text: w, files: files.map((a) => a.path) }).then(() => ({}))
      : api.post(`/api/tasks/${task.TaskId}/assistant/messages`, { text: w, attachments: files.map((a) => a.path), line_id: id, pick: sel.connectorId || null, model: sel.model || null }, { timeout: 0 }))
      .then((r) => { if (road) road(); else if (r.data?.messages) onSent?.(r.data); reloadList?.(); })
      .catch((x) => { setMine((m) => m.map((l) => (l.id === id ? { ...l, err: errText(x) } : l))); if (files.length) onAttachBack(files); reloadList?.(); });
    setTimeout(() => reloadList?.(), 120);
  }, [runtime, attachmentsRef, selectionRef, onClearAttachments, onAttachBack, onSent, road, reloadList, task.TaskId, start]);
  // ...and a line whose send failed is sent again as it was typed, the failed one taken off the screen
  // ...with the files its failure put back in the box (onAttachBack)
  const retry = useCallback((l) => { setMine((m) => m.filter((x) => x.id !== l.id)); sendLine(String(l.text || ""), true); }, [sendLine]);
  // ...TRY AGAIN IS A PRESS, never his words (the owner, 2026-11-22): the agent hears he pressed it; the button says what became of it
  const [againAt, setAgainAt] = useState(null);
  const againGo = useCallback(() => { if (againAt?.going) return; setAgainAt({ going: true });
    api.post(`/api/tasks/${task.TaskId}/again`).then((r) => setAgainAt(r.data?.ok ? null : { err: r.data?.why || "It could not start again." }))
      .catch((x) => setAgainAt({ err: errText(x) })).finally(() => reloadList?.()); }, [againAt, task.TaskId, reloadList]);
  const again = useMemo(() => ({ go: againGo, ...againAt }), [againGo, againAt]);
  // ...and what waits, taken back or sent in now - the server's word, read again at once (the list moves it, never the page)
  const dropLine = useCallback((l) => { setMine((m) => m.filter((x) => x.id !== l.id)); api.post(`/api/tasks/${task.TaskId}/waiting/${encodeURIComponent(l.id)}/drop`).catch(() => {}).finally(() => reloadList?.()); }, [task.TaskId, reloadList]);
  const sendNow = useCallback(() => { api.post(`/api/tasks/${task.TaskId}/waiting/now`).catch(() => {}).finally(() => reloadList?.()); }, [task.TaskId, reloadList]);
  const chipsWaiting = waitingChips(merged.pending, came?.label || "");
  // ...at its end, and held there while he has not moved away from it: what is new draws under what he was reading, never over it.
  // BEFORE THE FIRST PAINT (a layout effect): the lines of a long chat measure themselves as they are drawn and each grows a "Show all" - after
  // this component's own pin. Watched only from after the paint, the first frame of an opened task stood ~900px short of its end
  React.useLayoutEffect(() => {
    const v = viewport.current, el = inner.current;
    if (!v || !el) return undefined;
    // ...HIS scroll, not the chat's own growth (chatStream.heldAtEnd): a wheel, a finger, a key, or a press still down (the scrollbar's drag)
    let was = v.scrollTop, used = -Infinity, mark = null;
    const mine = () => { used = performance.now(); opening.current = false; }, down = () => { used = Infinity; opening.current = false; };
    // ...and away from the end, the row he was reading (chatStream.anchorOf): kept where it stood through a change of size
    const hold = () => { mark = stick.current ? null : anchorOf(v, el); };
    // ...OPENED AT THE START OF THE NEWEST REPLY (chatStream.openAt), held at the end only where that is the end
    const place = () => { v.scrollTop = openAt(v, el); stick.current = v.scrollHeight - v.scrollTop - v.clientHeight < AT_END; was = v.scrollTop; };
    const on = () => { stick.current = heldAtEnd(stick.current, { top: v.scrollTop, was, gap: v.scrollHeight - v.scrollTop - v.clientHeight, own: performance.now() - used < 1500 }); was = v.scrollTop; hold(); };
    // ...and at the end a fold waits a beat for what comes under it (chatStream.shrinkHeld): one move, never up and back down
    let tall = 0, free = null;
    const own = () => { const m = el.style.minHeight; el.style.minHeight = ""; const h = el.offsetHeight; el.style.minHeight = m; return h; };
    const ro = new ResizeObserver(() => {
      const h = own(), keep = shrinkHeld(stick.current, tall, h);
      if (keep) { el.style.minHeight = `${keep}px`; clearTimeout(free); free = setTimeout(() => { tall = own(); el.style.minHeight = ""; }, SHRINK_HOLD); }
      else { if (el.style.minHeight) { clearTimeout(free); el.style.minHeight = ""; } tall = h; }
      if (opening.current) { place(); hold(); return; }
      if (stick.current) v.scrollTop = v.scrollHeight;
      else { const d = anchorShift(v, mark); if (Math.abs(d) > 1) v.scrollTop += d; }
      folding = false; hold();
    });
    // ...and when the VIEW itself gets shorter - the box under it grew a line as he typed - as when the chat gets longer (the recorded walks,
    // 2026-11-11: 14 px behind its end for a beat each time)
    // ...AND A LINE HE OPENS OR SHUTS HIMSELF ("Show all" / "Show less", ArrivedWords) is his move, never the chat's own growth or fold: the end lets
    // go, and what he pressed stays where it stood - the line's top as it opens, its toggle as it shuts (the owner, 2026-11-25: Show less "reloaded
    // the page" - held at the end, the chat kept its old height over nothing for SHRINK_HOLD, a blank view, then dropped back to the top)
    // ...through the scroll the shrink itself makes (the browser pulls the view up to the new end, which read as "at the end" again) until the
    // observer has placed it
    let folding = false;
    const fold = (e) => { const b = e.target?.closest?.("[data-tq-arrived-expand]"); if (!b) return;
      const at = b.getAttribute("aria-expanded") === "true" ? b : b.closest("[data-tq-item], .tq-aui-arrived") || b;
      mine(); stick.current = false; folding = true; mark = { el: at, off: at.getBoundingClientRect().top - v.getBoundingClientRect().top }; };
    const scrolled = () => { if (folding) was = v.scrollTop; else on(); };
    el.addEventListener("click", fold, true);
    v.addEventListener("scroll", scrolled, { passive: true }); ro.observe(el); ro.observe(v);
    const off = [[v, "wheel", mine], [v, "touchmove", mine], [v, "pointerdown", down], [window, "pointerup", mine], [window, "pointercancel", mine], [document, "keydown", mine]];
    off.forEach(([t, n, f]) => t.addEventListener(n, f, { passive: true, capture: true }));
    opening.current = true; place(); hold();
    const settle = setTimeout(() => { opening.current = false; }, OPEN_HOLD);
    return () => { clearTimeout(free); clearTimeout(settle); v.removeEventListener("scroll", scrolled); el.removeEventListener("click", fold, true); ro.disconnect(); off.forEach(([t, n, f]) => t.removeEventListener(n, f, { capture: true })); };
  }, [!!list]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...after EVERY draw, not only the list's: a card's own words (the page's node) grow the chat too - and once more when the draw is whole
  // (a microtask: after the rows that measured themselves in this same draw have grown), still before anything is painted
  React.useLayoutEffect(() => { const pin = () => { const v = viewport.current; if (v && stick.current && !opening.current && v.scrollTop + v.clientHeight < v.scrollHeight) v.scrollTop = v.scrollHeight; };
    pin(); queueMicrotask(pin); });
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
  const boxOf = useRef(task.TaskId);
  useEffect(() => holdUnsent(runtime.thread.composer, task.TaskId, boxOf), [runtime, task.TaskId]);
  // ...a line sent while his files upload waits for them (promptImages.useSendWhenUp) - Enter and Send alike
  const { go: sendBox, waiting: sendHeld } = useSendWhenUp(pics, useCallback(() => sendLine(), [sendLine]));
  const onKey = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) { e.preventDefault(); sendBox(); } };
  // ...what the card read (LandingCard's onState) places it, and is handed back so it draws at once wherever it lands
  const [landS, setLandS] = useState(undefined);
  const landNode = landing ? React.cloneElement(landing, { onState: setLandS, rev: list?.rev || "", ...(landS ? { initial: landS } : {}) }) : null;
  // ...and only when it asks for a press or says what one did: "Worked on master - 8 files" alone is the header's diff, said again
  const landAt = landS && (landS.ask || landS.landed) ? landS.at || "" : null;
  // WHAT THE AGENT ASKS STANDS IN THE TURN THAT ASKED IT (conversation.items `asking.turn`): one node, drawn there
  const askNode = asking ? <AgentAsks asking={asking} name={name} onAnswer={onAnswer} taskId={task.TaskId} /> : null;
  const askAt = askTurn(asking, merged.items);
  const askWords = askPlaceholder(asking);
  return (
    <AssistantRuntimeProvider runtime={runtime}><StopCtx.Provider value={onStop}>
      <ThreadPrimitive.Root className={chat ? "tq-aui-thread tq-aui-chat" : "tq-aui-thread"}>
        {/* ...`data-tq-follows-end`: this scroller keeps its own place - its end, or where he scrolled to - and nothing else moves it (inView.unclip) */}
        <ThreadPrimitive.Viewport ref={viewport} className="tq-aui-viewport" autoScroll={false} data-tq-follows-end="">
          <div ref={inner} className="tq-conv" data-tq-conv={list ? "loaded" : ""}>
            {!list && <Box data-tq-chat-reading="" sx={{ py: 6, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}
            {chat && !!list && !merged.items.length && reading}
            {!!list && !merged.items.length && !!empty && <div className="tq-aui-hint" style={{ margin: "8px 0 16px" }}>{empty}</div>}
            {!!list && !merged.items.length && !empty && !(chat && reading) && <div className="tq-aui-welcome"><TaskuaryMark size={22} /><div>
              <div className="tq-aui-welcome-title">Work on this with your assistant</div>
              <div className="tq-aui-welcome-copy">Research, plan, write, analyze, or coordinate. This conversation stays on the task.</div></div></div>}
            <RetryCtx.Provider value={retry}><StopTriesCtx.Provider value={stopTries}><AgainCtx.Provider value={again}><WaitOnCtx.Provider value={waitingOn(list)}><Conversation items={merged.items} nodes={turnCards || []} posts={nextAt?.cards || []} reviews={nextAt?.reviews || []} next={askedFirst(asking, nextAt?.reviews) ? null : nextAt?.next || null}
              landing={landNode} landAt={landAt} name={turnName} tid={task.TaskId} onChanged={nextAt?.refresh} ask={askNode} askAt={askAt} queue={list?.queue || null} /></WaitOnCtx.Provider></AgainCtx.Provider></StopTriesCtx.Provider></RetryCtx.Provider>
            {/* WHAT THE SOURCE WAITS ON THE OWNER FOR, while it works too (`cards`): a coding agent's permission cards, its screen while it asks */}
            {cards}
            {/* ...under everything only while the list names no turn for it (a read behind, a chat with no turn yet) */}
            {!askAt && askNode}
            {/* ...a chat whose page places no cards itself (a walk's, a journey's): a drafted playbook and a held act are approved here */}
            {!turnCards && !!drafts?.length && <Box data-tq-playbook-drafts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{askNote(drafts[0])}</Typography>
              {drafts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {!turnCards && !!acts?.length && <Box data-tq-browser-acts="" sx={{ mt: 1.5, mx: { xs: 1, sm: 2 }, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.75 }}>{heldActsLine(acts)}</Typography>
              {acts.map((r) => <ReviewDecision key={r.ReviewId} review={r} onChanged={onDraftDecided} />)}</Box>}
            {/* AN UNTRUSTED SENDER'S TASK: one plain line why no agent works on it, and its one action (the list's `hold`, origin.hold) */}
            {hold && <HeldStart taskId={task.TaskId} hold={hold} onChanged={onTrusted} onRow={trustOnRow} />}
            {/* A START THAT DID NOT HAPPEN, AND WHY (the list's `idle`): one plain line under the chat until a turn begins - the box is the way on */}
            {!hold && !!idle && <Box data-tq-not-started="" className="tq-aui-summary" sx={{ mt: 1, mx: { xs: 1, sm: 2 }, fontSize: 13.5, color: "var(--tq-text, #292824)" }}>{idle}</Box>}
            {queued && <div className="tq-aui-message tq-aui-agent" data-tq-queued-turn=""><div className="tq-aui-role">{AGENT_TURN}</div><div className="tq-aui-agent-body">{queued}</div></div>}
            {/* ...said once: where the list holds his close as a press (`closes`), that line is the close (one press, one line) */}
            {closedLine && !merged.items.some((x) => x.closes) && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
          </div>
        </ThreadPrimitive.Viewport>
          <div className="tq-aui-footer">
            {/* HIS LINE THAT WAITS IS PINNED JUST OVER THE BOX until the agent takes it, then it lands in the chat where it was heard (the owner,
                2026-11-15: under the turn at work it went down the screen for as long as that turn wrote - a minute, on a terminal). It keeps its
                place whatever the turn does: a little room between it and the box, each line in its own border. Every kind of agent, one strip */}
            <PendingStrip items={merged.pending} now={!!list?.now} later={list?.later || ""} onRetry={retry} onDrop={dropLine} onNow={sendNow} />
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
            <OneBox root={ComposerPrimitive.Root} rootProps={{ onSubmit: (e) => { e.preventDefault(); sendBox(); } }} onFiles={onAttach}
              chips={attachmentsRef.current.length || pics?.busy || pics?.err || came || chipsWaiting.length ? <>
                {came && ((w) => <AttachChip data-tq-came-chip="" {...(w ? { "data-tq-pending-ids": w.ids.join(" ") } : {})} name={w ? w.label : came.label}
                  title={came.title || came.label} icon={came.icon || false} onClick={came.onOpen} sx={{ cursor: came.onOpen ? "pointer" : "default" }} />)(chipsWaiting.find((c) => c.came))}
                {chipsWaiting.filter((c) => !c.came).map((c) => <AttachChip key={c.key} data-tq-waiting-chip="" data-tq-pending-ids={c.ids.join(" ")} name={c.label} title={c.label} icon={false} />)}
                {/* ...his files, and their upload's state or why one failed, ON THE BOX (the owner, 2026-11-16: a paste's "Attaching..." stood at the
                    top of the chat and never resolved): the one attach road every box takes (promptImages.usePromptImages) */}
                {pics && <>{fileChips(pics)}{fileState(pics)}</>}</> : null}
              input={<ComposerPrimitive.Input className="tq-aui-input" onKeyDown={onKey} placeholder={askWords || placeholder || MESSAGE} />}
              onMic={(t) => { const c = runtime.thread.composer, was = c.getState().text; c.setText(was.trim() ? `${was.trimEnd()} ${t}` : t); }}
              send={<button type="button" className="tq-aui-send" aria-label="Send" data-tq-send="" disabled={sendHeld} onClick={sendBox}>
                {sendHeld ? <CircularProgress size={14} color="inherit" /> : <SendIcon fontSize="small" />}</button>} />
            <div className="tq-aui-hint">{hint || "Enter sends · Shift+Enter adds a line · paste, drop or attach a file"}</div></>}
          </div>
      </ThreadPrimitive.Root>
    </StopCtx.Provider></AssistantRuntimeProvider>
  );
}

export function GeneralWorkspace({ task, onSession, onAnswered, compact = false, toolsAt = null,
  prompt, onPromptUsed, noAiSaid = false, noTools = false, noComposer = false, liveSid = "", reread = 0, mails = [], reviews = [],
  checklist = null, opening = false, next = null, chat = false, came = null, closedLine = "", term = null, landing = null, turnCards = null, queued = null, stopTries = null, onChanged, seed = null, trustOnRow = false,
  made = null }) {
  // `made`: { list, start } - an item Taskuary made (madeTask): its chat is its own list, nothing on the server to read or poll yet, and its box
  // starts the agent on it. The same chat, rows, cards and box as every task's
  // ...drawn on its first frame from what is held of it (chatOf); a coding task's chat stands on its list alone
  const first = () => (made ? { messages: [], made: true } : chatSource(task, term) === "coding" ? { messages: [] } : chatOf(task.TaskId));
  const [data, setData] = useState(first);
  const [connectorId, setConnectorId] = useState(() => String(pickFor(first())?.id || ""));
  const [model, setModel] = useState(() => { const d = first(), p = pickFor(d); return p ? d?.session?.model || p.model || "" : ""; });
  // ...ITS FILES TAKE THE ONE ATTACH ROAD (promptImages.usePromptImages): paperclip, paste and drop alike, any file, on the box
  const pics = usePromptImages({ files: true });
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
  const served = useConversation(task.TaskId, !made), madeList = made?.list;
  const conv = useMemo(() => (madeList ? { list: madeList, load: () => Promise.resolve(false) } : served), [madeList, served]);
  // ..."WORKING" IS ONE FACT ON THE WHOLE PAGE (the recorded walk, 2026-11-11: the chat stood finished under a header that still read "agent
  // working"): the moment the list's own word on it changes, the task's header and its row are read again
  // ...but only when it CHANGES, and only by itself where no push will say it: an opening that holds the list already read its task and its rail,
  // and a turn's start and end are pushed (task-changed -> reloadFor, TaskPage's own listener) - asked again here they were a second forced
  // rebuild of every rail row (measured 2026-11-18). The look stays for a socket that is down, as every poll's safety look does (restLook)
  const convWorks = !!conv.list?.working, answeredRef = useRef(onAnswered); answeredRef.current = onAnswered;
  const workMoved = useRef(null); workMoved.current ||= changes(convWorks);
  useEffect(() => { if (workMoved.current(convWorks) && conv.list && !liveUp()) answeredRef.current?.(); }, [convWorks]);   // eslint-disable-line react-hooks/exhaustive-deps
  const defaults = useChatDefaults(), own = useOwnDetail(task.TaskId);
  const level = chat ? detailFor({ source, settings: defaults, own }) : "steps";
  // ...and the CLI that runs, what it asks and what it waits on his press for: the list's own (conversation.items `live`, `asking`, `permissions`)
  const cli = coding ? conv.list?.live || null : null;
  attachmentsRef.current = pics.imgs;

  // asked once, and only once: the marker is cleared on the server as the question goes
  const dropAsk = useCallback(() => {
    api.patch(`/api/tasks/${task.TaskId}`, { Tags: withoutAsk(task.Tags) }).catch(() => {});
  }, [task.TaskId, task.Tags]);

  const heldRev = useRef("");        // the name of the chat state this view draws (its `rev`), for the poll to ask "still this?"
  const accept = useCallback((payload) => {
    setData(payload); heldRev.current = payload?.rev || ""; if (payload) CHATS.set(task.TaskId, payload);
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
  }, [onSession, task.TaskId]);

  useEffect(() => {
    let live = true;
    setData(first()); setError(""); pics.clear();
    // Looking at a general task is not sending it to an agent. Load saved state only; the first
    // actual message (or an explicit Send to agent action) starts the regular agent.
    if (coding || made) return () => { live = false; };
    // ...the read asked ahead with the task, still on its way, is drawn the moment it lands - unless this view's own, newer, landed first
    let own = false;
    if (!first()) aheadChat(task.TaskId)?.then((d) => { if (live && !own && d) accept(d); });
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => { own = true; if (live) accept(r.data); }).catch((e) => live && setError(errText(e)));
    return () => { live = false; };
  }, [accept, task.TaskId, coding]);

  const updateProvider = async (nextId, nextModel = model) => {
    setConnectorId(String(nextId)); setModel(nextModel); setError("");
    try {
      const r = await api.post(`/api/tasks/${task.TaskId}/assistant/session`, { pick: nextId || null, model: nextModel || null });
      accept(r.data);
    } catch (e) { setError(errText(e)); }
  };
  // one path (a chip's x), or the paths a send took - never the whole box, so a file added since stays
  const clearAttachments = useCallback((paths) => (paths == null ? pics.clear() : [paths].flat().forEach(pics.remove)), [pics.clear, pics.remove]);   // eslint-disable-line react-hooks/exhaustive-deps
  const attachBack = pics.put;
  const sent = accept;
  const stopRun = useCallback(() => {
    if (coding) api.post(`/api/tasks/${task.TaskId}/agent/cancel`).then(() => setTimeout(conv.load, 600)).catch((x) => setError(errText(x)));
    else api.post(`/api/tasks/${task.TaskId}/assistant/cancel`).catch(() => {});
  }, [task.TaskId, coding, conv.load]);
  /* On screen, the agent's CLI stays open: the server reaps one nobody touches for 30 minutes, and this is the touch. Nothing starts here. */
  useEffect(() => {
    if (coding || made) return undefined;
    const seen =() => { if (!document.hidden) api.post(`/api/tasks/${task.TaskId}/assistant/seen`).catch(() => {}); };
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
  // ...and NOT while it only waits on the page (2026-11-17): every way the page's ask is answered - the saved sign-in typed, the fill page,
  // the owner signing in or stepping through on it (signin._continue, browsergate._close) - is a workerstate.record, whose task-changed the
  // quiet pane below reads once. Read every 2.5 s, it was a read of the whole conversation for as long as the page stood unanswered
  // ...READ WHEN THE TURN MOVES (stress round, 2026-11-18): each step is pushed (run-tail), read at most once a second; the tick only backs it
  // up - every tick while the socket is down, else every 5 s (restLook). Every 1-2.5 s for the whole turn was ~25 reads a minute of a turn
  // that was thinking in silence
  useEffect(() => {
    if (!busy) return undefined;
    let live = true, last = Date.now();
    const read = async () => {
      last = Date.now();
      try {
        // ...the name of what this chat holds rides along: unchanged, the answer is that name alone (server._revisioned), and nothing is drawn again
        const { data: fresh } = await api.get(`/api/tasks/${task.TaskId}/assistant`, { params: heldRev.current ? { rev: heldRev.current } : {} });
        if (!live || fresh?.same) return;
        heldRev.current = fresh.rev || "";
        setData(fresh);
        // ...and the page's copy too: it held the session the turn STARTED with, so its heading said "is working" under the
        // finished answer (2026-10-15)
        onSession?.(fresh.session || null);
      } catch { /* it will still be there next tick */ }
    };
    const [wake, stop] = coalesced(read, 1000);
    const off = onLive("run-tail", (ev) => { if (touches(ev, task.TaskId)) wake(); });
    const timer = setInterval(() => { if (restLook({ socket: liveUp(), last, now: Date.now(), every: 5000 })) read(); },
      drawn ? 2500 : 1000);      // a start that has drawn nothing yet is read every second with no socket: its first word gives the room at once
    return () => { live = false; clearInterval(timer); off(); stop(); };
  }, [busy, drawn, task.TaskId, onSession]);
  // ...and what a read brings is handed to the standing thread (a revision bump), as the poll does: taken into `data` alone, the owner's
  // Continue note waited for the next poll to show (the owner, 0.3.9.51: "I did Continue, filled it out and nothing happened")
  const refresh = useCallback(() => {
    conv.load();
    if (coding || made) return;
    api.get(`/api/tasks/${task.TaskId}/assistant`).then((r) => accept(r.data)).catch(() => {});
  }, [accept, task.TaskId, coding, conv.load, made]);
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
  // ...and when an AI card or setting moves (wrote.movesSetup): "No AI is connected yet" read the AIs once, and stood after the card came back on
  useEffect(() => { const f = () => { if (quietRef.current) refresh(); }; window.addEventListener(SETUP_CHANGED, f); return () => window.removeEventListener(SETUP_CHANGED, f); }, [refresh]);
  const { onPaste: pasted, onDrop: dropped, onDragOver: dragging } = pics.drop;

  // ...AND ONCE IT IS UP FOR THE OWNER IT STAYS UP until the agent answers again (the owner, 2026-11-05, signing in to a site in two steps: "I put
  // in username then hit next the box disappeared then reopened to put in password. You can leave it open until auth is done"): between a
  // sign-in's pages there is a moment with no ask open, and the page went away under them
  // ...what the agent asks, by the one read both payloads carry (taskstate.asking): gone from the card the moment it is answered
  const ask = (conv.list || data)?.asking, asking = ask && ask.request_id !== answered ? ask : null;
  // ...whether he has a part on the page is the server's one answer (taskstate.needs_owner), read from the payload that carries the ask - a coding
  // task reads its chat's state once, and its agent's hand-over never drew (the design loop, 2026-11-20); an ask he has just answered here stops it at once
  const needRaw = !!(conv.list || data)?.needsOwner && !(ask && ask.request_id === answered), answers = (conv.list?.items || []).filter((x) => x.kind === "turn" && x.state !== "working" && x.state !== "starting").length;
  const [needHeld, setNeedHeld] = useState(null);
  useEffect(() => { if (needRaw) setNeedHeld(answers); }, [needRaw]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...or is AT WORK again: his part is done the moment it goes on (the owner, 2026-11-11: "seamlessly hand off once login is in to go back to
  // normal chat") - a sign-in's ask stays open through every page of it (signin.watch), so the gap this hold covers is never a turn at work
  useEffect(() => { if (needHeld != null && !needRaw && (answers > needHeld || busy || !data?.session?.sid)) setNeedHeld(null); }, [answers, needRaw, needHeld, busy, data?.session?.sid]);
  const needNow = needRaw || needHeld != null;

  // ...a start the page already knows of says so before the conversation's first read lands, never a 520px spinner over nothing
  // ...never drawn from the list alone before this read: the files and cards it carries landed a beat later and grew the turn by 900 px under
  // the owner's eyes (recorded 2026-11-12) - the task view waits for the read asked ahead with it instead (TaskPage loadDetail, aheadChat)
  // ...AND A START ALREADY HEARD IS ITS CHAT FROM THERE: his words and the turn starting under them, from the list (the owner, 2026-11-16: the
  // dots stood in a box of their own, then the chat came in around them) - the one place a starting turn is drawn is the chat's (ConvTurn)
  if (!data && !error && !(opening && conv.list?.items?.length)) return <Box data-tq-chat-reading="" sx={{ height: 520, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>;
  const session = data?.session;
  // ...the agent's turns, as the list holds them: what each said, by the name the page keys a turn by
  const turnsNow = (conv.list?.items || []).filter((x) => x.kind === "turn");
  // ...and what typing does there: into the running CLI as its next line, or the session picked back up with these words leading - the files
  // a field beside the words, named to the CLI by their paths under them as the server builds its prompt (general.with_files)
  // ...and what a coding source reads once a line is in: its own sessions (the line itself goes the one road, holdText)
  const road = coding ? () => { onChanged?.(); conv.load(); } : null;
  // ...its screen is a card only on the pty road, and only while it asks (codingchat.live_of `asking`); over ACP Stop ends the turn
  const acp = cli?.transport === "acp", screenAsks = coding && !!cli?.asking && !acp && !!cli?.sid, perms = coding ? conv.list?.permissions || [] : [];
  const codingCards = coding ? <>
    {/* WHAT THE AGENT WAITS ON THE OWNER'S PRESS FOR (permissions.py), answered here or on a bound chat: on the row of the call it is about
        (PermitProvider), a card of its own only for one no row in the chat names (chatStream.asksOff) */}
    <PermissionCards taskId={task.TaskId} items={asksOff(perms, conv.list?.items)} onAnswered={conv.load} />
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
  // ...only a card the chat draws for his press now (pressable): never a line about a card that is not there
  const onChat = pressable(conv.list);
  const viewActs = (data?.browserActs || []).map((r) => heldOn(r, session?.sid)).filter((h) => h && onChat.has(h.id));
  // ...EVERY WAIT ON THE PAGE IS ONE TURN (a sign-in too - the Claude walk, 2026-11-19: a sign-in drew the toolbar's "I'm done", which only let
  // go of the page and told nobody): its bar's I'm done is the one hand-back - his line, the agent woken (handBack)
  const turn = asking && waitsOnPage(asking) ? asking : null;
  // ...a held SHELL step is the task page's card in Next steps, one card for the turn (HeldSteps) - it was drawn here a second time, per step
  const actsHere = (viewShown ? (data?.browserActs || []).filter((r) => !heldOn(r, session?.sid)) : data?.browserActs || []).filter((r) => proposalFrom(r)?.action !== "shell_act");
  // Approve runs the act and tells the agent on a thread of its own (browsergate._tell): its next turn starts a moment after the press
  const decidedOnView = () => { refresh(); setTimeout(refresh, 2000); };
  // THE VIEW'S DONE IS THEIR PRESS (the spine audit, 2026-11-09): it went in as words typed in their name - a bubble they never wrote. The
  // server closes the hand-over and tells the agent itself (workerstate.answer `press`, browsergate.done); the chat reads one quiet line
  const handBack = async () => {
    const req = asking;
    // ...a sign-in is handed back by its own answer (signin.DONE - its road keeps what he typed); a step on the page by his press
    const body = isSignin(req) ? { text: (req.choices || [])[0] || "Signed in" } : { text: "", press: true };
    try { await api.post(`/api/tasks/${task.TaskId}/worker/answer`, { request_id: req.request_id, ...body }); }
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
    <PermitProvider taskId={task.TaskId} perms={perms} onAnswered={conv.load}>
    <LevelCtx.Provider value={level}><ChatCtx.Provider value={chat}><AgentNameCtx.Provider value={made ? "Taskuary" : AGENT_TURN}><ShownCtx.Provider value={placed.by}>
    <WorkCtx.Provider value={{ reviews, checklist: steps, acts: [...(data?.browserActs || []), ...(data?.playbookDrafts || [])], next,
      cards: data?.cards || [], refresh }}>
    {/* ...and each file in the turn that made it (placeMade): one no turn made, or a page no turn holds, is not drawn in the conversation */}
    <OutputsCtx.Provider value={{ tid: task.TaskId, listed: placeMade(data?.outputs, turnsNow), versions: data?.turnOutputs }}>
    <LocalFiles.Provider value={{ tid: task.TaskId }}>
      <AssistantThread key={task.TaskId} task={task} list={conv.list} reloadList={conv.load}
        onAsked={dropAsk} onStop={stopRun} selectionRef={selectionRef}
        attachmentsRef={attachmentsRef} onSent={sent} onClearAttachments={clearAttachments} onAttachBack={attachBack}
        onAttach={pics.add} pics={pics}
        prompt={ownPrompt || prompt} onPromptUsed={promptUsed}
        asking={turn && viewShown ? null : asking} onAnswer={answerAsk} noComposer={noComposer}
        name={name}
        drafts={data?.playbookDrafts || []} acts={actsHere} onDraftDecided={refresh} seed={seed}
        chat={chat} reading={chat && readingOf(data?.thread || task?.ThreadJson)?.asking
          ? <div className="tq-aui-ask" data-tq-chat-ask="">{readingOf(data?.thread || task?.ThreadJson).asking}</div> : null}
        came={chat ? came : null} closedLine={chat ? closedLine : ""} queued={chat ? queued : null} stopTries={chat ? stopTries : null} hold={conv.list?.hold || null} trustOnRow={trustOnRow} idle={conv.list?.idle || ""} onTrusted={() => { conv.load(); onAnswered?.(); onChanged?.(); }}
        road={road} cards={codingCards} landing={chat ? landing : null} turnCards={chat ? turnCards : null} start={made?.start || null}
        // ...THE BOX SAYS WHAT THE HEADER SAYS (the owner's live task, 2026-11-12: "Write to pick the session back up" under a turn at work - its
        // session was being opened again for his line): "working" is the list's one fact, whatever process is up yet
        placeholder={coding ? (closedTask && !convWorks ? "Write to pick it back up…" : cli || convWorks || !conv.list?.ran ? MESSAGE : "Write to pick the session back up…") : ""}
        hint={!coding ? "" : acp ? (cli.working || convWorks ? "Enter sends it when this turn ends · Shift+Enter adds a line" : "Enter sends it to the agent · Shift+Enter adds a line")
          : cli ? "Enter types it into the running agent · Shift+Enter adds a line" : convWorks ? "Enter sends it when this turn ends · Shift+Enter adds a line"
          : "Enter picks the session back up with what you wrote · Shift+Enter adds a line"}
        empty={coding && conv.list ? (cli ? "The agent is starting - its turns show here as it works." : "No session has run on this task yet - write below to start one.") : ""}
        noAi={!coding && chat && !made && !data?.providers?.length && !noAiSaid && !data?.demo
          ? <div className="tq-aui-noai" data-tq-no-ai="">No AI is connected yet - what you type waits for one. <ConnectAi size="small" variant="text" /></div> : null} />
    </LocalFiles.Provider>
    </OutputsCtx.Provider>
    </WorkCtx.Provider>
    </ShownCtx.Provider></AgentNameCtx.Provider></ChatCtx.Provider></LevelCtx.Provider></PermitProvider>
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
        <Typography noWrap sx={{ ...mono, fontSize: 10.5, letterSpacing: ".13em", textTransform: "uppercase", color: DIM, flexShrink: 0 }}>{name}</Typography>
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
      {!chat && <ThreadReading reading={data?.thread} mails={mails} variant="chat" />}
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {/* ALWAYS inside the pane, session or not: a session that arrives mid-turn (`started`) must not
            change the tree around the thread, or the answer streaming into it is remounted away
            ...and no sid on a card whose session is not live (`noTools`): its browser was asked for every 3 s under a stopped, saved
            or failed agent's Result, for as long as it stayed open (the agents walk, 2026-10-26) */}
        {/* ...a coding agent's browser is its session's too, shown only while he is needed on its page (the recorded coding walk, 2026-11-12:
            the agent asked to be signed in, and with no chat session to name, no page was ever shown him) */}
        <SessionPane sid={(!noTools && session?.sid) || (coding && needNow && cli?.sid) || null} height="100%" yourTurn={waitsOnPage(asking)} idle={!busy}
          stack taskId={task.TaskId} held={pageBars(turn, viewActs).held} turn={turn} onHandBack={handBack} onDecided={decidedOnView}
          onView={viewShownIs} quiet={chat} need={needNow}>{thread}</SessionPane>
      </Box>
    </Box>
  );
}

export default GeneralWorkspace;
