// A DRAFT THE AGENT REPLACED IN A LATER TURN (wrapup.REPLACED; the owner, 2026-11-10: "it should go gray and then it should generate new email
// action box under it with new email.."): its record where it stood - greyed, its words as they were, nothing to press.
// ...AND NO BUTTON (the owner, 2026-11-11: "a card that cannot be pressed shows no button" - the card round, 2026-11-12: it was the whole reply
// card drawn again, dimmed, with a greyed Send and a live-looking Add CC and Add BCC under the new draft's own). ONE look for a draft that was
// rewritten, whichever way the server kept it (GeneralWorkspace PastCard: `tq-conv-past`)
import React from "react";

export default function ReplacedDraft({ review: r }) {
  return (
    <div className="tq-conv-past" data-tq-replaced={r.ReviewId} data-tq-past-card="superseded" role="note">
      <div className="tq-conv-past-head" data-tq-replaced-line="">Earlier draft - rewritten below</div>
      <div className="tq-conv-past-words" dir="auto">{String(r.DraftText || "").trim()}</div>
    </div>
  );
}
