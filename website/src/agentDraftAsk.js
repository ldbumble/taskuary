// AN AGENT'S DRAFT, in the one chat (the owner, 2026-11-06): its card is drawn under the turn that wrote it, Send under it - no notice that
// points elsewhere, for there is nowhere else. What is left here is which drafts are the page's. A draft the owner answered
// themselves is not drawn at all (the owner, 2026-11-09): the agent re-plans on their line and retires it (verdicts.not_needed) - no banner over it.
import { deliveryTo } from "./replyDelivery.js";

// the person by name ("Erin Blake", not "Erin Blake <erin@...>")
export const draftedTo = (r) => deliveryTo(r).split(",").map((a) => a.replace(/\s*<[^>]*>/, "").trim() || a.trim()).filter(Boolean).join(", ");
