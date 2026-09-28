// ONE DECISION, WHEREVER IT IS SHOWN. What they wrote, what we would say back, and the verdict
// buttons - extracted from the review queue so the task page can hold the decision instead of
// sending you to another tab to make it (2026-09-22). A proposal (a playbook, a setting, an
// action) renders through the same card: proposalPresentation() gives it its own title, its
// destination and its own labels, and nothing is sent to a sender.
import React, { useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import ReplyFiles from "./ReplyFiles.jsx";
import { CLOSE_OUT, proposalPresentation, reviewText } from "./reviewProposal.js";
import { PANEL2, BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { CcRow, timeAgo, cleanText, splitQuoted } from "./ui.jsx";
import { deliveryCc, deliveryFiles, deliveryMeta, replyContext } from "./replyDelivery.js";
import ApprovalInterrupt from "./ApprovalInterrupt.jsx";
import { interruptOf, resolveInterrupt } from "./approvalInterrupt.js";

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
export default function ReviewDecision({ review: r, closeout, onChanged, onOpenTask }) {
  const [text, setText] = useState(null);           // the owner's edit; null means "the draft as filed"
  const [cc, setCc] = useState(null);               // null means "the CC the draft was filed with"
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sendErr, setSendErr] = useState("");       // approved, but the channel refused it
  const [interrupt, setInterrupt] = useState(null); // PW-239: the click that did not send
  const [compare, setCompare] = useState(null);     // the refreshed draft, shown beside the owner's edit

  const proposal = proposalPresentation(r);
  const value = text ?? reviewText(r);
  const ccNow = cc ?? deliveryCc(r);
  const meta = deliveryMeta(r);
  const co = closeout && !proposal ? proposalPresentation(closeout) : null;
  // a reply to a GitHub PR/issue IS a comment on it, so the close-out carries it whatever the replies switch says
  const carried = !!co && String(r.Channel || "").toLowerCase() === "github";
  const sendable = r.CanSend !== false || carried;
  const onTask = !proposal && !!r.TaskId && r.Kind !== "clarification";
  const thenLine = co ? `${CLOSE_OUT} ${co.then}${sendable ? `, then sends your reply to ${replyContext(r)}` : ""}.`
    : onTask && !r.Stale && r.CanSend !== false ? `${CLOSE_OUT} sends this to ${replyContext(r)} and closes the task.` : "";
  const [coFail, setCoFail] = useState(null);       // the close-out itself refused: nothing was sent ({red} = checks)

  const decideBoth = async (verb) => {
    setBusy(true); setErr(""); setSendErr(""); setCoFail(null);
    try {
      const { data } = await api.post(`/api/reviews/${closeout.ReviewId}/decide`,
        { verb, final_text: null, note: null, reply_text: verb !== "reject" && sendable ? value : null, cc: sendable ? ccNow : null });
      // refused before anything happened is not "approved, but it did not send"
      if (!data.ok && data.send_error) setCoFail({ text: data.send_error, red: !!data.checks_red });
      else if (data.send_error) setSendErr(data.send_error);
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
    setBusy(false);
  };

  // Approving IS sending, so a send that failed has to say so HERE, the moment you click - it
  // used to return quietly and leave a "NOT SENT" line in the task history for you to find later.
  const decide = async (verb) => {
    setBusy(true); setErr(""); setSendErr("");
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/decide`,
        { verb, final_text: verb === "approve" ? value : null, note: null,
          // only on the send: rejecting or "no reply needed" copies nobody on nothing
          cc: verb === "approve" && !proposal ? ccNow : null });
      const it = interruptOf(data, r.ReviewId);
      if (it) { setInterrupt(it); onChanged?.(); setBusy(false); return; }
      if (data.send_error) setSendErr(data.send_error);
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
    setBusy(false);
  };

  // A held draft is one the session's findings will rewrite. Sometimes the sender needs telling
  // something today anyway - a reply stuck behind an agent that never finished is worse.
  const release = async () => {
    setBusy(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/release`); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not release it"); }
    setBusy(false);
  };

  const redraft = async () => {
    setBusy(true);
    try { await api.post(`/api/reviews/${r.ReviewId}/draft`); setText(null); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Redraft failed"); }
    setBusy(false);
  };

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
          <Button size="small" variant="outlined" disabled={busy} onClick={release}>Answer now anyway</Button>
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
      {!!r.Stale && <Alert severity="warning" sx={{ mb: 1 }}>
        New messages arrived after this draft. Refresh the draft before sending it.
        {r.LatestPreview && <Box sx={{ mt: 0.5, fontSize: 11.5 }}>Latest: {r.LatestPreview}</Box>}
      </Alert>}
      {!proposal && <Inbound r={r} />}
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
        <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 800,
          letterSpacing: "1.5px", flexShrink: 0 }}>{proposal?.destinationLabel || "TO"}</Typography>
        <Typography variant="body2" sx={{ color: INK, fontWeight: 650 }} noWrap>
          {proposal?.destination || replyContext(r)}
        </Typography>
      </Box>
      {co && (
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
          <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 800, letterSpacing: "1.5px", flexShrink: 0 }}>{co.destinationLabel}</Typography>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 650 }} noWrap>{co.destination}</Typography>
          <Typography variant="caption" sx={{ color: FAINT }} noWrap>· first, then the reply goes out</Typography>
        </Box>
      )}
      {!proposal && <ReplyFiles reviewId={r.ReviewId} files={deliveryFiles(r)}
        text={value} channel={r.Channel} onChanged={onChanged} />}
      {!proposal && <CcRow cc={ccNow} setCc={setCc} channel={r.Channel} />}
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
        placeholder={proposal?.kind === "closeout" ? proposal.placeholder : r.DraftText ? "" : proposal ? "Proposal details unavailable" : "No draft yet — hit Draft with AI"}
        inputProps={{ style: { fontSize: 12.5, lineHeight: 1.45 } }} />
      {compare?.reviewId === r.ReviewId && (
        <Box sx={{ mt: 0.75, border: "1px solid #d2d6cf", borderRadius: 1.5, px: 1.25, py: 0.75, bgcolor: PANEL2 }}>
          <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700, display: "block" }}>
            Refreshed draft - written after the new message. Your edit stays in the box above.
          </Typography>
          <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap", fontSize: 12.5, mt: 0.5 }}>{compare.refreshed || "(no refreshed draft - hit Redraft)"}</Typography>
          <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
            <Button size="small" variant="outlined" disabled={!compare.refreshed}
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
        {co && !r.Stale ? (
          /* ONE PRESS FOR THE LAST TWO ACTS (the owner, 2026-09-27: "shouldn't we combine this?"): the merge or
             close runs first, and the reply above goes out only once it succeeded. A reply this channel cannot
             carry leaves just the close-out. */
          <>
            <Button size="small" variant="contained" disableElevation disabled={busy || (sendable && !value.trim())}
              onClick={() => decideBoth("approve")} title={thenLine}>
              {busy ? co.busyLabel : co.approveLabel}</Button>
            {co.alt && <Button size="small" variant="outlined" disabled={busy || (sendable && !value.trim())}
              onClick={() => decideBoth(co.alt.verb)} title={`${co.alt.label} ${co.alt.then}${sendable ? ", then sends your reply" : ""}.`}>
              {co.alt.label}</Button>}
          </>
        ) : proposal ? (
          <Button size="small" variant="contained" disableElevation disabled={busy}
            onClick={() => decide("approve")}
            title={proposal.kind === "playbook"
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
            title={`Sends this response to ${replyContext(r)}`}>
            {/* on a task the one word is Close out, as everywhere; a draft with no task behind it is just sent */}
            {busy ? "sending…"
              : `${onTask ? CLOSE_OUT : "Approve & send"}${ccNow.length ? `, copying ${ccNow.length}` : ""}`}
          </Button>
        )}
        {/* no "No reply needed" - Mark done on the task is that (the owner, 2026-09-24: "no button should be that") */}
        {proposal?.alt && <Button size="small" variant="outlined" disabled={busy} onClick={() => decide(proposal.alt.verb)}
          title={`${proposal.alt.label} - ${proposal.alt.then}`}>{proposal.alt.label}</Button>}
        {co && <Button size="small" disabled={busy} onClick={() => decideBoth("reject")}
          title="Leaves the pull request as it is; the task stays open and on you, the reply unsent">{co.rejectLabel}</Button>}
        <Button size="small" color="error" disabled={busy} onClick={() => decide("reject")}>{proposal?.rejectLabel || (co ? "Reject reply" : "Reject")}</Button>
        <Box sx={{ flex: 1 }} />
        {!proposal && meta.kind !== "zoho_invoice" && <Button size="small" disabled={busy} onClick={redraft}>
          {busy ? <CircularProgress size={12} /> : r.Stale ? "Refresh draft" : r.DraftText ? "Redraft" : "Draft with AI"}
        </Button>}
      </Box>
      {/* what the one word does HERE - the buttons never change, this line does */}
      {thenLine && <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5 }}>{thenLine}</Typography>}
      {coFail && (
        <Alert severity="warning" sx={{ mt: 1 }} onClose={() => setCoFail(null)}
          action={coFail.red && (
            <Button size="small" color="inherit" disabled={busy} onClick={() => decideBoth("merge_anyway")}
              title="Merges although these checks are red - use it when they fail on the default branch too. A check the repository requires is still GitHub's to enforce.">
              {`${CLOSE_OUT} anyway`}</Button>
          )}>
          <b>Not done - nothing was merged or sent.</b> {coFail.text.replace(/ - nothing was merged or sent$/, "")}
        </Alert>
      )}
      {sendErr && (
        <Alert severity="error" sx={{ mt: 1 }} onClose={() => setSendErr("")}>
          <b>Approved, but it did not send.</b> {sendErr}
          <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
            The text is kept on the task marked NOT SENT, so nothing is lost — send it by hand,
            or hand the task to a person on a channel that works.
          </Box>
        </Alert>
      )}
    </Box>
  );
}
