// ONE DECISION, WHEREVER IT IS SHOWN. What they wrote, what we would say back, and the verdict
// buttons - extracted from the review queue so the task page can hold the decision instead of
// sending you to another tab to make it (2026-09-22). A proposal (a playbook, a setting, an
// action) renders through the same card: proposalPresentation() gives it its own title, its
// destination and its own labels, and nothing is sent to a sender.
import React, { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Typography, CircularProgress } from "@mui/material";
import api from "./api";
import ReplyFiles from "./ReplyFiles.jsx";
import { holdInView } from "./inView.js";
import { filesPromised } from "./replyFiles.js";
import { proposalPresentation, reviewText } from "./reviewProposal.js";
import { withSignature, withoutSignature } from "./signature.js";
import { OFFER_HINT, OFFER_LABEL, useCloseoutState } from "./closeoutState.js";
import { PANEL2, BORDER, DIM, FAINT, INK, label } from "./theme.jsx";
import { CcRow, DraftField, ToRow, timeAgo, cleanText, splitQuoted } from "./ui.jsx";
import { deliveryCc, deliveryFiles, deliveryMeta, replyContext } from "./replyDelivery.js";
import { acted, announce, useLit, useVerbs } from "./actionRow.js";
import { hint as btnHint, label as btn } from "./buttons.js";   // theme.jsx owns `label`
import { useDraftJob } from "./replyDraft.js";
import ApprovalInterrupt from "./ApprovalInterrupt.jsx";
import { interruptOf, resolveInterrupt } from "./approvalInterrupt.js";
import { DECIDE_TIMEOUT, draftState, failureHead, replySendFailure, reviewDeliveryState, sendFix, timedOut } from "./sendState.js";
import { openAppLink } from "./appLinks.js";
import { runOperation } from "./taskOps.js";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { blankRefusal, blankSpans } from "./blanks.js";

// What they wrote, above what we would say back. The queue used to show only the draft: you
// approved an answer without the question in front of you, or opened the task to find it. Four
// lines of the inbound message, the rest one click away.
const Inbound = ({ r }) => {
  const [full, setFull] = useState(false);
  const { latest } = splitQuoted(cleanText(r.Preview || ""));
  if (!latest) return null;
  const long = latest.length > 360 || latest.split("\n").length > 4;
  return (
    <Box sx={{ mb: 1, px: 1.25, py: 0.85, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, borderLeft: "3px solid #6f8a6e" }}>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.25 }}>
        {r.FromName || r.FromEmail || "they"} wrote{r.SentAt ? ` · ${timeAgo(r.SentAt)}` : ""}
      </Typography>
      <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", lineHeight: 1.5,
        ...(full || !long ? {} : { display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>
        {latest}
      </Typography>
      {long && (
        <Typography variant="caption" onClick={() => setFull((f) => !f)}
          sx={{ color: "#55697a", fontWeight: 600, cursor: "pointer", display: "block", mt: 0.35, "&:hover": { textDecoration: "underline" } }}>
          {full ? "less ↑" : "the whole message ↓"}
        </Typography>
      )}
    </Box>
  );
};

export const InvoiceLine = ({ meta }) => (
  <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 1, px: 1.25, py: 0.8,
    bgcolor: "#eef1ec", border: "1px solid #d9e0d6", borderRadius: 1.5 }}>
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
const edits = new Map();
const heldOf = (r) => { const e = edits.get(r?.ReviewId); return e && e.filed === reviewText(r) ? e : null; };
const hold = (r, part) => {
  const e = { text: null, cc: null, ...heldOf(r), ...part, filed: reviewText(r) };
  if (e.text == null && e.cc == null) edits.delete(r.ReviewId); else edits.set(r.ReviewId, e);
};

const CAL_ACT = { accept: btn("accept_invite"), decline: btn("decline_invite"), propose: "Propose", schedule: "Invite" };
// The times are the server's words (calwrite.when): the envelope carries them as they will be said.
export const CalendarLine = ({ meta }) => (
    <Box data-tq-calendar={meta.act} sx={{ display: "grid", gap: 0.25, mb: 1, px: 1.25, py: 0.8, bgcolor: "#eef1ec", border: "1px solid #d9e0d6", borderRadius: 1.5 }}>
      <Typography variant="caption" sx={{ color: INK, fontWeight: 600 }}>
        {CAL_ACT[meta.act] || "Answer"} · {meta.subject || "the meeting"}{meta.when ? ` · ${meta.when}` : ""}</Typography>
      <Typography variant="caption" sx={{ color: DIM }}>
        {meta.act === "schedule" ? `Invites ${(meta.to || []).join(", ") || "them"}` : `${(meta.to || [])[0] || "The organizer"} is told`}
        {meta.act === "propose" && meta.was ? ` · instead of ${meta.was}` : ""}</Typography>
      {!!meta.clash && <Typography variant="caption" sx={{ color: "#7a2f3c" }}>This {meta.clash}.</Typography>}
    </Box>
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
// `onEmailInstead`: the task's Send out results - a chat reply that has to carry a file is answered by email instead (U17).
export default function ReviewDecision({ review: r, closeout, onChanged, onOpenTask, onMarkDone = null, onSent = null, onRemind = null, closeOnSend = false, toRow = false, simulated = false, onDrop = null, onEmailInstead = null, why = "" }) {
  const [text, setTextNow] = useState(() => heldOf(r)?.text ?? null);   // the owner's edit; null means "the draft as filed"
  const setText = (v) => { hold(r, { text: v ?? null }); setTextNow(v); };
  const [cc, setCcNow] = useState(() => heldOf(r)?.cc ?? null);         // null means "the CC the draft was filed with"
  const setCc = (v) => { hold(r, { cc: v ?? null }); setCcNow(v); };
  const [busyNow, setBusy] = useState(false);
  // SENT STAYS SENT until the page's re-read takes the card away (the owner, 2026-10-26: "when you hit send on close out email it grey's
  // out and then turns blue again then closes"): busy still ends when the decide answers, as 2026-10-18 ruled, but the button after it
  // reads "Sent" and stays off - a blue Send again over a reply already gone invited a second press
  const [sent, setSent] = useState(false);
  const busy = busyNow || sent;
  const sentOr = (w) => (sent ? "Sent" : w);
  const [err, setErr] = useState("");
  const [sendErr, setSendErr] = useState("");       // approved, but the channel refused it
  const [interrupt, setInterrupt] = useState(null); // PW-239: the click that did not send
  const [compare, setCompare] = useState(null);     // the refreshed draft, shown beside the owner's edit
  // A BLANK LEFT IN IT (the owner, 2026-10-30): Send pressed over a "[REASON]" says "Fill in [REASON] first" under the button, and the
  // line follows the box - it names what is still blank as the owner types, and is gone once nothing is
  const [fillIn, setFillIn] = useState(false);

  const delivery = reviewDeliveryState(r);
  // ...until the review itself says where the send stands: its own delivery line (Sending… / Check delivery) takes over from "Sent"
  useEffect(() => { if (delivery.frozen) setSent(false); }, [delivery.frozen, r.ReviewId]);
  const filedDelivery = delivery.frozen ? { ...r, Deliver: JSON.stringify(delivery.envelope) } : r;
  const proposal = proposalPresentation(r);
  // the signature that goes under this email (signatures.py) is in the box: an empty one opens on it, a draft gets it once - and
  // a box holding only it is still "write the reply first"
  const value = delivery.frozen ? delivery.body : text ?? withSignature(reviewText(r), r.Signature);
  const words = withoutSignature(value, r.Signature);
  const ccNow = delivery.frozen ? deliveryCc(filedDelivery) : cc ?? deliveryCc(r);
  const meta = deliveryMeta(r);
  const isCal = meta.kind === "calendar";             // an invite answered or a meeting booked: its note may be empty
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
  const closesIt = closeOnSend && onTask && !!onSent;
  const sendWord = btn("approve"), stays = closesIt ? "then the task closes" : `the task stays open until you ${btn("close")}`;
  // A CHAT REPLY THAT PROMISES A FILE (U17): WhatsApp and the other chats carry words only, so a send went out with the promise and
  // without the file. The move becomes answering by email with the file; sending the words alone stays beside it.
  const chatFile = !!onEmailInstead && !proposal && !co && !isSlot && !r.Stale && !delivery.frozen && canSendIt
    && String(r.Channel || "email").toLowerCase() !== "email" && (deliveryFiles(filedDelivery).length > 0 || filesPromised(r));
  const thenLine = delivery.frozen ? "" : simulated ? "This approves the fictional reply and completes the demo task. No email is sent."
    : co ? `${co.approveLabel} ${co.then}${sendable ? `, then sends your reply to ${replyContext(r)}` : ""}${closesIt && sendable ? ` - ${stays}` : ` - and only that; the task stays open until you ${btn("close")}`}.`
    : chatFile ? `A ${r.Channel} message cannot carry a file. Reply by email with the file, or send the words alone.`
    : isCal && !r.Stale ? `${sendWord} tells the calendar, with the note above if there is one - ${stays}.`
    : onTask && !r.Stale && canSendIt ? `${sendWord} sends this to ${replyContext(r)} - ${stays}.` : "";
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
  const { gh, reload: reloadGh, act } = useCloseoutState(coRid);
  const blocked = !!gh && !gh.ok;
  // A REPLY OPENED AT ONCE is drawn before its draft exists (replyDraft.js, 2026-10-01): "Drafting…" until the model is done,
  // then the task is read again and the draft is in the box; one that could not be written says why here
  const job = useDraftJob(r.ReviewId);
  // A REDRAFT IS NOT A SEND (the email walk, 2026-10-29: Redraft turned Send into "Sending…"): its own state holds every button off
  // while the model writes, and only Redraft says what is happening
  const [redrafting, setRedrafting] = useState(false);
  const drafting = job?.state === "drafting" || redrafting;
  const off = busy || drafting;
  useEffect(() => {
    if (job?.state === "done") onChanged?.();
    if (job?.state === "failed") setErr(`The draft could not be written - ${job.error}. Write it here, or Draft with AI again.`);
  }, [job]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ...the press stops there, before anything is posted, with the cursor on the first blank
  const refuseBlank = () => {
    if (!blanks.length) return false;
    setFillIn(true);
    const el = draftRef.current?.querySelector("textarea[data-tq-draft]");
    if (el) { el.focus(); el.setSelectionRange(blanks[0][0], blanks[0][1]); }
    return true;
  };

  const decideBoth = async (verb) => {
    if (delivery.frozen) return;
    // the reply that rides with the close-out is checked before the merge, not after it (verdicts.decide refuses it there too)
    if (verb !== "reject" && sendable && words.trim() && refuseBlank()) return;
    announce(no(verb));
    setBusy(true); setErr(""); setSendErr(""); setCoFail(null);
    try {
      const { data } = await api.post(`/api/reviews/${closeout.ReviewId}/decide`,
        { verb, final_text: null, note: null, reply_text: verb !== "reject" && sendable && words.trim() ? value : null, cc: sendable ? ccNow : null },
        { timeout: DECIDE_TIMEOUT });
      if (data.blanks?.length) { setFillIn(true); if (!blanks.length) setErr(data.send_error); }
      // refused before anything happened is not "approved, but it did not send"
      else if (!data.ok && data.send_error) setCoFail({ text: data.send_error, offers: data.offers || [] });
      else if (data.send_error) setSendErr(replySendFailure(data));
      // WAIT FOR IT, THEN MOVE ON (the owner, 2026-10-02): the close-out landed with no error, so the task may be closed now
      // ...the press is over when the server answers: the re-read after it is the page's, and "Sending…" waited on it too
      // ...and the reply that went with it closes the task, on the task page (closeOnSend) - the merge alone does not
      else if (data.ok && verb !== "reject" && onSent) { setSent(true); setBusy(false); await onSent({ closes: closesIt && !!data.reply?.ok }); return; }
      reloadGh(); onChanged?.();
    } catch (e) {
      if (timedOut(e)) onChanged?.();       // no answer in a minute: the review's own delivery state says where it stands
      else setErr(e?.response?.data?.detail || "That didn't go through - nothing was sent. Try the button again.");
    }
    finally { acted(no(verb)); }          // the Advisor reads the item again: what it advised has been done, or failed
    setBusy(false);
  };

  // Approving IS sending, so a send that failed has to say so HERE, the moment you click - it
  // used to return quietly and leave a "NOT SENT" line in the task history for you to find later.
  const decide = async (verb, anyway = false) => {
    if (delivery.active || (delivery.frozen && verb !== "approve")) return;
    if (verb === "approve" && refuseBlank()) return;
    announce(no(verb));
    setBusy(true); setErr(""); setSendErr("");
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/decide`,
        { verb, final_text: verb === "approve" && !delivery.frozen ? value : null, note: null,
          // only on the send: rejecting or "no reply needed" copies nobody on nothing
          cc: verb === "approve" && !proposal && !delivery.frozen ? ccNow : null, anyway }, { timeout: DECIDE_TIMEOUT });
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
      else if (data.ok && (verb === "approve" || (verb === "close_unsent" && r.Kind !== "slot")) && onSent) {
        setSent(verb === "approve"); setBusy(false); await onSent({ closes: closesIt && verb === "approve" && (data.reply ? !!data.reply.ok : true) }); return;
      }
      onChanged?.();
    } catch (e) {
      // NO ANSWER IN A MINUTE is not "nothing was sent": the server may be sending still. The card reads the review again and its
      // DeliveryState draws Sending… or Check delivery (reviewDeliveryState) - the check it already has, not a line of ours
      if (timedOut(e)) onChanged?.();
      else setErr(e?.response?.data?.detail || "That didn't go through - nothing was sent. Try the button again.");
    }
    finally { acted(no(verb)); }
    setBusy(false);
  };

  // A held draft is one the session's findings will rewrite. Sometimes the sender needs telling
  // something today anyway - a reply stuck behind an agent that never finished is worse.
  const release = async () => {
    if (delivery.frozen) return;
    setBusy(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/release`); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not release it"); }
    setBusy(false);
  };

  const redraft = async () => {
    if (delivery.frozen) return;
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
    if (!lit.startsWith(`${r.ReviewId}:`)) return undefined;
    const el = movesRef.current?.querySelector(".MuiButton-contained");
    el?.setAttribute("data-tq-lit", "");
    const stop = holdInView(el);
    return () => { stop(); el?.removeAttribute("data-tq-lit"); };
  }, [lit, r.ReviewId]);
  const solid = toRow && lit !== no("approve") ? "outlined" : "contained";
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
  const moves = r.Status !== "pending" ? [] : [
    ...(delivery.frozen ? [
      { id: no("approve"), label: busy ? "Checking delivery…" : delivery.label, tone: "p", disabled: off || !delivery.canCheck,
        run: () => decide("approve"), title: delivery.line, why: delivery.active ? "waiting for the provider" : "" },
      ...(unconfirmed ? [{ id: no("anyway"), label: btn("approve", "unknown"), tone: "s", disabled: off, run: sendAnyway, title: btnHint("approve", "unknown") },
        ...(r.TaskId ? [{ id: no("done"), label: btn("close"), tone: "s", disabled: off, run: doneAnyway, title: btnHint("close") }] : [])] : []),
    ] : co && !r.Stale ? [
      { id: no("approve"), label: busy ? sentOr(co.busyLabel) : co.approveLabel, tone: "p", title: blocked ? gh.reason : thenLine, disabled: off || blocked || (sendable && !words.trim()), run: () => decideBoth("approve"),
        why: blocked ? gh.reason.split(" - ")[0] : sendable && !words.trim() ? "write the reply first" : "" },
      ...(co.alt ? [{ id: no("alt"), label: altSends ? `${co.alt.label} & send your text` : co.alt.label, tone: "s", title: altTitle, disabled: off, run: () => decideBoth(co.alt.verb) }] : []),
    ] : proposal ? [
      { id: no("approve"), label: busy ? sentOr(proposal.busyLabel) : proposal.approveLabel, tone: "p", disabled: off || (proposal.kind === "closeout" && blocked), run: () => decide("approve"),
        why: proposal.kind === "closeout" && blocked ? gh.reason.split(" - ")[0] : "",
        title: proposal.kind === "closeout" && blocked ? gh.reason : proposal.kind === "playbook" ? "Save this process in Reports → Playbooks; nothing is sent to the sender"
          : proposal.kind === "closeout" ? `${proposal.approveLabel} - the text above goes with it` : "Run the proposed action; nothing is sent to the sender" },
    ] : !canSendIt ? [
      // NO CLOSE UNDER A DRAFT THAT CANNOT LEAVE (the owner, 2026-10-22: "there should be no mark done under reply if you can't send
      // out message ... mark done is on the tasks"): the draft is there to copy, Redraft beside it, and the task's own Mark done closes
      { id: no("copy"), label: copied ? `✓ ${btn("copy", "done")}` : btn("copy"), tone: "s", disabled: off || !words.trim(), run: copyIt, title: copyTitle,
        why: words.trim() ? "" : "write the reply first" },
    ] : r.Stale ? [
      { id: no("approve"), label: redrafting ? "Redrafting…" : drafting ? "Drafting…" : btn("redraft"), tone: "p", disabled: off, run: redraft, title: btnHint("redraft") },
    ] : chatFile ? [
      { id: no("email-file"), label: "Reply by email with the file", tone: "p", disabled: off, run: onEmailInstead,
        title: `A ${r.Channel} message cannot carry a file - this writes an email with the file on it, which waits here for your yes` },
      { id: no("approve"), label: busy ? sentOr("Sending…") : `${sendWord} without the file`, tone: "s", disabled: off || !words.trim(), why: words.trim() ? "" : "write the reply first",
        run: () => decide("approve"), title: `Sends only the words to ${replyContext(r)} - no file goes with them` },
    ] : [
      { id: no("approve"), label: busy ? sentOr(simulated ? "Simulating…" : "Sending…") : simulated ? "Simulate approval" : `${sendWord}${ccNow.length && !isCal ? `, copying ${ccNow.length}` : ""}`, tone: "p", disabled: off || (!words.trim() && !isCal), why: words.trim() || isCal ? "" : "write the reply first",
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
  ].map((v) => ({ ...v, group: "decide", disabled: v.disabled || (delivery.frozen && ![no("approve"), no("anyway"), no("done")].includes(v.id)) }));
  // ...and behind More where the decision does not carry it already (a close-out; a stale draft's Refresh is the move itself)
  // The draft's own buttons are drawn under it, never on the task's bar (2026-10-06) - but they are REGISTERED as `card` verbs, so
  // the row knows the card holds the move and the Advisor's Send finds this Send instead of drawing a second one (B4, 2026-10-17)
  useVerbs(`decision:${r.ReviewId}`, [...moves, ...(canRedraft && moves.length && !moves.some((v) => v.id === no("redraft")) ? [{ id: no("redraft"), group: "more", tone: "s", label: redraftLabel, disabled: off || delivery.frozen, run: redraft,
    title: btnHint("redraft") }] : [])].map((v) => ({ ...v, card: true })), toRow);
  // A FAILED SEND'S FIX IS A BUTTON ON THE ROW, not directions in the error ("add one under Connections" with nothing to press,
  // 2026-10-17) - and an ordinary row verb, so the Advisor can pick it like any other
  const fix = sendFix(r, sendErr);
  useVerbs(`fix:${r.ReviewId}`, fix ? [{ id: no("fix"), group: "decide", tone: "s", label: fix.label, title: "Opens where this is fixed",
    run: () => openAppLink(fix.href) }] : [], !!fix && toRow);

  if (r.Status === "held") {
    return (
      <Box sx={{ mt: 0.5, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75 }}>
        <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 600, display: "block" }}>
          Waiting on the agent working this task
        </Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25 }}>
          This reply was drafted from the message alone, before anyone had looked at the problem — so it
          would be promising what nobody has checked yet. When the session is wrapped up, it comes back
          here rewritten from what the agent actually found.
        </Typography>
        <Box sx={{ display: "flex", gap: 0.75, mt: 0.75, alignItems: "center" }}>
          <Button size="small" variant="outlined" disabled={off || delivery.frozen} onClick={release}>Answer now anyway</Button>
          {onOpenTask && <Button size="small" sx={{ color: DIM }} onClick={() => onOpenTask(r.TaskId)}>Open the task</Button>}
        </Box>
        {r.DraftText && (
          <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: FAINT, display: "block", mt: 0.75 }}>
            {r.DraftText.slice(0, 300)}
          </Typography>
        )}
        {err && <Alert severity="error" sx={{ mt: 1 }} onClose={() => setErr("")}>{err}</Alert>}
      </Box>
    );
  }

  if (r.Status !== "pending") {
    return (r.FinalText || r.DraftText) ? (
      <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block", mt: 0.75,
        bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1 }}>
        {(r.FinalText || r.DraftText).slice(0, 500)}
      </Typography>
    ) : null;
  }

  return (
    <Box sx={{ mt: 0.5 }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1 }}>{err}</Alert>}
      {delivery.line && <Alert severity={delivery.state === "unknown" ? "warning" : "info"} sx={{ mb: 1 }}>{delivery.line}</Alert>}
      <ApprovalInterrupt it={interrupt} onResolve={(choice) => {
        // the click did not send; the owner's edit stays theirs, the refreshed draft is shown beside it
        const res = resolveInterrupt(interrupt, choice, { [r.ReviewId]: value });
        setText(res.edits[r.ReviewId] ?? value); setCompare(res.compare); setInterrupt(null);
      }} />
      {/* a close-out says what it closes, whatever an older row's Reason worded it as */}
      {proposal?.kind === "closeout" ? (
        <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mb: 0.5 }}>{proposal.context}</Typography>
      ) : r.Reason && (r.DraftText || !/draft/i.test(r.Reason)) && (
        <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mb: 0.5 }}>{r.Reason}</Typography>
      )}
      {meta.kind === "zoho_invoice" && <InvoiceLine meta={meta} />}
      {/* !!: the task detail carries the raw row, where Stale is the NUMBER 0 - and React draws a 0 */}
      {!!r.Stale && !delivery.frozen && <Alert severity="warning" sx={{ mb: 1 }}>
        New messages arrived after this draft. Refresh the draft before sending it.
        {r.LatestPreview && <Box sx={{ mt: 0.5, fontSize: 11.5 }}>Latest: {r.LatestPreview}</Box>}
      </Alert>}
      {/* the writer said what it needs: a plain line, never a red failure - its way on is Send to agent / Continue, lit by the Advisor */}
      {!proposal && draftState(r).state === "needs" && (
        <Typography variant="body2" data-tq-draft-needs="" sx={{ color: DIM, mb: 1 }}>{draftState(r).line}</Typography>
      )}
      {!proposal && <Inbound r={r} />}
      {/* an EMAIL draft's recipient is the owner's to correct (ToRow); a proposal's destination and a chat's room are not - and a
          calendar answer goes to the calendar: what it will be told stands in their place, with no copies and no files */}
      {isCal ? <CalendarLine meta={meta} /> : !proposal && String(r.Channel || deliveryMeta(r).channel || "").toLowerCase() === "email" ? (
        <ToRow to={replyContext(filedDelivery)} disabled={off || delivery.frozen}
          onSave={async (to) => { await api.put(`/api/reviews/${r.ReviewId}/envelope`, { to }); onChanged?.(); }} />
      ) : (
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
        <Typography sx={{ ...label, flexShrink: 0 }}>{proposal?.destinationLabel || "To"}</Typography>
        <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }} noWrap>
          {proposal?.destination || replyContext(filedDelivery)}
        </Typography>
      </Box>
      )}
      {co && (
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
          <Typography sx={{ ...label, flexShrink: 0 }}>{co.destinationLabel}</Typography>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }} noWrap>{co.destination}</Typography>
          <Typography variant="caption" sx={{ color: FAINT }} noWrap>· first, then the reply goes out</Typography>
        </Box>
      )}
      {!proposal && !isCal && <ReplyFiles reviewId={r.ReviewId} files={deliveryFiles(filedDelivery)}
        promised={filesPromised(r)} channel={r.Channel} onChanged={onChanged} toRow={toRow} disabled={off || delivery.frozen} />}
      {isCal ? null : !proposal && (busy || delivery.frozen) ? String(r.Channel || "").toLowerCase() === "email" && (
        <Typography variant="caption" data-tq-delivery-cc sx={{ display: "block", color: DIM, mb: 0.75 }}>
          CC: {ccNow.length ? ccNow.join(", ") : "none"}
        </Typography>
      ) : !proposal && <CcRow cc={ccNow} setCc={setCc} channel={r.Channel} />}
      {/* why there is no Send (outbound.send_block, PW-044) is the Copy button's hover under the draft, not a line over it (2026-10-22) */}
      {/* THE WARNING SITS OVER THE DRAFT IT IS ABOUT, ITS REDRAFT IN IT (the owner, 2026-10-28: "redraft warning on top of the reply should
          have the redraft button on it, not below the message box") */}
      {warnTop && <Box data-tq-redraft-warn="" sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 0.75, px: 1.25, py: 0.75,
        border: "1px solid #e3c9a8", bgcolor: "#fbf3e8", borderRadius: 1.5 }}>
        <Typography component="span" data-tq-lit-why="" sx={{ flex: "1 1 220px", minWidth: 0, color: "#6b4a1f", fontSize: 13, overflowWrap: "anywhere" }}>{why}</Typography>
        <Button size="small" variant="contained" disableElevation disabled={off} onClick={redraft} title={btnHint("redraft")}>
          {redraftLabel}</Button>
      </Box>}
      {/* ...named for the Assistant when the owner asks it about this draft (pageView.js): the reply's own box, filled through its onChange */}
      {/* ...and while the AI writes it, its spinner IN the box (the owner, 2026-10-30: "spin in the box of drafting") */}
      <Box ref={draftRef} data-tq-draft-box="" data-tq-field="draft" data-tq-label="Reply draft" sx={{ position: "relative" }}>
        {drafting && <CircularProgress size={14} data-tq-drafting-spin="" sx={{ position: "absolute", top: 12, right: 12, zIndex: 1, color: FAINT }} />}
        <DraftField value={value} onChange={(e) => setText(e.target.value)} marks={blanks}
        placeholder={proposal?.kind === "closeout" ? proposal.placeholder : isCal ? "A note with your answer - or leave it empty" : drafting ? "Drafting…" : r.DraftText ? "" : proposal ? "Proposal details unavailable" : "No draft yet — hit Draft with AI"}
        inputProps={{ readOnly: off || delivery.frozen || !!proposal?.readOnly, style: { fontSize: 12.5, lineHeight: 1.45 } }} /></Box>
      {compare?.reviewId === r.ReviewId && (
        <Box sx={{ mt: 0.75, border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75, bgcolor: PANEL2 }}>
          <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 600, display: "block" }}>
            Refreshed draft - written after the new message. Your edit stays in the box above.
          </Typography>
          <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5, mt: 0.5 }}>{compare.refreshed || "(no refreshed draft - hit Redraft)"}</Typography>
          <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
            <Button size="small" variant="outlined" disabled={off || delivery.frozen || !compare.refreshed}
              onClick={() => { setText(compare.refreshed); setCompare(null); }}>Use the refreshed draft</Button>
            <Button size="small" sx={{ color: DIM }} onClick={() => setCompare(null)}>Keep mine</Button>
          </Box>
        </Box>
      )}
      <Box ref={movesRef} sx={{ display: "flex", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>
        {/* ONE approve: it sends whatever is in the box above, edited or not. Two buttons
            asked you to declare something the text already shows. */}
        {/* a channel that cannot carry the reply must SAY so: github with replies
            off gets 'No response required' as THE action, not a send that bounces */}
        <>
        {delivery.frozen ? (<>
          <Button size="small" variant={solid} disableElevation disabled={off || !delivery.canCheck}
            onClick={() => decide("approve")} title={delivery.line}>
            {busy ? "Checking delivery…" : delivery.label}
          </Button>
          {unconfirmed && <Button size="small" variant="outlined" disabled={off} onClick={sendAnyway} title={btnHint("approve", "unknown")}>{btn("approve", "unknown")}</Button>}
          {unconfirmed && r.TaskId && <Button size="small" variant="outlined" disabled={off} onClick={doneAnyway} title={btnHint("close")}>{btn("close")}</Button>}
        </>) : co && !r.Stale ? (
          /* ONE PRESS FOR THE LAST TWO ACTS (the owner, 2026-09-27: "shouldn't we combine this?"): the merge or
             close runs first, and the reply above goes out only once it succeeded. A reply this channel cannot
             carry leaves just the close-out. */
          <>
            <Button size="small" variant={solid} disableElevation disabled={off || blocked || (sendable && !words.trim())}
              onClick={() => decideBoth("approve")} title={blocked ? gh.reason : thenLine}>
              {busy ? sentOr(co.busyLabel) : co.approveLabel}</Button>
            {co.alt && <Button size="small" variant="outlined" disabled={off}
              onClick={() => decideBoth(co.alt.verb)} title={altTitle}>
              {altSends ? `${co.alt.label} & send your text` : co.alt.label}</Button>}
          </>
        ) : proposal ? (
          <Button size="small" variant={solid} disableElevation disabled={off || (proposal.kind === "closeout" && blocked)}
            onClick={() => decide("approve")}
            title={proposal.kind === "closeout" && blocked ? gh.reason : proposal.kind === "playbook"
              ? "Save this process in Reports → Playbooks; nothing is sent to the sender"
              : proposal.kind === "closeout" ? `${proposal.approveLabel} - the text above goes with it`
              : "Run the proposed action; nothing is sent to the sender"}>
            {busy ? sentOr(proposal.busyLabel) : proposal.approveLabel}
          </Button>
        ) : !canSendIt ? (
          /* COPY, BESIDE REDRAFT (the owner, 2026-10-22): the draft goes to the clipboard and the task stays open - its badge says it
             went; the reason nothing here can send it is the hover */
          <Button size="small" variant={lit === no("copy") ? "contained" : "outlined"} disableElevation disabled={off || !words.trim()} onClick={copyIt}
            title={copyTitle} data-tq-copy={copied ? "done" : ""}>
            {copied ? `✓ ${btn("copy", "done")}` : btn("copy")}</Button>
        ) : r.Stale ? (
          /* THE ROAD OUT OF THE WARNING. A stale draft disabled the only button on the card
             and left a faint "Refresh draft" at the far end of the row, so the answer to "a
             new message arrived" was a dead end (the owner, 2026-09-21: "can't hit approve &
             send since there is warning? just reprocess it then"). Refreshing IS the primary
             action while the thread is ahead of the draft. */
          <Button size="small" variant={solid} disableElevation disabled={off}
            onClick={redraft} title={btnHint("redraft")}>
            {redrafting ? "Redrafting…" : drafting ? "Drafting…" : btn("redraft")}
          </Button>
        ) : chatFile ? (
          <>
            <Button size="small" variant={solid} disableElevation disabled={off} onClick={onEmailInstead}
              title={`A ${r.Channel} message cannot carry a file - this writes an email with the file on it, which waits here for your yes`}>
              Reply by email with the file</Button>
            <Button size="small" variant="outlined" disabled={off || !words.trim()} onClick={() => decide("approve")}
              title={`Sends only the words to ${replyContext(r)} - no file goes with them`}>
              {busy ? sentOr("Sending…") : `${sendWord} without the file`}</Button>
          </>
        ) : (
          // ...a calendar answer's note may be empty (verdicts: `cal`), so an invite with none still has its Send - New → Meeting's pick
          // drafts one with no note, and the button sat grey over it (2026-10-28)
          <Button size="small" variant={solid}
            disabled={off || (!words.trim() && !isCal)}
            onClick={() => decide("approve")}
            title={simulated ? "Complete this temporary demo; no email is sent" : `Sends this response to ${replyContext(r)}`}>
            {/* the one word for the send, as everywhere (buttons.json) */}
            {busy ? sentOr(simulated ? "Simulating…" : "Sending…")
              : simulated ? "Simulate approval" : `${sendWord}${ccNow.length ? `, copying ${ccNow.length}` : ""}`}
          </Button>
        )}
        {/* Redraft beside the send, under the draft it rewrites - not at the far end of the row, and not on the task's bar */}
        {canRedraft && !r.Stale && !delivery.frozen && !warnTop && <Button size="small" variant={lit === no("redraft") ? "contained" : "outlined"} disableElevation disabled={off} onClick={redraft}
          title={btnHint("redraft")}>
          {redraftLabel}</Button>}
        {/* ...and one email of several can be let go: it drops that slot and closes nothing (slots.settled) */}
        {isSlot && onDrop && !delivery.frozen && <Button size="small" variant="outlined" disabled={off} onClick={onDrop}
          title="Drop this email - it is never sent, and the task stays open">Don't send</Button>}
        {/* no "No reply needed" - Mark done on the task is that (the owner, 2026-09-24: "no button should be that") */}
        {proposal?.alt && <Button size="small" variant="outlined" disabled={off || delivery.frozen} onClick={() => decide(proposal.alt.verb)}
          title={`${proposal.alt.label} - ${proposal.alt.then}`}>{proposal.alt.label}</Button>}
        {(co || proposal?.kind === "closeout") && onRemind && <Button size="small" disabled={off || delivery.frozen} onClick={(e) => onRemind(e)} title={remindTitle}>{btn("defer")}</Button>}
        {/* a close-out card is Close out / Decline / Remind me and nothing else (the owner, 2026-09-28: "what does reject
            reply mean here? don't think we need that") - the reply is edited or redrafted in place, never rejected apart;
            and a plain draft is Close out, Redraft (at the row's end) or the task bar's own Mark done (2026-10-01) */}
        {proposal && proposal.kind !== "closeout" && <Button size="small" color="error" disabled={off || delivery.frozen} onClick={() => decide("reject")} title={rejectTitle}>{proposal.rejectLabel}</Button>}
        {/* WHY IT IS LIT, BESIDE IT (the owner, 2026-10-28): the Advisor's reason for lighting Redraft over Send stood in the folded Agent
            section, and Close out showed a lit Redraft with no word of why. `why`: the task's Advisor line, said where its button is lit */}
        {why && !warnTop && String(lit || "").startsWith(`${r.ReviewId}:`) && <Typography component="span" data-tq-lit-why="" variant="body2"
          sx={{ alignSelf: "center", color: "#55697a", fontSize: 12.5, minWidth: 0, overflowWrap: "anywhere" }}>{why}</Typography>}
        </>
      </Box>
      {fillLine && <Alert severity="warning" data-tq-fill-in="" sx={{ mt: 0.75 }} onClose={() => setFillIn(false)}>{fillLine} - nothing was sent.</Alert>}
      {/* what the one word does HERE - the buttons never change, this line does */}
      {thenLine && <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>{thenLine}</Typography>}
      {(coFail || (gh && (blocked || gh.note))) && (() => {
        const text = coFail ? coFail.text.replace(/ - nothing was merged or sent$/, "") : blocked ? gh.reason : gh.note;
        const offers = coFail ? coFail.offers : gh.offers;
        const run = async (o) => {
          if (o === "anyway") return closeout ? decideBoth("merge_anyway") : decide("merge_anyway");
          setBusy(true); setErr(""); setSaid(""); setCoFail(null);
          try { setSaid(await act(o)); } catch (e) { setErr(e?.response?.data?.detail || "GitHub refused it"); }
          setBusy(false);
        };
        return (
          <Alert severity={coFail || blocked ? "warning" : "info"} sx={{ mt: 1 }} onClose={coFail ? () => setCoFail(null) : undefined}
            action={offers?.length ? <Box sx={{ display: "flex", gap: 0.5 }}>{offers.map((o) => (
              <Button key={o} size="small" color="inherit" disabled={off || delivery.frozen} title={OFFER_HINT[o]} onClick={() => run(o)}>{OFFER_LABEL[o]}</Button>
            ))}</Box> : null}>
            {coFail || blocked ? <b>Not now - nothing is merged or sent. </b> : null}{text}
          </Alert>
        );
      })()}
      {said && <Alert severity="success" sx={{ mt: 1 }} onClose={() => setSaid("")}>{said}. Press {btn("approve", "action")} again once the checks pass.</Alert>}
      {sendErr && (
        <Alert severity="error" sx={{ mt: 1 }} onClose={() => setSendErr("")}>
          <b>{failureHead(sendErr, !!proposal)}</b> {sendErr.message}
          {/* a proposal's failure is the act's own sentence ("The held step failed: ..."): no reply, no draft, nothing to send again */}
          {(sendErr.unknown || !proposal) && <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
            {sendErr.unknown ? "Check the original attempt before sending by any other route. A missing receipt will not cause Taskuary to send it again."
              : fix ? `The draft stays on the task - ${fix.label} below, then send it again.` : "The draft stays on the task. Correct the delivery problem, then send it again."}
          </Box>}
        </Alert>
      )}
    </Box>
  );
}
