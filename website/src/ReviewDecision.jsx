// ONE DECISION, WHEREVER IT IS SHOWN. What they wrote, what we would say back, and the verdict
// buttons - extracted from the review queue so the task page can hold the decision instead of
// sending you to another tab to make it (2026-09-22). A proposal (a playbook, a setting, an
// action) renders through the same card: proposalPresentation() gives it its own title, its
// destination and its own labels, and nothing is sent to a sender.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import ReplyFiles from "./ReplyFiles.jsx";
import { CLOSE_OUT, proposalPresentation, reviewText } from "./reviewProposal.js";
import { OFFER_HINT, OFFER_LABEL, useCloseoutState } from "./closeoutState.js";
import { PANEL2, BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { CcRow, timeAgo, cleanText, splitQuoted } from "./ui.jsx";
import { deliveryCc, deliveryFiles, deliveryMeta, replyContext } from "./replyDelivery.js";
import { useVerbs } from "./actionRow.js";
import { useDraftJob } from "./replyDraft.js";
import ApprovalInterrupt from "./ApprovalInterrupt.jsx";
import { interruptOf, resolveInterrupt } from "./approvalInterrupt.js";
import { replySendFailure, reviewDeliveryState } from "./sendState.js";

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
    <Typography variant="caption" sx={{ color: INK, fontWeight: 700 }}>{meta.customer}</Typography>
    <Typography variant="caption" sx={{ color: INK }}>${Number(meta.amount || 0).toFixed(2)}</Typography>
    <Typography variant="caption" sx={{ color: DIM }}>last month: {meta.previous_amount == null ? "—" : `$${Number(meta.previous_amount).toFixed(2)}`}</Typography>
    {meta.invoice_number && <Typography variant="caption" sx={{ color: DIM }}>Zoho {meta.invoice_number}</Typography>}
  </Box>
);

// `onOpenTask` is optional: on the task page you are already there.
// `closeout` is the task's pending close-out (merge the PR, close the issue): given beside its reply, the two are
// ONE decision on this card, and the close-out runs first (verdicts.decide's reply_text).
// `onMarkDone`: the task's own Mark done (TaskPage puts the task down at the press) - a reply draft's other choice.
// `onRemind`: the task's own Remind me - a close-out's "not now" (the owner, 2026-10-02: Not yet IS remind me later).
// `onSent`: a send or close-out that went through - the task page reads the task and, when that closed it, walks on.
// `toRow`: the decision's buttons are drawn by the action row above the chat line (layout B), not here - the same handlers, registered.
export default function ReviewDecision({ review: r, closeout, onChanged, onOpenTask, onMarkDone = null, onSent = null, onRemind = null, toRow = false, simulated = false, onDrop = null }) {
  const [text, setText] = useState(null);           // the owner's edit; null means "the draft as filed"
  const [cc, setCc] = useState(null);               // null means "the CC the draft was filed with"
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sendErr, setSendErr] = useState("");       // approved, but the channel refused it
  const [interrupt, setInterrupt] = useState(null); // PW-239: the click that did not send
  const [compare, setCompare] = useState(null);     // the refreshed draft, shown beside the owner's edit

  const delivery = reviewDeliveryState(r);
  const filedDelivery = delivery.frozen ? { ...r, Deliver: JSON.stringify(delivery.envelope) } : r;
  const proposal = proposalPresentation(r);
  const value = delivery.frozen ? delivery.body : text ?? reviewText(r);
  const ccNow = delivery.frozen ? deliveryCc(filedDelivery) : cc ?? deliveryCc(r);
  const meta = deliveryMeta(r);
  const co = closeout && !proposal ? proposalPresentation(closeout) : null;
  // a reply to a GitHub PR/issue IS a comment on it, so the close-out carries it whatever the replies switch says
  const carried = !!co && String(r.Channel || "").toLowerCase() === "github";
  const sendable = r.CanSend !== false || carried;
  // one of the task's emails (slots.py) is not its close-out: sending it closes nothing until the last one goes
  const isSlot = r.Kind === "slot";
  const onTask = !proposal && !!r.TaskId && r.Kind !== "clarification" && !isSlot;
  const thenLine = delivery.frozen ? "" : simulated ? "This approves the fictional reply and completes the demo task. No email is sent."
    : co ? `${CLOSE_OUT} ${co.then}${sendable ? `, then sends your reply to ${replyContext(r)}` : ""}.`
    : onTask && !r.Stale && r.CanSend !== false ? `${CLOSE_OUT} sends this to ${replyContext(r)} and closes the task.` : "";
  const [coFail, setCoFail] = useState(null);       // the close-out itself refused: nothing was sent ({offers} = what fits instead)
  const [said, setSaid] = useState("");              // what Update branch / Re-run checks just did
  // THE CARD READS GITHUB FIRST (closeoutState.js): Close out is live only when this repo's rules let it merge now
  const coRid = closeout?.ReviewId || (proposal?.kind === "closeout" ? r.ReviewId : null);
  const { gh, reload: reloadGh, act } = useCloseoutState(coRid);
  const blocked = !!gh && !gh.ok;
  // A REPLY OPENED AT ONCE is drawn before its draft exists (replyDraft.js, 2026-10-01): "Drafting…" until the model is done,
  // then the task is read again and the draft is in the box; one that could not be written says why here
  const job = useDraftJob(r.ReviewId);
  const drafting = job?.state === "drafting";
  useEffect(() => {
    if (job?.state === "done") onChanged?.();
    if (job?.state === "failed") setErr(`The draft could not be written - ${job.error}. Write it here, or Draft with AI again.`);
  }, [job]);   // eslint-disable-line react-hooks/exhaustive-deps

  const decideBoth = async (verb) => {
    if (delivery.frozen) return;
    setBusy(true); setErr(""); setSendErr(""); setCoFail(null);
    try {
      const { data } = await api.post(`/api/reviews/${closeout.ReviewId}/decide`,
        { verb, final_text: null, note: null, reply_text: verb !== "reject" && sendable && value.trim() ? value : null, cc: sendable ? ccNow : null });
      // refused before anything happened is not "approved, but it did not send"
      if (!data.ok && data.send_error) setCoFail({ text: data.send_error, offers: data.offers || [] });
      else if (data.send_error) setSendErr(replySendFailure(data));
      // WAIT FOR IT, THEN MOVE ON (the owner, 2026-10-02): the close-out landed with no error, so the task may be closed now
      else if (data.ok && verb !== "reject" && onSent) { await onSent(); setBusy(false); return; }
      reloadGh(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
    setBusy(false);
  };

  // Approving IS sending, so a send that failed has to say so HERE, the moment you click - it
  // used to return quietly and leave a "NOT SENT" line in the task history for you to find later.
  const decide = async (verb) => {
    if (delivery.active || (delivery.frozen && verb !== "approve")) return;
    setBusy(true); setErr(""); setSendErr("");
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/decide`,
        { verb, final_text: verb === "approve" && !delivery.frozen ? value : null, note: null,
          // only on the send: rejecting or "no reply needed" copies nobody on nothing
          cc: verb === "approve" && !proposal && !delivery.frozen ? ccNow : null });
      const it = interruptOf(data, r.ReviewId);
      if (it) { setInterrupt(it); onChanged?.(); setBusy(false); return; }
      // a close-out GitHub's state refused is "not now", with what fits instead - never "approved, but it did not send"
      if (data.refused) { setCoFail({ text: data.send_error || "", offers: data.offers || [] }); reloadGh(); }
      else if (data.send_error) setSendErr(replySendFailure(data));
      // Close out / Approve & send is not put down at the press: it waits for the send so an error shows HERE, then the
      // task page closes the walk on it when that send closed the task (the owner, 2026-10-02)
      else if (data.ok && verb === "approve" && onSent) { await onSent(); setBusy(false); return; }
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
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
    setBusy(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/draft`); setText(null); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Redraft failed"); }
    setBusy(false);
  };

  // THE DECISION'S VERBS, one list for the card's buttons and the action row: what presses, what it says, when it is off
  const no = (id) => `${r.ReviewId}:${id}`;
  const rejectTitle = "Dismisses it - nothing runs and nothing is sent";
  const remindTitle = "Puts the task away until a day - nothing is merged, closed or sent; it is back on your rail that morning";
  const doneTitle = "Marks the task done without sending - the draft stays on it, to send later if you want";
  // Redraft / Refresh / Draft with AI: the same handler the in-card button has
  const canRedraft = !proposal && meta.kind !== "zoho_invoice" && !isSlot;   // the redrafter writes a REPLY to the sender
  const redraftWord = r.Stale ? "Refresh draft" : r.DraftText ? "Redraft" : "Draft with AI";
  // the alternative (Decline) sends WHAT IS IN THE BOX, edited or not - and with the box empty it just closes the pull request, sending nothing
  const altSends = sendable && !!value.trim();
  const altTitle = co?.alt ? `${co.alt.label} ${co.alt.then}${altSends ? ", then sends the text above exactly as you have it - edit it first if it reads as an accept" : ". The box is empty, so nothing is sent"}.` : "";
  const moves = r.Status !== "pending" ? [] : [
    ...(delivery.frozen ? [
      { id: no("approve"), label: busy ? "Checking delivery…" : delivery.label, tone: "p", disabled: busy || !delivery.canCheck,
        run: () => decide("approve"), title: delivery.line, why: delivery.active ? "waiting for the provider" : "" },
    ] : co && !r.Stale ? [
      { id: no("approve"), label: busy ? co.busyLabel : co.approveLabel, tone: "p", title: blocked ? gh.reason : thenLine, disabled: busy || blocked || (sendable && !value.trim()), run: () => decideBoth("approve"),
        why: blocked ? gh.reason.split(" - ")[0] : sendable && !value.trim() ? "write the reply first" : "" },
      ...(co.alt ? [{ id: no("alt"), label: altSends ? `${co.alt.label} & send your text` : co.alt.label, tone: "s", title: altTitle, disabled: busy, run: () => decideBoth(co.alt.verb) }] : []),
    ] : proposal ? [
      { id: no("approve"), label: busy ? proposal.busyLabel : proposal.approveLabel, tone: "p", disabled: busy || (proposal.kind === "closeout" && blocked), run: () => decide("approve"),
        why: proposal.kind === "closeout" && blocked ? gh.reason.split(" - ")[0] : "",
        title: proposal.kind === "closeout" && blocked ? gh.reason : proposal.kind === "playbook" ? "Save this process in Docs → Playbooks; nothing is sent to the sender"
          : proposal.kind === "closeout" ? `${proposal.approveLabel} - the text above goes with it` : "Run the proposed action; nothing is sent to the sender" },
    ] : r.CanSend === false ? [
      { id: no("approve"), label: busy ? "closing…" : "Mark done", tone: "p", disabled: busy, run: () => decide("close_unsent"),
        title: `No reply will be sent - ${r.SendBlock || (r.Channel === "github" ? "GitHub replies are off (GitHub card)" : "this channel cannot be replied to from here")}. The draft is kept; the task is marked done (PW-145).` },
    ] : r.Stale ? [
      { id: no("approve"), label: busy ? "refreshing…" : "Refresh the draft", tone: "p", disabled: busy, run: redraft, title: "Rewrites the draft from the newest message, then you approve it" },
    ] : [
      { id: no("approve"), label: busy ? (simulated ? "Simulating…" : "sending…") : simulated ? "Simulate approval" : `${onTask ? CLOSE_OUT : "Approve & send"}${ccNow.length ? `, copying ${ccNow.length}` : ""}`, tone: "p", disabled: busy || !value.trim(), why: value.trim() ? "" : "write the reply first",
        run: () => decide("approve"), title: simulated ? "Complete this temporary demo; no email is sent" : `Sends this response to ${replyContext(r)}` },
    ]),
    ...(proposal?.alt ? [{ id: no("palt"), label: proposal.alt.label, tone: "s", disabled: busy, run: () => decide(proposal.alt.verb), title: `${proposal.alt.label} - ${proposal.alt.then}` }] : []),
    // A CLOSE-OUT HAS NO "NOT YET" (the owner, 2026-10-02): Next keeps it open and moves on, Remind me keeps it open until a day
    ...(co || proposal?.kind === "closeout" ? (onRemind ? [{ id: no("remind"), label: "Remind me", tone: "q", disabled: busy, run: onRemind, title: remindTitle }] : [])
      : proposal ? [{ id: no("reject"), label: proposal.rejectLabel, tone: "q", disabled: busy, run: () => decide("reject"), title: rejectTitle }]
      // A REPLY DRAFT IS NEVER REJECTED (the owner, 2026-10-01: "rejected is useless - it should be redraft or close task"): Reject
      // threw the draft away and left the task open, which is neither. Its other choices are Redraft and the task's own Mark done.
      : [...(canRedraft && !r.Stale ? [{ id: no("redraft"), group: "decide", tone: "s", label: drafting ? "Drafting…" : redraftWord, disabled: busy || drafting, run: redraft,
          title: "Writes the draft again from the thread as it is now; your edit is kept beside it until you choose" }] : []),
        ...(onMarkDone && r.CanSend !== false ? [{ id: no("done"), group: "decide", closes: true, tone: "s", label: "Mark done", disabled: busy, run: onMarkDone, title: doneTitle }] : [])]),
  ].map((v) => ({ ...v, group: "decide", disabled: v.disabled || (delivery.frozen && v.id !== no("approve")) }));
  // ...and behind More where the decision does not carry it already (a close-out; a stale draft's Refresh is the move itself)
  useVerbs(`decision:${r.ReviewId}`, [...moves, ...(canRedraft && moves.length && !moves.some((v) => v.id === no("redraft")) ? [{ id: no("redraft"), group: "more", tone: "s", label: drafting ? "Drafting…" : redraftWord, disabled: busy || drafting || delivery.frozen, run: redraft,
    title: "Writes the draft again from the thread as it is now; your edit is kept beside it until you choose" }] : [])], toRow && moves.length > 0);

  if (r.Status === "held") {
    return (
      <Box sx={{ mt: 0.5, bgcolor: "#e3e6e1", border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75 }}>
        <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700, display: "block" }}>
          Waiting on the agent working this task
        </Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25 }}>
          This reply was drafted from the message alone, before anyone had looked at the problem — so it
          would be promising what nobody has checked yet. When the session is wrapped up, it comes back
          here rewritten from what the agent actually found.
        </Typography>
        <Box sx={{ display: "flex", gap: 0.75, mt: 0.75, alignItems: "center" }}>
          <Button size="small" variant="outlined" disabled={busy || delivery.frozen} onClick={release}>Answer now anyway</Button>
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
      {!proposal && <Inbound r={r} />}
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
        <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 800,
          letterSpacing: "1.5px", flexShrink: 0 }}>{proposal?.destinationLabel || "TO"}</Typography>
        <Typography variant="body2" sx={{ color: INK, fontWeight: 650 }} noWrap>
          {proposal?.destination || replyContext(filedDelivery)}
        </Typography>
      </Box>
      {co && (
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
          <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 800, letterSpacing: "1.5px", flexShrink: 0 }}>{co.destinationLabel}</Typography>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 650 }} noWrap>{co.destination}</Typography>
          <Typography variant="caption" sx={{ color: FAINT }} noWrap>· first, then the reply goes out</Typography>
        </Box>
      )}
      {!proposal && <ReplyFiles reviewId={r.ReviewId} files={deliveryFiles(filedDelivery)}
        text={value} channel={r.Channel} onChanged={onChanged} toRow={toRow} disabled={busy || delivery.frozen} />}
      {!proposal && (busy || delivery.frozen) ? String(r.Channel || "").toLowerCase() === "email" && (
        <Typography variant="caption" data-tq-delivery-cc sx={{ display: "block", color: DIM, mb: 0.75 }}>
          CC: {ccNow.length ? ccNow.join(", ") : "none"}
        </Typography>
      ) : !proposal && <CcRow cc={ccNow} setCc={setCc} channel={r.Channel} />}
      {/* WHY THERE IS NO SEND BUTTON, on the surface rather than under a hover. The server writes
          this one sentence for exactly this (outbound.send_block, PW-044) and every other surface
          shows it; here it lived only in the tooltip of the button that replaced Send, so a drafted
          answer with nowhere to go looked like a card that had simply lost its button. The draft is
          real and worth reading - a GitHub task with replies off is still answered, by hand. */}
      {!proposal && !carried && r.CanSend === false && (
        <Typography variant="caption" sx={{ display: "block", color: DIM, mb: 0.5 }}>
          No reply can be sent from here — {r.SendBlock || "this channel cannot be replied to"}. The draft stays for you to use.
        </Typography>
      )}
      <TextField fullWidth multiline minRows={2} maxRows={r.Kind === "action" ? 24 : 8}
        value={value} onChange={(e) => setText(e.target.value)}
        placeholder={proposal?.kind === "closeout" ? proposal.placeholder : drafting ? "Drafting…" : r.DraftText ? "" : proposal ? "Proposal details unavailable" : "No draft yet — hit Draft with AI"}
        inputProps={{ readOnly: busy || delivery.frozen, style: { fontSize: 12.5, lineHeight: 1.45 } }} />
      {compare?.reviewId === r.ReviewId && (
        <Box sx={{ mt: 0.75, border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75, bgcolor: PANEL2 }}>
          <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700, display: "block" }}>
            Refreshed draft - written after the new message. Your edit stays in the box above.
          </Typography>
          <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5, mt: 0.5 }}>{compare.refreshed || "(no refreshed draft - hit Redraft)"}</Typography>
          <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
            <Button size="small" variant="outlined" disabled={busy || delivery.frozen || !compare.refreshed}
              onClick={() => { setText(compare.refreshed); setCompare(null); }}>Use the refreshed draft</Button>
            <Button size="small" sx={{ color: DIM }} onClick={() => setCompare(null)}>Keep mine</Button>
          </Box>
        </Box>
      )}
      <Box sx={{ display: "flex", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>
        {/* ONE approve: it sends whatever is in the box above, edited or not. Two buttons
            asked you to declare something the text already shows. */}
        {/* a channel that cannot carry the reply must SAY so: github with replies
            off gets 'No response required' as THE action, not a send that bounces */}
        {!toRow && <>
        {delivery.frozen ? (
          <Button size="small" variant="contained" disableElevation disabled={busy || !delivery.canCheck}
            onClick={() => decide("approve")} title={delivery.line}>
            {busy ? "Checking delivery…" : delivery.label}
          </Button>
        ) : co && !r.Stale ? (
          /* ONE PRESS FOR THE LAST TWO ACTS (the owner, 2026-09-27: "shouldn't we combine this?"): the merge or
             close runs first, and the reply above goes out only once it succeeded. A reply this channel cannot
             carry leaves just the close-out. */
          <>
            <Button size="small" variant="contained" disableElevation disabled={busy || blocked || (sendable && !value.trim())}
              onClick={() => decideBoth("approve")} title={blocked ? gh.reason : thenLine}>
              {busy ? co.busyLabel : co.approveLabel}</Button>
            {co.alt && <Button size="small" variant="outlined" disabled={busy}
              onClick={() => decideBoth(co.alt.verb)} title={altTitle}>
              {altSends ? `${co.alt.label} & send your text` : co.alt.label}</Button>}
          </>
        ) : proposal ? (
          <Button size="small" variant="contained" disableElevation disabled={busy || (proposal.kind === "closeout" && blocked)}
            onClick={() => decide("approve")}
            title={proposal.kind === "closeout" && blocked ? gh.reason : proposal.kind === "playbook"
              ? "Save this process in Docs → Playbooks; nothing is sent to the sender"
              : proposal.kind === "closeout" ? `${proposal.approveLabel} - the text above goes with it`
              : "Run the proposed action; nothing is sent to the sender"}>
            {busy ? proposal.busyLabel : proposal.approveLabel}
          </Button>
        ) : r.CanSend === false ? (
          <Button size="small" variant="contained" disableElevation disabled={busy}
            sx={{ bgcolor: "#8a8276", "&:hover": { bgcolor: "#6b6459" } }}
            title={`No reply will be sent - ${r.SendBlock || (r.Channel === "github" ? "GitHub replies are off (GitHub card)" : "this channel cannot be replied to from here")}. The draft is kept; the task is marked done (PW-145).`}
            onClick={() => decide("close_unsent")}>
            {busy ? "closing…" : "Mark done"}
          </Button>
        ) : r.Stale ? (
          /* THE ROAD OUT OF THE WARNING. A stale draft disabled the only button on the card
             and left a faint "Refresh draft" at the far end of the row, so the answer to "a
             new message arrived" was a dead end (the owner, 2026-09-21: "can't hit approve &
             send since there is warning? just reprocess it then"). Refreshing IS the primary
             action while the thread is ahead of the draft. */
          <Button size="small" variant="contained" disableElevation disabled={busy}
            onClick={redraft} title="Rewrites the draft from the newest message, then you approve it">
            {busy ? "refreshing…" : "Refresh the draft"}
          </Button>
        ) : (
          <Button size="small" variant="contained"
            disabled={busy || !value.trim()}
            onClick={() => decide("approve")}
            title={simulated ? "Complete this temporary demo; no email is sent" : `Sends this response to ${replyContext(r)}`}>
            {/* on a task the one word is Close out, as everywhere; a draft with no task behind it is just sent */}
            {busy ? (simulated ? "Simulating…" : "sending…")
              : simulated ? "Simulate approval" : `${onTask ? CLOSE_OUT : "Approve & send"}${ccNow.length ? `, copying ${ccNow.length}` : ""}`}
          </Button>
        )}
        {/* ...but one email of several can be let go without closing anything: it drops that slot (slots.settled) */}
        {isSlot && onDrop && !delivery.frozen && <Button size="small" variant="outlined" disabled={busy} onClick={onDrop}
          title="Drop this email - the task closes when the rest are sent">Don't send</Button>}
        {/* no "No reply needed" - Mark done on the task is that (the owner, 2026-09-24: "no button should be that") */}
        {proposal?.alt && <Button size="small" variant="outlined" disabled={busy || delivery.frozen} onClick={() => decide(proposal.alt.verb)}
          title={`${proposal.alt.label} - ${proposal.alt.then}`}>{proposal.alt.label}</Button>}
        {(co || proposal?.kind === "closeout") && onRemind && <Button size="small" disabled={busy || delivery.frozen} onClick={(e) => onRemind(e)} title={remindTitle}>Remind me</Button>}
        {/* a close-out card is Close out / Decline / Remind me and nothing else (the owner, 2026-09-28: "what does reject
            reply mean here? don't think we need that") - the reply is edited or redrafted in place, never rejected apart;
            and a plain draft is Close out, Redraft (at the row's end) or the task bar's own Mark done (2026-10-01) */}
        {proposal && proposal.kind !== "closeout" && <Button size="small" color="error" disabled={busy || delivery.frozen} onClick={() => decide("reject")} title={rejectTitle}>{proposal.rejectLabel}</Button>}
        </>}
        <Box sx={{ flex: 1 }} />
        {!toRow && canRedraft && <Button size="small" disabled={busy || drafting || delivery.frozen} onClick={redraft}>
          {busy ? <CircularProgress size={12} /> : drafting ? "Drafting…" : redraftWord}
        </Button>}
      </Box>
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
              <Button key={o} size="small" color="inherit" disabled={busy || delivery.frozen} title={OFFER_HINT[o]} onClick={() => run(o)}>{OFFER_LABEL[o]}</Button>
            ))}</Box> : null}>
            {coFail || blocked ? <b>Not now - nothing is merged or sent. </b> : null}{text}
          </Alert>
        );
      })()}
      {said && <Alert severity="success" sx={{ mt: 1 }} onClose={() => setSaid("")}>{said}. Close out again once the checks pass.</Alert>}
      {sendErr && (
        <Alert severity="error" sx={{ mt: 1 }} onClose={() => setSendErr("")}>
          <b>{sendErr.unknown ? "Delivery has not been confirmed." : "The reply was not sent."}</b> {sendErr.message}
          <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
            {sendErr.unknown ? "Check the original attempt before sending by any other route. A missing receipt will not cause Taskuary to send it again."
              : "The draft stays on the task. Correct the delivery problem, then approve it again."}
          </Box>
        </Alert>
      )}
    </Box>
  );
}
