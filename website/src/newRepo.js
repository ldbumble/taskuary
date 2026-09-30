// WHICH CHECKOUT A NEW SESSION OPENS IN, decided before the task exists (the owner, 2026-09-30: "can't choose repo to create
// coding session in"). Three answers: AUTO (the default - a repository the words name outright, else nothing, and the server
// guesses from the ask exactly as it always did), a KNOWN repository from the list, or ANOTHER one by name and folder.
// Pure, so the rule is tested without a page.
import { namedRepo } from "./repoNames.js";

export const AUTO = "";
export const OTHER = "\u0000other";

// -> { repo, path, named, needsPath }: repo is what the task's `repo:` tag carries (null = let the server guess),
// path is a folder to save for it when the agent has none.
export const chosenRepo = ({ rows = [], pick = AUTO, said = "", name = "", path = "" }) => {
  if (pick === OTHER) { const repo = String(name).trim(); return { repo: repo || null, path: String(path).trim() || null, named: false, needsPath: !!repo && !String(path).trim() }; }
  if (pick) {
    const row = rows.find((r) => r.repo === pick);
    const need = !!row && !row.has_path;
    return { repo: pick, path: need ? String(path).trim() || null : null, named: false, needsPath: need && !String(path).trim() };
  }
  const repo = namedRepo(rows, said) || null;
  const row = rows.find((r) => r.repo === repo);
  const need = !!row && !row.has_path;
  return { repo, path: need ? String(path).trim() || null : null, named: !!repo, needsPath: need && !String(path).trim() };
};
