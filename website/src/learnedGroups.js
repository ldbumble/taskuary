// WHAT TASKUARY KNOWS ABOUT HOW YOU WORK, BY SUBJECT (slice 6 of the memory redesign, 2026-10-25): Visualize drew one LIVE bucket that
// "rides into every prompt" - false since each reader takes its own sections. Now it is the five subjects, each saying who reads it
// (served by /api/learned/graph from the reader matrix, learned_cut.READS), the people lines under the person they are about, and
// what still waits: Watching and Proposed. Pure, so node --test reads it.
export const MARKS = { keep: "Keep", wrong: "Wrong", forget: "Forget" };
export const MARK_HINT = {
  keep: "Keep this line - it is yours from now on, in these words, and nothing rewrites it",
  wrong: "This was never true - it leaves, and Taskuary never writes it back",
  forget: "Not now - it leaves, and comes back only if much more evidence says it again",
};
const PUT_DOWN = new Set(["wrong", "forgotten", "closed", "retired"]);

// the moves a line takes: your own line only Forget (it is not something Taskuary learned wrong); a learned one all three - and one you
// Kept no Keep again: Visualize was pixel-identical after Keep (the Advisor audit's judge, F6, 2026-10-26), so it says Kept instead
export const marksFor = (l) => (!l?.key ? [] : l.own ? ["forget"] : l.kept ? ["wrong", "forget"] : ["keep", "wrong", "forget"]);
// ...and a What changed row carries them once, on the newest row of a line that is not already put down
// (an owner's own line - standing "own" - Forget alone; one no longer anywhere - "gone" - nothing)
export const changeMarks = (r) => (!r?.key || !r.newest || PUT_DOWN.has(r.standing) || r.standing === "gone" ? []
  : r.standing === "own" ? ["forget"] : ["keep", "wrong", "forget"]);

// people lines under each person (their address), in the order they first appear; lines naming nobody last
export const byPerson = (ls) => {
  const out = new Map();
  for (const l of ls) { const k = l.subject || ""; if (!out.has(k)) out.set(k, []); out.get(k).push(l); }
  return [...out].sort(([a], [b]) => (a === "") - (b === "")).map(([subject, lines]) => ({ subject, lines }));
};

// the five as an older server (or the demo's recorded page) names none: the same words learned_cut.reads_label says
export const SECTIONS = [
  { slug: "people", title: "Your people", reads: "read by triage (priority only) · drafts · the Advisor · the Assistant · agents" },
  { slug: "care", title: "What you care about", reads: "read by triage · the Advisor · the Assistant · agents" },
  { slug: "work", title: "How you work", reads: "read by triage · the Advisor · the Assistant · agents" },
  { slug: "promises", title: "Promises", reads: "read by triage · the Advisor · the Assistant · agents" },
  { slug: "bring", title: "What to bring up", reads: "read by triage · the Assistant · agents" },
];

// [{slug, title, reads, lines, people?}] - the five subjects in the document's order, then Watching and Proposed
export const groupLines = (g) => {
  const ls = g?.lines || [];
  const subj = (g?.sections?.length ? g.sections : SECTIONS).map((s) => {
    const lines = ls.filter((l) => l.status === "live" && l.section_slug === s.slug);
    return { ...s, lines, ...(s.slug === "people" ? { people: byPerson(lines) } : {}) };
  });
  return [...subj,
    { slug: "watching", title: "Watching", reads: "read by nobody yet - still earning it", lines: ls.filter((l) => l.status === "hypothesis") },
    { slug: "proposed", title: "Proposed", reads: "your call - each would hide mail", lines: ls.filter((l) => l.status === "proposed") }];
};

// a person's page in the Docs tree (people_pages.py: person-<address>) - linked only where it exists
export const personDoc = (subject, people = []) => {
  const name = subject ? `person-${subject}` : "";
  return name && people.some((p) => (p?.name || p) === name) ? name : "";
};
