// What a Timeline row IS, in one word — and the one place that decides it.
//
// The row used to answer this with three overlapping controls: a dot for state, a chip for the
// verdict, and a "needs you" pill that outranked both. Two rows in the same situation could
// therefore read differently depending on which of the three happened to win, and the column as
// a whole was a wall of coloured pills with no single loud thing in it.
//
// So: ONE state per row, from the seven below. It renders as a small mark, its word in quiet
// type, and the card's left edge in the state's colour — colour identifies, it never tints a
// surface, and oxblood is still spent on nothing but "this is on you".
//
// Pure and dependency-free — no theme import, so it runs under bare node
// (test/timelineState.test.mjs) and the Board can read the same table later. Colour is named by
// ROLE, not by hex: theme.jsx stays the only place a colour is chosen and this file cannot drift
// from it. `role: null` is a state that takes no colour at all.
//
// mark: the glyph. word: what it says. role: the theme role its edge and its word take.
// loud: genuinely on you — at most two states may ever be loud, or none of them are.
export const STATES = {
  triaging: { mark: "spinner", word: "triaging", role: "working",
              hint: "the message has arrived — triage is deciding where it belongs" },
  waving:  { mark: "👋", word: "agent waving",  role: "you",     loud: true,
             hint: "the agent stopped and asked you something — open it and answer" },
  working: { mark: "taskuary", word: "agent working", role: "working",
             hint: "a session has this open right now" },
  reply:   { mark: "✉️", word: "reply ready",   role: "you",     loud: true,
             hint: "the agent finished and drafted the answer — read it and send" },
  held:    { mark: "🔒", word: "new sender",    role: "muted",
             hint: "first message from this address — nothing was started; release it if it is real" },
  mine:    { mark: "💡", word: "your note",     role: "info",
             hint: "a note you left yourself — nothing is working it, and nothing will" },
  done:    { mark: "✅", word: "done",          role: "done",
             hint: "closed out — kept for the record" },
  withdrawn: { mark: "🚫", word: "withdrawn",  role: "muted",
             hint: "the sender deleted this where it came from — kept here, with whatever was done about it" },
  answered: { mark: "↩️", word: "you answered", role: "done",
             hint: "you replied to this yourself, outside Taskuary — nothing here is waiting on you" },
  todo:    { mark: "📋", word: "on your list",  role: "working",
             hint: "real work with nobody on it — send it to an agent, or do it yourself" },
  fyi:     { mark: "👀", word: "fyi",           role: null,
             hint: "read it or don't — nothing was started and nothing is owed" },
};

// the categories that mean "somebody told you something and there is nothing to do"
const QUIET = new Set(["info", "automated", "promo", "filed", "ignored", "report", "feed", "yours", "triaging", "assistant"]);

export const HOLD_TAG = "hold:new-sender";
export const hasTag = (row, tag) => String(row?.TaskTags || "").split(/[\s,]+/).includes(tag);

// ORDER IS THE DESIGN. Read top to bottom, first hit wins, and the order is "who has this right
// now", not "what happened to it": an agent asking you a question outranks the fact that the
// message was once classified as coding work, because the question is the only thing you can act
// on. `done` sits above `working` deliberately — a closed task with a stale live session must
// not advertise work in progress.
export function stateOf(row) {
  if (!row) return "fyi";
  // gone at the source. Above everything: a message that no longer exists cannot be the thing
  // you act on, whatever it was classified as while it did.
  if (row.MsgStatus === "withdrawn") return "withdrawn";
  if (row.MsgStatus === "triaging") return "triaging";
  const pending = row.ReviewStatus === "pending";
  if (row.TaskStatus === "done" || row.TaskStatus === "dropped") return pending ? "reply" : "done";
  if (pending) return "reply";                          // a draft on the table is always the headline
  if (row.AgentWaiting) return "waving";
  if (row.Working) return "working";
  if (hasTag(row, HOLD_TAG)) return "held";
  if (row.TaskKind === "note") return "mine";
  // you answered it in Teams or Outlook and never came back here. The reply is ingested as a
  // `context` row (channels.ingest_own_message); until now nothing read it, so a message you
  // had already dealt with sat on your list for good.
  if (row.AnsweredAt) return "answered";
  // "waving" means an AGENT stopped and asked. It is not a synonym for NeedsYou, which only
  // says nobody is moving this - conflating them put the one loud mark on every open task and
  // made the two rows that were genuinely stuck invisible among them.
  if (row.TaskId && !QUIET.has(row.Category)) return "todo";
  return "fyi";
}

// The one state whose word depends on the row: a pending review with nothing written in it is a
// question waiting on you, not a reply waiting to be sent. Same state, same colour, honest word.
const undrafted = (row) => row?.ReviewStatus === "pending" && row?.HasDraft === 0;
export const stateMeta = (key, row) => (key === "reply" && undrafted(row)
  ? { ...STATES.reply, word: "reply needed", hint: "they asked and nothing is drafted yet — open it and write the answer, or have it drafted" }
  : STATES[key] || STATES.fyi);

// The second line, shown only on the row you are actually looking at: who is on it and what it
// is waiting for. Never guessed — every clause comes from a field the server sent.
export function subline(row, ref = (id) => `TQ-${String(id).padStart(4, "0")}`) {
  if (!row) return "";
  const bits = [];
  if (row.TaskId) bits.push(ref(row.TaskId));
  switch (stateOf(row)) {
    case "triaging": bits.push("triage is deciding what this is"); break;
    case "waving":  bits.push(row.Working ? `${row.Working} asked you something` : "waiting on you — nothing is moving it"); break;
    case "working": bits.push(row.Working ? `${row.Working} has this open` : "an agent has this"); break;
    case "reply":   bits.push(undrafted(row) ? "waiting for your answer — nothing drafted yet" : "a reply is drafted — read it and send"); break;
    case "held":    bits.push("first message from this address — nothing started"); break;
    case "mine":    bits.push("your own note — nothing is working it"); break;
    case "todo":    bits.push("nobody is on this yet"); break;
    case "done":    bits.push(row.ReviewStatus === "sent" ? "closed — reply sent" : "closed"); break;
    default:        if (row.RouteReason) bits.push(String(row.RouteReason).replace(/^triage:\s*/, ""));
  }
  return bits.join(" · ");
}
