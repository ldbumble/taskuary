// What the Agent work card draws from a session record (taskuary/sessionrecord.py) - kept out of the component so the
// one rule that matters is testable: the result is said ONCE (the owner, 2026-10-10: "make sure it's full and complete
// record but don't duplicate sections").

const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();

// the steps the full record lists. A conversation's own turns are already on screen in the chat under the card, so for a
// general session only its WORKING is listed (thoughts, tools, plans, errors); and the step that is the result itself
// becomes a pointer back to it rather than a second copy.
export const recordSteps = (s) => {
  const chat = s?.source === "conversation", res = norm(s?.result);
  return (s?.steps || [])
    .filter((x) => !(chat && (x.k === "you" || x.k === "said")))
    .map((x) => (x.k === "said" && res && norm(x.text) === res ? { ...x, k: "result" } : x));
};

// the report's parts that are not the result again
export const reportParts = (s) => {
  const r = s?.report || {}, res = norm(s?.result);
  return [["Decided", r.decided], ["Changed", r.changed], ["Summary", r.summary]]
    .filter(([, v]) => norm(v) && norm(v) !== res);
};

const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

// one line of facts: who, when, and how much it did - each only when there is some
export const recordFacts = (s) => {
  const c = s?.counts || {};
  return [s?.cli || s?.by, s?.at && s.at.slice(0, 16),
    c.thought ? plural(c.thought, "thought") : "", c.tool ? plural(c.tool, "step") : "",
    s?.files?.length ? plural(s.files.length, "file") : ""].filter(Boolean);
};

// is there anything behind "Full record" that the card does not already show?
export const hasMore = (s) => !!(recordSteps(s).some((x) => x.k !== "result") || reportParts(s).length || s?.plan?.length || s?.files?.length);

const SOURCES = { conversation: "the conversation", screen: "what was on screen" };
export const sourceLabel = (src) => SOURCES[src] || src || "";
