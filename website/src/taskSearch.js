// Search a Tasks page in the browser while the SQL round-trip is in flight. /api/tasks?q=
// is the real archive search; this is the same AND-of-terms so a keystroke still narrows
// the rows already on screen.
const FIELDS = [
  "ref", "TaskId", "Title", "Summary", "Kind", "Status", "Priority", "Assignee", "Source",
  "SourceRef", "Tags", "SearchChannels", "SearchSources", "SearchSubjects", "SearchPeople",
  "SearchEmails", "SearchExternalIds", "SearchLinks",
];

const folded = (value) => String(value ?? "").toLocaleLowerCase();

export const taskMatchesQuery = (task, query) => {
  const terms = folded(query).trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const haystack = folded(FIELDS.map((field) => task?.[field]).join(" "));
  return terms.every((term) => haystack.includes(term));
};
