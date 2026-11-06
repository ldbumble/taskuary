// The landing card's words (LandingCard.jsx), apart from React so a node test reads them.
import { plural as n } from "./timeWords.js";

export const HOW = { rebase: "Rebase and fast-forward", merge: "Merge commit", pr: "Open a PR", discard: "Discard" };

export function landingWords(s) {
  if (!s) return {};
  const stat = `${n(s.changed || 0, "file")} changed, +${s.plus || 0} −${s.minus || 0}`
    + (s.own ? ` · ${n(s.ahead || 0, "commit")} ahead` : " since the task started");
  const p = s.proposal;
  return {
    stat,
    proposal: p?.how ? `The agent proposes ${HOW[p.how] || p.how}${p.why ? ` — ${p.why}` : ""}.` : "",
    hint: s.own ? "A conflict lands nothing: the agent gets it to resolve. Open a PR pushes the branch and opens a draft." : "",
    landed: s.landed ? `Landed · ${HOW[s.landed.how] || s.landed.how}` : "",
  };
}
