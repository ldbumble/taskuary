// Review queue: decide without leaving the row - inbound message on the left, the agent's
// draft on the right, verdict buttons underneath. Escalations carry no draft by design.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, card, PILL_COLORS } from "./theme.jsx";
import { CcRow, ChannelIcon, RefChip, timeAgo, Empty, FilterPills, cleanText, splitQuoted } from "./ui.jsx";

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

const FILTERS = [
  { key: "pending", label: "pending", c: PILL_COLORS.you },
  { key: "held", label: "waiting on the agent", c: PILL_COLORS.teal },
  { key: "auto", label: "auto-handled", c: PILL_COLORS.teal },
  { key: "approved", label: "approved", c: PILL_COLORS.green }, { key: "edited", label: "edited" },
  { key: "no_reply", label: "no reply", c: PILL_COLORS.gray }, { key: "rejected", label: "rejected", c: PILL_COLORS.bad },
  { key: "", label: "all" },
];

const deliveryTo = (review) => {
  try {
    const raw = JSON.parse(review.Deliver || "null")?.to;
    const to = Array.isArray(raw) ? raw.filter(Boolean).join(", ") : String(raw || "").trim();
    if (to) return to;
  } catch { /* replies to inbound messages do not carry Deliver */ }
  if (review.FromName && review.FromEmail) return `${review.FromName} <${review.FromEmail}>`;
  return review.FromName || review.FromEmail || review.ConversationId || "this conversation";
};
const deliveryMeta = (review) => {
  try { return JSON.parse(review.Deliver || "null") || {}; } catch { return {}; }
};

const replyContext = (review) => {
  const channel = String(review.Channel || "").toLowerCase();
  if (["whatsapp", "teams", "slack", "telegram", "discord", "imessage"].includes(channel)) {
    return `${deliveryTo(review)} in ${review.SourceName || (channel === "whatsapp" ? "the chat" : channel)}`;
  }
  return deliveryTo(review);
};

// A proposed PLAYBOOK is a page of markdown inside a JSON envelope: show the page, and let the owner
// edit it before approving - the edited page is what gets filed (proposals.execute).
const proposalText = (t) => {
  try { const j = JSON.parse(t || ""); if (j?.action === "write_playbook" && j.text) return j.text; } catch { /* a plain draft */ }
  return t || "";
};

export default function ReviewView({ onOpenTask, onChanged }) {
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [sendErr, setSendErr] = useState(null);   // approved, but the channel refused it

  const load = useCallback(async () => {
    try { setRows((await api.get("/api/reviews", { params: filter ? { status: filter } : {} })).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load reviews"); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  // Who else gets this answer. Held here and nowhere else: the copy list you can SEE on the card
  // is the one that sends, and a reloaded page starts empty rather than quietly copying somebody
  // you added an hour ago and forgot.
  const [cc, setCc] = useState({});      // per review; the row itself is ui.jsx's CcRow

  // Approving IS sending, so a send that failed has to say so HERE, the moment you click - it
  // used to return quietly and leave a "NOT SENT" line in the task history for you to find later.
  const decide = async (r, verb) => {
    setBusy(r.ReviewId); setErr(""); setSendErr(null);
    try {
      const { data } = await api.post(`/api/reviews/${r.ReviewId}/decide`,
        { verb, final_text: verb === "approve" ? (edits[r.ReviewId] ?? r.DraftText ?? "") : null, note: null,
          // only on the send: rejecting or "no reply needed" copies nobody on nothing
          cc: verb === "approve" ? (cc[r.ReviewId] || []) : null });
      if (data.send_error) setSendErr({ id: r.ReviewId, msg: data.send_error });
      load(); onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Decide failed"); }
    setBusy(null);
  };

  // A held draft is one the session's findings will rewrite. Sometimes the sender needs telling
  // something today anyway - a reply stuck behind an agent that never finished is worse.
  const release = async (r) => {
    setBusy(r.ReviewId);
    try { await api.post(`/api/reviews/${r.ReviewId}/release`); load(); onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not release it"); }
    setBusy(null);
  };

  const redraft = async (r) => {
    setBusy(r.ReviewId);
    try { await api.post(`/api/reviews/${r.ReviewId}/draft`); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "Redraft failed"); }
    setBusy(null);
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Box sx={{ ...card, px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <FilterPills options={FILTERS} value={filter} onChange={setFilter} />
        <Box sx={{ flex: 1 }} />
        {rows && <Typography variant="caption" sx={{ color: FAINT }}>{rows.length} shown</Typography>}
      </Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mt: 1.5 }}>{err}</Alert>}
      {!rows ? <CircularProgress size={22} sx={{ m: 4 }} /> : !rows.length ? (
        <Empty>{filter === "pending" ? "Queue is clear — nothing needs you."
          : filter === "held" ? "Nothing is waiting on an agent."
          : "Nothing here."}</Empty>
      ) : rows.map((r) => (
        <Box key={r.ReviewId} sx={{ ...card, mt: 1.25, p: 0, overflow: "hidden" }}>
          {/* header strip: what kind of decision this is + who/what it's about */}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", px: 1.5, py: 1,
            bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}` }}>
            <Box sx={{ width: 28, height: 28, borderRadius: 1.5, flexShrink: 0, display: "flex",
              alignItems: "center", justifyContent: "center",
              bgcolor: "#e3e6e1" }}>
              <AutoAwesomeIcon sx={{ fontSize: 15, color: "#6f8a6e" }} />
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: INK, fontWeight: 700, lineHeight: 1.25 }} noWrap>
                {r.Subject || r.Title || "(no subject)"}
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
                {deliveryMeta(r).kind === "zoho_invoice" ? `Zoho invoice · ${deliveryMeta(r).period}`
                  : r.Status === "held" ? "Reply on hold" : r.Kind === "auto" ? "Auto-answered" : "Draft reply"}
                {" · To "}{replyContext(r)} · {timeAgo(r.CreatedAt)}
              </Typography>
            </Box>
            <ChannelIcon channel={r.Channel} />
            <RefChip taskId={r.TaskId} onClick={() => onOpenTask(r.TaskId)} />
            <Chip size="small" label={r.Status} sx={{ height: 19, fontSize: 10, bgcolor: PANEL, border: `1px solid ${BORDER}`, color: DIM }} />
          </Box>
          <Box sx={{ px: 1.5, py: 1.25 }}>
            {r.Reason && (r.DraftText || !/draft/i.test(r.Reason)) && (
              <Typography variant="caption" sx={{ color: "#6f8a6e", display: "block", mb: 0.5 }}>{r.Reason}</Typography>
            )}
            {deliveryMeta(r).kind === "zoho_invoice" && (
              <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 1, px: 1.25, py: 0.8,
                bgcolor: "#eef1ec", border: "1px solid #d9e0d6", borderRadius: 1.5 }}>
                <Typography variant="caption" sx={{ color: INK, fontWeight: 700 }}>{deliveryMeta(r).customer}</Typography>
                <Typography variant="caption" sx={{ color: INK }}>${Number(deliveryMeta(r).amount || 0).toFixed(2)}</Typography>
                <Typography variant="caption" sx={{ color: DIM }}>last month: {deliveryMeta(r).previous_amount == null ? "—" : `$${Number(deliveryMeta(r).previous_amount).toFixed(2)}`}</Typography>
                {deliveryMeta(r).invoice_number && <Typography variant="caption" sx={{ color: DIM }}>Zoho {deliveryMeta(r).invoice_number}</Typography>}
              </Box>
            )}

            {r.Status === "pending" && (
              <Box sx={{ mt: 0.5 }}>
                <Inbound r={r} />
                <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0 }}>
                  <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 800,
                    letterSpacing: "1.5px", flexShrink: 0 }}>TO</Typography>
                  <Typography variant="body2" sx={{ color: INK, fontWeight: 650 }} noWrap>
                    {replyContext(r)}
                  </Typography>
                </Box>
                <CcRow cc={cc[r.ReviewId] || []} setCc={(v) => setCc({ ...cc, [r.ReviewId]: v })}
                  channel={r.Channel} />
                <TextField fullWidth multiline minRows={2} maxRows={r.Kind === "action" ? 24 : 8}
                  value={edits[r.ReviewId] ?? proposalText(r.DraftText)}
                  onChange={(e) => setEdits({ ...edits, [r.ReviewId]: e.target.value })}
                  placeholder={r.DraftText ? "" : "No draft yet — hit Draft with AI"}
                  inputProps={{ style: { fontSize: 12.5, lineHeight: 1.45 } }} />
                <Box sx={{ display: "flex", gap: 0.75, mt: 0.75 }}>
                  {/* ONE approve: it sends whatever is in the box above, edited or not. Two buttons
                      asked you to declare something the text already shows. */}
                  {/* a channel that cannot carry the reply must SAY so: github with replies
                      off gets 'No response required' as THE action, not a send that bounces */}
                  {r.CanSend === false ? (
                    <Button size="small" variant="contained" disableElevation disabled={busy === r.ReviewId}
                      sx={{ bgcolor: "#8a8276", "&:hover": { bgcolor: "#6b6459" } }}
                      title={r.Channel === "github"
                        ? "GitHub replies are off (GitHub card → Reply to issue/PR authors) — close this without sending"
                        : "This channel can't be replied to — close this without sending"}
                      onClick={() => decide(r, "no_reply")}>
                      {busy === r.ReviewId ? "closing…" : "No response required"}
                    </Button>
                  ) : (
                    <Button size="small" variant="contained"
                      disabled={busy === r.ReviewId || !(edits[r.ReviewId] ?? r.DraftText ?? "").trim()}
                      onClick={() => decide(r, "approve")}
                      title={`Sends this response to ${replyContext(r)}`}>
                      {busy === r.ReviewId ? "sending…"
                        : (cc[r.ReviewId] || []).length ? `Approve & send, copying ${(cc[r.ReviewId] || []).length}`
                        : "Approve & send"}
                    </Button>
                  )}
                  {r.CanSend !== false && (
                    <Button size="small" sx={{ color: "#867f74" }} disabled={busy === r.ReviewId}
                      onClick={() => decide(r, "no_reply")}>No reply needed</Button>
                  )}
                  <Button size="small" color="error" disabled={busy === r.ReviewId} onClick={() => decide(r, "reject")}>Reject</Button>
                  <Box sx={{ flex: 1 }} />
                  {deliveryMeta(r).kind !== "zoho_invoice" && <Button size="small" disabled={busy === r.ReviewId} onClick={() => redraft(r)}>
                    {busy === r.ReviewId ? <CircularProgress size={12} /> : r.DraftText ? "Redraft" : "Draft with AI"}
                  </Button>}
                </Box>
                {sendErr?.id === r.ReviewId && (
                  <Alert severity="error" sx={{ mt: 1 }} onClose={() => setSendErr(null)}>
                    <b>Approved, but it did not send.</b> {sendErr.msg}
                    <Box sx={{ mt: 0.5, fontSize: 11.5 }}>
                      The text is kept on the task marked NOT SENT, so nothing is lost — send it by hand,
                      or hand the task to a person on a channel that works.
                    </Box>
                  </Alert>
                )}
              </Box>
            )}
            {r.Status === "held" && (
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
                  <Button size="small" variant="outlined" disabled={busy === r.ReviewId} onClick={() => release(r)}>
                    Answer now anyway
                  </Button>
                  <Button size="small" sx={{ color: DIM }} onClick={() => onOpenTask(r.TaskId)}>Open the task</Button>
                </Box>
                {r.DraftText && (
                  <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: FAINT, display: "block", mt: 0.75 }}>
                    {r.DraftText.slice(0, 300)}
                  </Typography>
                )}
              </Box>
            )}
            {!["pending", "held"].includes(r.Status) && (r.FinalText || r.DraftText) && (
              <Typography variant="caption" sx={{ whiteSpace: "pre-wrap", color: DIM, display: "block", mt: 0.75,
                bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1 }}>
                {(r.FinalText || r.DraftText).slice(0, 500)}
              </Typography>
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
