// THREE PRIORITIES (the owner, 2026-10-25: "be careful when updating triage to have 3 categories, important/urgent/regular and make
// sure it makes sense"): urgent is time-critical and on you now - today's meaning, its shade and its behaviour unchanged; important
// matters because of WHO or WHAT (people and topics your memory says you care about) but can wait; regular is everything else. The
// same words as taskuary/processing_order.py, and a task saved before the change reads in them: low and normal are regular, high is
// important. Importance never moves a row - the rail stays by arrival; it is a quiet mark in the row's own place.
export const PRIORITIES = ["regular", "important", "urgent"];
const LEGACY = { low: "regular", normal: "regular", medium: "regular", high: "important" };
export const level = (v) => { const s = String(v || "").trim().toLowerCase(); return PRIORITIES.includes(s) ? s : LEGACY[s] || "regular"; };
// a row is important when its task (or the ask triage judged) is - and urgent outranks it: an urgent row wears urgent's shade alone
export const isImportant = (item, urgent = false) => !urgent && !item?.settling && level(item?.priority) === "important";
