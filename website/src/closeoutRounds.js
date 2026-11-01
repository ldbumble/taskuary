// CLOSE OUT IN ROUNDS (the owner, 2026-11-01, on a task new mail had reopened: "Why is this showing not the last response i sent ... now
// that a new message can reopen close out can happen multiple times.. let's update the close out to match the agent runs"). Close out
// showed the newest reply ever sent and the last close's note over the message that reopened the task - an old round read as the
// current one, its "Sent ... stays open" over a reply nobody had written yet. Now the task's history is cut into rounds, one per time it
// was answered and put down, and the page draws the current round where Close out always stood and the earlier ones folded under it, a
// line each, as an agent's earlier runs fold (AgentRecord.EarlierRuns).
//
// A round ends where the next one starts: at a reopen (server store.closeouts - new mail's, or a Reopen press), or at a message from them
// that came after the round was already answered or closed. A reply belongs to the round it went in, a close (and its note) ends it.
const SENT = new Set(["approved", "edited", "sent"]);
const UNSENT = new Set(["no_reply", "closed_unsent", "rejected", "superseded"]);
const isReply = (r) => r.Kind !== "action" && r.Kind !== "slot";
const fresh = (start) => ({ start, ins: [], sent: [], unsent: [], close: null });

// `messages` the task's own (no review receipts), `outside` what the owner sent outside Taskuary (taskLifecycle.sentElsewhere),
// `closeouts` the server's closes and reopens in order, `open` whether the task is open now, `ms` the app's one clock (dates.tsMs).
// Oldest round first, each { n, start, ins, sent: [{ at, text, review | msg }], unsent: [review], close, answering }.
export const closeoutRounds = ({ messages = [], reviews = [], outside = [], closeouts = [], open = true, ms = (s) => Date.parse(s) || 0 } = {}) => {
  const t = (s) => ms(s) || 0;
  // ...a message by when it was written, or when it reached us if that is earlier: a sender's clock set ahead is not a later round
  const came = (m) => { const a = [m.SentAt, m.CreatedAt].map(t).filter(Boolean); return a.length ? Math.min(...a) : 0; };
  const ev = [
    ...messages.filter((m) => m.Direction !== "out" && m.Status !== "context" && !m.ReviewSent).map((m) => ({ k: 0, t: came(m), m })),
    ...reviews.filter((r) => isReply(r) && SENT.has(r.Status) && String(r.FinalText || r.DraftText || "").trim())
      .map((r) => ({ k: 1, t: t(r.DecidedAt || r.CreatedAt), sent: { at: r.DecidedAt || r.CreatedAt, text: r.FinalText || r.DraftText, review: r } })),
    ...outside.map((m) => ({ k: 1, t: t(m.SentAt || m.CreatedAt), sent: { at: m.SentAt || m.CreatedAt, text: m.OwnText || m.BodyText || "", msg: m } })),
    ...reviews.filter((r) => isReply(r) && UNSENT.has(r.Status) && String(r.DraftText || "").trim()).map((r) => ({ k: 2, t: t(r.DecidedAt || r.CreatedAt), unsent: r })),
    // ...a close and a reopen in the same second keep the server's order (store.closeouts takes them in turn)
    ...closeouts.map((c, i) => ({ k: 3, i, t: t(c.at), c })),
  ].sort((a, b) => a.t - b.t || a.k - b.k || (a.i || 0) - (b.i || 0));
  const rounds = [];
  let cur = fresh(0);
  const next = (at) => { rounds.push(cur); cur = fresh(at); };
  for (const e of ev) {
    if (e.m) { if (cur.close || cur.sent.length) next(e.t); cur.ins.push(e.m); }
    else if (e.sent) cur.sent.push(e.sent);      // ...one sent after the close, with nothing new between, is that round's still
    else if (e.unsent) cur.unsent.push(e.unsent);
    else if (e.c.what === "closed") { if (cur.close) next(e.t); cur.close = e.c; }
    else if (cur.close) next(e.t);
  }
  // ...and a task open again over its last close is a new round already - a Reopen drawn before the server says so (reopenedDetail)
  if (open && cur.close) next(t(cur.close.at) + 1);
  rounds.push(cur);
  return rounds.filter((r, i) => i === rounds.length - 1 || r.ins.length || r.sent.length || r.unsent.length || r.close).map((r, i) => {
    const first = r.sent[0] ? t(r.sent[0].at) : Infinity;
    const asked = r.ins.filter((m) => came(m) <= first);
    return { ...r, n: i + 1, answering: (asked.length ? asked : r.ins).at(-1) || null };
  });
};

// ...the current round's reviews: every one but those an earlier round already holds, so what it sent and what it closed without sending
// are its own (a pending draft is always the current round's)
export const roundReviews = (reviews = [], rounds = []) => {
  const old = new Set(rounds.slice(0, -1).flatMap((r) => [...r.sent.map((s) => s.review), ...r.unsent]).filter(Boolean).map((r) => r.ReviewId));
  return reviews.filter((r) => !old.has(r.ReviewId));
};

// AN EARLIER ROUND IN ONE LINE (the owner's words, 2026-11-01): what was done and when - "Replied to Erin Blake · Oct 30, 12:36 PM",
// "Marked done · Oct 31", "Closed with a note" - and the words that went (or the note, or what they asked) after it.
// `when` formats a time, `day` a date.
export const roundHead = (r, { when = String, day = String } = {}) => {
  const last = r.sent.at(-1), who = last?.review?.FromName || r.answering?.FromName || r.answering?.FromEmail || "";
  const what = last ? `${last.msg ? "You answered" : "Replied to"}${who ? ` ${who}` : ""}${last.msg?.SourceName ? ` in ${last.msg.SourceName}` : ""}`
    : r.close?.note ? "Closed with a note"
    : r.unsent.length && r.close ? "Closed without sending"
    : r.close ? (r.close.to === "dropped" ? "Put down" : "Marked done")
    : r.ins.length ? "Not answered" : "";
  const at = last ? when(last.at) : r.close ? (r.close.note ? when(r.close.at) : day(r.close.at)) : "";
  const line = String(last?.text || r.close?.note || r.unsent.at(-1)?.DraftText || r.answering?.ReadText || r.answering?.BodyText || "").replace(/\s+/g, " ").trim();
  return { what, at, head: [what, at].filter(Boolean).join(" · "), line };
};
