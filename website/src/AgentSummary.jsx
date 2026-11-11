// EACH TURN ENDS IN THREE PARTS (the closeout-in-chat spec, 2026-11-04): what this is about, what the agent did, and the next steps - the
// drafts waiting on Send, the steps only the owner can take ("On you: …"), or "Nothing left to do here". Where the chat is the task's home the
// drafts are their cards, inside Next steps (`next`, TaskPage's chat cards, so each draft is drawn once); elsewhere a
// line each. An On you step's mark says whose it is, never a press.
import React, { useEffect, useRef, useState } from "react";
import { Box, CircularProgress, IconButton, Tooltip, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import SendIcon from "@mui/icons-material/ArrowUpward";
import api from "./api.js";
import { hasReply, nextSteps, oneLine } from "./agentSummary.js";
import { isCardReview } from "./actionCard.js";
import { Md } from "./md.jsx";
import { MicButton } from "./ui.jsx";
import { MESSAGE } from "./kinds.js";
import { keepUnsent, unsent } from "./unsent.js";
import { AttachRow, IMAGE_ACCEPT, INLINE_CHIPS, fileChips, fileState, usePromptImages, withImages } from "./promptImages.jsx";
import { ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

// ...a chatbot's answer, split into sections to read (the owner, 2026-11-05): a short bold heading over each, no rules, no boxes but the email's
const HEAD = { display: "block", color: INK, fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 };
const Head = ({ children, first }) => <Typography component="span" sx={{ ...HEAD, ...(first ? { mt: 0 } : {}) }}>{children}</Typography>;
const LINE = { fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere" };
const who = (r) => r.FromName || r.FromEmail || "";

const PARA = { ...LINE, mt: 1 };
// A REGULAR CHAT (the owner, 2026-11-05: "it's just a chat with it summarizing in different paragraphs (short text as possible) this is the chat,
// this is what i did about it and this is what i suggest" - "hate all the boxes ... no lines"): plain paragraphs, no rules, no boxes, no
// "On you:" line per step - the steps only the owner can take are ONE sentence, the first three and how many more the To do holds
const ONYOU_SHOWN = 3;
const OnYou = ({ items }) => {
  if (!items.length) return null;
  const shown = items.slice(0, ONYOU_SHOWN).map((i) => i.text.replace(/[.\s]+$/, "")), more = items.length - shown.length;
  return <Typography data-tq-on-you={items.map((i) => i.id || "").join(" ")} sx={LINE}>
    {`For you to do: ${shown.join("; ")}${more > 0 ? `, and ${more} more in the On you line under To do` : ""}.`}</Typography>;
};
// NEXT STEPS HOLD THE REPLY (the owner, 2026-11-05: "next steps should be above or combined with suggested reply as that's the next steps.
// meaning review the file then send it"): one head, what is on the owner first, then the draft with its Send
const DraftHead = () => <Head>Next steps</Head>;

// `lead`: what this turn SET UP for the owner's press, drawn as itself (a post, ActionCard) - it leads Next steps, the action section (the owner,
// 2026-11-05: "Next steps is the action section"). `made`: the files the turn made, inline under What I did (TurnFiles). `kept`: the drafts this
// turn wrote, as it wrote them (draft_snapshot)
// `answered`: the turn has words of its own - they ARE the turn (the owner, 2026-11-08: "never show anything twice in a turn"), so the summary's
// prose (About, What I did, On you) stays out and only what is drawn as a card is here: the files, the post, the drafts and their Send
export default function AgentSummary({ summary, reviews = [], checklist = [], acts = [], cards = true, next = null, folded = false, lastAnswered = false,
  kept = null, lead = null, made = null, turnId = null, answered = false }) {
  if (!summary) return null;
  const did = String(summary.did || "").trim(), about = String(summary.about || "").trim();
  // ...a turn that is history keeps the draft it left, read-only: what was drafted and to whom, no Send (the owner, 2026-11-05)
  // ...read from the draft itself (its id is all the turn keeps), with where it went since: sent, set aside, or still waiting
  // ...a turn filed before it kept its draft's id: the NEWEST answered turn keeps the draft still waiting (the owner, 2026-11-05: "keep the draft on
  // the original message")
  const ids = summary.drafted ? summary.drafted.map((x) => x?.review)
    : lastAnswered ? (reviews || []).filter((r) => r?.Status === "pending" && r.Kind !== "action" && r.Kind !== "slot").map((r) => r.ReviewId) : [];
  // ...in the words THIS turn left (general.shown_history's `drafts_then`, the owner, 2026-11-05: "keep the original draft in that turn"): the
  // agent rewrites one draft in place, and the review's own text is the newest turn's. A turn filed before that kept nothing reads the review
  const drafted = ids.map((id) => {
    const r = (reviews || []).find((x) => x.ReviewId === id), k = (kept || []).filter((x) => x?.review === id).at(-1);
    return k ? { ...(r || {}), ReviewId: id, DraftText: k.text, FromName: k.to || r?.FromName, FromEmail: r?.FromEmail } : r;
  }).filter((r) => r && String(r.DraftText || "").trim());
  const fate = (r) => r.Status === "sent" || r.DeliveryState === "sent" ? "sent" : r.Status === "pending" ? "" : "not sent";
  const Drafted = () => drafted.map((r) => <Box key={r.ReviewId} data-tq-drafted-then="" sx={{ mt: 1, px: 1.5, py: 1, borderLeft: "3px solid var(--tq-border, #dcd6ca)", color: DIM, fontSize: 13, lineHeight: 1.5 }}>
    <Typography component="span" sx={{ display: "block", fontSize: 11.5, fontWeight: 700, color: FAINT, mb: 0.25 }}>
      {["Drafted", who(r) && `to ${who(r)}`, fate(r)].filter(Boolean).join(" · ")}</Typography>
    <Box sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 220, overflow: "auto" }}>{r.DraftText}</Box></Box>);
  if (answered) return made || lead || next || (folded && drafted.length) ? (
    <Box data-tq-summary="cards" className="tq-aui-summary">{made}{(lead || next) && <DraftHead />}{lead}
      {next ? <Box sx={{ mt: 0.75 }}>{next}</Box> : null}{folded && <Drafted />}</Box>) : null;
  // ...a nothing-new turn is its one line, folded or not: no heads, no Next steps, and the draft stays on the turn that wrote it (oneLine)
  if (oneLine(summary)) return <>{<Box data-tq-summary="line" className="tq-aui-summary" sx={LINE}><Md text={did} /></Box>}{made}{lead}</>;
  if (folded) return did || drafted.length ? (<>
    {did && <Box component="details" data-tq-summary="folded" className="tq-aui-summary" sx={{ mt: 0.75 }}>
      {/* ...one line: what it did, cut where the line ends - the whole of it a press away */}
      <Box component="summary" title={did} sx={{ ...HEAD, mt: 0, cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", "&:hover": { color: INK } }}>
        What I did<Box component="span" sx={{ fontWeight: 400, color: DIM, ml: 0.75 }}>{did.split("\n")[0]}</Box></Box>
      <Box sx={{ ...LINE, color: DIM }}><Md text={did} /></Box>
    </Box>}
    {made}{lead}
    <Drafted /></>) : made || lead ? <>{made}{lead}</> : null;
  const { drafts, onYou, held: heldAll, nothing } = nextSteps({ summary, reviews, checklist, acts, cards });
  const held = heldAll.filter((r) => !isCardReview(r));        // an act with its card (a post) leads Next steps - never "a step waits, below"
  return (
    <Box data-tq-summary="open" className="tq-aui-summary">
      {!!about && <><Head first>What this is about</Head><Typography data-tq-summary-about="" sx={LINE}>{about}</Typography></>}
      {!!did && <><Head first={!about}>What I did</Head><Box data-tq-summary-did="" sx={LINE}><Md text={did} /></Box></>}
      {made}
      {lead || (next && hasReply(reviews)) || (drafts.length && !next) || held.length || onYou.length || (nothing && !lead) ? <DraftHead /> : null}
      {lead}
      <OnYou items={onYou} />
      {!!held.length && <Typography data-tq-summary-held={held.length} sx={LINE}>
        {held.length === 1 ? "One step waits for your Approve, below." : `${held.length} steps wait for your Approve, below.`}</Typography>}
      {!next && drafts.map((r) => <Typography key={r.ReviewId} data-tq-summary-draft={r.ReviewId} sx={LINE}>
        {who(r) ? `A reply to ${who(r)} is drafted and waits for your Send.` : "A reply is drafted and waits for your Send."}</Typography>)}
      {next ? <Box sx={{ mt: 0.75 }}>{next}</Box> : null}
      {nothing && !lead && <Typography data-tq-nothing-left="" sx={{ ...LINE, color: DIM }}>Nothing left to do here.</Typography>}
    </Box>
  );
}

// A TO-DO NO AGENT HAS TOUCHED (the owner, 2026-11-06): under what came in - which says the ask and the To do already - the cards the chat would
// hold (`cards`: a draft and its Send, an email owed), the drafter's why over them, and the one box. The box is Send to agent's road (the
// dispatch, which makes the task the general agent's) with the owner's own words; from its first turn on, the chat is the agent's.
export function NoAgentChat({ task, reviews = [], cards = null, closed = "", onStarted }) {
  const [text, setText] = useState(() => unsent(task.TaskId)), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  // ...and words typed and not sent are this task's (unsent.js): back after a reload, and another task's box shows that task's own
  const kept = useRef(task.TaskId);
  useEffect(() => {
    if (kept.current !== task.TaskId) { kept.current = task.TaskId; setText(unsent(task.TaskId)); }
    else keepUnsent(task.TaskId, text);
  }, [task.TaskId, text]);
  const pics = usePromptImages({ files: true });          // ...a dropped, pasted or picked file goes with the words (the owner, 2026-11-05)
  const why = String((reviews || []).find((r) => r?.Status === "pending" && r.DraftWhy)?.DraftWhy || "").trim();
  const send = async () => {
    const words = text.trim();
    if ((!words && !pics.paths.length) || busy || pics.busy) return;
    setBusy(true); setErr("");
    // ...SENT IS NOT UNSENT, FROM THE PRESS (the recorded walk, 2026-11-11): the chat drew itself the moment the agent started, before this box
    // had emptied, found the words still kept and put them back in its own box - under the same words in his bubble. A send that fails keeps them
    keepUnsent(task.TaskId, "");
    try {
      const { data } = await api.post(`/api/tasks/${task.TaskId}/dispatch`, { kind: "general", instruction: withImages(words, pics.paths) });
      setText(""); pics.clear(); onStarted?.(data);
    }
    catch (e) { keepUnsent(task.TaskId, text); setErr(e?.response?.data?.detail || "Could not start the agent - check that an AI is connected under Connections, then send it again."); }
    finally { setBusy(false); }
  };
  return (
    <Box data-tq-no-agent-chat="" sx={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
      {!!(cards || why) && <Box sx={{ pb: 1 }}>
        {!!why && <><Head first>What I did</Head><Typography data-tq-draft-why="" sx={LINE}>{why}</Typography></>}
        {cards ? <Box>{hasReply(reviews) && <DraftHead />}{cards}</Box> : null}
      </Box>}
      {/* ...a closed one says how it closed over the box - typing there reopens it (server._refuse_closed_chat) */}
      {!!closed && <div className="tq-aui-closed" data-tq-chat-closed="">{closed}</div>}
      <PromptBox text={text} setText={setText} pics={pics} busy={busy} onSend={send} placeholder={MESSAGE}
        label="Send to the agent" title="Starts the agent on this task with your words" boxAttrs={{ "data-tq-no-agent-box": "" }} sendAttrs={{ "data-tq-no-agent-send": "" }} />
      {!!err && <Typography role="alert" sx={{ px: 1.5, pb: 1, fontSize: 12.5, color: ALERT_INK }}>{err}</Typography>}
    </Box>
  );
}

// ONE BOX, ONE COMPONENT (the owner, 2026-11-06: "you moved the attached thing to the same line but you removed mic and attach icons???" - the
// coding chat's box was a form of its own with a bare textarea). Every prompt box is this: left to right the paperclip, the chips (what it came
// from, the files), the words, the mic, the box's own buttons (`extra`: a Terminal toggle, a stop), Send. The paperclip and the mic are not
// props to leave out. `root`: the form element (assistant-ui's Composer root in the general chat), `input` and `send` the box's own; `onFiles`
// takes what the paperclip picked, `accept` narrows it, `onMic` the words dictated
export function OneBox({ root = "form", rootProps = {}, onFiles, accept, attachBusy = false, attachTitle = "Attach a file - or paste or drop one here",
  chips = null, input, onMic, extra = null, send }) {
  const Root = root, pick = useRef(null);
  return <Root className="tq-aui-composer" data-tq-one-box="" {...rootProps}>
    <Tooltip title={attachBusy ? "Uploading…" : attachTitle}><span>
      <IconButton size="small" className="tq-aui-attach" data-tq-box-attach="" aria-label={attachTitle.replace(/ - .*/, "")} disabled={attachBusy} onClick={() => pick.current?.click()}
        sx={{ width: 30, height: 30, p: 0, color: "var(--tq-secondary, #6e685f)" }}><AttachFileIcon sx={{ fontSize: 18 }} /></IconButton></span></Tooltip>
    <input ref={pick} hidden type="file" multiple accept={accept} onChange={(e) => { onFiles([...(e.target.files || [])]); e.target.value = ""; }} />
    {/* ...what goes with the words, in one line inside the box, left of them: the item it came from first, then the files (AttachRow) */}
    {chips && <AttachRow className="tq-aui-attachments" sx={INLINE_CHIPS}>{chips}</AttachRow>}
    {input}
    <MicButton size={18} sx={{ color: "var(--tq-warning, #6b5f45)", p: 0.5 }} onText={onMic} />
    {extra}
    {send}
  </Root>;
}
export const micInto = (put) => (t) => put((w) => (w.trim() ? `${w.trimEnd()} ${t}` : t));   // dictated words after the typed ones

// ...a task's chat before its first agent, an item's Agent tab, the coding chat: words in a textarea, files through usePromptImages
// (`chips`: what it goes with; `cannot`: why a file cannot go; `extra`: the box's own buttons; `emptyOk`: Send with nothing typed - the item alone
// is the job; `onSend` null: a box whose press is the form's own (RunForm's Start), so Enter adds nothing and no Send is drawn)
export function PromptBox({ text, setText, pics, busy = false, onSend = null, placeholder, label = "", title, chips = null, inputRef = null, cannot = null,
  boxAttrs = {}, sendAttrs = {}, extra = null, sendOff = false, emptyOk = false, autoFocus = false }) {
  const empty = !emptyOk && !(text.trim() || pics.imgs.length), any = !!(chips || pics.imgs.length || pics.busy || pics.err), go = () => onSend?.();
  return <OneBox rootProps={{ "data-tq-prompt-box": "", onSubmit: (e) => { e.preventDefault(); go(); }, ...pics.drop, style: { flexShrink: 0, minWidth: 0 } }}
    onFiles={pics.add} accept={pics.files ? undefined : IMAGE_ACCEPT} attachBusy={pics.busy} attachTitle={`Attach ${pics.files ? "a file" : "an image"} - or paste or drop one here`}
    chips={any ? <>{chips}{fileChips(pics, cannot)}{fileState(pics)}</> : null}
    input={<Box component="textarea" className="tq-aui-input" ref={inputRef} {...boxAttrs} rows={1} value={text} disabled={busy} autoFocus={autoFocus} onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) { e.preventDefault(); go(); } }}
      placeholder={placeholder} aria-label={label} />}
    onMic={micInto(setText)} extra={extra}
    send={onSend && <button type="submit" className="tq-aui-send" {...sendAttrs} aria-label={label} title={title} disabled={busy || pics.busy || empty || sendOff}>
      {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : <SendIcon fontSize="small" />}</button>} />;
}
