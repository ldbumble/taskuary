// AN AGENT'S DRAFT, in the one chat (the owner, 2026-11-06): its card is drawn under the turn that wrote it, Send under it - no notice that
// points elsewhere, for there is nowhere else. What is left here is which drafts are the page's. A draft the owner answered
// themselves is not drawn at all (the owner, 2026-11-09): the agent re-plans on their line and retires it (verdicts.not_needed) - no banner over it.
import { deliveryTo } from "./replyDelivery.js";

// AN EARLIER SESSION'S DRAFT IS NOT THE REPLY (the owner, 2026-11-03: "when you continue on general agent it shows the prior reply on bottom that
// the agent generated. Don't show that reply if it was based off another general session not the latest one"). A draft keeps the session that
// wrote it (DraftSid; "owner" once the owner edited it); while another session is live (`sid`) its pending draft is not the page's - the server
// holds it the same way (wrapup.stale_draft) and this keeps a read from before the hold from drawing it, its notice or its Send
export const earlierSession = (r, sid) => !!sid && r?.Status === "pending" && String(r.DraftBy || "").startsWith("agent:")
  && !!r.DraftSid && r.DraftSid !== "owner" && r.DraftSid !== sid;
export const latestDrafts = (reviews = [], sid = "") => (reviews || []).filter((r) => !earlierSession(r, sid));
// the person by name ("Erin Blake", not "Erin Blake <erin@...>")
export const draftedTo = (r) => deliveryTo(r).split(",").map((a) => a.replace(/\s*<[^>]*>/, "").trim() || a.trim()).filter(Boolean).join(", ");
