// "IS IT WORKING?" (the owner, 2026-10-22, picked from the gaps): whether the app's calls stood, as numbers - each call against the
// owner's own next move, over 7 and 30 days (GET /api/working, taskuary/working.py). Numbers, never a sentence about them.
export const WORKING_ROWS = [
  ["Drafts sent", (w) => w.drafts.sent, (w) => [[w.drafts.unedited, "as drafted"], [w.drafts.edited, "edited"], [w.drafts.redrafted, "redrafted"]]],
  ["Triage calls", (w) => w.triage.verdicts, (w) => [[w.triage.verdicts - w.triage.overturned, "stood"], [w.triage.overturned, "overturned"]]],
  ["Agent results", (w) => w.agents.results, (w) => [[w.agents.accepted, "marked done"], [w.agents.continued, "continued"], [w.agents.waiting, "waiting on you"]]],
];

// one cell: the count, then its non-zero parts - "12: 8 as drafted · 3 edited · 1 redrafted"; "none" for an empty window
export const workingCell = (n, parts) => (n ? `${n}: ${parts.filter(([k]) => k > 0).map(([k, w]) => `${k} ${w}`).join(" · ")}` : "none");

export const workingTable = (windows) => WORKING_ROWS.map(([label, n, parts]) => ({ label, cells: (windows || []).map((w) => workingCell(n(w), parts(w))) }));
