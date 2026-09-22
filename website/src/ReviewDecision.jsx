// ONE DECISION, WHEREVER IT IS SHOWN. What they wrote, what we would say back, and the verdict
// buttons - extracted from the Review tab so the task page can hold the decision instead of
// sending you to another tab to make it (2026-09-22). A proposal (a playbook, a setting, an
// action) renders through the same card: proposalPresentation() gives it its own title, its
// destination and its own labels, and nothing is sent to a sender.
import React, { useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import ReplyFiles from "./ReplyFiles.jsx";
import { proposalPresentation, reviewText } from "./reviewProposal.js";
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
export default function ReviewDecision({ review: r, onChanged, onOpenTask }) {
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
      {r.Reason && (r.DraftText || !/draft/i.test(r.Reason)) && (
        <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mb: 0.5 }}>{r.Reason}</Typography>
      )}
      {meta.kind === "zoho_invoice" && <InvoiceLine meta={meta} />}
      {r.Stale && <Alert severity="warning" sx={{ mb: 1 }}>
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
      {!proposal && <ReplyFiles reviewId={r.ReviewId} files={deliveryFiles(r)}
        text={value} channel={r.Channel} onChanged={onChanged} />}
      {!proposal && <CcRow cc={ccNow} setCc={setCc} channel={r.Channel} />}
      <TextField fullWidth multiline minRows={2} maxRows={r.Kind === "action" ? 24 : 8}
        value={value} onChange={(e) => setText(e.target.value)}
        placeholder={r.DraftText ? "" : proposal ? "Proposal details unavailable" : "No draft yet — hit Draft with AI"}
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
        {proposal ? (
          <Button size="small" variant="contained" disableElevation disabled={busy}
            onClick={() => decide("approve")}
            title={proposal.kind === "playbook"
              ? "Save this process in Docs → Playbooks; nothing is sent to the sender"
              : "Run the proposed action; nothing is sent to the sender"}>
            {busy ? proposal.busyLabel : proposal.approveLabel}
          </Button>
        ) : r.CanSend === false ? (
          <Button size="small" variant="contained" disableElevation disabled={busy}
            sx={{ bgcolor: "#8a8276", "&:hover": { bgcolor: "#6b6459" } }}
            title={`No reply will be sent - ${r.SendBlock || (r.Channel === "github" ? "GitHub replies are off (GitHub card)" : "this channel cannot be replied to from here")}. The draft is kept; the task closes as your decision (PW-145).`}
            onClick={() => decide("close_unsent")}>
            {busy ? "closing…" : "Close without sending"}
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
            {busy ? "sending…"
              : ccNow.length ? `Approve & send, copying ${ccNow.length}`
              : "Approve & send"}
          </Button>
        )}
        {!proposal && r.CanSend !== false && (
          <Button size="small" sx={{ color: "#867f74" }} disabled={busy}
            onClick={() => decide("no_reply")}>No reply needed</Button>
        )}
        <Button size="small" color="error" disabled={busy} onClick={() => decide("reject")}>{proposal?.rejectLabel || "Reject"}</Button>
        <Box sx={{ flex: 1 }} />
        {!proposal && meta.kind !== "zoho_invoice" && <Button size="small" disabled={busy} onClick={redraft}>
          {busy ? <CircularProgress size={12} /> : r.Stale ? "Refresh draft" : r.DraftText ? "Redraft" : "Draft with AI"}
        </Button>}
      </Box>
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
