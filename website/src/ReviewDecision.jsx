// ONE DECISION, WHEREVER IT IS SHOWN. What they wrote, what we would say back, and the verdict
// buttons - extracted from the review queue so the task page can hold the decision instead of
// sending you to another tab to make it (2026-09-22). A proposal (a playbook, a setting, an
// action) renders through the same card: proposalPresentation() gives it its own title, its
// destination and its own labels, and nothing is sent to a sender.
import React, { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Alert, Box, Button, Typography, Menu, MenuItem } from "@mui/material";
import api from "./api";
import ReplyFiles from "./ReplyFiles.jsx";
import { holdInView } from "./inView.js";
import { filesPromised, filesShort } from "./replyFiles.js";
import { outcomeOf, proposalFrom, proposalPresentation, receiptOf, resultOf, reviewStatusLabel, reviewText } from "./reviewProposal.js";
import { actionFor, cardOf, changed, faceOf, fieldsOf, lengthOf, pressable as actPressable, stateOf, textKey, valuesOf, viaBrowserSaid, wordsOf } from "./actionCard.js";
import { asLive, MovedPast } from "./PassedCard.jsx";
import { FileDialog } from "./PublishedPages.jsx";
import { withoutSignature } from "./signature.js";
import { OFFER_HINT, OFFER_LABEL, useCloseoutState } from "./closeoutState.js";
import { PANEL2, BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { timeAgo, cleanText, splitQuoted } from "./ui.jsx";
import { deliveryBcc, deliveryCc, deliveryFiles, deliveryMeta, deliverySubject, needsAddress, pressWords, replyContext, sentCardOf, sentTo } from "./replyDelivery.js";
import { cardLook, endPress, hearMarks, markOf, pressMark, sentMark, sentSaid, sentTitle, WENT } from "./sentLine.js";
import { fmtDateTime } from "./dates.js";
import { acted, announce, repeatClick, useLit, useVerbs } from "./actionRow.js";
import { useFoldBar } from "./foldBar.js";
import { hint as btnHint, label as btn } from "./buttons.js";
import { boxText, editAfterRefile, useDraftJob } from "./replyDraft.js";
import ApprovalInterrupt from "./ApprovalInterrupt.jsx";
import { interruptOf, resolveInterrupt } from "./approvalInterrupt.js";
import { draftState, failureHead, failureWhy, replySendFailure, reviewDeliveryState, savedSendFailure, sendFix } from "./sendState.js";
import { failLine, landed, landedSend, press } from "./press.js";
import { openAppLink } from "./appLinks.js";
import { setupType } from "./connectSetup.js";
// ...the connection's own setup under the card that needs it: the Connections page's code, loaded only when a Connect is pressed
const ConnectSetup = React.lazy(() => import("./ConnectSetup.jsx"));
const setupUnder = (href, onClose, onConnected) => href && <React.Suspense fallback={null}>
  <ConnectSetup href={href} onClose={onClose} onConnected={() => { onClose(); onConnected(); }} /></React.Suspense>;
// Connect brings the connection's setup up under the card, where it is one connection's card; any other link still opens where it points
const connectRun = (href, setAt) => () => (setupType(href) ? setAt((x) => (x ? "" : href)) : openAppLink(href));
// ...its setup comes up UNDER the card: the chat keeps what he pressed where it stood (GeneralWorkspace's fold), never its end
const OPENS_UNDER = { "data-tq-opens-under": "" };
import { FOCUS_RING, pressable } from "./pressable.js";
import { runOperation } from "./taskOps.js";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { blankAsk, blankRefusal, blankSpans } from "./blanks.js";
import { outputRow } from "./taskOutputs.js";
import { ReviewCard } from "./Artifact.jsx";
const hint = btnHint;

// What they wrote, above what we would say back. The queue used to show only the draft: you
// approved an answer without the question in front of you, or opened the task to find it. Four
// lines of the inbound message, the rest one click away.
const Inbound = ({ r }) => {
  const [full, setFull] = useState(false);
  const { latest } = splitQuoted(cleanText(r.Preview || ""));
  if (!latest) return null;
  const long = latest.length > 360 || latest.split("\n").length > 4;
  return (
    <Box sx={{ mb: 1, px: 1.25, py: 0.85, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, borderLeft: "3px solid var(--tq-border-strong, #6f8a6e)" }}>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.25 }}>
        {r.FromName || r.FromEmail || "they"} wrote{r.SentAt ? ` · ${timeAgo(r.SentAt)}` : ""}
      </Typography>
      <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", lineHeight: 1.5,
        ...(full || !long ? {} : { display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>
        {latest}
      </Typography>
      {long && (
        <Typography variant="caption" onClick={() => setFull((f) => !f)}
          sx={{ color: "var(--tq-link, #55697a)", fontWeight: 600, cursor: "pointer", display: "block", mt: 0.35, "&:hover": { textDecoration: "underline" } }}>
          {full ? "less ↑" : "the whole message ↓"}
        </Typography>
      )}
    </Box>
  );
};

export const InvoiceLine = ({ meta }) => (
  <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 1, px: 1.25, py: 0.8,
    bgcolor: "var(--tq-inset, #eef1ec)", border: "1px solid var(--tq-border, #d9e0d6)", borderRadius: 1.5 }}>
    <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>{meta.customer}</Typography>
    <Typography variant="caption" sx={{ color: INK }}>${Number(meta.amount || 0).toFixed(2)}</Typography>
    <Typography variant="caption" sx={{ color: DIM }}>last month: {meta.previous_amount == null ? "—" : `$${Number(meta.previous_amount).toFixed(2)}`}</Typography>
    {meta.invoice_number && <Typography variant="caption" sx={{ color: DIM }}>Zoho {meta.invoice_number}</Typography>}
  </Box>
);

// A CALENDAR ANSWER (calwrite.py) says what the calendar will be told - the act, the meeting, the time, and what it clashes with -
// where an email says who it goes to. The box under it is the note that rides along, and may be left empty.
// THE OWNER'S EDIT OUTLIVES THE CARD (the 2026-10-25 sweep): it lived in the card's own state, so a look at Reports or another row - anything
// that drew the task again - put the filed draft back and " Regards, Alex" was gone, with nothing said. Held per draft as filed: a new draft
// (Redraft, the server's own) starts from itself.
// ...and the CC the owner added with it (the overnight walk, 2026-10-27: Priya looped in, a look at another row, and the CC was back to
// "+ loop someone in" while the edited words stood - Send would have gone without her)
// ...and ONE DRAFT IN TWO PLACES reads the same in both (the agent's draft, 2026-11-02: Close out and the pop-up over the terminal): an edit in
// either is told to the other card on the same draft, so a Send from either sends what the owner last typed
const edits = new Map(), heard = new Set();
const heldEdit = (r) => { const e = edits.get(r?.ReviewId); return e && e.filed === reviewText(r) ? e : null; };
const hold = (r, part) => {
  const e = { text: null, cc: null, bcc: null, subject: null, ...heldEdit(r), ...part, filed: reviewText(r) };
  if (e.text == null && e.cc == null && e.bcc == null && e.subject == null) edits.delete(r.ReviewId); else edits.set(r.ReviewId, e);
  heard.forEach((f) => f(r.ReviewId));
};
// SEND AND CLOSE OUTLIVES THE PRESS (the owner, 2026-11-03): a send nobody could confirm comes back as Check delivery or Send anyway, and the
// card may be drawn again meanwhile - which of Close out's two sends was pressed is held per draft, so the confirmed send still closes, or not
const closing = new Set();

const CAL_ACT = { accept: btn("accept_invite"), decline: btn("decline_invite"), propose: "Propose", schedule: "Invite" };
// ...and ITS PRESS SAYS THE ACT (the owner, 2026-11-08: "fix it like email or all other actions"): the card the agent set up is pressed as
// what it does - Accept, Decline, Propose this time, Send invite - where an email's says Send
export const CAL_PRESS = { accept: btn("accept_invite"), decline: btn("decline_invite"), propose: "Propose this time", schedule: "Send invite" };
// ...and an invite's other answers beside it, each setting that one up instead (POST /api/messages/{mid}/calendar - the row's own draft; a new
// time with none named is the first free one): nothing reaches the calendar before the lit press
const CAL_OTHER = { accept: btn("accept_invite"), decline: btn("decline_invite"), propose: btn("propose_time") };
// WHAT A SHARE SHARES, OVER ITS PRESS (the owner, 2026-11-08: "the agent shows the dashboard inline in the chat"): the dashboard as Reports
// draws it, from its last run - lazy, so a card with none never loads the charts
const Dashboard = React.lazy(() => import("./dashboard/Dashboard.jsx"));
// ...AS LAST READ, ON ITS FIRST FRAME (recorded 2026-11-12: each time the task was opened its card stood at "Loading…" and then grew by the
// dashboard's ~370 px, the chat above it moving up by as much): the read still follows, and what it brings is the newest word
const DASHBOARDS = new Map();
export function SharedDashboard({ report, title }) {
  const [got, setGot] = useState(() => DASHBOARDS.get(report) || null);
  useEffect(() => { let live = true; setGot(DASHBOARDS.get(report) || null);
    api.get(`/api/dashboards/${report}`).then(({ data }) => { DASHBOARDS.set(report, data); if (live) setGot(data); }).catch(() => live && setGot((g) => g || {}));
    return () => { live = false; }; }, [report]);
  // ...ITS ROOM HELD FROM THE FIRST FRAME (decided 2026-11-12, the sweep's task 32 on a first open: "Loading…" 26 px, then the dashboard 420 px,
  // everything above it moving up): while it is read, and with its charts, it is the dashboard's whole height; only "not run yet" is a line
  const room = !got || got.data ? { height: 420 } : { maxHeight: 420 };
  return <Box data-tq-shared-dashboard={report} sx={{ mb: 1, border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden", ...room, overflowY: "auto", boxSizing: "border-box" }}>
    <Typography variant="caption" sx={{ display: "block", px: 1.25, pt: 0.75, color: INK, fontWeight: 600 }}>{title || "Dashboard"}
      <Box component="a" href={`#report=${report}`} sx={{ ml: 1, color: "var(--tq-link, #55697a)", fontWeight: 400 }}>Open it</Box></Typography>
    {got?.data ? <React.Suspense fallback={null}><Dashboard spec={got.config} data={got.data} /></React.Suspense>
      : <Typography variant="caption" sx={{ display: "block", px: 1.25, pb: 0.75, color: FAINT }}>{got ? "It has not run yet." : "Loading…"}</Typography>}
  </Box>;
}

// A SEND PRESSED OVER A BLANK ASKS ONCE (the owner, 2026-11-08): one inline line under the buttons, blanks.js's own words, and the press goes
// only on Send anyway - every card that sends a draft draws this one
export const BlankAsk = ({ line, onSend, onCancel }) => (
  <Alert severity="warning" data-tq-blank-ask="" sx={{ mt: 0.75, alignItems: "center" }}
    action={<Box sx={{ display: "flex", gap: 0.5 }}>
      <Button size="small" color="inherit" data-tq-blank-send="" onClick={onSend}>{btn("approve", "unknown")}</Button>
      <Button size="small" color="inherit" onClick={onCancel}>Cancel</Button></Box>}>{line}</Alert>
);

// `onOpenTask` is optional: on the task page you are already there.
// `closeout` is the task's pending close-out (merge the PR, close the issue): given beside its reply, the two are
// ONE decision on this card, and the close-out runs first (verdicts.decide's reply_text).
// `onMarkDone`: the task's own Mark done (TaskPage puts the task down at the press) - a reply draft's other choice.
// `onRemind`: the task's own Remind me - a close-out's "not now" (the owner, 2026-10-02: Not yet IS remind me later).
// `onSent`: a send or close-out that went through - the task page reads the task and, when that closed it, walks on.
// `closeOnSend`: the task page's Close out (the owner, 2026-10-29: "wait until the send actually succeeds, then close the task"): a reply
// that went is the close too - onSent({ closes }) says so, only after the server's receipt; a send that failed leaves it open, its error here.
// `toRow`: the decision's buttons are drawn by the action row above the chat line (layout B), not here - the same handlers, registered.
// A chat reply that has to carry a file is the same card by email instead (U17; wrapup.by_email) - wherever the card is drawn.
// `went`: on a card whose Send went, what the press did to the task beside it ({closing, kept}, TaskPage sentHere) - its sent card says it.
// ...an act a connector declares a card for (a post, a tracker comment) is drawn as that card (ActionCard.jsx), wherever its proposal shows -
// the same decide road, its own face
// `past`: the chat moved past it - the card as it stood while it waited, every button greyed, nothing registered on the row (MovedPast)
// ...AND SEND AND CLOSE ONLY ON A LINE'S LAST CARD (the judge's walk, 2026-11-19: "Send and close" the main button on "1 of 4"): while cards wait
// behind this one in the task's line (cardqueue: queue.held), closing the task with this send would close over them - the conversation says so
export const MoreCardsCtx = React.createContext(false);
export default function ReviewDecision({ past = false, ...props }) {
  const r = past ? asLive(props.review) : props.review, act = cardOf(r);
  return act ? <ActReview row={act} tid={r?.TaskId} onChanged={props.onChanged} past={past} />
    : <MovedPast on={past}><Decision {...props} review={r} past={past} toRow={!past && props.toRow} /></MovedPast>;
}
function Decision({ review: r, closeout, onChanged, onOpenTask, onMarkDone = null, onSent = null, onRemind = null, closeOnSend = false, toRow = false, simulated = false, onDrop = null, why = "", went = null, past = false }) {
  // ...a card moved past shows the words it was filed with, never an edit held for the live card of the same review
  const heldOf = (x) => (past ? null : heldEdit(x));
  const [text, setTextNow] = useState(() => heldOf(r)?.text ?? null);   // the owner's edit; null means "the draft as filed"
  const setText = (v) => { hold(r, { text: v ?? null }); setTextNow(v); };
  const [cc, setCcNow] = useState(() => heldOf(r)?.cc ?? null);         // null means "the CC the draft was filed with"
  const setCc = (v) => { hold(r, { cc: v ?? null }); setCcNow(v); };
  // ...and BCC and the subject, held the same way (the owner, 2026-11-08: one email card, every field editable, edits go out with Send)
  const [bcc, setBccNow] = useState(() => heldOf(r)?.bcc ?? null), [subj, setSubjNow] = useState(() => heldOf(r)?.subject ?? null);
  const setBcc = (v) => { hold(r, { bcc: v ?? null }); setBccNow(v); };
  const setSubj = (v) => { hold(r, { subject: v ?? null }); setSubjNow(v); };
  const [ccOpen, setCcOpen] = useState(false), [bccOpen, setBccOpen] = useState(false), [cmdOpen, setCmdOpen] = useState(false);
  // ...a change's new words as he leaves them, box by box (proposals.as_left saves exactly these), and its marks of where they change on or off
  const [words2, setWords2] = useState({}), [marksOn, setMarksOn] = useState(true);
  const rNow = useRef(r); rNow.current = r;
  useEffect(() => { const f = (id) => { if (id !== rNow.current.ReviewId) return; const e = heldOf(rNow.current); setTextNow(e?.text ?? null); setCcNow(e?.cc ?? null);
    setBccNow(e?.bcc ?? null); setSubjNow(e?.subject ?? null); };
    heard.add(f); return () => { heard.delete(f); }; }, []);
  // SENT STAYS SENT until the page's re-read takes the card away (the owner, 2026-10-26: "when you hit send on close out email it grey's
  // out and then turns blue again then closes"): busy still ends when the decide answers, as 2026-10-18 ruled, but the button after it
  // reads "Sent" and stays off - a blue Send again over a reply already gone invited a second press
  // ...and the send's press is the REVIEW'S (sentLine.markOf, 2026-11-17): this card drawn again mid-send, or after it went, reads where it stands
  // (the demo's own review is its own: its number may be a real one's)
  const rid = simulated ? `demo:${r.ReviewId}` : r.ReviewId, mark = useSyncExternalStore(hearMarks, () => (past ? null : markOf(rid)), () => (past ? null : markOf(rid))), look = cardLook(r, mark);
  const setMark = (m) => pressMark(rid, m);
  const [busyHere, setBusyHere] = useState(false);
  const setBusy = (b) => { setBusyHere(b); if (!b) endPress(rid); };
  const setSent = (s) => setMark(s ? { state: "sent" } : null);
  const sent = look === "sent", busyNow = busyHere || look === "going";
  const busy = busyNow || sent;
  // ...AND THE PRESSED BUTTON SAYS WHAT IS HAPPENING (the owner, 2026-11-12: "the card button should say sending then close"): a spinner
  // beside "Sending…" while it goes, then "Sent" - in place, never a line above the card
  // (the row's verbs read the words; the card's own buttons draw them with the spinner - `sentOr` is the word, its look is `spinning`)
  // ...in the card's own words: an invite's Accept says Accepting… then Accepted (pressWords)
  const pw = pressWords(r);
  const sentOr = (w) => (sent ? pw.done : w);
  // ...said by the send that was pressed: Close out has two, and "Sending…" stood on both
  const [pressedHere, setPressed] = useState("approve"), pressed = mark?.pressed || pressedHere;
  const [err, setErr] = useState("");
  const [setupAt, setSetupAt] = useState("");      // the connection whose setup stands under the card (ConnectSetup): its Connect pressed
  const [sendErr, setSendErr] = useState("");       // approved, but the channel refused it
  // ...and after a reload the review says so itself (savedSendFailure) - until the owner closes the line, or presses again
  const [shutErr, setShutErr] = useState(false);
  useEffect(() => { setShutErr(false); }, [r.ReviewId, r.DecidedAt]);
  const [interrupt, setInterrupt] = useState(null); // PW-239: the click that did not send
  const [compare, setCompare] = useState(null);     // the refreshed draft, shown beside the owner's edit
  // A NEW DRAFT UNDER THE OPEN CARD IS SHOWN (editAfterRefile, 2026-11-04): the Assistant's rewrite landed and an emptied box stayed empty,
  // Send grey, under "✓ Rewritten" - the edit followed the card, not the draft it was made on. Another review in the same card starts from its own.
  const filed = reviewText(r), was = useRef({ rid: r.ReviewId, filed });
  useEffect(() => {
    const w = was.current; was.current = { rid: r.ReviewId, filed };
    if (w.rid !== r.ReviewId) { const e = heldOf(r); setTextNow(e?.text ?? null); setCcNow(e?.cc ?? null); return; }
    if (w.filed === filed) return;
    const keep = !!interrupt || compare?.reviewId === r.ReviewId;
    if (keep && text != null) hold(r, { text });           // the owner's edit beside the refreshed draft stays theirs, held for the new one
    setTextNow(editAfterRefile({ text, held: heldOf(r), keep }));
  }, [r.ReviewId, filed]);   // eslint-disable-line react-hooks/exhaustive-deps
  // A BLANK LEFT IN IT (the owner, 2026-10-30): Send pressed over a "[REASON]" says "Fill in [REASON] first" under the button, and the
  // line follows the box - it names what is still blank as the owner types, and is gone once nothing is
  const [fillIn, setFillIn] = useState(false);

  // ...a send that went is Sent whatever a read a beat behind still says of its delivery (2026-11-17: the frozen form came back over it)
  const delivery = reviewDeliveryState(r);
  const filedDelivery = delivery.frozen ? { ...r, Deliver: JSON.stringify(delivery.envelope) } : r;
  const proposal = proposalPresentation(r);
  const changedWords = Object.fromEntries((proposal?.texts || []).filter((t) => words2[t.key] != null && words2[t.key] !== t.now).map((t) => [t.key, words2[t.key]]));
  // A REPLY OPENED AT ONCE is drawn before its draft exists (replyDraft.js, 2026-10-01): "Drafting…" until the model is done,
  // then the task is read again and the draft is in the box; one that could not be written says why here
  const jobNow = useDraftJob(r.ReviewId), job = past ? null : jobNow;
  // A REDRAFT IS NOT A SEND (the email walk, 2026-10-29: Redraft turned Send into "Sending…"): its own state holds every button off
  // while the model writes, and only Redraft says what is happening
  const [redrafting, setRedrafting] = useState(false);
  // ...and one the SERVER is still writing (`Drafting`: the arrival's own) is followed and waited on, not shown as nothing coming (2026-11-03)
  const drafting = job?.state === "drafting" || redrafting;
  // the signature that goes under this email (signatures.py) is in the box: an empty one opens on it, a draft gets it once - and
  // a box holding only it is still "write the reply first"
  // ...but while the AI writes it the box is empty under its spinner, reading "Drafting…" - the signature alone read as nothing coming
  const value = delivery.frozen ? delivery.body : boxText({ text, draft: reviewText(r), drafting, signature: r.Signature });
  const words = withoutSignature(value, r.Signature);
  const ccNow = delivery.frozen ? deliveryCc(filedDelivery) : cc ?? deliveryCc(r);
  const bccNow = delivery.frozen ? deliveryBcc(filedDelivery) : bcc ?? deliveryBcc(r);
  // the subject the card shows: the owner's, else the envelope's (an agent's email), else "Re:" the mail it answers
  const subjFiled = deliverySubject(r), subjNow = delivery.frozen ? deliverySubject(filedDelivery) : subj ?? subjFiled;
  const meta = deliveryMeta(r);
  const isEmail = String(r.Channel || meta.channel || "").toLowerCase() === "email";     // the one email card: To, CC, BCC, Subject, files
  // ...whose To holds no address asks for one, and nothing sends until it has it (slots.address_for found nobody)
  const needsTo = isEmail && !proposal && !delivery.frozen && meta.kind !== "calendar" && needsAddress(r);
  const isCal = meta.kind === "calendar";             // an invite answered or a meeting booked: its note may be empty
  const newMeeting = isCal && meta.act === "schedule";
  const [switching, setSwitching] = useState("");
  // ...an invite's answer set up instead: drafted in its place (calwrite.draft replaces the pending one), the card read again
  const answerInstead = async (act) => {
    setSwitching(act); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${r.MessageId}/calendar`, { act });
      if (!data?.ok) setErr(data?.say || "That answer could not be set up."); else onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "That answer could not be set up."); }
    finally { setSwitching(""); }
  };
  const co = closeout && !proposal ? proposalPresentation(closeout) : null;
  // the slots in a REPLY's box (blanks.js): a proposal's text is the agent's act, and a frozen one is past changing
  const blanks = proposal || isCal || delivery.frozen ? [] : blankSpans(value);
  const fillLine = fillIn && blanks.length ? blankRefusal(value) : "";
  // a reply to a GitHub PR/issue IS a comment on it, so the close-out carries it whatever the replies switch says
  const carried = !!co && String(r.Channel || "").toLowerCase() === "github";
  // can THIS draft leave: the channel's answer (capabilities.js, live as connections change) and the row's own - r.CanSend also
  // knows a draft with nobody to go to
  const caps = useCapabilities();
  const canSendIt = draftCanSend(caps, r);
  const sendable = canSendIt || carried;
  // one of the task's emails (slots.py) is not its close-out: sending it ticks that email and closes nothing
  const isSlot = r.Kind === "slot";
  const onTask = !proposal && !!r.TaskId && r.Kind !== "clarification" && !isSlot;
  // THE BUTTONS THAT ACT ON THE DRAFT ARE UNDER THE DRAFT (the owner, 2026-10-06: "any button that relates to a piece of a task ... put
  // the button right there, if related to task in general then put button on bottom"): Send where this channel carries it, Mark done
  // (with the draft copied) where it cannot - and Redraft beside them. ONE NAME for the send, wherever (buttons.json), and it only
  // sends: SENDING AND CLOSING ARE TWO STEPS (the owner, 2026-10-18) - the task's own Mark done is the close
  // ...and in Close out TWO SENDS (the owner, 2026-11-03: "button send and close and send without closing so task stays open on send"): Send and
  // close is the one that closes, and the primary; Send sends and the task stays open, as it does everywhere else
  const closesIt = closeOnSend && onTask && !!onSent;
  // ...whatever its agent is doing (the owner, 2026-11-11): Send and close is his close, and the server stops the agent under it
  // ...a calendar card's press is its act, and a share's names who it is for (sharing.agent_share's `share`)
  const calWord = isCal ? CAL_PRESS[meta.act] : "", shareTo = String(meta.share?.to || "").split(/\s+/)[0];
  const sendWord = calWord || (shareTo ? `Share with ${shareTo}` : btn("approve")), closeWord = calWord ? `${calWord} and close` : btn("send_close");
  const closeCo = btn("send_close", "closeout"), stays = `the task stays open until you ${btn("close")}`;
  const closeThen = "then the task closes";
  // A CHAT REPLY THAT PROMISES A FILE (U17): WhatsApp and the other chats carry words only, so a send went out with the promise and
  // without the file. The move becomes answering by email with the file; sending the words alone stays beside it.
  const chatFile = !proposal && !co && !isSlot && !r.Stale && !delivery.frozen && canSendIt
    && String(r.Channel || "email").toLowerCase() !== "email" && (deliveryFiles(filedDelivery).length > 0 || filesPromised(r));
  const thenLine = delivery.frozen ? "" : simulated ? "This approves the fictional reply and completes the demo task. No email is sent."
    : co ? (closesIt && sendable && !simulated && !r.Stale ? `${closeCo} ${co.then}, then sends your reply to ${replyContext(r)} - ${closeThen}; ${co.approveLabel} does the same and ${stays}.`
      : `${co.approveLabel} ${co.then}${sendable ? `, then sends your reply to ${replyContext(r)}` : ""} - and only that; ${stays}.`)
    : chatFile ? `A ${r.Channel} message cannot carry a file. Reply by email with the file, or send the words alone.`
    : isCal && !r.Stale ? (closesIt ? `${closeWord} tells the calendar, with the note above if there is one - ${closeThen}; ${sendWord} tells it and ${stays}.`
      : `${sendWord} tells the calendar, with the note above if there is one - ${stays}.`)
    : onTask && !r.Stale && canSendIt ? (closesIt ? `${closeWord} sends this to ${replyContext(r)} - ${closeThen}; ${sendWord} sends it and ${stays}.`
      : `${sendWord} sends this to ${replyContext(r)} - ${stays}.`) : "";
  // each send's hover says exactly what it does here
  const moreCards = React.useContext(MoreCardsCtx);
  const twoSends = closesIt && !moreCards && !simulated && !co && !proposal && canSendIt && !r.Stale && !chatFile && !delivery.frozen;
  const copying = ccNow.length && !isCal ? `, copying ${ccNow.length}` : "", to = isCal ? "Tells the calendar" : `Sends this to ${replyContext(r)}`;
  const closeTitle = `${to} - ${closeThen}`, sendTitle = `${to} - ${stays}`;
  // ...and A CLOSE-OUT'S TWO (the owner, 2026-11-03): Approve and close - the merge or the issue's close, then the reply, then the task's close -
  // and Approve, which does the same and leaves the task open. Only where the reply rides with it: with none, Approve never closed the task
  const twoApproves = !!co && !r.Stale && closesIt && sendable && !simulated && !delivery.frozen;
  const coDoes = co ? `${co.then}, then sends your reply to ${replyContext(r)}` : "";
  const going = busyNow && !sent && ["approve", "send_close"].includes(pressed);
  const closeCoTitle = `${closeCo} ${coDoes} - ${closeThen}`, coTitle = `${co?.approveLabel} ${coDoes} - ${stays}`;
  // ...either pair keeps its line, and folds its open one when tight
  const paired = twoSends || twoApproves;
  // A DRAFT THAT CANNOT LEAVE FROM HERE is copied (the owner, 2026-10-22: "buttons do the talking"): Copy beside Redraft, which
  // copies and closes nothing; why it cannot be sent is the Copy button's hover - the three lines that said so are gone
  const [copied, setCopied] = useState(false);
  const draftRef = useRef(null);
  useEffect(() => { setCopied(false); }, [r.ReviewId, value]);
  const copyTitle = `${btnHint("copy")}. It cannot be sent from here - ${r.SendBlock || "this channel cannot be replied to"}.`;
  const copyIt = async () => {
    announce(no("copy"));
    try { await navigator.clipboard.writeText(value); setCopied(true); }
    catch { const el = draftRef.current?.querySelector("textarea"); el?.focus(); el?.select(); }   // a refused clipboard: the text, selected, to copy by hand
    finally { acted(no("copy")); }
  };
  const [coFail, setCoFail] = useState(null);       // the close-out itself refused: nothing was sent ({offers} = what fits instead)
  const [said, setSaid] = useState("");              // what Update branch / Re-run checks just did
  // THE CARD READS GITHUB FIRST (closeoutState.js): Close out is live only when this repo's rules let it merge now
  const coRid = closeout?.ReviewId || (proposal?.kind === "closeout" ? r.ReviewId : null);
  const { gh, reload: reloadGh, act } = useCloseoutState(past ? null : coRid);
  const blocked = !!gh && !gh.ok;
  const off = busy || drafting;
  useEffect(() => {
    if (job?.state === "done") onChanged?.();
    if (job?.state === "failed") setErr(`The draft could not be written - ${job.error}. Write it here, or Draft with AI again.`);
  }, [job]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ...the press ASKS ONCE, before anything is posted (the owner, 2026-11-08: Send stays lit): "This still has [ROOM]. Send anyway?" with Send
  // anyway / Cancel under the buttons, the cursor on the first blank. `asked`: the press it holds - replayed as it was, with the text as it is
  const [asked, setAsked] = useState(null);
  useEffect(() => { setAsked(null); }, [value]);
  const askBlank = (press) => {
    if (!blanks.length) return false;
    setAsked({ line: blankAsk(value), ...press });
    const el = draftRef.current?.querySelector("textarea[data-tq-draft]");
    if (el) { el.focus(); el.setSelectionRange(blanks[0][0], blanks[0][1]); }
    return true;
  };

  // `close`: false on the pair's plain Approve - the close-out and the reply go, and the task stays open (twoApproves)
  const decideBoth = async (verb, close = true, blanksOk = false) => {
    if (delivery.frozen) return;
    // the reply that rides with the close-out is asked about before the merge, not after it (verdicts.decide refuses it there too)
    if (!blanksOk && verb !== "reject" && sendable && words.trim() && askBlank({ both: true, verb, close })) return;
    setAsked(null);
    const id = verb === "approve" && close && twoApproves ? "send_close" : verb;
    announce(no(id)); setPressed(id); if (verb !== "reject") setMark({ state: "going", pressed: id });
    setBusy(true); setErr(""); setSendErr(""); setCoFail(null);
    try {
      const out = await press(api, closeout.ReviewId,
        { verb, reply_text: verb !== "reject" && sendable && words.trim() ? value : null, cc: sendable ? ccNow : null, blanks_ok: blanksOk,
          ...(closesIt && close && verb !== "reject" ? { closes: true } : {}) }), data = out.data;
      // no answer in a minute: the review's own delivery state says where it stands (press.js `unknown`) - never a line of ours
      if (!data) { if (out.kind === "unknown") onChanged?.(); else setErr(out.why || "That didn't go through - nothing was sent. Try the button again."); setBusy(false); return; }
      if (data.blanks?.length) { setFillIn(true); if (!blanks.length) setErr(data.send_error); }
      // refused before anything happened is not "approved, but it did not send"
      else if (!data.ok && data.send_error) setCoFail({ text: data.send_error, offers: data.offers || [] });
      else if (data.send_error) setSendErr(replySendFailure(data));
      // WAIT FOR IT, THEN MOVE ON (the owner, 2026-10-02): the close-out landed with no error, so the task may be closed now
      // ...the press is over when the server answers: the re-read after it is the page's, and "Sending…" waited on it too
      // ...and the reply that went with it closes the task, on the task page (closeOnSend) - the merge alone does not
      else if (data.ok && verb !== "reject" && onSent) { setSent(true); setBusy(false); await onSent({ closes: closesIt && close && !!data.reply?.ok }); return; }
      reloadGh(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "That didn't go through - nothing was sent. Try the button again."); }      // what the page did after the answer (onSent), not the press
    finally { acted(no(id)); }          // the Advisor reads the item again: what it advised has been done, or failed
    setBusy(false);
  };

  // Approving IS sending, so a send that failed has to say so HERE, the moment you click - it
  // used to return quietly and leave a "NOT SENT" line in the task history for you to find later.
  // `close`: Close out's Send and close - the send, then the task's close once the server's receipt says it went (onSent closes). Check
  // delivery and Send anyway pass nothing: they finish the press that froze the draft, held in `closing`
  // ...the email card's BCC and a changed subject, on the send only
  // ...and a new meeting's title, the one field of its invite the card edits (calwrite.deliver reads the envelope's subject)
  const envelopeEdits = (verb) => verb !== "approve" || proposal || delivery.frozen ? {}
    : isEmail ? { bcc: bccNow, subject: subj != null && subj !== subjFiled ? subj : null }
    : newMeeting ? { subject: subj != null && subj !== subjFiled ? subj : null } : {};
  // `always`: "Always approve this step" on a routine's write card - it runs now, and that step as saved runs unpressed after (flow.grant)
  const decide = async (verb, anyway = false, close = undefined, blanksOk = false, always = false) => {
    if (delivery.active || (delivery.frozen && verb !== "approve")) return;
    if (verb === "approve" && !blanksOk && askBlank({ verb, anyway, close })) return;
    setAsked(null);
    if (close !== undefined) { if (close) closing.add(r.ReviewId); else closing.delete(r.ReviewId); }
    const shut = closing.has(r.ReviewId);
    announce(no(verb === "approve" && shut ? "send_close" : verb));
    setPressed(verb === "approve" && shut ? "send_close" : verb);
    if (verb === "approve") setMark({ state: "going", pressed: shut ? "send_close" : "approve" });
    setBusy(true); setErr(""); setSendErr("");
    try {
      const out = await press(api, r.ReviewId,
        { verb, final_text: verb === "approve" && !delivery.frozen ? value : null, ...(r.Kind === "action" ? { shown: proposalFrom(r) } : delivery.frozen ? {} : { shown: { to: meta.to ?? null } }),
          // only on the send: rejecting or "no reply needed" copies nobody on nothing
          cc: verb === "approve" && !proposal && !delivery.frozen ? ccNow : null, anyway, blanks_ok: blanksOk, ...envelopeEdits(verb),
          // ...Send and close says so WITH the send: the server closes as it goes, before the task's agent is told it went - told first, a
          // parked agent was working again by the time the page asked for the close, and the task stayed open (the agent walk, 2026-11-10)
          ...(closesIt && shut && verb === "approve" ? { closes: true } : {}),
          ...(always && verb === "approve" ? { always: true } : {}),
          // ...a change card's boxes he changed, by their keys (workflows.edit_change): what he edited is what is saved
          ...(verb === "approve" && Object.keys(changedWords).length ? { fields: changedWords } : {}) }), data = out.data;
      // NO ANSWER IN A MINUTE is not "nothing was sent": the server may be sending still. The card reads the review again and its
      // DeliveryState draws Sending… or Check delivery (reviewDeliveryState) - the check it already has, not a line of ours
      if (!data) { if (out.kind === "unknown") onChanged?.(); else setErr(out.why || "That didn't go through - nothing was sent. Try the button again."); setBusy(false); return; }
      if (data.ok && !data.send_error && verb === "approve") closing.delete(r.ReviewId);    // the press is over: the next one says again which send
      const it = interruptOf(data, r.ReviewId);
      if (it) { setInterrupt(it); onChanged?.(); setBusy(false); return; }
      // DECIDED ALREADY - answered in the chat itself (channels.retire_draft_answered_elsewhere), or by another window - is not a
      // delivery problem: it read "The reply was not sent ... correct the delivery problem" over a reply the owner had sent in Teams
      if (data.already) { onChanged?.(); setBusy(false); return; }
      // a blank the server found: the same line as the press's own (blanks.js) - never "the reply was not sent ... delivery problem"
      if (data.blanks?.length) { setFillIn(true); if (!blanks.length) setErr(data.send_error); setBusy(false); return; }
      // a close-out GitHub's state refused is "not now", with what fits instead - never "approved, but it did not send"
      if (data.refused) { setCoFail({ text: data.send_error || "", offers: data.offers || [] }); reloadGh(); }
      else if (data.send_error) setSendErr(replySendFailure(data));
      // Send / Approve is not put down at the press: it waits for the send so an error shows HERE, then the task page reads the
      // task again - still open, its Mark done the move now (the owner, 2026-10-02; 2026-10-18: a send never closes it)
      // ...and a close without sending (a chat's Mark done, which copies the draft) is a close: the task page reads it the same way,
      // finds it done and walks on - it stood on the table as "task · done" with no line over it (the matrix's verify, 2026-10-20)
      // ...and busy ends when the decide answers, not when that re-read does: behind a slow server "Sending…" outlived the send
      // ...and on the task page a send that went IS the close (closeOnSend, 2026-10-29): only here, after the receipt - never at the press
      // ...and only Send and close's (`shut`, the owner 2026-11-03): Close out's plain Send leaves the task open, as every other Send does
      // ...AND ONLY ON A RECEIPT THAT SAYS IT WENT (design round 5, I2: the page walked on from a Send and close with nothing sent): an answer
      // without its sent state reads the card again in place, never moves the page
      else if (data.ok && (verb === "approve" ? landedSend(data) : verb === "close_unsent" && r.Kind !== "slot") && onSent) {
        // ...with what went and where (`said`): the chat keeps the sent card in place, marked, while the task closes (TaskPage SentHere)
        setSent(verb === "approve"); setBusy(false); await onSent({ closes: closesIt && shut && verb === "approve" && (data.reply ? !!data.reply.ok : true),
          said: verb === "approve" ? { text: value, channel: r.Channel || "", to: sentTo(r), subject: deliverySubject(r), id: r.ReviewId, done: pw.sentAs } : null }); return;
      }
      // ...and a send with no page behind it - one of the task's emails - is Sent from its answer on too: its Send and Don't send lit again
      // until the re-read came (the walk, 2026-11-17)
      else if (data.ok && verb === "approve" && !proposal) setSent(true);
      // ...and an act's Approve that landed stays pressed until the re-read has it decided - never Approve lit again between (walk 9)
      else if (data.ok && verb === "approve") setMark({ state: "landed", pressed: "approve" });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "That didn't go through - nothing was sent. Try the button again."); }      // what the page did after the answer (onSent), not the press
    finally { acted(no(verb === "approve" && shut ? "send_close" : verb)); }
    setBusy(false);
  };

  // A held draft is one the session's findings will rewrite. Sometimes the sender needs telling
  // something today anyway - a reply stuck behind an agent that never finished is worse.
  // THE SAME CARD, BY EMAIL (walk 6, H7: "Reply by email with the file" opened Email a summary, an empty To and a second voice - the agent's
  // words, its files and the person gone): its words and files stay, bound to that person's email on the task (wrapup.by_email)
  const byEmail = async () => {
    setBusy(true); setErr("");
    try { const { data } = await api.post(`/api/reviews/${r.ReviewId}/by-email`); if (!data?.ok) setErr(data?.why || "It could not go by email."); else onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "It could not go by email."); }
    setBusy(false);
  };
  const release = async () => {
    if (delivery.frozen) return;
    setBusy(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/release`); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not release it"); }
    setBusy(false);
  };

  const redraft = async (e) => {
    // ...a double-click is ONE Redraft (the button stress, 2026-11-02): a draft written inside the double-click's 70ms was asked for again
    if (delivery.frozen || redrafting || repeatClick(no("redraft"), e)) return;
    announce(no("redraft"));
    setRedrafting(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/draft`); setText(null); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Redraft failed"); }
    finally { acted(no("redraft")); setRedrafting(false); }
  };

  // THE DECISION'S VERBS, one list for the card's buttons and the action row: what presses, what it says, when it is off
  const no = (id) => `${r.ReviewId}:${id}`;
  // with the row carrying the item, the dark button is the Advisor's pick on the bar (actionRow.rowOf): the draft's own stay outlined
  // ...and the Advisor's pick of this card's own move is lit HERE, where the button stands (rowOf's `lit`) - never a second one on the bar
  const lit = useLit();
  // ...AND IN VIEW: after a refused send the line said "redraft it" over a Redraft a scroll below the card's edge, under the strip
  // (the Advisor group's verify, 2026-10-19) - a lit move the owner cannot see is no move. It is brought into view once, when it lights.
  const movesRef = useRef(null);
  // ...and UNCOVERED (the matrix's phone pass, 2026-10-20): at 390px "nearest" left it under the docked strip and row - inView.js
  // reads what stands over it and scrolls it clear, and holds it there while the dock's line and row fill in; marked
  // [data-tq-lit] so the conversation's pin (AssistantView keepTable) holds it clear too, instead of pulling the card's top back.
  useEffect(() => {
    if (past || !lit.startsWith(`${r.ReviewId}:`)) return undefined;
    const el = movesRef.current?.querySelector(".MuiButton-contained");
    el?.setAttribute("data-tq-lit", "");
    const stop = holdInView(el);
    return () => { stop(); el?.removeAttribute("data-tq-lit"); };
  }, [lit, r.ReviewId]);
  // ...Close out's Send and close IS the primary (the owner, 2026-11-03: "make it the primary button"): filled as it stands, and it steps
  // back only while another move on this card is lit - an advised Send or Redraft - so one button is ever filled
  // ...and only for a move DRAWN beside it (the product audit, 2026-11-08): a lit Redraft this card does not draw left Send and close outlined
  // on one reply card and filled on the next - closeVariant, below, once the drawn moves are known
  // THE LINE NEVER WRAPS (the owner, 2026-10-23): with two sends it holds one line, and when they do not fit Send folds into a ▾ - and it
  // comes back out once there is room again. An advised Send stays in view (actionRow: the lit move)
  // ...and after Send, AN INVITE'S OTHER ANSWERS (the owner, 2026-11-15): on a phone "Propose this time and close", the ▾ and Accept / Decline
  // ran off the card's right edge. The line folds as every bar of fixed buttons does (foldBar.useFoldBar, the Tasks bar's road): Send first,
  // then the other answers, into the one ▾ beside the filled move - the card's own measure of its Send is gone
  const calOthers = isCal && CAL_OTHER[meta.act] && r.MessageId && r.Status === "pending" && !delivery.frozen ? Object.entries(CAL_OTHER).filter(([a]) => a !== meta.act) : [];
  const sendLit = lit === no("approve");
  const foldRanks = useMemo(() => (paired ? { ...(sendLit ? {} : { send: 1 }), ...Object.fromEntries(Object.keys(CAL_OTHER).map((a) => [`cal:${a}`, 2])) } : {}), [paired, sendLit]);
  const bar = useFoldBar(foldRanks, `${sendWord}|${closeWord}|${copying}|${busy}|${switching}|${calOthers.length}`), [sendAt, setSendAt] = useState(null);
  const setMoves = useCallback((el) => { movesRef.current = el; bar.ref(el); }, [bar.ref]);
  const folded = paired && !bar.shown("send");
  const rejectTitle = "Dismisses it - nothing runs and nothing is sent";
  const remindTitle = `${btnHint("defer")} - nothing is merged, closed or sent`;
  const doneTitle = `${btnHint("close")} - nothing is sent; the draft stays on it, to send later if you want`;
  // Redraft (Draft with AI while nothing is drafted): the same handler the in-card button has
  const canRedraft = !proposal && meta.kind !== "zoho_invoice" && !isCal && !isSlot;   // the redrafter writes a REPLY to the sender
  const redraftWord = r.DraftText || r.Stale ? btn("redraft") : btn("redraft", "none");
  const redraftLabel = redrafting && r.DraftText ? "Redrafting…" : drafting ? "Drafting…" : redraftWord;
  // the Advisor lit Redraft and said why: the warning and its button go over the draft (warnTop), not a line beside the buttons under it
  const warnTop = !!why && canRedraft && !r.Stale && !delivery.frozen && lit === no("redraft");
  // the alternative (Decline) sends WHAT IS IN THE BOX, edited or not - and with the box empty it just closes the pull request, sending nothing
  const altSends = sendable && !!words.trim();
  const altTitle = co?.alt ? `${co.alt.label} ${co.alt.then}${altSends ? ", then sends the text above exactly as you have it - edit it first if it reads as an accept" : ". The box is empty, so nothing is sent"}.` : "";
  // A SEND NOBODY CAN CONFIRM has two ways past it beside Check delivery, as in the chat (concierge.recover): Send anyway - the owner's
  // own word that a second copy is fine - and Mark done, for when it went. Only Check delivery was here (the rebuilt walk, 2026-10-18)
  const unconfirmed = delivery.state === "unknown" && !delivery.active;
  const sendAnyway = () => decide("approve", true);
  const doneAnyway = async () => {
    setBusy(true); setErr("");
    try { if (onMarkDone) await onMarkDone(); else { await runOperation(api, "task.complete", r.TaskId); onChanged?.(); } }
    catch (e) { setErr(e?.message || e?.response?.data?.detail || `${btn("close")} didn't go through.`); }
    setBusy(false);
  };
  // ITS CHANNEL IS NOT CONNECTED (the owner, 2026-11-08): the card says so and its one move is Connect, which opens that connection's card -
  // the draft waits as it is, and Send is back once it is connected (server: outbound.connect_fix, `Connect` on the review) - and a mail card
  // that is connected but cannot send says why the same way, its fix as the move (`waits` is its own end of the line)
  // ...and an act on a connection not set up (outbound.review_connect, the owner 2026-11-25): its Connect where its Approve would be
  const connect = (!proposal || proposalFrom(r)?.action === "run_tool") && !delivery.frozen ? r.Connect : null;
  const moves = r.Status !== "pending" || look === "sent" ? [] : [
    ...(connect ? [
      { id: no("connect"), label: connect.label, tone: "p", disabled: off, run: connectRun(connect.href, setSetupAt), title: `${connect.says} - sets up its connection here`, attrs: OPENS_UNDER },
      // ...and a card that is connected but cannot send keeps the Copy it drew before (`waits`): the draft can still go out by hand
      ...(connect.waits ? [{ id: no("copy"), label: copied ? `✓ ${btn("copy", "done")}` : btn("copy"), tone: "s", disabled: off || !words.trim(), run: copyIt, title: copyTitle }] : []),
    ] : delivery.frozen ? [
      { id: no("approve"), label: delivery.active ? pw.busy : busy ? "Checking delivery…" : delivery.label, tone: "p", disabled: off || !delivery.canCheck,
        run: () => decide("approve"), title: delivery.line, why: delivery.active ? "waiting for the provider" : "" },
      ...(unconfirmed ? [{ id: no("anyway"), label: btn("approve", "unknown"), tone: "s", disabled: off, run: sendAnyway, title: btnHint("approve", "unknown") },
        ...(r.TaskId ? [{ id: no("done"), label: btn("close"), tone: "s", disabled: off, run: doneAnyway, title: btnHint("close") }] : [])] : []),
    ] : co && !r.Stale ? [
      // a close-out's two: Approve and close the primary, Approve beside it - the one that folds when the line is tight
      ...(twoApproves ? [{ id: no("send_close"), label: busy && pressed === "send_close" ? sentOr(co.busyLabel) : closeCo, tone: "p", title: blocked ? gh.reason : closeCoTitle,
        disabled: off || blocked || !words.trim(), run: () => decideBoth("approve", true), why: blocked ? gh.reason.split(" - ")[0] : !words.trim() ? "write the reply first" : "" }] : []),
      { id: no("approve"), label: busy && !(twoApproves && pressed === "send_close") ? sentOr(co.busyLabel) : co.approveLabel, tone: twoApproves ? "s" : "p",
        title: blocked ? gh.reason : twoApproves ? coTitle : thenLine, disabled: off || blocked || (sendable && !words.trim()), run: () => decideBoth("approve", !twoApproves),
        why: blocked ? gh.reason.split(" - ")[0] : sendable && !words.trim() ? "write the reply first" : "" },
      ...(co.alt ? [{ id: no("alt"), label: altSends ? `${co.alt.label} & send your text` : co.alt.label, tone: "s", title: altTitle, disabled: off, run: () => decideBoth(co.alt.verb) }] : []),
    ] : proposal ? [
      { id: no("approve"), label: busy ? sentOr(proposal.busyLabel) : proposal.approveLabel, tone: "p", disabled: off || (proposal.kind === "closeout" && blocked), run: () => decide("approve"),
        why: proposal.kind === "closeout" && blocked ? gh.reason.split(" - ")[0] : "",
        title: proposal.kind === "closeout" && blocked ? gh.reason : proposal.kind === "playbook" ? "Save this process in Reports → Playbooks; nothing is sent to the sender"
          : proposal.kind === "closeout" ? `${proposal.approveLabel} - the text above goes with it` : "Run the proposed action; nothing is sent to the sender" },
      // ...A ROUTINE'S OWN WRITE STEP can be approved for good (the owner, 2026-11-25): this step, as saved, runs unpressed on its later runs
      ...(proposalFrom(r)?.flow_run?.key ? [{ id: no("always"), label: "Always approve this step", tone: "s", disabled: off, run: () => decide("approve", false, undefined, false, true),
        title: "Run it now, and let this routine run this exact step without asking again - take it back under Settings → Agent permissions" }] : []),
    ] : !canSendIt ? [
      // NO CLOSE UNDER A DRAFT THAT CANNOT LEAVE (the owner, 2026-10-22: "there should be no mark done under reply if you can't send
      // out message ... mark done is on the tasks"): the draft is there to copy, Redraft beside it, and the task's own Mark done closes
      { id: no("copy"), label: copied ? `✓ ${btn("copy", "done")}` : btn("copy"), tone: "s", disabled: off || !words.trim(), run: copyIt, title: copyTitle,
        why: words.trim() ? "" : "write the reply first" },
    ] : r.Stale ? [
      { id: no("approve"), label: redrafting ? "Redrafting…" : drafting ? "Drafting…" : btn("redraft"), tone: "p", disabled: off, run: redraft, title: btnHint("redraft") },
    ] : chatFile ? [
      { id: no("email-file"), label: "Reply by email with the file", tone: "p", disabled: off, run: byEmail,
        title: `A ${r.Channel} message cannot carry a file - the same words and file go as an email to them instead, waiting here for your yes` },
      { id: no("approve"), label: busy ? sentOr(pw.busy) : `${sendWord} without the file`, tone: "s", disabled: off || !words.trim(), why: words.trim() ? "" : "write the reply first",
        run: () => decide("approve"), title: `Sends only the words to ${replyContext(r)} - no file goes with them` },
    ] : twoSends ? [
      // Close out's two: Send and close the primary, Send beside it - the one that gives up its place when the line is tight (useFoldBar)
      { id: no("send_close"), label: busy && pressed === "send_close" ? sentOr(pw.busy) : `${closeWord}${copying}`, tone: "p", disabled: off || (!words.trim() && !isCal),
        why: words.trim() || isCal ? "" : "write the reply first", run: () => decide("approve", false, true), title: closeTitle },
      { id: no("approve"), label: busy && pressed !== "send_close" ? sentOr(pw.busy) : `${sendWord}${copying}`, tone: "s", disabled: off || (!words.trim() && !isCal),
        why: words.trim() || isCal ? "" : "write the reply first", run: () => decide("approve", false, false), title: sendTitle },
    ] : [
      { id: no("approve"), label: busy ? sentOr(simulated ? "Simulating…" : pw.busy) : simulated ? "Simulate approval" : `${sendWord}${ccNow.length && !isCal ? `, copying ${ccNow.length}` : ""}`, tone: "p", disabled: off || (!words.trim() && !isCal), why: words.trim() || isCal ? "" : "write the reply first",
        run: () => decide("approve"), title: simulated ? "Complete this temporary demo; no email is sent" : isCal ? thenLine : `Sends this response to ${replyContext(r)}` },
    ]),
    ...(proposal?.alt ? [{ id: no("palt"), label: proposal.alt.label, tone: "s", disabled: off, run: () => decide(proposal.alt.verb), title: `${proposal.alt.label} - ${proposal.alt.then}` }] : []),
    // A CLOSE-OUT HAS NO "NOT YET" (the owner, 2026-10-02): Next keeps it open and moves on, Remind me keeps it open until a day
    ...(co || proposal?.kind === "closeout" ? (onRemind ? [{ id: no("remind"), label: btn("defer"), tone: "q", disabled: off, run: onRemind, title: remindTitle }] : [])
      : proposal ? [{ id: no("reject"), label: proposal.rejectLabel, tone: "q", disabled: off, run: () => decide("reject"), title: rejectTitle }]
      // A REPLY DRAFT IS NEVER REJECTED (the owner, 2026-10-01: "rejected is useless - it should be redraft or close task"): Reject
      // threw the draft away and left the task open, which is neither. Its other choices are Redraft and the task's own Mark done.
      : [...(canRedraft && !r.Stale ? [{ id: no("redraft"), group: "decide", tone: "s", label: redraftLabel, disabled: off, run: redraft,
          title: btnHint("redraft") }] : []),
        ...(onMarkDone && canSendIt ? [{ id: no("done"), group: "decide", closes: true, tone: "s", label: btn("close"), disabled: off, run: onMarkDone, title: doneTitle }] : [])]),
  ].map((v) => ({ ...v, group: "decide", disabled: v.disabled || (delivery.frozen && ![no("approve"), no("anyway"), no("done")].includes(v.id)) }))
    .map((v) => needsTo && [no("approve"), no("send_close"), no("anyway")].includes(v.id) ? { ...v, disabled: true, why: "give the email address first" } : v);
  // ...and behind More where the decision does not carry it already (a close-out; a stale draft's Refresh is the move itself)
  // The draft's own buttons are drawn under it, never on the task's bar (2026-10-06) - but they are REGISTERED as `card` verbs, so
  // the row knows the card holds the move and the Advisor's Send finds this Send instead of drawing a second one (B4, 2026-10-17)
  useVerbs(`decision:${r.ReviewId}`, past ? [] : [...moves, ...(canRedraft && moves.length && !moves.some((v) => v.id === no("redraft")) ? [{ id: no("redraft"), group: "more", tone: "s", label: redraftLabel, disabled: off || delivery.frozen, run: redraft,
    title: btnHint("redraft") }] : [])].map((v) => ({ ...v, card: true })), toRow);
  // A FAILED SEND'S FIX IS A BUTTON ON THE ROW, not directions in the error ("add one under Connections" with nothing to press,
  // 2026-10-17) - and an ordinary row verb, so the Advisor can pick it like any other
  const failure = sendErr || (!busy && !shutErr && savedSendFailure(r)) || null;
  const fix = sendFix(r, failure);
  useVerbs(`fix:${r.ReviewId}`, fix && !past ? [{ id: no("fix"), group: "decide", tone: "s", label: fix.label, title: "Opens where this is fixed",
    run: () => openAppLink(fix.href) }] : [], !!fix && toRow);
  // THE LINE'S ONE ▾: the open Send its pair gave up (`send`), then whichever other answers the width could not hold - each the press its button is
  const calTitle = (w) => `Sets up "${w}" in place of this answer - nothing reaches the calendar until you press it`;
  const foldMore = (send) => {
    const rest = [...(folded ? send : []), ...calOthers.filter(([a]) => !bar.shown(`cal:${a}`)).map(([a, w]) => ({ id: `cal:${a}`, label: switching === a ? "Setting up…" : w, title: calTitle(w),
      disabled: off || !!switching, run: () => { setSendAt(null); answerInstead(a); } }))];
    return rest.length > 0 && <>
      <Button size="small" variant="outlined" disabled={rest.every((x) => x.disabled)} onClick={(e) => setSendAt(e.currentTarget)} title={rest.map((x) => x.label).join(", ")}
        aria-label={`More - ${rest.map((x) => x.label).join(", ")}`} aria-haspopup="menu" data-tq-send-more="" data-tq-bar-more="" sx={{ minWidth: 0, px: 1 }}>▾</Button>
      <Menu open={!!sendAt} anchorEl={sendAt} onClose={() => setSendAt(null)}>
        {rest.map((x) => <MenuItem key={x.id} dense disabled={x.disabled} title={x.title} data-tq-verb={x.id} sx={{ fontSize: 13 }} onClick={x.run}>{x.label}</MenuItem>)}
      </Menu></>;
  };
  // A REPLY HELD FOR ITS AGENT is the same card: what it waits on, its words, and Answer now anyway
  if (r.Status === "held") return (
    <ReviewCard id={r.ReviewId} kind="reply" state="held" label="Waiting on the agent working this task"
      before={<Typography variant="caption" sx={{ color: DIM, display: "block", mb: 0.75 }}>This reply was drafted from the message alone, before anyone had
        looked at the problem — so it would be promising what nobody has checked yet. When the session is wrapped up, it comes back here rewritten from
        what the agent actually found.</Typography>}
      fields={r.DraftText ? [{ key: "draft", type: "text", value: r.DraftText.slice(0, 300), dim: true }] : []}
      press={[{ id: no("release"), label: "Answer now anyway", tone: "s", disabled: off || delivery.frozen, run: release },
        ...(onOpenTask ? [{ id: no("open"), label: "Open the task", tone: "q", run: () => onOpenTask(r.TaskId) }] : [])]}
      under={err && <Alert severity="error" sx={{ mt: 1 }} onClose={() => setErr("")}>{err}</Alert>} />);

  // THE ONE CARD IN EVERY STATE (Artifact ReviewCard): waiting, going, sent, done, not sent - the same component where it stood, its words
  // read-only once it went and its press row turned to what the press did. Never a second card swapped in at the press (the owner, 2026-11-17:
  // "when you click buttons on card it flickers then presses"; 2026-11-24: one card, the after-state on it)
  const done = resultOf(r), wentNow = look === "sent" && !proposal && !co;
  // ...its words as saved once pressed (the receipt: proposals.receipt keeps his edit), else as proposed
  const changeTexts = (done && receiptOf(r)?.texts) || proposal?.texts || [];
  const sp = wentNow ? { ...sentCardOf(r, WENT.includes(r.Status) ? "" : value), ...(went || {}) } : null;
  const over = !wentNow && !done && r.Status !== "pending";
  const shut = wentNow || !!done || over;                 // its words stand as they went: nothing to edit
  const after = sp ? { mark: "sent", label: sentMark(sp), line: `${sentSaid(sp)}${sp.at ? ` · ${fmtDateTime(sp.at)}` : ""}` }
    : done ? ((o) => ({ mark: o.mark, label: o.label, line: o.line, ...(o.url ? { link: { href: o.url, text: o.url.replace(/^https?:\/\//, "").slice(0, 80) } } : {}) }))(outcomeOf(r))
    : over ? { mark: r.Status === "rejected" ? "dismissed" : "discard", label: `✗ ${upFirst(reviewStatusLabel(r.Status))}` } : null;
  // ...TO, THEN CC AND BCC AS A MAIL CLIENT DRAWS THEM (the owner, 2026-11-13: "make it look normal"): "Cc" and "Bcc" at the To line's end,
  // each opening its own row under it, labelled as To is - never a CC label beside its own "Add CC"
  const linkSx = { ...FOCUS_RING, fontSize: 12, color: "var(--tq-link, #55697a)", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } };
  const editing = !(busy || delivery.frozen || shut);
  const ccLinks = isEmail && !proposal && !isCal && editing && (!ccNow.length && !ccOpen || !bccNow.length && !bccOpen) &&
    <Box sx={{ display: "flex", gap: 1.25, ml: "auto", flexShrink: 0 }}>
      {!ccNow.length && !ccOpen && <Typography {...pressable(() => setCcOpen(true))} data-tq-add-cc="" sx={linkSx}>Cc</Typography>}
      {!bccNow.length && !bccOpen && <Typography {...pressable(() => setBccOpen(true))} data-tq-add-bcc="" sx={linkSx}>Bcc</Typography>}
    </Box>;
  // ITS FIELDS, AS ITS KIND'S DATA (the owner, 2026-11-24: "fields come from the kind's data"): the one card draws each
  const email = isEmail && !proposal && !isCal, post = proposal?.post, pic = post?.picture ? outputRow(r.TaskId, post.picture) : null;
  const fields = [
    ...(newMeeting && !delivery.frozen && !shut ? [{ key: "subject", type: "line", label: "Subject", value: subjNow, editable: !off, onChange: setSubj, placeholder: "(no subject)" }] : []),
    ...(isCal ? [{ key: "meeting", type: "read", label: CAL_ACT[meta.act] || "Answer", value: [meta.subject || "the meeting", meta.when].filter(Boolean).join(" · ") },
      { key: "who", type: "read", label: meta.act === "schedule" ? "Invites" : "Tells", value: meta.act === "schedule" ? (meta.to || []).join(", ") || "them" : (meta.to || [])[0] || "the organizer",
        note: [meta.act === "propose" && meta.was ? `instead of ${meta.was}` : "", meta.link ? `with a ${meta.link} link, made when it is sent` : ""].filter(Boolean).join(" · ") },
      ...(meta.clash ? [{ key: "clash", type: "read", label: "Clashes", value: `This ${meta.clash}.` }] : [])]
    : email ? [{ key: "to", type: "to", value: replyContext(filedDelivery), editable: editing && !off, needs: needsTo, who: String(meta.needs || [].concat(meta.to || []).join(", ")),
        onSave: async (to) => { await api.put(`/api/reviews/${r.ReviewId}/envelope`, { to }); onChanged?.(); }, trail: ccLinks },
      ...(editing ? [...(ccOpen || ccNow.length ? [{ key: "cc", type: "people", label: "CC", value: ccNow, editable: true, onChange: setCc, autoOpen: ccOpen && !ccNow.length, onClose: () => setCcOpen(false) }] : []),
        ...(bccOpen || bccNow.length ? [{ key: "bcc", type: "people", label: "BCC", value: bccNow, editable: true, onChange: setBcc, autoOpen: bccOpen && !bccNow.length, onClose: () => setBccOpen(false) }] : [])]
        : [...(ccNow.length ? [{ key: "cc", type: "people", label: "CC", value: ccNow }] : []), ...(bccNow.length ? [{ key: "bcc", type: "people", label: "BCC", value: bccNow }] : [])]),
      { key: "subject", type: "line", label: "Subject", value: subjNow, editable: editing && !off, onChange: setSubj, placeholder: "(no subject)" }]
    // ...and never a place its title already names (walk 19: "Click the "Sign in" button on 127.0.0.1" over "On 127.0.0.1")
    : proposal?.destination === "" || saysPlace(proposal?.lead || proposal?.title, proposal?.destination) ? []
    : [{ key: "to", type: "read", label: proposal?.destinationLabel || "To", value: proposal?.destination || replyContext(filedDelivery) }]),
    // ...A CHANGE TO SOMETHING STORED (reviewProposal.changeOf): what else it changes as facts, then its new words whole, each its own box, marked
    // where they change - and the switch for the marks, where there is a before to mark against
    ...(proposal?.rows || []).map((x, i) => ({ key: `row-${i}`, type: "read", label: x.label, value: x.was ? `${x.was} → ${x.now}` : x.now })),
    ...changeTexts.map((t) => ({ key: t.key, type: "change", label: t.label, was: t.was, value: words2[t.key] ?? t.now, marks: marksOn, editable: !(off || shut),
      onChange: (v) => setWords2((w) => ({ ...w, [t.key]: v })) })),
    ...(changeTexts.some((t) => t.was) || proposal?.was ? [{ key: "marks", type: "fold", label: marksOn ? "Hide what changed" : "Show what changed", open: marksOn, onToggle: () => setMarksOn((o) => !o) }] : []),
    ...(co ? [{ key: "closes", type: "read", label: co.destinationLabel, value: co.destination, note: "· first, then the reply goes out" }] : []),
    // ...A HELD PRESS THAT SENDS A FORM IS THE POST AS IT WILL GO (walk 15 S12, reviewProposal.heldPost): its words and picture, read-only
    ...(post ? [...(post.title ? [{ key: "post-title", type: "heading", value: post.title }] : []), ...post.lines.map((l, i) => ({ key: `post-line-${i}`, type: "read", value: l })),
      ...(post.body ? [{ key: "post-body", type: "text", value: post.body }] : []),
      ...(pic ? [{ key: "post-picture", type: "picture", value: post.picture, file: pic }] : [])] : []),
    ...(proposal?.folded && !shut ? [{ key: "fold", type: "fold", label: `${cmdOpen ? "Hide" : "Show"} the ${proposal.foldWord || "command"}`, open: cmdOpen, onToggle: () => setCmdOpen((o) => !o) }] : []),
    // ...the words, the card's own box: while the AI writes it, its spinner IN the box (the owner, 2026-10-30: "spin in the box of drafting")
    ...(shut ? (sp?.text || (over && (r.FinalText || r.DraftText)) ? [{ key: "draft", type: "text", value: sp?.text || String(r.FinalText || r.DraftText).slice(0, 500), clamp: true, dim: over }] : [])
      : [{ key: "draft", type: "text", box: true, label: "Reply draft", value, ...(proposal?.was ? { type: "change", label: "The playbook will say", was: proposal.was, marks: marksOn } : {}), editable: !(off || delivery.frozen || proposal?.readOnly), onChange: (v) => setText(v), marks: blanks,
        spin: drafting, boxRef: draftRef, hidden: (proposal?.folded && !cmdOpen) || proposal?.bare,
        placeholder: proposal?.kind === "closeout" ? proposal.placeholder : isCal ? "A note with your answer - or leave it empty" : drafting ? "Drafting…" : r.DraftText ? "" : proposal ? "Proposal details unavailable" : "No draft yet — write the reply here" }]),
  ];
  // ...its press row, the moves the action row registers (one list, `moves`): what the card itself draws of them, and an invite's other answers
  const presses = shut ? [] : [...moves.filter((v) => !v.closes && !(v.id === no("redraft") && (warnTop || delivery.frozen)))
    .map((v) => ({ ...v, spin: busy && /…$/.test(String(v.label)), tone: v.id === no("reject") ? "x" : v.tone,
      ...(v.id === no("approve") && paired ? { hidden: folded, attrs: { "data-tq-bar-item": "send", "data-tq-send": "open" } } : v.id === no("send_close") ? { attrs: { "data-tq-send": "close" } } : {}) })),
    ...calOthers.map(([a, w]) => ({ id: `cal:${a}`, label: switching === a ? "Setting up…" : w, tone: "s", disabled: off || !!switching, run: () => answerInstead(a), title: calTitle(w),
      hidden: !bar.shown(`cal:${a}`), attrs: { "data-tq-cal-instead": a, "data-tq-bar-item": `cal:${a}` } })),
    // ...and one email of several can be let go: it drops that slot and closes nothing (slots.settled)
    ...(isSlot && onDrop && !delivery.frozen ? [{ id: no("drop"), label: "Don't send", tone: "s", disabled: off, run: onDrop, title: "Drop this email - it is never sent, and the task stays open" }] : [])];
  const pairSend = paired ? [{ id: no("approve"), label: moves.find((v) => v.id === no("approve"))?.label, title: twoSends ? sendTitle : coTitle, disabled: off || (!words.trim() && !isCal),
    run: () => { setSendAt(null); if (twoSends) decide("approve", false, false); else decideBoth("approve", false); } }] : [];
  return (
    <ReviewCard id={r.ReviewId} kind={proposal ? proposal.kind : isCal ? "calendar" : email ? "email" : "reply"} state={sp ? "sent" : done ? "done" : over ? "not-done" : going ? "going" : "waiting"}
      data-tq-card-frame="" {...(done ? { "data-tq-act-result": "" } : {})} {...(sp ? { "data-tq-sent-here": sp.id || "" } : {})}
      label={proposal ? proposal.lead || proposal.title : kindLabel(r, meta, email)} fields={fields} lit={lit} press={presses} after={after}
      barRef={setMoves} nowrap={paired} {...(paired ? { "data-tq-two-sends": folded ? "folded" : "both" } : {})}
      tail={!shut && <>{foldMore(pairSend)}
        {/* WHY IT IS LIT, BESIDE IT (the owner, 2026-10-28): the Advisor's reason, said where its button is lit */}
        {why && !warnTop && String(lit || "").startsWith(`${r.ReviewId}:`) && <Typography component="span" data-tq-lit-why="" variant="body2"
          sx={{ alignSelf: "center", color: "var(--tq-link, #55697a)", fontSize: 12.5, minWidth: 0, overflowWrap: "anywhere" }}>{why}</Typography>}</>}
      before={!shut && <>
        {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
        {/* ...ONE FAILURE, SAID ONCE ON THE CARD (round 3, 2026-11-22): where the failure block stands, it says it - and the banner goes */}
        {!going && delivery.line && !failure?.unknown && <Alert severity={delivery.state === "unknown" ? "warning" : "info"} sx={{ mb: 1 }}>{delivery.line}</Alert>}
        <ApprovalInterrupt it={interrupt} onResolve={(choice) => {
          const res = resolveInterrupt(interrupt, choice, { [r.ReviewId]: value });
          setText(res.edits[r.ReviewId] ?? value); setCompare(res.compare); setInterrupt(null);
        }} />
        {proposal?.kind === "closeout" ? <Typography variant="caption" sx={{ color: "var(--tq-success, #6f8a6e)", display: "block", mb: 0.5 }}>{proposal.context}</Typography>
          : proposal?.lead ? <Typography data-tq-held-lead="" variant="caption" sx={{ color: "var(--tq-success, #6f8a6e)", display: "block", mb: 0.75 }}>{proposal.leadWhy}</Typography>
          : r.Reason && !failure && (r.DraftText || !/draft/i.test(r.Reason)) && <Typography data-tq-review-reason="" variant="caption" sx={{ color: "var(--tq-success, #6f8a6e)", display: "block", mb: 0.5 }}>{r.Reason}</Typography>}
        {meta.kind === "zoho_invoice" && <InvoiceLine meta={meta} />}
        {/* !!: the task detail carries the raw row, where Stale is the NUMBER 0 - and React draws a 0 */}
        {!!r.Stale && !delivery.frozen && <Alert severity="warning" sx={{ mb: 1 }}>
          New messages arrived after this draft. Refresh the draft before sending it.
          {r.LatestPreview && <Box sx={{ mt: 0.5, fontSize: 11.5 }}>Latest: {r.LatestPreview}</Box>}</Alert>}
        {/* a draft the writer could not write, or one that came back empty, says so plainly (the owner, 2026-11-03) */}
        {!proposal && !drafting && !err && ["needs", "failed", "empty", "kept"].includes(draftState(r).state) && !!draftState(r).line &&
          <Typography variant="body2" data-tq-draft-needs="" sx={{ color: DIM, mb: 1 }}>{draftState(r).line}</Typography>}
        {!proposal && <Inbound r={r} />}
        {meta.share?.report != null && <SharedDashboard report={meta.share.report} title={meta.share.title} />}
        {/* THE WARNING SITS OVER THE DRAFT IT IS ABOUT, ITS REDRAFT IN IT (the owner, 2026-10-28) */}
        {warnTop && <Box data-tq-redraft-warn="" sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.75, px: 1.25, py: 0.75,
          border: "1px solid var(--tq-edge-brass, #e3c9a8)", bgcolor: "var(--tq-panel, #fbf3e8)", borderRadius: 1.5 }}>
          <Typography component="span" data-tq-lit-why="" sx={{ flex: "1 1 220px", minWidth: 0, color: "var(--tq-warning, #6b4a1f)", fontSize: 13, overflowWrap: "anywhere" }}>{why}</Typography>
          <Button size="small" variant="contained" disableElevation disabled={off} onClick={redraft} title={btnHint("redraft")}>{redraftLabel}</Button>
        </Box>}</>}
      files={!proposal && !isCal && (!shut || deliveryFiles(filedDelivery).length > 0) && <ReplyFiles reviewId={r.ReviewId} files={deliveryFiles(filedDelivery)} promised={filesPromised(r)} short={filesShort(filedDelivery, deliveryFiles(filedDelivery))}
        channel={r.Channel} onChanged={onChanged} toRow={toRow} disabled={off || delivery.frozen || shut} over={shut} />}
      under={shut ? done?.command && <details><summary style={{ fontSize: 12, color: DIM, cursor: "pointer" }}>What it runs</summary>
        <Typography component="code" variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block" }}>{done.command}</Typography></details> : <>
        {connect && <Typography data-tq-not-connected="" variant="body2" sx={{ color: DIM, mt: 0.75 }}>{connect.says} - {connect.waits || "the draft waits here until it is"}.</Typography>}
        {connect && setupUnder(setupAt, () => setSetupAt(""), () => decide("approve"))}
        {fillLine && <Alert severity="warning" data-tq-fill-in="" sx={{ mt: 0.75 }} onClose={() => setFillIn(false)}>{fillLine} - nothing was sent.</Alert>}
        {asked && <BlankAsk line={asked.line} onCancel={() => setAsked(null)}
          onSend={() => (asked.both ? decideBoth(asked.verb, asked.close, true) : decide(asked.verb, asked.anyway, asked.close, true))} />}
        {/* what the one word does HERE - the buttons never change, this line does */}
        {thenLine && <Typography data-tq-then-line="" variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>{thenLine}</Typography>}
        {(coFail || (gh && (blocked || gh.note))) && (() => {
          const text = coFail ? coFail.text.replace(/ - nothing was merged or sent$/, "") : blocked ? gh.reason : gh.note;
          const offers = coFail ? coFail.offers : gh.offers;
          const run = async (o) => {
            if (o === "anyway") return closeout ? decideBoth("merge_anyway") : decide("merge_anyway");
            setBusy(true); setErr(""); setSaid(""); setCoFail(null);
            try { setSaid(await act(o)); } catch (e) { setErr(e?.response?.data?.detail || "GitHub refused it"); }
            setBusy(false);
          };
          return <Alert severity={coFail || blocked ? "warning" : "info"} sx={{ mt: 1 }} onClose={coFail ? () => setCoFail(null) : undefined}
            action={offers?.length ? <Box sx={{ display: "flex", gap: 0.5 }}>{offers.map((o) => (
              <Button key={o} size="small" color="inherit" disabled={off || delivery.frozen} title={OFFER_HINT[o]} onClick={() => run(o)}>{OFFER_LABEL[o]}</Button>
            ))}</Box> : null}>{coFail || blocked ? <b>Not now - nothing is merged or sent. </b> : null}{text}</Alert>;
        })()}
        {said && <Alert severity="success" sx={{ mt: 1 }} onClose={() => setSaid("")}>{said}. Press {btn("approve", "action")} again once the checks pass.</Alert>}
        {failure && <Alert data-tq-send-failed="" severity="error" sx={{ mt: 1 }} onClose={() => { setSendErr(""); setShutErr(true); }}>
          <b>{failureHead(failure, !!proposal)}</b> {failureWhy(failure)}
          {/* a proposal's failure is the act's own sentence: no reply, no draft, nothing to send again */}
          {(failure.unknown || !proposal) && <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
            {failure.unknown ? "Check the original attempt before sending by any other route. A missing receipt will not cause Taskuary to send it again."
              : fix ? `The draft stays on the task - ${fix.label} below, then send it again.` : "The draft stays on the task. Correct the delivery problem, then send it again."}
          </Box>}</Alert>}</>}>
      {!shut && compare?.reviewId === r.ReviewId && <Box sx={{ mt: 0.75, border: "1px solid var(--tq-border, #d2d6cf)", borderRadius: 1.5, px: 1.25, py: 0.75, bgcolor: PANEL2 }}>
        <Typography variant="caption" sx={{ color: "var(--tq-success, #6f8a6e)", fontWeight: 600, display: "block" }}>
          Refreshed draft - written after the new message. Your edit stays in the box above.</Typography>
        <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5, mt: 0.5 }}>{compare.refreshed || "(no refreshed draft - hit Redraft)"}</Typography>
        <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
          <Button size="small" variant="outlined" disabled={off || delivery.frozen || !compare.refreshed} onClick={() => { setText(compare.refreshed); setCompare(null); }}>Use the refreshed draft</Button>
          <Button size="small" sx={{ color: DIM }} onClick={() => setCompare(null)}>Keep mine</Button>
        </Box>
      </Box>}
    </ReviewCard>
  );
}

// A PLACE THE CARD'S OWN TITLE ALREADY SAYS (its last words: "... on 127.0.0.1"), said once - by the title
export const saysPlace = (title, place) => { const t = String(title || "").trim().toLowerCase(), p = String(place || "").trim().toLowerCase();
  return !!p && (t.endsWith(` ${p}`) || t.endsWith(` ${p}.`)); };

// WHAT A CARD IS, IN PLAIN WORDS, over its fields: a reply by its channel, an email, an invite's answer, a share
const BY = { email: "by email", outlook: "by email", gmail: "by email", whatsapp: "on WhatsApp", teams: "on Teams", slack: "on Slack", telegram: "on Telegram",
  sms: "by text", github: "on GitHub" };
const upFirst = (x) => (x ? String(x)[0].toUpperCase() + String(x).slice(1) : "");
const kindLabel = (r, meta, email) => meta.share ? `Share ${meta.share.title || "a dashboard"}` : r.Kind === "slot" || (email && !r.MessageId) ? "Email"
  : `Reply${BY[String(r.Channel || meta.channel || "").toLowerCase()] ? ` ${BY[String(r.Channel || meta.channel || "").toLowerCase()]}` : ""}`;

// A REPLY THAT WENT, AS A RECORD IN ITS TURN (TaskPage sentHere): the same card, its words as they went and the press it took
export function SentReview(p) {
  return <ReviewCard id={p.id || ""} kind="reply" state="sent" data-tq-sent-here={p.id || ""} label={sentTitle(p)}
    fields={[{ key: "draft", type: "text", value: p.text, clamp: true, dim: true }]}
    after={{ mark: "sent", label: sentMark(p), line: `${sentSaid(p)}${p.at ? ` · ${fmtDateTime(p.at)}` : ""}` }} />;
}

// AN ACT A CONNECTOR DECLARES (the owner, 2026-11-05: "each connector should have settings what the action view looks like no?"): a post with its
// picture and who sees it, a tracker comment, a new GitHub issue - its fields read off the catalogue (actionCard.js), each line and its words his
// to change while it waits, its press named by the act ("Post to LinkedIn", "Create issue"). The press is the one decide road every proposal
// takes (/api/reviews/{id}/decide -> proposals.execute); a post on a network not connected goes up through the agent's browser at his press,
// its final Post held for him (the owner, 2026-11-22: "card first, sign-in at the press"). `past`: the chat moved past it, greyed (MovedPast)
// `step`: {review, what} - the step of that browser road held for him now (chatlog.advance): THIS card's next press, drawn here (walk 22,
// 2026-11-25: the final Post was held and nothing anywhere could be pressed)
export function ActReview({ row: was, tid, live = true, onChanged, past = false, step = null }) {
  const given = past ? asLive(was) : was;
  // ...A PRESS ANSWERED IS THE CARD'S STATE AT ONCE (the card round, 2026-11-18): the status the server answered with stands over a row that still
  // says pending, until that row says it too - one answered elsewhere (`already`) holds greyed instead, its words not this card's to say
  const [settled, setSettled] = useState(null);
  const answered = !!settled && given?.Status === "pending", row = answered && settled.mine ? { ...given, Status: settled.Status, ActError: settled.ActError || given.ActError } : given;
  const held = answered && !settled.mine ? "held" : "";
  const p = row?.post || {}, act = actionFor(p.type), st = stateOf(row, live), tk = textKey(act);
  const [text, setText] = useState(String(p[tk] || "")), [vals, setVals] = useState(() => valuesOf(act, p)), [copied, setCopied] = useState(false);
  const [pressing, setBusy] = useState(""), [err, setErr] = useState(""), [viewing, setViewing] = useState(null), [setupAt, setSetupAt] = useState("");
  const done = answered && settled.mine && ["approved", "edited"].includes(settled.Status) ? settled : null;
  const busy = pressing || held;
  if (!act) return null;
  // ...gone by it, it reads what he pressed - his words, his picks - not the proposal's until the row comes back with them
  const shown = done ? { ...p, ...vals, [tk]: text } : p, edit = !!st.live && !done && !busy;
  const fs = fieldsOf(act, shown, !!st.live && !done), post = act.kind === "post", w = wordsOf(act, done || st.live ? vals : p);
  // ...EVERY POST CARRIES ITS PICTURE (the owner, 2026-11-20): one its network takes no upload for is shown all the same, to save and add by hand
  const img = fs.find((f) => f.type === "image" && f.value) || (p.image ? { key: "image", value: p.image, manual: true } : null);
  const pic = img ? outputRow(tid ?? row?.TaskId, img.value) : null;
  const box = fs.find((f) => f.key === tk), max = box?.max, n = lengthOf(box, text), over = max && n > max;
  const go = done?.url || st.url, gone = !!done || st.done;
  // ...a press that failed before this card was drawn is still said on it: the review keeps it (store.review_act_failed)
  const failed = err || (!busy && !gone && ["pending", "superseded"].includes(row?.Status) && row?.ActError) || "";
  const moved = changed(act, p, vals), edits = Object.keys(moved).length ? { fields: moved } : {};
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    const o = await press(api, row.ReviewId, { verb, final_text: verb === "approve" ? text : null, shown: p, ...(verb === "approve" ? edits : {}) }, 2);
    const line = landed(o) || o.kind === "already" ? "" : failLine(o, post ? "posted" : "sent"), status = o.data?.status;
    if (status && status !== "pending") setSettled({ Status: status, ActError: line, url: o.data.result?.url || "", mine: o.kind !== "already" });
    else setErr(line);
    if (o.kind !== "error") onChanged?.();
    setBusy("");
  };
  const viaBrowser = async () => {
    setBusy("browser"); setErr("");
    try { const { data } = await api.post(`/api/reviews/${row.ReviewId}/via-browser`, { final_text: text, ...edits });
      if (data?.ok) setSettled({ Status: data.status || "approved", mine: true, browser: true }); else setErr(data?.why || "It could not be handed over.");
      onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "It could not be handed over."); }
    setBusy("");
  };
  // ...the held step's own press: the one decide road, on the step's review - what it did is this card's next state, as the list says it
  const decideStep = async (verb) => {
    setBusy(`step:${verb}`); setErr("");
    const o = await press(api, step.review, { verb }, 2);
    setErr(landed(o) || o.kind === "already" ? "" : failLine(o, "done"));
    if (o.kind !== "error") onChanged?.();
    setBusy("");
  };
  const set = (k) => (v) => setVals((x) => ({ ...x, [k]: v }));
  const has = (f) => f.value || f.editable;
  // ITS FIELDS FROM ITS DECLARATION: its picks under the label, a heading line bold, its other lines, its words, its picture once
  const fields = [
    ...fs.filter((f) => f.type === "choice").map((f) => ({ ...f, value: edit || done ? vals[f.key] : f.value, editable: edit, onChange: set(f.key) })),
    ...fs.filter((f) => f.type === "line" && has(f)).sort((a, b) => !!b.heading - !!a.heading)
      .map((f) => ({ ...f, type: f.heading ? "heading" : "line", value: f.editable ? vals[f.key] : f.value, editable: edit && f.editable, onChange: set(f.key) })),
    { key: tk, type: "text", label: fs.find((f) => f.key === tk)?.label || "Words", box: !!st.live && !gone, value: st.live && !gone ? text : shown[tk], editable: edit && !gone,
      onChange: setText, dim: !gone && !st.live, over: over ? `${n} of ${max} characters` : "" },
    ...(pic ? [{ key: "image", type: "picture", value: img.value, file: pic, alt: p.alt || pic.name,
      note: img.manual && !gone ? `${row?.network || "This network"} gets the words from here - open the picture to save it, and add it yourself` : "" }] : []),
  ];
  const ok = !busy && actPressable(act, p, text, vals) && !over;
  // ...his no, as every card draws it (tone x)
  const dismiss = { id: "dismiss", label: "Dismiss", tone: "x", disabled: !!busy, run: () => decide("reject"), attrs: { "data-tq-act-dismiss": "" } };
  const pressRow = gone || !st.live ? [] : row?.connect ? [
    ...(post ? [{ id: "browser", label: busy === "browser" ? "Handing it over…" : "Post via the browser", tone: "p", spin: busy === "browser", disabled: !ok || !text.trim(), run: viaBrowser,
      attrs: { "data-tq-act-browser": "" } }] : []),
    { id: "connect", label: row.connect.label, tone: post ? "s" : "p", run: connectRun(row.connect.href, setSetupAt), attrs: { "data-tq-act-connect": "", ...OPENS_UNDER } },
    { id: "copy", label: copied ? `✓ ${btn("copy", "done") || "Copied"}` : btn("copy"), tone: "s", disabled: !text.trim(), title: hint("copy"), attrs: { "data-tq-act-copy": "" },
      run: () => { try { navigator.clipboard?.writeText(text); setCopied(true); } catch { /* the words stay on the card */ } } }, dismiss]
    : [{ id: "approve", label: busy === "approve" ? w.busy : w.press, tone: "p", spin: busy === "approve", disabled: !ok, run: () => decide("approve"),
      title: act.note || hint("approve", post ? "post" : "action"), attrs: { "data-tq-act-press": "" } }, dismiss];
  const stepRow = step && gone && !past && st.said.startsWith("Handed") ? [
    { id: "approve", label: btn("approve", "action"), tone: "p", spin: busy === "step:approve", disabled: !!busy, run: () => decideStep("approve"), attrs: { "data-tq-act-step": step.review } },
    { ...dismiss, run: () => decideStep("reject") }] : null;
  const after = stepRow ? null : gone ? { mark: "approved", label: `✓ ${done ? (done.browser ? "Handed to the agent" : w.done) : st.said.startsWith("Handed") ? "Handed to the agent" : st.said}`,
    line: done?.browser || st.said.startsWith("Handed") ? viaBrowserSaid(row?.network).replace(/^Handed to the agent - /, "") : "",
    ...(go ? { link: { href: go, text: `See it on ${row?.network}` } } : {}) }
    : !st.live && !st.failed ? { mark: "dismissed", label: `✗ ${st.said}` } : null;
  return (<MovedPast on={past}>
    <ReviewCard id={row?.ReviewId} kind={act.kind} state={stepRow ? "waiting" : gone ? "done" : st.live ? "waiting" : "not-done"} data-tq-act={row?.ReviewId} data-tq-act-kind={act.kind}
      face={post ? faceOf(row) : ""} label={post ? `${row?.as || `Your ${row?.network || ""} account`} · ${row?.network || "post"}` : act.title}
      fields={fields} press={stepRow || pressRow} after={after} failed={failed || (stepRow && err) || ""} onView={setViewing}
      before={stepRow && <Typography data-tq-act-step-says="" sx={{ fontSize: 12.5, color: INK, mb: 0.75 }}>Waiting for your press - the agent has it ready on the page: {step.what}</Typography>}
      tail={st.live && !gone && row?.connect && <Typography data-tq-not-connected="" sx={{ fontSize: 11.5, color: FAINT }}>{row.connect.says}{post
        ? " - Post via the browser has the agent put it up there, and its last Post waits for you" : row.connect.waits ? ` - ${row.connect.waits}` : ""}</Typography>}
      under={<>{row?.connect && st.live && !gone && setupUnder(setupAt, () => setSetupAt(""), () => decide("approve"))}
        <FileDialog file={viewing} onClose={() => setViewing(null)} /></>} />
  </MovedPast>);
}
