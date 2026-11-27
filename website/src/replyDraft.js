// A REPLY IS THE TASK'S AGENT'S (the owner, 2026-11-27: "side model should never work in agent canvas"): Reply, Redraft and Draft with AI
// are his ask to that agent (server.open_reply) - it writes the reply and raises its card. Nothing here drafts.
import { withSignature } from "./signature.js";

// The owner's own edit always stands; the filed draft shows under it otherwise.
export const boxText = ({ text, draft, drafting, signature }) => text ?? (drafting && !draft ? "" : withSignature(draft, signature));

// A NEW DRAFT FILED UNDER AN OPEN CARD IS SHOWN (2026-11-04): the owner's edit was kept only for the draft it was made on when the card was
// drawn again - a card left open kept its edit over every draft after it, and an emptied box stayed empty under "✓ Rewritten". What the box
// holds once the filed draft changes: the edit held for this new one (another card's, heldOf), else the draft itself (null) - unless the
// owner's edit is being shown beside a refreshed draft (`keep`: the interrupt's compare), which stays theirs
// ...AND NEVER OVER WORDS HE TYPED (the owner, 2026-11-26: "never even overwrite an edit of a text for any card"): `keep` is every case but
// his own ask for other words - the server holds what he typed and writes no draft over it (store.hold_review_edit), so a draft that did
// change under words it no longer holds is the one he asked for. A box he emptied holds no words: the new draft shows
export const editAfterRefile = ({ text, keep }) => (keep && String(text ?? "").trim() ? text : null);
export const heldWords = (stored) => { try { return (typeof stored === "string" ? JSON.parse(stored) : stored)?.text ?? ""; } catch { return ""; } };

// THE REPLY PRESS: his ask to the message's task's agent - his words, else the press's label (`verb`: reply | redraft) - the task made
// where it has none. Resolves with {taskId, ref, asked, receipt}. `line`: the Assistant's under-way line, said again by the server.
export async function askReply(api, mid, instruction = null, verb = "reply", line = null) {
  const { data } = await api.post(`/api/messages/${mid}/reply`, { instruction, verb, ...(line ? { line } : {}) });
  return data;
}

// ...BUT ON AN FYI IT IS HIS OWN (the owner, 2026-11-27, option A): the row's Reply opens HIS box on the FYI itself (assistantCards.OwnReply) -
// To and Subject filled in, his words, his Send; no agent, no task (server.open_reply's `own`)
export const OWN_REPLY = "tq-own-reply";
export const openOwnReply = (key) => window.dispatchEvent(new CustomEvent(OWN_REPLY, { detail: { key } }));
// ...the box's envelope (no `text`), or his words sent on the one Send road - {to, cc, subject, reviewId?, ok?, send_error?}
export async function ownReply(api, mid, text = null) {
  const { data } = await api.post(`/api/messages/${mid}/reply`, { write: true, own: true, ...(text != null ? { text } : {}) });
  return data;
}
